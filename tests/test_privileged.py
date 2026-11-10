import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from powerstar.changes import Change, FileWrite, Step
from powerstar.privileged import Elevator, build_script
from powerstar.system import Result
from tests.fakes import FakeSystem


class ScriptTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, self.tmp)
        bin = self.tmp / "bin"
        bin.mkdir()
        (bin / "install").write_text('#!/bin/sh\nfor a in "$@"; do src="$dst"; dst="$a"; done\ncp "$src" "$dst"\n')
        for name in ("sysctl", "rcctl"):
            (bin / name).write_text(f'#!/bin/sh\necho "{name} $*" >> "$LOG"\ncase "$*" in *FAIL*) exit 1;; esac\n')
        for f in bin.iterdir():
            f.chmod(0o755)
        self.log = self.tmp / "log"
        self.env = {**os.environ, "PATH": f"{bin}:{os.environ['PATH']}", "LOG": str(self.log)}

    def run_script(self, change, files=None):
        staged = {}
        for i, f in enumerate(change.files):
            staged[f.path] = str(self.tmp / f"stage{i}")
            Path(staged[f.path]).write_text(f.content)
        script = self.tmp / "apply.sh"
        script.write_text(build_script(change, staged, str(self.tmp / "backup")))
        return subprocess.run(["sh", str(script)], env=self.env, capture_output=True, text=True)

    def logged(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_success(self):
        target = self.tmp / "sysctl.conf"
        target.write_text("old\n")
        c = Change([FileWrite(str(target), "new\n", 0o644)], [
            Step(["sysctl", "a=1"], ["sysctl", "a=0"], "a"), Step(["sysctl", "b=1"], ["sysctl", "b=0"], "b")])
        r = self.run_script(c)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(target.read_text(), "new\n")
        self.assertEqual(self.logged(), ["sysctl a=1", "sysctl b=1"])

    def test_failure_rolls_back(self):
        target = self.tmp / "sysctl.conf"
        target.write_bytes(b"old\xff\n")
        c = Change([FileWrite(str(target), "new\n", 0o644)], [
            Step(["sysctl", "a=1"], ["sysctl", "a=0"], "a"), Step(["sysctl", "hw.x=FAIL"], ["sysctl", "hw.x=0"], "the bad one")])
        r = self.run_script(c)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(target.read_bytes(), b"old\xff\n")
        self.assertEqual(self.logged(), ["sysctl a=1", "sysctl hw.x=FAIL", "sysctl a=0"])
        self.assertIn("powerstar: failed: the bad one", r.stderr)

    def test_new_file_removed_on_failure(self):
        target = self.tmp / "new.conf"
        c = Change([FileWrite(str(target), "x\n", 0o644)], [Step(["sysctl", "FAIL"], None, "bad")])
        self.assertEqual(self.run_script(c).returncode, 1)
        self.assertFalse(target.exists())

    def test_quoting(self):
        c = Change([], [Step(["sysctl", "k=a b'c"], None, "q")])
        self.assertEqual(self.run_script(c).returncode, 0)
        self.assertEqual(self.logged(), ["sysctl k=a b'c"])


class ElevatorTest(unittest.TestCase):
    CHANGE = Change([FileWrite("/etc/sysctl.conf", "x\n", 0o644)], [Step(["sysctl", "a=1"], None, "a")])

    def elevate(self, responses, pkexec=True, xterm_writes_status=None):
        calls = []

        def run_cmd(argv):
            calls.append(argv[0])
            r = responses[argv[0]]
            if argv[0] == "xterm" and xterm_writes_status is not None:
                cmd = argv[-1]
                status = cmd.split("echo $? > ")[1].strip("'")
                Path(status).write_text(xterm_writes_status)
            return r

        with mock.patch("powerstar.privileged.shutil.which", return_value="/x/pkexec" if pkexec else None):
            return Elevator(FakeSystem(), run_cmd).run(self.CHANGE), calls

    AUTH = Result(1, "", "doas: Authentication required\n")

    def test_doas_n_ok(self):
        out, calls = self.elevate({"doas": Result(0, "", "")})
        self.assertTrue(out.ok)
        self.assertEqual(calls, ["doas"])

    def test_falls_through_to_xterm(self):
        out, calls = self.elevate({"doas": self.AUTH, "pkexec": Result(127, "", ""), "xterm": Result(0, "", "")}, xterm_writes_status="0\n")
        self.assertTrue(out.ok)
        self.assertEqual(calls, ["doas", "pkexec", "xterm"])

    def test_xterm_failure_has_log(self):
        out, _ = self.elevate({"doas": self.AUTH, "xterm": Result(0, "", "")}, pkexec=False, xterm_writes_status="1\n")
        self.assertFalse(out.ok)
        self.assertFalse(out.cancelled)

    def test_pkexec_cancelled(self):
        out, calls = self.elevate({"doas": self.AUTH, "pkexec": Result(126, "", "")})
        self.assertEqual((out.ok, out.cancelled), (False, True))
        self.assertEqual(calls, ["doas", "pkexec"])

    def test_other_doas_failure_stops(self):
        out, calls = self.elevate({"doas": Result(1, "", "powerstar: failed: a\n")})
        self.assertEqual((out.ok, out.cancelled, out.output), (False, False, "powerstar: failed: a\n"))
        self.assertEqual(calls, ["doas"])

    def test_no_status_file_is_cancelled(self):
        out, _ = self.elevate({"doas": self.AUTH, "xterm": Result(0, "", "")}, pkexec=False)
        self.assertEqual((out.ok, out.cancelled), (False, True))
