"""
OLED Simulator – a PySide6 widget that replicates the 128x64 SSD1306 display
driven by the ESP32 firmware, so you can preview the OLED output on-screen
without plugging in hardware.

Layout matches the ESP32 firmware:
    Top 48 px  – lyrics (word-wrapped, vertically scrollable) or equalizer bars
    y=49       – horizontal separator line
    y=52..63   – status bar: play/pause icon + scrolling meta text
"""

import math

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSizePolicy
from PySide6.QtCore import Qt, QTimer, QRect
from PySide6.QtGui import (
    QPainter, QColor, QImage, QFont, QFontMetrics, QPen, QPolygon,
)
from PySide6.QtCore import QPoint

# ── Display constants (matching ESP32 firmware) ──────────────────────
SCREEN_WIDTH = 128
SCREEN_HEIGHT = 64
LYRICS_AREA_HEIGHT = 48
SEPARATOR_Y = 49
STATUS_BAR_Y = 52
ICON_X = 2
META_TEXT_X = 16
META_AVAIL_WIDTH = SCREEN_WIDTH - META_TEXT_X  # 112 px

# ── Scroll / animation constants ────────────────────────────────────
LYRIC_SCROLL_INTERVAL_MS = 2000
LYRIC_SCROLL_STEP = 16
META_SCROLL_SPEED_MS = 50
META_SCROLL_GAP = 30

# ── Adafruit GFX default font metrics ───────────────────────────────
# The built-in font is 5x7 rendered in a 6x8 cell per textSize=1.
GFX_CHAR_W = 6   # pixels per character at textSize=1
GFX_CHAR_H = 8   # pixels per character at textSize=1

# Equalizer
EQ_BARS = 12
EQ_MAX_LEVELS = 12

# Colors
COL_BLACK = QColor(0, 0, 0)
COL_WHITE = QColor(255, 255, 255)
# Slightly blue-tinted OLED look
COL_OLED_BG = QColor(0, 0, 8)
COL_OLED_FG = QColor(120, 200, 255)


class OledSimulator(QWidget):
    """
    Pixel-accurate simulation of the 128x64 SSD1306 OLED.

    Public methods mirror the serial commands the PC sends to the ESP32:
        clear(), set_text(), set_font_size(), set_mode(),
        set_state(), set_meta(), set_equalizer()
    """

    SCALE = 5  # each OLED pixel = 5x5 screen pixels

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("OLED Simulator (128\u00d764)")
        self.setFixedSize(SCREEN_WIDTH * self.SCALE + 16,
                          SCREEN_HEIGHT * self.SCALE + 32)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)

        header = QLabel("OLED Preview  (128\u00d764)")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet("font-size: 10px; color: #888;")
        layout.addWidget(header)

        self._canvas = _OledCanvas(self.SCALE, self)
        layout.addWidget(self._canvas)

    # ── Public API (mirrors serial commands) ─────────────────────────

    def clear(self):
        self._canvas.clear()

    def set_text(self, text: str):
        self._canvas.set_text(text)

    def set_font_size(self, size: float):
        self._canvas.set_font_size(size)

    def set_mode(self, mode: str):
        """mode: 'lyrics' or 'equalizer'"""
        self._canvas.set_mode(mode)

    def set_state(self, state: str):
        """state: 'playing', 'paused', or 'stopped'"""
        self._canvas.set_state(state)

    def set_meta(self, text: str):
        self._canvas.set_meta(text)

    def set_equalizer(self, levels: list[int]):
        self._canvas.set_equalizer(levels)


