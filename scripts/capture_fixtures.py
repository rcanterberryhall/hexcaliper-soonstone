"""One-shot dev script: capture a small corpus of real METAR + TAF strings
from the AWC API into tests/fixtures/.

Designed to be run manually when seeding fixtures, not from CI. Skips files
that already exist so re-running is idempotent (delete a file to re-capture
it).
"""
from __future__ import annotations

import sys
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
METAR_DIR = REPO_ROOT / "tests" / "fixtures" / "metars"
TAF_DIR = REPO_ROOT / "tests" / "fixtures" / "tafs"

# Florida ASOS stations chosen for variety: convective coast, panhandle, keys.
METAR_STATIONS = ["KMIA", "KTPA", "KMCO", "KEYW", "KTLH", "KJAX"]
TAF_STATIONS = ["KMIA", "KTPA", "KMCO", "KEYW", "KTLH", "KJAX", "KFLL", "KPBI"]

USER_AGENT = "soonstone-fixture-capture/0.0.1 (+soonstone.hexcaliper.com)"
BASE = "https://aviationweather.gov/api/data"


def _fetch(endpoint: str, station: str) -> str | None:
    url = f"{BASE}/{endpoint}"
    params = {"ids": station, "format": "raw"}
    resp = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=15)
    resp.raise_for_status()
    body = resp.text.strip()
    return body or None


def capture(endpoint: str, dest: Path, stations: list[str]) -> int:
    dest.mkdir(parents=True, exist_ok=True)
    written = 0
    for station in stations:
        target = dest / f"{station}_{endpoint}.txt"
        if target.exists():
            print(f"  skip (exists): {target.name}")
            continue
        try:
            body = _fetch(endpoint, station)
        except requests.RequestException as exc:
            print(f"  fail ({station}): {exc}", file=sys.stderr)
            continue
        if not body:
            print(f"  empty ({station})", file=sys.stderr)
            continue
        target.write_text(body + "\n", encoding="utf-8")
        print(f"  wrote: {target.name} ({len(body)} chars)")
        written += 1
    return written


if __name__ == "__main__":
    print("METARs:")
    n_metar = capture("metar", METAR_DIR, METAR_STATIONS)
    print("TAFs:")
    n_taf = capture("taf", TAF_DIR, TAF_STATIONS)
    print(f"\nDone. Wrote {n_metar} METARs and {n_taf} TAFs.")
