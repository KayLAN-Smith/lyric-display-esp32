"""
Serial connection manager for ESP32 communication.

Runs a reader thread to receive button events and heartbeat responses.
Provides thread-safe methods to send display commands.

Protocol (newline-delimited, UTF-8):
    PC -> ESP32:  CLR | TXT|<text> | PING | FONT|<1.0-3.0> | MODE|<LYR/EQ>
                  EQ|<levels>
                  STA|PLAY | STA|PAUSE | STA|STOP
                  META|<artist – title>
    ESP32 -> PC:  PONG | BTN|PRESS | BTN|LONG
"""

import time
import threading
from typing import Optional

import serial
import serial.tools.list_ports
from PySide6.QtCore import QObject, Signal, QTimer


def list_serial_ports() -> list[str]:
    """Return list of available COM port names."""
    return [p.device for p in serial.tools.list_ports.comports()]


class SerialConnection(QObject):
    """
    Manages USB serial connection to the ESP32.

    Signals:
        connected        - Emitted when connection is established.
        disconnected     - Emitted when connection is lost.
        button_press     - Short press detected.
        button_long      - Long press detected.
        error(str)       - Communication error.
    """

    connected = Signal()
    disconnected = Signal()
    button_press = Signal()
    button_long = Signal()
    error = Signal(str)

    PING_INTERVAL_S = 2.0
    PONG_TIMEOUT_S = 5.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._serial: Optional[serial.Serial] = None
        self._port: str = ""
        self._baud: int = 115200
        self._running = False
        self._reader_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._is_connected = False
        self._last_pong_time: float = 0

        # Ping timer (runs on Qt main thread)
        self._ping_timer = QTimer(self)
        self._ping_timer.timeout.connect(self._send_ping)

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    @property
    def port(self) -> str:
        return self._port

    def open_port(self, port: str, baud: int = 115200) -> bool:
        """Open serial connection and start reader thread."""
        self.close_port()

        self._port = port
        self._baud = baud

        try:
            self._serial = serial.Serial(
                port=port,
                baudrate=baud,
                timeout=0.1,
                write_timeout=0.1,
            )
            time.sleep(0.1)  # Let ESP32 reset if needed
        except (serial.SerialException, OSError) as e:
            self.error.emit(f"Cannot open {port}: {e}")
            return False

        self._running = True
        self._last_pong_time = time.time()
        self._reader_thread = threading.Thread(
            target=self._reader_loop, daemon=True
        )
        self._reader_thread.start()

        self._ping_timer.start(int(self.PING_INTERVAL_S * 1000))

        # Don't set _is_connected = True here; wait for first PONG.
        # Send an initial ping so we discover the ESP32 quickly.
        self._write("PING\n")
        return True

    def close_port(self):
        """Close the serial connection."""
        self._running = False
        self._ping_timer.stop()

        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=2.0)
        self._reader_thread = None

        with self._lock:
            if self._serial and self._serial.is_open:
                try:
                    self._serial.close()
                except Exception:
                    pass
            self._serial = None

        if self._is_connected:
            self._is_connected = False
            self.disconnected.emit()

    def send_clear(self):
        """Send CLR command."""
        self._write("CLR\n")

    def send_text(self, text: str):
        """Send TXT|<text> command. Newlines in text are replaced with spaces."""
        clean = text.replace("\n", " ").replace("\r", "")
        self._write(f"TXT|{clean}\n")

    def send_font_size(self, size: float):
        """Send FONT|<size> command (1.0-3.0)."""
        size = max(1.0, min(3.0, float(size)))
        self._write(f"FONT|{size:.1f}\n")

    def send_state(self, state: str):
        """Send STA|PLAY, STA|PAUSE, or STA|STOP."""
        cmd = {"playing": "PLAY", "paused": "PAUSE", "stopped": "STOP"}.get(state, "STOP")
        self._write(f"STA|{cmd}\n")

    def send_meta(self, text: str):
        """Send META|<artist – title> for the status bar."""
        clean = text.replace("\n", " ").replace("\r", "")
        self._write(f"META|{clean}\n")

    def send_mode(self, mode: str):
        """Send MODE|LYR or MODE|EQ command."""
        mapped = "EQ" if mode == "equalizer" else "LYR"
        self._write(f"MODE|{mapped}\n")

    def send_equalizer(self, levels: list[int]):
        """Send EQ|<levels> command with comma-separated 0-12 values."""
        clean_levels = [str(max(0, min(12, int(v)))) for v in levels]
        payload = ",".join(clean_levels)
        self._write(f"EQ|{payload}\n")

    def _send_ping(self):
        """Periodic ping (called by QTimer on main thread)."""
        if not self._running:
            return
        self._write("PING\n")
        # Check pong timeout
        if time.time() - self._last_pong_time > self.PONG_TIMEOUT_S:
            if self._is_connected:
                self._is_connected = False
            # No response — close port entirely to stop blocking writes
            self.error.emit(f"No response from {self._port}")
            QTimer.singleShot(0, self.close_port)

    def _write(self, data: str):
        """Thread-safe serial write."""
        with self._lock:
            if self._serial and self._serial.is_open:
                try:
                    self._serial.write(data.encode("utf-8"))
                except (serial.SerialException, OSError):
                    pass  # Will be caught by pong timeout

    def _reader_loop(self):
        """Background thread: reads lines from serial."""
        buffer = ""
        while self._running:
            try:
                # Grab a reference to the serial port under the lock,
                # but do the actual read OUTSIDE the lock so writes
                # from the main thread are never blocked by a slow read.
                with self._lock:
                    if not self._serial or not self._serial.is_open:
                        break
                    ser = self._serial

                raw = ser.read(256)

                if not raw:
                    continue
                buffer += raw.decode("utf-8", errors="replace")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    self._process_line(line)
            except (serial.SerialException, OSError):
                # Port disconnected
                if self._running:
                    self._is_connected = False
                    self.disconnected.emit()
                break
            except Exception:
                continue

    def _process_line(self, line: str):
        """Process a received line from ESP32."""
        if line == "PONG":
            self._last_pong_time = time.time()
            if not self._is_connected:
                self._is_connected = True
                self.connected.emit()
        elif line == "BTN|PRESS":
            self.button_press.emit()
        elif line == "BTN|LONG":
            self.button_long.emit()
