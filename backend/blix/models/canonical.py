"""Canonical, provider-agnostic transit model.

Every provider (Delhi OTD today; other cities/modes later) normalizes its data
into these types, so the transport engine never depends on a specific city or
feed format. The schema deliberately mirrors GTFS, the de-facto standard.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum, StrEnum

from pydantic import BaseModel, Field


class RouteType(int, Enum):
    """Subset of GTFS route_type values relevant to Blix."""

    TRAM = 0
    METRO = 1
    RAIL = 2
    BUS = 3
    FERRY = 4


class Freshness(StrEnum):
    """How trustworthy a real-time-derived value is.

    This is first-class in Blix: the UI and AI must never present SCHEDULED or
    STALE data as if it were LIVE.
    """

    LIVE = "live"          # fresh real-time observation
    STALE = "stale"        # real-time seen, but older than the staleness window
    SCHEDULED = "scheduled"  # no real-time; derived from the timetable
    UNKNOWN = "unknown"    # no basis for an estimate


class Agency(BaseModel):
    id: str
    name: str
    url: str | None = None
    timezone: str = "Asia/Kolkata"


class Stop(BaseModel):
    id: str
    code: str | None = None
    name: str
    lat: float
    lon: float
    zone_id: str | None = None


class Route(BaseModel):
    id: str
    agency_id: str
    short_name: str | None = None
    long_name: str | None = None
    route_type: RouteType = RouteType.BUS

    @property
    def display_name(self) -> str:
        return self.short_name or self.long_name or self.id


class StopTime(BaseModel):
    trip_id: str
    stop_id: str
    stop_sequence: int
    # GTFS times can exceed 24:00:00; stored as seconds-after-midnight.
    arrival_s: int | None = None
    departure_s: int | None = None


class Trip(BaseModel):
    id: str
    route_id: str
    service_id: str
    shape_id: str | None = None
    headsign: str | None = None


class Fare(BaseModel):
    """A single origin->destination fare observation."""

    route_id: str | None = None
    origin_zone_id: str
    destination_zone_id: str
    price: float
    currency: str = "INR"


class VehiclePosition(BaseModel):
    """A single real-time vehicle observation (from GTFS-RT VehiclePositions)."""

    vehicle_id: str
    trip_id: str | None = None
    route_id: str | None = None
    lat: float
    lon: float
    bearing: float | None = None
    speed_mps: float | None = None
    observed_at: datetime
    freshness: Freshness = Freshness.LIVE


class NearbyStop(BaseModel):
    stop: Stop
    distance_m: float = Field(..., description="Great-circle distance from query point")


class StopArrival(BaseModel):
    """A predicted (or scheduled) arrival of a route at a stop."""

    route_id: str
    route_name: str
    trip_id: str | None = None
    headsign: str | None = None
    eta_seconds: int | None = None
    freshness: Freshness = Freshness.SCHEDULED
    vehicle_id: str | None = None


class RouteStop(BaseModel):
    """A stop in a route's ordered timeline."""

    stop: Stop
    stop_sequence: int
    scheduled_arrival_s: int | None = None


class RouteDetails(BaseModel):
    route: Route
    stops: list[RouteStop]
    live_vehicles: list[VehiclePosition] = Field(default_factory=list)
