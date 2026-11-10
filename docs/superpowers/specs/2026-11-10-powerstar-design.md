# Power Star design

Date: 2026-11-10. Status: ready for the user's approval.

## Intent

Power Star is a system-tray power manager for OpenBSD laptops, in the spirit of
xfce4-power-manager but written for OpenBSD from scratch. The user wants to do
"complex power management at ease": every power capability that OpenBSD's base
CLI tools expose (apm, apmd, sysctl, zzz/ZZZ, xbacklight, wsconsctl, xset)
should be reachable from one GUI, and every setting must survive a reboot.

It continues the 2024 prototype in this repository (wxPython, ~150 lines:
tray icon, percentage tooltip, a placeholder settings window). The prototype is
replaced, not extended: the user chose to switch to PyQt6.

It is published on PyPI and follows the structure, packaging and conventions of
the sibling projects wifzf and vmmanager.

## Goals

1. **Tray icon** that always shows the battery state:
   - the icon reflects the charge level and whether it is charging,
     discharging or full;
   - hover tooltip: percentage, status (charging / discharging / charged /
     on AC, not charging), and the remaining time when discharging (time to
     full when charging, if apm reports it);
   - right-click menu: a few live stats, quick actions, and "Preferences...".
2. **Preferences window** with tabs, one concern per tab (below).
3. **Every setting persists across reboots**, using the OpenBSD-native place
   for it (`/etc/sysctl.conf`, `rcctl`, `/etc/wsconsctl.conf`, or the user's
   own config for per-session X settings).
4. **Root via doas only**, the same principle as vmmanager: no setuid helper,
   no daemon. Reads never need root.
5. Published on PyPI, one-command install, man page, README in wifzf's style
   with a screenshot.

## Non-goals

- No TUI. It is a GUI that lives in the tray.
- Not Xfce-integrated, not a panel plugin. Must work in any X session with a
  system tray (the test box runs i3 with i3bar).
- No custom kernel interfaces (ioctl to /dev/apm, sensor structs). Parse the
  CLI tools' output, as vmmanager does with vmctl.
- No Linux/FreeBSD support.

## Anti-goals (failure even if it "works")

- Silently rewriting the user's hand-written `/etc/sysctl.conf`,
  `/etc/rc.conf.local` or `/etc/wsconsctl.conf`. Edits are line-level, keep
  every other line and comment byte-for-byte, and are announced first.
- A setting that applies now but is lost at reboot, or one saved for boot but
  not applied now.
- Two sources fighting over the same setting (see apmd and hw.perfpolicy).
- A GUI that freezes while waiting for doas or a slow command.

## Platform facts (verified on the test box, OpenBSD 8.0, ThinkPad T480 20L6)

- `apm -l/-m/-a/-b/-P` give percent, minutes, AC, battery state, perf mode.
  `apm -m` prints the time to full charge while charging. Combined over all
  batteries.
- `/var/run/apmdev` is root:wheel 0660: wheel users can run `apm -A/-H/-L`,
  `zzz`, `ZZZ`, `apm -S` without doas. Others need doas.
- `sysctl hw.sensors` (no root) lists per battery `acpibatN`: last full and
  design capacity (Wh), remaining Wh, rate (W), voltage, state, discharge
  cycles; `acpiac0`, `acpibtn` (lid), `acpithinkpad0` (temp, fan RPM),
  `acpitz0` temp. The box has two batteries.
- `hw.battery.chargemode` (-1 force discharge, 0 inhibit, 1 charge within
  limits), `hw.battery.chargestart` (may be read-only on some hardware),
  `hw.battery.chargestop`. Only present on supporting hardware.
- `hw.perfpolicy`: `manual`, `auto`, `high`, or `AC,battery` pair such as
  `high,auto` (default). `hw.setperf` (0-100) is writable only in manual.
  `hw.cpuspeed` is the current MHz.
- `hw.blockcpu`: letters S (SMT), P (performance), E (efficiency), L
  (low-power efficiency) naming CPU types the scheduler avoids. Default on the
  box is `L`. CPU types per core are in dmesg (`cpuN: smt 1, core 0, ...,
  type SP`); the box has 4 P cores, each with an SMT sibling (type SP).
