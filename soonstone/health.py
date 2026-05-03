"""In-process job-health tracker.

The scheduler updates this via APScheduler EVENT_JOB_EXECUTED / EVENT_JOB_ERROR
listeners. The /health endpoint reads it. State is in-process only -- restarting
the service resets all timestamps. That is intentional for v0: a freshly
restarted service IS unhealthy until its first successful ingestion cycle, and
that's exactly what we want Cloudflare to see.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


class JobHealth:
    def __init__(self) -> None:
        self._success: dict[str, datetime] = {}
        self._error: dict[str, str] = {}

    def record_success(self, name: str, at: datetime | None = None) -> None:
        self._success[name] = at or datetime.now(timezone.utc)
        self._error.pop(name, None)

    def record_error(self, name: str, exc: BaseException) -> None:
        self._error[name] = f"{type(exc).__name__}: {exc}"

    def last_success(self, name: str) -> datetime | None:
        return self._success.get(name)

    def last_error(self, name: str) -> str | None:
        return self._error.get(name)

    def is_healthy(self, jobs: list[str], max_age_minutes: int) -> bool:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
        for name in jobs:
            ts = self._success.get(name)
            if ts is None or ts < cutoff:
                return False
        return True

    def snapshot(self) -> dict:
        return {
            "last_success": {
                k: v.strftime("%Y-%m-%dT%H:%M:%SZ") for k, v in self._success.items()
            },
            "last_error": dict(self._error),
        }
