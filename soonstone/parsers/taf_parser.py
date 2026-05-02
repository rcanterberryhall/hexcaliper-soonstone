"""Hand-rolled TAF parser.

Built incrementally. This file currently handles:
  - Header (station_id, issued_at, valid_from/valid_to, amendment_type)
  - Base group (the body of the TAF before the first FM/BECMG/TEMPO/PROB group)

Future additions (later tasks): FM, BECMG, TEMPO, PROB30/PROB40 change groups.

TAF time tokens use a DDHH format relative to the current month/year. We
resolve them against the TAF's issuance time, accounting for month rollover
when the day number wraps.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any


_HEADER_RE = re.compile(
    r"""
    ^\s*
    (?:TAF\s+)?
    (?P<amend>(?:AMD|COR|RTD)\s+)?
    (?P<station>[A-Z][A-Z0-9]{3})\s+
    (?P<issued>\d{6})Z\s+
    (?P<valid_from>\d{4})/(?P<valid_to>\d{4})\b
    """,
    re.VERBOSE,
)

_WIND_RE = re.compile(
    r"\b(?P<dir>VRB|\d{3})(?P<spd>\d{2,3})(?:G(?P<gust>\d{2,3}))?KT\b"
)
_VIS_RE = re.compile(r"\b(?P<vis>P?6SM|\d{1,2}SM|\d/\dSM|M?1/\dSM)\b")
_CLOUD_RE = re.compile(
    r"\b(?P<cover>FEW|SCT|BKN|OVC|SKC|CLR|VV)(?P<height>\d{3})(?P<type>CB|TCU)?\b"
)


def _parse_dd_hh(token: str, anchor: datetime) -> datetime:
    """Resolve a DDHH TAF token relative to anchor (the issuance time).

    If the day number is less than the anchor's day, assume next-month rollover.
    """
    day = int(token[:2])
    hour = int(token[2:])
    add_day = 0
    if hour == 24:
        hour = 0
        add_day = 1

    candidate_month = anchor.month
    candidate_year = anchor.year
    # If day already passed in current month, bump to next.
    if day < anchor.day:
        if candidate_month == 12:
            candidate_month = 1
            candidate_year += 1
        else:
            candidate_month += 1

    candidate = datetime(
        candidate_year, candidate_month, day, hour, 0, 0, tzinfo=timezone.utc
    )
    candidate += timedelta(days=add_day)
    return candidate


def _isoformat_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_visibility(token: str) -> float:
    if token.startswith("P"):
        token = token[1:]  # P6SM -> 6SM
    if token.startswith("M"):
        token = token[1:]
    if "/" in token:
        num, denom = token[:-2].split("/")
        return float(num) / float(denom)
    return float(token[:-2])


def _parse_clouds(text: str) -> list[dict]:
    layers: list[dict] = []
    for m in _CLOUD_RE.finditer(text):
        cover = m.group("cover")
        if cover in {"SKC", "CLR"}:
            return [{"cover": cover}]
        layer: dict[str, Any] = {
            "cover": cover,
            "base_ft": int(m.group("height")) * 100,
        }
        if m.group("type"):
            layer["type"] = m.group("type")
        layers.append(layer)
    return layers


def _ceiling_from_layers(layers: list[dict]) -> int | None:
    for layer in layers:
        if layer.get("cover") in {"BKN", "OVC", "VV"}:
            return layer.get("base_ft")
    return None


def _flight_category(visibility_sm: float | None, ceiling_ft: int | None) -> str | None:
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


def _parse_group_body(body: str) -> dict:
    """Extract wind/vis/clouds from the text body of one group."""
    out: dict[str, Any] = {
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

    wind = _WIND_RE.search(body)
    if wind:
        d = wind.group("dir")
        out["wind_dir_deg"] = None if d == "VRB" else int(d)
        out["wind_speed_kt"] = float(wind.group("spd"))
        if wind.group("gust"):
            out["wind_gust_kt"] = float(wind.group("gust"))

    vis = _VIS_RE.search(body)
    if vis:
        out["visibility_sm"] = _parse_visibility(vis.group("vis"))

    layers = _parse_clouds(body)
    if layers:
        out["cloud_layers"] = json.dumps(layers)
        out["ceiling_ft"] = _ceiling_from_layers(layers)

    out["flight_category"] = _flight_category(out["visibility_sm"], out["ceiling_ft"])
    return out


def parse_taf(raw: str) -> dict:
    raw = raw.strip()
    header = _HEADER_RE.match(raw)
    if not header:
        raise ValueError(f"could not parse TAF header from: {raw[:80]!r}")

    issued = header.group("issued")
    issued_day = int(issued[:2])
    issued_hour = int(issued[2:4])
    issued_minute = int(issued[4:])
    now = datetime.now(timezone.utc)
    anchor = datetime(
        now.year, now.month, issued_day, issued_hour, issued_minute,
        0, tzinfo=timezone.utc,
    )
    # If the resolved day is in the future relative to now, the TAF was issued last month.
    if anchor > now + timedelta(hours=2):
        if anchor.month == 1:
            anchor = anchor.replace(year=anchor.year - 1, month=12)
        else:
            anchor = anchor.replace(month=anchor.month - 1)
    issued_at = anchor

    valid_from = _parse_dd_hh(header.group("valid_from"), issued_at)
    valid_to = _parse_dd_hh(header.group("valid_to"), issued_at)

    body_start = header.end()
    body = raw[body_start:].strip()

    base_body = _parse_group_body(body)
    base_group = {
        "group_index": 0,
        "group_type": "BASE",
        "group_from": _isoformat_utc(valid_from),
        "group_to": _isoformat_utc(valid_to),
        **base_body,
    }

    return {
        "station_id": header.group("station"),
        "issued_at": _isoformat_utc(issued_at),
        "valid_from": _isoformat_utc(valid_from),
        "valid_to": _isoformat_utc(valid_to),
        "amendment_type": (header.group("amend") or "").strip() or None,
        "raw_taf": raw,
        "parse_method": "deterministic",
        "parse_warnings": None,
        "groups": [base_group],
    }
