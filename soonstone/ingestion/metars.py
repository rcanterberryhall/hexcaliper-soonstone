"""ingest_metars: pull AWC METARs, parse, idempotent-insert into observations."""
from __future__ import annotations

import logging

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from soonstone.config import Config
from soonstone.ingestion.awc_client import AwcClient
from soonstone.ingestion.results import MetarsResult
from soonstone.models import Observation, Station
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

        # Auto-stub a station row if AWC sent us a METAR for one we haven't
        # catalogued yet. AWC's stationinfo endpoint caps at 400 rows so for
        # CONUS we routinely see METARs from stations beyond the catalog.
        # The METAR JSON itself carries lat/lon/name, which is enough for the
        # map marker to render and the FK constraint to be satisfied.
        if raw_row.get("lat") is not None and raw_row.get("lon") is not None:
            stub = sqlite_insert(Station).values(
                station_id=parsed["station_id"],
                name=raw_row.get("name"),
                latitude=float(raw_row["lat"]),
                longitude=float(raw_row["lon"]),
                elevation_m=(
                    float(raw_row["elev"]) if raw_row.get("elev") is not None else None
                ),
                taf_site=0,
                active=1,
            ).on_conflict_do_nothing(index_elements=["station_id"])
            session.execute(stub)

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
