# Building the Lyric Display Executable

## Prerequisites

- Python 3.10+ installed and on PATH
- All dependencies installed: `pip install -r requirements.txt`
- PyInstaller: `pip install pyinstaller`

## Build Command

From the project root directory:

```bash
pyinstaller --name LyricDisplay ^
    --windowed ^
    --onedir ^
    --add-data "app/assets;assets" ^
    --hidden-import PySide6.QtMultimedia ^
    --hidden-import PySide6.QtWidgets ^
    --hidden-import PySide6.QtCore ^
    --hidden-import PySide6.QtGui ^
    app/main.py
```

### One-file variant (larger startup time, single .exe)

```bash
pyinstaller --name LyricDisplay ^
    --windowed ^
    --onefile ^
    --hidden-import PySide6.QtMultimedia ^
    --hidden-import PySide6.QtWidgets ^
    --hidden-import PySide6.QtCore ^
    --hidden-import PySide6.QtGui ^
    app/main.py
```

## Output

- `--onedir` build: `dist/LyricDisplay/LyricDisplay.exe` (plus support files in the same folder)
- `--onefile` build: `dist/LyricDisplay.exe`

## Notes

- The app stores its data (database, imported songs, config) in
  `%APPDATA%\LyricDisplay\`, so no data is bundled in the exe.
- On first run the app creates the database and config automatically.
- If the build fails with missing DLL errors, ensure the MSVC redistributable
  is installed and PySide6 is the correct version for your Python.
- If `PySide6.QtMultimedia` fails to load audio, install the
  Windows Media Feature Pack (required on some Windows N/KN editions).

## Troubleshooting Build Issues

| Issue | Solution |
|-------|---------|
| `ModuleNotFoundError: PySide6` | Run `pip install PySide6` in the same Python used by PyInstaller |
| Missing Qt plugins | Add `--collect-all PySide6` to the PyInstaller command |
| No audio playback in built exe | Add `--hidden-import PySide6.QtMultimedia` (already included above) |
| Large exe size | Use `--onedir` instead of `--onefile`; use UPX for compression |
