# Lyric Display – Windows + ESP32 OLED

A Windows desktop application that plays MP3 songs and displays synchronized
lyrics on a 0.96" SSD1306 OLED connected to an ESP32 Dev Module over USB serial.

## Architecture

```
┌──────────────────────────┐     USB Serial (115200)     ┌─────────────────────┐
│  Windows PC              │ ──────────────────────────── │  ESP32 Dev Module   │
│                          │   PC → ESP32: CLR, TXT|..., │                     │
│  • PySide6 GUI           │              PING, FONT|n   │  • Reads serial     │
│  • MP3 playback          │                              │  • Renders text on  │
│  • SRT lyric parsing     │   ESP32 → PC: PONG,         │    128×64 SSD1306   │
│  • SQLite library        │              BTN|PRESS,      │  • Button input     │
│  • Serial communication  │              BTN|LONG        │    (play/pause/next)│
└──────────────────────────┘                              └─────────────────────┘
```

## Features

- **Song library** with SQLite metadata, import MP3+SRT pairs
- **Playlists** – create, rename, delete, reorder, shuffle, play in order
- **Synced playback** – lyrics follow the audio position, not wall clock
- **ESP32 OLED display** – one lyric line at a time, word-wrapped, auto-scrolling for long lines
- **Offset calibration** – global offset + per-track offset, adjustable in real time
- **Configurable hotkeys** – play/pause, next/prev, offset adjustment, volume
- **Physical button** on ESP32 – short press = play/pause, long press = next track
- **Auto-reconnect** – serial connection resilience; app works without ESP32
- **Packageable** as a Windows .exe via PyInstaller

## Hardware Requirements

| Component | Details |
|-----------|---------|
| ESP32 Dev Module | Any ESP32 with USB serial (e.g. ESP32-WROOM-32) |
| SSD1306 OLED | 0.96", 128×64, I2C, 4-pin |
| Push button | Momentary, connected to GPIO 4 (configurable) |
| Wiring | VCC→3.3V, GND→GND, SDA→GPIO 21, SCL→GPIO 22 |

### Wiring Diagram

```
ESP32              SSD1306 OLED
─────              ────────────
3.3V  ──────────── VCC
GND   ──────────── GND
GPIO 21 (SDA) ──── SDA
GPIO 22 (SCL) ──── SCL

ESP32              Button
─────              ──────
GPIO 4 ──────────── one leg
GND    ──────────── other leg
(internal pull-up enabled in firmware)
```

## Setup Instructions

### 1. ESP32 Firmware