class _OledCanvas(QWidget):
    """The actual drawing surface for the OLED simulation."""

    def __init__(self, scale: int, parent=None):
        super().__init__(parent)
        self._scale = scale
        self.setFixedSize(SCREEN_WIDTH * scale, SCREEN_HEIGHT * scale)

        # ── State (mirrors ESP32 globals) ────────────────────────────
        self._current_text: str = ""
        self._text_size: int = 2
        self._text_scale: float = 2.0
        self._use_custom_font: bool = False
        self._display_mode: str = "lyrics"  # "lyrics" or "equalizer"
        self._play_state: str = "stopped"
        self._meta_text: str = ""

        # Lyric scroll
        self._lyric_scroll_offset: int = 0
        self._total_lyric_height: int = 0

        # Meta scroll
        self._meta_text_width: int = 0
        self._meta_scroll_x: int = 0
        self._meta_needs_scroll: bool = False

        # Equalizer
        self._eq_heights: list[int] = [0] * EQ_BARS

        # ── Scroll timers ────────────────────────────────────────────
        self._lyric_scroll_timer = QTimer(self)
        self._lyric_scroll_timer.setInterval(LYRIC_SCROLL_INTERVAL_MS)
        self._lyric_scroll_timer.timeout.connect(self._on_lyric_scroll)

        self._meta_scroll_timer = QTimer(self)
        self._meta_scroll_timer.setInterval(META_SCROLL_SPEED_MS)
        self._meta_scroll_timer.timeout.connect(self._on_meta_scroll)

        # Pre-allocate the image buffer to avoid per-frame allocation
        self._img = QImage(SCREEN_WIDTH, SCREEN_HEIGHT, QImage.Format.Format_RGB32)

    # ── State setters ────────────────────────────────────────────────

    def clear(self):
        self._current_text = ""
        self._lyric_scroll_offset = 0
        self._total_lyric_height = 0
        self._lyric_scroll_timer.stop()
        self.update()

    def set_text(self, text: str):
        if text != self._current_text:
            self._current_text = text
            self._lyric_scroll_offset = 0
            self._total_lyric_height = 0
            self.update()

    def set_font_size(self, size: float):
        size = max(1.0, min(3.0, size))
        if size != self._text_scale:
            self._text_scale = size
            self._use_custom_font = (1.4 < size < 1.6) or (2.4 < size < 2.6)
            if not self._use_custom_font:
                self._text_size = int(size + 0.5)
            self._lyric_scroll_offset = 0
            self.update()

    def set_mode(self, mode: str):
        mapped = "equalizer" if mode in ("equalizer", "EQ") else "lyrics"
        if mapped != self._display_mode:
            self._display_mode = mapped
            self._lyric_scroll_offset = 0
            self.update()

    def set_state(self, state: str):
        if state not in ("playing", "paused", "stopped"):
            state = "stopped"
        if state != self._play_state:
            self._play_state = state
            self.update()

    def set_meta(self, text: str):
        if text != self._meta_text:
            self._meta_text = text
            self._meta_text_width = len(text) * GFX_CHAR_W
            self._meta_scroll_x = 0
            self._meta_needs_scroll = self._meta_text_width > META_AVAIL_WIDTH
            if self._meta_needs_scroll:
                self._meta_scroll_timer.start()
            else:
                self._meta_scroll_timer.stop()
            self.update()

    def set_equalizer(self, levels: list[int]):
        changed = False
        for i in range(min(EQ_BARS, len(levels))):
            v = max(0, min(EQ_MAX_LEVELS, levels[i]))
            if self._eq_heights[i] != v:
                self._eq_heights[i] = v
                changed = True
        if changed:
            self.update()

    # ── Scroll handlers ──────────────────────────────────────────────

    def _update_lyric_scroll_timer(self):
        """Start or stop the lyric scroll timer based on content height."""
        needs = (self._display_mode == "lyrics"
                 and self._total_lyric_height > LYRICS_AREA_HEIGHT
                 and len(self._current_text) > 0)
        if needs and not self._lyric_scroll_timer.isActive():
            self._lyric_scroll_timer.start()
        elif not needs and self._lyric_scroll_timer.isActive():
            self._lyric_scroll_timer.stop()

    def _on_lyric_scroll(self):
        if self._total_lyric_height <= LYRICS_AREA_HEIGHT:
            self._lyric_scroll_timer.stop()
            return
        max_scroll = self._total_lyric_height - LYRICS_AREA_HEIGHT
        self._lyric_scroll_offset += LYRIC_SCROLL_STEP
        if self._lyric_scroll_offset > max_scroll:
            self._lyric_scroll_offset = 0
        self.update()

    def _on_meta_scroll(self):
        if not self._meta_needs_scroll:
            return
        total_w = self._meta_text_width + META_SCROLL_GAP
        self._meta_scroll_x = (self._meta_scroll_x + 1) % total_w
        self.update()

    # ── Paint ────────────────────────────────────────────────────────

    def paintEvent(self, event):
        # Draw onto the pre-allocated 128x64 QImage, then scale up
        img = self._img
        img.fill(COL_OLED_BG)

        p = QPainter(img)
        p.setPen(QPen(COL_OLED_FG))

        # 1. Main area (clipped to lyrics zone so text can't bleed into status bar)
        p.save()
        p.setClipRect(QRect(0, 0, SCREEN_WIDTH, LYRICS_AREA_HEIGHT))
        if self._display_mode == "equalizer":
            self._paint_equalizer(p)
        else:
            if self._current_text:
                self._paint_lyrics(p)
        p.restore()

        # 2. Separator
        p.drawLine(0, SEPARATOR_Y, SCREEN_WIDTH - 1, SEPARATOR_Y)

        # 3. Status bar
        self._paint_status_bar(p)

        p.end()

        # Check if lyric scroll timer needs starting/stopping
        self._update_lyric_scroll_timer()

        # Scale up and draw to widget
        scaled = img.scaled(
            SCREEN_WIDTH * self._scale,
            SCREEN_HEIGHT * self._scale,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        wp = QPainter(self)
        wp.drawImage(0, 0, scaled)
        wp.end()

    def _paint_lyrics(self, p: QPainter):
        """Word-wrap and draw lyrics in the top 48px area."""
        if self._use_custom_font:
            # 1.5x ~ FreeSans9pt (14px), 2.5x ~ FreeSans12pt (18px)
            char_h = 18 if (2.4 < self._text_scale < 2.6) else 14
            self._paint_lyrics_custom_font(p, char_h)
        else:
            char_w = GFX_CHAR_W * self._text_size
            char_h = GFX_CHAR_H * self._text_size
            chars_per_line = max(1, SCREEN_WIDTH // char_w)

            lines = self._word_wrap(self._current_text, chars_per_line)
            self._total_lyric_height = len(lines) * char_h

            font = QFont("Courier New", 1)
            font.setPixelSize(max(1, char_h - 2))
            font.setStyleStrategy(QFont.StyleStrategy.NoAntialias)
            p.setFont(font)

            start_y = -self._lyric_scroll_offset
            for i, line in enumerate(lines):
                y = start_y + i * char_h
                if y + char_h > 0 and y < LYRICS_AREA_HEIGHT:
                    p.drawText(0, y + char_h - 2, line)

    def _paint_lyrics_custom_font(self, p: QPainter, char_h: int):
        """Render lyrics with a proportional font (simulating FreeSans9pt7b)."""
        font = QFont("Arial", 1)
        font.setPixelSize(max(1, char_h - 2))
        font.setStyleStrategy(QFont.StyleStrategy.NoAntialias)
        p.setFont(font)
        fm = QFontMetrics(font)

        # Word-wrap using pixel width
        lines: list[str] = []
        words = self._current_text.split()
        current_line = ""
        for word in words:
            candidate = (current_line + " " + word).strip() if current_line else word
            if fm.horizontalAdvance(candidate) <= SCREEN_WIDTH:
                current_line = candidate
            elif current_line:
                lines.append(current_line)
                current_line = word
            else:
                # Single word wider than screen — force it
                current_line = word
        if current_line:
            lines.append(current_line)

        self._total_lyric_height = len(lines) * char_h

        start_y = -self._lyric_scroll_offset
        for i, line in enumerate(lines):
            y = start_y + i * char_h
            if y + char_h > 0 and y < LYRICS_AREA_HEIGHT:
                p.drawText(0, y + char_h - 2, line)

    def _paint_equalizer(self, p: QPainter):
        """Draw EQ bars in the top 48px area."""
        bar_width = SCREEN_WIDTH // EQ_BARS
        max_height = LYRICS_AREA_HEIGHT - 2

        for i in range(EQ_BARS):
            level = self._eq_heights[i]
            bar_height = (level * max_height) // EQ_MAX_LEVELS
            x = i * bar_width
            y = max_height - bar_height
            if bar_height > 0:
                p.fillRect(x + 1, y, bar_width - 2, bar_height, COL_OLED_FG)

    def _paint_status_bar(self, p: QPainter):
        """Draw play/pause icon and scrolling meta text."""
        icon_y = STATUS_BAR_Y

        # Play/pause/stop icon
        if self._play_state == "playing":
            # Triangle (play)
            tri = QPolygon([
                QPoint(ICON_X, icon_y),
                QPoint(ICON_X, icon_y + 10),
                QPoint(ICON_X + 8, icon_y + 5),
            ])
            p.setBrush(COL_OLED_FG)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPolygon(tri)
            p.setPen(QPen(COL_OLED_FG))
            p.setBrush(Qt.BrushStyle.NoBrush)
        elif self._play_state == "paused":
            p.fillRect(ICON_X, icon_y, 3, 11, COL_OLED_FG)
            p.fillRect(ICON_X + 5, icon_y, 3, 11, COL_OLED_FG)
        else:
            # Stop square
            p.fillRect(ICON_X, icon_y, 9, 9, COL_OLED_FG)

        # Meta text
        if not self._meta_text:
            return

        meta_font_px = 10
        font = QFont("Courier New", 1)
        font.setPixelSize(meta_font_px)
        font.setStyleStrategy(QFont.StyleStrategy.NoAntialias)
        p.setFont(font)

        if not self._meta_needs_scroll:
            p.drawText(META_TEXT_X, STATUS_BAR_Y + meta_font_px, self._meta_text)
        else:
            # Scrolling text — draw two copies offset by total width
            total_w = self._meta_text_width + META_SCROLL_GAP
            for pass_i in range(2):
                base_x = META_TEXT_X - self._meta_scroll_x + pass_i * total_w
                # Clip: only draw if visible
                if base_x + self._meta_text_width < META_TEXT_X:
                    continue
                if base_x >= SCREEN_WIDTH:
                    continue
                # Save clip region, draw, restore
                p.save()
                p.setClipRect(QRect(META_TEXT_X, STATUS_BAR_Y,
                                    META_AVAIL_WIDTH, SCREEN_HEIGHT - STATUS_BAR_Y))
                p.drawText(base_x, STATUS_BAR_Y + 10, self._meta_text)
                p.restore()

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _word_wrap(text: str, chars_per_line: int) -> list[str]:
        """Word-wrap text to fit chars_per_line (matching ESP32 algorithm)."""
        lines: list[str] = []
        pos = 0
        length = len(text)

        while pos < length and len(lines) < 32:
            remaining = length - pos
            if remaining <= chars_per_line:
                lines.append(text[pos:])
                break

            break_at = pos + chars_per_line
            last_space = -1
            for i in range(pos, min(break_at, length)):
                if text[i] == " ":
                    last_space = i

            if last_space > pos:
                lines.append(text[pos:last_space])
                pos = last_space + 1
            else:
                lines.append(text[pos:break_at])
                pos = break_at

        return lines
