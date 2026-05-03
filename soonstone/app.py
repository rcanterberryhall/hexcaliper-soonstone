"""Flask app factory for soonstone.

For Plan 2 the app exposes shared resources (DB engine, AwcClient, Config) on
`app.extensions` but registers no routes. Plan 3 will register the API
blueprint here.
"""
from __future__ import annotations

from typing import Optional

from flask import Flask

from soonstone.api.health import bp as health_bp
from soonstone.api.snapshot import bp as snapshot_bp
from soonstone.api.stations import bp as stations_bp
from soonstone.config import Config
from soonstone.db import create_engine_with_pragmas
from soonstone.health import JobHealth
from soonstone.ingestion.awc_client import AwcClient
from soonstone.logging import configure_logging


def create_app(config: Optional[Config] = None) -> Flask:
    cfg = config or Config.from_env()
    configure_logging(cfg.log_level)

    app = Flask("soonstone")
    app.config.update(SOONSTONE_CONFIG=cfg)

    engine = create_engine_with_pragmas(cfg.database_url)
    awc = AwcClient(config=cfg)

    app.extensions["soonstone_config"] = cfg
    app.extensions["soonstone_engine"] = engine
    app.extensions["soonstone_awc_client"] = awc
    app.extensions["soonstone_health"] = JobHealth()

    app.register_blueprint(stations_bp)
    app.register_blueprint(snapshot_bp)
    app.register_blueprint(health_bp)

    return app
