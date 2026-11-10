# Power Star

A system tray power manager for OpenBSD. One battery icon in your tray, and one place to see and change what OpenBSD exposes for power: charge thresholds, performance policy, CPU types, brightness, lid and power button actions, automatic suspend. Settings that need root are saved where OpenBSD keeps them, so they survive a reboot.

![Power Star Preferences and tray menu](https://raw.githubusercontent.com/kasramp/power_star/master/docs/screenshot.png)

## Requirements

- OpenBSD (tested on 8.0, amd64) running an X session with a system tray
- Python 3.11+ and `py3-qt6`
- `doas` for changes that need root (see [Notes](#notes))

## Installation

### Quick install (recommended)

```
$ doas pkg_add py3-qt6 py3-pipx
$ pipx install --system-site-packages powerstar
```

`--system-site-packages` lets pipx use the `py3-qt6` package instead of building Qt from PyPI.

Then run:

```
$ powerstar
```

### From source

```
$ git clone https://github.com/kasramp/power_star
$ cd power_star
$ python3 -m venv --system-site-packages venv && . venv/bin/activate
$ pip install -e .
$ powerstar
```

## First run

Power Star starts in the tray; there is nothing to set up. If no system tray is available it says so and exits. Controls your machine does not support (for example charge thresholds on a laptop without them) are disabled with a reason.

## Usage

The tray icon shows the charge level, a lightning bolt while charging and a plug on external power. It turns orange below 30% and red at 10% or less. Hover for the percentage, status and time left. Click it to open Preferences; right-click for the menu: status, health and cycles of each battery, CPU speed, temperature and fan, a Performance submenu (Automatic, High performance, Power saving), Suspend, Hibernate, Preferences and Quit. The Performance submenu needs no password but lasts only until the next reboot; Power Star re-applies your last choice when it starts.

| Tab            | What it drives                                                                                      |
|----------------|-----------------------------------------------------------------------------------------------------|
| Battery        | `hw.battery.chargemode`, `chargestart`, `chargestop`; per-battery charge, health, cycles, rate, voltage |
| Performance    | `hw.perfpolicy` (on AC and on battery), `hw.setperf`, `hw.blockcpu` (hyper-threads, P, E, L cores)  |
| Display        | Brightness (`xbacklight`) and screen off time (`xset` DPMS)                                         |
| Sleep & buttons| `machdep.lidaction`, `machdep.pwraction`, automatic suspend or hibernate at a battery % (`apmd -z`, `-Z`) |
| General        | Percentage on the icon, low battery notification and level, how often the status is read           |

Apply lists the files and commands first, then applies the values now and saves them for boot. Display settings belong to the X session, so they are stored in `~/.config/powerstar/config.toml` and applied each time Power Star starts.

## Starting at login

i3, in `~/.config/i3/config`:

```
exec --no-startup-id powerstar
```

A plain X session, in `~/.xsession` before the window manager starts:

```
powerstar &
```

Xfce: Settings, Session and Startup, Application Autostart, then add `powerstar`.

## Notes

- Power Star never asks for, sees or stores a password. For each Apply it writes one shell script and runs it as root, trying `doas -n` (works only if `doas.conf` allows it without a prompt), then `pkexec` (if polkit and a polkit agent are present), then an `xterm` running `doas`, where you type the password into doas's own prompt.
- `sysctl` values are set now and written to `/etc/sysctl.conf`: only the line of the changed key is replaced, a new key is appended below a `# added by powerstar` comment, and every other line is kept.
- `apmd` flags are changed with `rcctl`. Saving a performance policy removes `-A`, `-H` or `-L` from them, because they would override `hw.perfpolicy` when apmd starts.
- `hw.smt` is a deprecated alias of the S letter of `hw.blockcpu`. When the CPU types are saved, an `hw.smt` line is commented out (`# disabled by powerstar:`) so the two do not fight at boot. A choice that would block every core type is refused.
- OpenBSD's `sysctl` exits 0 when a write is rejected, so Power Star treats anything on stderr as a failure.
- If any step fails, the files are restored and the values already changed are set back.
- Powering off from the power button also needs `hw.allowpowerdown=1`, which only changes at boot, so that choice takes effect after a reboot.

## Manual

`powerstar(1)` covers the tray, tabs, authorisation, files and how to uninstall. Read it with `man powerstar` once installed system-wide (`powerstar --install-man`), or without installing with `powerstar --man`.

## License

GPL-3.0
