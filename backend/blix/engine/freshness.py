"""Freshness classification for real-time-derived values.

Centralized so every feature labels liveness identically. Blix must never present
stale or scheduled data as live.
"""

from __future__ import annotations

from datetime import UTC, datetime

from blix.config import get_settings
from blix.models.canonical import Freshness


def classify(observed_at: datetime | None, now: datetime | None = None) -> Freshness:
    if observed_at is None:
        return Freshness.SCHEDULED
    now = now or datetime.now(tz=UTC)
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=UTC)
    age = (now - observed_at).total_seconds()
    if age <= get_settings().rt_stale_after_seconds:
        return Freshness.LIVE
    return Freshness.STALE
