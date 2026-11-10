# Power Star v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 2024 wxPython prototype with a PyQt6 tray power manager for OpenBSD that reads every power value the base CLI exposes, changes them from a tabbed Preferences window, and saves them so they survive reboot.

**Architecture:** Pure-Python core (parsing, config-file edits, change planning, privileged script building) with no Qt import, fully unit-tested against output recorded on the test box. A thin `powerstar/ui/` layer (tray icon, menu, Preferences) calls the core. Root work is one generated `sh` script per Apply, run through `doas -n`, then `pkexec`, then `xterm -e doas`.

**Tech Stack:** Python >= 3.11 (tomllib), PyQt6 from OpenBSD packages (`py3-qt6`), unittest, mandoc. Packaging copied from vmmanager (`/home/kixz/Private/mygit/vmmanager`).

**Spec:** `docs/superpowers/specs/2026-11-10-powerstar-design.md`

## Global Constraints

- Python `>=3.11`; package `powerstar`, command `powerstar`, PyPI name `powerstar`, version `0.1.0` in BOTH `pyproject.toml` and `powerstar/__init__.py`.
- PyQt6 is NOT a pip dependency (`dependencies = []`). Missing PyQt6 → print `doas pkg_add py3-qt6` and `pipx install --system-site-packages powerstar`, exit 1.
- Only `powerstar/ui/` and `powerstar/cli.py` (lazily) may import PyQt6.
- Never ask for, read, or store a password. Never edit doas.conf.
- Edits to `/etc/sysctl.conf` are line-level; every other byte is kept. New lines get the comment line `# added by powerstar` above them; conflicting lines are commented as `# disabled by powerstar: <original line>`.
- Every root change shows a confirmation listing the files and commands first.
- Setting applied now ⇔ saved for boot (except `hw.allowpowerdown`, which is saved only and shown "takes effect after reboot").
- Licence GPL-3.0-or-later; author "Kasra Madadipouya <kasra@madadipouya.com>" (as vmmanager).
- The GUI thread never blocks on doas/pkexec/xterm or any root command.

## Review Focus

1. Machine without `hw.battery.*` (desktop, older laptop) or without a battery (`apm -l` = -1 / state 4): app must start, tooltip says "No battery", Battery tab controls disabled with reason. → tests in Task 2 and Task 8.
2. Hand-written sysctl.conf with comments, duplicates, a key set twice, no trailing newline: edit changes only the intended line(s). → tests in Task 3.
3. Apply where a later step fails (e.g. `sysctl hw.battery.chargestart=` rejected): files restored and earlier live values undone. → test in Task 6 running the generated script with fake commands.
4. apmd not running / `/var/run/apmdev` not accessible: right-click performance items disabled with reason, no crash. → test in Task 7.
5. User cancels pkexec (exit 126) or closes the xterm: nothing changed, UI says "cancelled". → test in Task 6.

## File structure

```
powerstar/__init__.py        __version__ = "0.1.0"
powerstar/errors.py          PowerStarError(message, detail="")
powerstar/system.py          System.run(argv) -> Result(rc, out, err); read_file(path)
powerstar/readings.py        parse apm / sysctl / dmesg.boot; read_state(sys) -> State
powerstar/sysctlconf.py      pure line-level edits of sysctl.conf text
powerstar/apmdflags.py       pure edits of an apmd flags string
powerstar/blockcpu.py        pure hw.blockcpu letter logic
powerstar/changes.py         plan_changes(...) -> Change (steps + files + description)
powerstar/privileged.py      build_script(change) -> str; Elevator.run(change) -> Outcome
powerstar/userconfig.py      ~/.config/powerstar/config.toml load/save
powerstar/session.py         user-level actions: xbacklight, xset dpms, apm -A/-H/-L
powerstar/manpages.py        --man / --install-man
powerstar/man/powerstar.1
powerstar/cli.py             argparse entry point
powerstar/ui/icon.py         draw_icon(...) -> QIcon; status_text(state) -> str
powerstar/ui/tray.py         Tray(QSystemTrayIcon), menu, timer, notifications
powerstar/ui/prefs.py        Preferences(QDialog) with 5 tabs
powerstar/ui/worker.py       run a callable off the GUI thread, emit result
tests/fixtures/box-raw.txt   raw output recorded on the box 2026-11-10 (exists)
tests/test_*.py              one per core module + test_ui_smoke.py
```

