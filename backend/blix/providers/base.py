"""Provider abstraction.

Every city/mode implements `TransitProvider`. The engine and ingestion code depend
only on this interface, so adding a new city (or the Metro) means writing one
adapter — not touching the engine. Delhi OTD is the first implementation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from blix.models.canonical import VehiclePosition


class TransitProvider(ABC):
    """Interface a data source must implement to be usable by Blix."""

    #: Stable identifier, e.g. "delhi-otd".
    provider_id: str

    @abstractmethod
    def fetch_static_gtfs(self, dest_dir: Path) -> Path:
        """Download/obtain the static GTFS bundle and return the extracted dir."""

    @abstractmethod
    def supports_realtime(self) -> bool:
        """Whether real-time vehicle positions are available/configured."""

    @abstractmethod
    def fetch_vehicle_positions(self) -> list[VehiclePosition]:
        """Fetch the current real-time vehicle positions (may be empty)."""
