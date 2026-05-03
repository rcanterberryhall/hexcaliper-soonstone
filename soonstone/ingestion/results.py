"""Result objects returned by ingestion jobs.

Each job returns a small dataclass that captures what it did. The scheduler
logs these as `extra={...}` on the JSON log record, which gives us grep-able
fields without inventing a per-job log format.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class StationsResult:
    fetched: int
    inserted: int
    updated: int

    def as_log_extra(self) -> dict:
        d = asdict(self)
        d["job"] = "refresh_stations"
        return d


@dataclass(frozen=True)
class MetarsResult:
    fetched: int
    inserted: int
    skipped_duplicate: int
    parse_failures: int

    def as_log_extra(self) -> dict:
        d = asdict(self)
        d["job"] = "ingest_metars"
        return d


@dataclass(frozen=True)
class TafsResult:
    fetched: int
    inserted: int
    skipped_duplicate: int
    parse_failures: int
    groups_inserted: int

    def as_log_extra(self) -> dict:
        d = asdict(self)
        d["job"] = "ingest_tafs"
        return d


@dataclass(frozen=True)
class PruneResult:
    raw_metars_nulled: int
    raw_tafs_nulled: int

    def as_log_extra(self) -> dict:
        d = asdict(self)
        d["job"] = "prune_old"
        return d
