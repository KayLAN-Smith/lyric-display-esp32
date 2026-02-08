"""
Audio playback engine using Qt6 Multimedia (QMediaPlayer).

Provides play, pause, stop, seek, and accurate position tracking.
"""

from PySide6.QtCore import QObject, Signal, QUrl, QTimer
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput


class AudioPlayer(QObject):
    """
    Wraps QMediaPlayer for MP3 playback with position tracking.

    Signals:
        position_changed(int)   - Current playback position in ms.
        duration_changed(int)   - Total duration in ms.
        state_changed(str)      - "playing", "paused", or "stopped".
        media_ended             - Current track finished naturally.
        error_occurred(str)     - Playback error description.
    """

    position_changed = Signal(int)
    duration_changed = Signal(int)
    state_changed = Signal(str)
    media_ended = Signal()
    error_occurred = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._player.setAudioOutput(self._audio_output)

        # Position polling timer (50 ms for smooth sync)
        self._pos_timer = QTimer(self)
        self._pos_timer.setInterval(50)
        self._pos_timer.timeout.connect(self._poll_position)

        # Fallback timer: force play if media status never reaches Loaded
        self._auto_play_timeout = QTimer(self)
        self._auto_play_timeout.setSingleShot(True)
        self._auto_play_timeout.setInterval(2000)
        self._auto_play_timeout.timeout.connect(self._on_auto_play_timeout)

        # Connect Qt signals
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_state_changed)
        self._player.errorOccurred.connect(self._on_error)
        self._player.mediaStatusChanged.connect(self._on_media_status)

        self._last_emitted_pos = -1
        self._auto_play = False

    # ── Public API ───────────────────────────────────────────────

    def load(self, filepath: str):
        """Load an audio file for playback."""
        self._auto_play_timeout.stop()
        self._auto_play = False
        self._player.stop()
        self._player.setSource(QUrl.fromLocalFile(filepath))
        self._last_emitted_pos = -1

    def load_and_play(self, filepath: str):
        """Load an audio file and start playback once ready."""
        self._auto_play_timeout.stop()
        # Keep _auto_play False during stop() so media status events from
        # the old song don't consume it.
        self._auto_play = False
        self._player.stop()
        # Now set the flag before setSource() so a synchronous LoadedMedia
        # (which can happen on Windows) is handled correctly.
        self._auto_play = True
        self._player.setSource(QUrl.fromLocalFile(filepath))
        self._last_emitted_pos = -1
        # Start a fallback timer in case LoadedMedia/BufferedMedia never fires
        if self._auto_play:
            self._auto_play_timeout.start()

    def play(self):
        self._player.play()
        self._pos_timer.start()

    def pause(self):
        self._player.pause()
        self._pos_timer.stop()

    def stop(self):
        self._player.stop()
        self._pos_timer.stop()
        self._last_emitted_pos = -1
        self.position_changed.emit(0)

    def toggle_play_pause(self):
        state = self._player.playbackState()
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.pause()
        else:
            self.play()

    def seek(self, position_ms: int):
        self._player.setPosition(position_ms)

    def set_volume(self, volume: float):
        """Set volume (0.0 to 1.0)."""
        self._audio_output.setVolume(max(0.0, min(1.0, volume)))

    def get_volume(self) -> float:
        return self._audio_output.volume()

    @property
    def position(self) -> int:
        """Current playback position in milliseconds."""
        return self._player.position()

    @property
    def duration(self) -> int:
        """Total duration in milliseconds."""
        return self._player.duration()

    @property
    def is_playing(self) -> bool:
        return self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    @property
    def is_paused(self) -> bool:
        return self._player.playbackState() == QMediaPlayer.PlaybackState.PausedState

    @property
    def is_stopped(self) -> bool:
        return self._player.playbackState() == QMediaPlayer.PlaybackState.StoppedState

    # ── Internal ─────────────────────────────────────────────────

    def _poll_position(self):
        pos = self._player.position()
        if pos != self._last_emitted_pos:
            self._last_emitted_pos = pos
            self.position_changed.emit(pos)

    def _on_duration_changed(self, duration_ms: int):
        self.duration_changed.emit(duration_ms)

    def _on_state_changed(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.state_changed.emit("playing")
            self._pos_timer.start()
        elif state == QMediaPlayer.PlaybackState.PausedState:
            self.state_changed.emit("paused")
            self._pos_timer.stop()
        else:
            self.state_changed.emit("stopped")
            self._pos_timer.stop()

    def _on_media_status(self, status):
        if status in (
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
        ):
            if self._auto_play:
                self._auto_play = False
                self._auto_play_timeout.stop()
                # Seek to 0 now that media is fully loaded, then play
                self._player.setPosition(0)
                self.play()
        elif status == QMediaPlayer.MediaStatus.StalledMedia:
            # On Windows, media can stall briefly during loading.
            # If we're trying to auto-play, give it another nudge.
            if self._auto_play:
                self._player.play()
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._pos_timer.stop()
            self.media_ended.emit()

    def _on_auto_play_timeout(self):
        """Fallback: force play if media status callbacks didn't trigger."""
        if self._auto_play:
            self._auto_play = False
            self._player.setPosition(0)
            self.play()

    def _on_error(self, error, error_string=""):
        msg = self._player.errorString() or str(error)
        self.error_occurred.emit(msg)
