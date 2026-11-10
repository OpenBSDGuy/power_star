"""Regenerate the README screenshot from the repo root:

    QT_QPA_PLATFORM=offscreen python -m docs.make_screenshot

Renders the real Preferences window (Battery tab) and tray menu, plus one image per other tab, from the recorded
box output through the test fakes (nothing on the host is touched) to docs/screenshot*.png.
"""
import os
import tempfile
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["QT_SCALE_FACTOR"] = "2"  # grabs come out at 2x device pixel ratio
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()  # never touch the real config

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PyQt6.QtWidgets import QApplication

from powerstar import userconfig
from powerstar.readings import read_state
from powerstar.ui.icon import draw_icon
from powerstar.ui.prefs import Preferences
from powerstar.ui.tray import Tray
from tests.test_ui_smoke import FakeElevator, make_sys, run_now

OUT = Path(__file__).parent / "screenshot.png"
SCALE = 2
TITLE_H, PAD = 30, 24
BG = QColor("#d8dde3")


def xfce_window(content: QImage, title: str) -> QImage:
    """Wrap a grabbed widget in an XFCE-style frame: title left, minimize/maximize/close right."""
    w, h = round(content.width() / content.devicePixelRatio()), round(content.height() / content.devicePixelRatio())
    img = QImage(w * SCALE, (h + TITLE_H) * SCALE, QImage.Format.Format_ARGB32)
    img.setDevicePixelRatio(SCALE)
    img.fill(QColor("#3b4252"))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    font = QFont()
    font.setBold(True)
    p.setFont(font)
    p.setPen(QColor("#eceff4"))
    p.drawText(QRectF(12, 0, w, TITLE_H), Qt.AlignmentFlag.AlignVCenter, title)
    p.setPen(QPen(QColor("#eceff4"), 1.5))
    cy = TITLE_H / 2
    x = w - 20  # close is rightmost
    p.drawLine(int(x - 5), int(cy - 5), int(x + 5), int(cy + 5))
    p.drawLine(int(x - 5), int(cy + 5), int(x + 5), int(cy - 5))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(QRectF(x - 32 - 5, cy - 5, 10, 10))  # maximize
    p.drawLine(int(x - 64 - 5), int(cy + 5), int(x - 64 + 5), int(cy + 5))  # minimize
    p.drawImage(0, TITLE_H, content)
    p.end()
    return img


def main() -> None:
    app = QApplication.instance() or QApplication([])
    sys = make_sys()
    cfg = userconfig.load(Path(os.devnull))
    with mock.patch("powerstar.ui.worker.run_async", run_now), mock.patch("os.access", return_value=True):
        tray = Tray(sys, FakeElevator(), cfg)
        prefs = Preferences(read_state(sys), cfg, sys, FakeElevator(), lambda lines: True)
    prefs.tabs.setCurrentIndex(0)
    prefs.resize(prefs.sizeHint())
    prefs.show()
    win = xfce_window(prefs.grab().toImage(), "Power Star")
    tray.menu.resize(tray.menu.sizeHint())
    menu = tray.menu.grab().toImage()
    icon = draw_icon(82, False, True, True, 48 * SCALE).pixmap(48 * SCALE, 48 * SCALE).toImage()

    gap = 30
    panel_h = 32  # the tray icon sits in a panel strip above the menu
    mw, mh = round(menu.width() / SCALE), round(menu.height() / SCALE)
    W = PAD * 3 + round(win.width() / SCALE) + max(mw, 80)
    H = max(round(win.height() / SCALE), panel_h + mh) + PAD * 2
    canvas = QImage(W * SCALE, H * SCALE, QImage.Format.Format_ARGB32)
    canvas.setDevicePixelRatio(SCALE)
    canvas.fill(BG)
    p = QPainter(canvas)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.drawImage(PAD, PAD, win)
    mx = PAD * 2 + round(win.width() / SCALE)
    p.fillRect(QRectF(mx, PAD, max(mw, 80), panel_h), QColor("#c9ced6"))
    p.drawImage(QRectF(mx + max(mw, 80) - 34, PAD + 2, 28, 28), icon)
    p.drawImage(mx + max(mw, 80) - mw, PAD + panel_h, menu)
    p.end()
    canvas.save(str(OUT))

    # one image per other tab, same window size as the Battery tab
    for i in range(1, prefs.tabs.count()):
        prefs.tabs.setCurrentIndex(i)
        win = xfce_window(prefs.grab().toImage(), "Power Star")
        w, h = round(win.width() / SCALE), round(win.height() / SCALE)
        tab = QImage((w + PAD * 2) * SCALE, (h + PAD * 2) * SCALE, QImage.Format.Format_ARGB32)
        tab.setDevicePixelRatio(SCALE)
        tab.fill(BG)
        p = QPainter(tab)
        p.drawImage(PAD, PAD, win)
        p.end()
        slug = prefs.tabs.tabText(i).replace("&&", "").lower().split()[0]
        tab.save(str(OUT.with_name(f"screenshot-{slug}.png")))


if __name__ == "__main__":
    main()
