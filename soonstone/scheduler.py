"""APScheduler wiring for the four soonstone background jobs.

`build_scheduler(app)` returns a configured but NOT-yet-started
BackgroundScheduler. Caller is responsible for `.start()` and `.shutdown()`
(see soonstone.__main__).

Each registered job is a closure that:
  1. opens a fresh SQLAlchemy session
  2. calls the underlying ingestion function
  3. logs the result as JSON
  4. closes the session, regardless of outcome
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from flask import Flask

from soonstone.db import make_session_factory
from soonstone.ingestion.airsigmets import ingest_airsigmets
from soonstone.ingestion.iem_radar import IemRadarClient
from soonstone.ingestion.metars import ingest_metars
from soonstone.ingestion.nws import ingest_nws_forecasts
from soonstone.ingestion.nws_client import NwsClient
from soonstone.ingestion.prune import prune_old
from soonstone.ingestion.radar import fetch_radar_images
from soonstone.ingestion.stations import refresh_stations
from soonstone.ingestion.tafs import ingest_tafs

log = logging.getLogger(__name__)


def _get_nws_client(app: Flask) -> NwsClient:
    nws = app.extensions.get("soonstone_nws_client")
    if nws is None:
        nws = NwsClient(config=app.extensions["soonstone_config"])
        app.extensions["soonstone_nws_client"] = nws
    return nws


def _get_iem_radar_client(app: Flask) -> IemRadarClient:
    iem = app.extensions.get("soonstone_iem_radar_client")
    if iem is None:
        iem = IemRadarClient(config=app.extensions["soonstone_config"])
        app.extensions["soonstone_iem_radar_client"] = iem
    return iem


def _make_runner(app: Flask, fn, name: str):
    session_factory = make_session_factory(app.extensions["soonstone_engine"])
    awc_client = app.extensions["soonstone_awc_client"]
    config = app.extensions["soonstone_config"]

    def _run() -> None:
        with session_factory() as session:
            try:
                if fn is prune_old:
                    result = fn(session)
                elif fn is ingest_nws_forecasts:
                    result = fn(session, _get_nws_client(app), config)
                elif fn is fetch_radar_images:
                    result = fn(session, _get_iem_radar_client(app), config)
                elif fn is ingest_airsigmets:
                    result = fn(awc_client, config)  # no session; cache-to-disk only
                else:
                    result = fn(session, awc_client, config)
                log.info("ingestion_done", extra=result.as_log_extra())
            except Exception:
                log.exception("ingestion_failed", extra={"job": name})
                raise

    _run.__name__ = name
    return _run


def build_scheduler(app: Flask) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="UTC")

    health = app.extensions["soonstone_health"]

    def _on_event(event):
        if event.exception:
            health.record_error(event.job_id, event.exception)
        else:
            health.record_success(event.job_id)

    scheduler.add_listener(_on_event, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

    scheduler.add_job(
        _make_runner(app, refresh_stations, "refresh_stations"),
        trigger=CronTrigger(day_of_week="mon", hour=3, minute=0),
        id="refresh_stations",
        replace_existing=True,
    )
    scheduler.add_job(
        _make_runner(app, ingest_metars, "ingest_metars"),
        trigger=CronTrigger(minute="25,55"),
        id="ingest_metars",
        replace_existing=True,
    )
    scheduler.add_job(
        _make_runner(app, ingest_tafs, "ingest_tafs"),
        trigger=CronTrigger(minute="0,30"),
        id="ingest_tafs",
        replace_existing=True,
    )
    scheduler.add_job(
        _make_runner(app, prune_old, "prune_old"),
        trigger=CronTrigger(hour=4, minute=0),
        id="prune_old",
        replace_existing=True,
    )
    scheduler.add_job(
        _make_runner(app, ingest_nws_forecasts, "ingest_nws_forecasts"),
        trigger=CronTrigger(minute=10),
        id="ingest_nws_forecasts",
        replace_existing=True,
    )
    # Radar fetcher runs 5 min after each METAR ingest so the new
    # observations are already in the DB.
    scheduler.add_job(
        _make_runner(app, fetch_radar_images, "fetch_radar_images"),
        trigger=CronTrigger(minute="35,5"),
        id="fetch_radar_images",
        replace_existing=True,
    )
    # AIRMETs/SIGMETs issue ad-hoc; poll every 10 min on minute 7,17,...
    scheduler.add_job(
        _make_runner(app, ingest_airsigmets, "ingest_airsigmets"),
        trigger=CronTrigger(minute="7,17,27,37,47,57"),
        id="ingest_airsigmets",
        replace_existing=True,
    )
    return scheduler


def run_once(job_name: str, app: Flask) -> None:
    """Manually fire one ingestion job, then exit. Used by `python -m soonstone --run-once`."""
    fn_map = {
        "refresh_stations": refresh_stations,
        "ingest_metars": ingest_metars,
        "ingest_tafs": ingest_tafs,
        "prune_old": prune_old,
        "ingest_nws_forecasts": ingest_nws_forecasts,
        "fetch_radar_images": fetch_radar_images,
        "ingest_airsigmets": ingest_airsigmets,
    }


# Order + offsets chosen so the data the user cares about most appears first
# (stations -> AIRMETs -> METARs -> TAFs -> NWS -> radar) and so back-to-back
# write-heavy jobs don't stomp on the SQLite write lock.
_FIRST_SCAN_SCHEDULE: tuple[tuple[str, int], ...] = (
    ("refresh_stations",     5),
    ("ingest_airsigmets",   10),
    ("ingest_metars",       30),
    ("ingest_tafs",        120),
    ("ingest_nws_forecasts", 180),
    ("fetch_radar_images", 240),
)


def first_scan(scheduler: BackgroundScheduler) -> None:
    """Fire each ingest job once shortly after startup.

    Mirrors a PLC's 'first scan' phase: initialize state on power-up instead
    of waiting for the next cron tick (which can be 30 min away). Bumping
    next_run_time on each existing cron job hands one extra invocation to
    APScheduler, then the cron schedule resumes naturally. Staggered offsets
    prevent SQLite write-lock contention between concurrent ingest jobs.
    """
    now = datetime.now(timezone.utc)
    for job_id, offset_sec in _FIRST_SCAN_SCHEDULE:
        try:
            scheduler.modify_job(
                job_id, next_run_time=now + timedelta(seconds=offset_sec)
            )
            log.info(
                "first_scan_scheduled",
                extra={"job": job_id, "in_seconds": offset_sec},
            )
        except Exception as exc:
            log.warning(
                "first_scan_modify_failed",
                extra={"job": job_id, "error": str(exc)},
            )
    if job_name not in fn_map:
        raise ValueError(f"unknown job: {job_name}")
    runner = _make_runner(app, fn_map[job_name], job_name)
    health = app.extensions.get("soonstone_health")
    try:
        runner()
        if health:
            health.record_success(job_name)
    except Exception as exc:
        if health:
            health.record_error(job_name, exc)
        raise
