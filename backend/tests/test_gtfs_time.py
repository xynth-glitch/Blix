from blix.ingestion.gtfs_time import format_gtfs_time, parse_gtfs_time


def test_parse_basic():
    assert parse_gtfs_time("00:00:00") == 0
    assert parse_gtfs_time("01:02:03") == 3723
    assert parse_gtfs_time("12:30:00") == 45000


def test_parse_after_midnight():
    # GTFS allows hours >= 24 for trips crossing midnight.
    assert parse_gtfs_time("25:30:00") == 25 * 3600 + 1800


def test_parse_invalid():
    assert parse_gtfs_time(None) is None
    assert parse_gtfs_time("") is None
    assert parse_gtfs_time("   ") is None
    assert parse_gtfs_time("bad") is None
    assert parse_gtfs_time("1:2") is None


def test_roundtrip():
    for s in ("00:00:00", "09:15:45", "26:00:00"):
        assert format_gtfs_time(parse_gtfs_time(s)) == s
