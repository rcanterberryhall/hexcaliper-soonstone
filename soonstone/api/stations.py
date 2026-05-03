"""GET /api/stations -- GeoJSON FeatureCollection of active stations."""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify
from sqlalchemy import select

from soonstone.db import make_session_factory
from soonstone.models import Station

bp = Blueprint("stations", __name__, url_prefix="/api")


@bp.get("/stations")
def list_stations():
    engine = current_app.extensions["soonstone_engine"]
    sf = make_session_factory(engine)
    with sf() as session:
        rows = session.execute(
            select(Station).where(Station.active == 1)
        ).scalars().all()

    features = [
        {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [row.longitude, row.latitude],
            },
            "properties": {
                "id": row.station_id,
                "name": row.name,
                "state": row.state,
                "taf_site": bool(row.taf_site),
                "elevation_m": row.elevation_m,
            },
        }
        for row in rows
    ]
    return jsonify({"type": "FeatureCollection", "features": features})
