"""
Playlists tab – playlist list on the left, playlist contents on the right.
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QListWidget,
    QListWidgetItem, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QInputDialog, QMessageBox, QMenu, QLabel, QSplitter,
)
from PySide6.QtCore import Signal, Qt


class PlaylistsTab(QWidget):
    """
    Manages playlists: create, rename, delete, add/remove/reorder songs.

    Signals:
        play_track_in_playlist(int, int) - (playlist_id, track_id) start playback.
        play_playlist(int)               - Play all songs in playlist.
    """

    play_track_in_playlist = Signal(int, int)
    play_playlist = Signal(int)

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._current_playlist_id = None
        self._build_ui()
        self.refresh_playlists()

    def _build_ui(self):
        layout = QHBoxLayout(self)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Left panel: playlist list ────────────────────────────
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        left_layout.addWidget(QLabel("Playlists"))
        self._playlist_list = QListWidget()
        self._playlist_list.currentRowChanged.connect(self._on_playlist_selected)
        self._playlist_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._playlist_list.customContextMenuRequested.connect(self._playlist_context_menu)
        left_layout.addWidget(self._playlist_list)

        btn_row = QHBoxLayout()
        new_btn = QPushButton("New")
        new_btn.clicked.connect(self._create_playlist)
        btn_row.addWidget(new_btn)
        rename_btn = QPushButton("Rename")
        rename_btn.clicked.connect(self._rename_playlist)
        btn_row.addWidget(rename_btn)
        del_btn = QPushButton("Delete")
        del_btn.clicked.connect(self._delete_playlist)
        btn_row.addWidget(del_btn)
        left_layout.addLayout(btn_row)

        splitter.addWidget(left)

        # ── Right panel: playlist songs ──────────────────────────
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        header_row = QHBoxLayout()
        self._playlist_title = QLabel("Select a playlist")
        self._playlist_title.setStyleSheet("font-weight: bold; font-size: 14px;")
        header_row.addWidget(self._playlist_title)
        header_row.addStretch()
        play_all_btn = QPushButton("Play All")
        play_all_btn.clicked.connect(self._play_all)
        header_row.addWidget(play_all_btn)
        right_layout.addLayout(header_row)

        self._track_table = QTableWidget()
        self._track_table.setColumnCount(4)
        self._track_table.setHorizontalHeaderLabels(["#", "Title", "Artist", "Duration"])
        self._track_table.horizontalHeader().setStretchLastSection(True)
        self._track_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._track_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._track_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._track_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._track_table.verticalHeader().setVisible(False)
        self._track_table.doubleClicked.connect(self._on_track_double_click)
        self._track_table.itemClicked.connect(self._on_track_single_click)
        self._track_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._track_table.customContextMenuRequested.connect(self._track_context_menu)
        right_layout.addWidget(self._track_table)

        btn_row2 = QHBoxLayout()
        btn_row2.addStretch()
        up_btn = QPushButton("Move Up")
        up_btn.clicked.connect(self._move_up)
        btn_row2.addWidget(up_btn)
        down_btn = QPushButton("Move Down")
        down_btn.clicked.connect(self._move_down)
        btn_row2.addWidget(down_btn)
        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self._remove_track)
        btn_row2.addWidget(remove_btn)
        right_layout.addLayout(btn_row2)

        splitter.addWidget(right)
        splitter.setSizes([200, 500])
        layout.addWidget(splitter)

    # ── Playlist list management ─────────────────────────────────

    def refresh_playlists(self):
        self._playlist_list.clear()
        for pl in self.db.get_all_playlists():
            item = QListWidgetItem(pl["name"])
            item.setData(Qt.ItemDataRole.UserRole, pl["id"])
            self._playlist_list.addItem(item)

    def _selected_playlist_id(self) -> int | None:
        item = self._playlist_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _on_playlist_selected(self, row):
        pid = self._selected_playlist_id()
        self._current_playlist_id = pid
        if pid is not None:
            item = self._playlist_list.currentItem()
            self._playlist_title.setText(item.text() if item else "")
            self._refresh_tracks(pid)
        else:
            self._playlist_title.setText("Select a playlist")
            self._track_table.setRowCount(0)

    def _refresh_tracks(self, playlist_id: int):
        tracks = self.db.get_playlist_tracks(playlist_id)
        self._track_table.setRowCount(len(tracks))
        for row, t in enumerate(tracks):
            pos_item = QTableWidgetItem(str(row + 1))
            pos_item.setData(Qt.ItemDataRole.UserRole, t["id"])
            self._track_table.setItem(row, 0, pos_item)
            self._track_table.setItem(row, 1, QTableWidgetItem(t["title"]))
            self._track_table.setItem(row, 2, QTableWidgetItem(t.get("artist", "")))
            dur_ms = t.get("duration_ms", 0)
            self._track_table.setItem(row, 3, QTableWidgetItem(_fmt_dur(dur_ms)))
        self._track_table.resizeColumnToContents(0)
        self._track_table.resizeColumnToContents(3)

    def _create_playlist(self):
        name, ok = QInputDialog.getText(self, "New Playlist", "Playlist name:")
        if ok and name.strip():
            self.db.create_playlist(name.strip())
            self.refresh_playlists()

    def _rename_playlist(self):
        pid = self._selected_playlist_id()
        if pid is None:
            return
        item = self._playlist_list.currentItem()
        old_name = item.text() if item else ""
        name, ok = QInputDialog.getText(self, "Rename Playlist", "New name:", text=old_name)
        if ok and name.strip():
            self.db.rename_playlist(pid, name.strip())
            self.refresh_playlists()

    def _delete_playlist(self):
        pid = self._selected_playlist_id()
        if pid is None:
            return
        reply = QMessageBox.question(
            self, "Delete Playlist", "Are you sure?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.db.delete_playlist(pid)
            self.refresh_playlists()
            self._track_table.setRowCount(0)
            self._playlist_title.setText("Select a playlist")

    def _playlist_context_menu(self, pos):
        pid = self._selected_playlist_id()
        if pid is None:
            return
        menu = QMenu(self)
        menu.addAction("Play All", self._play_all)
        menu.addAction("Rename", self._rename_playlist)
        menu.addAction("Delete", self._delete_playlist)
        menu.exec(self._playlist_list.viewport().mapToGlobal(pos))

    # ── Track management in playlist ─────────────────────────────

    def _selected_track_row(self) -> int:
        rows = self._track_table.selectionModel().selectedRows()
        return rows[0].row() if rows else -1

    def _selected_track_id(self) -> int | None:
        row = self._selected_track_row()
        if row < 0:
            return None
        item = self._track_table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _on_track_double_click(self, index):
        pid = self._current_playlist_id
        tid = self._selected_track_id()
        if pid is not None and tid is not None:
            self.play_track_in_playlist.emit(pid, tid)

    def _on_track_single_click(self, item):
        pid = self._current_playlist_id
        tid = self._selected_track_id()
        if pid is not None and tid is not None:
            self.play_track_in_playlist.emit(pid, tid)

    def _track_context_menu(self, pos):
        tid = self._selected_track_id()
        pid = self._current_playlist_id
        if tid is None or pid is None:
            return
        menu = QMenu(self)
        menu.addAction("Play", lambda: self.play_track_in_playlist.emit(pid, tid))
        menu.addAction("Remove from Playlist", self._remove_track)
        menu.exec(self._track_table.viewport().mapToGlobal(pos))

    def _remove_track(self):
        pid = self._current_playlist_id
        tid = self._selected_track_id()
        if pid is not None and tid is not None:
            self.db.remove_track_from_playlist(pid, tid)
            self._refresh_tracks(pid)

    def _move_up(self):
        row = self._selected_track_row()
        pid = self._current_playlist_id
        if pid is not None and row > 0:
            self.db.move_track_in_playlist(pid, row, row - 1)
            self._refresh_tracks(pid)
            self._track_table.selectRow(row - 1)

    def _move_down(self):
        row = self._selected_track_row()
        pid = self._current_playlist_id
        if pid is not None and 0 <= row < self._track_table.rowCount() - 1:
            self.db.move_track_in_playlist(pid, row, row + 1)
            self._refresh_tracks(pid)
            self._track_table.selectRow(row + 1)

    def _play_all(self):
        pid = self._current_playlist_id
        if pid is not None:
            self.play_playlist.emit(pid)

    # ── Public helpers ───────────────────────────────────────────

    def add_track_to_current_or_choose(self, track_id: int):
        """Add track(s) to a playlist. If no playlist selected, ask the user to pick one."""
        track_ids = [track_id]
        self.add_tracks_to_current_or_choose(track_ids)

    def add_tracks_to_current_or_choose(self, track_ids: list[int]):
        """Add multiple tracks to a playlist. If no playlist selected, ask the user to pick one."""
        playlists = self.db.get_all_playlists()
        if not playlists:
            QMessageBox.information(self, "No Playlists", "Create a playlist first.")
            return

        names = [p["name"] for p in playlists]
        # If a playlist is selected, default to it
        default_idx = 0
        if self._current_playlist_id:
            for i, p in enumerate(playlists):
                if p["id"] == self._current_playlist_id:
                    default_idx = i
                    break

        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getItem(
            self, "Add to Playlist", "Choose playlist:", names, default_idx, False
        )
        if ok and name:
            for p in playlists:
                if p["name"] == name:
                    for track_id in track_ids:
                        self.db.add_track_to_playlist(p["id"], track_id)
                    if self._current_playlist_id == p["id"]:
                        self._refresh_tracks(p["id"])
                    break


def _fmt_dur(ms: int) -> str:
    if ms <= 0:
        return "--:--"
    total_s = ms // 1000
    m, s = divmod(total_s, 60)
    return f"{m}:{s:02d}"
