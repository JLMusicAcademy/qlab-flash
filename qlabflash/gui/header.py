"""A horizontal header that shows a mic's number with its name underneath.

When any mic has a custom name, the header grows taller and each mic column
draws its number across the top and the name rotated vertically below it — the
familiar look of a console's channel strip — so 32 names fit without making the
columns wide. With no names, it behaves like an ordinary header (just numbers).
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QRect, Qt
from PySide6.QtWidgets import QHeaderView


class MicHeaderView(QHeaderView):
    SHORT_HEIGHT = 26
    TALL_HEIGHT = 104
    NUMBER_BAND = 18  # vertical space reserved for the channel number

    def __init__(self, label_fn: Callable[[int], str], parent=None):
        super().__init__(Qt.Horizontal, parent)
        self._label_fn = label_fn
        self._tall = False
        self.setSectionsClickable(True)
        self.setHighlightSections(True)
        self.setDefaultAlignment(Qt.AlignCenter)

    def set_tall(self, tall: bool) -> None:
        self._tall = tall
        self.setFixedHeight(self.TALL_HEIGHT if tall else self.SHORT_HEIGHT)
        if self.viewport():
            self.viewport().update()

    def paintSection(self, painter, rect, logicalIndex):
        # Column 0 ("Cue") and short mode use the normal header rendering.
        if logicalIndex == 0 or not self._tall:
            super().paintSection(painter, rect, logicalIndex)
            return

        painter.save()
        # Background + separator lines (kept simple to avoid style quirks).
        painter.fillRect(rect, self.palette().button())
        painter.setPen(self.palette().mid().color())
        painter.drawLine(rect.right(), rect.top(), rect.right(), rect.bottom())
        painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())

        channel = logicalIndex  # column 1 -> mic 1
        painter.setPen(self.palette().buttonText().color())
        number_rect = QRect(rect.left(), rect.top() + 2, rect.width(),
                            self.NUMBER_BAND)
        painter.drawText(number_rect, Qt.AlignHCenter | Qt.AlignTop, str(channel))

        label = self._label_fn(channel)
        if label:
            avail = rect.height() - self.NUMBER_BAND - 8
            painter.translate(rect.center().x(), rect.bottom() - 5)
            painter.rotate(-90)  # text reads bottom-to-top
            text = painter.fontMetrics().elidedText(label, Qt.ElideRight, avail)
            text_rect = QRect(0, -rect.width() // 2, avail, rect.width())
            painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, text)
        painter.restore()
