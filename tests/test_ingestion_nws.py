"""Tests for ingest_nws_forecasts: per-station forecast pull, points-URL caching."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from soonstone.config import Config
from soonstone.db import Base, create_engine_with_pragmas, make_session_factory
from soonstone.ingestion.nws import ingest_nws_forecasts
from soonstone.models import NwsForecast, Station


@pytest.fixture
def factory(tmp_path, monkeypatch):
    # Squash the per-call sleep so the test runs fast.
    monkeypatch.setattr("soonstone.ingestion.nws._REQUEST_GAP_SEC", 0)
    db_url = f"sqlite:///{tmp_path / 'nws.db'}"
    engine = create_engine_with_pragmas(db_url)
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


@pytest.fixture
def seeded(factory):
    with factory() as s:
        s.add(Station(station_id="KMIA", latitude=25.79, longitude=-80.29, taf_site=1))
        s.add(Station(station_id="K0J4", latitude=31.04, longitude=-86.31, taf_site=0))
        s.commit()
    return factory


def _periods():
    return [
        {"name": "Today", "startTime": "2026-05-03T08:00:00+00:00",
         "endTime": "2026-05-03T18:00:00+00:00", "temperature": 78,
         "windSpeed": "5 to 10 mph", "windDirection": "SW",
         "probabilityOfPrecipitation": {"value": 20},
         "shortForecast": "Mostly sunny", "detailedForecast": "..."},
        {"name": "Tonight", "startTime": "2026-05-03T18:00:00+00:00",
         "endTime": "2026-05-04T06:00:00+00:00", "temperature": 68,
         "windSpeed": "5 mph", "windDirection": "SE",
         "probabilityOfPrecipitation": {"value": 40},
         "shortForecast": "Showers likely", "detailedForecast": "..."},
    ]


def _mock_nws():
    m = MagicMock()
    m.fetch_points.return_value = "https://api.weather.gov/gridpoints/MFL/110,50/forecast"
    m.fetch_forecast.return_value = _periods()
    return m


def test_ingest_only_taf_sites(seeded):
    nws = _mock_nws()
    with seeded() as session:
        result = ingest_nws_forecasts(session, nws, Config.from_env())
    assert result.stations_processed == 1
    assert result.forecasts_inserted == 2
    assert nws.fetch_points.call_count == 1


def test_points_url_cached_on_station(seeded):
    nws = _mock_nws()
    with seeded() as session:
        ingest_nws_forecasts(session, nws, Config.from_env())
    with seeded() as session:
        kmia = session.get(Station, "KMIA")
        assert kmia.nws_forecast_url == "https://api.weather.gov/gridpoints/MFL/110,50/forecast"
    nws.fetch_points.reset_mock()
    with seeded() as session:
        ingest_nws_forecasts(session, nws, Config.from_env())
    assert nws.fetch_points.call_count == 0


def test_idempotent_forecast_insert(seeded):
    nws = _mock_nws()
    with seeded() as session:
        ingest_nws_forecasts(session, nws, Config.from_env())
    with seeded() as session:
        result = ingest_nws_forecasts(session, nws, Config.from_env())
    assert result.forecasts_inserted == 0
    assert result.forecasts_skipped_duplicate == 2


def test_fetch_failure_does_not_break_other_stations(seeded):
    """Add a third TAF station that errors; the first should still process."""
    with seeded() as session:
        session.add(Station(station_id="KFAIL", latitude=40, longitude=-100, taf_site=1))
        session.commit()
    nws = MagicMock()
    nws.fetch_points.return_value = "https://api.weather.gov/gridpoints/MFL/110,50/forecast"
    # First call succeeds, second raises
    nws.fetch_forecast.side_effect = [_periods(), Exception("boom")]
    with seeded() as session:
        result = ingest_nws_forecasts(session, nws, Config.from_env())
    assert result.stations_processed == 1  # only the successful one
    assert result.fetch_failures >= 1
    assert result.forecasts_inserted == 2
