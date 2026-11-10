"""Settings that need no root: brightness, screen blanking, apm performance mode."""

import os

from powerstar.errors import PowerStarError


def get_brightness(sys) -> int | None:
    try:
        return round(float(sys.run(["xbacklight", "-get"]).out))
    except (PowerStarError, ValueError):
        return None


def set_brightness(sys, percent: int) -> None:
    sys.run(["xbacklight", "-set", str(percent)])


def set_screen_off(sys, minutes: int) -> None:
    if minutes == 0:
        sys.run(["xset", "-dpms"])
        return
    secs = str(minutes * 60)
    sys.run(["xset", "+dpms"])
    sys.run(["xset", "dpms", secs, secs, secs])


def set_perf(sys, mode: str) -> None:
    sys.run(["apm", f"-{mode}"])


def perf_problem(state) -> str | None:
    if not state.apmd_running:
        return "apmd is not running"
    if not os.access("/var/run/apmdev", os.R_OK | os.W_OK):
        return "No access to /var/run/apmdev (needs the wheel group)"
    return None


def reapply(sys, cfg: dict) -> list[str]:
    actions = []
    if cfg.get("brightness") is not None:
        actions.append(lambda: set_brightness(sys, cfg["brightness"]))
    if cfg.get("screen_off_minutes") is not None:
        actions.append(lambda: set_screen_off(sys, cfg["screen_off_minutes"]))
    if cfg.get("menu_perf") is not None:
        actions.append(lambda: set_perf(sys, cfg["menu_perf"]))
    errors = []
    for act in actions:
        try:
            act()
        except PowerStarError as e:
            errors.append(f"{e.message}: {e.detail}".strip(": "))
    return errors
