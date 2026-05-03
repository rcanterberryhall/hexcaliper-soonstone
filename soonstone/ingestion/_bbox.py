"""Shared helper: split an AWC bounding box into 4 sub-bboxes.

AWC's per-endpoint cap is 400 rows. CONUS routinely exceeds that for
stationinfo, METAR, and TAF; quartering then dedup gets us full coverage
at the cost of 4x request volume per cycle (negligible since the jobs
run every 30 min at most).
"""
from __future__ import annotations


def quartered_bboxes(bbox: str) -> list[str]:
    """Split 'south,west,north,east' into 4 sub-bboxes (SW/SE/NW/NE)."""
    s, w, n, e = [float(x) for x in bbox.split(",")]
    mid_lat = (s + n) / 2
    mid_lon = (w + e) / 2
    return [
        f"{s},{w},{mid_lat},{mid_lon}",
        f"{s},{mid_lon},{mid_lat},{e}",
        f"{mid_lat},{w},{n},{mid_lon}",
        f"{mid_lat},{mid_lon},{n},{e}",
    ]
