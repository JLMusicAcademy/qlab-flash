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
        """Read the mic state for a cue list and build the worksheet tree.

        Builds a *fresh* GridModel rather than mutating the one currently shown,
        so reloading can't corrupt the live view from the worker thread.
        """
        if not self.cue_lists:
            self.fetch_cue_lists()
        if not self.cue_lists:
            raise QLabError("No cue lists found in this workspace.")
        cue_list = self.cue_lists[min(cue_list_index, len(self.cue_lists) - 1)]
        top_level = cue_list.children

        model = GridModel(self.config)
        leaf_uids = model.candidate_uids(top_level)
        if progress:
            progress(f"Reading {len(leaf_uids)} cues...")

        prop = self.config.osc_message_property
        texts = self.client.get_cue_properties(self.workspace_id, leaf_uids, prop)

        model.build_tree(top_level, lambda uid: texts.get(uid))
        self.model = model
        return model

    # -- renaming cues ------------------------------------------------------
    def rename_cues(self, changes: List[tuple],
                    progress: Optional[Callable[[int, int], None]] = None) -> int:
        """Apply ``(cue_uid, new_name)`` renames to QLab. Returns the count."""
        total = len(changes)
        for i, (uid, name) in enumerate(changes, start=1):
            self.client.set_cue_property(self.workspace_id, uid, "name", name)
            if progress:
                progress(i, total)
        return total

    # -- submitting ---------------------------------------------------------
    def submit(self, only_dirty: bool = True,
               progress: Optional[Callable[[int, int], None]] = None) -> tuple:
        """Push mic-state and cue-name changes to QLab.

        Returns ``(mic_count, name_count)``. Mic changes honour ``only_dirty``;
        cue-name changes are always just the edited ones.
        """
        mic_writes = (self.model.dirty_writes() if only_dirty
                      else self.model.all_writes())
        name_writes = self.model.name_writes()
        prop = self.config.osc_message_property
        total = len(mic_writes) + len(name_writes)
        done = 0
        for uid, message in mic_writes:
            self.client.set_cue_property(self.workspace_id, uid, prop, message)
            done += 1
            if progress:
                progress(done, total)
        for uid, name in name_writes:
            self.client.set_cue_property(self.workspace_id, uid, "name", name)
            done += 1
            if progress:
                progress(done, total)
        self.model.mark_committed()
        return len(mic_writes), len(name_writes)
