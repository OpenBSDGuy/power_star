import unittest

from powerstar import session
from powerstar.readings import Sensors, State
from powerstar.system import Result
from tests.fakes import FakeSystem


class SessionTest(unittest.TestCase):
    def test_screen_off(self):
        f = FakeSystem({("xset", "+dpms"): "", ("xset", "dpms", "600", "600", "600"): "", ("xset", "-dpms"): ""})
        session.set_screen_off(f, 10)
        self.assertEqual(f.calls, [["xset", "+dpms"], ["xset", "dpms", "600", "600", "600"]])
        f.calls.clear()
        session.set_screen_off(f, 0)
        self.assertEqual(f.calls, [["xset", "-dpms"]])

    def test_get_brightness(self):
        self.assertEqual(session.get_brightness(FakeSystem({("xbacklight", "-get"): "36.237624\n"})), 36)
        self.assertIsNone(session.get_brightness(FakeSystem({("xbacklight", "-get"): Result(1, "", "no")})))

    def test_perf_problem_apmd_down(self):
        st = State(None, Sensors(), {}, set(), False, "")
        self.assertEqual(session.perf_problem(st), "apmd is not running")

    def test_reapply_continues_after_failure(self):
        f = FakeSystem({("xbacklight", "-set", "50"): Result(1, "", "boom"), ("apm", "-H"): ""})
        errors = session.reapply(f, {"brightness": 50, "screen_off_minutes": None, "menu_perf": "H"})
        self.assertEqual(f.calls, [["xbacklight", "-set", "50"], ["apm", "-H"]])
        self.assertEqual(len(errors), 1)
