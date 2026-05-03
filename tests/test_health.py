"""Tests for the in-process JobHealth tracker."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from soonstone.health import JobHealth


def test_records_success_with_timestamp():
    h = JobHealth()
    h.record_success("ingest_metars")
    assert h.last_success("ingest_metars") is not None
    assert h.last_error("ingest_metars") is None


def test_records_error_separately_from_success():
    h = JobHealth()
    h.record_success("ingest_metars")
    h.record_error("ingest_metars", RuntimeError("boom"))
    assert h.last_success("ingest_metars") is not None
    assert h.last_error("ingest_metars") == "RuntimeError: boom"


def test_is_healthy_requires_recent_success_for_each_named_job():
    h = JobHealth()
    h.record_success("ingest_metars", at=datetime.now(timezone.utc))
    h.record_success("ingest_tafs", at=datetime.now(timezone.utc) - timedelta(hours=2))
    assert not h.is_healthy(["ingest_metars", "ingest_tafs"], max_age_minutes=90)
    assert h.is_healthy(["ingest_metars"], max_age_minutes=90)


def test_is_healthy_false_if_job_never_ran():
    h = JobHealth()
    assert not h.is_healthy(["ingest_metars"], max_age_minutes=90)
