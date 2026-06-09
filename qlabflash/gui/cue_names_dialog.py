"""Dialog for bulk-renaming every cue in the workspace.

Shows the whole cue hierarchy (cue lists, groups, and individual cues) with an
editable Name column. Type a new name on any rows you like, hit OK, and only the
changed names are pushed to QLab. Tab moves down the Name column so you can rip
through a cast/scene list quickly.
"""

from __future__ import annotations

from typing import List, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QStyledItemDelegate, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QLabel,
)

from ..model import Cue

UID_ROLE = Qt.UserRole
ORIG_ROLE = Qt.UserRole + 1


class _NameOnlyDelegate(QStyledItemDelegate):
    """Allow editing only the Name column (column 1)."""

    def createEditor(self, parent, option, index):
        if index.column() != 1:
            return None
        return super().createEditor(parent, option, index)


class CueNamesDialog(QDialog):
    def __init__(self, cue_lists: List[Cue], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cue names")
        self.resize(620, 680)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Edit any names below, then OK to push the changes to QLab. "
            "Double-click a name to edit; press Enter to confirm."))

        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Cue", "Name"])
        self.tree.setItemDelegate(_NameOnlyDelegate(self.tree))
        self.tree.setColumnWidth(0, 240)
        layout.addWidget(self.tree)

        for cue in cue_lists:
            self._add(cue, self.tree.invisibleRootItem())
        self.tree.expandAll()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _add(self, cue: Cue, parent: QTreeWidgetItem) -> None:
        descr = " ".join(p for p in (cue.number, f"[{cue.type}]" if cue.type else "")
                         if p) or cue.uid
        item = QTreeWidgetItem(parent, [descr, cue.name])
        item.setData(0, UID_ROLE, cue.uid)
        item.setData(0, ORIG_ROLE, cue.name)
        item.setFlags(item.flags() | Qt.ItemIsEditable)
        for child in cue.children:
            self._add(child, item)

    def changes(self) -> List[Tuple[str, str]]:
        """``(uid, new_name)`` for every row whose name was edited."""
        result: List[Tuple[str, str]] = []

        def walk(item: QTreeWidgetItem):
            for i in range(item.childCount()):
                child = item.child(i)
                uid = child.data(0, UID_ROLE)
                original = child.data(0, ORIG_ROLE)
                current = child.text(1)
                if uid and current != original:
                    result.append((uid, current))
                walk(child)

        walk(self.tree.invisibleRootItem())
        return result
