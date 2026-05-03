"""Job-health tracker.

In-memory by default; optionally file-backed for cross-process visibility.

Why file-backed: the v0 deploy runs ingestion via the long-running --serve
process AND lets operators trigger jobs ad-hoc with `docker exec ... --run-once
<job>`. Those are *separate Python processes*; each has its own in-memory dict.
Without persistence, ad-hoc runs wouldn't show up in /health, and the long-
running scheduler's runs wouldn't show up if you exec'd a quick check.

Persistence is intentionally simple: dump JSON on every write, reload on every
read. State file lives next to the SQLite DB. No locking — at our cadence
(jobs every 30 min, ad-hoc runs by humans) the race window is nil. Worst case
is a transient corrupted read which the next clean write overwrites.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


class JobHealth:
    def __init__(self, state_file: Path | None = None) -> None:
        self._state_file = state_file
        self._success: dict[str, datetime] = {}
        self._error: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if not self._state_file or not self._state_file.exists():
            return
        try:
            data = json.loads(self._state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        success = data.get("success") or {}
        self._success = {}
        for k, v in success.items():
            try:
                self._success[k] = datetime.fromisoformat(v)
            except (TypeError, ValueError):
                continue
        self._error = dict(data.get("error") or {})

    def _persist(self) -> None:
        if not self._state_file:
            return
        payload = {
            "success": {k: v.isoformat() for k, v in self._success.items()},
            "error": dict(self._error),
        }
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        self._state_file.write_text(json.dumps(payload), encoding="utf-8")

    def record_success(self, name: str, at: datetime | None = None) -> None:
        self._load()
        self._success[name] = at or datetime.now(timezone.utc)
        self._error.pop(name, None)
        self._persist()

    def record_error(self, name: str, exc: BaseException) -> None:
        self._load()
        self._error[name] = f"{type(exc).__name__}: {exc}"
        self._persist()

    def last_success(self, name: str) -> datetime | None:
        self._load()
        return self._success.get(name)

    def last_error(self, name: str) -> str | None:
        self._load()
        return self._error.get(name)

    def is_healthy(self, jobs: list[str], max_age_minutes: int) -> bool:
        self._load()
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
        for name in jobs:
            ts = self._success.get(name)
            if ts is None or ts < cutoff:
                return False
        return True

    def snapshot(self) -> dict:
        self._load()
        return {
            "last_success": {
                k: v.strftime("%Y-%m-%dT%H:%M:%SZ") for k, v in self._success.items()
            },
            "last_error": dict(self._error),
        }
