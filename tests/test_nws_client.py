"""Verify NwsClient hits /points and /forecast with the right shape."""
from __future__ import annotations

import pytest
import requests_mock

from soonstone.config import Config
from soonstone.ingestion.nws_client import NwsClient


@pytest.fixture
def client():
    return NwsClient(config=Config.from_env())


def test_fetch_points_returns_forecast_url(client):
    with requests_mock.Mocker() as m:
        m.get(
            "https://api.weather.gov/points/25.79,-80.29",
            json={"properties": {
                "forecast": "https://api.weather.gov/gridpoints/MFL/110,50/forecast"
            }},
        )
        url = client.fetch_points(lat=25.79, lon=-80.29)
    assert url == "https://api.weather.gov/gridpoints/MFL/110,50/forecast"


def test_fetch_forecast_returns_periods_array(client):
    sample = {"properties": {"periods": [
        {"name": "Tonight", "startTime": "2026-05-03T18:00:00-04:00",
         "endTime": "2026-05-04T06:00:00-04:00",
         "temperature": 72, "temperatureUnit": "F",
         "windSpeed": "5 to 10 mph", "windDirection": "SW",
         "probabilityOfPrecipitation": {"value": 30},
         "shortForecast": "Mostly clear",
         "detailedForecast": "Mostly clear, with a low around 72."},
    ]}}
    with requests_mock.Mocker() as m:
        m.get("https://api.weather.gov/gridpoints/MFL/110,50/forecast", json=sample)
        periods = client.fetch_forecast(
            "https://api.weather.gov/gridpoints/MFL/110,50/forecast"
        )
    assert len(periods) == 1
    assert periods[0]["temperature"] == 72


def test_user_agent_set(client):
    with requests_mock.Mocker() as m:
        m.get("https://api.weather.gov/points/0,0",
              json={"properties": {"forecast": "x"}})
        client.fetch_points(lat=0, lon=0)
    ua = m.last_request.headers["User-Agent"]
    assert "soonstone" in ua


def test_http_error_raises(client):
    with requests_mock.Mocker() as m:
        m.get("https://api.weather.gov/points/0,0",
              status_code=503, text="upstream down")
        with pytest.raises(Exception):
            client.fetch_points(lat=0, lon=0)
