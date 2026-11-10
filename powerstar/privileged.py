"""Run one generated root script per Apply: doas -n, then pkexec, then doas in an xterm."""

import os
import shlex
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from powerstar.changes import Change
from powerstar.errors import PowerStarError
from powerstar.system import Result, System

# doas's own refusals; anything else means the script itself ran
NEEDS_AUTH = ("doas: Authentication required", "doas: Operation not permitted", "command not found")


def build_script(change: Change, staged: dict[str, str], backup_dir: str) -> str:
    q = shlex.quote
    out = ["set -u", f"mkdir -p {q(backup_dir)}", "n=0"]
    for i, f in enumerate(change.files):
        out.append(f"if [ -e {q(f.path)} ]; then cp -p {q(f.path)} {q(backup_dir)}/{i}; had{i}=1; else had{i}=0; fi")
    out.append("rollback() {\n  :")
    for i in range(len(change.steps), 0, -1):
        undo = change.steps[i - 1].undo
        if undo:
            out.append(f"  [ $n -ge {i} ] && {shlex.join(undo)} >/dev/null 2>&1")
    for i, f in enumerate(change.files):
        out.append(f"  if [ $had{i} = 1 ]; then cp -p {q(backup_dir)}/{i} {q(f.path)}; else rm -f {q(f.path)}; fi")
    out.append("}")
    out.append("fail() { rollback; echo \"powerstar: failed: $1\" >&2; exit 1; }")
    for f in change.files:
        out.append(f"install -o root -g wheel -m {f.mode:04o} {q(staged[f.path])} {q(f.path)} || fail {q('write ' + f.path)}")
    for i, s in enumerate(change.steps, 1):
        if s.do[0] == "sysctl":
            # OpenBSD's sysctl exits 0 even when a write is rejected; stderr is the only sign
            out.append(f'e=$({shlex.join(s.do)} 2>&1 >/dev/null); [ -z "$e" ] || fail {q(s.label + ": ")}"$e"')
        else:
            out.append(f"{shlex.join(s.do)} || fail {q(s.label)}")
        out.append(f"n={i}")
    return "\n".join(out) + "\n"


@dataclass
class Outcome:
    ok: bool
    cancelled: bool
    output: str


class Elevator:
    def __init__(self, sys: System, run_cmd: Callable[[list[str]], Result] | None = None) -> None:
        self.sys = sys
        self.run_cmd = run_cmd or (lambda argv: sys.run(argv, check=False))

    def _try(self, argv: list[str]) -> Result:
        try:
            return self.run_cmd(argv)
        except PowerStarError as e:
            return Result(127, "", e.message)

    def run(self, change: Change) -> Outcome:
        tmp = Path(tempfile.mkdtemp(prefix="powerstar."))
        try:
            staged = {}
            for i, f in enumerate(change.files):
                staged[f.path] = str(tmp / f"stage{i}")
                (tmp / f"stage{i}").write_text(f.content, encoding="utf-8", errors="surrogateescape")
            (tmp / "backup").mkdir()  # user-owned, so the cleanup below can remove root's backup copies
            script = tmp / "apply.sh"
            script.write_text(build_script(change, staged, str(tmp / "backup")))
            return self._elevate(str(script), tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def _elevate(self, script: str, tmp: Path) -> Outcome:
        r = self._try(["doas", "-n", "sh", script])
        if r.rc == 0:
            return Outcome(True, False, r.out)
        # any other failure means the script ran, so it must not run a second time
        if not any(s in r.err for s in NEEDS_AUTH):
            return Outcome(False, False, r.err)
        if shutil.which("pkexec"):
            r = self._try(["pkexec", "/bin/sh", script])
            if r.rc == 0:
                return Outcome(True, False, r.out)
            if r.rc == 126:
                return Outcome(False, True, "cancelled")
            if r.rc != 127:
                return Outcome(False, False, r.err)
        log, status = tmp / "log", tmp / "status"
        q = shlex.quote
        cmd = (
            "echo 'Power Star needs root to change power settings. Enter your doas password.'; "
            f"doas sh {q(script)} > {q(str(log))} 2>&1; echo $? > {q(str(status))}"
        )
        r = self._try(["xterm", "-T", "Power Star needs root", "-e", "sh", "-c", cmd])
        if r.rc == 127:
            return Outcome(False, False, "No way to get root: doas needs a password and neither pkexec nor xterm works")
        if not status.exists():
            return Outcome(False, True, "cancelled")
        output = log.read_text(errors="replace") if log.exists() else ""
        return Outcome(status.read_text().strip() == "0", False, output)
