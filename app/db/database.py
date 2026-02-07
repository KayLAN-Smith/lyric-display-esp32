"""
SQLite database layer for the Lyric Display app.

Tables: tracks, playlists, playlist_tracks, settings.
"""

import sqlite3
import os
import threading
from datetime import datetime
from typing import Optional


class Database:
    """Thread-safe SQLite wrapper for the Lyric Display app."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA foreign_keys = ON")
        return self._local.conn

    def _init_db(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS tracks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT    NOT NULL,
                artist      TEXT    DEFAULT '',
                duration_ms INTEGER DEFAULT 0,
                audio_path  TEXT    NOT NULL,
                srt_path    TEXT    DEFAULT '',
                lyric_offset_ms INTEGER DEFAULT 0,
                added_date  TEXT    DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS playlists (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                name         TEXT    NOT NULL,
                created_date TEXT    DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS playlist_tracks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                playlist_id INTEGER NOT NULL,
                track_id    INTEGER NOT NULL,
                position    INTEGER NOT NULL,
                FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,
                FOREIGN KEY (track_id)    REFERENCES tracks(id)    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
        """)
        conn.commit()

    # ── Track CRUD ───────────────────────────────────────────────

    def add_track(self, title: str, artist: str, duration_ms: int,
                  audio_path: str, srt_path: str) -> int:
        conn = self._get_conn()
        cur = conn.execute(
            "INSERT INTO tracks (title, artist, duration_ms, audio_path, srt_path) "
            "VALUES (?, ?, ?, ?, ?)",
            (title, artist, duration_ms, audio_path, srt_path),
        )
        conn.commit()
        return cur.lastrowid

    def get_all_tracks(self) -> list[dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM tracks ORDER BY added_date DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_track(self, track_id: int) -> Optional[dict]:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM tracks WHERE id = ?", (track_id,)).fetchone()
        return dict(row) if row else None

    def update_track(self, track_id: int, **kwargs):
        if not kwargs:
            return
        conn = self._get_conn()
        cols = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [track_id]
        conn.execute(f"UPDATE tracks SET {cols} WHERE id = ?", vals)
        conn.commit()

    def delete_track(self, track_id: int):
        conn = self._get_conn()
        track = self.get_track(track_id)
        conn.execute("DELETE FROM tracks WHERE id = ?", (track_id,))
        conn.execute("DELETE FROM playlist_tracks WHERE track_id = ?", (track_id,))
        conn.commit()
        return track

    def set_track_offset(self, track_id: int, offset_ms: int):
        self.update_track(track_id, lyric_offset_ms=offset_ms)

    def get_track_offset(self, track_id: int) -> int:
        t = self.get_track(track_id)
        return t["lyric_offset_ms"] if t else 0

    # ── Playlist CRUD ────────────────────────────────────────────

    def create_playlist(self, name: str) -> int:
        conn = self._get_conn()
        cur = conn.execute("INSERT INTO playlists (name) VALUES (?)", (name,))
        conn.commit()
        return cur.lastrowid

    def get_all_playlists(self) -> list[dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM playlists ORDER BY created_date DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def rename_playlist(self, playlist_id: int, name: str):
        conn = self._get_conn()
        conn.execute("UPDATE playlists SET name = ? WHERE id = ?", (name, playlist_id))
        conn.commit()

    def delete_playlist(self, playlist_id: int):
        conn = self._get_conn()
        conn.execute("DELETE FROM playlist_tracks WHERE playlist_id = ?", (playlist_id,))
        conn.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,))
        conn.commit()

    # ── Playlist track management ────────────────────────────────

    def get_playlist_tracks(self, playlist_id: int) -> list[dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT t.*, pt.position FROM playlist_tracks pt "
            "JOIN tracks t ON t.id = pt.track_id "
            "WHERE pt.playlist_id = ? ORDER BY pt.position",
            (playlist_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def add_track_to_playlist(self, playlist_id: int, track_id: int):
        conn = self._get_conn()
        row = conn.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 AS next_pos "
            "FROM playlist_tracks WHERE playlist_id = ?",
            (playlist_id,),
        ).fetchone()
        next_pos = row["next_pos"]
        conn.execute(
            "INSERT INTO playlist_tracks (playlist_id, track_id, position) VALUES (?, ?, ?)",
            (playlist_id, track_id, next_pos),
        )
        conn.commit()

    def remove_track_from_playlist(self, playlist_id: int, track_id: int):
        conn = self._get_conn()
        conn.execute(
            "DELETE FROM playlist_tracks WHERE playlist_id = ? AND track_id = ?",
            (playlist_id, track_id),
        )
        self._reorder_playlist(playlist_id)
        conn.commit()

    def move_track_in_playlist(self, playlist_id: int, old_pos: int, new_pos: int):
        conn = self._get_conn()
        tracks = self.get_playlist_tracks(playlist_id)
        if old_pos < 0 or old_pos >= len(tracks) or new_pos < 0 or new_pos >= len(tracks):
            return
        ids = [t["id"] for t in tracks]
        item = ids.pop(old_pos)
        ids.insert(new_pos, item)
        for i, tid in enumerate(ids):
            conn.execute(
                "UPDATE playlist_tracks SET position = ? "
                "WHERE playlist_id = ? AND track_id = ?",
                (i, playlist_id, tid),
            )
        conn.commit()

    def _reorder_playlist(self, playlist_id: int):
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT id FROM playlist_tracks WHERE playlist_id = ? ORDER BY position",
            (playlist_id,),
        ).fetchall()
        for i, row in enumerate(rows):
            conn.execute(
                "UPDATE playlist_tracks SET position = ? WHERE id = ?",
                (i, row["id"]),
            )

    # ── Artist helpers ────────────────────────────────────────────

    def get_all_artists(self) -> list[str]:
        """Return a sorted list of distinct non-empty artist names."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT DISTINCT artist FROM tracks WHERE artist != '' ORDER BY artist"
        ).fetchall()
        return [r["artist"] for r in rows]

    # ── Settings ─────────────────────────────────────────────────

    def get_setting(self, key: str, default: str = "") -> str:
        conn = self._get_conn()
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str):
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )
        conn.commit()
