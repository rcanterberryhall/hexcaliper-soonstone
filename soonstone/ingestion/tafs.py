"""ingest_tafs: pull AWC TAFs, parse, idempotent-insert parent + children."""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from soonstone.config import Config
from soonstone.ingestion.awc_client import AwcClient
from soonstone.ingestion.results import TafsResult
from soonstone.models import Taf, TafGroup
from soonstone.parsers.taf_parser import parse_taf

log = logging.getLogger(__name__)


def _is_duplicate(session: Session, parsed: dict) -> bool:
    # SQL: NULL = NULL is UNKNOWN, not TRUE. Use IS NULL for the routine-TAF case
    # (where amendment_type is None) and = for AMD/COR/RTD.
    amendment = parsed["amendment_type"]
    if amendment is None:
        amend_clause = Taf.amendment_type.is_(None)
    else:
        amend_clause = Taf.amendment_type == amendment

    existing = session.execute(
        select(Taf.taf_id).where(
            Taf.station_id == parsed["station_id"],
            Taf.issued_at == parsed["issued_at"],
            amend_clause,
        )
    ).first()
    return existing is not None


def ingest_tafs(
    session: Session, awc_client: AwcClient, config: Config
) -> TafsResult:
    rows = awc_client.fetch_tafs(bbox=config.bbox_query)
    inserted = 0
    skipped = 0
    failed = 0
    groups_inserted = 0

    for raw_row in rows:
        text = raw_row.get("rawTAF")
        if not text:
            continue
        try:
            parsed = parse_taf(text)
        except Exception as exc:
            failed += 1
            log.warning(
                "taf_parse_failed",
                extra={
                    "job": "ingest_tafs",
                    "station_id": raw_row.get("icaoId"),
                    "raw": text,
                    "error": str(exc),
                },
            )
            continue

        if _is_duplicate(session, parsed):
            skipped += 1
            continue

        groups = parsed.pop("groups")
        taf = Taf(**parsed)
        session.add(taf)
        session.flush()  # populate taf.taf_id

        for group in groups:
            session.add(TafGroup(taf_id=taf.taf_id, **group))
            groups_inserted += 1

        inserted += 1

    session.commit()
    return TafsResult(
        fetched=len(rows),
        inserted=inserted,
        skipped_duplicate=skipped,
        parse_failures=failed,
        groups_inserted=groups_inserted,
    )
