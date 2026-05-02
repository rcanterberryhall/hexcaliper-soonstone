"""HTTP client for the AWC (Aviation Weather Center) public API.

One method per endpoint. Bounding-box queries return all matching rows in a
single request — this is the polite ingest pattern AWC's docs recommend.
"""
from __future__ import annotations

from typing import Any

import requests

from soonstone.config import Config


class AwcClient:
    def __init__(self, config: Config, session: requests.Session | None = None) -> None:
        self._config = config
        self._session = session or requests.Session()
        self._session.headers.update({"User-Agent": config.http_user_agent})

    def _get(self, endpoint: str, params: dict[str, Any]) -> Any:
        url = f"{self._config.awc_base_url}/{endpoint}"
        resp = self._session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def fetch_metars(self, bbox: str) -> list[dict]:
        return self._get("metar", {"bbox": bbox, "format": "json"})

    def fetch_tafs(self, bbox: str) -> list[dict]:
        return self._get("taf", {"bbox": bbox, "format": "json"})

    def fetch_stations(self, bbox: str) -> list[dict]:
        return self._get("stationinfo", {"bbox": bbox, "format": "json"})
