"""refresh_stations: pull AWC station list, upsert into stations table."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from soonstone.config import Config
from soonstone.ingestion.awc_client import AwcClient
from soonstone.ingestion.results import StationsResult
from soonstone.models import Station


def _now_iso_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _project(awc_row: dict, now: str) -> dict:
    return {
        "station_id": awc_row["icaoId"],
        "name": awc_row.get("site"),
        "latitude": float(awc_row["lat"]),
        "longitude": float(awc_row["lon"]),
        "elevation_m": (
            float(awc_row["elev"]) if awc_row.get("elev") is not None else None
        ),
        "state": awc_row.get("state"),
        "station_type": awc_row.get("type"),
        "taf_site": 1 if awc_row.get("tafSite") else 0,
        "active": 1,
        "last_seen": now,
    }


def _quartered_bboxes(bbox: str) -> list[str]:
    """Split a 'south,west,north,east' bbox into 4 sub-bboxes (SW/SE/NW/NE).

    AWC's stationinfo endpoint caps each response at 400 rows. CONUS exceeds
    that, so we fetch in quadrants and dedup by icaoId. For small bboxes
    (Florida) the call count goes from 1 to 4 with negligible cost since
    refresh_stations runs weekly.
    """
    s, w, n, e = [float(x) for x in bbox.split(",")]
    mid_lat = (s + n) / 2
    mid_lon = (w + e) / 2
    return [
        f"{s},{w},{mid_lat},{mid_lon}",
        f"{s},{mid_lon},{mid_lat},{e}",
        f"{mid_lat},{w},{n},{mid_lon}",
        f"{mid_lat},{mid_lon},{n},{e}",
    ]


def refresh_stations(
    session: Session, awc_client: AwcClient, config: Config
) -> StationsResult:
    rows: list[dict] = []
    seen: set[str] = set()
    for sub in _quartered_bboxes(config.bbox_query):
        for raw in awc_client.fetch_stations(bbox=sub):
            icao = raw.get("icaoId")
            if not icao or icao in seen:
                continue
            seen.add(icao)
            rows.append(raw)
    now = _now_iso_utc()

    existing_ids = set(session.execute(select(Station.station_id)).scalars().all())

    inserted = 0
    updated = 0
    for raw in rows:
        projected = _project(raw, now)
        if projected["station_id"] in existing_ids:
            session.execute(
                update(Station)
                .where(Station.station_id == projected["station_id"])
                .values(last_seen=now)
            )
            updated += 1
        else:
            session.execute(sqlite_insert(Station).values(**projected))
            inserted += 1
    session.commit()

    return StationsResult(fetched=len(rows), inserted=inserted, updated=updated)
