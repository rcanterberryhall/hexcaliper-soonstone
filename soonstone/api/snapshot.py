"""GET /api/stations/<station_id>/snapshot -- now + convergence + forward."""
from __future__ import annotations

from flask import Blueprint, abort, current_app, jsonify

from soonstone.db import make_session_factory
from soonstone.verification.snapshot import build_snapshot

bp = Blueprint("snapshot", __name__, url_prefix="/api")


@bp.get("/stations/<string:station_id>/snapshot")
def get_snapshot(station_id: str):
    engine = current_app.extensions["soonstone_engine"]
    sf = make_session_factory(engine)
    with sf() as session:
        snap = build_snapshot(session, station_id.upper())
    if snap is None:
        abort(404, description=f"unknown station: {station_id}")
    return jsonify(snap)
