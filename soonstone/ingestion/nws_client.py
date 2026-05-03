"""HTTP client for the NWS public forecast API (api.weather.gov).

NWS guidance: identify with a User-Agent. No auth, no documented hard cap
on rate, but they ask for 'reasonable' -- we throttle on the calling side.
"""
from __future__ import annotations

from typing import Any

import requests

from soonstone.config import Config


class NwsClient:
    BASE = "https://api.weather.gov"

    def __init__(self, config: Config, session: requests.Session | None = None) -> None:
        self._session = session or requests.Session()
        self._session.headers.update({
            "User-Agent": config.http_user_agent,
            "Accept": "application/geo+json",
        })

    def _get(self, url: str) -> Any:
        resp = self._session.get(url, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def fetch_points(self, lat: float, lon: float) -> str:
        """Return the forecast URL for the given coords.

        NWS /points returns a small object whose `properties.forecast` is the
        URL of the 12h-period forecast endpoint for the gridpoint covering
        those coords. We cache the URL on stations.nws_forecast_url upstream
        so this only runs once per station, ever.
        """
        data = self._get(f"{self.BASE}/points/{lat},{lon}")
        return data["properties"]["forecast"]

    def fetch_forecast(self, forecast_url: str) -> list[dict]:
        """Return the periods array from a /forecast URL."""
        data = self._get(forecast_url)
        return data.get("properties", {}).get("periods", [])
