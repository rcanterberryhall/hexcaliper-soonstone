"""Verify GET / serves the static index.html."""
from __future__ import annotations

import pytest

from soonstone.app import create_app


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'index.db'}")
    return create_app()


def test_index_returns_html(app):
    resp = app.test_client().get("/")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "<!DOCTYPE html>" in body
    assert "Soonstone" in body
    assert "leaflet" in body.lower()
