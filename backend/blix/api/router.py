"""HTTP API — a thin layer over the deterministic engine.

Every response that carries a real-time-derived value also carries its freshness,
so clients (and the future AI layer) can never mistake scheduled data for live.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from blix import engine
from blix.db import get_session
from blix.models import orm
from blix.models.canonical import (
    Fare,
    NearbyStop,
    Route,
    RouteDetails,
    StopArrival,
)

router = APIRouter(prefix="/api")


@router.get("/stops/nearby", response_model=list[NearbyStop], tags=["stops"])
def get_nearby_stops(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius_m: int | None = Query(None, ge=1, le=3000),
    limit: int = Query(20, ge=1, le=100),
    session: Session = Depends(get_session),
) -> list[NearbyStop]:
    return engine.nearby_stops(session, lat, lon, radius_m, limit)


@router.get("/stops/{stop_id}/arrivals", response_model=list[StopArrival], tags=["stops"])
def get_stop_arrivals(
    stop_id: str,
    limit: int = Query(10, ge=1, le=50),
    session: Session = Depends(get_session),
) -> list[StopArrival]:
    if session.get(orm.Stop, stop_id) is None:
        raise HTTPException(status_code=404, detail="Stop not found")
    return engine.stop_arrivals(session, stop_id, now=datetime.now(tz=UTC), limit=limit)


@router.get("/routes/search", response_model=list[Route], tags=["routes"])
def search_routes(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    session: Session = Depends(get_session),
) -> list[Route]:
    return engine.search_routes(session, q, limit)


@router.get("/routes/{route_id}", response_model=RouteDetails, tags=["routes"])
def get_route_details(
    route_id: str,
    session: Session = Depends(get_session),
) -> RouteDetails:
    details = engine.route_details(session, route_id)
    if details is None:
        raise HTTPException(status_code=404, detail="Route not found")
    return details


@router.get("/fares", response_model=Fare, tags=["fares"])
def get_fare(
    origin_stop: str | None = Query(None),
    destination_stop: str | None = Query(None),
    origin_zone: str | None = Query(None),
    destination_zone: str | None = Query(None),
    session: Session = Depends(get_session),
) -> Fare:
    if origin_stop and destination_stop:
        fare = engine.fare_between_stops(session, origin_stop, destination_stop)
    elif origin_zone and destination_zone:
        fare = engine.fare_between(session, origin_zone, destination_zone)
    else:
        raise HTTPException(
            status_code=400,
            detail="Provide origin_stop+destination_stop or origin_zone+destination_zone",
        )
    if fare is None:
        raise HTTPException(status_code=404, detail="No fare found for this pair")
    return fare


@router.get("/feeds/status", tags=["system"])
def feed_status(session: Session = Depends(get_session)) -> list[dict[str, object]]:
    rows = session.execute(select(orm.FeedStatus)).scalars()
    return [
        {
            "feed": r.feed,
            "last_success_at": r.last_success_at,
            "last_attempt_at": r.last_attempt_at,
            "record_count": r.record_count,
            "last_error": r.last_error,
        }
        for r in rows
    ]
