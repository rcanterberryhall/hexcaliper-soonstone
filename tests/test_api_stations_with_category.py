"""Verify /api/stations includes the latest flight_category per station."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from soonstone.app import create_app
from soonstone.db import Base, make_session_factory
from soonstone.models import Observation, Station


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'flightcat.db'}")
    a = create_app()
    Base.metadata.create_all(a.extensions["soonstone_engine"])
    sf = make_session_factory(a.extensions["soonstone_engine"])
    now = datetime.now(timezone.utc)
    with sf() as s:
        s.add(Station(station_id="KMIA", name="Miami",
                      latitude=25.79, longitude=-80.29, active=1))
        s.add(Station(station_id="KEYW", name="Key West",
                      latitude=24.55, longitude=-81.76, active=1))
        s.flush()
        # KMIA has two obs; latest is IFR
        s.add(Observation(station_id="KMIA",
                          observed_at=_iso(now - timedelta(hours=2)),
                          raw_metar="X", flight_category="VFR",
                          ingested_at=_iso(now)))
        s.add(Observation(station_id="KMIA",
                          observed_at=_iso(now - timedelta(minutes=10)),
                          raw_metar="X", flight_category="IFR",
                          ingested_at=_iso(now)))
        # KEYW has none
        s.commit()
    return a


def test_stations_includes_latest_flight_category(app):
    """Default endpoint hides stations without a recent (last 6h) observation;
    use ?include_stale=1 to verify both the IFR-fresh KMIA and
    no-observation KEYW."""
    body = app.test_client().get("/api/stations?include_stale=1").get_json()
    by_id = {f["properties"]["id"]: f["properties"] for f in body["features"]}
    assert by_id["KMIA"]["flight_category"] == "IFR"
    assert by_id["KEYW"]["flight_category"] is None


def test_default_filters_out_stations_without_recent_obs(app):
    body = app.test_client().get("/api/stations").get_json()
    ids = {f["properties"]["id"] for f in body["features"]}
    # KMIA had a recent (10-min-old) observation in the fixture; KEYW had none.
    assert "KMIA" in ids
    assert "KEYW" not in ids
