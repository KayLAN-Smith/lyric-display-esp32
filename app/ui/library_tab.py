"""
All Songs tab – table of imported tracks with import, delete, and context menu.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QMenu, QAbstractItemView, QMessageBox,
    QLineEdit,
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QGuiApplication

import os


class LibraryTab(QWidget):
    """
    Displays all tracks in a sortable table.

    Signals:
        play_track(int)        - User wants to play track with given id.
        edit_offset(int)       - User wants to edit offset for track id.
        add_to_playlist(list[int])   - User wants to add track ids to a playlist.
    """

    play_track = Signal(int)
    edit_offset = Signal(int)
    add_to_playlist = Signal(list)

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Toolbar
        toolbar = QHBoxLayout()
        self._import_btn = QPushButton("Import Song")
        toolbar.addWidget(self._import_btn)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search...")
        self._search_edit.textChanged.connect(self._filter_table)
        toolbar.addWidget(self._search_edit)
        layout.addLayout(toolbar)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(["#", "Title", "Artist", "Duration", "Offset"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._context_menu)
        self._table.doubleClicked.connect(self._on_double_click)
        self._table.itemClicked.connect(self._on_single_click)
        self._table.verticalHeader().setVisible(False)
        layout.addWidget(self._table)

    @property
    def import_button(self) -> QPushButton:
        return self._import_btn

    def refresh(self):
        """Reload tracks from DB into the table."""
        tracks = self.db.get_all_tracks()
        self._table.setRowCount(len(tracks))
        for row, t in enumerate(tracks):
            id_item = QTableWidgetItem(str(t["id"]))
            id_item.setData(Qt.ItemDataRole.UserRole, t["id"])
            self._table.setItem(row, 0, id_item)
            self._table.setItem(row, 1, QTableWidgetItem(t["title"]))
            self._table.setItem(row, 2, QTableWidgetItem(t.get("artist", "")))
            self._table.setItem(row, 3, QTableWidgetItem(_fmt_duration(t.get("duration_ms", 0))))
            self._table.setItem(row, 4, QTableWidgetItem(f"{t.get('lyric_offset_ms', 0)} ms"))
        self._table.resizeColumnToContents(0)
        self._table.resizeColumnToContents(3)
        self._table.resizeColumnToContents(4)

    def _selected_track_id(self) -> int | None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        row = rows[0].row()
        item = self._table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None
 
    def _selected_track_ids(self) -> list[int]:
        ids: list[int] = []
        for row in self._table.selectionModel().selectedRows():
            item = self._table.item(row.row(), 0)
            if item:
                ids.append(item.data(Qt.ItemDataRole.UserRole))
        return ids

    def _on_double_click(self, index):
        tid = self._selected_track_id()
        if tid is not None:
            self.play_track.emit(tid)

    def _on_single_click(self, item):
        if QGuiApplication.keyboardModifiers() != Qt.KeyboardModifier.NoModifier:
            return
        ids = self._selected_track_ids()
        if len(ids) == 1:
            self.play_track.emit(ids[0])

    def _context_menu(self, pos):
        ids = self._selected_track_ids()
        if not ids:
            return
        menu = QMenu(self)
        menu.addAction("Play", lambda: self.play_track.emit(ids[0]))
        menu.addAction("Add to Playlist...", lambda: self.add_to_playlist.emit(ids))
        if len(ids) == 1:
            menu.addAction("Edit Lyric Offset...", lambda: self.edit_offset.emit(ids[0]))
        menu.addSeparator()
        menu.addAction("Delete", lambda: self._delete_tracks(ids))
        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _delete_tracks(self, track_ids: list[int]):
        if not track_ids:
            return
        reply = QMessageBox.question(
            self, "Delete Track",
            "Remove this track from the library?\n(Files will also be deleted.)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            for track_id in track_ids:
                track = self.db.delete_track(track_id)
                # Clean up files
                if track:
                    for key in ("audio_path", "srt_path"):
                        p = track.get(key, "")
                        if p and os.path.isfile(p):
                            try:
                                os.remove(p)
                            except OSError:
                                pass
                    # Remove directory if empty
                    if track.get("audio_path"):
                        d = os.path.dirname(track["audio_path"])
                        try:
                            os.rmdir(d)
                        except OSError:
                            pass
            self.refresh()

    def _filter_table(self, text: str):
        text = text.lower()
        for row in range(self._table.rowCount()):
            title_item = self._table.item(row, 1)
            artist_item = self._table.item(row, 2)
            title = title_item.text().lower() if title_item else ""
            artist = artist_item.text().lower() if artist_item else ""
            match = text in title or text in artist
            self._table.setRowHidden(row, not match)


def _fmt_duration(ms: int) -> str:
    if ms <= 0:
        return "--:--"
    total_s = ms // 1000
    m, s = divmod(total_s, 60)
    return f"{m}:{s:02d}"
