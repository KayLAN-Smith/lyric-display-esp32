"""
Application configuration loaded from / saved to a JSON file.

Manages hotkeys, serial port settings, display settings, and paths.
"""

import json
import os
from typing import Any

DEFAULT_CONFIG = {
    "com_port": "",
    "baud_rate": 115200,
    "auto_connect": True,
    "global_offset_ms": 0,
    "esp32_font_size": 1.5,
    "display_mode": "lyrics",
    "lyric_font_size_px": 13,
    "volume": 0.7,
    "hotkeys": {
        "play_pause": "Space",
        "next_track": "Ctrl+Right",
        "prev_track": "Ctrl+Left",
        "volume_up": "Ctrl+Up",
        "volume_down": "Ctrl+Down",
        "offset_plus_50": "Ctrl+]",
        "offset_minus_50": "Ctrl+[",
        "offset_plus_200": "Ctrl+Shift+]",
        "offset_minus_200": "Ctrl+Shift+[",
    },
}


def get_app_data_dir() -> str:
    """Return the application data directory, creating it if needed."""
    base = os.environ.get("APPDATA", os.path.expanduser("~"))
    app_dir = os.path.join(base, "LyricDisplay")
    os.makedirs(app_dir, exist_ok=True)
    return app_dir


def get_library_dir() -> str:
    """Return the library storage directory for audio/SRT files."""
    lib_dir = os.path.join(get_app_data_dir(), "library")
    os.makedirs(lib_dir, exist_ok=True)
    return lib_dir


def get_db_path() -> str:
    return os.path.join(get_app_data_dir(), "database.db")


def get_config_path() -> str:
    return os.path.join(get_app_data_dir(), "config.json")


class AppConfig:
    """Read/write application settings from a JSON config file."""

    def __init__(self, path: str = ""):
        self.path = path or get_config_path()
        self._data: dict = {}
        self.load()

    def load(self):
        """Load config from disk, filling in defaults for missing keys."""
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._data = {}
        else:
            self._data = {}
        # Merge defaults
        self._data = _deep_merge(DEFAULT_CONFIG, self._data)

    def save(self):
        """Persist config to disk."""
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a top-level config value."""
        return self._data.get(key, default)

    def set(self, key: str, value: Any):
        """Set a top-level config value and save."""
        self._data[key] = value
        self.save()

    @property
    def hotkeys(self) -> dict[str, str]:
        return self._data.get("hotkeys", DEFAULT_CONFIG["hotkeys"])

    @hotkeys.setter
    def hotkeys(self, mapping: dict[str, str]):
        self._data["hotkeys"] = mapping
        self.save()

    @property
    def com_port(self) -> str:
        return self._data.get("com_port", "")

    @com_port.setter
    def com_port(self, port: str):
        self._data["com_port"] = port
        self.save()

    @property
    def baud_rate(self) -> int:
        return self._data.get("baud_rate", 115200)

    @property
    def global_offset_ms(self) -> int:
        return self._data.get("global_offset_ms", 0)

    @global_offset_ms.setter
    def global_offset_ms(self, val: int):
        self._data["global_offset_ms"] = val
        self.save()

    @property
    def esp32_font_size(self) -> float:
        return self._data.get("esp32_font_size", 2.0)

    @esp32_font_size.setter
    def esp32_font_size(self, val: float):
        self._data["esp32_font_size"] = max(1.0, min(3.0, float(val)))
        self.save()

    @property
    def display_mode(self) -> str:
        return self._data.get("display_mode", "lyrics")

    @display_mode.setter
    def display_mode(self, mode: str):
        if mode not in {"lyrics", "equalizer"}:
            mode = "lyrics"
        self._data["display_mode"] = mode
        self.save()

    @property
    def volume(self) -> float:
        return self._data.get("volume", 0.7)

    @volume.setter
    def volume(self, val: float):
        self._data["volume"] = max(0.0, min(1.0, val))
        self.save()

    @property
    def lyric_font_size_px(self) -> int:
        return self._data.get("lyric_font_size_px", 13)

    @lyric_font_size_px.setter
    def lyric_font_size_px(self, val: int):
        self._data["lyric_font_size_px"] = max(8, min(32, val))
        self.save()


def _deep_merge(defaults: dict, overrides: dict) -> dict:
    """Recursively merge overrides into defaults."""
    result = dict(defaults)
    for k, v in overrides.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result
