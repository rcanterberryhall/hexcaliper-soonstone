"""TAF parser tests, built incrementally: header -> FM/BECMG -> TEMPO/PROB."""
from __future__ import annotations

import json

import pytest

from soonstone.parsers.taf_parser import parse_taf


def test_header_extracts_station_issuance_and_validity():
    raw = "KMIA 021720Z 0218/0324 10010KT P6SM SCT030 SCT250"
    parsed = parse_taf(raw)
    assert parsed["station_id"] == "KMIA"
    assert parsed["issued_at"].endswith("Z")
    assert parsed["valid_from"].endswith("Z")
    assert parsed["valid_to"].endswith("Z")
    assert parsed["amendment_type"] is None
    assert parsed["raw_taf"] == raw


def test_header_detects_amendment_type():
    raw = "TAF AMD KMIA 021820Z 0218/0324 18015G25KT 4SM TSRA BKN025CB"
    parsed = parse_taf(raw)
    assert parsed["amendment_type"] == "AMD"
    assert parsed["station_id"] == "KMIA"


def test_header_detects_correction():
    raw = "TAF COR KMIA 021720Z 0218/0324 10010KT P6SM SCT030"
    parsed = parse_taf(raw)
    assert parsed["amendment_type"] == "COR"


def test_base_group_present_with_index_zero():
    raw = "KMIA 021720Z 0218/0324 10010KT P6SM SCT030 SCT250"
    parsed = parse_taf(raw)
    groups = parsed["groups"]
    assert len(groups) >= 1
    base = groups[0]
    assert base["group_type"] == "BASE"
    assert base["group_index"] == 0
    assert base["wind_dir_deg"] == 100
    assert base["wind_speed_kt"] == 10.0
    assert base["visibility_sm"] >= 6.0  # P6SM
    layers = json.loads(base["cloud_layers"])
    covers = [l["cover"] for l in layers]
    assert "SCT" in covers
