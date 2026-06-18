"""The worksheet widget: a QTreeView tuned for mic-checkbox editing + renaming.

The left column shows QLab's cue hierarchy (expand/collapse with the arrows);
double-click a name to rename it. The mic columns hold checkboxes. Dragging
across cells rubber-band-selects a rectangular block, which can then be flipped
en masse from the toolbar, the right-click menu, or the keyboard:

* Space / X  -> toggle    * Enter / 1 -> unmute (check)    * 0 / Delete -> mute
"""

from __future__ import annotations

from PySide6.QtCore import QPersistentModelIndex, Qt, QTimer, Signal
from PySide6.QtWidgets import QAbstractItemView, QMenu, QTreeView

from .selection_delegate import SelectionOutlineDelegate


class CueTreeView(QTreeView):
    selectionChangedCount = Signal(int)
    # Emitted with the hovered mic channel (>=1), or -1 when not over a mic.
    hoverCell = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hover_col = None
        # Track mouse moves (even with no button down) for the hover crosshair.
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        # Throttle the selection-count signal: during a rubber-band drag the
        # selection changes on every mouse-move, so we recompute at most every
        # 40 ms (and the count itself is O(ranges), not O(cells)).
        self._sel_timer = QTimer(self)
        self._sel_timer.setSingleShot(True)
        self._sel_timer.setInterval(40)
        self._sel_timer.timeout.connect(self._emit_selection_count)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectItems)
        self._delegate = SelectionOutlineDelegate(self)
        self.setItemDelegate(self._delegate)
        self.setUniformRowHeights(True)
        self.setAlternatingRowColors(True)
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
        # Don't materialize the whole selection here — that's O(N) per move and
        # O(N^2) across a drag. Just (re)arm the throttle; the count is computed
        # from selection ranges when it fires.
        self._sel_timer.start()

    def _emit_selection_count(self):
        model = self.selectionModel()
        if model is None:
            self.selectionChangedCount.emit(0)
            return
        # Count selected mic cells from the selection *ranges* (O(ranges)),
        # excluding the name column (0). No per-index list is built.
        count = 0
        for r in model.selection():
            width = sum(1 for c in range(r.left(), r.right() + 1) if c != 0)
            count += (r.bottom() - r.top() + 1) * width
        self.selectionChangedCount.emit(count)

    # -- hover crosshair ----------------------------------------------------
    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        self._update_hover(self.indexAt(event.position().toPoint()))

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._update_hover(None)

    def _update_hover(self, index):
        col = index.column() if (index is not None and index.isValid()) else None
        row = (QPersistentModelIndex(index.siblingAtColumn(0))
               if (index is not None and index.isValid()) else None)
        # Only repaint/emit when the highlighted cell actually changed.
        prev_row = self._delegate.active_row
        same_row = (prev_row is None and row is None) or (
            prev_row is not None and row is not None
            and prev_row.row() == row.row() and prev_row.parent() == row.parent())
        if col == self._delegate.active_col and same_row:
            return
        self._delegate.active_col = col
        self._delegate.active_row = row
        self.viewport().update()
        self.hoverCell.emit(col if (col is not None and col >= 1) else -1)

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
