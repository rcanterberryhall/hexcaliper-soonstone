"""Tests for GET /api/airsigmets."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from soonstone.app import create_app


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'x.db'}")
    monkeypatch.setenv("SOONSTONE_RADAR_DIR", str(tmp_path / "data" / "radar"))
    return create_app()


def test_returns_empty_collection_when_no_cache(app):
    body = app.test_client().get("/api/airsigmets").get_json()
    assert body["type"] == "FeatureCollection"
    assert body["features"] == []


def test_serves_cached_file_when_present(app, tmp_path):
    target = tmp_path / "data" / "airsigmets" / "current.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    fc = {"type": "FeatureCollection", "features": [{"properties": {"hazard": "TURB"}}]}
    target.write_text(json.dumps(fc))
    resp = app.test_client().get("/api/airsigmets")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["features"][0]["properties"]["hazard"] == "TURB"
    assert "max-age=300" in resp.headers.get("Cache-Control", "")