**Prerequisites:**
- [Arduino IDE](https://www.arduino.cc/en/software) 1.8+ or 2.x
- ESP32 board package installed in Arduino IDE
  ([instructions](https://docs.espressif.com/projects/arduino-esp32/en/latest/installing.html))
- Libraries installed via Library Manager:
  - `Adafruit SSD1306`
  - `Adafruit GFX Library`

**Upload:**

1. Open `esp32/lyric_display/lyric_display.ino` in Arduino IDE
2. Select board: **ESP32 Dev Module**
3. Select the correct COM port
4. Click **Upload**
5. Open Serial Monitor at **115200 baud** to verify – you should see "Waiting for connection..." on the OLED

**Configuration constants** (edit at top of .ino if needed):

| Constant | Default | Description |
|----------|---------|-------------|
| `SCREEN_ADDRESS` | `0x3C` | I2C address of the SSD1306 |
| `SDA_PIN` | `21` | I2C data pin |
| `SCL_PIN` | `22` | I2C clock pin |
| `BUTTON_PIN` | `4` | GPIO for the push button |
| `BAUD_RATE` | `115200` | Serial baud rate |
| `LONG_PRESS_MS` | `700` | Long press threshold (ms) |
| `SCROLL_INTERVAL_MS` | `2000` | Auto-scroll speed for long text |

### 2. Windows Application

**Prerequisites:**
- Python 3.10 or newer
- Windows 10/11

**Install dependencies:**

```bash
cd <project-root>
pip install -r requirements.txt
```

**Run the app:**

```bash
python app/main.py
```

### 3. Connect ESP32

1. Plug in the ESP32 via USB
2. In the app, select the COM port from the dropdown (top of window)
3. Click **Connect**
4. Status should change to **Connected** (green)

### 4. Import Songs

1. Click **Import Song** (or File → Import Song)
2. Browse to an MP3 file
3. Optionally browse to a matching SRT lyric file
4. Enter a title (auto-filled from filename) and artist
5. Click **Import**

**SRT format example:**

```
1
00:00:05,000 --> 00:00:09,000
This is the first lyric line

2
00:00:10,500 --> 00:00:14,000
This is the second lyric line
```

### 5. Create Playlists

1. Go to the **Playlists** tab
2. Click **New**, enter a name
3. Right-click songs in **All Songs** → **Add to Playlist**
4. In the playlist view, use **Move Up/Down** to reorder
5. Click **Play All** or double-click a song to start

### 6. Adjust Lyric Offset

**Global offset** (applies to all songs):
- File → Settings → Display tab → Global Lyric Offset

**Per-track offset** (stored in database):
- Right-click a song → **Edit Lyric Offset**
- Use the +50/−50/+200/−200 ms buttons while the song plays
- See the effect in real time on both the PC and ESP32 display
- Click **Save** to persist

**Hotkeys** (while the main window is focused):
- `Ctrl+]` / `Ctrl+[` → ±50 ms
- `Ctrl+Shift+]` / `Ctrl+Shift+[` → ±200 ms

### 7. Build the Windows Executable

See [build_exe.md](build_exe.md) for detailed instructions.

Quick version:

```bash
pip install pyinstaller
pyinstaller --name LyricDisplay --windowed --onedir ^
    --hidden-import PySide6.QtMultimedia ^
    app/main.py
```

Output: `dist/LyricDisplay/LyricDisplay.exe`

## Serial Protocol Reference

All messages are newline-delimited UTF-8.

| Direction | Message | Description |
|-----------|---------|-------------|
| PC → ESP32 | `CLR` | Clear the display |
| PC → ESP32 | `TXT\|<text>` | Display lyric text (one line) |
| PC → ESP32 | `PING` | Heartbeat request |
| PC → ESP32 | `FONT\|<1-3>` | Set text size on OLED |
| ESP32 → PC | `PONG` | Heartbeat response |
| ESP32 → PC | `BTN\|PRESS` | Short button press |
| ESP32 → PC | `BTN\|LONG` | Long button press (>700 ms) |

## Hotkey Defaults

| Action | Default Key |
|--------|-------------|
| Play / Pause | `Space` |
| Next track | `Ctrl+Right` |
| Previous track | `Ctrl+Left` |
| Volume up | `Ctrl+Up` |
| Volume down | `Ctrl+Down` |
| Offset +50 ms | `Ctrl+]` |
| Offset −50 ms | `Ctrl+[` |
| Offset +200 ms | `Ctrl+Shift+]` |
| Offset −200 ms | `Ctrl+Shift+[` |

All hotkeys are configurable in File → Settings → Hotkeys tab.

## Project Structure

```
├── app/
│   ├── main.py                 # Entry point
│   ├── audio/
│   │   └── player.py           # QMediaPlayer wrapper
│   ├── db/
│   │   └── database.py         # SQLite layer
│   ├── serial_comm/
│   │   └── connection.py       # USB serial manager
│   ├── srt/
│   │   └── parser.py           # SRT file parser
│   ├── settings/
│   │   └── config.py           # JSON config manager
│   ├── ui/
│   │   ├── main_window.py      # Main window orchestrator
│   │   ├── library_tab.py      # All Songs tab
│   │   ├── playlists_tab.py    # Playlists tab
│   │   ├── playback_controls.py # Transport bar + seek + lyrics
│   │   ├── import_dialog.py    # Song import dialog
│   │   ├── offset_editor.py    # Per-track offset calibration
│   │   └── settings_dialog.py  # Settings dialog
│   └── assets/                 # (icons, etc.)
├── esp32/
│   └── lyric_display/
│       └── lyric_display.ino   # ESP32 Arduino sketch
├── requirements.txt
├── build_exe.md
└── README.md
```

## Data Storage

The app stores all data in `%APPDATA%\LyricDisplay\`:

```
%APPDATA%\LyricDisplay\
├── database.db       # SQLite – tracks, playlists, settings
├── config.json       # Hotkeys, serial port, display settings
└── library/
    ├── <uuid1>/
    │   ├── audio.mp3
    │   └── lyrics.srt
    ├── <uuid2>/
    │   ├── audio.mp3
    │   └── lyrics.srt
    └── ...
```

## Troubleshooting

### ESP32 / Serial Issues

| Problem | Solution |
|---------|----------|
| **Wrong COM port** | Open Device Manager → Ports (COM & LPT) to find the correct port. Install the CP2102 or CH340 driver if the port doesn't appear. |
| **"Cannot open COMx"** | Close Arduino IDE Serial Monitor or any other app using the port. Unplug and replug the ESP32. |
| **OLED shows nothing** | Check wiring (SDA→21, SCL→22, VCC→3.3V). Verify OLED address with an I2C scanner sketch. Try `0x3D` if `0x3C` doesn't work. |
| **Garbled text on OLED** | Ensure baud rate matches (115200 in both app settings and sketch). Try a shorter USB cable. |
| **"Disconnected" keeps flashing** | The ESP32 may be resetting. Check power supply. Some USB hubs cause issues – try a direct port. |
| **Button not working** | Verify wiring: one leg to GPIO 4, other to GND. The sketch uses `INPUT_PULLUP`, so no external resistor needed. |

### Audio Issues

| Problem | Solution |
|---------|----------|
| **No audio** | Check Windows volume mixer. Ensure the correct output device is selected in Windows Sound settings. |
| **MP3 won't play** | Install the Windows Media Feature Pack (required on Windows N/KN editions). Verify the file plays in Windows Media Player. |
| **Audio stutters** | Close other heavy applications. Try a different audio output device. |

### Lyric Sync Issues

| Problem | Solution |
|---------|----------|
| **Lyrics too early** | Increase the per-track offset (positive values delay lyrics). Use the offset editor for real-time adjustment. |
| **Lyrics too late** | Decrease the offset (negative values advance lyrics). |
| **Lyrics don't appear** | Verify the SRT file is valid. Open it in a text editor and check the timestamp format: `HH:MM:SS,mmm --> HH:MM:SS,mmm`. |
| **Lyrics on PC but not on OLED** | Check serial connection status. The OLED only updates when the lyric line changes. |
| **Drift over time** | The app uses the audio engine position (not wall clock), so drift should not occur. If it does, the SRT timestamps may be wrong. |

### Build / Packaging Issues

| Problem | Solution |
|---------|----------|
| **PyInstaller fails** | Ensure you're using the same Python that has PySide6 installed. Run `pip show PySide6` to verify. |
| **Built exe crashes on start** | Run from command line to see the error: `dist\LyricDisplay\LyricDisplay.exe`. Add `--debug all` to PyInstaller for verbose output. |
| **Missing Qt plugins** | Add `--collect-all PySide6` to the PyInstaller command. |
