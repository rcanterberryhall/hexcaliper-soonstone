"""GET / -- serve the static index.html."""
from __future__ import annotations

from flask import Blueprint, send_from_directory

bp = Blueprint("index", __name__)


@bp.get("/")
def index():
    from soonstone.app import _STATIC_DIR
    return send_from_directory(_STATIC_DIR, "index.html")
