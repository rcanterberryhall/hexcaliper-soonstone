"""Tests for ingest_metars: parse, idempotent insert, parse-failure handling."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from soonstone.config import Config
from soonstone.db import Base, create_engine_with_pragmas, make_session_factory
from soonstone.ingestion.metars import ingest_metars
from soonstone.models import Observation, Station


KMIA_RAW = "METAR KMIA 022253Z 26009KT 10SM FEW065 SCT250 32/17 A2986"
KEYW_RAW = "KEYW 022253Z 12012KT 10SM FEW028 27/23 A3009"


@pytest.fixture
def session_factory(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'metars_test.db'}"
    engine = create_engine_with_pragmas(db_url)
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


@pytest.fixture
def seeded_factory(session_factory):
    """Same as session_factory but with KMIA + KEYW pre-inserted as stations."""
    with session_factory() as session:
        session.add_all([
            Station(station_id="KMIA", latitude=25.79, longitude=-80.29),
            Station(station_id="KEYW", latitude=24.55, longitude=-81.76),
        ])
        session.commit()
    return session_factory


def _mock_awc(metars: list[dict]):
    m = MagicMock()
    m.fetch_metars.return_value = metars
    return m


def test_ingest_metars_inserts_parsed_rows(seeded_factory):
    awc = _mock_awc([
        {"icaoId": "KMIA", "rawOb": KMIA_RAW},
        {"icaoId": "KEYW", "rawOb": KEYW_RAW},
    ])
    with seeded_factory() as session:
        result = ingest_metars(session, awc, Config.from_env())

    assert result.fetched == 2
    assert result.inserted == 2
    assert result.parse_failures == 0
    with seeded_factory() as session:
        rows = session.execute(select(Observation)).scalars().all()
    assert {r.station_id for r in rows} == {"KMIA", "KEYW"}
    kmia = next(r for r in rows if r.station_id == "KMIA")
    assert kmia.flight_category == "VFR"
    assert kmia.wind_dir_deg == 260


def test_ingest_metars_is_idempotent(seeded_factory):
    awc = _mock_awc([{"icaoId": "KMIA", "rawOb": KMIA_RAW}])
    with seeded_factory() as session:
        ingest_metars(session, awc, Config.from_env())
    with seeded_factory() as session:
        result = ingest_metars(session, awc, Config.from_env())
    assert result.inserted == 0
    assert result.skipped_duplicate == 1


def test_ingest_metars_logs_and_skips_parse_failures(seeded_factory):
    awc = _mock_awc([
        {"icaoId": "KMIA", "rawOb": "this is not a metar"},
        {"icaoId": "KEYW", "rawOb": KEYW_RAW},
    ])
    with seeded_factory() as session:
        result = ingest_metars(session, awc, Config.from_env())
    assert result.parse_failures == 1
    assert result.inserted == 1
    with seeded_factory() as session:
        rows = session.execute(select(Observation)).scalars().all()
    assert {r.station_id for r in rows} == {"KEYW"}


def test_ingest_metars_skips_rows_without_raw_text(seeded_factory):
    awc = _mock_awc([{"icaoId": "KMIA"}])  # no rawOb
    with seeded_factory() as session:
        result = ingest_metars(session, awc, Config.from_env())
    assert result.inserted == 0
    assert result.parse_failures == 0
