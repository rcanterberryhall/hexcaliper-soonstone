"""Tests for GET /health."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from soonstone.app import create_app


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'health.db'}")
    return create_app()


def test_health_503_before_first_run(app):
    resp = app.test_client().get("/health")
    assert resp.status_code == 503


def test_health_200_after_recent_metar_and_taf_runs(app):
    health = app.extensions["soonstone_health"]
    health.record_success("ingest_metars")
    health.record_success("ingest_tafs")
    resp = app.test_client().get("/health")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ok"


def test_health_503_when_metar_stale(app):
    health = app.extensions["soonstone_health"]
    health.record_success(
        "ingest_metars",
        at=datetime.now(timezone.utc) - timedelta(hours=3),
    )
    health.record_success("ingest_tafs")
    resp = app.test_client().get("/health")
    assert resp.status_code == 503
