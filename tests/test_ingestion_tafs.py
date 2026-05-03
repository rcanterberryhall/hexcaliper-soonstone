"""Tests for ingest_tafs: parent+children insert, amendment coexistence, idempotency."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from soonstone.config import Config
from soonstone.db import Base, create_engine_with_pragmas, make_session_factory
from soonstone.ingestion.tafs import ingest_tafs
from soonstone.models import Station, Taf, TafGroup


KMIA_TAF = (
    "TAF KMIA 022205Z 0222/0324 25012G22KT P6SM SCT040 "
    "FM030100 VRB04KT P6SM SCT040 BKN150"
)
KMIA_AMD = (
    "TAF AMD KMIA 022300Z 0223/0324 18020G30KT 4SM TSRA BKN025CB"
)


@pytest.fixture
def session_factory(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'tafs_test.db'}"
    engine = create_engine_with_pragmas(db_url)
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


@pytest.fixture
def seeded_factory(session_factory):
    with session_factory() as session:
        session.add(Station(station_id="KMIA", latitude=25.79, longitude=-80.29))
        session.commit()
    return session_factory


def _mock_awc(tafs: list[dict]):
    m = MagicMock()
    m.fetch_tafs.return_value = tafs
    return m


def test_ingest_tafs_inserts_parent_and_children(seeded_factory):
    awc = _mock_awc([{"icaoId": "KMIA", "rawTAF": KMIA_TAF}])
    with seeded_factory() as session:
        result = ingest_tafs(session, awc, Config.from_env())

    assert result.fetched == 1
    assert result.inserted == 1
    assert result.groups_inserted >= 2  # BASE + at least one FM
    with seeded_factory() as session:
        tafs = session.execute(select(Taf)).scalars().all()
        groups = session.execute(select(TafGroup)).scalars().all()
    assert len(tafs) == 1
    assert tafs[0].station_id == "KMIA"
    assert len(groups) == result.groups_inserted


def test_ingest_tafs_routine_and_amendment_coexist(seeded_factory):
    awc = _mock_awc([
        {"icaoId": "KMIA", "rawTAF": KMIA_TAF},
        {"icaoId": "KMIA", "rawTAF": KMIA_AMD},
    ])
    with seeded_factory() as session:
        result = ingest_tafs(session, awc, Config.from_env())
    assert result.inserted == 2
    with seeded_factory() as session:
        tafs = session.execute(select(Taf).order_by(Taf.taf_id)).scalars().all()
    assert [t.amendment_type for t in tafs] == [None, "AMD"]


def test_ingest_tafs_is_idempotent(seeded_factory):
    awc = _mock_awc([{"icaoId": "KMIA", "rawTAF": KMIA_TAF}])
    with seeded_factory() as session:
        ingest_tafs(session, awc, Config.from_env())
    with seeded_factory() as session:
        result = ingest_tafs(session, awc, Config.from_env())
    assert result.inserted == 0
    assert result.skipped_duplicate == 1


def test_ingest_tafs_handles_parse_failure(seeded_factory):
    awc = _mock_awc([
        {"icaoId": "KMIA", "rawTAF": "garbage that will not parse"},
        {"icaoId": "KMIA", "rawTAF": KMIA_TAF},
    ])
    with seeded_factory() as session:
        result = ingest_tafs(session, awc, Config.from_env())
    assert result.parse_failures == 1
    assert result.inserted == 1
