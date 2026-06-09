"""Qt table model presenting the mic grid as a checkbox spreadsheet.

Column 0 is the cue label; columns 1..N are mics 1..N. A checked box means the
mic is unmuted; unchecked means muted. Cells with no backing QLab cue are shown
dimmed and are not checkable.
"""

from __future__ import annotations

from typing import Iterable, List

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QBrush, QColor

from ..model import GridModel

DIRTY_BRUSH = QBrush(QColor(255, 244, 200))      # pale amber for edited cells
UNMUTED_BRUSH = QBrush(QColor(214, 245, 214))     # soft green for live mics
MISSING_BRUSH = QBrush(QColor(244, 244, 244))     # grey for non-existent cells
LABEL_BRUSH = QBrush(QColor(238, 240, 245))


class MicTableModel(QAbstractTableModel):
    def __init__(self, grid: GridModel, parent=None):
        super().__init__(parent)
        self.grid = grid
        self.mic_count = grid.config.mic_count

    # -- shape --------------------------------------------------------------
    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.grid.rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else self.mic_count + 1

    def is_mic_column(self, column: int) -> bool:
        return column >= 1

    def channel_for_column(self, column: int) -> int:
        return column  # column 1 -> mic 1

    # -- data ---------------------------------------------------------------
    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self.grid.rows[index.row()]
        col = index.column()

        if col == 0:
            if role == Qt.DisplayRole:
                return row.label
            if role == Qt.BackgroundRole:
                return LABEL_BRUSH
            if role == Qt.ToolTipRole:
                return f"Cue {row.label}"
            return None

        chan = self.channel_for_column(col)
        cell = row.cells.get(chan)

        if role == Qt.CheckStateRole:
            if cell is None:
                return None
            return Qt.Checked if cell.unmuted else Qt.Unchecked

        if role == Qt.BackgroundRole:
            if cell is None:
                return MISSING_BRUSH
            if cell.dirty:
                return DIRTY_BRUSH
            if cell.unmuted:
                return UNMUTED_BRUSH
            return None

        if role == Qt.ToolTipRole:
            if cell is None:
                return f"Mic {chan}: no cue in “{row.label}”"
            state = "UNMUTED (on)" if cell.unmuted else "muted (off)"
            dirty = " — edited" if cell.dirty else ""
            return f"{row.label} · Mic {chan}: {state}{dirty}"

        return None

    def setData(self, index: QModelIndex, value, role=Qt.CheckStateRole) -> bool:
        if not index.isValid() or role != Qt.CheckStateRole:
            return False
        row = self.grid.rows[index.row()]
        cell = row.cells.get(self.channel_for_column(index.column()))
        if cell is None:
            return False
        cell.unmuted = (Qt.CheckState(value) == Qt.Checked)
        self.dataChanged.emit(index, index, [Qt.CheckStateRole, Qt.BackgroundRole])
        return True

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.NoItemFlags
        base = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if index.column() == 0:
            return base
        chan = self.channel_for_column(index.column())
        cell = self.grid.rows[index.row()].cells.get(chan)
        if cell is None:
            return base  # selectable (so rubber-band works) but not checkable
        return base | Qt.ItemIsUserCheckable

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return "Cue" if section == 0 else str(self.channel_for_column(section))
        return str(section + 1)

    # -- bulk operations on a set of indexes --------------------------------
    def set_cells(self, indexes: Iterable[QModelIndex], unmuted: bool) -> int:
        """Force every checkable mic cell in ``indexes`` to ``unmuted``."""
        changed = 0
        cells_changed: List[QModelIndex] = []
        for index in indexes:
            if not index.isValid() or index.column() == 0:
                continue
            cell = self.grid.rows[index.row()].cells.get(
                self.channel_for_column(index.column()))
            if cell is None or cell.unmuted == unmuted:
                continue
            cell.unmuted = unmuted
            cells_changed.append(index)
            changed += 1
        self._emit_changes(cells_changed)
        return changed

    def toggle_cells(self, indexes: Iterable[QModelIndex]) -> int:
        changed = 0
        cells_changed: List[QModelIndex] = []
        for index in indexes:
            if not index.isValid() or index.column() == 0:
                continue
            cell = self.grid.rows[index.row()].cells.get(
                self.channel_for_column(index.column()))
            if cell is None:
                continue
            cell.unmuted = not cell.unmuted
            cells_changed.append(index)
            changed += 1
        self._emit_changes(cells_changed)
        return changed

    def _emit_changes(self, indexes: List[QModelIndex]) -> None:
        if not indexes:
            return
        rows = [i.row() for i in indexes]
        cols = [i.column() for i in indexes]
        top_left = self.index(min(rows), min(cols))
        bottom_right = self.index(max(rows), max(cols))
        self.dataChanged.emit(top_left, bottom_right,
                              [Qt.CheckStateRole, Qt.BackgroundRole])

    def dirty_count(self) -> int:
        return sum(1 for row in self.grid.rows
                   for cell in row.cells.values() if cell.dirty)
