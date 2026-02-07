"""
SRT subtitle parser.

Parses .srt files into a list of LyricLine named tuples:
    (index, start_ms, end_ms, text)
"""

import re
from typing import NamedTuple


class LyricLine(NamedTuple):
    index: int
    start_ms: int
    end_ms: int
    text: str


_TIMESTAMP_RE = re.compile(
    r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})"
)
_LRC_TIMESTAMP_RE = re.compile(
    r"\[(\d{1,2}):(\d{2})(?:[.:](\d{1,3}))?\]"
)


def _parse_timestamp(ts: str) -> int:
    """Convert an SRT timestamp string to milliseconds."""
    m = _TIMESTAMP_RE.match(ts.strip())
    if not m:
        return 0
    hours, minutes, seconds, millis = m.groups()
    # Pad millis to 3 digits (some files use 1 or 2 digit fractional)
    millis = millis.ljust(3, "0")
    return (
        int(hours) * 3600000
        + int(minutes) * 60000
        + int(seconds) * 1000
        + int(millis)
    )


def parse_srt(text: str) -> list[LyricLine]:
    """
    Parse SRT (or LRC-style) formatted text into a list of LyricLine.

    Handles both \\r\\n and \\n line endings.
    """
    text = text.replace("\r\n", "\n").strip()
    if not text:
        return []

    blocks = re.split(r"\n\n+", text)
    lyrics: list[LyricLine] = []

    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 2:
            continue

        # First line: index (skip if not a number)
        try:
            idx = int(lines[0].strip())
        except ValueError:
            continue

        # Second line: timestamp range
        ts_line = lines[1].strip()
        parts = re.split(r"\s*-->\s*", ts_line)
        if len(parts) != 2:
            continue

        start_ms = _parse_timestamp(parts[0])
        end_ms = _parse_timestamp(parts[1])

        # Remaining lines: subtitle text
        subtitle_text = " ".join(l.strip() for l in lines[2:] if l.strip())
        # Strip basic HTML tags (e.g. <i>, <b>)
        subtitle_text = re.sub(r"<[^>]+>", "", subtitle_text)

        if subtitle_text:
            lyrics.append(LyricLine(idx, start_ms, end_ms, subtitle_text))

    if lyrics:
        return lyrics

    return _parse_lrc(text)


def _parse_lrc(text: str) -> list[LyricLine]:
    """
    Parse LRC-style timestamps: [mm:ss.xx]Lyric line.
    """
    entries: list[tuple[int, str]] = []
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        timestamps = list(_LRC_TIMESTAMP_RE.finditer(line))
        if not timestamps:
            continue
        lyric_text = _LRC_TIMESTAMP_RE.sub("", line).strip()
        for match in timestamps:
            minutes, seconds, millis = match.groups()
            millis = (millis or "0").ljust(3, "0")
            start_ms = (
                int(minutes) * 60000
                + int(seconds) * 1000
                + int(millis)
            )
            entries.append((start_ms, lyric_text))

    if not entries:
        return []

    entries.sort(key=lambda item: item[0])
    lyrics: list[LyricLine] = []
    for idx, (start_ms, lyric_text) in enumerate(entries, start=1):
        if idx < len(entries):
            end_ms = entries[idx][0]
        else:
            end_ms = start_ms + 5000
        if lyric_text:
            lyrics.append(LyricLine(idx, start_ms, end_ms, lyric_text))
    return lyrics


def parse_srt_file(filepath: str) -> list[LyricLine]:
    """Read and parse an SRT file."""
    encodings = ["utf-8-sig", "utf-8", "latin-1"]
    for enc in encodings:
        try:
            with open(filepath, "r", encoding=enc) as f:
                return parse_srt(f.read())
        except (UnicodeDecodeError, UnicodeError):
            continue
    return []


def get_lyric_at_position(lyrics: list[LyricLine], position_ms: int,
                          offset_ms: int = 0) -> tuple[int, str]:
    """
    Return (index_in_list, text) for the lyric active at position_ms.
    offset_ms is added to position_ms before lookup.
    Returns (-1, "") if no lyric is active.
    """
    adjusted = position_ms + offset_ms
    for i, line in enumerate(lyrics):
        if line.start_ms <= adjusted < line.end_ms:
            return i, line.text
    return -1, ""
