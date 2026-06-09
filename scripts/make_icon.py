"""Generate the QLab Flash app icon (assets/icon.png) at 1024x1024.

The icon evokes the app itself: a grid of mute/unmute checkboxes (the worksheet)
with a lightning bolt for "Flash". Rendered with Qt so we need no extra deps.

Run:  python scripts/make_icon.py
"""

import os
import sys

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QImage, QLinearGradient,
                           QPainter, QPainterPath, QPen, QPolygonF)
from PySide6.QtWidgets import QApplication

SIZE = 1024
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "assets", "icon.png")


def rounded(rect, r):
    path = QPainterPath()
    path.addRoundedRect(rect, r, r)
    return path


def draw_check(p, rect):
    pen = QPen(QColor("#FFFFFF"), rect.width() * 0.13,
               Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    p.drawPolyline(QPolygonF([
        QPointF(x + 0.22 * w, y + 0.55 * h),
        QPointF(x + 0.42 * w, y + 0.74 * h),
        QPointF(x + 0.78 * w, y + 0.28 * h),
    ]))


def render():
    img = QImage(SIZE, SIZE, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)

    # Rounded-square background with a blue gradient (macOS "squircle"-ish).
    bg = QRectF(0, 0, SIZE, SIZE)
    grad = QLinearGradient(0, 0, SIZE, SIZE)
    grad.setColorAt(0.0, QColor("#3B82F6"))
    grad.setColorAt(1.0, QColor("#16317D"))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(grad))
    p.drawPath(rounded(bg, SIZE * 0.225))

    # Checkbox grid (4 cols x 3 rows) — the worksheet motif.
    cols, rows = 4, 3
    cell, gap = 150.0, 46.0
    grid_w = cols * cell + (cols - 1) * gap
    grid_h = rows * cell + (rows - 1) * gap
    ox = (SIZE - grid_w) / 2
    oy = (SIZE - grid_h) / 2 - 10
    checked = {(0, 0), (0, 2), (1, 1), (1, 3), (2, 0), (2, 2), (2, 3)}

    for r in range(rows):
        for c in range(cols):
            x = ox + c * (cell + gap)
            y = oy + r * (cell + gap)
            box = QRectF(x, y, cell, cell)
            if (r, c) in checked:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor("#34C759"))           # unmuted = green
                p.drawPath(rounded(box, cell * 0.22))
                draw_check(p, box)
            else:
                p.setBrush(QColor(255, 255, 255, 38))    # muted = empty
                p.setPen(QPen(QColor(255, 255, 255, 220), 9))
                p.drawPath(rounded(box, cell * 0.22))

    # Lightning bolt badge (the "Flash") in the lower-right.
    bolt = QPolygonF([
        QPointF(560, 612), QPointF(470, 815), QPointF(556, 815),
        QPointF(486, 980), QPointF(700, 742), QPointF(596, 742),
        QPointF(672, 612),
    ])
    p.setPen(QPen(QColor("#16317D"), 22, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(QColor("#FFC83D"))
    p.drawPolygon(bolt)

    p.end()
    out = os.path.abspath(OUT)
    img.save(out, "PNG")
    print("wrote", out)


def main():
    QApplication(sys.argv)
    render()


if __name__ == "__main__":
    main()
