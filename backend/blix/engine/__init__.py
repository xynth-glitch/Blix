"""Deterministic transport engine.

This is the correctness core of Blix. The AI layer (added later) is only a
*consumer* of these functions and never a source of transit facts.
"""

from blix.engine.arrivals import stop_arrivals
from blix.engine.fare import fare_between, fare_between_stops
from blix.engine.nearby import nearby_stops
from blix.engine.routes import get_route, route_details, search_routes

__all__ = [
    "stop_arrivals",
    "fare_between",
    "fare_between_stops",
    "nearby_stops",
    "get_route",
    "route_details",
    "search_routes",
]
