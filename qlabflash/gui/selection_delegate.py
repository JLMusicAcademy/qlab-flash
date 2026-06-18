"""Item delegate: centered checkboxes + a light selection tint.

* Checkboxes are drawn (and clicked) centered in their cell instead of the
  default left-aligned position. We strip the built-in check indicator in
  ``initStyleOption`` (so the base paint never draws the left one) and render a
  centered one ourselves.
* Selection is a translucent tint rather than a solid fill, so the checkmarks
  stay visible and adjacent selected cells blend with no internal lines.
* Faint grid lines keep the 32 mic columns readable.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QRect, Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import (
    QApplication, QStyle, QStyledItemDelegate, QStyleOptionViewItem,
)

GRID_COLOR = QColor(0, 0, 0, 30)        # faint spreadsheet grid lines
BANK_COLOR = QColor(0, 0, 0, 90)        # stronger rule between banks of 8
SELECTION_ALPHA = 60                    # translucency of the selection tint
CROSSHAIR_TINT = QColor(60, 120, 220, 28)  # active row/column highlight
BANK_SIZE = 8                           # X32 groups channels into banks of 8


class SelectionOutlineDelegate(QStyledItemDelegate):
    # The view sets these so we can tint the hovered row/column ("crosshair").
    # active_col is the hovered mic column (>=1) or None; active_row is a
    # QPersistentModelIndex on column 0 of the hovered row, or None.
    active_col = None
    active_row = None

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        # Drop the built-in (left-aligned) checkbox; we draw it centered.
        option.features &= ~QStyleOptionViewItem.HasCheckIndicator

    # -- helpers ------------------------------------------------------------
    def _in_crosshair(self, index) -> bool:
        """True if this cell is in the hovered column or the hovered row."""
        col = index.column()
        if self.active_col is not None and col >= 1 and col == self.active_col:
            return True
        row = self.active_row
        if (row is not None and row.isValid()
                and index.row() == row.row()
                and index.parent() == row.parent()):
            return True
        return False

    @staticmethod
    def _is_checkable(index) -> bool:
        return (bool(index.flags() & Qt.ItemIsUserCheckable)
                and index.data(Qt.CheckStateRole) is not None)

    def _check_rect(self, option, index) -> QRect:
        """Centered checkbox rect, sized from the style's indicator metrics."""
        style = option.widget.style() if option.widget else QApplication.style()
        w = style.pixelMetric(QStyle.PM_IndicatorWidth, None, option.widget)
        h = style.pixelMetric(QStyle.PM_IndicatorHeight, None, option.widget)
        x = option.rect.x() + (option.rect.width() - w) // 2
        y = option.rect.y() + (option.rect.height() - h) // 2
        return QRect(x, y, w, h)

    # -- painting -----------------------------------------------------------
    def paint(self, painter, option, index):
        selected = bool(option.state & QStyle.State_Selected)

        opt = QStyleOptionViewItem(option)
        opt.state = option.state & ~QStyle.State_Selected
        super().paint(painter, opt, index)        # background + text, no checkbox

        # Crosshair: tint the hovered column and row so it's easy to follow one
        # mic straight down. Translucent, and painted before the checkbox so the
        # box stays crisp on top.
        if self._in_crosshair(index):
            painter.fillRect(option.rect, CROSSHAIR_TINT)

        if self._is_checkable(index):
            self._paint_centered_check(painter, option, index)

        # Faint grid lines so the mic columns are easy to read across; a stronger
        # rule on bank-of-8 boundaries (channels 8/16/24) as coarse reference.
        painter.save()
        r = option.rect
        chan = index.column()
        last = index.model().columnCount() - 1 if index.model() else 0
        bank_edge = chan >= 1 and chan % BANK_SIZE == 0 and chan != last
        painter.setPen(QPen(BANK_COLOR if bank_edge else GRID_COLOR,
                            2 if bank_edge else 1))
        painter.drawLine(r.right(), r.top(), r.right(), r.bottom())
        painter.setPen(QPen(GRID_COLOR, 1))
        painter.drawLine(r.left(), r.bottom(), r.right(), r.bottom())
        painter.restore()

        # Selected cells get a light, uniform tint laid over the content.
        if selected:
            tint = QColor(option.palette.highlight().color())
            tint.setAlpha(SELECTION_ALPHA)
            painter.fillRect(option.rect, tint)

    def _paint_centered_check(self, painter, option, index):
        widget = option.widget
        style = widget.style() if widget else QApplication.style()
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.rect = self._check_rect(option, index)
        cs = Qt.CheckState(index.data(Qt.CheckStateRole))
        state = opt.state & ~(QStyle.State_Selected | QStyle.State_On
                              | QStyle.State_Off | QStyle.State_NoChange)
        if cs == Qt.Checked:
            state |= QStyle.State_On
        elif cs == Qt.Unchecked:
            state |= QStyle.State_Off
        else:
            state |= QStyle.State_NoChange
        opt.state = state | QStyle.State_Enabled
        style.drawPrimitive(QStyle.PE_IndicatorItemViewItemCheck, opt, painter,
                            widget)

    # -- clicking (toggle when the centered checkbox is clicked) ------------
    def editorEvent(self, event, model, option, index):
        if not self._is_checkable(index) or not (index.flags() & Qt.ItemIsEnabled):
            return super().editorEvent(event, model, option, index)

        et = event.type()
        if et == QEvent.MouseButtonPress:
            # Note whether the press hit the checkbox, but don't consume it so
            # drag-to-select still works.
            self._pressed_on_check = self._check_rect(option, index).contains(
                event.position().toPoint())
            return False
        if et == QEvent.MouseButtonRelease:
            hit = self._check_rect(option, index).contains(
                event.position().toPoint())
            if getattr(self, "_pressed_on_check", False) and hit:
                self._pressed_on_check = False
                value = index.data(Qt.CheckStateRole)
                new = (Qt.Unchecked if Qt.CheckState(value) == Qt.Checked
                       else Qt.Checked)
                model.setData(index, new, Qt.CheckStateRole)
                return True
            self._pressed_on_check = False
            return False
        return super().editorEvent(event, model, option, index)
