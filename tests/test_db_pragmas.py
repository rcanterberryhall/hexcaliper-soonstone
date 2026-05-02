"""Verify that connecting via our engine factory applies all required pragmas."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from soonstone.db import create_engine_with_pragmas


REQUIRED_PRAGMAS = {
    "journal_mode": "wal",
    "synchronous": 1,         # NORMAL = 1
    "foreign_keys": 1,
    "temp_store": 2,          # MEMORY = 2
    "busy_timeout": 5000,
}


def _get_pragma(conn, name):
    return conn.execute(text(f"PRAGMA {name}")).scalar()


def test_pragma_listener_applies_required_pragmas(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'pragma_test.db'}"
    engine = create_engine_with_pragmas(db_url)

    with engine.connect() as conn:
        for pragma, expected in REQUIRED_PRAGMAS.items():
            actual = _get_pragma(conn, pragma)
            if isinstance(expected, str):
                assert str(actual).lower() == expected, f"PRAGMA {pragma}: got {actual!r}"
            else:
                assert int(actual) == expected, f"PRAGMA {pragma}: got {actual!r}"

        cache_size = _get_pragma(conn, "cache_size")
        assert int(cache_size) == -64000, f"cache_size: got {cache_size!r}"

        mmap_size = _get_pragma(conn, "mmap_size")
        assert int(mmap_size) == 268435456, f"mmap_size: got {mmap_size!r}"
