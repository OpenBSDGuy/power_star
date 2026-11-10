"""Run commands and read files; everything here works without root."""

import subprocess
from dataclasses import dataclass
from pathlib import Path

from powerstar.errors import PowerStarError


@dataclass
class Result:
    rc: int
    out: str
    err: str


class System:
    def run(self, argv: list[str], check: bool = True) -> Result:
        try:
            p = subprocess.run(argv, capture_output=True)
        except OSError as e:
            raise PowerStarError(f"{argv[0]}: command not found", detail=str(e)) from e
        # surrogateescape keeps non-UTF-8 bytes intact for byte-exact restore
        dec = lambda b: (b or b"").decode("utf-8", "surrogateescape")
        r = Result(p.returncode, dec(p.stdout), dec(p.stderr))
        if check and r.rc != 0:
            raise PowerStarError(f"{argv[0]} failed", detail=r.err)
        return r

    def read_file(self, path: Path) -> str | None:
        try:
            with open(path, encoding="utf-8", errors="surrogateescape", newline="") as f:
                return f.read()
        except (FileNotFoundError, PermissionError):
            return None
