"""Verify metar_parser.parse_metar returns dicts matching the Observation schema."""
from __future__ import annotations

import pytest

from soonstone.parsers.metar_parser import parse_metar


REQUIRED_KEYS = {
    "station_id",
    "observed_at",
    "raw_metar",
    "metar_type",
    "temp_c",
    "dewpoint_c",
    "wind_dir_deg",
    "wind_speed_kt",
    "wind_gust_kt",
    "visibility_sm",
    "altimeter_inhg",
    "present_weather",
    "cloud_layers",
    "ceiling_ft",
    "flight_category",
}


def test_all_fixtures_parse_into_required_shape(metar_fixtures):
    assert metar_fixtures, "no METAR fixtures captured — run scripts/capture_fixtures.py"
    for name, raw in metar_fixtures.items():
        parsed = parse_metar(raw)
        missing = REQUIRED_KEYS - parsed.keys()
        assert not missing, f"{name}: missing keys {missing}"
        assert parsed["raw_metar"] == raw
        # The METAR header may start with the literal METAR or SPECI keyword
        # before the station id; the parsed station_id must come from the
        # report itself, not from string slicing.
        assert parsed["station_id"], f"{name}: empty station_id"
        assert parsed["observed_at"].endswith("Z"), f"{name}: observed_at not Z-suffixed"
        if parsed["present_weather"] is not None:
            assert isinstance(parsed["present_weather"], str)
            assert parsed["present_weather"].startswith("[")


def test_kmia_sample_extracts_temp_and_wind():
    raw = (
        "KMIA 021753Z 10010KT 10SM FEW030 SCT250 28/22 A3007 "
        "RMK AO2 SLP180 T02780222"
    )
    parsed = parse_metar(raw)
    assert parsed["station_id"] == "KMIA"
    assert parsed["wind_dir_deg"] == 100
    assert parsed["wind_speed_kt"] == 10.0
    assert parsed["wind_gust_kt"] is None
    assert parsed["visibility_sm"] == 10.0
    # The metar library prefers the high-precision T-group from the remarks
    # (T02780222 -> 27.8/22.2) over the whole-degree group (28/22).
    assert parsed["temp_c"] == pytest.approx(27.8, abs=0.05)
    assert parsed["dewpoint_c"] == pytest.approx(22.2, abs=0.05)
    assert parsed["altimeter_inhg"] == pytest.approx(30.07, abs=0.01)
    assert parsed["flight_category"] == "VFR"


def test_metar_with_gust_extracts_gust_value():
    raw = "KTPA 021753Z 25018G28KT 10SM SCT028 28/23 A3008"
    parsed = parse_metar(raw)
    assert parsed["wind_speed_kt"] == 18.0
    assert parsed["wind_gust_kt"] == 28.0


def test_speci_marks_metar_type():
    raw = "SPECI KMIA 021820Z 18025G40KT 1SM +TSRA BKN015CB BKN025 23/22 A2998"
    parsed = parse_metar(raw)
    assert parsed["metar_type"] == "SPECI"
    assert parsed["flight_category"] == "IFR"  # 1 SM, ceiling 1500 = IFR
