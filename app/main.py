"""
Lyric Display – Windows desktop app for synced lyric display on ESP32 OLED.

Entry point: creates the Qt application, initializes the database and
config, and launches the main window.
"""

import sys
import os

# Ensure the app package is on sys.path when running from source
APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from db.database import Database
from settings.config import AppConfig, get_db_path
from ui.main_window import MainWindow


def main():
    # High-DPI scaling (Qt6 enables this by default, but be explicit)
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Lyric Display")
    app.setOrganizationName("LyricDisplay")

    # Apply a clean stylesheet
    app.setStyleSheet(_STYLESHEET)

    # Initialize database and config
    db = Database(get_db_path())
    config = AppConfig()

    # Launch main window
    window = MainWindow(db, config)
    window.show()

    sys.exit(app.exec())


_STYLESHEET = """
QMainWindow {
    background-color: #f5f5f5;
}
QTabWidget::pane {
    border: 1px solid #ccc;
    background: white;
}
QTableWidget {
    background: white;
    alternate-background-color: #f9f9f9;
    gridline-color: #e0e0e0;
    selection-background-color: #0078d7;
    selection-color: white;
}
QTableWidget::item {
    padding: 4px;
}
QHeaderView::section {
    background-color: #e8e8e8;
    padding: 4px;
    border: 1px solid #ccc;
    font-weight: bold;
}
QPushButton {
    padding: 4px 12px;
    border: 1px solid #aaa;
    border-radius: 3px;
    background: #f0f0f0;
}
QPushButton:hover {
    background: #e0e0e0;
}
QPushButton:pressed {
    background: #d0d0d0;
}
QSlider::groove:horizontal {
    height: 6px;
    background: #ccc;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #0078d7;
    width: 14px;
    margin: -4px 0;
    border-radius: 7px;
}
QSlider::sub-page:horizontal {
    background: #0078d7;
    border-radius: 3px;
}
QComboBox {
    padding: 3px 8px;
    border: 1px solid #aaa;
    border-radius: 3px;
}
QListWidget {
    background: white;
    border: 1px solid #ccc;
}
QListWidget::item:selected {
    background: #0078d7;
    color: white;
}
QGroupBox {
    font-weight: bold;
    border: 1px solid #ccc;
    border-radius: 4px;
    margin-top: 8px;
    padding-top: 16px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}
"""


if __name__ == "__main__":
    main()
