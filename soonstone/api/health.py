"""GET /health -- 200 if ingest_metars and ingest_tafs both succeeded recently."""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify

bp = Blueprint("health", __name__)

_REQUIRED = ["ingest_metars", "ingest_tafs"]
_MAX_AGE_MIN = 90


@bp.get("/health")
def health():
    h = current_app.extensions["soonstone_health"]
    ok = h.is_healthy(_REQUIRED, max_age_minutes=_MAX_AGE_MIN)
    payload = {"status": "ok" if ok else "stale", **h.snapshot()}
    return jsonify(payload), (200 if ok else 503)
