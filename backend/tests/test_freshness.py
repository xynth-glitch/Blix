from datetime import UTC, datetime, timedelta

from blix.engine.freshness import classify
from blix.models.canonical import Freshness


def test_none_is_scheduled():
    assert classify(None) is Freshness.SCHEDULED


def test_recent_is_live():
    now = datetime.now(tz=UTC)
    assert classify(now - timedelta(seconds=5), now=now) is Freshness.LIVE


def test_old_is_stale():
    now = datetime.now(tz=UTC)
    assert classify(now - timedelta(minutes=10), now=now) is Freshness.STALE


def test_naive_datetime_assumed_utc():
    now = datetime.now(tz=UTC)
    naive = (now - timedelta(seconds=5)).replace(tzinfo=None)
    assert classify(naive, now=now) is Freshness.LIVE
