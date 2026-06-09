"""Item delegate that shows selection as an outline instead of a solid fill.

The default view selection paints a solid highlight over each selected cell,
which hides the checkbox underneath. This delegate paints every cell normally
(background, checkbox, text — no highlight fill) and then strokes a coloured
border along the *outer* edge of the selected block, so a dragged selection
reads as a clean outlined rectangle with the checkmarks still visible.
"""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtGui import QPen
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem


class SelectionOutlineDelegate(QStyledItemDelegate):
    OUTLINE_WIDTH = 2

    def paint(self, painter, option, index):
        selected = bool(option.state & QStyle.State_Selected)

        # Paint the cell as if it were not selected, so the checkbox and our
        # amber/green backgrounds remain fully visible.
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.state = option.state & ~QStyle.State_Selected
        super().paint(painter, opt, index)

        if not selected:
            return

        view = option.widget
        sm = view.selectionModel() if view is not None else None

        def is_selected(other: QModelIndex) -> bool:
            return bool(sm and other.isValid() and sm.isSelected(other))

        col = index.column()
        left = index.sibling(index.row(), col - 1) if col > 0 else QModelIndex()
        right = index.sibling(index.row(), col + 1)
        above = below = QModelIndex()
        if view is not None:
            a = view.indexAbove(index)
            b = view.indexBelow(index)
            above = a.sibling(a.row(), col) if a.isValid() else a
            below = b.sibling(b.row(), col) if b.isValid() else b

        pen = QPen(option.palette.highlight().color(), self.OUTLINE_WIDTH)
        painter.save()
        painter.setPen(pen)
        # Inset by half the pen width so the stroke stays inside the cell.
        r = option.rect.adjusted(1, 1, -1, -1)
        # Only draw an edge where the neighbour in that direction isn't selected,
        # which yields a single outline around a contiguous block.
        if not is_selected(left):
            painter.drawLine(r.topLeft(), r.bottomLeft())
        if not is_selected(right):
            painter.drawLine(r.topRight(), r.bottomRight())
        if not is_selected(above):
            painter.drawLine(r.topLeft(), r.topRight())
        if not is_selected(below):
            painter.drawLine(r.bottomLeft(), r.bottomRight())
        painter.restore()
