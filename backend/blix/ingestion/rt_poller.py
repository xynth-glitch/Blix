"""Real-time VehiclePositions poller.

Every tick it fetches the provider's current vehicle positions and writes them to
two places:
  * `vehicle_positions_live`  — upserted latest-per-vehicle (hot path)
  * `vehicle_positions_history` — append-only (warehouse for future ETA/delay ML)

Warehousing from day one is deliberate: Delhi supplies only raw positions (no
predicted arrivals), so Blix must learn travel times from its own history.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

import structlog
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from blix.config import get_settings
from blix.db import session_scope
from blix.models import orm
from blix.models.canonical import VehiclePosition
from blix.providers import get_provider
from blix.providers.base import TransitProvider

log = structlog.get_logger(__name__)


def persist_positions(session: Session, positions: list[VehiclePosition]) -> int:
    if not positions:
        return 0

    history = [
        {
            "vehicle_id": p.vehicle_id,
            "trip_id": p.trip_id,
            "route_id": p.route_id,
            "lat": p.lat,
            "lon": p.lon,
            "bearing": p.bearing,
            "speed_mps": p.speed_mps,
            "observed_at": p.observed_at,
        }
        for p in positions
    ]
    session.bulk_insert_mappings(orm.VehiclePositionHistory, history)

    # Upsert latest-per-vehicle.
    for row in history:
        stmt = pg_insert(orm.VehiclePositionLive).values(**row)
        stmt = stmt.on_conflict_do_update(
            index_elements=[orm.VehiclePositionLive.vehicle_id],
            set_={
                "trip_id": stmt.excluded.trip_id,
                "route_id": stmt.excluded.route_id,
                "lat": stmt.excluded.lat,
                "lon": stmt.excluded.lon,
                "bearing": stmt.excluded.bearing,
                "speed_mps": stmt.excluded.speed_mps,
                "observed_at": stmt.excluded.observed_at,
            },
        )
        session.execute(stmt)
    return len(positions)


def poll_once(provider: TransitProvider | None = None) -> int:
    provider = provider or get_provider()
    now = datetime.now(tz=UTC)
    with session_scope() as session:
        status = session.get(orm.FeedStatus, "vehicle_positions") or orm.FeedStatus(
            feed="vehicle_positions"
        )
        status.last_attempt_at = now
        try:
            positions = provider.fetch_vehicle_positions()
            count = persist_positions(session, positions)
            status.last_success_at = now
            status.record_count = count
            status.last_error = None
            session.merge(status)
            log.info("rt.poll.ok", count=count)
            return count
        except Exception as exc:  # noqa: BLE001 — record and keep the loop alive
            status.last_error = str(exc)
            session.merge(status)
            log.error("rt.poll.error", error=str(exc))
            raise


def run_forever() -> None:
    settings = get_settings()
    provider = get_provider()
    if not provider.supports_realtime():
        log.warning("rt.poll.disabled", reason="no realtime key configured")
        return
    log.info("rt.poll.start", interval=settings.rt_poll_interval_seconds)
    while True:
        try:
            poll_once(provider)
        except Exception:  # noqa: BLE001 — already logged; don't kill the loop
            pass
        time.sleep(settings.rt_poll_interval_seconds)
