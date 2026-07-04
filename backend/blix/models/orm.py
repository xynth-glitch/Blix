"""SQLAlchemy ORM models — the persistence schema for normalized transit data.

Two data speeds live here:
- *Static* tables (agencies, stops, routes, trips, stop_times, fares): refreshed
  when the provider publishes a new GTFS bundle.
- *Real-time* tables: `vehicle_positions_live` (latest per vehicle, hot path) and
  `vehicle_positions_history` (append-only warehouse powering future ETA/delay ML).
"""

from __future__ import annotations

from datetime import datetime

from geoalchemy2 import Geography
from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# --------------------------------------------------------------------------- #
# Static GTFS
# --------------------------------------------------------------------------- #
class Agency(Base):
    __tablename__ = "agencies"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str | None] = mapped_column(String)
    timezone: Mapped[str] = mapped_column(String, default="Asia/Kolkata")


class Stop(Base):
    __tablename__ = "stops"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    code: Mapped[str | None] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    zone_id: Mapped[str | None] = mapped_column(String, index=True)
    # PostGIS geography for fast spatial (nearby) queries.
    geom: Mapped[object] = mapped_column(Geography(geometry_type="POINT", srid=4326))

    __table_args__ = (
        Index("ix_stops_geom", "geom", postgresql_using="gist"),
    )


class Route(Base):
    __tablename__ = "routes"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    agency_id: Mapped[str] = mapped_column(String, ForeignKey("agencies.id"), index=True)
    short_name: Mapped[str | None] = mapped_column(String, index=True)
    long_name: Mapped[str | None] = mapped_column(String, index=True)
    route_type: Mapped[int] = mapped_column(Integer, default=3)


class Trip(Base):
    __tablename__ = "trips"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    route_id: Mapped[str] = mapped_column(String, ForeignKey("routes.id"), index=True)
    service_id: Mapped[str] = mapped_column(String, index=True)
    shape_id: Mapped[str | None] = mapped_column(String)
    headsign: Mapped[str | None] = mapped_column(String)


class StopTime(Base):
    __tablename__ = "stop_times"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trip_id: Mapped[str] = mapped_column(String, ForeignKey("trips.id"), index=True)
    stop_id: Mapped[str] = mapped_column(String, ForeignKey("stops.id"), index=True)
    stop_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    arrival_s: Mapped[int | None] = mapped_column(Integer)
    departure_s: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        Index("ix_stop_times_trip_seq", "trip_id", "stop_sequence"),
    )


class Fare(Base):
    __tablename__ = "fares"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    route_id: Mapped[str | None] = mapped_column(String, index=True)
    origin_zone_id: Mapped[str] = mapped_column(String, index=True)
    destination_zone_id: Mapped[str] = mapped_column(String, index=True)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String, default="INR")

    __table_args__ = (
        Index("ix_fares_od", "origin_zone_id", "destination_zone_id"),
    )


# --------------------------------------------------------------------------- #
# Real-time
# --------------------------------------------------------------------------- #
class VehiclePositionLive(Base):
    """Latest known position per vehicle (hot path for live features)."""

    __tablename__ = "vehicle_positions_live"

    vehicle_id: Mapped[str] = mapped_column(String, primary_key=True)
    trip_id: Mapped[str | None] = mapped_column(String, index=True)
    route_id: Mapped[str | None] = mapped_column(String, index=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    bearing: Mapped[float | None] = mapped_column(Float)
    speed_mps: Mapped[float | None] = mapped_column(Float)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class VehiclePositionHistory(Base):
    """Append-only warehouse of every observed position.

    This exists from day one *specifically* so future features (ETA models,
    delay prediction, reliability scores) have historical data to learn from.
    """

    __tablename__ = "vehicle_positions_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    vehicle_id: Mapped[str] = mapped_column(String, index=True)
    trip_id: Mapped[str | None] = mapped_column(String, index=True)
    route_id: Mapped[str | None] = mapped_column(String, index=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    bearing: Mapped[float | None] = mapped_column(Float)
    speed_mps: Mapped[float | None] = mapped_column(Float)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_vph_route_time", "route_id", "observed_at"),
    )


class FeedStatus(Base):
    """Tracks freshness/health of each ingested feed (static & real-time)."""

    __tablename__ = "feed_status"

    # e.g. "static", "vehicle_positions"
    feed: Mapped[str] = mapped_column(String, primary_key=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String)
    record_count: Mapped[int | None] = mapped_column(Integer)
