"""The spreadsheet widget: a QTableView tuned for mic-checkbox editing.

Dragging across cells rubber-band-selects a rectangular block (standard
QTableView behaviour with item selection). Selected cells can then be flipped en
masse from the toolbar, the right-click menu, or the keyboard:

* Space / X  -> toggle
* Enter / 1  -> unmute (check)
* 0 / Delete -> mute (uncheck)
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QMenu, QTableView


class MicTableView(QTableView):
    selectionChangedCount = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectItems)
        # Single click toggles the box; drag selects a region without toggling.
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)
        self.setShowGrid(True)
        self.setCornerButtonEnabled(False)

    # -- bulk helpers -------------------------------------------------------
    def _selected(self):
        return self.selectionModel().selectedIndexes() if self.selectionModel() else []

    def set_selected(self, unmuted: bool) -> int:
        model = self.model()
        if model is None:
            return 0
        return model.set_cells(self._selected(), unmuted)

    def toggle_selected(self) -> int:
        model = self.model()
        if model is None:
            return 0
        return model.toggle_cells(self._selected())

    # -- input --------------------------------------------------------------
    def keyPressEvent(self, event):
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
        # Count only checkable mic cells for the status bar.
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
