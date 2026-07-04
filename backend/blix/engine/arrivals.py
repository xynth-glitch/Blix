"""Arrivals board for a stop.

IMPORTANT honesty constraint: the Delhi static feed's stop_times are explicitly
"a rough estimate assuming constant speed", and the real-time feed provides only
vehicle positions (no predicted arrivals). Until the map-matching ETA service
lands, arrivals here are labeled SCHEDULED — never LIVE. This encodes the core
principle that Blix must not present schedule guesses as real-time truth.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from blix.models import orm
from blix.models.canonical import Freshness, StopArrival

_IST = ZoneInfo("Asia/Kolkata")
_DAY = 86_400


def _seconds_after_midnight(now: datetime) -> int:
    local = now.astimezone(_IST)
    return local.hour * 3600 + local.minute * 60 + local.second


def stop_arrivals(
    session: Session,
    stop_id: str,
    now: datetime | None = None,
    limit: int = 10,
    window_seconds: int = 3 * 3600,
) -> list[StopArrival]:
    now = now or datetime.now(tz=UTC)
    start = _seconds_after_midnight(now)
    end = start + window_seconds

    stmt = (
        select(orm.StopTime, orm.Trip, orm.Route)
        .join(orm.Trip, orm.Trip.id == orm.StopTime.trip_id)
        .join(orm.Route, orm.Route.id == orm.Trip.route_id)
        .where(
            orm.StopTime.stop_id == stop_id,
            orm.StopTime.arrival_s.is_not(None),
            orm.StopTime.arrival_s >= start,
            orm.StopTime.arrival_s <= end,
        )
        .order_by(orm.StopTime.arrival_s)
        .limit(limit)
    )

    out: list[StopArrival] = []
    for st, trip, route in session.execute(stmt):
        eta = st.arrival_s - start
        if eta < 0:
            eta += _DAY
        out.append(
            StopArrival(
                route_id=route.id,
                route_name=route.short_name or route.long_name or route.id,
                trip_id=trip.id,
                headsign=trip.headsign,
                eta_seconds=eta,
                freshness=Freshness.SCHEDULED,
            )
        )
    return out