Delete the prototype: `powerstar.py`, `utils/`, `icons/` (the icon is drawn with QPainter, Claude's call per "left to the builder").

## Recorded platform facts the code relies on (from the box)

- `apm -blmaP` prints five lines in this FIXED order whatever the flag order: battery state (0 high,1 low,2 critical,3 charging,4 absent,255 unknown), percent, minutes or `unknown`, AC (0,1,2,255), perf mode (0 manual, 1 auto). One call per poll.
- `sysctl hw.sensors` lines: `hw.sensors.acpibat0.watthour0=18.70 Wh (last full capacity)`, `watthour3 ... (remaining capacity)`, `watthour4 ... (design capacity)`, `power0=0.00 W (rate)`, `volt1=11.90 VDC (current voltage)`, `raw0=0 (battery idle), OK`, `raw1=756 (discharge cycles)`, `acpithinkpad0.fan0=0 RPM`, `cpu0.temp0=43.00 degC`, `acpibtn1.indicator0=Off (lid open)`.
- `/var/run/dmesg.boot` is world-readable: `cpu4: smt 1, core 0, package 0, type SP` and `acpibat0 at acpi0: BAT0 model "01AV421" serial   748 type LiP oem "SMP"`.
- `sysctl` of a missing key prints `sysctl: second level name battery in hw.battery is invalid` style errors and rc != 0: query keys one `sysctl` call with all keys; parse what came back; missing keys = unsupported.
- `rcctl get apmd flags` → `-A`; `rcctl check apmd` → `apmd(ok)` rc 0.

---

### Task 1: Skeleton, CLI, CI, remove prototype

**Files:**
- Create: `pyproject.toml`, `powerstar/__init__.py`, `powerstar/errors.py`, `powerstar/system.py`, `powerstar/cli.py`, `.github/workflows/test.yml`, `tests/__init__.py`, `tests/fakes.py`, `tests/test_cli.py`
- Delete: `powerstar.py`, `utils/`, `icons/`

**Interfaces:**
- Produces: `PowerStarError(message: str, detail: str = "")` with `.message`, `.detail`; `Result(rc: int, out: str, err: str)`; `System.run(argv: list[str], check: bool = True) -> Result` (raises `PowerStarError(f"{argv[0]} failed", detail=err)` on rc != 0 when `check`; `PowerStarError("<cmd>: command not found")` on OSError); `System.read_file(path: Path) -> str | None`. `tests/fakes.py: FakeSystem(responses: dict[tuple[str, ...], Result | str])` records `.calls`, returns `Result(0, str, "")` for str values, raises for missing keys. `cli.main(argv: list[str] | None = None) -> int`.

- [ ] **Step 1: Write failing tests** in `tests/test_cli.py`: `test_version` (`main(["--version"])` prints `powerstar 0.1.0`, returns 0); `test_missing_pyqt6_prints_install_hint` (patch `importlib.util.find_spec` to return None for `PyQt6`; `main([])` returns 1 and stderr contains `doas pkg_add py3-qt6` and `pipx install --system-site-packages powerstar`).
- [ ] **Step 2: Run** `python -m unittest discover -s tests -v` → FAIL (module missing).
- [ ] **Step 3: Implement.** `pyproject.toml` mirrors vmmanager's (name `powerstar`, description "A system tray power manager for OpenBSD", keywords openbsd/apm/apmd/battery/power/tray/qt, classifiers `Environment :: X11 Applications :: Qt`, `Operating System :: POSIX :: BSD :: OpenBSD`, `Topic :: System :: Power (UPS)`; URLs `https://github.com/OpenBSDGuy/power_star`; `dependencies = []`; `packages = ["powerstar", "powerstar.ui"]`; package-data `man/*`; script `powerstar = "powerstar.cli:main"`). `cli.main` with argparse `--version`, `--man`, `--install-man` (Task 10 wires the last two); with no flag: check PyQt6, then `from powerstar.ui.tray import run; return run()`. `system.py` is vmmanager's `System` minus every doas/suspend/install part. Delete prototype files.
- [ ] **Step 4: CI** `.github/workflows/test.yml` like vmmanager's: matrix 3.11/3.14, `pip install PyQt6`, `sudo apt-get install -y libegl1 libxkbcommon0`, `python -m py_compile powerstar/*.py powerstar/ui/*.py`, `QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v`, mandoc lint step guarded by `hashFiles('powerstar/man/powerstar.1')`.
- [ ] **Step 5: Run tests** → PASS. **Commit** "Start the PyQt6 rewrite: package skeleton, CLI, CI".

### Task 2: Readings (parse everything, no root)

**Files:** Create `powerstar/readings.py`, `tests/test_readings.py`

**Interfaces:**
- Consumes: `System.run`, `System.read_file`.
- Produces:
  - `ApmStatus(state: int, percent: int | None, minutes: int | None, ac: int, perf_auto: bool)`; `parse_apm(out: str) -> ApmStatus` (percent `None` when < 0 or state 4; minutes `None` for `unknown`).
  - `Battery(name: str, model: str | None, last_full_wh: float | None, design_wh: float | None, remaining_wh: float | None, rate_w: float | None, voltage: float | None, status: str | None, cycles: int | None)` with property `health_percent -> int | None` (round(last_full/design*100)).
  - `parse_sensors(out: str) -> Sensors` where `Sensors(batteries: list[Battery], cpu_temp: float | None, fan_rpm: int | None, lid_open: bool | None)`; battery `status` is the text in parentheses of `raw0` (e.g. `battery idle`); cpu temp prefers `cpu0.temp0`, else `acpitz0.temp0`.
  - `parse_sysctl(out: str) -> dict[str, str]` (`key=value` lines only).
  - `cpu_types(dmesg: str) -> set[str]` returns letters present among P/E/L plus `S` if any core has an `S` type (box → `{"P", "S"}`); `battery_models(dmesg: str) -> dict[str, str]` (`{"acpibat0": "01AV421"}`).
  - `SYSCTL_KEYS = ["hw.battery.chargemode", "hw.battery.chargestart", "hw.battery.chargestop", "hw.perfpolicy", "hw.setperf", "hw.cpuspeed", "hw.blockcpu", "hw.ncpuonline", "hw.allowpowerdown", "machdep.lidaction", "machdep.pwraction"]`
  - `State(apm: ApmStatus | None, sensors: Sensors, sysctl: dict[str, str], cpu_types: set[str], apmd_running: bool, apmd_flags: str)`; `read_state(sys) -> State` (apm failure → `apm=None`; sysctl called once with all keys and `check=False`; `rcctl check apmd` rc 0 → running; `rcctl get apmd flags`).

- [ ] **Step 1: Failing tests** using text cut from `tests/fixtures/box-raw.txt`: `parse_apm("0\n82\nunknown\n1\n1\n")` == `ApmStatus(0, 82, None, 1, True)`; `parse_apm("4\n-1\nunknown\n1\n0\n").percent is None`; two batteries parsed, `acpibat0.health_percent == 78`, `acpibat1.cycles == 380`, fan 0, lid_open True, cpu_temp 43.0; `cpu_types` of the 8 box cpu lines == `{"P","S"}`; `battery_models` gives both models; `read_state` on a FakeSystem where `apm` raises → `state.apm is None` and no exception; sysctl output missing `hw.battery.*` → those keys absent from `state.sysctl`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS. **Step 5: Commit** "Read battery, sensor and sysctl state".

### Task 3: sysctl.conf line edits

**Files:** Create `powerstar/sysctlconf.py`, `tests/test_sysctlconf.py`

**Interfaces:**
- Produces: `set_value(text: str, key: str, value: str) -> str`; `disable_key(text: str, key: str) -> str`; `current_value(text: str, key: str) -> str | None`.
- Rules: an "active line" is `^\s*<key>\s*=` (not commented). `set_value` replaces the LAST active line for the key with `key=value` keeping its leading whitespace and any trailing ` # comment`; earlier active duplicates become `# disabled by powerstar: <line>`; no active line → append `# added by powerstar\nkey=value\n` (adding a newline first if the text lacks a trailing one). Unchanged value → text returned unchanged. `disable_key` comments every active line of the key. `current_value` returns the last active line's value.

- [ ] **Step 1: Failing tests:** box text (`... # start and stop charge at 40 and 80\nhw.battery.chargestart=40\nhw.battery.chargestop=80\n`) with `set_value(..., "hw.battery.chargestop", "90")` changes exactly that line; append case; no trailing newline case; duplicate key case; inline comment kept (`hw.smt=1 # x` → `hw.smt=0 # x`); commented line `#hw.perfpolicy=high` ignored; `disable_key(text, "hw.smt")` yields `# disabled by powerstar: hw.smt=1`; idempotent `set_value` returns identical text.
- [ ] **Step 2–4:** run FAIL, implement, run PASS. **Step 5: Commit** "Edit sysctl.conf line by line".

### Task 4: apmd flags and hw.blockcpu logic

**Files:** Create `powerstar/apmdflags.py`, `powerstar/blockcpu.py`, `tests/test_apmdflags.py`, `tests/test_blockcpu.py`

**Interfaces:**
- `apmdflags.auto_sleep(flags: str) -> tuple[str | None, int | None]` returns `("suspend", 5)` for `-z 5`/`-z5`, `("hibernate", N)` for `-Z`, `(None, None)` otherwise (last of -z/-Z wins, as apmd(8)).
- `apmdflags.with_auto_sleep(flags: str, mode: str | None, percent: int | None) -> str` removes all `-z/-Z` (with attached or separate value) and appends `-z N`/`-Z N`; other flags kept in order.
- `apmdflags.without_perf_flags(flags: str) -> str` removes `-A`, `-H`, `-L`, including inside combined flags like `-aA` (→ `-a`).
- `blockcpu.blocked(value: str) -> set[str]`; `blockcpu.compose(current: str, wanted: set[str], present: set[str]) -> str` — letters in `present` follow `wanted`, letters not in `present` are kept from `current`; output order `S P E L`.
- `blockcpu.problem(wanted: set[str], present: set[str]) -> str | None` returns `"This would leave only one CPU running"` when every core-type letter in `present - {"S"}` is blocked.

- [ ] **Step 1: Failing tests:** `with_auto_sleep("-A", "suspend", 5) == "-A -z 5"`; `with_auto_sleep("-A -z 5 -t 30", None, None) == "-A -t 30"`; `auto_sleep("-z5 -Z 3") == ("hibernate", 3)`; `without_perf_flags("-A -z 5") == "-z 5"`; `without_perf_flags("-aA") == "-a"`; `compose("L", {"S"}, {"P","S"}) == "SL"`; `compose("SL", set(), {"P","S"}) == "L"`; `problem({"P"}, {"P","S"})` is the message; `problem({"S"}, {"P","S"}) is None`.
- [ ] **Step 2–4:** FAIL, implement, PASS. **Step 5: Commit** "apmd flags and hw.blockcpu helpers".

### Task 5: Change planning

**Files:** Create `powerstar/changes.py`, `tests/test_changes.py`

**Interfaces:**
- Consumes: Tasks 2–4.
- Produces:
  - `Wanted` dataclass, every field optional (None = leave alone): `chargemode: int | None`, `chargestart: int | None`, `chargestop: int | None`, `perfpolicy: str | None` (e.g. `"high,auto"`), `setperf: int | None`, `blocked: set[str] | None`, `lidaction: int | None`, `pwraction: int | None`, `auto_sleep: tuple[str | None, int | None] | None`.
  - `Step(do: list[str], undo: list[str] | None, label: str)`; `FileWrite(path: str, content: str, mode: int)`; `Change(files: list[FileWrite], steps: list[Step])` with `describe() -> list[str]` (one line per file "Edit /etc/sysctl.conf: hw.battery.chargestop=90" etc. and one per step label) and `empty -> bool`.
  - `plan_changes(state: State, wanted: Wanted, sysctl_conf: str) -> Change` raising `PowerStarError` on invalid input.
- Rules (from the spec):
  - Only values that differ from `state.sysctl` (live) OR from the sysctl.conf value produce work. One `FileWrite("/etc/sysctl.conf", new_text, 0o644)` for all sysctl keys (mode: keep 0644; file absent → content starts empty).
  - Live step per changed key: `do=["sysctl", f"{k}={v}"]`, `undo=["sysctl", f"{k}={old}"]`.
  - Validation: `0 <= chargestart < chargestop <= 100`; `setperf` 0–100 and only with a `manual` part in perfpolicy; perfpolicy parts each in `{"auto","high","manual"}`, at most 2 parts; `blockcpu.problem` → error; lid 0–2; pwr 0–2; auto_sleep percent 1–50.
  - Ordering: chargestop before chargestart when the new start >= the current live stop, else start first; `hw.perfpolicy` before `hw.setperf` (both live and in the file).
  - `blocked` → `hw.blockcpu=<compose(...)>`, and `disable_key(text, "hw.smt")` (the description says "Comment out hw.smt (deprecated alias of the S letter)").
  - `pwraction == 1` and live `hw.allowpowerdown != "1"` → add `hw.allowpowerdown=1` to the FILE only, no live step; description "hw.allowpowerdown=1 (takes effect after reboot)".
  - `perfpolicy` set and `state.apmd_flags` contains -A/-H/-L → step `rcctl set apmd flags <without_perf_flags(...)>` (undo: old flags) and description "Remove -A from apmd flags (it overrides hw.perfpolicy at boot)". If the result is empty, use `["rcctl", "set", "apmd", "flags", ""]`.
  - `auto_sleep` changed → `rcctl set apmd flags <with_auto_sleep(...)>`, `rcctl enable apmd` if not running (description says it), then `rcctl restart apmd` (undo: none). Merge with the perf-flag removal into one flags value.

- [ ] **Step 1: Failing tests** on the box state (`sysctl` dict from fixture, `apmd_flags="-A"`, `cpu_types={"P","S"}`): chargestop 90 → one file write with only that line changed + one live step `["sysctl","hw.battery.chargestop=90"]` with undo `=80`; chargestart 85 + chargestop 95 → stop step before start step; chargestart 90 chargestop 80 → PowerStarError; perfpolicy `"high,auto"` → sysctl.conf gains `hw.perfpolicy=high,auto` and steps include `["rcctl","set","apmd","flags",""]`; blocked `{"S"}` → `hw.blockcpu=SL` and the `hw.smt=1` line disabled; blocked `{"P"}` → error; pwraction 1 with allowpowerdown "0" → no live step for allowpowerdown; auto_sleep ("suspend", 5) → flags `-A -z 5` (when perfpolicy untouched) and a restart step; wanted all-None → `change.empty`.
- [ ] **Step 2–4:** FAIL, implement, PASS. **Step 5: Commit** "Plan root changes from wanted settings".

### Task 6: Privileged script and elevation

**Files:** Create `powerstar/privileged.py`, `tests/test_privileged.py`

**Interfaces:**
- Consumes: `Change`, `FileWrite`, `Step` (Task 5); `System`.
- Produces:
  - `build_script(change: Change, staged: dict[str, str], backup_dir: str) -> str` — `staged` maps each FileWrite path to a temp file already holding the new content. The script (POSIX sh, `set -u`, all values `shlex.quote`d): for each file, `cp -p` the original to backup_dir (or record that it did not exist), `install -o root -g wheel -m <mode> <staged> <path>`; then each step's `do`. On the first failure: run the undo of every completed step in reverse, restore every file (or `rm -f` the ones that did not exist), print `powerstar: failed: <label>` to stderr, exit 1. Success exits 0.
  - `Outcome(ok: bool, cancelled: bool, output: str)`.
  - `Elevator(sys: System, run_cmd: Callable[[list[str]], Result] | None = None)` with `run(change: Change) -> Outcome` that writes the staged files and script into a fresh `tempfile.mkdtemp(prefix="powerstar.")` (0700), then tries in order:
    1. `doas -n sh <script>` — success → done. rc != 0 with stderr containing `Authentication required` or `not permitted` → next method; any other failure → `Outcome(False, False, err)` (the script ran and failed: never run it twice).
    2. If `shutil.which("pkexec")`: `pkexec /bin/sh <script>` — rc 0 ok; 126 → `Outcome(False, True, "cancelled")`; 127 → next method; other → failure.
    3. `xterm -T "Power Star needs root" -e sh -c 'doas sh <script> > <log> 2>&1; echo $? > <status>'`; read status file: missing → cancelled; "0" → ok; else failure with the log. The xterm is told what is happening by an `echo` line first.
  - The temp dir is removed afterwards. Never passes a password anywhere.

- [ ] **Step 1: Failing tests.** Script tests run the generated script as the current user with a `PATH` prefix dir holding fake `install` (copies src to dest), `sysctl` (appends args to a log; exits 1 when the arg contains `FAIL`), `rcctl` (logs) and target paths inside a temp dir: success writes the file and logs both sysctl calls; a step `["sysctl","hw.x=FAIL"]` after a successful step → exit 1, the file is restored byte-for-byte, the earlier step's undo is in the log, stderr has `powerstar: failed:`; a file that did not exist before is removed on failure; a value containing a space and `'` survives quoting. Elevator tests with a fake `run_cmd`: doas -n ok → pkexec never called; doas "Authentication required" + pkexec 127 → xterm called; pkexec 126 → `cancelled` and xterm not called; doas -n rc 1 with other stderr → failure and nothing else called; no status file after xterm → cancelled.
- [ ] **Step 2–4:** FAIL, implement, PASS. **Step 5: Commit** "Run root changes through doas, pkexec or a doas terminal".

### Task 7: User config and session actions

**Files:** Create `powerstar/userconfig.py`, `powerstar/session.py`, `tests/test_userconfig.py`, `tests/test_session.py`

**Interfaces:**
- `userconfig.DEFAULTS = {"brightness": None, "screen_off_minutes": None, "menu_perf": None, "show_percent": True, "notify_low": True, "low_percent": 10, "poll_seconds": 5}`; `load(path: Path | None = None) -> dict` (defaults merged; missing or broken file → defaults; default path `$XDG_CONFIG_HOME/powerstar/config.toml` or `~/.config/powerstar/config.toml`); `save(cfg: dict, path: Path | None = None)` writes a flat TOML of str/int/bool, skipping None values.
- `session.get_brightness(sys) -> int | None` (`xbacklight -get`, rounded; failure → None); `set_brightness(sys, percent: int)`; `set_screen_off(sys, minutes: int)` (0 → `xset -dpms`; else `xset +dpms` then `xset dpms S S S` with S = minutes*60); `set_perf(sys, mode: str)` with mode in `"A","H","L"` → `apm -A|-H|-L`; `perf_problem(state) -> str | None` → `"apmd is not running"` if not `state.apmd_running`, `"No access to /var/run/apmdev (needs the wheel group)"` if `os.access("/var/run/apmdev", os.R_OK | os.W_OK)` is false; `reapply(sys, cfg)` applies brightness, screen-off and menu_perf when set, ignoring failures of each (returns list of error strings).

- [ ] **Step 1: Failing tests:** load of missing file == DEFAULTS; save/load round-trip; broken TOML → defaults; `set_screen_off(fake, 10)` calls `xset +dpms` then `xset dpms 600 600 600`; `set_screen_off(fake, 0)` calls `xset -dpms`; `get_brightness` of `"36.237624"` → 36; `perf_problem` with `apmd_running=False` → message (Review Focus 4); `reapply` with a failing xbacklight still runs the apm call.
- [ ] **Step 2–4:** FAIL, implement, PASS. **Step 5: Commit** "User config and session-level settings".

### Task 8: Tray icon drawing and status text

**Files:** Create `powerstar/ui/__init__.py`, `powerstar/ui/icon.py`, `tests/test_icon.py`

**Interfaces:**
- `status_text(state: State) -> str` (pure, no Qt use inside): first line `82% — Charging`, `82% — Discharging`, `100% — Charged`, `82% — Plugged in, not charging`, or `No battery`; second line when discharging with minutes: `1:23 remaining`; when charging with minutes: `1:23 until full`. "Plugged in, not charging" = AC 1 and battery state not 3 and percent < 100.
- `draw_icon(percent: int | None, charging: bool, on_ac: bool, show_percent: bool, size: int = 64) -> QIcon` — battery outline; fill width proportional to percent; fill green ≥ 30, orange 11–29, red ≤ 10; lightning bolt when charging; plug mark when on AC and not charging; the number centred in the body when `show_percent` (100 drawn as "F" is NOT allowed; draw "100" with a smaller font); `None` percent → outline with "?".

- [ ] **Step 1: Failing tests:** status_text on the box state → `"82% — Plugged in, not charging"`; discharging state with minutes 83 → second line `1:23 remaining`; no-battery state → `"No battery"` (Review Focus 1). Offscreen smoke: `QApplication` created once in `setUpModule` with `QT_QPA_PLATFORM=offscreen`; `draw_icon(5, False, False, True)` returns a non-null icon whose 64px pixmap has a red pixel inside the body.
- [ ] **Step 2–4:** FAIL, implement, PASS. **Step 5: Commit** "Draw the tray icon and its tooltip text".

### Task 9: Tray, menu and Preferences window

**Files:** Create `powerstar/ui/worker.py`, `powerstar/ui/tray.py`, `powerstar/ui/prefs.py`, `tests/test_ui_smoke.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `tray.run() -> int` (creates QApplication, `setQuitOnLastWindowClosed(False)`, exits 1 with a message box if `QSystemTrayIcon.isSystemTrayAvailable()` is false, calls `session.reapply`, starts the tray); `Tray(sys: System, elevator: Elevator)`; `Preferences(state: State, cfg: dict, sys: System, elevator: Elevator)`; `worker.run_async(fn: Callable[[], T], done: Callable[[T | BaseException], None])` using a `QThread`-backed object and a queued signal.
- Behaviour:
  - Timer every `cfg["poll_seconds"]` runs `read_state` via `run_async`; on result update icon (`draw_icon`), tooltip (`status_text`), the menu's info lines, and fire `showMessage("Battery low", ...)` once when discharging and percent drops to ≤ `low_percent` (re-armed when AC returns).
  - Menu: disabled info actions (status line; per battery `BAT0: 78% health, 756 cycles`; `CPU 400 MHz, 44 °C, fan 0 RPM`; `Performance: auto`), separator, submenu "Performance" with checkable "Automatic" (A) / "High performance" (H) / "Power saving" (L) → `session.set_perf` + save `menu_perf`; disabled with `perf_problem` text as tooltip and as a disabled line; "Suspend" (`zzz`), "Hibernate" (`ZZZ`), separator, "Preferences…", "Quit". Left click opens Preferences.
  - Preferences: `QTabWidget` tabs "Battery", "Performance", "Display", "Sleep & buttons", "General", plus Apply / Close buttons. Root-backed controls (all of Battery/Performance/Sleep tabs) are built from `state.sysctl`; a missing key → control disabled with a reason label "Not supported on this machine". Apply: build `Wanted` from controls that changed, `plan_changes`, show a confirmation `QMessageBox` listing `change.describe()`, then `run_async(lambda: elevator.run(change))`; while running, buttons are disabled and a label says "Waiting for authorisation…"; afterwards show the error output on failure, "Cancelled" on cancel, and re-read state. A successful Performance apply clears `cfg["menu_perf"]`. Display and General tabs save to the user config and apply at once (no root): brightness slider (disabled if `get_brightness` is None), screen-off minutes spin box (0 = never), show percent, low-battery notify + level, poll seconds (2–60). Battery tab also shows each battery's stats in a read-only grid. Performance tab: AC policy + battery policy combos (auto/high/manual), setperf slider enabled only when a manual policy is chosen, SMT + P/E/L checkboxes per `state.cpu_types` with `blockcpu.problem` shown inline, live CPU MHz/temp/fan. Sleep tab: lid action and power-button action combos (labels from acpibtn(4)), "power off" shows "takes effect after reboot" when allowpowerdown is not 1; auto sleep combo (Off/Suspend/Hibernate) + percent spin box; when apmd is not running, a note that Apply will enable it.
- [ ] **Step 1: Failing smoke tests** (offscreen, FakeSystem built from the fixture, a fake Elevator recording the Change): Preferences constructs with the box state and has 5 tabs with those names; with a state lacking `hw.battery.*` the charge controls are disabled (Review Focus 1); setting the stop spin box to 90 and calling the Apply handler with the confirmation auto-accepted gives the fake elevator a Change whose describe() mentions `hw.battery.chargestop=90`; Tray constructs and its menu contains "Preferences…" and "Quit"; with `apmd_running=False` the Performance submenu is disabled.
- [ ] **Step 2–4:** FAIL, implement, PASS. **Step 5: Commit** "Tray menu and Preferences window".

### Task 10: Man page

**Files:** Create `powerstar/man/powerstar.1`, `powerstar/manpages.py`, `tests/test_manpages.py`; modify `powerstar/cli.py`

**Interfaces:** `manpages.view(sys) -> int` (`man -l <bundled>` interactive); `manpages.install() -> int` runs `doas install -o root -g wheel -m 0644 <page> /usr/local/man/man1/powerstar.1` then `doas makewhatis /usr/local/man` via `subprocess.call` (CLI has a tty, so plain doas prompts).
- Page sections (mdoc, `mandoc -Tlint -Wwarning` clean): NAME, SYNOPSIS, DESCRIPTION (tray, menu, each tab and the exact sysctl/apmd/xbacklight/xset it drives), FILES (`~/.config/powerstar/config.toml`, `/etc/sysctl.conf`, `/etc/rc.conf.local`), AUTHORISATION (doas -n → pkexec → doas in xterm; Power Star never sees the password; it runs `sh <script>` as root, so the only doas rule that removes the prompt is `permit nopass <user> cmd sh`, which is password-free root: documented as possible, not recommended), STARTING AT LOGIN (i3 `exec --no-startup-id powerstar`, `~/.xsession` `powerstar &`, Xfce Session and Startup), UNINSTALL (`pipx uninstall powerstar`, remove the man page), SEE ALSO (apm 8, apmd 8, sysctl 8, acpibtn 4, doas 1, xbacklight 1, xset 1, rcctl 8 — sorted by section then name).
- [ ] **Step 1:** failing test: `bundled()` lists `powerstar.1`; `main(["--man"])` calls `man -l` with the bundled path (patched). **Step 2–4:** FAIL, implement, PASS (+ `mandoc -Tlint` locally if available, else on the box). **Step 5: Commit** "Add the powerstar(1) man page".

### Task 11: README, screenshot, publish script

**Files:** Create `README.md` (replace), `docs/make_screenshot.py`, `docs/screenshot.png`, `publish_pypi.sh`

- README in wifzf/vmmanager structure: pitch, screenshot, Requirements (OpenBSD, X with a system tray, `py3-qt6`), Installation (`doas pkg_add py3-qt6` + `pipx install --system-site-packages powerstar`; from source), First run, Usage (menu and tabs table), Starting at login, Notes (authorisation order; settings saved to /etc/sysctl.conf and apmd flags), Manual, License. Image via absolute `https://raw.githubusercontent.com/OpenBSDGuy/power_star/master/docs/screenshot.png`.
- `docs/make_screenshot.py`: offscreen Qt, the fixture state, grabs the Preferences window (Battery tab) and the tray menu, composes them on one canvas with an XFCE-style title bar (user prefers XFCE look over macOS buttons), saves `docs/screenshot.png`.
- `publish_pypi.sh`: copy of vmmanager's with `openbsd-vmmanager`/`vmmanager` → `powerstar`.
- [ ] Run `python -m docs.make_screenshot`, view the PNG, `python -m build` + `twine check dist/*` (or on the box), commit "README, screenshot and publish script".

### Task 12: Live acceptance on the test box

Not code; verify on the test box (password from the user, never stored) in the running i3 session (`DISPLAY=:0`):
- [ ] Back up `/etc/sysctl.conf` and `apmd` flags to `~/powerstar-backup/` first.
- [ ] Build the wheel, `pipx install --system-site-packages <wheel>`; `powerstar --version`.
- [ ] Start `powerstar` on :0; tray icon visible (screenshot with `xwd -root` → PNG), tooltip text matches `apm`.
- [ ] Apply chargestop 85 via Preferences: doas -n fails → pkexec 127 → xterm doas appears; the user (or a pty helper) types the password; `/etc/sysctl.conf` line changed, `sysctl hw.battery.chargestop` = 85. Revert to 80.
- [ ] Rollback check: a forced failing step leaves sysctl.conf identical (sha256).
- [ ] Right-click Performance → High: `apm -P` = 0, `hw.setperf` 100; back to Automatic.
- [ ] Brightness slider changes `xbacklight -get`.
- [ ] Restore the backups; record results in the vault note.
