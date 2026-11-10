import unittest
from pathlib import Path

from powerstar.errors import PowerStarError
from powerstar.readings import (
    SYSCTL_KEYS, ApmStatus, battery_models, cpu_types, parse_apm, parse_sensors, parse_sysctl, read_state,
)
from powerstar.system import Result
from tests.fakes import FakeSystem


def section(name: str) -> str:
    raw = (Path(__file__).parent / "fixtures" / "box-raw.txt").read_text()
    return raw.split(f"=={name}\n", 1)[1].split("\n==", 1)[0] + "\n"


DMESG = section("dmesgboot") + 'acpibat0 at acpi0: BAT0 model "01AV421" serial   748 type LiP oem "SMP"\n' \
    'acpibat1 at acpi0: BAT1 model "01AV424" serial  3341 type LiP oem "SMP"\n'


class ParseTest(unittest.TestCase):
    def test_apm(self):
        self.assertEqual(parse_apm("0\n82\nunknown\n1\n1\n"), ApmStatus(0, 82, None, 1, True))
        self.assertEqual(parse_apm("1\n20\n83\n0\n0\n"), ApmStatus(1, 20, 83, 0, False))

    def test_apm_no_battery(self):
        self.assertIsNone(parse_apm("4\n-1\nunknown\n1\n0\n").percent)
        self.assertIsNone(parse_apm("4\n50\nunknown\n1\n0\n").percent)

    def test_sensors(self):
        s = parse_sensors(section("sensors"))
        b0, b1 = s.batteries
        self.assertEqual((b0.name, b0.health_percent, b0.status, b0.cycles), ("acpibat0", 78, "battery idle", 756))
        self.assertEqual((b0.remaining_wh, b0.rate_w, b0.voltage), (18.11, 0.0, 11.90))
        self.assertEqual(b1.cycles, 380)
        self.assertEqual((s.fan_rpm, s.lid_open, s.cpu_temp), (0, True, 43.0))

    def test_cpu_temp_falls_back_to_acpitz(self):
        self.assertEqual(parse_sensors("hw.sensors.acpitz0.temp0=51.00 degC (zone temperature)\n").cpu_temp, 51.0)

    def test_sysctl(self):
        self.assertEqual(parse_sysctl(section("hw"))["hw.battery.chargestop"], "80")

    def test_dmesg(self):
        self.assertEqual(cpu_types(DMESG), {"P", "S"})
        self.assertEqual(battery_models(DMESG), {"acpibat0": "01AV421", "acpibat1": "01AV424"})


class ReadStateTest(unittest.TestCase):
    def fake(self, apm, sysctl):
        return FakeSystem(
            {
                ("apm", "-blmaP"): apm,
                ("sysctl", "hw.sensors"): section("sensors"),
                ("sysctl", *SYSCTL_KEYS): Result(1, sysctl, "sysctl: second level name battery in hw.battery is invalid\n"),
                ("rcctl", "check", "apmd"): "apmd(ok)\n",
                ("rcctl", "get", "apmd", "flags"): "-A\n",
                ("rcctl", "get", "apmd", "status"): "",
            },
            {"/var/run/dmesg.boot": DMESG},
        )

    def test_full(self):
        st = read_state(self.fake("0\n82\nunknown\n1\n1\n", section("hw")))
        self.assertEqual(st.apm.percent, 82)
        self.assertEqual((st.apmd_running, st.apmd_flags, st.cpu_types), (True, "-A", {"P", "S"}))
        self.assertEqual(st.sensors.batteries[0].model, "01AV421")

    def test_apmd_disabled(self):
        f = self.fake("0\n82\nunknown\n1\n1\n", section("hw"))
        f.responses[("rcctl", "get", "apmd", "flags")] = "NO\n"
        f.responses[("rcctl", "get", "apmd", "status")] = Result(1, "", "")
        st = read_state(f)
        self.assertEqual((st.apmd_flags, st.apmd_enabled), ("", False))

    def test_apm_failure(self):
        st = read_state(self.fake(PowerStarError("apm failed"), section("hw")))
        self.assertIsNone(st.apm)

    def test_missing_battery_keys(self):
        out = "".join(l + "\n" for l in section("hw").splitlines() if not l.startswith("hw.battery"))
        st = read_state(self.fake("0\n82\nunknown\n1\n1\n", out))
        self.assertNotIn("hw.battery.chargestop", st.sysctl)
        self.assertIn("hw.perfpolicy", st.sysctl)
