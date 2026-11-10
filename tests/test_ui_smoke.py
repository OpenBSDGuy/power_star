import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()  # never touch the real config

from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from powerstar import userconfig
from powerstar.privileged import Outcome
from powerstar.readings import SYSCTL_KEYS, read_state
from powerstar.system import Result
from powerstar.ui.prefs import Preferences
from powerstar.ui.tray import Tray
from tests.fakes import FakeSystem
from tests.test_readings import DMESG, section

app = None


def setUpModule():
    global app
    app = QApplication.instance() or QApplication([])


def run_now(fn, done):
    """Stand-in for worker.run_async that runs inline."""
    try:
        done(fn())
    except BaseException as e:
        done(e)


def make_sys(sysctl_out=None, apmd_ok=True):
    sysctl_out = section("hw") if sysctl_out is None else sysctl_out
    return FakeSystem(
        {
            ("apm", "-blmaP"): "0\n82\nunknown\n1\n1\n",
            ("sysctl", "hw.sensors"): section("sensors"),
            ("sysctl", *SYSCTL_KEYS): Result(1, sysctl_out, "sysctl: invalid\n"),
            ("rcctl", "check", "apmd"): Result(0 if apmd_ok else 1, "", ""),
            ("rcctl", "get", "apmd", "flags"): "-A\n",
            ("rcctl", "get", "apmd", "status"): Result(0, "", ""),
            ("xbacklight", "-get"): "36.2\n",
        },
        {"/var/run/dmesg.boot": DMESG, "/etc/sysctl.conf": "hw.battery.chargestop=80\n"},
    )


class FakeElevator:
    def __init__(self):
        self.changes = []

    def run(self, change):
        self.changes.append(change)
        return Outcome(True, False, "")


@mock.patch("powerstar.ui.worker.run_async", run_now)
class PreferencesTest(unittest.TestCase):
    def prefs(self, sys=None, confirm=lambda lines: True):
        sys = sys or make_sys()
        self.elevator = FakeElevator()
        return Preferences(read_state(sys), userconfig.load(Path(os.devnull)), sys, self.elevator, confirm)

    def test_five_tabs(self):
        p = self.prefs()
        self.assertEqual([p.tabs.tabText(i) for i in range(5)], ["Battery", "Performance", "Display", "Sleep && buttons", "General"])

    def test_core_type_boxes_only_with_two_core_types(self):
        self.assertEqual(set(self.prefs().letters), {"S"})  # the box: only P cores, with SMT
        sys = make_sys()
        state = read_state(sys)
        state.cpu_types = {"P", "E", "S"}
        p = Preferences(state, userconfig.load(Path(os.devnull)), sys, FakeElevator(), lambda lines: True)
        self.assertEqual(set(p.letters), {"S", "P", "E"})

    def test_no_battery_keys_disables_charge_controls(self):
        out = "".join(l + "\n" for l in section("hw").splitlines() if not l.startswith("hw.battery"))
        p = self.prefs(make_sys(out))
        self.assertFalse(p.chargestart.isEnabled())
        self.assertFalse(p.chargestop.isEnabled())
        self.assertFalse(p.chargemode.isEnabled())
        self.assertTrue(p.lid.isEnabled())

    def test_apply_sends_only_changed_values_after_confirmation(self):
        shown = []
        p = self.prefs(confirm=lambda lines: shown.append(lines) or True)
        p.chargestop.setValue(90)
        p.apply()
        (change,) = self.elevator.changes
        self.assertTrue(any("hw.battery.chargestop=90" in l for l in change.describe()))
        self.assertFalse(any("chargestart" in l for l in change.describe()))
        self.assertEqual(shown[0], change.describe())
        self.assertTrue(p.apply_button.isEnabled())

    def test_unreadable_sysctl_conf_refuses_to_apply(self):
        sys = make_sys()
        sys.files["/etc/sysctl.conf"] = None  # PermissionError reads as None
        sys.modes["/etc/sysctl.conf"] = 0o600
        p = self.prefs(sys)
        p.chargestop.setValue(90)
        p.apply()
        self.assertEqual(self.elevator.changes, [])
        self.assertIn("Cannot read /etc/sysctl.conf", p.status.text())
        self.assertIn("not readable", p.status.text())

    def test_missing_sysctl_conf_is_created_and_mode_is_kept(self):
        sys = make_sys()
        del sys.files["/etc/sysctl.conf"]
        p = self.prefs(sys)
        p.chargestop.setValue(90)
        p.apply()
        self.assertEqual(self.elevator.changes[0].files[0].mode, 0o644)
        sys.files["/etc/sysctl.conf"] = "hw.battery.chargestop=80\n"
        sys.modes["/etc/sysctl.conf"] = 0o640
        p = self.prefs(sys)
        p.chargestop.setValue(90)
        p.apply()
        self.assertEqual(self.elevator.changes[0].files[0].mode, 0o640)

    def test_declined_confirmation_runs_nothing(self):
        p = self.prefs(confirm=lambda lines: False)
        p.chargestop.setValue(90)
        p.apply()
        self.assertEqual(self.elevator.changes, [])

    def test_unchanged_apply_does_nothing(self):
        p = self.prefs()
        p.apply()
        self.assertEqual(self.elevator.changes, [])


@mock.patch("powerstar.ui.worker.run_async", run_now)
class TrayTest(unittest.TestCase):
    def tray(self, **kw):
        t = Tray(make_sys(**kw), FakeElevator(), userconfig.load(Path(os.devnull)))
        self.addCleanup(t.timer.stop)
        return t

    def test_menu_entries(self):
        t = self.tray()
        texts = [a.text() for a in t.menu.actions()]
        self.assertIn("Preferences…", texts)
        self.assertIn("Quit", texts)
        self.assertIn("82% — Plugged in, not charging", texts)

    def test_performance_submenu_disabled_without_apmd(self):
        self.assertFalse(self.tray(apmd_ok=False).perf_menu.isEnabled())


class WorkerTest(unittest.TestCase):
    def test_result_and_exception_come_back_on_the_gui_thread(self):
        import threading

        from powerstar.ui.worker import run_async

        got = []
        run_async(lambda: threading.current_thread().name, lambda r: got.append((r, threading.current_thread().name)))
        run_async(lambda: 1 / 0, got.append)
        for _ in range(200):
            if len(got) == 2:
                break
            QTest.qWait(10)
        self.assertEqual(len(got), 2)
        results = [g for g in got if isinstance(g, tuple)]
        self.assertEqual(results[0][1], threading.main_thread().name)
        self.assertNotEqual(results[0][0], results[0][1])
        self.assertTrue(any(isinstance(g, ZeroDivisionError) for g in got))
