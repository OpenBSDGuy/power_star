"""Turn wanted settings into the root work needed: file edits and commands."""

from dataclasses import dataclass, field

from powerstar import apmdflags, blockcpu, sysctlconf
from powerstar.errors import PowerStarError
from powerstar.readings import State

SYSCTL_CONF = "/etc/sysctl.conf"
POLICIES = {"auto", "high", "manual"}


@dataclass
class Wanted:
    chargemode: int | None = None
    chargestart: int | None = None
    chargestop: int | None = None
    perfpolicy: str | None = None
    setperf: int | None = None
    blocked: set[str] | None = None
    lidaction: int | None = None
    pwraction: int | None = None
    auto_sleep: tuple[str | None, int | None] | None = None


@dataclass
class Step:
    do: list[str]
    undo: list[str] | None
    label: str


@dataclass
class FileWrite:
    path: str
    content: str
    mode: int
    summary: str = ""


@dataclass
class Change:
    files: list[FileWrite] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)

    def describe(self) -> list[str]:
        return [f"Edit {f.path}: {f.summary}" for f in self.files] + [s.label for s in self.steps]

    @property
    def empty(self) -> bool:
        return not self.files and not self.steps


def _validate(state: State, w: Wanted) -> None:
    live = state.sysctl
    if w.chargestart is not None or w.chargestop is not None:
        start = w.chargestart if w.chargestart is not None else int(live.get("hw.battery.chargestart", 0))
        stop = w.chargestop if w.chargestop is not None else int(live.get("hw.battery.chargestop", 100))
        if not 0 <= start < stop <= 100:
            raise PowerStarError("Invalid charge thresholds", detail="Need 0 <= start < stop <= 100")
    if w.perfpolicy is not None:
        parts = w.perfpolicy.split(",")
        if len(parts) > 2 or not set(parts) <= POLICIES:
            raise PowerStarError("Invalid performance policy", detail=w.perfpolicy)
    if w.setperf is not None:
        if not 0 <= w.setperf <= 100:
            raise PowerStarError("hw.setperf must be 0-100")
        if "manual" not in (w.perfpolicy or live.get("hw.perfpolicy", "")).split(","):
            raise PowerStarError("hw.setperf needs a manual performance policy")
    if w.blocked is not None and (msg := blockcpu.problem(w.blocked, state.cpu_types)):
        raise PowerStarError(msg)
    for name, v in (("lid action", w.lidaction), ("power button action", w.pwraction)):
        if v is not None and not 0 <= v <= 2:
            raise PowerStarError(f"Invalid {name}")
    if w.auto_sleep and w.auto_sleep[0]:
        mode, pct = w.auto_sleep
        if mode not in ("suspend", "hibernate") or pct is None or not 1 <= pct <= 50:
            raise PowerStarError("Auto sleep needs suspend or hibernate at 1-50%")


def plan_changes(state: State, wanted: Wanted, sysctl_conf: str) -> Change:
    _validate(state, wanted)
    live, w = state.sysctl, wanted
    items: list[tuple[str, str]] = []  # in the order they are applied

    def want(key: str, value) -> None:
        if value is not None:
            items.append((key, str(value)))

    want("hw.battery.chargemode", w.chargemode)
    start, stop = w.chargestart, w.chargestop
    cur_stop = int(live.get("hw.battery.chargestop", 100))
    pair = [("hw.battery.chargestart", start), ("hw.battery.chargestop", stop)]
    if start is not None and start >= cur_stop:
        pair.reverse()  # raise the stop first, or the kernel rejects start >= stop
    for k, v in pair:
        want(k, v)
    want("hw.perfpolicy", w.perfpolicy)
    want("hw.setperf", w.setperf)
    if w.blocked is not None:
        want("hw.blockcpu", blockcpu.compose(live.get("hw.blockcpu", ""), w.blocked, state.cpu_types))
    want("machdep.lidaction", w.lidaction)
    want("machdep.pwraction", w.pwraction)

    text, summary, steps = sysctl_conf, [], []
    for key, value in items:
        if key not in live:
            raise PowerStarError(f"{key} is not supported on this machine")
        if live[key] != value:
            steps.append(Step(["sysctl", f"{key}={value}"], ["sysctl", f"{key}={live[key]}"], f"Run sysctl {key}={value}"))
        new = sysctlconf.set_value(text, key, value)
        if new != text:
            summary.append(f"{key}={value}")
        text = new
    if w.blocked is not None:
        new = sysctlconf.disable_key(text, "hw.smt")
        if new != text:
            summary.append("Comment out hw.smt (deprecated alias of the S letter)")
        text = new
    if w.pwraction == 1 and live.get("hw.allowpowerdown") != "1":
        new = sysctlconf.set_value(text, "hw.allowpowerdown", "1")
        if new != text:
            summary.append("hw.allowpowerdown=1 (takes effect after reboot)")
        text = new

    flags = state.apmd_flags
    overridden = w.perfpolicy is not None and apmdflags.without_perf_flags(flags).split() != flags.split()
    new_flags = apmdflags.without_perf_flags(flags) if overridden else flags
    sleep_changed = w.auto_sleep is not None and w.auto_sleep != apmdflags.auto_sleep(flags)
    if sleep_changed:
        new_flags = apmdflags.with_auto_sleep(new_flags, *w.auto_sleep)
    if new_flags.split() != flags.split():
        if sleep_changed:
            label = f"Set apmd flags to '{new_flags}'"
            if overridden:
                label += " (removes the perf flag, which overrides hw.perfpolicy at boot)"
        else:
            removed = " ".join(f"-{c}" for c in "AHL" if c in "".join(t for t in flags.split() if t.startswith("-")))
            label = f"Remove {removed} from apmd flags (it overrides hw.perfpolicy at boot)"
        steps.append(Step(["rcctl", "set", "apmd", "flags", new_flags], ["rcctl", "set", "apmd", "flags", flags], label))
    if sleep_changed:
        if not state.apmd_running:
            steps.append(Step(["rcctl", "enable", "apmd"], ["rcctl", "disable", "apmd"], "Enable apmd (it is not running)"))
        steps.append(Step(["rcctl", "restart", "apmd"], None, "Restart apmd"))

    files = [FileWrite(SYSCTL_CONF, text, 0o644, ", ".join(summary))] if text != sysctl_conf else []
    return Change(files, steps)
