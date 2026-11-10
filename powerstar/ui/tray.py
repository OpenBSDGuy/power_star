"""System tray icon, its menu and the poll timer."""

import sys as _sys

from PyQt6.QtGui import QAction, QActionGroup
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from powerstar import session, userconfig
from powerstar.errors import PowerStarError
from powerstar.privileged import Elevator
from powerstar.readings import State, read_state
from powerstar.system import System
from powerstar.ui import worker
from powerstar.ui.icon import draw_icon, status_text
from powerstar.ui.prefs import Preferences

PERF_MODES = [("A", "Automatic"), ("H", "High performance"), ("L", "Power saving")]


def info_lines(state: State) -> list[str]:
    lines = [status_text(state).replace("\n", ", ")]
    for b in state.sensors.batteries:
        health = "?" if b.health_percent is None else f"{b.health_percent}%"
        lines.append(f"BAT{b.name.removeprefix('acpibat')}: {health} health, {'?' if b.cycles is None else b.cycles} cycles")
    s = state.sensors
    cpu = f"CPU {state.sysctl.get('hw.cpuspeed', '?')} MHz"
    if s.cpu_temp is not None:
        cpu += f", {s.cpu_temp:g} °C"
    if s.fan_rpm is not None:
        cpu += f", fan {s.fan_rpm} RPM"
    lines.append(cpu)
    if state.apm:
        lines.append(f"Performance: {'auto' if state.apm.perf_auto else 'manual'}")
    return lines


class Tray(QSystemTrayIcon):
    def __init__(self, sys: System, elevator: Elevator, cfg: dict | None = None) -> None:
        super().__init__()
        self.sys, self.elevator = sys, elevator
        self.cfg = cfg if cfg is not None else userconfig.load()
        self.state: State | None = None
        self.prefs: Preferences | None = None
        self.warned = False
        self._low_setting: tuple | None = None
        self.info_actions: list[QAction] = []

        self.menu = QMenu()
        self.perf_menu = self.menu.addMenu("Performance")
        self.perf_group = QActionGroup(self.perf_menu)
        for mode, label in PERF_MODES:
            act = self.perf_menu.addAction(label)
            act.setCheckable(True)
            act.setData(mode)
            self.perf_group.addAction(act)
            act.triggered.connect(lambda _=False, m=mode: self._set_perf(m))
        self.sleep_actions = [self.menu.addAction("Suspend"), self.menu.addAction("Hibernate")]
        self.sleep_actions[0].triggered.connect(lambda: self._sleep("zzz"))
        self.sleep_actions[1].triggered.connect(lambda: self._sleep("ZZZ"))
        self.menu.addSeparator()
        self.menu.addAction("Preferences…").triggered.connect(self.open_prefs)
        self.menu.addAction("Quit").triggered.connect(QApplication.quit)
        self.setContextMenu(self.menu)
        self.activated.connect(lambda reason: reason == QSystemTrayIcon.ActivationReason.Trigger and self.open_prefs())

        self.setIcon(draw_icon(None, False, False, self.cfg["show_percent"]))
        self.setToolTip("Power Star")
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh)
        self.settings_changed()
        self.refresh()

    def settings_changed(self) -> None:
        if (self.cfg["notify_low"], self.cfg["low_percent"]) != self._low_setting:
            self.warned = False  # check the new level right away instead of after the next unplug
            self._low_setting = (self.cfg["notify_low"], self.cfg["low_percent"])
        self.timer.start(self.cfg["poll_seconds"] * 1000)
        if self.state:
            self._show(self.state)

    def refresh(self) -> None:
        worker.run_async(lambda: read_state(self.sys), self._got_state)

    def _got_state(self, state) -> None:
        if isinstance(state, BaseException):
            return  # keep the last good display
        self.state = state
        self._show(state)
        if self.prefs is not None and self.prefs.isVisible():
            self.prefs.show_live(state)
        apm = state.apm
        if apm is None or apm.percent is None:
            return
        if apm.ac == 1:
            self.warned = False
        elif self.cfg["notify_low"] and not self.warned and apm.percent <= self.cfg["low_percent"]:
            self.warned = True
            self.showMessage("Battery low", f"{apm.percent}% remaining")

    def _show(self, state: State) -> None:
        apm = state.apm
        has = apm is not None and apm.percent is not None
        self.setIcon(draw_icon(apm.percent if has else None, has and apm.state == 3, bool(apm) and apm.ac == 1, self.cfg["show_percent"]))
        self.setToolTip(status_text(state))
        problem = session.perf_problem(state)
        for act in self.info_actions:
            self.menu.removeAction(act)
            act.deleteLater()
        lines = info_lines(state) + ([problem] if problem else [])
        self.info_actions = [QAction(text, self.menu) for text in lines]
        for act in self.info_actions:
            act.setEnabled(False)
        self.menu.insertActions(self.perf_menu.menuAction(), self.info_actions)
        self.perf_menu.setEnabled(problem is None)
        self.perf_menu.setToolTip(problem or "")
        for act in self.sleep_actions:
            act.setEnabled(problem is None)
            act.setToolTip(problem or "")
        for act in self.perf_group.actions():
            act.setChecked(bool(state.apm and state.apm.perf_auto) and act.data() == "A")

    def _set_perf(self, mode: str) -> None:
        worker.run_async(lambda: session.set_perf(self.sys, mode), lambda r: self._perf_set(mode, r))

    def _perf_set(self, mode: str, result) -> None:
        if isinstance(result, BaseException):
            self._failed(result)
            return
        self.cfg["menu_perf"] = mode
        userconfig.save(self.cfg)
        self.refresh()

    def _failed(self, e: BaseException) -> None:
        self.showMessage("Power Star", f"{e.message}: {e.detail}" if isinstance(e, PowerStarError) else str(e))

    def _sleep(self, cmd: str) -> None:
        worker.run_async(lambda: self.sys.run([cmd]), lambda r: self._failed(r) if isinstance(r, BaseException) else None)

    def open_prefs(self) -> None:
        if self.state is None:
            return
        if self.prefs is None or not (self.prefs.isVisible() or self.prefs.applying):
            self.prefs = Preferences(self.state, self.cfg, self.sys, self.elevator)
            self.prefs.applied.connect(self.refresh)
            self.prefs.settings_changed.connect(self.settings_changed)
            self.prefs.show()
        self.prefs.raise_()
        self.prefs.activateWindow()


def run() -> int:
    app = QApplication(_sys.argv)
    app.setQuitOnLastWindowClosed(False)
    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "Power Star", "No system tray is available on this desktop.")
        return 1
    system = System()
    cfg = userconfig.load()
    session.reapply(system, cfg)
    tray = Tray(system, Elevator(system), cfg)
    tray.show()
    app.aboutToQuit.connect(worker.wait_all)
    return app.exec()
