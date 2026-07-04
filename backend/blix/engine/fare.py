"""Fare lookup.

Delhi OTD ships an origin->destination fare matrix (fare_rules + fare_attributes),
so base fares are a direct lookup by zone. Official schemes not encoded in the feed
(AC vs non-AC premiums, women's free-travel "pink ticket") should be layered on top
here as they are modeled — this module is the single place fares are resolved.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from blix.models import orm
from blix.models.canonical import Fare


def fare_between(
    session: Session,
    origin_zone_id: str,
    destination_zone_id: str,
    route_id: str | None = None,
) -> Fare | None:
    """Cheapest fare for an origin->destination zone pair (optionally per route)."""
    stmt = select(orm.Fare).where(
        orm.Fare.origin_zone_id == origin_zone_id,
        orm.Fare.destination_zone_id == destination_zone_id,
    )
    if route_id is not None:
        stmt = stmt.where(orm.Fare.route_id == route_id)
    stmt = stmt.order_by(orm.Fare.price.asc()).limit(1)

    row = session.execute(stmt).scalars().first()
    if row is None:
        return None
    return Fare(
        route_id=row.route_id,
        origin_zone_id=row.origin_zone_id,
        destination_zone_id=row.destination_zone_id,
        price=row.price,
        currency=row.currency,
    )


def fare_between_stops(
    session: Session, origin_stop_id: str, destination_stop_id: str
) -> Fare | None:
    """Resolve stop ids to zones, then look up the fare."""
    o = session.get(orm.Stop, origin_stop_id)
    d = session.get(orm.Stop, destination_stop_id)
    if o is None or d is None or o.zone_id is None or d.zone_id is None:
        return None
    return fare_between(session, o.zone_id, d.zone_id)