- `hw.smt` is deprecated ("sysctl: hw.smt deprecated, use hw.blockcpu") and is
  now an alias for the S letter (tested live 2026-11-10): `hw.blockcpu=SL`
  reads back `hw.smt=0` and 4 CPUs online; `hw.smt=1` turns `SL` back into
  `L`; `hw.smt=0` turns `L` into `SL`. So an `hw.smt=` line in sysctl.conf
  and a `hw.blockcpu=` line fight, and the later line wins.
- Blocking every core type present is accepted by the kernel and leaves only
  the boot CPU: `hw.blockcpu=P` on the box gave `hw.ncpuonline=1`.
- `machdep.lidaction` 0 nothing / 1 suspend / 2 hibernate.
  `machdep.pwraction` 0 nothing / 1 power off (needs `hw.allowpowerdown=1`) /
  2 suspend. `hw.allowpowerdown` cannot change at securelevel > 0, so only via
  `/etc/sysctl.conf`.
- apmd flags (via `rcctl set apmd flags ...`): `-A/-H/-L` set the perf policy
  at apmd startup; `-z N` / `-Z N` auto suspend / hibernate at N% on battery;
  `-w N` warnlow; `-t S` poll interval; `-a` ignore BIOS suspend on AC. The box
  runs `apmd -A`.
- Brightness: `xbacklight -get/-set` works as the user under X (RandR
  Backlight property). `wsconsctl` needs root (`/dev/ttyC0` is 0600).
- `xset q` shows DPMS standby/suspend/off timeouts; settable as the user.
- PyQt6 (`py3-qt6`) is packaged and installed on the box;
  `QSystemTrayIcon.isSystemTrayAvailable()` is True under i3.
- `/etc/sysctl.conf` on the box is hand-written and already has
  `hw.battery.chargestart=40`, `hw.battery.chargestop=80`, `hw.smt=1`.
- doas.conf: `permit persist keepenv :wheel`. A GUI has no tty, so plain
  `doas` cannot prompt.

## Preferences tabs (the user's tabbed layout, split by Claude)

Each tab shows only the controls the hardware supports; an unsupported or
read-only control is disabled with a one-line reason.

1. **Battery** – charge mode (charge within limits / do not charge / force
   discharge), start and stop thresholds. Per-battery stats: model, health
   (last full / design), cycles, rate, voltage, state.
2. **Performance** – policy on AC and on battery (auto / high / manual), manual
   CPU speed (`hw.setperf` 0-100), and CPU scheduling via `hw.blockcpu`:
   "disable hyper-threading (SMT)" (the S letter) plus a checkbox for each of
   P/E/L only when this machine has cores of that type. Letters for types the
   machine lacks are kept as they are. A choice that blocks every core type
   present is refused (it would leave one CPU). Live CPU speed, temperature, fan.
3. **Display** – brightness slider (xbacklight), screen blank / DPMS off after
   N minutes (xset). These are per X session, so they are stored in the user's
   config and re-applied when Power Star starts.
4. **Sleep & buttons** – lid close action, power button action,
   auto suspend or hibernate at N% on battery (apmd -z/-Z).
5. **General** – tray options: show percentage on the icon, low-battery
   notification on/off and level, poll interval.

Right-click menu: percentage + status + time line, current perf policy and
CPU MHz, a "Performance" submenu (auto / high / manual via apm -A/-H/-L,
live only, see "Decided with the user"), Suspend, Hibernate, Preferences...,
Quit.

## Persistence and root writes

- **sysctl settings**: apply now with `sysctl key=value` and save by editing
  `/etc/sysctl.conf` line-level: replace the existing uncommented line for the
  key, else append it with a `# added by powerstar` marker comment. Same
  temp-file + `doas install` + rollback pattern as vmmanager's
  `RootTransaction`.
- **apmd flags**: `rcctl set apmd flags ...` then `rcctl restart apmd`
  (and `rcctl enable apmd` if it is not enabled, after asking). Only the flags
  Power Star owns (`-z/-Z/-w`) are changed; other flags are kept.
