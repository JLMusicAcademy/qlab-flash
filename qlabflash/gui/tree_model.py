"""Qt item model exposing QLab's cue hierarchy as an editable worksheet tree.

Column 0 is the cue name (expandable tree, double-click to rename — the change
is pushed to QLab on submit). Columns 1..N are mics: a checkbox appears only on
rows that actually own that channel (anchor cues, and the individual mic cues
beneath them); every other row is blank under the mic columns.
"""

from __future__ import annotations

from typing import Iterable, List

from PySide6.QtCore import QAbstractItemModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QBrush, QColor

from ..config import Config
from ..model import GridModel, RowNode

DIRTY_BRUSH = QBrush(QColor(255, 244, 200))      # edited (mic or name)
UNMUTED_BRUSH = QBrush(QColor(214, 245, 214))     # live mic
ANCHOR_BRUSH = QBrush(QColor(232, 238, 248))      # an anchor cue's name cell


class CueTreeModel(QAbstractItemModel):
    # Emitted after mic states change so the view can repaint aliased cells
    # (an anchor cue and the mic cue beneath it share one underlying state).
    micChanged = Signal()

    UNDO_LIMIT = 30

    def __init__(self, grid: GridModel, config: Config, parent=None):
        super().__init__(parent)
        self.grid = grid
        self.config = config
        self.mic_count = config.mic_count
        self._undo = []      # stack of action entries; each is a list of items

    # -- tree structure -----------------------------------------------------
    def _node(self, index: QModelIndex) -> RowNode:
        return index.internalPointer()

    def index(self, row, column, parent=QModelIndex()):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        siblings = (self.grid.roots if not parent.isValid()
                    else self._node(parent).children)
        return self.createIndex(row, column, siblings[row])

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()
        node = self._node(index)
        p = node.parent
        if p is None:
            return QModelIndex()
        siblings = p.parent.children if p.parent else self.grid.roots
        return self.createIndex(siblings.index(p), 0, p)

    def rowCount(self, parent=QModelIndex()):
        if parent.column() > 0:
            return 0
        if not parent.isValid():
            return len(self.grid.roots)
        return len(self._node(parent).children)

    def columnCount(self, parent=QModelIndex()):
        return self.mic_count + 1

    def channel_for_column(self, column: int) -> int:
        return column

    # -- data ---------------------------------------------------------------
    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        node = self._node(index)
        col = index.column()

        if col == 0:
            if role in (Qt.DisplayRole,):
                return node.display_name
            if role == Qt.EditRole:
                return node.name
            if role == Qt.ToolTipRole:
                bits = [b for b in (node.number, f"[{node.type}]") if b]
                tip = " ".join(bits)
                return tip + (" — edited" if node.name_dirty else "")
            if role == Qt.BackgroundRole:
                if node.name_dirty:
                    return DIRTY_BRUSH
                if node.is_anchor:
                    return ANCHOR_BRUSH
            return None

        cell = node.cells.get(self.channel_for_column(col))
        if role == Qt.CheckStateRole:
            if cell is None:
                return None
            return Qt.Checked if cell.unmuted else Qt.Unchecked
        if role == Qt.BackgroundRole and cell is not None:
            if cell.dirty:
                return DIRTY_BRUSH
            if cell.unmuted:
                return UNMUTED_BRUSH
        if role == Qt.ToolTipRole and cell is not None:
            state = "UNMUTED (on)" if cell.unmuted else "muted (off)"
            return f"{node.display_name} · Mic {cell.channel}: {state}"
        return None

    def setData(self, index, value, role=Qt.EditRole):
        if not index.isValid():
            return False
        node = self._node(index)
        if index.column() == 0 and role == Qt.EditRole:
            new = str(value).strip()
            if new != node.name:
                self._push_undo([("name", node, node.name)])
                node.name = new
            self.dataChanged.emit(index, index,
                                  [Qt.DisplayRole, Qt.EditRole, Qt.BackgroundRole])
            return True
        if index.column() >= 1 and role == Qt.CheckStateRole:
            cell = node.cells.get(self.channel_for_column(index.column()))
            if cell is None:
                return False
            new_state = (Qt.CheckState(value) == Qt.Checked)
            if new_state != cell.unmuted:
                self._push_undo([("mic", cell, cell.unmuted)])
                cell.unmuted = new_state
            self.dataChanged.emit(index, index,
                                  [Qt.CheckStateRole, Qt.BackgroundRole])
            self.micChanged.emit()
            return True
        return False

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        base = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if index.column() == 0:
            return base | Qt.ItemIsEditable
        node = self._node(index)
        if node.cells.get(self.channel_for_column(index.column())) is not None:
            return base | Qt.ItemIsUserCheckable
        return base  # blank but selectable so rubber-band drag still works

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and section >= 1:
            chan = self.channel_for_column(section)
            if role == Qt.DisplayRole:
                return self.config.header_text(chan)
            if role == Qt.ToolTipRole:
                name = self.config.label_for(chan)
                return f"Mic {chan} — {name}" if name else f"Mic {chan}"
            return None
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return "Cue"
        return None

    # -- bulk operations on selected indexes --------------------------------
    def set_cells(self, indexes: Iterable[QModelIndex], unmuted: bool) -> int:
        seen = set()
        undo = []
        for index in indexes:
            cell = self._cell_at(index)
            if cell is None or id(cell) in seen:
                continue
            seen.add(id(cell))
            if cell.unmuted != unmuted:
                undo.append(("mic", cell, cell.unmuted))
                cell.unmuted = unmuted
        if undo:
            self._push_undo(undo)
            self.micChanged.emit()
        return len(undo)

    def toggle_cells(self, indexes: Iterable[QModelIndex]) -> int:
        seen = set()
        undo = []
        for index in indexes:
            cell = self._cell_at(index)
            if cell is None or id(cell) in seen:
                continue
            seen.add(id(cell))           # dedupe aliased cells so we flip once
            undo.append(("mic", cell, cell.unmuted))
            cell.unmuted = not cell.unmuted
        if undo:
            self._push_undo(undo)
            self.micChanged.emit()
        return len(undo)

    # -- renaming a whole mic channel (pushes to QLab cue names) ------------
    def rename_channel(self, channel: int, name: str) -> int:
        """Set the column label and rename every cue for this channel.

        The cue renames are staged (name-dirty) and pushed to QLab on submit.
        Returns the number of cues affected.
        """
        name = (name or "").strip()
        undo = [("label", channel, self.config.label_for(channel))]
        self.config.set_label(channel, name)
        for node, old_name in self.grid.set_channel_name(channel, name):
            undo.append(("name", node, old_name))
        self._push_undo(undo)
        self.micChanged.emit()
        return len(undo) - 1   # minus the label entry

    # -- undo (last UNDO_LIMIT actions) ------------------------------------
    def _push_undo(self, items: list) -> None:
        self._undo.append(items)
        if len(self._undo) > self.UNDO_LIMIT:
            self._undo.pop(0)

    def can_undo(self) -> bool:
        return bool(self._undo)

    def undo(self) -> bool:
        if not self._undo:
            return False
        for kind, obj, old in reversed(self._undo.pop()):
            if kind == "mic":
                obj.unmuted = old
            elif kind == "name":
                obj.name = old
            elif kind == "label":
                self.config.set_label(obj, old)
        self.micChanged.emit()
        return True

    def _cell_at(self, index: QModelIndex):
        if not index.isValid() or index.column() == 0:
            return None
        node = self._node(index)
        return node.cells.get(self.channel_for_column(index.column()))

    # -- dirty bookkeeping --------------------------------------------------
    def mic_dirty_count(self) -> int:
        return self.grid.mic_dirty_count()

    def name_dirty_count(self) -> int:
        return self.grid.name_dirty_count()

    def scribble_dirty_count(self) -> int:
        return self.grid.scribble_dirty_count()
