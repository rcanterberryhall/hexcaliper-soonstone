"""Tests for build_snapshot: now / convergence / forward shape against a seeded DB."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from soonstone.db import Base, create_engine_with_pragmas, make_session_factory
from soonstone.models import Observation, Station, Taf, TafGroup
from soonstone.verification.snapshot import build_snapshot


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def session_factory(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'snapshot.db'}"
    engine = create_engine_with_pragmas(db_url)
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


@pytest.fixture
def now():
    return datetime(2026, 5, 2, 18, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def seeded(session_factory, now):
    with session_factory() as s:
        s.add(Station(station_id="KMIA", name="Miami Intl",
                      latitude=25.79, longitude=-80.29))
        s.flush()
        s.add(Observation(
            station_id="KMIA", observed_at=_iso(now - timedelta(minutes=10)),
            raw_metar="KMIA TEST", wind_dir_deg=180, wind_speed_kt=10.0,
            visibility_sm=10.0, flight_category="VFR",
            ingested_at=_iso(now - timedelta(minutes=5)),
        ))
        t1 = Taf(
            station_id="KMIA",
            issued_at=_iso(now - timedelta(hours=12)),
            valid_from=_iso(now - timedelta(hours=12)),
            valid_to=_iso(now + timedelta(hours=12)),
            raw_taf="KMIA t1",
            amendment_type=None,
            ingested_at=_iso(now - timedelta(hours=12)),
        )
        s.add(t1)
        s.flush()
        s.add(TafGroup(
            taf_id=t1.taf_id, group_index=0, group_type="BASE",
            group_from=t1.valid_from, group_to=t1.valid_to,
            wind_dir_deg=180, wind_speed_kt=10.0, visibility_sm=10.0,
            flight_category="VFR",
        ))
        s.add(TafGroup(
            taf_id=t1.taf_id, group_index=1, group_type="FM",
            group_from=_iso(now - timedelta(hours=4)),
            group_to=t1.valid_to,
            wind_dir_deg=200, wind_speed_kt=12.0, visibility_sm=10.0,
            flight_category="VFR",
        ))

        t2 = Taf(
            station_id="KMIA",
            issued_at=_iso(now - timedelta(hours=2)),
            valid_from=_iso(now - timedelta(hours=2)),
            valid_to=_iso(now + timedelta(hours=22)),
            raw_taf="KMIA t2 amd",
            amendment_type="AMD",
            ingested_at=_iso(now - timedelta(hours=2)),
        )
        s.add(t2)
        s.flush()
        s.add(TafGroup(
            taf_id=t2.taf_id, group_index=0, group_type="BASE",
            group_from=t2.valid_from, group_to=t2.valid_to,
            wind_dir_deg=170, wind_speed_kt=15.0, wind_gust_kt=22.0,
            visibility_sm=10.0, flight_category="VFR",
        ))
        s.commit()
    return session_factory


def test_snapshot_returns_station_metadata(seeded, now):
    with seeded() as session:
        snap = build_snapshot(session, "KMIA", now=now)
    assert snap["station"]["id"] == "KMIA"
    assert snap["station"]["name"] == "Miami Intl"
    assert snap["station"]["lat"] == pytest.approx(25.79)


def test_snapshot_now_section(seeded, now):
    with seeded() as session:
        snap = build_snapshot(session, "KMIA", now=now)
    assert snap["now"]["wind_dir_deg"] == 180
    assert snap["now"]["wind_speed_kt"] == 10.0
    assert snap["now"]["flight_category"] == "VFR"
    assert snap["now"]["observed_at"].endswith("Z")


def test_snapshot_convergence_lists_both_tafs(seeded, now):
    with seeded() as session:
        snap = build_snapshot(session, "KMIA", now=now)
    conv = snap["convergence"]
    assert len(conv) == 2
    assert conv[0]["amendment_type"] is None
    assert conv[1]["amendment_type"] == "AMD"
    assert conv[0]["wind_dir_deg"] == 200
    assert conv[1]["wind_dir_deg"] == 170
    assert conv[1]["wind_gust_kt"] == 22.0
    assert conv[0]["lead_hours"] == pytest.approx(12.0, abs=0.01)
    assert conv[1]["lead_hours"] == pytest.approx(2.0, abs=0.01)


def test_snapshot_forward_walks_active_taf_groups(seeded, now):
    with seeded() as session:
        snap = build_snapshot(session, "KMIA", now=now)
    fwd = snap["forward"]
    assert len(fwd) >= 1
    assert fwd[0]["group_type"] == "BASE"
    assert fwd[0]["wind_dir_deg"] == 170


def test_snapshot_unknown_station_returns_none(seeded, now):
    with seeded() as session:
        snap = build_snapshot(session, "ZZZZ", now=now)
    assert snap is None