- **Perf policy vs apmd** (Claude's call): `hw.perfpolicy` is the single source
  of truth, saved in `/etc/sysctl.conf`. If apmd_flags contains `-A`, `-H` or
  `-L`, which would override it at boot, Power Star removes that flag in the
  same change and says so in the confirmation.
- **Keyboard/display wsconsctl values** (if any are added later):
  `/etc/wsconsctl.conf`, same line-level edit.
- **User settings** (brightness, DPMS, tray options): `~/.config/powerstar/
  config.toml`, re-applied at start.
- **One doas per Apply**: all root steps of one Apply go into one doas call so
  the password is asked once. Order: write files, apply live values, check,
  roll back the files on failure.
- **Getting root from a GUI** (decided with the user, see below), in order:
  1. `doas -n` succeeds (the user has a nopass rule): no prompt.
  2. polkit is usable: `pkexec` runs the Apply script and the desktop's polkit
     agent shows its own password dialog. Exit 126 = the user cancelled, stop.
     Exit 127 = no agent / polkit not working (seen on the box under i3:
     "Error creating textual authentication agent"), fall through.
  3. A terminal (`xterm` from base X) runs `doas` on the Apply script, so the
     user types the password into the real doas prompt. The terminal closes
     when done; output and exit status come back to the GUI.
  Power Star never asks for or handles the password itself.
  If the user is not allowed to use doas or pkexec, root controls are
  disabled with the reason.
- Every Apply that touches root files shows a confirmation naming the files
  and commands, like vmmanager.

## Packaging and project structure (as in vmmanager)

- Package `powerstar/` (command `powerstar`), PyPI name `powerstar` (checked
  2026-11-10: powerstar, power-star, power_star, power.star all free).
- `pyproject.toml` with `requirements.txt` as dynamic dependencies,
  `publish_pypi.sh` copied from vmmanager, GitHub Actions test workflow
  (Python 3.11 and 3.14, unittest, mandoc lint), GPL-3.0 (already the repo
  licence).
- PyQt6 is NOT a pip dependency: PyPI has no OpenBSD wheels and pip would try
  to build it. Install is `doas pkg_add py3-qt6` then
  `pipx install --system-site-packages powerstar`. If PyQt6 is missing,
  `powerstar` prints that command and exits.
- `powerstar.1` man page, `--man`, `--install-man`, `--version`, as in
  vmmanager.
- Logic (parsing, config editing, transactions) is pure Python with unit tests
  against fakes and recorded command output from the box; the Qt layer is thin
  and smoke-tested with `QT_QPA_PLATFORM=offscreen` (PyQt6 from pip in CI on
  Linux).

## Calls made after the builder review (Claude's, for the user to check)

- **Deprecated/conflicting keys**: when a saved setting conflicts with another
  line in `/etc/sysctl.conf` (e.g. `hw.smt=1`, an alias of the S letter in
  `hw.blockcpu`), the conflicting line is commented out with a
  `# disabled by powerstar:` marker, never deleted, and the confirmation says
  so.
- **Power button "power off"** needs `hw.allowpowerdown=1`, which only changes
  at boot. It is offered; choosing it also saves `hw.allowpowerdown=1` and the
  control shows "takes effect after reboot" until the live value matches. This
  is the only "pending until reboot" setting.
- **One low-battery level**: Power Star's own tray notification (user config,
  no root). apmd `-w` is not offered: it only runs `/etc/apm/warnlow`, which
  does not exist by default.
- **Start at login**: no checkbox. README and man page give the line for i3
  (`exec --no-startup-id powerstar`), `~/.xsession`, and Xfce's autostart.
- **One doas per Apply** means a single root shell script per Apply that
  writes the staged files, applies the live values, and restores the backups
  if any step fails.

## Decided with the user (2026-11-10)

- **Right-click performance switch is live only, no password**: it uses
  `apm -A/-H/-L` through the apmd socket (wheel users need no root; others
  get the item disabled with the reason). Power Star remembers the choice in
  the user config and re-applies it at start. The permanent default is set in
  Preferences > Performance, which saves to `/etc/sysctl.conf` with one doas
  prompt per Apply.
- **Never touch doas.conf.** Power Star works with whatever the user has:
  `doas -n` succeeds (a nopass rule) → no prompt. Verified on the box: doas
  `persist` does not carry over between ptys, so each Apply asks again. The
  man page documents an optional nopass rule and its trade-off.
- **polkit first, doas in a terminal as fallback; no password dialog of our
  own** (the user's decision): an app collecting the root password itself
  looks like phishing and teaches bad habits; the trusted prompts are the
  polkit agent and doas's own. polkit is in ports, not base, and needs dbus,
  ConsoleKit and a desktop agent, so it is detected by trying it, not
  assumed.

## Left to the builder

- Module split, icon drawing details, exact widget layout.
- Poll interval default and how the stats refresh.
- Whether the tray icon is drawn with QPainter or uses the existing PNGs.
