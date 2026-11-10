"""Tray icon drawn with QPainter, and the tooltip text."""

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap, QPolygonF

from powerstar.readings import State


def status_text(state: State) -> str:
    apm = state.apm
    if apm is None or apm.percent is None:
        return "No battery"
    pct = apm.percent
    if apm.state == 3:
        first, tail = f"{pct}% — Charging", "until full"
    elif apm.ac == 1 and pct >= 100:
        first, tail = f"{pct}% — Charged", None
    elif apm.ac == 1:
        first, tail = f"{pct}% — Plugged in, not charging", None
    else:
        first, tail = f"{pct}% — Discharging", "remaining"
    if tail and apm.minutes is not None:
        return f"{first}\n{apm.minutes // 60}:{apm.minutes % 60:02d} {tail}"
    return first


def draw_icon(percent: int | None, charging: bool, on_ac: bool, show_percent: bool, size: int = 64) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / 64, size / 64)
    outline = QColor("#303030")
    p.setPen(QPen(outline, 3))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(QRectF(4, 22, 48, 28))
    p.setBrush(outline)
    p.drawRect(QRectF(52, 30, 6, 12))
    if percent is not None:
        color = QColor("#2e9e3e") if percent >= 30 else QColor("#f08000") if percent > 10 else QColor(220, 0, 0)
        width = max(2.0, 42 * min(percent, 100) / 100) if percent > 0 else 0
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawRect(QRectF(7, 25, width, 22))
    if charging:  # lightning bolt above the body
        p.setBrush(QColor("#ffd000"))
        p.setPen(QPen(outline, 1.5))
        p.drawPolygon(QPolygonF([QPointF(*pt) for pt in ((32, 0), (22, 12), (29, 12), (25, 21), (38, 8), (31, 8), (36, 0))]))
    elif on_ac:  # plug: two prongs over a block
        p.setPen(QPen(outline, 3))
        p.drawLine(26, 2, 26, 9)
        p.drawLine(36, 2, 36, 9)
        p.setBrush(outline)
        p.drawRect(QRectF(22, 9, 18, 8))
    if percent is None or show_percent:
        text = "?" if percent is None else str(percent)
        font = QFont()
        font.setBold(True)
        font.setPixelSize(14 if len(text) == 3 else 20)
        p.setFont(font)
        p.setPen(QColor("black"))
        p.drawText(QRectF(4, 22, 48, 28), Qt.AlignmentFlag.AlignCenter, text)
    p.end()
    return QIcon(pm)
