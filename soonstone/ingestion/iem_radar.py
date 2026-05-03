"""IEM radar imagery client.

Fetches a static reflectivity image centered on a station's lat/lon at a
specific UTC timestamp. Returns the PNG bytes on success, None on any failure
(logged at WARNING). Radar imagery is decoration -- METAR ingestion stays
canonical and is never blocked by a radar fetch failure.

URL pattern (IEM GIS radmap):
  {base}/GIS/radmap.php?bbox={w},{s},{e},{n}&width=400&height=300
        &layers[]=nexrad-n0r&layers[]=usstates&ts={YYYYMMDDHHMM}

If IEM rotates their endpoint we fix the URL here without touching the
caller.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import requests

from soonstone.config import Config

log = logging.getLogger(__name__)

# Half-width of the bbox we crop around each station, in degrees.
# 0.5 deg ~ 35 mi N-S and ~30-40 mi E-W in CONUS latitudes.
_BBOX_HALF_DEG = 0.5

# Round the requested radar frame to the nearest 5 minutes (IEM serves
# composite reflectivity at 5-min cadence).
_FRAME_INTERVAL_MIN = 5


def _round_to_frame(observed_at_iso: str) -> str:
    """Convert ISO 8601 'YYYY-MM-DDTHH:MM:SSZ' to the IEM ts param 'YYYYMMDDHHMM'.

    Rounds DOWN to the nearest 5-min boundary so we always ask for a frame
    that has already been published.
    """
    dt = datetime.fromisoformat(observed_at_iso.replace("Z", "+00:00"))
    minute = (dt.minute // _FRAME_INTERVAL_MIN) * _FRAME_INTERVAL_MIN
    return f"{dt.year:04d}{dt.month:02d}{dt.day:02d}{dt.hour:02d}{minute:02d}"


def _bbox(lat: float, lon: float) -> str:
    w = lon - _BBOX_HALF_DEG
    s = lat - _BBOX_HALF_DEG
    e = lon + _BBOX_HALF_DEG
    n = lat + _BBOX_HALF_DEG
    return f"{w},{s},{e},{n}"


class IemRadarClient:
    def __init__(self, config: Config, session: requests.Session | None = None) -> None:
        self._config = config
        self._session = session or requests.Session()
        self._session.headers.update({"User-Agent": config.http_user_agent})

    def build_url(self, lat: float, lon: float, observed_at_iso: str) -> str:
        ts = _round_to_frame(observed_at_iso)
        return (
            f"{self._config.iem_base_url}/GIS/radmap.php"
            f"?bbox={_bbox(lat, lon)}"
            f"&width=400&height=300"
            f"&layers[]=nexrad-n0r&layers[]=usstates"
            f"&ts={ts}"
        )

    def fetch(
        self, lat: float, lon: float, observed_at_iso: str
    ) -> Optional[bytes]:
        url = self.build_url(lat, lon, observed_at_iso)
        try:
            resp = self._session.get(url, timeout=20)
            resp.raise_for_status()
        except requests.RequestException as exc:
            log.warning(
                "iem_radar_http_failed",
                extra={"job": "fetch_radar_images", "url": url, "error": str(exc)},
            )
            return None
        body = resp.content
        # IEM occasionally returns a 200 with an HTML error body. Sniff the PNG
        # magic bytes; treat anything else as a failed fetch.
        if not body.startswith(b"\x89PNG"):
            log.warning(
                "iem_radar_non_png",
                extra={
                    "job": "fetch_radar_images",
                    "url": url,
                    "content_type": resp.headers.get("content-type"),
                    "len": len(body),
                },
            )
            return None
        return body
