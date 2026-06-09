"""Reshape a full-bleed image into a native-looking macOS app icon.

macOS app icons aren't edge-to-edge: the artwork sits in a rounded-rectangle
inset within the 1024x1024 canvas with transparent margins and a soft shadow.
This takes any square-ish image and fits it to that template so it matches the
size/shape of stock macOS icons.

    python scripts/native_icon.py [input.png] [output.png]
"""

import sys

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter, QPainterPath, QPixmap, QColor
from PySide6.QtWidgets import (QApplication, QGraphicsDropShadowEffect,
                               QGraphicsPixmapItem, QGraphicsScene)

CANVAS = 1024            # final icon size
CONTENT = 824            # rounded-rect body size (Apple's macOS grid)
MARGIN = (CANVAS - CONTENT) // 2          # 100 px transparent margin
RADIUS = 185             # corner radius of the body (~0.225 * CONTENT)


def rounded_content(src_path: str) -> QPixmap:
    """Scale the source to CONTENT and clip it to the rounded-rect body."""
    src = QImage(src_path)
    if src.isNull():
        raise SystemExit(f"Could not read image: {src_path}")
    # Cover the square fully, then centre-crop to CONTENT x CONTENT.
    scaled = src.scaled(CONTENT, CONTENT, Qt.KeepAspectRatioByExpanding,
                        Qt.SmoothTransformation)
    cx = (scaled.width() - CONTENT) // 2
    cy = (scaled.height() - CONTENT) // 2
    scaled = scaled.copy(cx, cy, CONTENT, CONTENT)

    out = QImage(CONTENT, CONTENT, QImage.Format_ARGB32_Premultiplied)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing, True)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, CONTENT, CONTENT), RADIUS, RADIUS)
    p.setClipPath(path)
    p.drawImage(0, 0, scaled)
    p.end()
    return QPixmap.fromImage(out)


def build(src_path: str, out_path: str) -> None:
    body = rounded_content(src_path)

    scene = QGraphicsScene(0, 0, CANVAS, CANVAS)
    item = QGraphicsPixmapItem(body)
    item.setOffset(MARGIN, MARGIN - 6)        # nudge up slightly for the shadow
    shadow = QGraphicsDropShadowEffect()
    shadow.setBlurRadius(34)
    shadow.setOffset(0, 12)
    shadow.setColor(QColor(0, 0, 0, 90))
    item.setGraphicsEffect(shadow)
    scene.addItem(item)

    canvas = QImage(CANVAS, CANVAS, QImage.Format_ARGB32_Premultiplied)
    canvas.fill(Qt.transparent)
    p = QPainter(canvas)
    p.setRenderHint(QPainter.Antialiasing, True)
    scene.render(p, QRectF(0, 0, CANVAS, CANVAS), QRectF(0, 0, CANVAS, CANVAS))
    p.end()
    canvas.save(out_path, "PNG")
    print("wrote", out_path)


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "assets/icon.png"
    out = sys.argv[2] if len(sys.argv) > 2 else "assets/icon.png"
    QApplication(sys.argv)
    build(src, out)


if __name__ == "__main__":
    main()
