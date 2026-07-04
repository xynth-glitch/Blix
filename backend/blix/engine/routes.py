"""Route lookup and route-details assembly."""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from blix.engine.freshness import classify
from blix.models import orm
from blix.models.canonical import (
    Route,
    RouteDetails,
    RouteStop,
    RouteType,
    Stop,
    VehiclePosition,
)


def _route_type(value: int) -> RouteType:
    try:
        return RouteType(value)
    except ValueError:
        return RouteType.BUS


def _to_route(r: orm.Route) -> Route:
    return Route(
        id=r.id,
        agency_id=r.agency_id,
        short_name=r.short_name,
        long_name=r.long_name,
        route_type=_route_type(r.route_type),
    )


def search_routes(session: Session, query: str, limit: int = 20) -> list[Route]:
    """Search routes by short/long name (bus 'number')."""
    q = f"%{query.strip()}%"
    stmt = (
        select(orm.Route)
        .where(or_(orm.Route.short_name.ilike(q), orm.Route.long_name.ilike(q)))
        .limit(limit)
    )
    return [_to_route(r) for r in session.execute(stmt).scalars()]


def get_route(session: Session, route_id: str) -> Route | None:
    r = session.get(orm.Route, route_id)
    return _to_route(r) if r else None


def _representative_trip_id(session: Session, route_id: str) -> str | None:
    """Pick the trip with the most stops as the canonical stop timeline."""
    stmt = (
        select(orm.StopTime.trip_id, func.count().label("n"))
        .join(orm.Trip, orm.Trip.id == orm.StopTime.trip_id)
        .where(orm.Trip.route_id == route_id)
        .group_by(orm.StopTime.trip_id)
        .order_by(func.count().desc())
        .limit(1)
    )
    row = session.execute(stmt).first()
    return row[0] if row else None


def _live_vehicles(session: Session, route_id: str) -> list[VehiclePosition]:
    stmt = select(orm.VehiclePositionLive).where(orm.VehiclePositionLive.route_id == route_id)
    out: list[VehiclePosition] = []
    for v in session.execute(stmt).scalars():
        out.append(
            VehiclePosition(
                vehicle_id=v.vehicle_id,
                trip_id=v.trip_id,
                route_id=v.route_id,
                lat=v.lat,
                lon=v.lon,
                bearing=v.bearing,
                speed_mps=v.speed_mps,
                observed_at=v.observed_at,
                freshness=classify(v.observed_at),
            )
        )
    return out


def route_details(session: Session, route_id: str) -> RouteDetails | None:
    route = get_route(session, route_id)
    if route is None:
        return None

    trip_id = _representative_trip_id(session, route_id)
    stops: list[RouteStop] = []
    if trip_id is not None:
        stmt = (
            select(orm.StopTime, orm.Stop)
            .join(orm.Stop, orm.Stop.id == orm.StopTime.stop_id)
            .where(orm.StopTime.trip_id == trip_id)
            .order_by(orm.StopTime.stop_sequence)
        )
        for st, stop in session.execute(stmt):
            stops.append(
                RouteStop(
                    stop=Stop(
                        id=stop.id,
                        code=stop.code,
                        name=stop.name,
                        lat=stop.lat,
                        lon=stop.lon,
                        zone_id=stop.zone_id,
                    ),
                    stop_sequence=st.stop_sequence,
                    scheduled_arrival_s=st.arrival_s,
                )
            )

    return RouteDetails(route=route, stops=stops, live_vehicles=_live_vehicles(session, route_id))
