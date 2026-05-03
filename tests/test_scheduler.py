"""Scheduler wiring: registers the 4 jobs at the expected triggers."""
from __future__ import annotations

import pytest

from soonstone.app import create_app
from soonstone.scheduler import build_scheduler


def test_scheduler_registers_all_jobs(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'sched.db'}")
    app = create_app()
    scheduler = build_scheduler(app)
    job_ids = {job.id for job in scheduler.get_jobs()}
    assert job_ids == {
        "refresh_stations",
        "ingest_metars",
        "ingest_tafs",
        "prune_old",
        "ingest_nws_forecasts",
        "fetch_radar_images",
    }


def test_metars_runs_twice_an_hour(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'sched.db'}")
    app = create_app()
    scheduler = build_scheduler(app)
    metars = scheduler.get_job("ingest_metars")
    minute_field = next(f for f in metars.trigger.fields if f.name == "minute")
    assert "25" in str(minute_field)
    assert "55" in str(minute_field)


def test_tafs_offset_from_metars(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'sched.db'}")
    app = create_app()
    scheduler = build_scheduler(app)
    tafs = scheduler.get_job("ingest_tafs")
    minute_field = next(f for f in tafs.trigger.fields if f.name == "minute")
    assert "30" in str(minute_field)
    assert "0" in str(minute_field)
