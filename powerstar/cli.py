"""Command-line entry point."""

import argparse
import importlib.util
import sys

from powerstar import __version__


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="powerstar", description="A system tray power manager for OpenBSD")
    p.add_argument("--version", action="store_true", help="show the version")
    p.add_argument("--man", action="store_true", help="show the manual page")
    p.add_argument("--install-man", action="store_true", help="install the manual page (asks for doas)")
    args = p.parse_args(argv)
    if args.version:
        print(f"powerstar {__version__}")
        return 0
    if args.man or args.install_man:
        from powerstar import manpages

        return manpages.view() if args.man else manpages.install()
    if importlib.util.find_spec("PyQt6") is None:
        print(
            "PyQt6 is missing. Install it with:\n"
            "  doas pkg_add py3-qt6\n"
            "  pipx install --system-site-packages powerstar",
            file=sys.stderr,
        )
        return 1
    from powerstar.ui.tray import run

    return run()
