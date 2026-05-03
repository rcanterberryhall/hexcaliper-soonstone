"""Verify create_app boots cleanly and exposes engine + awc_client on app.extensions."""
from __future__ import annotations

import pytest

from soonstone.app import create_app
from soonstone.config import Config
from soonstone.ingestion.awc_client import AwcClient


def test_create_app_returns_flask_app(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'app.db'}")
    app = create_app()
    assert app.name == "soonstone"


def test_create_app_exposes_engine_and_awc_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'app.db'}")
    app = create_app()
    assert "soonstone_engine" in app.extensions
    assert "soonstone_awc_client" in app.extensions
    assert "soonstone_config" in app.extensions
    assert isinstance(app.extensions["soonstone_awc_client"], AwcClient)
    assert isinstance(app.extensions["soonstone_config"], Config)


def test_create_app_accepts_overrides(tmp_path):
    cfg = Config.from_env()
    overridden = Config(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        bbox_south=10.0, bbox_west=10.0, bbox_north=20.0, bbox_east=20.0,
        log_level="WARNING",
        awc_base_url=cfg.awc_base_url,
        http_user_agent=cfg.http_user_agent,
    )
    app = create_app(config=overridden)
    assert app.extensions["soonstone_config"].bbox_south == 10.0
