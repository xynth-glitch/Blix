from blix.config import Settings


def test_vehicle_positions_url_none_without_key():
    s = Settings(otd_realtime_key=None)
    assert s.vehicle_positions_url is None


def test_vehicle_positions_url_with_key():
    s = Settings(otd_realtime_key="secret123")
    url = s.vehicle_positions_url
    assert url is not None
    assert url.endswith("/api/realtime/VehiclePositions.pb?key=secret123")
