"""Tests for GET /api/stations/<id>/snapshot."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from soonstone.app import create_app
from soonstone.db import Base, make_session_factory
from soonstone.models import Observation, Station, Taf, TafGroup


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'snap_api.db'}")
    a = create_app()
    Base.metadata.create_all(a.extensions["soonstone_engine"])
    sf = make_session_factory(a.extensions["soonstone_engine"])
    now = datetime(2026, 5, 2, 18, 0, tzinfo=timezone.utc)
    with sf() as s:
        s.add(Station(station_id="KMIA", name="Miami Intl",
                      latitude=25.79, longitude=-80.29, active=1))
        s.flush()
        s.add(Observation(
            station_id="KMIA", observed_at=_iso(now - timedelta(minutes=10)),
            raw_metar="X", wind_dir_deg=180, wind_speed_kt=10.0,
            visibility_sm=10.0, flight_category="VFR",
            ingested_at=_iso(now - timedelta(minutes=5)),
        ))
        t = Taf(
            station_id="KMIA",
            issued_at=_iso(now - timedelta(hours=4)),
            valid_from=_iso(now - timedelta(hours=4)),
            valid_to=_iso(now + timedelta(hours=20)),
            raw_taf="X",
            ingested_at=_iso(now - timedelta(hours=4)),
        )
        s.add(t)
        s.flush()
        s.add(TafGroup(
            taf_id=t.taf_id, group_index=0, group_type="BASE",
            group_from=t.valid_from, group_to=t.valid_to,
            wind_dir_deg=180, wind_speed_kt=10.0, flight_category="VFR",
        ))
        s.commit()
    return a


def test_snapshot_endpoint_returns_expected_shape(app):
    client = app.test_client()
    resp = client.get("/api/stations/KMIA/snapshot")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["station"]["id"] == "KMIA"
    assert "now" in body
    assert "convergence" in body
    assert "forward" in body
    assert isinstance(body["convergence"], list)


def test_snapshot_unknown_station_404(app):
    client = app.test_client()
    resp = client.get("/api/stations/ZZZZ/snapshot")
    assert resp.status_code == 404
