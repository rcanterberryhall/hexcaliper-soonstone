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

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            database_url=os.environ.get(
                "DATABASE_URL", "sqlite:///./data/soonstone.db"
            ),
            bbox_south=float(os.environ.get("SOONSTONE_BBOX_SOUTH", "24.0")),
            bbox_west=float(os.environ.get("SOONSTONE_BBOX_WEST", "-88.0")),
            bbox_north=float(os.environ.get("SOONSTONE_BBOX_NORTH", "31.5")),
            bbox_east=float(os.environ.get("SOONSTONE_BBOX_EAST", "-79.5")),
            log_level=os.environ.get("SOONSTONE_LOG_LEVEL", "INFO"),
            awc_base_url=os.environ.get(
                "AWC_BASE_URL", "https://aviationweather.gov/api/data"
            ),
            http_user_agent=os.environ.get(
                "SOONSTONE_USER_AGENT",
                "soonstone/0.0.1 (forecast verification; +weather.hexcaliper.com)",
            ),
        )

    @property
    def bbox_query(self) -> str:
        """AWC API expects bbox as 'south,west,north,east'."""
        return f"{self.bbox_south},{self.bbox_west},{self.bbox_north},{self.bbox_east}"
