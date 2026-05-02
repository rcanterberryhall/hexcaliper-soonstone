"""Shared pytest fixtures for soonstone tests."""
from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES_ROOT = Path(__file__).parent / "fixtures"


def _load_fixture_dir(subdir: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for path in sorted((FIXTURES_ROOT / subdir).glob("*.txt")):
        out[path.stem] = path.read_text(encoding="utf-8").strip()
    return out


@pytest.fixture(scope="session")
def metar_fixtures() -> dict[str, str]:
    """Map fixture-name (filename stem) -> raw METAR string."""
    return _load_fixture_dir("metars")


@pytest.fixture(scope="session")
def taf_fixtures() -> dict[str, str]:
    """Map fixture-name -> raw TAF string."""
    return _load_fixture_dir("tafs")
