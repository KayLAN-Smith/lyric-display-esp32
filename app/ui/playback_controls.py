"""
Playback control bar – play/pause/stop/next/prev, seek bar, time display,
shuffle/repeat toggles, volume slider, and current lyric display.
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QSlider, QLabel,
    QSizePolicy, QStyle,
)
from PySide6.QtCore import Signal, Qt


class PlaybackControls(QWidget):
    """
    Bottom playback bar.

    Signals:
        play_pause_clicked()
        stop_clicked()
        next_clicked()
        prev_clicked()
        seek_requested(int)   - seek to position in ms
        volume_changed(float) - 0.0 to 1.0
        shuffle_toggled(bool)
        repeat_changed(str)   - "off", "playlist", "one"
    """

    play_pause_clicked = Signal()
    stop_clicked = Signal()
    next_clicked = Signal()
    prev_clicked = Signal()
    seek_requested = Signal(int)
    volume_changed = Signal(float)
    shuffle_toggled = Signal(bool)
    repeat_changed = Signal(str)

    REPEAT_MODES = ["off", "playlist", "one"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._duration_ms = 0
        self._seeking = False
        self._shuffle = False
        self._repeat_idx = 0  # index into REPEAT_MODES
        self._lyric_font_size_px = 13

        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 4, 8, 4)

        # ── Now playing label ────────────────────────────────────
        self._now_playing = QLabel("No track loaded")
        self._now_playing.setStyleSheet("font-weight: bold;")
        self._now_playing.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self._now_playing)

        # ── Seek bar row ─────────────────────────────────────────
        seek_row = QHBoxLayout()
        self._time_label = QLabel("0:00")
        self._time_label.setFixedWidth(48)
        self._time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        seek_row.addWidget(self._time_label)

        self._seek_slider = QSlider(Qt.Orientation.Horizontal)
        self._seek_slider.setRange(0, 0)
        self._seek_slider.sliderPressed.connect(self._on_seek_pressed)
        self._seek_slider.sliderReleased.connect(self._on_seek_released)
        seek_row.addWidget(self._seek_slider)

        self._duration_label = QLabel("0:00")
        self._duration_label.setFixedWidth(48)
        seek_row.addWidget(self._duration_label)
        outer.addLayout(seek_row)

        # ── Buttons row ──────────────────────────────────────────
        btn_row = QHBoxLayout()

        self._shuffle_btn = QPushButton("Shuffle: Off")
        self._shuffle_btn.setCheckable(True)
        self._shuffle_btn.setFixedWidth(90)
        self._shuffle_btn.clicked.connect(self._toggle_shuffle)
        btn_row.addWidget(self._shuffle_btn)

        btn_row.addStretch()

        self._prev_btn = QPushButton()
        self._prev_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaSkipBackward))
        self._prev_btn.setFixedSize(36, 36)
        self._prev_btn.clicked.connect(self.prev_clicked)
        btn_row.addWidget(self._prev_btn)

        self._play_btn = QPushButton()
        self._play_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self._play_btn.setFixedSize(44, 44)
        self._play_btn.clicked.connect(self.play_pause_clicked)
        btn_row.addWidget(self._play_btn)

        self._stop_btn = QPushButton()
        self._stop_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaStop))
        self._stop_btn.setFixedSize(36, 36)
        self._stop_btn.clicked.connect(self.stop_clicked)
        btn_row.addWidget(self._stop_btn)

        self._next_btn = QPushButton()
        self._next_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaSkipForward))
        self._next_btn.setFixedSize(36, 36)
        self._next_btn.clicked.connect(self.next_clicked)
        btn_row.addWidget(self._next_btn)

        btn_row.addStretch()

        self._repeat_btn = QPushButton("Repeat: Off")
        self._repeat_btn.setFixedWidth(100)
        self._repeat_btn.clicked.connect(self._cycle_repeat)
        btn_row.addWidget(self._repeat_btn)

        # Volume
        vol_label = QLabel("Vol:")
        btn_row.addWidget(vol_label)
        self._vol_slider = QSlider(Qt.Orientation.Horizontal)
        self._vol_slider.setRange(0, 100)
        self._vol_slider.setValue(70)
        self._vol_slider.setFixedWidth(100)
        self._vol_slider.valueChanged.connect(
            lambda v: self.volume_changed.emit(v / 100.0)
        )
        btn_row.addWidget(self._vol_slider)

        outer.addLayout(btn_row)

        # ── Current lyric display ────────────────────────────────
        self._lyric_label = QLabel("")
        self._lyric_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._apply_lyric_style()
        self._lyric_label.setWordWrap(True)
        self._lyric_label.setMaximumHeight(40)
        outer.addWidget(self._lyric_label)

    # ── Public setters ───────────────────────────────────────────

    def set_now_playing(self, title: str, artist: str = ""):
        text = title
        if artist:
            text += f" – {artist}"
        self._now_playing.setText(text)

    def set_duration(self, ms: int):
        self._duration_ms = ms
        self._seek_slider.setRange(0, ms)
        self._duration_label.setText(_fmt(ms))

    def set_position(self, ms: int):
        if not self._seeking:
            self._seek_slider.setValue(ms)
        self._time_label.setText(_fmt(ms))

    def set_playing(self, playing: bool):
        if playing:
            self._play_btn.setIcon(
                self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause)
            )
        else:
            self._play_btn.setIcon(
                self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
            )

    def set_lyric(self, text: str):
        self._lyric_label.setText(text)

    def set_lyric_font_size(self, size_px: int):
        self._lyric_font_size_px = size_px
        self._apply_lyric_style()

    def set_volume_slider(self, volume: float):
        self._vol_slider.setValue(int(volume * 100))

    def clear(self):
        self._now_playing.setText("No track loaded")
        self._time_label.setText("0:00")
        self._duration_label.setText("0:00")
        self._seek_slider.setRange(0, 0)
        self._lyric_label.setText("")

    @property
    def shuffle(self) -> bool:
        return self._shuffle

    @property
    def repeat_mode(self) -> str:
        return self.REPEAT_MODES[self._repeat_idx]

    # ── Internal ─────────────────────────────────────────────────

    def _on_seek_pressed(self):
        self._seeking = True

    def _on_seek_released(self):
        self._seeking = False
        self.seek_requested.emit(self._seek_slider.value())

    def _toggle_shuffle(self):
        self._shuffle = self._shuffle_btn.isChecked()
        self._shuffle_btn.setText(f"Shuffle: {'On' if self._shuffle else 'Off'}")
        self.shuffle_toggled.emit(self._shuffle)

    def _cycle_repeat(self):
        self._repeat_idx = (self._repeat_idx + 1) % len(self.REPEAT_MODES)
        mode = self.REPEAT_MODES[self._repeat_idx]
        labels = {"off": "Repeat: Off", "playlist": "Repeat: All", "one": "Repeat: One"}
        self._repeat_btn.setText(labels[mode])
        self.repeat_changed.emit(mode)

    def _apply_lyric_style(self):
        self._lyric_label.setStyleSheet(
            f"color: #0078d7; font-size: {self._lyric_font_size_px}px;"
        )


def _fmt(ms: int) -> str:
    """Format milliseconds as m:ss."""
    if ms < 0:
        ms = 0
    s = ms // 1000
    m, s = divmod(s, 60)
    return f"{m}:{s:02d}"
