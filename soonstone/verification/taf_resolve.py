"""Resolve a TAF to its predicted state at a given target time.

Pure function over the parsed TAF + group rows from the DB (passed as dicts
or as SQLAlchemy ORM rows -- we use attribute access via getattr to support
both).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ResolvedState:
    wind_dir_deg: int | None = None
    wind_speed_kt: float | None = None
    wind_gust_kt: float | None = None
    visibility_sm: float | None = None
    weather: str | None = None
    cloud_layers: str | None = None
    ceiling_ft: int | None = None
    flight_category: str | None = None
    caveats: list[dict] = field(default_factory=list)


_STATE_FIELDS = (
    "wind_dir_deg", "wind_speed_kt", "wind_gust_kt", "visibility_sm",
    "weather", "cloud_layers", "ceiling_ft", "flight_category",
)


def _get(g: Any, key: str, default=None):
    if isinstance(g, dict):
        return g.get(key, default)
    return getattr(g, key, default)


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _apply(state: ResolvedState, group: Any) -> None:
    for f in _STATE_FIELDS:
        v = _get(group, f)
        if v is not None:
            setattr(state, f, v)


def _caveat(group: Any) -> dict:
    out = {f: _get(group, f) for f in _STATE_FIELDS}
    out["group_type"] = _get(group, "group_type")
    out["group_from"] = _get(group, "group_from")
    out["group_to"] = _get(group, "group_to")
    out["probability_pct"] = _get(group, "probability_pct")
    return out


def resolve_taf_at(
    target_time: datetime, base_group: Any, change_groups: list[Any]
) -> ResolvedState:
    state = ResolvedState()
    _apply(state, base_group)

    for grp in change_groups:
        gtype = _get(grp, "group_type")
        gf = _parse_iso(_get(grp, "group_from"))
        gt = _parse_iso(_get(grp, "group_to"))

        if gtype == "FM":
            if gf <= target_time:
                _apply(state, grp)
        elif gtype == "BECMG":
            if target_time > gt:
                _apply(state, grp)
            elif gf <= target_time <= gt:
                midpoint = gf + (gt - gf) / 2
                if target_time >= midpoint:
                    _apply(state, grp)
        elif gtype == "TEMPO" or (gtype and gtype.startswith("PROB")):
            if gf <= target_time <= gt:
                state.caveats.append(_caveat(grp))

    return state
