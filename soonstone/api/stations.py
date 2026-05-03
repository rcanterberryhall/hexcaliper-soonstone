"""GET /api/stations -- GeoJSON FeatureCollection of active stations.

By default returns stations whose latest observation is fresher than
SOONSTONE_DEFAULT_STALE_HOURS (6h). Override with ?stale_h=N or
?include_stale=1 to see the full catalog.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import select

from soonstone.db import make_session_factory
from soonstone.models import Observation, Station

bp = Blueprint("stations", __name__, url_prefix="/api")

DEFAULT_STALE_HOURS = 6


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


@bp.get("/stations")
def list_stations():
    engine = current_app.extensions["soonstone_engine"]
    sf = make_session_factory(engine)

    if request.args.get("include_stale") in ("1", "true", "yes"):
        stale_threshold_iso = None
    else:
        try:
            stale_h = float(request.args.get("stale_h", DEFAULT_STALE_HOURS))
        except (TypeError, ValueError):
            stale_h = DEFAULT_STALE_HOURS
        cutoff = datetime.now(timezone.utc) - timedelta(hours=stale_h)
        stale_threshold_iso = _iso(cutoff)

    latest_cat = (
        select(Observation.flight_category)
        .where(Observation.station_id == Station.station_id)
        .order_by(Observation.observed_at.desc())
        .limit(1)
        .correlate(Station)
        .scalar_subquery()
        .label("flight_category")
    )
    latest_obs = (
        select(Observation.observed_at)
        .where(Observation.station_id == Station.station_id)
        .order_by(Observation.observed_at.desc())
        .limit(1)
        .correlate(Station)
        .scalar_subquery()
        .label("latest_observed_at")
    )
    stmt = select(Station, latest_cat, latest_obs).where(Station.active == 1)
    if stale_threshold_iso is not None:
        stmt = stmt.where(latest_obs >= stale_threshold_iso)

    with sf() as session:
        rows = session.execute(stmt).all()

    features = [
        {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [station.longitude, station.latitude],
            },
            "properties": {
                "id": station.station_id,
                "name": station.name,
                "state": station.state,
                "taf_site": bool(station.taf_site),
                "elevation_m": station.elevation_m,
                "flight_category": flight_category,
                "latest_observed_at": latest,
            },
        }
        for station, flight_category, latest in rows
    ]
    return jsonify({"type": "FeatureCollection", "features": features})
