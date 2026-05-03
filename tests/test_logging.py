"""Verify configure_logging emits JSON records with the soonstone field set."""
from __future__ import annotations

import json
import logging

import pytest

from soonstone.logging import JsonFormatter, configure_logging


def test_json_formatter_emits_required_fields():
    record = logging.LogRecord(
        name="soonstone.test", level=logging.INFO, pathname="x", lineno=1,
        msg="hello %s", args=("world",), exc_info=None,
    )
    out = JsonFormatter().format(record)
    payload = json.loads(out)
    assert payload["msg"] == "hello world"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "soonstone.test"
    assert "ts" in payload and payload["ts"].endswith("Z")


def test_extra_fields_pass_through():
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="soonstone.ingest", level=logging.INFO, pathname="x", lineno=1,
        msg="ingest done", args=(), exc_info=None,
    )
    record.job = "ingest_metars"
    record.inserted = 42
    record.skipped = 3
    payload = json.loads(formatter.format(record))
    assert payload["job"] == "ingest_metars"
    assert payload["inserted"] == 42
    assert payload["skipped"] == 3


def test_configure_logging_attaches_json_formatter_once():
    configure_logging("INFO")
    configure_logging("INFO")  # idempotent — must not double-attach
    root = logging.getLogger()
    json_handlers = [h for h in root.handlers if isinstance(h.formatter, JsonFormatter)]
    assert len(json_handlers) == 1
