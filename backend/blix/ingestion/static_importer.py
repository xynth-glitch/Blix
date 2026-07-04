"""Import a static GTFS bundle into the normalized Postgres schema.

Streams the large files (stop_times ~3.7M rows, fares ~2.3M rows for Delhi) in
chunked bulk inserts so memory stays bounded. Import is idempotent: it truncates
the static tables and reloads, wrapped in a transaction.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

from blix.ingestion.gtfs_time import parse_gtfs_time
from blix.models import orm

log = structlog.get_logger(__name__)

CHUNK = 5_000

# Static tables in FK-safe truncation order.
_STATIC_TABLES = [
    "fares",
    "stop_times",
    "trips",
    "routes",
    "stops",
    "agencies",
]


def _rows(path: Path) -> Iterator[dict[str, str]]:
    if not path.exists():
        log.warning("gtfs.file.missing", file=path.name)
        return
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield {(k.strip() if k else k): (v.strip() if v else v) for k, v in row.items()}


def _bulk(session: Session, model: type[Any], mappings: list[dict[str, Any]]) -> None:
    if mappings:
        session.bulk_insert_mappings(model, mappings)


def import_gtfs_dir(session: Session, gtfs_dir: Path) -> dict[str, int]:
    """Import an extracted GTFS directory. Returns per-table row counts."""
    counts: dict[str, int] = {}

    log.info("gtfs.import.begin", dir=str(gtfs_dir))
    # Truncate existing static data (real-time tables are untouched).
    session.execute(text("TRUNCATE {} RESTART IDENTITY CASCADE".format(", ".join(_STATIC_TABLES))))

    counts["agencies"] = _import_agencies(session, gtfs_dir / "agency.txt")
    counts["stops"] = _import_stops(session, gtfs_dir / "stops.txt")
    counts["routes"] = _import_routes(session, gtfs_dir / "routes.txt")
    counts["trips"] = _import_trips(session, gtfs_dir / "trips.txt")
    counts["stop_times"] = _import_stop_times(session, gtfs_dir / "stop_times.txt")
    counts["fares"] = _import_fares(session, gtfs_dir)

    total = sum(counts.values())
    _record_status(session, "static", total)
    log.info("gtfs.import.done", counts=counts)
    return counts


def _import_agencies(session: Session, path: Path) -> int:
    rows = [
        {
            "id": r.get("agency_id") or "default",
            "name": r.get("agency_name") or "",
            "url": r.get("agency_url") or None,
            "timezone": r.get("agency_timezone") or "Asia/Kolkata",
        }
        for r in _rows(path)
    ]
    _bulk(session, orm.Agency, rows)
    return len(rows)


def _import_stops(session: Session, path: Path) -> int:
    buf: list[dict[str, Any]] = []
    n = 0
    for r in _rows(path):
        try:
            lat = float(r["stop_lat"])
            lon = float(r["stop_lon"])
        except (KeyError, ValueError):
            continue
        buf.append(
            {
                "id": r.get("stop_id"),
                "code": r.get("stop_code") or None,
                "name": r.get("stop_name") or "",
                "lat": lat,
                "lon": lon,
                "zone_id": r.get("zone_id") or None,
                "geom": f"SRID=4326;POINT({lon} {lat})",
            }
        )
        if len(buf) >= CHUNK:
            _bulk(session, orm.Stop, buf)
            n += len(buf)
            buf.clear()
    _bulk(session, orm.Stop, buf)
    return n + len(buf)


def _import_routes(session: Session, path: Path) -> int:
    rows = []
    for r in _rows(path):
        try:
            rtype = int(r.get("route_type") or 3)
        except ValueError:
            rtype = 3
        rows.append(
            {
                "id": r.get("route_id"),
                "agency_id": r.get("agency_id") or "default",
                "short_name": r.get("route_short_name") or None,
                "long_name": r.get("route_long_name") or None,
                "route_type": rtype,
            }
        )
    _bulk(session, orm.Route, rows)
    return len(rows)


def _import_trips(session: Session, path: Path) -> int:
    buf: list[dict[str, Any]] = []
    n = 0
    for r in _rows(path):
        buf.append(
            {
                "id": r.get("trip_id"),
                "route_id": r.get("route_id"),
                "service_id": r.get("service_id") or "",
                "shape_id": r.get("shape_id") or None,
                "headsign": r.get("trip_headsign") or None,
            }
        )
        if len(buf) >= CHUNK:
            _bulk(session, orm.Trip, buf)
            n += len(buf)
            buf.clear()
    _bulk(session, orm.Trip, buf)
    return n + len(buf)


def _import_stop_times(session: Session, path: Path) -> int:
    buf: list[dict[str, Any]] = []
    n = 0
    for r in _rows(path):
        try:
            seq = int(r["stop_sequence"])
        except (KeyError, ValueError):
            continue
        buf.append(
            {
                "trip_id": r.get("trip_id"),
                "stop_id": r.get("stop_id"),
                "stop_sequence": seq,
                "arrival_s": parse_gtfs_time(r.get("arrival_time")),
                "departure_s": parse_gtfs_time(r.get("departure_time")),
            }
        )
        if len(buf) >= CHUNK:
            _bulk(session, orm.StopTime, buf)
            n += len(buf)
            buf.clear()
    _bulk(session, orm.StopTime, buf)
    return n + len(buf)


def _import_fares(session: Session, gtfs_dir: Path) -> int:
    """Join fare_rules (route/origin/destination) with fare_attributes (price)."""
    attrs_path = gtfs_dir / "fare_attributes.txt"
    rules_path = gtfs_dir / "fare_rules.txt"
    if not attrs_path.exists() or not rules_path.exists():
        log.warning("gtfs.fares.missing")
        return 0

    prices: dict[str, tuple[float, str]] = {}
    for r in _rows(attrs_path):
        fid = r.get("fare_id")
        if not fid:
            continue
        try:
            price = float(r.get("price") or 0)
        except ValueError:
            continue
        prices[fid] = (price, r.get("currency_type") or "INR")

    buf: list[dict[str, Any]] = []
    n = 0
    for r in _rows(rules_path):
        fid = r.get("fare_id")
        if not fid or fid not in prices:
            continue
        price, currency = prices[fid]
        buf.append(
            {
                "route_id": r.get("route_id") or None,
                "origin_zone_id": r.get("origin_id") or "",
                "destination_zone_id": r.get("destination_id") or "",
                "price": price,
                "currency": currency,
            }
        )
        if len(buf) >= CHUNK:
            _bulk(session, orm.Fare, buf)
            n += len(buf)
            buf.clear()
    _bulk(session, orm.Fare, buf)
    return n + len(buf)


def _record_status(session: Session, feed: str, count: int) -> None:
    now = datetime.now(tz=UTC)
    existing = session.get(orm.FeedStatus, feed)
    if existing is None:
        session.add(
            orm.FeedStatus(
                feed=feed, last_success_at=now, last_attempt_at=now, record_count=count
            )
        )
    else:
        existing.last_success_at = now
        existing.last_attempt_at = now
        existing.record_count = count
        existing.last_error = None
