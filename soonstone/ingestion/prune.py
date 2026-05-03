"""prune_old: null out raw_metar / raw_taf older than N days.

Parsed columns stay forever — the only loss is the verbatim source text we'd
need for re-parsing. This is an optional housekeeping job.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import update
from sqlalchemy.orm import Session

from soonstone.ingestion.results import PruneResult
from soonstone.models import Observation, Taf


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def prune_old(session: Session, days: int = 30) -> PruneResult:
    cutoff = _iso(datetime.now(timezone.utc) - timedelta(days=days))

    metars_result = session.execute(
        update(Observation)
        .where(Observation.ingested_at < cutoff, Observation.raw_metar.is_not(None))
        .values(raw_metar=None)
    )
    tafs_result = session.execute(
        update(Taf)
        .where(Taf.ingested_at < cutoff, Taf.raw_taf.is_not(None))
        .values(raw_taf=None)
    )
    session.commit()

    return PruneResult(
        raw_metars_nulled=metars_result.rowcount,
        raw_tafs_nulled=tafs_result.rowcount,
    )
