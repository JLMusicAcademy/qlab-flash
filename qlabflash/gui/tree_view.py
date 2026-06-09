"""The worksheet widget: a QTreeView tuned for mic-checkbox editing + renaming.

The left column shows QLab's cue hierarchy (expand/collapse with the arrows);
double-click a name to rename it. The mic columns hold checkboxes. Dragging
across cells rubber-band-selects a rectangular block, which can then be flipped
en masse from the toolbar, the right-click menu, or the keyboard:

* Space / X  -> toggle    * Enter / 1 -> unmute (check)    * 0 / Delete -> mute
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QMenu, QTreeView


class CueTreeView(QTreeView):
    selectionChangedCount = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.setUniformRowHeights(True)
        self.setAllColumnsShowFocus(True)
        self.setExpandsOnDoubleClick(False)  # double-click edits the name instead
        self.setEditTriggers(QAbstractItemView.DoubleClicked
                             | QAbstractItemView.EditKeyPressed)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)

    # -- bulk helpers -------------------------------------------------------
    def _selected(self):
        return self.selectionModel().selectedIndexes() if self.selectionModel() else []

    def set_selected(self, unmuted: bool) -> int:
        model = self.model()
        return model.set_cells(self._selected(), unmuted) if model else 0

    def toggle_selected(self) -> int:
        model = self.model()
        return model.toggle_cells(self._selected()) if model else 0

    # -- input --------------------------------------------------------------
    def keyPressEvent(self, event):
        # Don't hijack keys while a name editor is open.
        if self.state() == QAbstractItemView.EditingState:
            super().keyPressEvent(event)
            return
        key = event.key()
        if key in (Qt.Key_Space, Qt.Key_X):
            if self.toggle_selected():
                return
        elif key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_1):
            if self.set_selected(True):
                return
        elif key in (Qt.Key_0, Qt.Key_Delete, Qt.Key_Backspace):
            if self.set_selected(False):
                return
        super().keyPressEvent(event)

    def selectionChanged(self, selected, deselected):
        super().selectionChanged(selected, deselected)
        count = sum(1 for i in self._selected() if i.column() != 0)
        self.selectionChangedCount.emit(count)

    def _context_menu(self, pos):
        if self.model() is None:
            return
        menu = QMenu(self)
        act_check = menu.addAction("Unmute selected (check)")
        act_uncheck = menu.addAction("Mute selected (uncheck)")
        act_toggle = menu.addAction("Toggle selected")
        chosen = menu.exec(self.viewport().mapToGlobal(pos))
        if chosen == act_check:
            self.set_selected(True)
        elif chosen == act_uncheck:
            self.set_selected(False)
        elif chosen == act_toggle:
            self.toggle_selected()
