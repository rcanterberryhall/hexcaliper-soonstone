"""Tests for refresh_stations: fresh insert, idempotent re-run, last_seen update."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from soonstone.config import Config
from soonstone.db import Base, create_engine_with_pragmas, make_session_factory
from soonstone.ingestion.stations import refresh_stations
from soonstone.models import Station


@pytest.fixture
def session_factory(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'stations_test.db'}"
    engine = create_engine_with_pragmas(db_url)
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


@pytest.fixture
def cfg():
    return Config.from_env()


def _mock_awc(stations: list[dict]):
    m = MagicMock()
    m.fetch_stations.return_value = stations
    return m


def test_refresh_stations_inserts_new_rows(session_factory, cfg):
    awc = _mock_awc([
        {"icaoId": "KMIA", "lat": 25.79, "lon": -80.29, "elev": 9,
         "site": "Miami Intl", "state": "FL", "country": "US"},
        {"icaoId": "KEYW", "lat": 24.55, "lon": -81.76, "elev": 1,
         "site": "Key West Intl", "state": "FL", "country": "US"},
    ])
    with session_factory() as session:
        result = refresh_stations(session, awc, cfg)

    assert result.fetched == 2
    assert result.inserted == 2
    assert result.updated == 0

    with session_factory() as session:
        rows = session.execute(select(Station).order_by(Station.station_id)).scalars().all()
    assert [r.station_id for r in rows] == ["KEYW", "KMIA"]
    assert rows[1].latitude == pytest.approx(25.79)


def test_refresh_stations_is_idempotent(session_factory, cfg):
    payload = [{"icaoId": "KMIA", "lat": 25.79, "lon": -80.29, "elev": 9,
                "site": "Miami Intl", "state": "FL", "country": "US"}]
    awc = _mock_awc(payload)

    with session_factory() as session:
        refresh_stations(session, awc, cfg)

    with session_factory() as session:
        result = refresh_stations(session, awc, cfg)

    assert result.inserted == 0
    assert result.updated == 1  # last_seen bumped
    with session_factory() as session:
        row = session.get(Station, "KMIA")
    assert row.last_seen is not None


def test_refresh_stations_marks_taf_sites(session_factory, cfg):
    awc = _mock_awc([
        {"icaoId": "KMIA", "lat": 25.79, "lon": -80.29, "elev": 9,
         "site": "Miami Intl", "state": "FL", "country": "US", "tafSite": True},
        {"icaoId": "KMTH", "lat": 24.73, "lon": -81.05, "elev": 2,
         "site": "Marathon", "state": "FL", "country": "US"},
    ])
    with session_factory() as session:
        refresh_stations(session, awc, cfg)
    with session_factory() as session:
        kmia = session.get(Station, "KMIA")
        kmth = session.get(Station, "KMTH")
    assert kmia.taf_site == 1
    assert kmth.taf_site == 0
