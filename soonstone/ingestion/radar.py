"""fetch_radar_images: scan recent observations missing radar_image_path,
fetch a per-station radar PNG from IEM, save to hot storage, update the path.

Designed to start collecting NOW so when the rendering / archival pipeline is
built later (per #5 long-term), we already have history. The frontend does
not yet read radar_image_path; that's fine -- the data accumulates regardless.

Hot path: ./data/radar/hot/{station_id}/{YYYYMMDDHHMM}Z.png
Daily archival to animated WebP is the next phase (not in this commit).
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from soonstone.config import Config
from soonstone.ingestion.iem_radar import IemRadarClient, _round_to_frame
from soonstone.ingestion.results import RadarResult
from soonstone.models import Observation, Station

log = logging.getLogger(__name__)

# Throttle to ~5 RPS to be polite to IEM (they're a free public service).
_REQUEST_GAP_SEC = 0.2

# How far back to look for observations missing radar.
# Default: 6h. Past that, the radar frame may have rolled out of IEM's cache.
_LOOKBACK_HOURS = 6


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _hot_path_for(radar_dir: Path, station_id: str, observed_at_iso: str) -> Path:
    ts = _round_to_frame(observed_at_iso)  # YYYYMMDDHHMM
    return radar_dir / "hot" / station_id / f"{ts}Z.png"


def fetch_radar_images(
    session: Session, iem_client: IemRadarClient, config: Config
) -> RadarResult:
    radar_dir = Path(config.radar_dir)
    cutoff = _iso(datetime.now(timezone.utc) - timedelta(hours=_LOOKBACK_HOURS))

    # Recent METARs without an image yet, joined with their station for lat/lon.
    rows = session.execute(
        select(Observation, Station)
        .join(Station, Observation.station_id == Station.station_id)
        .where(
            Observation.observed_at >= cutoff,
            Observation.radar_image_path.is_(None),
            Station.active == 1,
        )
        .order_by(Observation.observed_at.desc())
    ).all()

    scanned = len(rows)
    fetched = 0
    skipped = 0
    failed = 0

    for obs, station in rows:
        target = _hot_path_for(radar_dir, station.station_id, obs.observed_at)
        if target.exists():
            # Already on disk from a prior run; just record the path.
            session.execute(
                update(Observation)
                .where(
                    Observation.station_id == obs.station_id,
                    Observation.observed_at == obs.observed_at,
                )
                .values(radar_image_path=str(target.relative_to(radar_dir.parent)))
            )
            skipped += 1
            continue

        body = iem_client.fetch(
            lat=station.latitude,
            lon=station.longitude,
            observed_at_iso=obs.observed_at,
        )
        if body is None:
            failed += 1
            time.sleep(_REQUEST_GAP_SEC)
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        session.execute(
            update(Observation)
            .where(
                Observation.station_id == obs.station_id,
                Observation.observed_at == obs.observed_at,
            )
            .values(radar_image_path=str(target.relative_to(radar_dir.parent)))
        )
        fetched += 1
        time.sleep(_REQUEST_GAP_SEC)

    session.commit()
    return RadarResult(
        observations_scanned=scanned,
        images_fetched=fetched,
        images_skipped_existing=skipped,
        fetch_failures=failed,
    )
