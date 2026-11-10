"""The Preferences window: five tabs; root-backed settings go through Apply."""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGridLayout, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QSlider, QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)
from PyQt6.QtCore import Qt

from powerstar import apmdflags, blockcpu, session, userconfig
from powerstar.changes import SYSCTL_CONF, Wanted, plan_changes
from powerstar.errors import PowerStarError
from powerstar.readings import State, read_state
from powerstar.ui import worker

UNSUPPORTED = "Not supported on this machine"
POLICY_LABELS = [("auto", "Automatic"), ("high", "High performance"), ("manual", "Manual")]
CHARGE_MODES = [(1, "Charge within the limits"), (0, "Do not charge"), (-1, "Force discharge")]
LID_ACTIONS = [(0, "Do nothing"), (1, "Suspend"), (2, "Hibernate")]
POWER_ACTIONS = [(0, "Do nothing"), (1, "Power off"), (2, "Suspend")]
SLEEP_MODES = [(None, "Off"), ("suspend", "Suspend"), ("hibernate", "Hibernate")]
LETTER_LABELS = {"S": "Disable hyper-threading (SMT)", "P": "Do not use performance cores (P)",
                 "E": "Do not use efficiency cores (E)", "L": "Do not use low-power cores (L)"}  # fmt: skip


def combo(items) -> QComboBox:
    c = QComboBox()
    for value, label in items:
        c.addItem(label, value)
    return c


def spin(lo: int, hi: int, suffix: str = "") -> QSpinBox:
    s = QSpinBox()
    s.setRange(lo, hi)
    s.setSuffix(suffix)
    return s


def confirm_box(parent, lines: list[str]) -> bool:
    text = "Power Star will make these changes as root:\n\n" + "\n".join(lines)
    return QMessageBox.question(parent, "Confirm changes", text) == QMessageBox.StandardButton.Yes


def split_policy(policy: str) -> tuple[str, str]:
    parts = policy.split(",")
    return parts[0], parts[-1]


def join_policy(ac: str, battery: str) -> str:
    return ac if ac == battery else f"{ac},{battery}"


