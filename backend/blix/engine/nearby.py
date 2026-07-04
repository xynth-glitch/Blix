"""Nearby-stops queries backed by PostGIS.

'Nearby buses' is deliberately modeled as *arrivals at nearby stops* (robust even
when real-time coverage is partial) rather than 'vehicles physically near me'
(which looks broken with sparse GPS). See the Phase 0 doc, feature 3.3.
"""

from __future__ import annotations

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from blix.config import get_settings
from blix.models.canonical import NearbyStop, Stop

_NEARBY_SQL = text(
    """
    SELECT id, code, name, lat, lon, zone_id,
           ST_Distance(geom, ST_MakePoint(:lon, :lat)::geography) AS distance_m
    FROM stops
    WHERE ST_DWithin(geom, ST_MakePoint(:lon, :lat)::geography, :radius)
    ORDER BY distance_m ASC
    LIMIT :limit
    """
).bindparams(
    bindparam("lat"), bindparam("lon"), bindparam("radius"), bindparam("limit")
)


def nearby_stops(
    session: Session,
    lat: float,
    lon: float,
    radius_m: int | None = None,
    limit: int = 20,
) -> list[NearbyStop]:
    settings = get_settings()
    radius = min(radius_m or settings.nearby_default_radius_m, settings.nearby_max_radius_m)
    rows = session.execute(
        _NEARBY_SQL, {"lat": lat, "lon": lon, "radius": radius, "limit": limit}
    ).mappings()
    return [
        NearbyStop(
            stop=Stop(
                id=r["id"],
                code=r["code"],
                name=r["name"],
                lat=r["lat"],
                lon=r["lon"],
                zone_id=r["zone_id"],
            ),
            distance_m=round(r["distance_m"], 1),
        )
        for r in rows
    ]
