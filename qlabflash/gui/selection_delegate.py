"""Item delegate: show selection as a light tint, not a solid fill.

The default view selection paints a solid highlight that hides the checkbox
underneath. This delegate paints every cell normally (background, checkbox,
text), draws faint grid lines, then lays a *translucent* highlight over selected
cells — so a dragged selection reads clearly while the checkmarks stay visible,
with no seams or stray lines between cells.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

GRID_COLOR = QColor(0, 0, 0, 30)        # faint spreadsheet grid lines
SELECTION_ALPHA = 60                    # translucency of the selection tint


class SelectionOutlineDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        selected = bool(option.state & QStyle.State_Selected)

        # Paint the cell as if it were not selected, so the checkbox and our
        # amber/green backgrounds remain fully visible.
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.state = option.state & ~QStyle.State_Selected
        super().paint(painter, opt, index)

        # Faint grid lines (right + bottom of every cell) so the 32 mic columns
        # are easy to read across.
        painter.save()
        painter.setPen(QPen(GRID_COLOR, 1))
        r = option.rect
        painter.drawLine(r.right(), r.top(), r.right(), r.bottom())
        painter.drawLine(r.left(), r.bottom(), r.right(), r.bottom())
        painter.restore()

        # Selected cells get a light, uniform tint laid over the content.
        if selected:
            tint = QColor(option.palette.highlight().color())
            tint.setAlpha(SELECTION_ALPHA)
            painter.fillRect(option.rect, tint)
