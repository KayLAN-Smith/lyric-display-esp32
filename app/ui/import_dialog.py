"""
Import dialog for adding new tracks to the library.

Lets the user pick an MP3 and an optional SRT file,
enter title/artist, then copies files into app storage.

The artist field uses an editable combo box with autocomplete
populated from previously entered artist names.
"""

import os
import shutil
import uuid

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QMessageBox, QComboBox, QCompleter,
)
from PySide6.QtCore import Qt

from settings.config import get_library_dir
from db.database import Database


class ImportDialog(QDialog):
    """Dialog for importing an MP3 + SRT pair."""

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Import Song")
        self.setMinimumWidth(500)

        self.mp3_path = ""
        self.srt_path = ""
        self.track_title = ""
        self.track_artist = ""

        # Result paths (after copy into library)
        self.stored_audio_path = ""
        self.stored_srt_path = ""

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # MP3 file
        layout.addWidget(QLabel("MP3 File (required):"))
        row = QHBoxLayout()
        self._mp3_edit = QLineEdit()
        self._mp3_edit.setReadOnly(True)
        row.addWidget(self._mp3_edit)
        btn = QPushButton("Browse...")
        btn.clicked.connect(self._browse_mp3)
        row.addWidget(btn)
        layout.addLayout(row)

        # SRT file
        layout.addWidget(QLabel("SRT Lyric File (optional):"))
        row = QHBoxLayout()
        self._srt_edit = QLineEdit()
        self._srt_edit.setReadOnly(True)
        row.addWidget(self._srt_edit)
        btn = QPushButton("Browse...")
        btn.clicked.connect(self._browse_srt)
        row.addWidget(btn)
        layout.addLayout(row)

        # Title
        layout.addWidget(QLabel("Title:"))
        self._title_edit = QLineEdit()
        layout.addWidget(self._title_edit)

        # Artist – editable combo box with autocomplete from existing artists
        layout.addWidget(QLabel("Artist (optional):"))
        self._artist_combo = QComboBox()
        self._artist_combo.setEditable(True)
        self._artist_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._artist_combo.lineEdit().setPlaceholderText("Start typing to see suggestions...")

        # Populate with existing artists from the database
        existing_artists = self.db.get_all_artists()
        self._artist_combo.addItem("")  # blank default
        self._artist_combo.addItems(existing_artists)

        # Set up case-insensitive completer
        completer = QCompleter(existing_artists, self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._artist_combo.setCompleter(completer)

        layout.addWidget(self._artist_combo)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok_btn = QPushButton("Import")
        ok_btn.clicked.connect(self._do_import)
        btn_row.addWidget(ok_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _browse_mp3(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select MP3 File", "", "Audio Files (*.mp3);;All Files (*)"
        )
        if path:
            self.mp3_path = path
            self._mp3_edit.setText(path)
            # Auto-fill title from filename
            if not self._title_edit.text():
                name = os.path.splitext(os.path.basename(path))[0]
                self._title_edit.setText(name)

    def _browse_srt(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select SRT File", "", "SRT Files (*.srt);;All Files (*)"
        )
        if path:
            self.srt_path = path
            self._srt_edit.setText(path)

    def _do_import(self):
        if not self.mp3_path:
            QMessageBox.warning(self, "Missing File", "Please select an MP3 file.")
            return
        title = self._title_edit.text().strip()
        if not title:
            QMessageBox.warning(self, "Missing Title", "Please enter a title.")
            return

        self.track_title = title
        self.track_artist = self._artist_combo.currentText().strip()

        # Copy files to library
        try:
            track_dir = os.path.join(get_library_dir(), uuid.uuid4().hex[:12])
            os.makedirs(track_dir, exist_ok=True)

            ext = os.path.splitext(self.mp3_path)[1]
            self.stored_audio_path = os.path.join(track_dir, f"audio{ext}")
            shutil.copy2(self.mp3_path, self.stored_audio_path)

            if self.srt_path:
                self.stored_srt_path = os.path.join(track_dir, "lyrics.srt")
                shutil.copy2(self.srt_path, self.stored_srt_path)
            else:
                self.stored_srt_path = ""
        except OSError as e:
            QMessageBox.critical(self, "Import Error", f"Failed to copy files:\n{e}")
            return

        self.accept()
