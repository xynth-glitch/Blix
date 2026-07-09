"""Application configuration, loaded from environment / .env."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BLIX_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql+psycopg://blix:blix@localhost:5432/blix"

    # Delhi OTD provider
    otd_base_url: str = "https://otd.delhi.gov.in"
    # Static GTFS bundle. The OTD download is gated behind a form POST; a stable
    # local/mirror path can be provided instead for reproducible ingestion.
    otd_static_gtfs_url: str | None = None
    # Real-time VehiclePositions endpoint requires a private key issued after
    # registration at https://otd.delhi.gov.in/data/realtime/
    otd_realtime_key: str | None = None
    otd_vehicle_positions_path: str = "/api/realtime/VehiclePositions.pb"

    # Real-time poller
    rt_poll_interval_seconds: int = 15
    # A vehicle position older than this is considered STALE (not live).
    rt_stale_after_seconds: int = 60

    # OpenAI assistant
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.5"
    openai_timeout_seconds: float = 20.0

    # Engine defaults
    nearby_default_radius_m: int = 500
    nearby_max_radius_m: int = 3000

    # Server
    cors_allow_origins: list[str] = ["http://localhost:3000"]

    @property
    def vehicle_positions_url(self) -> str | None:
        """Fully-formed real-time endpoint, or None if no key is configured."""
        if not self.otd_realtime_key:
            return None
        return (
            f"{self.otd_base_url}{self.otd_vehicle_positions_path}"
            f"?key={self.otd_realtime_key}"
        )


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
