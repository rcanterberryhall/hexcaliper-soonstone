# Soonstone

Self-hosted forecast verification. Pulls METARs (observations) and TAFs (forecasts) from the FAA Aviation Weather Center, archives them, and visualizes how past forecasts converged on what actually happened.

The headline product is not a weather app. It is a *forecast trust* app.

The full design and roadmap live in [`soonstone_roadmap.md`](./soonstone_roadmap.md).

## v0 status

In active development. v0 covers ~59 Florida ASOS stations (METAR + TAF only), single Flask container, SQLite + WAL, Leaflet map UI. CONUS expansion is a one-line config change planned for v0.5.

## Quickstart (development)

```bash
git clone https://github.com/rcanterberryhall/hexcaliper-soonstone.git
cd hexcaliper-soonstone
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/alembic upgrade head
.venv/bin/pytest
```

If you have [`uv`](https://github.com/astral-sh/uv) installed, the venv + install steps collapse to `uv venv && uv pip install -e ".[dev]"` and run roughly an order of magnitude faster.

## Stack

- Python 3.11+ / Flask
- SQLite + WAL (file at `./data/soonstone.db`)
- SQLAlchemy 2.x ORM + Alembic migrations
- APScheduler for in-process job scheduling
- `metar` (PyPI) for METAR parsing; hand-rolled TAF parser
- Leaflet + CartoDB Positron tiles for the map UI

## Repo layout

See `soonstone_roadmap.md` "Project Layout" section. Plan and architectural docs live at the repo root alongside the roadmap.

## Design log

Notable deviations from the roadmap are recorded here as they happen.

- 2026-05-02 — Roadmap updated to switch from PostgreSQL 16 to SQLite + WAL. Rationale: aligns with the other three Hexcaliper apps; volume math (≤100M rows after 5 years at full CONUS scope) sits inside SQLite's working envelope. See `soonstone_roadmap.md` Resolved Decision #3 + Operational Notes / Scaling considerations.

## License

MIT (see `LICENSE`).
