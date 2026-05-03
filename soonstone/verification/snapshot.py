"""build_snapshot: assemble the now / convergence / forward sections for one station."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from soonstone.models import NwsForecast, Observation, Station, Taf
from soonstone.verification.taf_resolve import ResolvedState, resolve_taf_at


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _state_to_dict(state: ResolvedState) -> dict:
    return {
        "wind_dir_deg": state.wind_dir_deg,
        "wind_speed_kt": state.wind_speed_kt,
        "wind_gust_kt": state.wind_gust_kt,
        "visibility_sm": state.visibility_sm,
        "weather": state.weather,
        "cloud_layers": state.cloud_layers,
        "ceiling_ft": state.ceiling_ft,
        "flight_category": state.flight_category,
        "caveats": state.caveats,
    }


def _now_section(session: Session, station_id: str) -> dict | None:
    obs = session.execute(
        select(Observation)
        .where(Observation.station_id == station_id)
        .order_by(Observation.observed_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if obs is None:
        return None
    return {
        "observed_at": obs.observed_at,
        "metar_type": obs.metar_type,
        "wind_dir_deg": obs.wind_dir_deg,
        "wind_speed_kt": obs.wind_speed_kt,
        "wind_gust_kt": obs.wind_gust_kt,
        "visibility_sm": obs.visibility_sm,
        "weather": obs.present_weather,
        "cloud_layers": obs.cloud_layers,
        "ceiling_ft": obs.ceiling_ft,
        "flight_category": obs.flight_category,
    }


def _convergence_section(
    session: Session, station_id: str, now: datetime
) -> list[dict]:
    window_start = _iso(now - timedelta(hours=24))
    window_end = _iso(now)

    tafs = session.execute(
        select(Taf)
        .where(
            Taf.station_id == station_id,
            Taf.issued_at >= window_start,
            Taf.issued_at <= window_end,
        )
        .order_by(Taf.issued_at)
    ).scalars().all()

    out: list[dict] = []
    for taf in tafs:
        if _parse_iso(taf.valid_to) < now:
            continue
        groups = list(taf.groups)
        if not groups:
            continue
        base = groups[0]
        change = groups[1:]
        state = resolve_taf_at(now, base, change)
        lead = (now - _parse_iso(taf.issued_at)).total_seconds() / 3600.0
        entry = {
            "issued_at": taf.issued_at,
            "amendment_type": taf.amendment_type,
            "lead_hours": round(lead, 2),
            "forecast_source": "TAF",
            **_state_to_dict(state),
        }
        out.append(entry)
    return out


def _active_taf(session: Session, station_id: str, now: datetime) -> Taf | None:
    iso_now = _iso(now)
    candidates = session.execute(
        select(Taf)
        .where(
            Taf.station_id == station_id,
            Taf.valid_from <= iso_now,
            Taf.valid_to >= iso_now,
        )
        .order_by(Taf.issued_at.desc())
    ).scalars().all()
    if not candidates:
        return None
    latest_issued = candidates[0].issued_at
    same_issued = [t for t in candidates if t.issued_at == latest_issued]
    amended = [t for t in same_issued if t.amendment_type]
    return amended[0] if amended else same_issued[0]


def _forward_taf_section(
    session: Session, station_id: str, now: datetime
) -> list[dict]:
    taf = _active_taf(session, station_id, now)
    if taf is None:
        return []
    groups = list(taf.groups)
    out: list[dict] = []
    for grp in groups:
        anchor_iso = grp.group_from if grp.group_type != "BASE" else taf.valid_from
        anchor = _parse_iso(anchor_iso)
        state = resolve_taf_at(anchor, groups[0], groups[1:])
        lead = (anchor - now).total_seconds() / 3600.0
        out.append({
            "valid_at": anchor_iso,
            "lead_hours": round(lead, 2),
            "forecast_source": "TAF",
            "group_type": grp.group_type,
            "probability_pct": grp.probability_pct,
            **_state_to_dict(state),
        })
    return out


def _forward_nws_section(
    session: Session, station_id: str, now: datetime
) -> list[dict]:
    iso_now = _iso(now)
    rows = session.execute(
        select(NwsForecast)
        .where(
            NwsForecast.station_id == station_id,
            NwsForecast.valid_to >= iso_now,
        )
        .order_by(NwsForecast.valid_from)
    ).scalars().all()
    out: list[dict] = []
    for row in rows:
        anchor = _parse_iso(row.valid_from)
        lead = (anchor - now).total_seconds() / 3600.0
        out.append({
            "valid_at": row.valid_from,
            "valid_to": row.valid_to,
            "lead_hours": round(lead, 2),
            "forecast_source": "NWS",
            "period_name": row.period_name,
            "temperature_f": row.temperature_f,
            "wind_dir": row.wind_dir,
            "wind_speed": row.wind_speed,
            "pop_pct": row.pop_pct,
            "short_forecast": row.short_forecast,
        })
    return out


def _forward_section(
    session: Session, station_id: str, now: datetime
) -> list[dict]:
    out = _forward_taf_section(session, station_id, now)
    out.extend(_forward_nws_section(session, station_id, now))
    out.sort(key=lambda x: x["valid_at"])
    return out


def _recent_section(
    session: Session, station_id: str, now: datetime
) -> list[dict]:
    """Hourly-cadence observations from the past 24h.

    For each of the past 25 hour anchors (24h ago through now), pick the
    closest observation within 90 min of the anchor. Skip hours with no
    nearby observation. Used by the consumer-mode 'past 24h' strip.
    """
    cutoff = _iso(now - timedelta(hours=25))
    rows = session.execute(
        select(Observation)
        .where(
            Observation.station_id == station_id,
            Observation.observed_at >= cutoff,
            Observation.observed_at <= _iso(now),
        )
        .order_by(Observation.observed_at)
    ).scalars().all()

    out: list[dict] = []
    for hours_ago in range(24, -1, -1):
        anchor = now - timedelta(hours=hours_ago)
        best = None
        best_diff = float("inf")
        for o in rows:
            d = abs((_parse_iso(o.observed_at) - anchor).total_seconds())
            if d < best_diff:
                best = o
                best_diff = d
        if best is None or best_diff > 90 * 60:
            continue
        out.append({
            "anchor_hour": _iso(anchor),
            "observed_at": best.observed_at,
            "temp_c": best.temp_c,
            "wind_dir_deg": best.wind_dir_deg,
            "wind_speed_kt": best.wind_speed_kt,
            "wind_gust_kt": best.wind_gust_kt,
            "visibility_sm": best.visibility_sm,
            "weather": best.present_weather,
            "cloud_layers": best.cloud_layers,
            "ceiling_ft": best.ceiling_ft,
            "flight_category": best.flight_category,
        })
    return out


def _hourly_forecast_section(
    session: Session, station_id: str, now: datetime
) -> list[dict]:
    """Hourly-cadence forecast for the next 24h, derived from the active TAF.

    Walks the TAF's change groups via resolve_taf_at at each hourly anchor.
    Stops when we exit the TAF's valid window. TAFs don't forecast
    temperature, so the consumer view will fall back to NWS for temp.
    """
    taf = _active_taf(session, station_id, now)
    if taf is None:
        return []
    groups = list(taf.groups)
    if not groups:
        return []
    base = groups[0]
    change = groups[1:]
    valid_to = _parse_iso(taf.valid_to)

    out: list[dict] = []
    for hours_ahead in range(0, 25):
        anchor = now + timedelta(hours=hours_ahead)
        if anchor > valid_to:
            break
        state = resolve_taf_at(anchor, base, change)
        out.append({
            "anchor_hour": _iso(anchor),
            "wind_dir_deg": state.wind_dir_deg,
            "wind_speed_kt": state.wind_speed_kt,
            "wind_gust_kt": state.wind_gust_kt,
            "visibility_sm": state.visibility_sm,
            "weather": state.weather,
            "cloud_layers": state.cloud_layers,
            "ceiling_ft": state.ceiling_ft,
            "flight_category": state.flight_category,
        })
    return out


def build_snapshot(
    session: Session, station_id: str, now: datetime | None = None
) -> dict | None:
    if now is None:
        now = datetime.now(timezone.utc)

    station = session.get(Station, station_id)
    if station is None:
        return None

    return {
        "station": {
            "id": station.station_id,
            "name": station.name,
            "lat": station.latitude,
            "lon": station.longitude,
        },
        "now": _now_section(session, station_id),
        "recent": _recent_section(session, station_id, now),
        "hourly": _hourly_forecast_section(session, station_id, now),
        "convergence": _convergence_section(session, station_id, now),
        "forward": _forward_section(session, station_id, now),
    }
