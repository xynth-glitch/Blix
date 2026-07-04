from google.transit import gtfs_realtime_pb2

from blix.models.canonical import Freshness
from blix.providers.delhi_otd import DelhiOTDProvider


def _build_feed() -> bytes:
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = 1_700_000_000

    ent = feed.entity.add()
    ent.id = "veh-1"
    ent.vehicle.vehicle.id = "DL1PC1234"
    ent.vehicle.trip.trip_id = "trip-1"
    ent.vehicle.trip.route_id = "142"
    ent.vehicle.position.latitude = 28.6139
    ent.vehicle.position.longitude = 77.2090
    ent.vehicle.position.bearing = 90.0
    ent.vehicle.timestamp = 1_700_000_050

    # An entity without a position should be skipped.
    ent2 = feed.entity.add()
    ent2.id = "veh-2"
    ent2.vehicle.vehicle.id = "DL1PC9999"

    return feed.SerializeToString()


def test_parse_vehicle_positions():
    positions = DelhiOTDProvider.parse_vehicle_positions(_build_feed())
    assert len(positions) == 1
    p = positions[0]
    assert p.vehicle_id == "DL1PC1234"
    assert p.route_id == "142"
    assert p.trip_id == "trip-1"
    assert abs(p.lat - 28.6139) < 1e-6
    assert p.bearing == 90.0
    assert p.freshness is Freshness.LIVE


def test_parse_empty_feed():
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    assert DelhiOTDProvider.parse_vehicle_positions(feed.SerializeToString()) == []
