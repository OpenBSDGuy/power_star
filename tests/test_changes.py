import unittest
from pathlib import Path

from powerstar.changes import Wanted, plan_changes
from powerstar.errors import PowerStarError
from powerstar.readings import ApmStatus, Sensors, State, parse_sysctl
from tests.test_readings import section

CONF = "# my box\nhw.smt=1\n# start and stop charge at 40 and 80\nhw.battery.chargestart=40\nhw.battery.chargestop=80\n"


def box(**kw) -> State:
    d = dict(
        apm=ApmStatus(0, 82, None, 1, True), sensors=Sensors(), sysctl=parse_sysctl(section("hw")),
        cpu_types={"P", "S"}, apmd_running=True, apmd_flags="-A",
    )
    d.update(kw)
    return State(**d)


class PlanTest(unittest.TestCase):
    def test_empty(self):
        self.assertTrue(plan_changes(box(), Wanted(), CONF).empty)

    def test_chargestop(self):
        c = plan_changes(box(), Wanted(chargestop=90), CONF)
        self.assertEqual(c.files[0].path, "/etc/sysctl.conf")
        self.assertEqual(c.files[0].content, CONF.replace("chargestop=80", "chargestop=90"))
        self.assertEqual(c.files[0].mode, 0o644)
        self.assertEqual(len(c.steps), 1)
        self.assertEqual(c.steps[0].do, ["sysctl", "hw.battery.chargestop=90"])
        self.assertEqual(c.steps[0].undo, ["sysctl", "hw.battery.chargestop=80"])
        self.assertIn("Edit /etc/sysctl.conf: hw.battery.chargestop=90", c.describe())

    def test_stop_before_start(self):
        c = plan_changes(box(), Wanted(chargestart=85, chargestop=95), CONF)
        self.assertEqual([s.do[1] for s in c.steps], ["hw.battery.chargestop=95", "hw.battery.chargestart=85"])

    def test_start_first_when_lower(self):
        c = plan_changes(box(), Wanted(chargestart=20, chargestop=60), CONF)
        self.assertEqual([s.do[1] for s in c.steps], ["hw.battery.chargestart=20", "hw.battery.chargestop=60"])

    def test_bad_thresholds(self):
        with self.assertRaises(PowerStarError):
            plan_changes(box(), Wanted(chargestart=90, chargestop=80), CONF)

    def test_perfpolicy_removes_apmd_flag(self):
        c = plan_changes(box(), Wanted(perfpolicy="high,auto"), CONF)
        self.assertIn("hw.perfpolicy=high,auto", c.files[0].content)
        self.assertIn(["rcctl", "set", "apmd", "flags", ""], [s.do for s in c.steps])
        self.assertIn("Remove -A from apmd flags (it overrides hw.perfpolicy at boot)", c.describe())

    def test_setperf_needs_manual(self):
        with self.assertRaises(PowerStarError):
            plan_changes(box(), Wanted(setperf=50), CONF)
        c = plan_changes(box(), Wanted(perfpolicy="manual", setperf=50), CONF)
        self.assertEqual([s.do[1] for s in c.steps[:2]], ["hw.perfpolicy=manual", "hw.setperf=50"])

    def test_blocked(self):
        c = plan_changes(box(), Wanted(blocked={"S"}), CONF)
        self.assertEqual(c.steps[0].do, ["sysctl", "hw.blockcpu=SL"])
        self.assertIn("# disabled by powerstar: hw.smt=1", c.files[0].content)
        self.assertIn("hw.blockcpu=SL", c.files[0].content)

    def test_blocked_all_cores_refused(self):
        with self.assertRaises(PowerStarError):
            plan_changes(box(), Wanted(blocked={"P"}), CONF)

    def test_power_off_saved_only(self):
        st = box()
        st.sysctl["hw.allowpowerdown"] = "0"
        c = plan_changes(st, Wanted(pwraction=1), CONF)
        self.assertEqual(c.steps, [])  # machdep.pwraction is already 1 live
        self.assertIn("hw.allowpowerdown=1", c.files[0].content)
        self.assertFalse(any("allowpowerdown" in " ".join(s.do) for s in c.steps))
        self.assertIn("takes effect after reboot", c.describe()[0])

    def test_auto_sleep(self):
        c = plan_changes(box(), Wanted(auto_sleep=("suspend", 5)), CONF)
        self.assertEqual([s.do for s in c.steps], [["rcctl", "set", "apmd", "flags", "-A -z 5"], ["rcctl", "restart", "apmd"]])
        self.assertIsNone(c.steps[1].undo)
        self.assertEqual(c.files, [])

    def test_auto_sleep_enables_apmd(self):
        c = plan_changes(box(apmd_running=False, apmd_flags=""), Wanted(auto_sleep=("hibernate", 3)), CONF)
        self.assertEqual([s.do[:2] for s in c.steps], [["rcctl", "set"], ["rcctl", "enable"], ["rcctl", "restart"]])

    def test_auto_sleep_merged_with_perf(self):
        c = plan_changes(box(), Wanted(perfpolicy="high", auto_sleep=("suspend", 5)), CONF)
        self.assertEqual(c.steps[-2].do, ["rcctl", "set", "apmd", "flags", "-z 5"])

    def test_unsupported_key(self):
        st = box()
        del st.sysctl["hw.battery.chargestop"]
        with self.assertRaises(PowerStarError):
            plan_changes(st, Wanted(chargestop=90), CONF)
