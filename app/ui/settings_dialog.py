"""
Settings dialog – COM port, hotkeys, global offset, display mode.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QSpinBox, QGroupBox, QFormLayout, QLineEdit, QTabWidget, QWidget,
    QKeySequenceEdit, QMessageBox,
)
from PySide6.QtCore import Signal

from serial_comm.connection import list_serial_ports
from settings.config import AppConfig, DEFAULT_CONFIG


class SettingsDialog(QDialog):
    """Application settings dialog with tabs."""

    # Emitted when the user clicks Apply or OK
    settings_applied = Signal()

    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(500)
        self.config = config
        self._build_ui()
        self._load_values()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        tabs = QTabWidget()

        # ── Serial tab ───────────────────────────────────────────
        serial_tab = QWidget()
        s_layout = QFormLayout(serial_tab)

        port_row = QHBoxLayout()
        self._port_combo = QComboBox()
        self._port_combo.setEditable(True)
        port_row.addWidget(self._port_combo)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh_ports)
        port_row.addWidget(refresh_btn)
        s_layout.addRow("COM Port:", port_row)

        self._baud_combo = QComboBox()
        self._baud_combo.addItems(["9600", "57600", "115200", "230400"])
        s_layout.addRow("Baud Rate:", self._baud_combo)

        tabs.addTab(serial_tab, "Serial")

        # ── Display tab ──────────────────────────────────────────
        display_tab = QWidget()
        d_layout = QFormLayout(display_tab)

        self._mode_combo = QComboBox()
        self._mode_combo.addItem("Lyrics", "lyrics")
        self._mode_combo.addItem("Equalizer", "equalizer")
        d_layout.addRow("Display Mode:", self._mode_combo)

        self._lyric_font_spin = QSpinBox()
        self._lyric_font_spin.setRange(8, 32)
        self._lyric_font_spin.setSuffix(" px")
        d_layout.addRow("Lyric Text Size:", self._lyric_font_spin)

        self._global_offset_spin = QSpinBox()
        self._global_offset_spin.setRange(-30000, 30000)
        self._global_offset_spin.setSingleStep(50)
        self._global_offset_spin.setSuffix(" ms")
        d_layout.addRow("Global Lyric Offset:", self._global_offset_spin)

        tabs.addTab(display_tab, "Display")

        # ── Hotkeys tab ──────────────────────────────────────────
        hotkeys_tab = QWidget()
        h_layout = QFormLayout(hotkeys_tab)
        self._hotkey_edits: dict[str, QLineEdit] = {}

        hotkey_labels = {
            "play_pause": "Play / Pause",
            "next_track": "Next Track",
            "prev_track": "Previous Track",
            "volume_up": "Volume Up",
            "volume_down": "Volume Down",
            "offset_plus_50": "Offset +50 ms",
            "offset_minus_50": "Offset −50 ms",
            "offset_plus_200": "Offset +200 ms",
            "offset_minus_200": "Offset −200 ms",
        }
        for key, label in hotkey_labels.items():
            edit = QLineEdit()
            edit.setPlaceholderText("e.g. Ctrl+Shift+P")
            self._hotkey_edits[key] = edit
            h_layout.addRow(f"{label}:", edit)

        reset_hk_btn = QPushButton("Reset Hotkeys to Defaults")
        reset_hk_btn.clicked.connect(self._reset_hotkeys)
        h_layout.addRow("", reset_hk_btn)

        tabs.addTab(hotkeys_tab, "Hotkeys")

        layout.addWidget(tabs)

        # ── Buttons ──────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(self._apply)
        btn_row.addWidget(apply_btn)
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self._ok)
        btn_row.addWidget(ok_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _load_values(self):
        self._refresh_ports()
        # Set current port
        port = self.config.com_port
        idx = self._port_combo.findText(port)
        if idx >= 0:
            self._port_combo.setCurrentIndex(idx)
        elif port:
            self._port_combo.setCurrentText(port)

        # Baud
        baud_str = str(self.config.baud_rate)
        idx = self._baud_combo.findText(baud_str)
        if idx >= 0:
            self._baud_combo.setCurrentIndex(idx)

        mode_value = self.config.display_mode
        for idx in range(self._mode_combo.count()):
            if self._mode_combo.itemData(idx) == mode_value:
                self._mode_combo.setCurrentIndex(idx)
                break
        self._lyric_font_spin.setValue(self.config.lyric_font_size_px)
        self._global_offset_spin.setValue(self.config.global_offset_ms)

        # Hotkeys
        hk = self.config.hotkeys
        for key, edit in self._hotkey_edits.items():
            edit.setText(hk.get(key, ""))

    def _refresh_ports(self):
        current = self._port_combo.currentText()
        self._port_combo.clear()
        ports = list_serial_ports()
        self._port_combo.addItems(ports)
        if current:
            idx = self._port_combo.findText(current)
            if idx >= 0:
                self._port_combo.setCurrentIndex(idx)
            else:
                self._port_combo.setCurrentText(current)

    def _reset_hotkeys(self):
        defaults = DEFAULT_CONFIG["hotkeys"]
        for key, edit in self._hotkey_edits.items():
            edit.setText(defaults.get(key, ""))

    def _apply(self):
        self.config.com_port = self._port_combo.currentText().strip()
        self.config.set("baud_rate", int(self._baud_combo.currentText()))
        self.config.display_mode = str(self._mode_combo.currentData())
        self.config.lyric_font_size_px = self._lyric_font_spin.value()
        self.config.global_offset_ms = self._global_offset_spin.value()

        hk = {}
        for key, edit in self._hotkey_edits.items():
            hk[key] = edit.text().strip()
        self.config.hotkeys = hk

        self.config.save()
        self.settings_applied.emit()

    def _ok(self):
        self._apply()
        self.accept()
