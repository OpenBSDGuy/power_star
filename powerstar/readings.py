"""Parse the output of apm, sysctl and dmesg.boot; none of it needs root."""

import re
from dataclasses import dataclass, field, replace
from pathlib import Path

from powerstar.errors import PowerStarError

SYSCTL_KEYS = [
    "hw.battery.chargemode", "hw.battery.chargestart", "hw.battery.chargestop",
    "hw.perfpolicy", "hw.setperf", "hw.cpuspeed", "hw.blockcpu", "hw.ncpuonline",
    "hw.allowpowerdown", "machdep.lidaction", "machdep.pwraction",
]  # fmt: skip

DMESG_BOOT = Path("/var/run/dmesg.boot")


@dataclass
class ApmStatus:
    state: int
    percent: int | None
    minutes: int | None
    ac: int
    perf_auto: bool


@dataclass
class Battery:
    name: str
    model: str | None = None
    last_full_wh: float | None = None
    design_wh: float | None = None
    remaining_wh: float | None = None
    rate_w: float | None = None
    voltage: float | None = None
    status: str | None = None
    cycles: int | None = None

    @property
    def health_percent(self) -> int | None:
        if not self.last_full_wh or not self.design_wh:
            return None
        return round(self.last_full_wh / self.design_wh * 100)


@dataclass
class Sensors:
    batteries: list[Battery] = field(default_factory=list)
    cpu_temp: float | None = None
    fan_rpm: int | None = None
    lid_open: bool | None = None


@dataclass
class State:
    apm: ApmStatus | None
    sensors: Sensors
    sysctl: dict[str, str]
    cpu_types: set[str]
    apmd_running: bool
    apmd_flags: str


def parse_apm(out: str) -> ApmStatus:
    """Input is `apm -blmaP`, which prints its five values in a fixed order."""
    state, percent, minutes, ac, perf = out.split()[:5]
    pct = int(percent)
    return ApmStatus(
        state=int(state),
        percent=None if pct < 0 or int(state) == 4 else pct,
        minutes=None if minutes == "unknown" else int(minutes),
        ac=int(ac),
        perf_auto=perf == "1",
    )


_SENSOR = re.compile(r"^hw\.sensors\.([^.=]+)\.([a-z]+)(\d+)=(.*)$")
_NUMBER = re.compile(r"^\s*(-?\d+(?:\.\d+)?)")
_PAREN = re.compile(r"\(([^)]*)\)")


def _num(text: str) -> float | None:
    m = _NUMBER.match(text)
    return float(m.group(1)) if m else None


def parse_sensors(out: str) -> Sensors:
    s = Sensors()
    bats: dict[str, Battery] = {}
    temps: dict[str, float | None] = {}
    for line in out.splitlines():
        m = _SENSOR.match(line.strip())
        if not m:
            continue
        dev, kind, idx, val = m.group(1), m.group(2), m.group(3), m.group(4)
        key = f"{kind}{idx}"
        if dev.startswith("acpibat"):
            b = bats.setdefault(dev, Battery(dev))
            n = _num(val)
            if key == "watthour0":
                b.last_full_wh = n
            elif key == "watthour3":
                b.remaining_wh = n
            elif key == "watthour4":
                b.design_wh = n
            elif key == "power0":
                b.rate_w = n
            elif key == "volt1":
                b.voltage = n
            elif key == "raw0":
                p = _PAREN.search(val)
                b.status = p.group(1) if p else None
            elif key == "raw1":
                b.cycles = int(n) if n is not None else None
        elif key == "temp0":
            temps[dev] = _num(val)
        elif kind == "fan" and s.fan_rpm is None:
            n = _num(val)
            s.fan_rpm = int(n) if n is not None else None
        elif dev.startswith("acpibtn") and kind == "indicator":
            if "(lid open)" in val:
                s.lid_open = True
            elif "(lid closed)" in val:
                s.lid_open = False
    s.batteries = list(bats.values())
    s.cpu_temp = temps.get("cpu0", temps.get("acpitz0"))
    return s


def parse_sysctl(out: str) -> dict[str, str]:
    return {k: v for k, _, v in (line.partition("=") for line in out.splitlines() if "=" in line)}


def cpu_types(dmesg: str) -> set[str]:
    letters: set[str] = set()
    for m in re.finditer(r"^cpu\d+: .*\btype (\w+)", dmesg, re.M):
        letters |= set(m.group(1)) & set("PELS")
    return letters


def battery_models(dmesg: str) -> dict[str, str]:
    return dict(re.findall(r'^(acpibat\d+) at \S+: \S+ model "([^"]*)"', dmesg, re.M))


def read_state(sys) -> State:
    try:
        apm = parse_apm(sys.run(["apm", "-blmaP"]).out)
    except (PowerStarError, ValueError):
        apm = None
    try:
        sensors = parse_sensors(sys.run(["sysctl", "hw.sensors"], check=False).out)
    except PowerStarError:
        sensors = Sensors()
    dmesg = sys.read_file(DMESG_BOOT) or ""
    models = battery_models(dmesg)
    sensors.batteries = [replace(b, model=models.get(b.name)) for b in sensors.batteries]
    return State(
        apm=apm,
        sensors=sensors,
        sysctl=parse_sysctl(sys.run(["sysctl", *SYSCTL_KEYS], check=False).out),
        cpu_types=cpu_types(dmesg),
        apmd_running=sys.run(["rcctl", "check", "apmd"], check=False).rc == 0,
        apmd_flags=sys.run(["rcctl", "get", "apmd", "flags"], check=False).out.strip(),
    )
