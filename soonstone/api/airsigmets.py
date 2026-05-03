"""GET /api/airsigmets -- serve the cached AWC AIRMET/SIGMET FeatureCollection."""
from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, jsonify, send_file

bp = Blueprint("airsigmets", __name__, url_prefix="/api")


@bp.get("/airsigmets")
def get_airsigmets():
    cfg = current_app.extensions["soonstone_config"]
    target = Path(cfg.radar_dir).parent / "airsigmets" / "current.json"
    if not target.exists():
        # No ingest has run yet; return an empty collection so the frontend
        # can render gracefully instead of erroring.
        return jsonify({"type": "FeatureCollection", "features": []})
    resp = send_file(target, mimetype="application/json")
    resp.headers["Cache-Control"] = "public, max-age=300"
    return resp