class Preferences(QDialog):
    applied = pyqtSignal()  # root change done (state re-read)
    settings_changed = pyqtSignal()  # a user-level setting changed

    def __init__(self, state: State, cfg: dict, sys, elevator, confirm=None) -> None:
        super().__init__()
        self.setWindowTitle("Power Star")
        self.state, self.cfg, self.sys, self.elevator = state, cfg, sys, elevator
        self.confirm = confirm or (lambda lines: confirm_box(self, lines))
        self.base: dict = {}
        self.applying = False
        self.root_problem = elevator.available()
        self.tabs = QTabWidget()
        self.tabs.addTab(self._battery_tab(), "Battery")
        self.tabs.addTab(self._performance_tab(), "Performance")
        self.tabs.addTab(self._display_tab(), "Display")
        self.tabs.addTab(self._sleep_tab(), "Sleep && buttons")  # "&&": a single & marks a shortcut key
        self.tabs.addTab(self._general_tab(), "General")
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.buttons = QDialogButtonBox()
        self.apply_button = self.buttons.addButton("Apply", QDialogButtonBox.ButtonRole.ApplyRole)
        self.close_button = self.buttons.addButton(QDialogButtonBox.StandardButton.Close)
        self.apply_button.clicked.connect(self.apply)
        self.close_button.clicked.connect(self.close)
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        layout.addWidget(self.status)
        layout.addWidget(self.buttons)
        self._populate()
        if self.root_problem:
            self.apply_button.setEnabled(False)
            self.apply_button.setToolTip(self.root_problem)
            self.status.setText(self.root_problem)

    def reject(self) -> None:  # Esc and the window's close button; a running Apply must not be abandoned
        if not self.applying:
            super().reject()

    # ---- building the tabs

    def _row(self, form: QFormLayout, label: str, widget: QWidget, key: str | None) -> None:
        """Add a row; a sysctl key missing from the state disables the widget with a reason."""
        apm = self.state.apm
        no_battery = apm is None or apm.state == 4 or not self.state.sensors.batteries
        reason = None
        if key is not None and key not in self.state.sysctl:
            reason = UNSUPPORTED
        elif key is not None and key.startswith("hw.battery.") and no_battery:
            reason = "No battery"
        if reason:
            widget.setEnabled(False)
            box = QHBoxLayout()
            box.addWidget(widget)
            box.addWidget(QLabel(reason))
            form.addRow(label, box)
        else:
            form.addRow(label, widget)

    def _battery_tab(self) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)
        self.chargemode = combo(CHARGE_MODES)
        self.chargestart, self.chargestop = spin(0, 99, " %"), spin(1, 100, " %")
        self._row(form, "Charge mode", self.chargemode, "hw.battery.chargemode")
        self._row(form, "Start charging below", self.chargestart, "hw.battery.chargestart")
        self._row(form, "Stop charging at", self.chargestop, "hw.battery.chargestop")
        grid = QGridLayout()
        bats = self.state.sensors.batteries
        for col, head in enumerate(["", "Model", "Health", "Last full / design", "Cycles", "Rate", "Voltage", "State"]):
            grid.addWidget(QLabel(f"<b>{head}</b>"), 0, col)
        fmt = lambda v, unit: "?" if v is None else f"{v:g} {unit}"
        for row, b in enumerate(bats, 1):
            cells = [b.name, b.model or "?", "?" if b.health_percent is None else f"{b.health_percent}%",
                     f"{fmt(b.last_full_wh, 'Wh')} / {fmt(b.design_wh, 'Wh')}", fmt(b.cycles, ""),
                     fmt(b.rate_w, "W"), fmt(b.voltage, "V"), b.status or "?"]  # fmt: skip
            for col, text in enumerate(cells):
                grid.addWidget(QLabel(text), row, col)
        if not bats:
            grid.addWidget(QLabel("No battery"), 1, 0)
        form.addRow(grid)
        return tab

    def _performance_tab(self) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)
        self.policy_ac, self.policy_bat = combo(POLICY_LABELS), combo(POLICY_LABELS)
        self.setperf = QSlider(Qt.Orientation.Horizontal)
        self.setperf.setRange(0, 100)
        self._row(form, "Policy on AC", self.policy_ac, "hw.perfpolicy")
        self._row(form, "Policy on battery", self.policy_bat, "hw.perfpolicy")
        self._row(form, "Manual CPU speed", self.setperf, "hw.setperf")
        for c in (self.policy_ac, self.policy_bat):
            c.currentIndexChanged.connect(self._update_setperf)
        self.letters: dict[str, QCheckBox] = {}
        core_types = self.state.cpu_types - {"S"}
        for letter in blockcpu.ORDER:
            # blocking the only core type would leave one CPU, so offer core types only when there are two or more
            if letter in self.state.cpu_types and (letter == "S" or len(core_types) > 1):
                self.letters[letter] = QCheckBox(LETTER_LABELS[letter])
                self.letters[letter].toggled.connect(self._update_block_problem)
                self._row(form, "", self.letters[letter], "hw.blockcpu")
        self.block_problem = QLabel("")
        form.addRow(self.block_problem)
        sensors = self.state.sensors
        live = [f"CPU {self.state.sysctl.get('hw.cpuspeed', '?')} MHz"]
        live.append("temperature ?" if sensors.cpu_temp is None else f"{sensors.cpu_temp:g} °C")
        live.append("fan ?" if sensors.fan_rpm is None else f"fan {sensors.fan_rpm} RPM")
        form.addRow(QLabel(", ".join(live)))
        return tab

    def _display_tab(self) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)
        self.brightness = QSlider(Qt.Orientation.Horizontal)
        self.brightness.setRange(1, 100)
        self.brightness.setTracking(False)  # one xbacklight call per release, not per pixel
        self.brightness.setEnabled(False)  # until xbacklight has answered
        self.brightness_note = QLabel("Reading…")
        form.addRow("Brightness", self._with_note(self.brightness, self.brightness_note))
        self.brightness.valueChanged.connect(lambda v: self._user_setting("brightness", v, session.set_brightness))
        worker.run_async(lambda: session.get_brightness(self.sys), self._got_brightness)
        self.screen_off = spin(0, 240, " min")
        self.screen_off.setSpecialValueText("Never")
        self.screen_off.setKeyboardTracking(False)
        self.screen_off.setValue(self.cfg.get("screen_off_minutes") or 0)
        self.screen_off.valueChanged.connect(lambda v: self._user_setting("screen_off_minutes", v, session.set_screen_off))
        form.addRow("Turn screen off after", self.screen_off)
        return tab

    def _got_brightness(self, level) -> None:
        if not isinstance(level, int):
            self.brightness_note.setText(UNSUPPORTED)
            return
        self.brightness.blockSignals(True)  # showing the current level is not a change
        self.brightness.setValue(level)
        self.brightness.blockSignals(False)
        self.brightness.setEnabled(True)
        self.brightness_note.setText("")

    def _with_note(self, widget: QWidget, note: QLabel) -> QHBoxLayout:
        box = QHBoxLayout()
        box.addWidget(widget)
        box.addWidget(note)
        return box

    def _sleep_tab(self) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)
        self.lid = combo(LID_ACTIONS)
        self.power_button = combo(POWER_ACTIONS)
        self.auto_mode = combo(SLEEP_MODES)
        self.auto_percent = spin(1, 50, " %")
        self._row(form, "Lid closed", self.lid, "machdep.lidaction")
        self._row(form, "Power button", self.power_button, "machdep.pwraction")
        self.reboot_note = QLabel("Power off takes effect after reboot")
        form.addRow(self.reboot_note)
        self.power_button.currentIndexChanged.connect(self._update_reboot_note)
        form.addRow("Sleep automatically", self.auto_mode)
        form.addRow("when battery is below", self.auto_percent)
        if not self.state.apmd_enabled:
            form.addRow(QLabel("apmd is not enabled; Apply will enable it"))
        return tab

    def _general_tab(self) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)
        self.show_percent = QCheckBox("Show the percentage on the icon")
        self.notify_low = QCheckBox("Notify when the battery is low")
        self.low_percent = spin(1, 50, " %")
        self.poll_seconds = spin(2, 60, " s")
        self.show_percent.setChecked(self.cfg["show_percent"])
        self.notify_low.setChecked(self.cfg["notify_low"])
        self.low_percent.setValue(self.cfg["low_percent"])
        self.poll_seconds.setValue(self.cfg["poll_seconds"])
        self.show_percent.toggled.connect(lambda v: self._save("show_percent", v))
        self.notify_low.toggled.connect(lambda v: self._save("notify_low", v))
        self.low_percent.valueChanged.connect(lambda v: self._save("low_percent", v))
        self.poll_seconds.valueChanged.connect(lambda v: self._save("poll_seconds", v))
        form.addRow(self.show_percent)
        form.addRow(self.notify_low)
        form.addRow("Low battery level", self.low_percent)
        form.addRow("Check every", self.poll_seconds)
        return tab

    # ---- user-level settings (no root, applied at once)

    def _save(self, key: str, value) -> None:
        self.cfg[key] = value
        userconfig.save(self.cfg)
        self.status.setText("Saved")
        self.settings_changed.emit()

    def _user_setting(self, key: str, value: int, action) -> None:
        worker.run_async(lambda: action(self.sys, value), lambda r: self._user_done(key, value, r))

    def _user_done(self, key: str, value: int, result) -> None:
        if isinstance(result, PowerStarError):
            self.status.setText(f"{result.message}: {result.detail}")
        elif isinstance(result, BaseException):
            self.status.setText(str(result))
        else:
            self._save(key, value)

    # ---- root-backed settings

    def _populate(self) -> None:
        live = self.state.sysctl
        geti = lambda k, d: int(live[k]) if live.get(k, "").lstrip("-").isdigit() else d
        set_combo = lambda c, v: c.setCurrentIndex(max(0, c.findData(v)))
        set_combo(self.chargemode, geti("hw.battery.chargemode", 1))
        self.chargestart.setValue(geti("hw.battery.chargestart", 0))
        self.chargestop.setValue(geti("hw.battery.chargestop", 100))
        ac, bat = split_policy(live.get("hw.perfpolicy", "auto"))
        set_combo(self.policy_ac, ac)
        set_combo(self.policy_bat, bat)
        self.setperf.setValue(geti("hw.setperf", 0))
        blocked = blockcpu.blocked(live.get("hw.blockcpu", ""))
        for letter, box in self.letters.items():
            box.setChecked(letter in blocked)
        set_combo(self.lid, geti("machdep.lidaction", 0))
        set_combo(self.power_button, geti("machdep.pwraction", 0))
        mode, pct = apmdflags.auto_sleep(self.state.apmd_flags)
        set_combo(self.auto_mode, mode)
        self.auto_percent.setValue(pct or 10)
        self._update_setperf()
        self._update_block_problem()
        self._update_reboot_note()
        self.base = self._values()

    def _update_setperf(self) -> None:
        manual = "manual" in (self.policy_ac.currentData(), self.policy_bat.currentData())
        self.setperf.setEnabled(manual and "hw.setperf" in self.state.sysctl)

    def _update_block_problem(self) -> None:
        self.block_problem.setText(blockcpu.problem(self._blocked(), self.state.cpu_types) or "")

    def _update_reboot_note(self) -> None:
        self.reboot_note.setVisible(
            self.power_button.currentData() == 1 and self.state.sysctl.get("hw.allowpowerdown") != "1"
        )

    def _blocked(self) -> set[str]:
        return {letter for letter, box in self.letters.items() if box.isChecked()}

    def _values(self) -> dict:
        return {
            "chargemode": self.chargemode.currentData(),
            "chargestart": self.chargestart.value(),
            "chargestop": self.chargestop.value(),
            "perfpolicy": join_policy(self.policy_ac.currentData(), self.policy_bat.currentData()),
            "setperf": self.setperf.value(),
            "blocked": self._blocked(),
            "lidaction": self.lid.currentData(),
            "pwraction": self.power_button.currentData(),
            "auto_sleep": (self.auto_mode.currentData(), self.auto_percent.value() if self.auto_mode.currentData() else None),
        }  # fmt: skip

    def wanted(self) -> Wanted:
        """Only the controls the user changed."""
        now = self._values()
        return Wanted(**{k: v for k, v in now.items() if v != self.base[k]})

    def _busy(self, busy: bool, text: str = "") -> None:
        self.applying = busy
        self.apply_button.setEnabled(not busy and self.root_problem is None)
        self.close_button.setEnabled(not busy)
        self.status.setText(text)

    def apply(self) -> None:
        wanted = self.wanted()
        try:
            mode = self.sys.file_mode(SYSCTL_CONF)
            text = self.sys.read_file(SYSCTL_CONF)
            if text is None:
                if mode is not None:  # present but unreadable: writing our lines alone would drop the rest
                    raise PowerStarError(f"Cannot read {SYSCTL_CONF}", detail="It is not readable by this user.")
                text = ""
            change = plan_changes(self.state, wanted, text, 0o644 if mode is None else mode)
        except PowerStarError as e:
            self.status.setText(f"{e.message}. {e.detail}".strip())
            return
        if change.empty:
            self.status.setText("No system settings changed (Display and General settings are saved as you change them)")
            return
        if not self.confirm(change.describe()):
            return
        self._busy(True, "Waiting for authorisation…")
        worker.run_async(lambda: self.elevator.run(change), lambda r: self._finished(r, wanted))

    def _finished(self, outcome, wanted: Wanted) -> None:
        if isinstance(outcome, BaseException):
            self._busy(False, f"Failed: {outcome}")
        elif outcome.cancelled:
            self._busy(False, "Cancelled")
        elif not outcome.ok:
            self._busy(False, f"Failed:\n{outcome.output}")
        else:
            self._busy(False, "Applied")
            if wanted.perfpolicy is not None and self.cfg.get("menu_perf") is not None:
                self.cfg["menu_perf"] = None
                userconfig.save(self.cfg)
            worker.run_async(lambda: read_state(self.sys), self._reread)

    def _reread(self, state) -> None:
        if isinstance(state, BaseException):
            return
        self.state = state
        self._populate()
        self.applied.emit()
