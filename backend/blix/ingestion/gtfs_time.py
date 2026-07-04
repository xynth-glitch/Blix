"""Helpers for GTFS time fields.

GTFS times may exceed 24:00:00 (a trip after midnight belongs to the prior
service day), so they are stored as seconds-after-midnight rather than clock time.
"""

from __future__ import annotations


def parse_gtfs_time(value: str | None) -> int | None:
    """Parse 'HH:MM:SS' (HH may be >= 24) into seconds-after-midnight."""
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    parts = value.split(":")
    if len(parts) != 3:
        return None
    try:
        h, m, s = (int(p) for p in parts)
    except ValueError:
        return None
    return h * 3600 + m * 60 + s


def format_gtfs_time(seconds: int | None) -> str | None:
    """Inverse of `parse_gtfs_time`."""
    if seconds is None:
        return None
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"
