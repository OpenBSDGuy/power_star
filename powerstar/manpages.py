"""The bundled man page: view it in place or install it system-wide."""

import subprocess
from importlib import resources
from pathlib import Path

MAN_DIR = Path("/usr/local/man")


def bundled() -> list[Path]:
    return sorted(p for p in (resources.files("powerstar") / "man").iterdir() if p.is_file())  # type: ignore[arg-type]


def view() -> int:
    return subprocess.call(["man", "-l", str(bundled()[0])])


def install() -> int:
    # the CLI has a terminal, so plain doas can prompt here
    for page in bundled():
        rc = subprocess.call(["doas", "install", "-D", "-o", "root", "-g", "wheel", "-m", "0644", str(page), str(MAN_DIR / f"man{page.suffix[1:]}" / page.name)])
        if rc:
            return rc
    return subprocess.call(["doas", "makewhatis", str(MAN_DIR)])
