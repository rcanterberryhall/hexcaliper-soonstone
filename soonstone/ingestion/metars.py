"""ingest_metars: pull AWC METARs, parse, idempotent-insert into observations."""
from __future__ import annotations

import logging

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from soonstone.config import Config
from soonstone.ingestion.awc_client import AwcClient
from soonstone.ingestion.results import MetarsResult
from soonstone.models import Observation
from soonstone.parsers.metar_parser import parse_metar

log = logging.getLogger(__name__)


def ingest_metars(
    session: Session, awc_client: AwcClient, config: Config
) -> MetarsResult:
    rows = awc_client.fetch_metars(bbox=config.bbox_query)
    inserted = 0
    skipped = 0
    failed = 0

    for raw_row in rows:
        text = raw_row.get("rawOb")
        if not text:
            continue
        try:
            parsed = parse_metar(text)
        except Exception as exc:
            failed += 1
            log.warning(
                "metar_parse_failed",
                extra={
                    "job": "ingest_metars",
                    "station_id": raw_row.get("icaoId"),
                    "raw": text,
                    "error": str(exc),
                },
            )
            continue

        stmt = (
            sqlite_insert(Observation)
            .values(**parsed)
            .on_conflict_do_nothing(index_elements=["station_id", "observed_at"])
        )
        result = session.execute(stmt)
        if result.rowcount == 1:
            inserted += 1
        else:
            skipped += 1

    session.commit()
    return MetarsResult(
        fetched=len(rows),
        inserted=inserted,
        skipped_duplicate=skipped,
        parse_failures=failed,
    )
