"""Verify the initial migration applies cleanly and produces the expected schema."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import inspect, text

from soonstone.db import create_engine_with_pragmas

REPO_ROOT = Path(__file__).resolve().parent.parent

EXPECTED_TABLES = {"stations", "observations", "tafs", "taf_groups", "alembic_version"}


def _run_alembic(db_url: str, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_URL": db_url}
    return subprocess.run(
        [".venv/bin/alembic", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )


def test_initial_migration_applies_cleanly(tmp_path):
    db_path = tmp_path / "migration_test.db"
    db_url = f"sqlite:///{db_path}"

    _run_alembic(db_url, "upgrade", "head")

    engine = create_engine_with_pragmas(db_url)
    with engine.connect() as conn:
        # auto_vacuum=2 = INCREMENTAL
        auto_vacuum = conn.execute(text("PRAGMA auto_vacuum")).scalar()
        assert int(auto_vacuum) == 2, f"auto_vacuum: got {auto_vacuum!r}, expected 2 (INCREMENTAL)"

        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        assert EXPECTED_TABLES.issubset(tables), f"missing tables: {EXPECTED_TABLES - tables}"

        obs_columns = {col["name"] for col in inspector.get_columns("observations")}
        assert "radar_image_path" in obs_columns, "observations.radar_image_path missing"

        tafs_uniques = {
            tuple(uc["column_names"])
            for uc in inspector.get_unique_constraints("tafs")
        }
        assert ("station_id", "issued_at", "amendment_type") in tafs_uniques
