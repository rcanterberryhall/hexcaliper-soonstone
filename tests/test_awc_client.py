"""Verify AwcClient sends correct request shape and parses JSON responses."""
from __future__ import annotations

import pytest
import requests_mock

from soonstone.config import Config
from soonstone.ingestion.awc_client import AwcClient


@pytest.fixture
def client():
    cfg = Config.from_env()
    return AwcClient(config=cfg)


def test_fetch_metars_uses_bbox_and_json_format(client):
    sample = [
        {
            "icaoId": "KMIA",
            "rawOb": "KMIA 021753Z 10010KT 10SM FEW030 SCT250 28/22 A3007",
            "obsTime": 1714672380,
        }
    ]
    with requests_mock.Mocker() as m:
        m.get(
            "https://aviationweather.gov/api/data/metar",
            json=sample,
        )
        result = client.fetch_metars(bbox="24.0,-88.0,31.5,-79.5")

    assert result == sample
    last = m.last_request
    assert last.qs["bbox"] == ["24.0,-88.0,31.5,-79.5"]
    assert last.qs["format"] == ["json"]
    assert last.headers["User-Agent"].startswith("soonstone/")


def test_fetch_tafs_uses_bbox_and_json_format(client):
    sample = [{"icaoId": "KMIA", "rawTAF": "KMIA 021720Z 0218/0324 ..."}]
    with requests_mock.Mocker() as m:
        m.get("https://aviationweather.gov/api/data/taf", json=sample)
        result = client.fetch_tafs(bbox="24.0,-88.0,31.5,-79.5")

    assert result == sample
    assert m.last_request.qs["bbox"] == ["24.0,-88.0,31.5,-79.5"]


def test_fetch_stations_returns_list_of_dicts(client):
    sample = [
        {"icaoId": "KMIA", "lat": 25.79, "lon": -80.29, "elev": 9, "site": "Miami Intl"}
    ]
    with requests_mock.Mocker() as m:
        m.get("https://aviationweather.gov/api/data/stationinfo", json=sample)
        result = client.fetch_stations(bbox="24.0,-88.0,31.5,-79.5")

    assert result == sample


def test_http_error_raises(client):
    with requests_mock.Mocker() as m:
        m.get(
            "https://aviationweather.gov/api/data/metar",
            status_code=503,
            text="upstream down",
        )
        with pytest.raises(Exception):
            client.fetch_metars(bbox="24.0,-88.0,31.5,-79.5")
