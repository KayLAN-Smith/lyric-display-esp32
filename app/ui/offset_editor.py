"""
Per-track lyric offset editor dialog.

Shows the current lyric, allows real-time offset adjustment with
buttons and hotkeys, and persists the result on save.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSpinBox,
    QGroupBox,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QShortcut, QKeySequence


class OffsetEditorDialog(QDialog):
    """
    Offset calibration window.

    Signals:
        offset_changed(int) - emitted in real time as the user adjusts.
    """

    offset_changed = Signal(int)

    def __init__(self, track_title: str, current_offset_ms: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Lyric Offset – {track_title}")
        self.setMinimumWidth(400)

        self._offset = current_offset_ms
        self._saved = False
        self._build_ui()
        self._setup_shortcuts()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Info
        layout.addWidget(QLabel(
            "Adjust the lyric offset while the song plays.\n"
            "Positive values delay lyrics, negative values advance them."
        ))

        # Current offset display
        group = QGroupBox("Offset (milliseconds)")
        g_layout = QVBoxLayout(group)

        spin_row = QHBoxLayout()
        self._spin = QSpinBox()
        self._spin.setRange(-30000, 30000)
        self._spin.setSingleStep(50)
        self._spin.setValue(self._offset)
        self._spin.setSuffix(" ms")
        self._spin.valueChanged.connect(self._on_spin_changed)
        spin_row.addWidget(self._spin)

        reset_btn = QPushButton("Reset to 0")
        reset_btn.clicked.connect(self._reset)
        spin_row.addWidget(reset_btn)
        g_layout.addLayout(spin_row)

        # Fine / coarse buttons
        btn_row = QHBoxLayout()
        for delta, label in [
            (-200, "−200"), (-50, "−50"), (50, "+50"), (200, "+200")
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(lambda checked, d=delta: self._adjust(d))
            btn_row.addWidget(btn)
        g_layout.addLayout(btn_row)

        layout.addWidget(group)

        # Current lyric preview
        self._lyric_label = QLabel("")
        self._lyric_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lyric_label.setWordWrap(True)
        self._lyric_label.setStyleSheet("color: #0078d7; font-size: 14px; padding: 8px;")
        layout.addWidget(self._lyric_label)

        # Save / Cancel
        btn_row2 = QHBoxLayout()
        btn_row2.addStretch()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save)
        btn_row2.addWidget(save_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row2.addWidget(cancel_btn)
        layout.addLayout(btn_row2)

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+]"), self, lambda: self._adjust(50))
        QShortcut(QKeySequence("Ctrl+["), self, lambda: self._adjust(-50))
        QShortcut(QKeySequence("Ctrl+Shift+]"), self, lambda: self._adjust(200))
        QShortcut(QKeySequence("Ctrl+Shift+["), self, lambda: self._adjust(-200))

    def _adjust(self, delta: int):
        self._offset += delta
        self._spin.setValue(self._offset)

    def _on_spin_changed(self, value: int):
        self._offset = value
        self.offset_changed.emit(self._offset)

    def _reset(self):
        self._offset = 0
        self._spin.setValue(0)

    def _save(self):
        self._saved = True
        self.accept()

    def set_current_lyric(self, text: str):
        """Update the lyric preview (called from outside while song plays)."""
        self._lyric_label.setText(text)

    @property
    def offset(self) -> int:
        return self._offset

    @property
    def was_saved(self) -> bool:
        return self._saved
