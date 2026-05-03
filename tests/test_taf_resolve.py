"""Tests for resolve_taf_at: walks BASE/FM/BECMG/TEMPO/PROB groups."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from soonstone.verification.taf_resolve import resolve_taf_at


def _g(idx: int, gtype: str, gf: str, gt: str, **fields) -> dict:
    base = {
        "group_index": idx,
        "group_type": gtype,
        "group_from": gf,
        "group_to": gt,
        "wind_dir_deg": None,
        "wind_speed_kt": None,
        "wind_gust_kt": None,
        "visibility_sm": None,
        "weather": None,
        "cloud_layers": None,
        "ceiling_ft": None,
        "flight_category": None,
        "probability_pct": None,
    }
    base.update(fields)
    return base


def _t(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def test_only_base_returns_base_state():
    base = _g(0, "BASE", "2026-05-02T18:00:00Z", "2026-05-03T18:00:00Z",
              wind_dir_deg=180, wind_speed_kt=10.0, visibility_sm=10.0,
              flight_category="VFR")
    state = resolve_taf_at(_t("2026-05-02T20:00:00Z"), base, [])
    assert state.wind_dir_deg == 180
    assert state.wind_speed_kt == 10.0
    assert state.flight_category == "VFR"
    assert state.caveats == []


def test_fm_after_target_does_not_apply():
    base = _g(0, "BASE", "2026-05-02T18:00:00Z", "2026-05-03T18:00:00Z",
              wind_dir_deg=180, wind_speed_kt=10.0, flight_category="VFR")
    fm = _g(1, "FM", "2026-05-03T00:00:00Z", "2026-05-03T18:00:00Z",
            wind_dir_deg=90, wind_speed_kt=8.0, flight_category="VFR")
    state = resolve_taf_at(_t("2026-05-02T20:00:00Z"), base, [fm])
    assert state.wind_dir_deg == 180


def test_fm_at_or_before_target_replaces():
    base = _g(0, "BASE", "2026-05-02T18:00:00Z", "2026-05-03T18:00:00Z",
              wind_dir_deg=180, wind_speed_kt=10.0, flight_category="VFR")
    fm = _g(1, "FM", "2026-05-03T00:00:00Z", "2026-05-03T18:00:00Z",
            wind_dir_deg=90, wind_speed_kt=8.0, flight_category="VFR")
    state = resolve_taf_at(_t("2026-05-03T03:00:00Z"), base, [fm])
    assert state.wind_dir_deg == 90
    assert state.wind_speed_kt == 8.0


def test_multiple_fm_use_latest_applicable():
    base = _g(0, "BASE", "2026-05-02T18:00:00Z", "2026-05-03T18:00:00Z",
              wind_dir_deg=180, wind_speed_kt=10.0)
    fm1 = _g(1, "FM", "2026-05-03T00:00:00Z", "2026-05-03T18:00:00Z",
             wind_dir_deg=90, wind_speed_kt=8.0)
    fm2 = _g(2, "FM", "2026-05-03T06:00:00Z", "2026-05-03T18:00:00Z",
             wind_dir_deg=270, wind_speed_kt=12.0)
    state = resolve_taf_at(_t("2026-05-03T10:00:00Z"), base, [fm1, fm2])
    assert state.wind_dir_deg == 270


def test_becmg_after_window_replaces():
    base = _g(0, "BASE", "2026-05-02T18:00:00Z", "2026-05-03T18:00:00Z",
              wind_dir_deg=180, wind_speed_kt=10.0)
    becmg = _g(1, "BECMG", "2026-05-02T20:00:00Z", "2026-05-02T22:00:00Z",
               wind_dir_deg=270, wind_speed_kt=12.0)
    state = resolve_taf_at(_t("2026-05-02T23:00:00Z"), base, [becmg])
    assert state.wind_dir_deg == 270


def test_becmg_inside_window_uses_midpoint_threshold():
    base = _g(0, "BASE", "2026-05-02T18:00:00Z", "2026-05-03T18:00:00Z",
              wind_dir_deg=180, wind_speed_kt=10.0)
    becmg = _g(1, "BECMG", "2026-05-02T20:00:00Z", "2026-05-02T22:00:00Z",
               wind_dir_deg=270, wind_speed_kt=12.0)
    s_pre = resolve_taf_at(_t("2026-05-02T20:30:00Z"), base, [becmg])
    assert s_pre.wind_dir_deg == 180
    s_post = resolve_taf_at(_t("2026-05-02T21:30:00Z"), base, [becmg])
    assert s_post.wind_dir_deg == 270


def test_tempo_inside_window_appended_as_caveat_no_state_change():
    base = _g(0, "BASE", "2026-05-02T18:00:00Z", "2026-05-03T18:00:00Z",
              wind_dir_deg=180, wind_speed_kt=10.0, flight_category="VFR")
    tempo = _g(1, "TEMPO", "2026-05-02T19:00:00Z", "2026-05-02T22:00:00Z",
               wind_dir_deg=200, wind_speed_kt=15.0, flight_category="MVFR")
    state = resolve_taf_at(_t("2026-05-02T20:00:00Z"), base, [tempo])
    assert state.wind_dir_deg == 180
    assert state.flight_category == "VFR"
    assert len(state.caveats) == 1
    cav = state.caveats[0]
    assert cav["group_type"] == "TEMPO"
    assert cav["flight_category"] == "MVFR"


def test_prob_caveat_carries_probability():
    base = _g(0, "BASE", "2026-05-02T18:00:00Z", "2026-05-03T18:00:00Z",
              wind_dir_deg=180, flight_category="VFR")
    prob = _g(1, "PROB30", "2026-05-02T19:00:00Z", "2026-05-02T22:00:00Z",
              probability_pct=30, visibility_sm=4.0, flight_category="MVFR")
    state = resolve_taf_at(_t("2026-05-02T20:00:00Z"), base, [prob])
    assert state.caveats[0]["probability_pct"] == 30


def test_tempo_outside_window_not_a_caveat():
    base = _g(0, "BASE", "2026-05-02T18:00:00Z", "2026-05-03T18:00:00Z",
              wind_dir_deg=180)
    tempo = _g(1, "TEMPO", "2026-05-02T19:00:00Z", "2026-05-02T20:00:00Z",
               wind_dir_deg=200)
    state = resolve_taf_at(_t("2026-05-02T22:00:00Z"), base, [tempo])
    assert state.caveats == []
