"""METAR parser: wraps the PyPI `metar` library and projects onto the
Observation schema in soonstone/models.py.

We do NOT trust the metar library's repr — we explicitly map the fields we
care about and JSON-serialize the multi-valued ones.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from metar import Metar


def _flight_category(visibility_sm: float | None, ceiling_ft: int | None) -> str | None:
    """Standard FAA flight categories.

    LIFR: vis < 1 SM or ceiling < 500 ft
    IFR:  1 <= vis < 3 SM or 500 <= ceiling < 1000 ft
    MVFR: 3 <= vis <= 5 SM or 1000 <= ceiling <= 3000 ft
    VFR:  vis > 5 SM and ceiling > 3000 ft (or no ceiling reported)
    """
    if visibility_sm is None and ceiling_ft is None:
        return None

    vis = visibility_sm if visibility_sm is not None else 99.0
    ceil = ceiling_ft if ceiling_ft is not None else 99999

    if vis < 1 or ceil < 500:
        return "LIFR"
    if vis < 3 or ceil < 1000:
        return "IFR"
    if vis <= 5 or ceil <= 3000:
        return "MVFR"
    return "VFR"


def _ceiling_from_layers(layers: list[dict]) -> int | None:
    """Lowest BKN or OVC base in feet AGL, else None."""
    for layer in layers:
        if layer.get("cover") in {"BKN", "OVC", "VV"}:
            base = layer.get("base_ft")
            if base is not None:
                return int(base)
    return None


def _cloud_layers(metar: Metar.Metar) -> list[dict]:
    out: list[dict] = []
    for cover, height, cloud_type in metar.sky:
        layer: dict[str, Any] = {"cover": cover}
        if height is not None:
            try:
                layer["base_ft"] = int(height.value("FT"))
            except Exception:
                pass
        if cloud_type:
            layer["type"] = cloud_type
        out.append(layer)
    return out


def _present_weather(metar: Metar.Metar) -> list[str]:
    out: list[str] = []
    for w in metar.weather:
        # metar lib returns 6-tuples: (intensity, descriptor, precipitation, obscuration, other, _)
        token = "".join(p for p in w if p)
        if token:
            out.append(token)
    return out


def _detect_metar_type(raw: str) -> str:
    return "SPECI" if raw.lstrip().startswith("SPECI ") else "METAR"


def _isoformat_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_metar(raw: str) -> dict:
    """Parse a raw METAR string into a dict matching Observation columns.

    Returns keys for every column in observations except station-FK metadata
    (station_id is taken from the report itself) and bookkeeping columns
    (ingested_at, radar_image_path).
    """
    raw = raw.strip()
    metar = Metar.Metar(raw, strict=False)

    cloud_layers = _cloud_layers(metar)
    ceiling_ft = _ceiling_from_layers(cloud_layers)

    visibility_sm = metar.vis.value("SM") if metar.vis else None
    temp_c = metar.temp.value("C") if metar.temp else None
    dewpoint_c = metar.dewpt.value("C") if metar.dewpt else None
    altimeter_inhg = metar.press.value("IN") if metar.press else None

    wind_dir_deg = int(metar.wind_dir.value()) if metar.wind_dir else None
    wind_speed_kt = float(metar.wind_speed.value("KT")) if metar.wind_speed else None
    wind_gust_kt = float(metar.wind_gust.value("KT")) if metar.wind_gust else None

    present_weather = _present_weather(metar)
    observed_at = _isoformat_utc(metar.time.replace(tzinfo=timezone.utc) if metar.time.tzinfo is None else metar.time)

    return {
        "station_id": metar.station_id,
        "observed_at": observed_at,
        "raw_metar": raw,
        "metar_type": _detect_metar_type(raw),
        "temp_c": temp_c,
        "dewpoint_c": dewpoint_c,
        "wind_dir_deg": wind_dir_deg,
        "wind_speed_kt": wind_speed_kt,
        "wind_gust_kt": wind_gust_kt,
        "visibility_sm": visibility_sm,
        "altimeter_inhg": altimeter_inhg,
        "precip_1hr_in": None,
        "present_weather": json.dumps(present_weather) if present_weather else None,
        "cloud_layers": json.dumps(cloud_layers) if cloud_layers else None,
        "ceiling_ft": ceiling_ft,
        "flight_category": _flight_category(visibility_sm, ceiling_ft),
    }
