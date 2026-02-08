"""
Main application window – ties together all UI components and orchestrates
playback, serial communication, and lyric synchronization.
"""

import os
import math
import random

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QLabel, QPushButton, QComboBox, QStatusBar, QMenuBar, QMessageBox,
    QFrame,
)
from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QAction, QShortcut, QKeySequence

from db.database import Database
from audio.player import AudioPlayer
from audio.spectrum import SpectrumAnalyzer
from srt.parser import parse_srt_file, get_lyric_at_position
from serial_comm.connection import SerialConnection, list_serial_ports
from settings.config import AppConfig

from ui.library_tab import LibraryTab
from ui.playlists_tab import PlaylistsTab
from ui.playback_controls import PlaybackControls
from ui.import_dialog import ImportDialog
from ui.offset_editor import OffsetEditorDialog
from ui.settings_dialog import SettingsDialog
from ui.oled_simulator import OledSimulator


class MainWindow(QMainWindow):
    def __init__(self, db: Database, config: AppConfig):
        super().__init__()
        self.db = db
        self.config = config

        self.setWindowTitle("Lyric Display")
        self.setMinimumSize(800, 600)
        self.resize(960, 680)

        # Core objects
        self.player = AudioPlayer(self)
        self.serial = SerialConnection(self)
        self._spectrum = SpectrumAnalyzer()

        # Playback state
        self._current_track: dict | None = None
        self._lyrics: list = []
        self._last_lyric_idx: int = -1
        self._track_offset_ms: int = 0
        self._playlist_queue: list[dict] = []
        self._playlist_pos: int = -1
        self._current_playlist_id: int | None = None
        self._shuffle_on: bool = False
        self._repeat_mode: str = "off"
        self._in_lyric_gap: bool = False  # auto-EQ during lyric gaps
        self._eq_timer = QTimer(self)
        self._eq_timer.setInterval(80)
        self._eq_timer.timeout.connect(self._send_equalizer_levels)
        self._eq_timer.start()

        # Offset editor reference (for live updates)
        self._offset_dialog: OffsetEditorDialog | None = None

        # OLED simulator window
        self._oled_sim = OledSimulator()
        self._oled_sim.setWindowFlags(
            Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint
        )

        self._build_ui()
        self._connect_signals()
        self._setup_hotkeys()
        self._apply_config()

        # Auto-connect serial if port is configured
        if self.config.com_port:
            QTimer.singleShot(500, self._auto_connect_serial)

    # ═════════════════════════════════════════════════════════════
    #  UI CONSTRUCTION
    # ═════════════════════════════════════════════════════════════

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(4, 4, 4, 4)

        # ── Menu bar ─────────────────────────────────────────────
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("File")
        file_menu.addAction("Import Song...", self._import_song)
        file_menu.addSeparator()
        file_menu.addAction("Settings...", self._open_settings)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)

        view_menu = menu_bar.addMenu("View")
        self._sim_action = QAction("OLED Simulator", self)
        self._sim_action.setCheckable(True)
        self._sim_action.setChecked(False)
        self._sim_action.toggled.connect(self._toggle_oled_sim)
        view_menu.addAction(self._sim_action)

        # ── Serial connection bar ────────────────────────────────
        serial_bar = QHBoxLayout()
        serial_bar.addWidget(QLabel("Serial:"))
        self._port_combo = QComboBox()
        self._port_combo.setEditable(True)
        self._port_combo.setMinimumWidth(120)
        serial_bar.addWidget(self._port_combo)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFixedWidth(60)
        refresh_btn.clicked.connect(self._refresh_ports)
        serial_bar.addWidget(refresh_btn)
        self._connect_btn = QPushButton("Connect")
        self._connect_btn.setFixedWidth(80)
        self._connect_btn.clicked.connect(self._toggle_serial)
        serial_bar.addWidget(self._connect_btn)
        self._serial_status = QLabel("Disconnected")
        self._serial_status.setStyleSheet("color: red; font-weight: bold;")
        serial_bar.addWidget(self._serial_status)
        serial_bar.addStretch()
        main_layout.addLayout(serial_bar)

        # ── Separator ────────────────────────────────────────────
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        main_layout.addWidget(line)

        # ── Tabs ─────────────────────────────────────────────────
        self._tabs = QTabWidget()

        self._library_tab = LibraryTab(self.db)
        self._tabs.addTab(self._library_tab, "All Songs")

        self._playlists_tab = PlaylistsTab(self.db)
        self._tabs.addTab(self._playlists_tab, "Playlists")

        main_layout.addWidget(self._tabs, 1)

        # ── Separator ────────────────────────────────────────────
        line2 = QFrame()
        line2.setFrameShape(QFrame.Shape.HLine)
        main_layout.addWidget(line2)

        # ── Playback controls ────────────────────────────────────
        self._controls = PlaybackControls()
        main_layout.addWidget(self._controls)

        # Populate serial ports
        self._refresh_ports()

    # ═════════════════════════════════════════════════════════════
    #  SIGNAL WIRING
    # ═════════════════════════════════════════════════════════════

    def _connect_signals(self):
        # Library
        self._library_tab.import_button.clicked.connect(self._import_song)
        self._library_tab.play_track.connect(self._play_track_by_id)
        self._library_tab.edit_offset.connect(self._open_offset_editor)
        self._library_tab.add_to_playlist.connect(
            self._playlists_tab.add_tracks_to_current_or_choose
        )

        # Playlists
        self._playlists_tab.play_track_in_playlist.connect(self._play_track_in_playlist)
        self._playlists_tab.play_playlist.connect(self._play_playlist)

        # Playback controls
        self._controls.play_pause_clicked.connect(self._toggle_play)
        self._controls.stop_clicked.connect(self._stop)
        self._controls.next_clicked.connect(self._next_track)
        self._controls.prev_clicked.connect(self._prev_track)
        self._controls.seek_requested.connect(self._seek)
        self._controls.volume_changed.connect(self._set_volume)
        self._controls.shuffle_toggled.connect(self._on_shuffle)
        self._controls.repeat_changed.connect(self._on_repeat)

        # Audio player
        self.player.position_changed.connect(self._on_position)
        self.player.duration_changed.connect(self._on_duration)
        self.player.state_changed.connect(self._on_state)
        self.player.media_ended.connect(self._on_media_ended)
        self.player.error_occurred.connect(
            lambda msg: QMessageBox.warning(self, "Playback Error", msg)
        )

        # Serial
        self.serial.connected.connect(self._on_serial_connected)
        self.serial.disconnected.connect(self._on_serial_disconnected)
        self.serial.button_press.connect(self._toggle_play)
        self.serial.button_long.connect(self._next_track)
        self.serial.error.connect(
            lambda msg: self._serial_status.setText(f"Error: {msg}")
        )

    # ═════════════════════════════════════════════════════════════
    #  HOTKEYS
    # ═════════════════════════════════════════════════════════════

    def _setup_hotkeys(self):
        self._shortcuts: list[QShortcut] = []
        self._apply_hotkeys()

    def _apply_hotkeys(self):
        # Clear old shortcuts
        for sc in self._shortcuts:
            sc.setEnabled(False)
            sc.deleteLater()
        self._shortcuts.clear()

        hk = self.config.hotkeys
        bindings = {
            "play_pause": self._toggle_play,
            "next_track": self._next_track,
            "prev_track": self._prev_track,
            "volume_up": lambda: self._adjust_volume(0.05),
            "volume_down": lambda: self._adjust_volume(-0.05),
            "offset_plus_50": lambda: self._adjust_offset(50),
            "offset_minus_50": lambda: self._adjust_offset(-50),
            "offset_plus_200": lambda: self._adjust_offset(200),
            "offset_minus_200": lambda: self._adjust_offset(-200),
        }

        for key, func in bindings.items():
            seq = hk.get(key, "")
            if seq:
                sc = QShortcut(QKeySequence(seq), self)
                sc.activated.connect(func)
                self._shortcuts.append(sc)

    def _toggle_oled_sim(self, checked: bool):
        if checked:
            self._oled_sim.show()
            self._oled_sim.set_font_size(self.config.esp32_font_size)
            self._oled_sim.set_mode(self.config.display_mode)
            self._push_full_state_to_sim()
        else:
            self._oled_sim.hide()

    def _push_full_state_to_sim(self):
        """Push current playback state to the OLED simulator."""
        if self.player.is_playing:
            self._oled_sim.set_state("playing")
        elif self.player.is_paused:
            self._oled_sim.set_state("paused")
        else:
            self._oled_sim.set_state("stopped")
        if self._current_track:
            self._oled_sim.set_meta(self._build_meta_text(self._current_track))
        if self._current_track and not self.player.is_stopped:
            idx, text = get_lyric_at_position(
                self._lyrics, self.player.position,
                self._track_offset_ms + self.config.global_offset_ms,
            )
            if text:
                self._oled_sim.set_text(text)

    def _apply_config(self):
        self.player.set_volume(self.config.volume)
        self._controls.set_volume_slider(self.config.volume)
        self._controls.set_lyric_font_size(self.config.lyric_font_size_px)
        # Update ESP32
        if self.serial.is_connected:
            self.serial.send_font_size(self.config.esp32_font_size)
            self.serial.send_mode(self.config.display_mode)
        # Update simulator
        self._oled_sim.set_font_size(self.config.esp32_font_size)
        self._oled_sim.set_mode(self.config.display_mode)

    # ═════════════════════════════════════════════════════════════
    #  SERIAL
    # ═════════════════════════════════════════════════════════════

    def _refresh_ports(self):
        current = self._port_combo.currentText()
        self._port_combo.clear()
        self._port_combo.addItems(list_serial_ports())
        if current:
            idx = self._port_combo.findText(current)
            if idx >= 0:
                self._port_combo.setCurrentIndex(idx)
            else:
                self._port_combo.setCurrentText(current)

    def _toggle_serial(self):
        if self.serial.is_connected:
            self.serial.close_port()
        else:
            port = self._port_combo.currentText().strip()
            if not port:
                QMessageBox.warning(self, "No Port", "Select a COM port first.")
                return
            self.config.com_port = port
            self.serial.open_port(port, self.config.baud_rate)

    def _auto_connect_serial(self):
        port = self.config.com_port
        if port:
            self._port_combo.setCurrentText(port)
            self.serial.open_port(port, self.config.baud_rate)

    @Slot()
    def _on_serial_connected(self):
        self._serial_status.setText("Connected")
        self._serial_status.setStyleSheet("color: green; font-weight: bold;")
        self._connect_btn.setText("Disconnect")
        self.serial.send_font_size(self.config.esp32_font_size)
        self.serial.send_mode(self.config.display_mode)
        # Send current state to ESP32
        self._send_full_state_to_esp32()

    @Slot()
    def _on_serial_disconnected(self):
        self._serial_status.setText("Disconnected")
        self._serial_status.setStyleSheet("color: red; font-weight: bold;")
        self._connect_btn.setText("Connect")

    def _send_full_state_to_esp32(self):
        """Push current playback state, meta, and lyric to ESP32."""
        if not self.serial.is_connected:
            return
        # Send play state
        if self.player.is_playing:
            self.serial.send_state("playing")
        elif self.player.is_paused:
            self.serial.send_state("paused")
        else:
            self.serial.send_state("stopped")
        # Send meta (artist – title)
        if self._current_track:
            self.serial.send_meta(self._build_meta_text(self._current_track))
        # Send current lyric
        if self._current_track and not self.player.is_stopped:
            idx, text = get_lyric_at_position(
                self._lyrics, self.player.position,
                self._track_offset_ms + self.config.global_offset_ms,
            )
            if text:
                self.serial.send_text(text)

    # ═════════════════════════════════════════════════════════════
    #  IMPORT
    # ═════════════════════════════════════════════════════════════

    def _import_song(self):
        dlg = ImportDialog(self.db, self)
        if dlg.exec() == ImportDialog.DialogCode.Accepted:
            track_id = self.db.add_track(
                title=dlg.track_title,
                artist=dlg.track_artist,
                duration_ms=0,
                audio_path=dlg.stored_audio_path,
                srt_path=dlg.stored_srt_path,
            )
            if dlg.stored_offset_ms != 0:
                self.db.set_track_offset(track_id, dlg.stored_offset_ms)
            self._library_tab.refresh()

    # ═════════════════════════════════════════════════════════════
    #  PLAYBACK
    # ═════════════════════════════════════════════════════════════

    def _play_track_by_id(self, track_id: int):
        """Play a single track (not from a playlist context)."""
        track = self.db.get_track(track_id)
        if not track:
            return
        self._playlist_queue = []
        self._playlist_pos = -1
        self._current_playlist_id = None
        self._load_and_play(track)

    def _play_track_in_playlist(self, playlist_id: int, track_id: int):
        """Play a specific track within a playlist, building the queue."""
        tracks = self.db.get_playlist_tracks(playlist_id)
        if not tracks:
            return
        self._current_playlist_id = playlist_id
        self._playlist_queue = list(tracks)
        if self._shuffle_on:
            random.shuffle(self._playlist_queue)
        # Find position of the requested track
        self._playlist_pos = 0
        for i, t in enumerate(self._playlist_queue):
            if t["id"] == track_id:
                self._playlist_pos = i
                break
        self._load_and_play(self._playlist_queue[self._playlist_pos])

    def _play_playlist(self, playlist_id: int):
        """Play an entire playlist from the beginning."""
        tracks = self.db.get_playlist_tracks(playlist_id)
        if not tracks:
            return
        self._current_playlist_id = playlist_id
        self._playlist_queue = list(tracks)
        if self._shuffle_on:
            random.shuffle(self._playlist_queue)
        self._playlist_pos = 0
        self._load_and_play(self._playlist_queue[0])

    @staticmethod
    def _build_meta_text(track: dict) -> str:
        """Build 'Artist – Title' string for the ESP32 status bar."""
        artist = track.get("artist", "").strip()
        title = track.get("title", "").strip()
        if artist:
            return f"{artist} \u2013 {title}"
        return title

    def _load_and_play(self, track: dict):
        """Load a track dict and start playback."""
        self._current_track = track
        self._track_offset_ms = track.get("lyric_offset_ms", 0)
        self._last_lyric_idx = -1
        self._in_lyric_gap = False

        # Load lyrics
        srt_path = track.get("srt_path", "")
        if srt_path and os.path.isfile(srt_path):
            self._lyrics = parse_srt_file(srt_path)
        else:
            self._lyrics = []

        # Load audio
        audio_path = track.get("audio_path", "")
        if not audio_path or not os.path.isfile(audio_path):
            QMessageBox.warning(self, "File Not Found", f"Audio file missing:\n{audio_path}")
            return

        self.player.load_and_play(audio_path)
        # Delay spectrum decode so QMediaPlayer can open the file first;
        # avoids Windows exclusive file-lock conflicts.
        QTimer.singleShot(500, lambda p=audio_path: self._spectrum.load_file(p))

        self._controls.set_now_playing(track["title"], track.get("artist", ""))

        # Send to ESP32: clear old lyric, restore mode, and set meta
        meta = self._build_meta_text(track)
        if self.serial.is_connected:
            self.serial.send_clear()
            self.serial.send_mode(self.config.display_mode)
            self.serial.send_meta(meta)
        # Mirror to simulator
        self._oled_sim.clear()
        self._oled_sim.set_mode(self.config.display_mode)
        self._oled_sim.set_meta(meta)

    def _toggle_play(self):
        if self._current_track is None:
            return
        self.player.toggle_play_pause()

    def _stop(self):
        self.player.stop()
        self._controls.clear()
        self._controls.set_lyric("")
        self._in_lyric_gap = False
        if self.serial.is_connected:
            self.serial.send_clear()
            self.serial.send_state("stopped")
            if self.config.display_mode == "lyrics":
                self.serial.send_mode("lyrics")
        self._oled_sim.clear()
        self._oled_sim.set_state("stopped")
        self._oled_sim.set_mode(self.config.display_mode)
        self._current_track = None
        self._last_lyric_idx = -1

    def _next_track(self):
        if not self._playlist_queue:
            return
        if self._playlist_pos < len(self._playlist_queue) - 1:
            self._playlist_pos += 1
            self._load_and_play(self._playlist_queue[self._playlist_pos])
        elif self._repeat_mode == "playlist":
            if self._shuffle_on:
                random.shuffle(self._playlist_queue)
            self._playlist_pos = 0
            self._load_and_play(self._playlist_queue[0])

    def _prev_track(self):
        # If > 3 seconds into the track, restart it; otherwise go to previous
        if self.player.position > 3000:
            self.player.seek(0)
            return
        if not self._playlist_queue:
            return
        if self._playlist_pos > 0:
            self._playlist_pos -= 1
            self._load_and_play(self._playlist_queue[self._playlist_pos])
        elif self._repeat_mode == "playlist":
            self._playlist_pos = len(self._playlist_queue) - 1
            self._load_and_play(self._playlist_queue[self._playlist_pos])

    def _seek(self, ms: int):
        self.player.seek(ms)

    def _set_volume(self, vol: float):
        self.player.set_volume(vol)
        self.config.volume = vol

    def _adjust_volume(self, delta: float):
        new_vol = max(0.0, min(1.0, self.player.get_volume() + delta))
        self.player.set_volume(new_vol)
        self._controls.set_volume_slider(new_vol)
        self.config.volume = new_vol

    def _on_shuffle(self, on: bool):
        self._shuffle_on = on

    def _on_repeat(self, mode: str):
        self._repeat_mode = mode

    # ═════════════════════════════════════════════════════════════
    #  POSITION / LYRIC SYNC
    # ═════════════════════════════════════════════════════════════

    @Slot(int)
    def _on_position(self, ms: int):
        self._controls.set_position(ms)
        self._sync_lyrics(ms)

    @Slot(int)
    def _on_duration(self, ms: int):
        self._controls.set_duration(ms)
        # Update duration in DB if not set
        if self._current_track and self._current_track.get("duration_ms", 0) == 0 and ms > 0:
            self.db.update_track(self._current_track["id"], duration_ms=ms)
            self._current_track["duration_ms"] = ms
            self._library_tab.refresh()

    @Slot(str)
    def _on_state(self, state: str):
        self._controls.set_playing(state == "playing")
        # Forward play state to ESP32 and simulator
        if self.serial.is_connected:
            self.serial.send_state(state)
        self._oled_sim.set_state(state)
        if state == "playing":
            self._send_equalizer_levels()

    @Slot()
    def _on_media_ended(self):
        if self._repeat_mode == "one":
            self.player.seek(0)
            self.player.play()
        elif self._playlist_queue:
            self._next_track()
        else:
            self._controls.set_playing(False)

    def _sync_lyrics(self, position_ms: int):
        if not self._lyrics:
            return

        total_offset = self._track_offset_ms + self.config.global_offset_ms
        idx, text = get_lyric_at_position(self._lyrics, position_ms, total_offset)

        # Update PC lyric display
        self._controls.set_lyric(text)

        # Update offset editor if open
        if self._offset_dialog and self._offset_dialog.isVisible():
            self._offset_dialog.set_current_lyric(text)

        # Auto-switch to equalizer during lyric gaps > 300ms
        if self.config.display_mode == "lyrics":
            if not text and not self._in_lyric_gap:
                # Check if the gap until the next lyric is > 300ms
                gap_ms = self._gap_until_next_lyric(position_ms, total_offset)
                if gap_ms < 0 or gap_ms > 300:
                    self._in_lyric_gap = True
                    if self.serial.is_connected:
                        self.serial.send_mode("equalizer")
                    self._oled_sim.set_mode("equalizer")
            elif text and self._in_lyric_gap:
                self._in_lyric_gap = False
                if self.serial.is_connected:
                    self.serial.send_mode("lyrics")
                self._oled_sim.set_mode("lyrics")

        # Send to ESP32 and simulator only when the line changes
        if idx != self._last_lyric_idx:
            self._last_lyric_idx = idx
            if self.serial.is_connected and not self._in_lyric_gap:
                if text:
                    self.serial.send_text(text)
                else:
                    self.serial.send_clear()
            if text:
                self._oled_sim.set_text(text)
            elif not self._in_lyric_gap:
                self._oled_sim.clear()

    def _gap_until_next_lyric(self, position_ms: int, total_offset: int) -> int:
        """Return ms until the next lyric starts, or -1 if no more lyrics."""
        adjusted = position_ms - total_offset
        for line in self._lyrics:
            if line.start_ms > adjusted:
                return line.start_ms - adjusted
        return -1

    def _send_equalizer_levels(self):
        if self.config.display_mode != "equalizer" and not self._in_lyric_gap:
            return
        if not self.player.is_playing:
            return
        volume = self.player.get_volume()
        if volume <= 0.01:
            levels = [0] * 12
        else:
            # Try real FFT-based spectrum analysis first
            levels = self._spectrum.get_levels(self.player.position)
            if levels is None:
                # Fallback: fake sine-wave animation
                t = self.player.position / 1000.0
                base = 0.2 + (volume * 0.8)
                levels = []
                for i in range(12):
                    wave = math.sin(t * 2.5 + i * 0.7)
                    wobble = math.sin(t * 0.7 + i * 1.3)
                    value = (wave + 1.0) * 0.5 + (wobble + 1.0) * 0.2
                    level = int(min(12, max(0, value * 12 * base)))
                    levels.append(level)
        if self.serial.is_connected:
            self.serial.send_equalizer(levels)
        self._oled_sim.set_equalizer(levels)

    # ═════════════════════════════════════════════════════════════
    #  OFFSET
    # ═════════════════════════════════════════════════════════════

    def _adjust_offset(self, delta: int):
        """Adjust current track offset by delta ms (hotkey handler)."""
        if self._current_track is None:
            return
        self._track_offset_ms += delta
        self._last_lyric_idx = -1  # force re-sync

    def _open_offset_editor(self, track_id: int):
        track = self.db.get_track(track_id)
        if not track:
            return
        current_offset = track.get("lyric_offset_ms", 0)
        dlg = OffsetEditorDialog(track["title"], current_offset, self)

        # If this is the currently playing track, do live updates
        is_current = self._current_track and self._current_track["id"] == track_id
        if is_current:
            self._offset_dialog = dlg
            dlg.offset_changed.connect(self._on_live_offset_change)

        dlg.exec()

        if is_current:
            self._offset_dialog = None
            dlg.offset_changed.disconnect(self._on_live_offset_change)

        if dlg.was_saved:
            self.db.set_track_offset(track_id, dlg.offset)
            if is_current:
                self._track_offset_ms = dlg.offset
            # Write offset.txt to the track folder for shareability
            audio_path = track.get("audio_path", "")
            if audio_path:
                track_dir = os.path.dirname(audio_path)
                try:
                    with open(os.path.join(track_dir, "offset.txt"), "w") as f:
                        f.write(str(dlg.offset))
                except OSError:
                    pass
            self._library_tab.refresh()
        elif is_current:
            # Revert live changes
            self._track_offset_ms = current_offset
            self._last_lyric_idx = -1

    @Slot(int)
    def _on_live_offset_change(self, offset_ms: int):
        if self._current_track:
            self._track_offset_ms = offset_ms
            self._last_lyric_idx = -1  # force re-sync

    # ═════════════════════════════════════════════════════════════
    #  SETTINGS
    # ═════════════════════════════════════════════════════════════

    def _open_settings(self):
        dlg = SettingsDialog(self.config, self)
        dlg.settings_applied.connect(self._on_settings_applied)
        dlg.exec()

    def _on_settings_applied(self):
        self._apply_hotkeys()
        self._apply_config()
        if self.serial.is_connected:
            self.serial.send_font_size(self.config.esp32_font_size)
            self.serial.send_mode(self.config.display_mode)

    # ═════════════════════════════════════════════════════════════
    #  CLEANUP
    # ═════════════════════════════════════════════════════════════

    def closeEvent(self, event):
        self.player.stop()
        self.serial.close_port()
        self._oled_sim.close()
        self.config.save()
        super().closeEvent(event)
