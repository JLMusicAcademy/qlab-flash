"""High-level workflow: connect, read the grid, push edits back.

The GUI uses this so it never has to know about OSC addresses or cue trees.
"""

from __future__ import annotations

from typing import Callable, List, Optional

from .config import Config
from .model import Cue, GridModel
from .qlab import QLabClient, QLabError


class WorkspaceSession:
    def __init__(self, client: QLabClient, workspace_id: str, config: Config):
        self.client = client
        self.workspace_id = workspace_id
        self.config = config
        self.model = GridModel(config)
        self.cue_lists: List[Cue] = []

    # -- loading ------------------------------------------------------------
    def fetch_cue_lists(self) -> List[Cue]:
        raw = self.client.cue_lists(self.workspace_id)
        self.cue_lists = [Cue.from_json(obj) for obj in raw]
        return self.cue_lists

    def load_grid(self, cue_list_index: int = 0,
                  progress: Optional[Callable[[str], None]] = None) -> GridModel:
        """Read the mic state for every top-level cue in a cue list."""
        if not self.cue_lists:
            self.fetch_cue_lists()
        if not self.cue_lists:
            raise QLabError("No cue lists found in this workspace.")
        cue_list = self.cue_lists[min(cue_list_index, len(self.cue_lists) - 1)]
        top_level = cue_list.children

        # Gather every leaf cue under this list, then fetch their OSC messages.
        leaf_uids: List[str] = []
        for cue in top_level:
            leaf_uids.extend(cue.leaf_uids())
        if progress:
            progress(f"Reading {len(leaf_uids)} cues...")

        prop = self.config.osc_message_property
        texts = self.client.get_cue_properties(self.workspace_id, leaf_uids, prop)

        self.model.build(top_level, lambda uid: texts.get(uid))
        return self.model

    # -- submitting ---------------------------------------------------------
    def submit(self, only_dirty: bool = True,
               progress: Optional[Callable[[int, int], None]] = None) -> int:
        """Send mic-state changes to QLab. Returns the number of cues written."""
        writes = self.model.dirty_writes() if only_dirty else self.model.all_writes()
        prop = self.config.osc_message_property
        total = len(writes)
        for i, (uid, message) in enumerate(writes, start=1):
            self.client.set_cue_property(self.workspace_id, uid, prop, message)
            if progress:
                progress(i, total)
        self.model.mark_committed()
        return total
