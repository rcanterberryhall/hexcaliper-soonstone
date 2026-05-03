"""Tests for GET /api/stations."""
from __future__ import annotations

import pytest

from soonstone.app import create_app
from soonstone.db import Base, make_session_factory
from soonstone.models import Station


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'api.db'}")
    a = create_app()
    Base.metadata.create_all(a.extensions["soonstone_engine"])
    return a


def _seed(app, stations):
    sf = make_session_factory(app.extensions["soonstone_engine"])
    with sf() as s:
        s.add_all(stations)
        s.commit()


def test_returns_geojson_feature_collection(app):
    _seed(app, [
        Station(station_id="KMIA", name="Miami Intl",
                latitude=25.79, longitude=-80.29, active=1),
        Station(station_id="KEYW", name="Key West",
                latitude=24.55, longitude=-81.76, active=1),
    ])
    client = app.test_client()
    resp = client.get("/api/stations?include_stale=1")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) == 2
    feature = body["features"][0]
    assert feature["type"] == "Feature"
    assert feature["geometry"]["type"] == "Point"
    assert "id" in feature["properties"]


def test_excludes_inactive_stations(app):
    _seed(app, [
        Station(station_id="KMIA", name="Miami", latitude=25.79, longitude=-80.29, active=1),
        Station(station_id="KGONE", name="Gone", latitude=20.0, longitude=-80.0, active=0),
    ])
    client = app.test_client()
    body = client.get("/api/stations?include_stale=1").get_json()
    ids = {f["properties"]["id"] for f in body["features"]}
    assert ids == {"KMIA"}
