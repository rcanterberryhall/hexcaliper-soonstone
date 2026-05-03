"""Tests for prune_old: nulls raw text on old rows, leaves recent rows alone."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from soonstone.db import Base, create_engine_with_pragmas, make_session_factory
from soonstone.ingestion.prune import prune_old
from soonstone.models import Observation, Station, Taf


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def session_factory(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'prune_test.db'}"
    engine = create_engine_with_pragmas(db_url)
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


def test_prune_nulls_old_raw_metars_only(session_factory):
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=45)
    recent = now - timedelta(days=5)

    with session_factory() as session:
        session.add(Station(station_id="KMIA", latitude=25.79, longitude=-80.29))
        session.flush()  # ensure FK target exists before child INSERTs
        session.add(
            Observation(
                station_id="KMIA", observed_at=_iso(old), raw_metar="OLD METAR",
                ingested_at=_iso(old),
            )
        )
        session.add(
            Observation(
                station_id="KMIA", observed_at=_iso(recent), raw_metar="RECENT METAR",
                ingested_at=_iso(recent),
            )
        )
        session.commit()

    with session_factory() as session:
        result = prune_old(session, days=30)

    assert result.raw_metars_nulled == 1
    assert result.raw_tafs_nulled == 0
    with session_factory() as session:
        rows = session.execute(select(Observation).order_by(Observation.observed_at)).scalars().all()
    assert rows[0].raw_metar is None  # old row got nulled
    assert rows[1].raw_metar == "RECENT METAR"


def test_prune_nulls_old_raw_tafs_only(session_factory):
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=60)
    recent = now - timedelta(days=10)

    with session_factory() as session:
        session.add(Station(station_id="KMIA", latitude=25.79, longitude=-80.29))
        session.flush()  # ensure FK target exists before child INSERTs
        session.add(
            Taf(
                station_id="KMIA", issued_at=_iso(old), valid_from=_iso(old),
                valid_to=_iso(old + timedelta(hours=24)),
                raw_taf="OLD TAF", ingested_at=_iso(old),
            )
        )
        session.add(
            Taf(
                station_id="KMIA", issued_at=_iso(recent), valid_from=_iso(recent),
                valid_to=_iso(recent + timedelta(hours=24)),
                raw_taf="RECENT TAF", ingested_at=_iso(recent),
            )
        )
        session.commit()

    with session_factory() as session:
        result = prune_old(session, days=30)

    assert result.raw_tafs_nulled == 1
    assert result.raw_metars_nulled == 0
