import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication

from powerstar.readings import ApmStatus, Sensors, State
from powerstar.ui.icon import draw_icon, status_text

app = None


def setUpModule():
    global app
    app = QApplication.instance() or QApplication([])


def make_state(apm):
    return State(apm, Sensors(), {}, set(), True, "-A")


class StatusTextTest(unittest.TestCase):
    def test_plugged_in_not_charging(self):
        self.assertEqual(status_text(make_state(ApmStatus(0, 82, None, 1, True))), "82% — Plugged in, not charging")

    def test_discharging_with_minutes(self):
        self.assertEqual(status_text(make_state(ApmStatus(0, 50, 83, 0, True))), "50% — Discharging\n1:23 remaining")

    def test_charging_with_minutes(self):
        self.assertEqual(status_text(make_state(ApmStatus(3, 82, 83, 1, True))), "82% — Charging\n1:23 until full")

    def test_charged(self):
        self.assertEqual(status_text(make_state(ApmStatus(0, 100, None, 1, True))), "100% — Charged")

    def test_no_battery(self):
        self.assertEqual(status_text(make_state(ApmStatus(4, None, None, 1, False))), "No battery")
        self.assertEqual(status_text(make_state(None)), "No battery")


class DrawIconTest(unittest.TestCase):
    def test_low_battery_has_red_pixel_in_body(self):
        icon = draw_icon(5, False, False, True)
        self.assertFalse(icon.isNull())
        img = icon.pixmap(64, 64).toImage()
        red = [
            (x, y) for x in range(4, 52) for y in range(22, 50)
            if (c := QColor(img.pixel(x, y))).red() > 200 and c.green() < 60 and c.blue() < 60
        ]
        self.assertTrue(red)

    def test_unknown_and_charging_do_not_crash(self):
        self.assertFalse(draw_icon(None, False, True, True).isNull())
        self.assertFalse(draw_icon(100, True, True, True).isNull())
        self.assertFalse(draw_icon(60, False, True, False).isNull())
