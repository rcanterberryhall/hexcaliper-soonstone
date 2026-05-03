"""ingest_nws_forecasts: pull NWS 12h-period forecasts for TAF-issuing stations."""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from soonstone.config import Config
from soonstone.ingestion.nws_client import NwsClient
from soonstone.ingestion.results import NwsResult
from soonstone.models import NwsForecast, Station

log = logging.getLogger(__name__)

# Throttle to ~5 RPS per NWS courtesy guidance.
_REQUEST_GAP_SEC = 0.2


def _iso_utc(s: str) -> str:
    """NWS returns ISO 8601 with offset; normalize to UTC Z form."""
    dt = datetime.fromisoformat(s)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _project_period(station_id: str, period: dict) -> dict:
    pop = period.get("probabilityOfPrecipitation") or {}
    return {
        "station_id": station_id,
        "period_name": period.get("name"),
        "valid_from": _iso_utc(period["startTime"]),
        "valid_to": _iso_utc(period["endTime"]),
        "temperature_f": period.get("temperature"),
        "wind_dir": period.get("windDirection"),
        "wind_speed": period.get("windSpeed"),
        "pop_pct": pop.get("value"),
        "short_forecast": period.get("shortForecast"),
        "detailed_forecast": period.get("detailedForecast"),
        "raw_json": json.dumps(period),
    }


def ingest_nws_forecasts(
    session: Session, nws_client: NwsClient, config: Config
) -> NwsResult:
    stations = session.execute(
        select(Station).where(Station.taf_site == 1, Station.active == 1)
    ).scalars().all()

    points_lookups = 0
    fetch_failures = 0
    inserted = 0
    skipped = 0
    processed = 0

    for station in stations:
        forecast_url = station.nws_forecast_url
        if not forecast_url:
            try:
                forecast_url = nws_client.fetch_points(
                    lat=station.latitude, lon=station.longitude
                )
            except Exception as exc:
                fetch_failures += 1
                log.warning(
                    "nws_points_failed",
                    extra={"job": "ingest_nws_forecasts",
                           "station_id": station.station_id, "error": str(exc)},
                )
                time.sleep(_REQUEST_GAP_SEC)
                continue
            points_lookups += 1
            session.execute(
                update(Station)
                .where(Station.station_id == station.station_id)
                .values(nws_forecast_url=forecast_url)
            )
            time.sleep(_REQUEST_GAP_SEC)

        try:
            periods = nws_client.fetch_forecast(forecast_url)
        except Exception as exc:
            fetch_failures += 1
            log.warning(
                "nws_forecast_failed",
                extra={"job": "ingest_nws_forecasts",
                       "station_id": station.station_id, "error": str(exc)},
            )
            time.sleep(_REQUEST_GAP_SEC)
            continue

        processed += 1
        for period in periods:
            try:
                projected = _project_period(station.station_id, period)
            except Exception as exc:
                log.warning(
                    "nws_period_project_failed",
                    extra={"job": "ingest_nws_forecasts",
                           "station_id": station.station_id, "error": str(exc)},
                )
                continue
            stmt = (
                sqlite_insert(NwsForecast)
                .values(**projected)
                .on_conflict_do_nothing(
                    index_elements=["station_id", "valid_from", "valid_to"]
                )
            )
            r = session.execute(stmt)
            if r.rowcount == 1:
                inserted += 1
            else:
                skipped += 1

        time.sleep(_REQUEST_GAP_SEC)

    session.commit()
    return NwsResult(
        stations_processed=processed,
        forecasts_inserted=inserted,
        forecasts_skipped_duplicate=skipped,
        points_lookups=points_lookups,
        fetch_failures=fetch_failures,
    )
