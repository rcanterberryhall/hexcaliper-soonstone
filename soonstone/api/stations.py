"""GET /api/stations -- GeoJSON FeatureCollection of active stations."""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify
from sqlalchemy import select

from soonstone.db import make_session_factory
from soonstone.models import Observation, Station

bp = Blueprint("stations", __name__, url_prefix="/api")


@bp.get("/stations")
def list_stations():
    engine = current_app.extensions["soonstone_engine"]
    sf = make_session_factory(engine)

    latest_cat = (
        select(Observation.flight_category)
        .where(Observation.station_id == Station.station_id)
        .order_by(Observation.observed_at.desc())
        .limit(1)
        .correlate(Station)
        .scalar_subquery()
        .label("flight_category")
    )
    stmt = select(Station, latest_cat).where(Station.active == 1)

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
            },
        }
        for station, flight_category in rows
    ]
    return jsonify({"type": "FeatureCollection", "features": features})
