"""Verify IemRadarClient builds the right URL and validates the response."""
from __future__ import annotations

import pytest
import requests_mock

from soonstone.config import Config
from soonstone.ingestion.iem_radar import IemRadarClient, _round_to_frame


@pytest.fixture
def client():
    return IemRadarClient(config=Config.from_env())


def test_round_to_frame_rounds_down_to_5min():
    assert _round_to_frame("2026-05-03T17:53:42Z") == "202605031750"
    assert _round_to_frame("2026-05-03T17:55:00Z") == "202605031755"
    assert _round_to_frame("2026-05-03T00:01:00Z") == "202605030000"


def test_build_url_contains_bbox_and_timestamp(client):
    url = client.build_url(lat=25.79, lon=-80.29, observed_at_iso="2026-05-03T17:53:00Z")
    assert "ts=202605031750" in url
    assert "bbox=-80.79,25.29,-79.79,26.29" in url
    assert "nexrad-n0r" in url


def test_fetch_returns_png_bytes(client):
    png_magic = b"\x89PNG\r\n\x1a\nfakebody"
    with requests_mock.Mocker() as m:
        m.get(requests_mock.ANY, content=png_magic)
        body = client.fetch(lat=25.79, lon=-80.29, observed_at_iso="2026-05-03T17:53:00Z")
    assert body == png_magic


def test_fetch_returns_none_on_non_png_body(client):
    """IEM occasionally serves a 200 with an HTML error body; treat as failure."""
    with requests_mock.Mocker() as m:
        m.get(requests_mock.ANY, text="<html>error</html>",
              headers={"content-type": "text/html"})
        body = client.fetch(lat=25.79, lon=-80.29, observed_at_iso="2026-05-03T17:53:00Z")
    assert body is None


def test_fetch_returns_none_on_http_error(client):
    with requests_mock.Mocker() as m:
        m.get(requests_mock.ANY, status_code=503, text="upstream down")
        body = client.fetch(lat=25.79, lon=-80.29, observed_at_iso="2026-05-03T17:53:00Z")
    assert body is None
