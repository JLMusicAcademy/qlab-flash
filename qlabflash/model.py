"""Translation between QLab's cue tree and the mic-mute grid.

This layer is deliberately pure (no networking): given the cue-list JSON that
QLab returns plus a lookup of each cue's OSC message text, it produces the grid
of rows x mics, and it turns edited checkbox states back into the list of OSC
writes that must be sent to QLab.

The mental model
----------------
Each *row* in the grid is a top-level cue of the chosen cue list (typically a
Group cue named like "Cue 12 - Top of Act 2"). Inside that group live the
per-channel Network cues that talk to the X32, e.g. a cue whose OSC message is
``/ch/03/mix/on 1``. We scan a row's whole subtree for cues whose message
matches the configured channel pattern and map them onto mic columns.

A checked box means unmuted (channel ON); an unchecked box means muted
(channel OFF).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from .config import Config

# Cue "type" strings that contain other cues rather than carrying a mic message.
CONTAINER_TYPES = {"Group", "Cue List", "Cart", "cuelist", "group", "cart"}


@dataclass
class MicCell:
    """One checkbox: mic ``channel`` within a given row."""
    channel: int                       # 1-based mic number.
    cue_uid: Optional[str] = None      # Backing QLab cue, if one exists.
    original_unmuted: Optional[bool] = None  # State read from QLab.
    unmuted: bool = False              # Current (possibly edited) state.

    @property
    def exists(self) -> bool:
        """Whether there is a real QLab cue backing this checkbox."""
        return self.cue_uid is not None

    @property
    def dirty(self) -> bool:
        return self.exists and self.unmuted != self.original_unmuted


@dataclass
class CueRow:
    cue_uid: str
    number: str
    name: str
    cells: Dict[int, MicCell] = field(default_factory=dict)

    @property
    def label(self) -> str:
        parts = [p for p in (self.number, self.name) if p]
        return " ".join(parts) if parts else self.cue_uid


@dataclass
class Cue:
    """Light wrapper around one cue object from QLab's cueLists reply."""
    uid: str
    number: str
    name: str
    type: str
    children: List["Cue"] = field(default_factory=list)

    @property
    def is_container(self) -> bool:
        return self.type in CONTAINER_TYPES or bool(self.children)

    @classmethod
    def from_json(cls, obj: dict) -> "Cue":
        return cls(
            uid=str(obj.get("uniqueID", "")),
            number=str(obj.get("number", "") or ""),
            name=str(obj.get("name", "") or obj.get("listName", "") or ""),
            type=str(obj.get("type", "") or ""),
            children=[cls.from_json(c) for c in (obj.get("cues") or [])],
        )

    def walk(self):
        """Yield this cue and every descendant, depth-first."""
        yield self
        for child in self.children:
            yield from child.walk()

    def leaf_uids(self) -> List[str]:
        """UIDs of every non-container cue in this subtree (mic-cue candidates)."""
        return [c.uid for c in self.walk() if not c.is_container]


class GridModel:
    """The full grid: rows of cues x ``mic_count`` mic columns."""

    def __init__(self, config: Config):
        self.config = config
        self.rows: List[CueRow] = []
        self._pattern = re.compile(config.channel_pattern)

    # -- Parsing QLab message text -----------------------------------------
    def parse_channel(self, text: str) -> Optional[tuple]:
        """Return ``(channel, unmuted_or_None)`` if ``text`` is a mic message."""
        if not text:
            return None
        match = self._pattern.match(text)
        if not match:
            return None
        chan = int(match.group("chan"))
        if chan < 1 or chan > self.config.mic_count:
            return None
        unmuted: Optional[bool] = None
        # The pattern defines an (optional) ``state`` group; when the message
        # carried no explicit argument it simply comes back as None.
        state_str = match.groupdict().get("state")
        if state_str is not None:
            unmuted = self.config.is_unmuted_value(int(state_str))
        return chan, unmuted

    # -- Building the grid -------------------------------------------------
    def build(self, top_level_cues: List[Cue], get_text: Callable[[str], Optional[str]]):
        """Populate ``self.rows`` from the chosen cue list's top-level cues.

        ``get_text(uid)`` returns a cue's OSC message text (or None).
        """
        rows: List[CueRow] = []
        for cue in top_level_cues:
            row = CueRow(cue_uid=cue.uid, number=cue.number, name=cue.name)
            for descendant in cue.walk():
                if descendant.is_container:
                    continue
                parsed = self.parse_channel(get_text(descendant.uid) or "")
                if parsed is None:
                    continue
                chan, unmuted = parsed
                state = bool(unmuted) if unmuted is not None else False
                row.cells[chan] = MicCell(
                    channel=chan,
                    cue_uid=descendant.uid,
                    original_unmuted=state,
                    unmuted=state,
                )
            rows.append(row)
        self.rows = rows
        return rows

    # -- Producing writes --------------------------------------------------
    def dirty_writes(self) -> List[tuple]:
        """List of ``(cue_uid, message_text)`` for changed, backed cells."""
        writes = []
        for row in self.rows:
            for cell in row.cells.values():
                if cell.dirty:
                    writes.append((cell.cue_uid, self.message_for(cell)))
        return writes

    def all_writes(self) -> List[tuple]:
        """Writes for every backed cell, regardless of dirty state."""
        writes = []
        for row in self.rows:
            for cell in row.cells.values():
                if cell.exists:
                    writes.append((cell.cue_uid, self.message_for(cell)))
        return writes

    def message_for(self, cell: MicCell) -> str:
        state = self.config.channel_state_value(cell.unmuted)
        return self.config.write_template.format(chan=cell.channel, state=state)

    def mark_committed(self) -> None:
        """After a successful submit, current state becomes the baseline."""
        for row in self.rows:
            for cell in row.cells.values():
                if cell.exists:
                    cell.original_unmuted = cell.unmuted
