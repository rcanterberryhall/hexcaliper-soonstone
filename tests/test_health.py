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


def test_state_file_makes_writes_visible_to_a_second_instance(tmp_path):
    state = tmp_path / "jobhealth.json"
    a = JobHealth(state_file=state)
    b = JobHealth(state_file=state)

    a.record_success("ingest_metars")
    a.record_success("ingest_tafs")
    a.record_error("ingest_tafs", RuntimeError("upstream 503"))

    # b was constructed BEFORE a's writes -- it must reload from disk on read.
    assert b.last_success("ingest_metars") is not None
    assert b.last_error("ingest_tafs") == "RuntimeError: upstream 503"
    assert b.is_healthy(["ingest_metars"], max_age_minutes=90)


def test_corrupt_state_file_does_not_crash(tmp_path):
    state = tmp_path / "jobhealth.json"
    state.write_text("not json")
    h = JobHealth(state_file=state)
    # Should silently skip corrupt content; record_success then overwrites cleanly.
    assert h.last_success("ingest_metars") is None
    h.record_success("ingest_metars")
    assert h.last_success("ingest_metars") is not None
