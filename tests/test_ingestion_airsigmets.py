"""Tests for ingest_airsigmets: writes the cached FeatureCollection to disk."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from soonstone.config import Config
from soonstone.ingestion.airsigmets import ingest_airsigmets


def _config(tmp_path):
    return Config(
        database_url=f"sqlite:///{tmp_path / 'x.db'}",
        bbox_south=24.0, bbox_west=-88.0, bbox_north=31.5, bbox_east=-79.5,
        log_level="INFO",
        awc_base_url="https://aviationweather.gov/api/data",
        http_user_agent="test",
        radar_dir=str(tmp_path / "data" / "radar"),
        iem_base_url="https://mesonet.agron.iastate.edu",
    )


def test_writes_cached_feature_collection(tmp_path):
    cfg = _config(tmp_path)
    awc = MagicMock()
    awc.fetch_airsigmets.return_value = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature",
             "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
             "properties": {"airSigmetType": "SIGMET", "hazard": "CONVECTIVE"}},
        ],
    }
    result = ingest_airsigmets(awc, cfg)
    assert result.features_count == 1
    target = tmp_path / "data" / "airsigmets" / "current.json"
    assert target.exists()
    fc = json.loads(target.read_text())
    assert fc["features"][0]["properties"]["hazard"] == "CONVECTIVE"


def test_handles_unexpected_payload_shape(tmp_path):
    cfg = _config(tmp_path)
    awc = MagicMock()
    awc.fetch_airsigmets.return_value = ["not", "a", "FeatureCollection"]
    result = ingest_airsigmets(awc, cfg)
    assert result.features_count == 0
    target = tmp_path / "data" / "airsigmets" / "current.json"
    fc = json.loads(target.read_text())
    assert fc["features"] == []
