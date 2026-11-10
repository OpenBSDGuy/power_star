"""Per-user settings in ~/.config/powerstar/config.toml (flat TOML)."""

import json
import os
import tomllib
from pathlib import Path

DEFAULTS = {
    "brightness": None, "screen_off_minutes": None, "menu_perf": None,
    "show_percent": True, "notify_low": True, "low_percent": 10, "poll_seconds": 5,
}  # fmt: skip


def default_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "powerstar" / "config.toml"


def load(path: Path | None = None) -> dict:
    try:
        with open(path or default_path(), "rb") as f:
            return {**DEFAULTS, **tomllib.load(f)}
    except (OSError, tomllib.TOMLDecodeError):
        return dict(DEFAULTS)


def save(cfg: dict, path: Path | None = None) -> None:
    path = path or default_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # json.dumps gives valid TOML for str, int and (lowercased) bool
    lines = [f"{k} = {json.dumps(v)}" for k, v in cfg.items() if v is not None]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
