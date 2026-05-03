"""Env-driven configuration for soonstone.

All configuration flows from environment variables (docker-compose-friendly).
Defaults target local development with a SQLite file under ./data/.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    database_url: str
    # Florida bbox: (south, west, north, east)
    bbox_south: float
    bbox_west: float
    bbox_north: float
    bbox_east: float
    log_level: str
    awc_base_url: str
    http_user_agent: str
    radar_dir: str = "./data/radar"
    iem_base_url: str = "https://mesonet.agron.iastate.edu"

    @classmethod
    def from_env(cls) -> "Config":
        database_url = os.environ.get(
            "DATABASE_URL", "sqlite:///./data/soonstone.db"
        )
        # Default radar dir = sibling of the SQLite DB file, so the same
        # volume mount that holds /data/soonstone.db also holds /data/radar.
        default_radar_dir = "./data/radar"
        if database_url.startswith("sqlite:///"):
            from pathlib import Path as _P
            default_radar_dir = str(_P(database_url[len("sqlite:///"):]).parent / "radar")
        return cls(
            database_url=database_url,
            # CONUS bbox (south, west, north, east). v0 used Florida (24.0,-88.0,31.5,-79.5).
            bbox_south=float(os.environ.get("SOONSTONE_BBOX_SOUTH", "24.5")),
            bbox_west=float(os.environ.get("SOONSTONE_BBOX_WEST", "-125.0")),
            bbox_north=float(os.environ.get("SOONSTONE_BBOX_NORTH", "49.4")),
            bbox_east=float(os.environ.get("SOONSTONE_BBOX_EAST", "-66.9")),
            log_level=os.environ.get("SOONSTONE_LOG_LEVEL", "INFO"),
            awc_base_url=os.environ.get(
                "AWC_BASE_URL", "https://aviationweather.gov/api/data"
            ),
            http_user_agent=os.environ.get(
                "SOONSTONE_USER_AGENT",
                "soonstone/0.0.1 (forecast verification; +soonstone.hexcaliper.com)",
            ),
            radar_dir=os.environ.get("SOONSTONE_RADAR_DIR", default_radar_dir),
            iem_base_url=os.environ.get(
                "IEM_BASE_URL", "https://mesonet.agron.iastate.edu"
            ),
        )

    @property
    def bbox_query(self) -> str:
        """AWC API expects bbox as 'south,west,north,east'."""
        return f"{self.bbox_south},{self.bbox_west},{self.bbox_north},{self.bbox_east}"
