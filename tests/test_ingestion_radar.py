"""Tests for fetch_radar_images: scans recent obs, writes hot PNG, updates path."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from soonstone.config import Config
from soonstone.db import Base, create_engine_with_pragmas, make_session_factory
from soonstone.ingestion.radar import fetch_radar_images
from soonstone.models import Observation, Station


PNG_MAGIC = b"\x89PNG\r\n\x1a\nfakebody"


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr("soonstone.ingestion.radar._REQUEST_GAP_SEC", 0)
    db_url = f"sqlite:///{tmp_path / 'radar.db'}"
    engine = create_engine_with_pragmas(db_url)
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    radar_dir = tmp_path / "data" / "radar"

    cfg_kwargs = dict(
        database_url=db_url,
        bbox_south=24.0, bbox_west=-88.0, bbox_north=31.5, bbox_east=-79.5,
        log_level="INFO",
        awc_base_url="https://aviationweather.gov/api/data",
        http_user_agent="test",
        radar_dir=str(radar_dir),
        iem_base_url="https://mesonet.agron.iastate.edu",
    )
    config = Config(**cfg_kwargs)

    now = datetime.now(timezone.utc)
    with factory() as s:
        s.add(Station(station_id="KMIA", latitude=25.79, longitude=-80.29, active=1))
        s.flush()
        # One recent obs missing radar
        s.add(Observation(
            station_id="KMIA", observed_at=_iso(now - timedelta(minutes=10)),
            raw_metar="X", ingested_at=_iso(now),
        ))
        s.commit()
    return factory, config, radar_dir, now


def _mock_iem(body=PNG_MAGIC):
    m = MagicMock()
    m.fetch.return_value = body
    return m


def test_fetches_writes_png_and_updates_path(setup):
    factory, config, radar_dir, now = setup
    iem = _mock_iem()
    with factory() as session:
        result = fetch_radar_images(session, iem, config)

    assert result.observations_scanned == 1
    assert result.images_fetched == 1
    assert iem.fetch.call_count == 1

    # File on disk
    png_files = list(radar_dir.glob("hot/KMIA/*.png"))
    assert len(png_files) == 1
    assert png_files[0].read_bytes() == PNG_MAGIC

    # Path recorded on the observation
    with factory() as session:
        obs = session.execute(
            __import__("sqlalchemy").select(Observation)
        ).scalars().first()
    assert obs.radar_image_path is not None
    assert obs.radar_image_path.startswith("radar/hot/KMIA/")
    assert obs.radar_image_path.endswith("Z.png")


def test_skips_observations_with_existing_radar_image(setup):
    factory, config, radar_dir, now = setup
    # Pre-set radar_image_path on the seeded obs
    with factory() as session:
        from sqlalchemy import update
        session.execute(
            update(Observation).values(radar_image_path="radar/hot/KMIA/old.png")
        )
        session.commit()
    iem = _mock_iem()
    with factory() as session:
        result = fetch_radar_images(session, iem, config)
    assert result.observations_scanned == 0  # not selected
    assert iem.fetch.call_count == 0


def test_skips_fetch_when_file_already_on_disk(setup):
    """Disk-side idempotency: a prior crash that wrote PNG but didn't commit
    DB shouldn't re-pay the IEM call on the next run."""
    factory, config, radar_dir, now = setup
    # Pre-create the target file
    with factory() as session:
        obs = session.execute(
            __import__("sqlalchemy").select(Observation)
        ).scalars().first()
    from soonstone.ingestion.radar import _hot_path_for
    target = _hot_path_for(radar_dir, "KMIA", obs.observed_at)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"existing")

    iem = _mock_iem()
    with factory() as session:
        result = fetch_radar_images(session, iem, config)
    assert result.images_skipped_existing == 1
    assert iem.fetch.call_count == 0


def test_fetch_failure_does_not_update_path(setup):
    factory, config, radar_dir, now = setup
    iem = _mock_iem(body=None)
    with factory() as session:
        result = fetch_radar_images(session, iem, config)
    assert result.fetch_failures == 1
    assert result.images_fetched == 0
    with factory() as session:
        obs = session.execute(
            __import__("sqlalchemy").select(Observation)
        ).scalars().first()
    assert obs.radar_image_path is None
