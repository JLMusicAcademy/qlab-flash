"""Translation between QLab's cue tree and the mic-mute grid.

This layer is deliberately pure (no networking): given the cue-list JSON that
QLab returns plus a lookup of each cue's OSC message text, it mirrors QLab's
hierarchy as a tree of rows and decides — dynamically, for any workspace shape —
which cues own a set of mics.

How a "mic look" is found (works at any nesting depth)
------------------------------------------------------
A *mic cue* is a leaf cue whose OSC message matches the channel pattern, e.g.
``/ch/03/mix/on 1``. We want to attach the 32 mic checkboxes to the cue the user
thinks of as "the cue" — but that could be a top-level group, a group three
levels down, or the mic cue itself, and we can't assume.

The rule: a cue is a **look anchor** if its subtree contains mic cues with *no
duplicated channel numbers*, and it is the highest such cue (its parent's
subtree does have duplicates, meaning the parent spans more than one look). This
makes the grouping fully dynamic:

* ``Cue → mics``                      → Cue is the look
* ``Cue → Mics group → mics``         → Cue is the look
* ``Cue → G2 → Mics group → mics``    → Cue is the look
* ``Act → Cue1, Cue2 → … → mics``     → Act spans two looks (duplicate channels),
                                         so Cue1 and Cue2 each become looks.

A checked box means unmuted (channel ON); an unchecked box means muted (OFF).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterator, List, Optional

from .config import Config

# Cue "type" strings that contain other cues rather than carrying a mic message.
CONTAINER_TYPES = {"Group", "Cue List", "Cart", "cuelist", "group", "cart"}


@dataclass
class MicCell:
    """One checkbox: mic ``channel`` backed by a single QLab mic cue."""
    channel: int                       # 1-based mic number.
    cue_uid: Optional[str] = None      # Backing QLab cue, if one exists.
    original_unmuted: Optional[bool] = None  # State read from QLab.
    unmuted: bool = False              # Current (possibly edited) state.

    @property
    def exists(self) -> bool:
        return self.cue_uid is not None

    @property
    def dirty(self) -> bool:
        return self.exists and self.unmuted != self.original_unmuted


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

    def walk(self) -> Iterator["Cue"]:
        yield self
        for child in self.children:
            yield from child.walk()

    def leaf_uids(self) -> List[str]:
        """UIDs of every non-container cue in this subtree (mic-cue candidates)."""
        return [c.uid for c in self.walk() if not c.is_container]


@dataclass
class RowNode:
    """One row in the worksheet, mirroring a QLab cue (at any depth)."""
    uid: str
    number: str
    name: str
    type: str
    original_name: str
    parent: Optional["RowNode"] = None
    children: List["RowNode"] = field(default_factory=list)

    # The mic cell this cue carries itself, if it is an individual mic cue.
    own_cell: Optional[MicCell] = None
    # Channel -> MicCell shown on this row (aggregated set on a look anchor, the
    # single own cell on a mic cue, empty for everything else).
    cells: Dict[int, MicCell] = field(default_factory=dict)

    is_anchor: bool = False
    # Whether the subtree's mic channels are all distinct (internal bookkeeping).
    _unique: bool = False

    @property
    def display_name(self) -> str:
        if self.name:
            return self.name
        if self.number:
            return f"(cue {self.number})"
        return self.uid

    @property
    def name_dirty(self) -> bool:
        return self.name != self.original_name

    def walk(self) -> Iterator["RowNode"]:
        yield self
        for child in self.children:
            yield from child.walk()


class GridModel:
    """The worksheet: a tree of cue rows x ``mic_count`` mic columns."""

    def __init__(self, config: Config):
        self.config = config
        self.roots: List[RowNode] = []
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
        state_str = match.groupdict().get("state")
        if state_str is not None:
            unmuted = self.config.is_unmuted_value(int(state_str))
        return chan, unmuted

    def candidate_uids(self, top_level_cues: List[Cue]) -> List[str]:
        """Every leaf cue under the given cues — the mic-cue candidates to fetch."""
        uids: List[str] = []
        for cue in top_level_cues:
            uids.extend(cue.leaf_uids())
        return uids

    # -- Building the tree -------------------------------------------------
    def build_tree(self, top_level_cues: List[Cue],
                   get_text: Callable[[str], Optional[str]]) -> List[RowNode]:
        roots = [self._make_node(cue, None, get_text) for cue in top_level_cues]
        for root in roots:
            self._annotate(root, parent_unique=False)
        self.roots = roots
        return roots

    def _make_node(self, cue: Cue, parent: Optional[RowNode],
                   get_text: Callable[[str], Optional[str]]) -> RowNode:
        node = RowNode(uid=cue.uid, number=cue.number, name=cue.name,
                       type=cue.type, original_name=cue.name, parent=parent)
        parsed = self.parse_channel(get_text(cue.uid) or "")
        if parsed is not None:
            chan, unmuted = parsed
            state = bool(unmuted) if unmuted is not None else False
            node.own_cell = MicCell(channel=chan, cue_uid=cue.uid,
                                    original_unmuted=state, unmuted=state)
        node.children = [self._make_node(c, node, get_text) for c in cue.children]
        return node

    def _subtree_cells(self, node: RowNode) -> List[MicCell]:
        cells: List[MicCell] = []
        if node.own_cell is not None:
            cells.append(node.own_cell)
        for child in node.children:
            cells.extend(self._subtree_cells(child))
        return cells

    def _annotate(self, node: RowNode, parent_unique: bool) -> None:
        cells = self._subtree_cells(node)
        channels = [c.channel for c in cells]
        node._unique = bool(channels) and len(channels) == len(set(channels))
        # Highest cue whose channels are all distinct = the look anchor.
        node.is_anchor = node._unique and not parent_unique

        if node.is_anchor:
            node.cells = {c.channel: c for c in cells}
        elif node.own_cell is not None:
            # An individual mic cue below an anchor shows its single box (the
            # same MicCell object the anchor aggregates, so edits stay in sync).
            node.cells = {node.own_cell.channel: node.own_cell}
        else:
            node.cells = {}

        for child in node.children:
            self._annotate(child, parent_unique=node._unique)

    # -- Iteration ---------------------------------------------------------
    def iter_rows(self) -> Iterator[RowNode]:
        for root in self.roots:
            yield from root.walk()

    def anchors(self) -> List[RowNode]:
        return [n for n in self.iter_rows() if n.is_anchor]

    def _own_cells(self) -> Iterator[MicCell]:
        for node in self.iter_rows():
            if node.own_cell is not None:
                yield node.own_cell

    # -- Producing writes --------------------------------------------------
    def dirty_writes(self) -> List[tuple]:
        return [(c.cue_uid, self.message_for(c))
                for c in self._own_cells() if c.dirty]

    def all_writes(self) -> List[tuple]:
        return [(c.cue_uid, self.message_for(c))
                for c in self._own_cells() if c.exists]

    def name_writes(self) -> List[tuple]:
        """`(uid, new_name)` for every cue whose name was edited."""
        return [(n.uid, n.name) for n in self.iter_rows()
                if n.name_dirty and n.uid]

    def message_for(self, cell: MicCell) -> str:
        state = self.config.channel_state_value(cell.unmuted)
        return self.config.write_template.format(chan=cell.channel, state=state)

    def mic_dirty_count(self) -> int:
        return sum(1 for c in self._own_cells() if c.dirty)

    def name_dirty_count(self) -> int:
        return sum(1 for n in self.iter_rows() if n.name_dirty and n.uid)

    def mark_committed(self) -> None:
        """After a successful submit, current state becomes the baseline."""
        for cell in self._own_cells():
            if cell.exists:
                cell.original_unmuted = cell.unmuted
        for node in self.iter_rows():
            node.original_name = node.name
