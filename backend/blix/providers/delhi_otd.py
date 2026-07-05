"""Delhi Open Transit Data (OTD) provider adapter.

Static:   GTFS.zip downloaded from otd.delhi.gov.in (form-gated POST, no key).
Real-time: GTFS-Realtime VehiclePositions protobuf, requires a private key issued
           after registration at https://otd.delhi.gov.in/data/realtime/.

Note (verified against the live feed): the static bundle contains agency, calendar,
stops, routes, trips, stop_times, fare_attributes, fare_rules — but NO shapes.txt
(route geometry must be derived downstream), and the real-time feed provides only
VehiclePositions (no TripUpdates/Alerts), so ETAs are computed by Blix, not supplied.
"""

from __future__ import annotations

import io
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import httpx
import structlog
from google.transit import gtfs_realtime_pb2

from blix.config import Settings, get_settings
from blix.models.canonical import Freshness, VehiclePosition
from blix.providers.base import TransitProvider

log = structlog.get_logger(__name__)

_CSRF_RE = re.compile(r"name=['\"]csrfmiddlewaretoken['\"]\s+value=['\"]([^'\"]+)['\"]")


class DelhiOTDProvider(TransitProvider):
    provider_id = "delhi-otd"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    # ------------------------------------------------------------------ #
    # Static
    # ------------------------------------------------------------------ #
    def fetch_static_gtfs(self, dest_dir: Path) -> Path:
        dest_dir.mkdir(parents=True, exist_ok=True)
        content = self._download_static_zip()
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            zf.extractall(dest_dir)
        log.info("otd.static.extracted", dir=str(dest_dir), files=len(list(dest_dir.iterdir())))
        return dest_dir

    def _download_static_zip(self) -> bytes:
        # Prefer an explicit mirror/local URL for reproducible ingestion.
        if self.settings.otd_static_gtfs_url:
            resp = httpx.get(self.settings.otd_static_gtfs_url, timeout=120, follow_redirects=True)
            resp.raise_for_status()
            return resp.content

        # Otherwise replicate the portal's CSRF-protected form POST.
        base = self.settings.otd_base_url
        with httpx.Client(timeout=120, follow_redirects=True) as client:
            page = client.get(f"{base}/data/static/")
            page.raise_for_status()
            token = self._csrf_from(page.text, client)
            resp = client.post(
                f"{base}/data/static/",
                headers={"X-CSRFToken": token, "Referer": f"{base}/data/static/"},
                data={
                    "csrfmiddlewaretoken": token,
                    "dataDownloaded": "all",
                    "usageType": "R&D",
                    "purpose": "R&D",
                },
            )
            resp.raise_for_status()
            if "zip" not in resp.headers.get("content-type", ""):
                raise RuntimeError(
                    f"OTD static download did not return a zip (content-type="
                    f"{resp.headers.get('content-type')!r})"
                )
            return resp.content

    @staticmethod
    def _csrf_from(html: str, client: httpx.Client) -> str:
        cookie = client.cookies.get("csrftoken")
        if cookie:
            return cookie
        m = _CSRF_RE.search(html)
        if not m:
            raise RuntimeError("Could not obtain CSRF token from OTD static page")
        return m.group(1)

    # ------------------------------------------------------------------ #
    # Real-time
    # ------------------------------------------------------------------ #
    def supports_realtime(self) -> bool:
        return self.settings.vehicle_positions_url is not None

    def fetch_vehicle_positions(self) -> list[VehiclePosition]:
        url = self.settings.vehicle_positions_url
        if url is None:
            log.warning("otd.realtime.no_key")
            return []
        resp = httpx.get(url, timeout=30)
        resp.raise_for_status()
        return self.parse_vehicle_positions(resp.content)

    @staticmethod
    def parse_vehicle_positions(data: bytes) -> list[VehiclePosition]:
        """Parse a GTFS-Realtime VehiclePositions protobuf payload."""
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(data)
        out: list[VehiclePosition] = []
        for entity in feed.entity:
            if not entity.HasField("vehicle"):
                continue
            v = entity.vehicle
            if not v.HasField("position"):
                continue
            ts = v.timestamp or feed.header.timestamp
            observed = datetime.fromtimestamp(ts, tz=UTC) if ts else datetime.now(tz=UTC)
            vehicle_id = v.vehicle.id or entity.id
            out.append(
                VehiclePosition(
                    vehicle_id=vehicle_id,
                    trip_id=v.trip.trip_id or None,
                    route_id=v.trip.route_id or None,
                    lat=v.position.latitude,
                    lon=v.position.longitude,
                    bearing=v.position.bearing or None,
                    speed_mps=v.position.speed or None,
                    observed_at=observed,
                    freshness=Freshness.LIVE,
                )
            )
        return out
