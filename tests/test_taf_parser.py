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


def test_fm_group_creates_separate_change_group():
    raw = (
        "KMIA 021720Z 0218/0324 10010KT P6SM SCT030 SCT250 "
        "FM030000 09008KT P6SM SCT030 SCT250"
    )
    parsed = parse_taf(raw)
    groups = parsed["groups"]
    assert len(groups) == 2
    assert groups[0]["group_type"] == "BASE"
    assert groups[1]["group_type"] == "FM"
    assert groups[1]["group_index"] == 1
    assert groups[1]["wind_dir_deg"] == 90
    assert groups[1]["wind_speed_kt"] == 8.0
    assert groups[1]["group_from"].endswith("Z")


def test_multiple_fm_groups_chronological():
    raw = (
        "KMIA 021720Z 0218/0324 10010KT P6SM SCT030 "
        "FM030000 09008KT P6SM SCT030 "
        "FM031500 10012KT P6SM BKN250"
    )
    parsed = parse_taf(raw)
    types = [g["group_type"] for g in parsed["groups"]]
    assert types == ["BASE", "FM", "FM"]
    assert parsed["groups"][1]["group_from"] < parsed["groups"][2]["group_from"]


def test_becmg_group_has_window():
    raw = (
        "KTPA 021720Z 0218/0324 25008KT P6SM SCT030 "
        "BECMG 0312/0314 26010KT P6SM SCT040"
    )
    parsed = parse_taf(raw)
    becmg = [g for g in parsed["groups"] if g["group_type"] == "BECMG"]
    assert len(becmg) == 1
    g = becmg[0]
    assert g["group_from"] != g["group_to"], "BECMG must have a non-zero window"
    assert g["wind_dir_deg"] == 260


def test_tempo_group_marked_with_probability_implicit():
    raw = (
        "KTPA 021720Z 0218/0324 25008KT P6SM SCT030 "
        "TEMPO 0218/0222 VRB10G20KT 3SM TSRA BKN025CB"
    )
    parsed = parse_taf(raw)
    tempo_groups = [g for g in parsed["groups"] if g["group_type"] == "TEMPO"]
    assert len(tempo_groups) == 1
    g = tempo_groups[0]
    assert g["wind_speed_kt"] == 10.0
    assert g["wind_gust_kt"] == 20.0
    assert g["visibility_sm"] == 3.0
    assert g["ceiling_ft"] == 2500


def test_prob30_group_carries_probability():
    raw = (
        "KMIA 021720Z 0218/0324 10010KT P6SM SCT030 "
        "PROB30 0219/0223 VRB05KT 4SM TSRA BKN025CB"
    )
    parsed = parse_taf(raw)
    prob_groups = [g for g in parsed["groups"] if g["group_type"] == "PROB30"]
    assert len(prob_groups) == 1
    assert prob_groups[0]["probability_pct"] == 30
    assert prob_groups[0]["visibility_sm"] == 4.0


def test_all_taf_fixtures_parse_without_raising(taf_fixtures):
    assert taf_fixtures, "no TAF fixtures captured -- run scripts/capture_fixtures.py"
    for name, raw in taf_fixtures.items():
        parsed = parse_taf(raw)
        assert parsed["station_id"], f"{name}: empty station_id"
        assert parsed["groups"], f"{name}: no groups produced"
        assert parsed["groups"][0]["group_type"] == "BASE"
        idxs = [g["group_index"] for g in parsed["groups"]]
        assert idxs == sorted(idxs) == list(range(len(idxs)))
