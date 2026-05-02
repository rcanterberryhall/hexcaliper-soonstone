# Soonstone — Project Roadmap

A self-hosted forecast verification tool. Pulls METARs and TAFs (and later, NWS public forecasts) for ~59 Florida ASOS stations to start, archives them, and visualizes how well past forecasts predicted observed conditions. The headline product is not a weather app — it is a *forecast trust* app, showing convergence of past forecasts onto current observations and the empirical skill of forward-looking forecasts.

This document is the handoff for Claude Code to build the v0 prototype.

---

## Project Identity

**Name:** `Soonstone`. After the Norse *sólarsteinn* — a crystal that revealed the sun's position through overcast skies via polarized-light filtering. The original instrument cut through cloud cover to find the present; this project cuts through forecast noise to find the future, with appropriate honesty about how soon and how reliably. Joins the Hexcaliper Arthurian/CS-pun family (LanceLLMot, Parsival, merLLM) with a Pratchett-flavored register: a name that sounds like an artifact from a saga, with a small embedded joke about the inherent tentativeness of forecasting.

**Domain:** `weather.hexcaliper.com`, routed through the existing Cloudflare Tunnel.

**Repo location:** `/GitHub/soonstone/` on the R730.

**Python package:** `soonstone`.

**Stack:**

- Python 3.11+ with Flask (matches existing Hexcaliper services)
- SQLite with WAL mode (consistent with other Hexcaliper projects; volume justifies it but doesn't require Postgres — see Operational Notes for the scaling analysis)
- APScheduler for in-process job scheduling (avoids cron coupling)
- Leaflet.js + CartoDB Positron tiles for the frontend map
- Vanilla JS frontend, no build step for v0 (React only if complexity demands it later)

**Deployment:** single application container via `docker-compose`, with a volume-mounted SQLite database file. Routed through the existing Cloudflare Tunnel using the `setup_cloudflare.sh` conventions. The database is a file at `./data/soonstone.db` on the host, mounted into the container at `/data/soonstone.db`.

---

## Conceptual Foundation

The project answers a single question per station: **how does the forecast trajectory for "right now" look as it converged from 24 hours out?**

For any given station and observation time `T`:

- We have an observation at `T` (the METAR closest to `T`).
- We have a forecast trajectory: the values that successive forecasts predicted for time `T`, issued at `T-24h`, `T-12h`, `T-6h`, `T-3h`, `T-1h`.
- The trajectory should converge on the observation. The shape of that convergence is the story.

The product extends this forward: for any future time `T+N`, we show the current forecast plus an empirical skill envelope derived from how forecasts at this station have historically performed at lead time `N`.

This is a *verification-first* product, not a forecast product. We do not generate forecasts; we score them.

---

## Data Sources for v0

Two sources, both free, both keyless, both from the FAA/NWS Aviation Weather Center.

**METAR (observations):**

- Endpoint: `https://aviationweather.gov/api/data/metar`
- Pull: hourly at `:55` past the hour, plus `:25` past for SPECI catch
- Bounding box query for the active scope (Florida for v0, CONUS for v0.5+) gets all stations in one HTTP call
- Format: JSON or raw METAR text — request JSON for v0
- No authentication, no rate limits documented; be polite (one query per pull cycle)

**TAF (forecasts):**

- Endpoint: `https://aviationweather.gov/api/data/taf`
- Pull: every 30 minutes (TAFs issue at 00/06/12/18Z, plus amendments at any time)
- Same JSON option, same bounding box approach
- Stores both the raw TAF and parsed change groups

The bounding box for v0 is approximately `(24.0, -88.0, 31.5, -79.5)` covering Florida and adjacent waters. The bounding box is configurable; expanding to CONUS is a config change.

These two sources alone give us the v0 product. Adding NWS gridpoint forecasts (for PoP, QPF, temp) is a v1 addition — see Roadmap below.

---

## Database Schema

SQLite. UTC everywhere, stored as ISO 8601 text strings (e.g. `2026-05-02T17:53:00Z`). Composite primary keys to make idempotent ingestion natural. JSON arrays and objects stored as text in JSON-typed columns; SQLite's JSON1 functions are available if needed but for v0 we read and write whole.

```sql
CREATE TABLE stations (
    station_id      TEXT PRIMARY KEY,           -- ICAO identifier, e.g. KMIA
    name            TEXT,
    latitude        REAL NOT NULL,
    longitude       REAL NOT NULL,
    elevation_m     REAL,
    state           TEXT,
    station_type    TEXT,                       -- ASOS, AWOS, etc.
    taf_site        INTEGER NOT NULL DEFAULT 0, -- boolean: does this station issue TAFs?
    active          INTEGER NOT NULL DEFAULT 1, -- boolean
    first_seen      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    last_seen       TEXT
);

CREATE TABLE observations (
    station_id          TEXT NOT NULL REFERENCES stations(station_id),
    observed_at         TEXT NOT NULL,          -- ISO 8601 UTC, e.g. '2026-05-02T17:53:00Z'
    raw_metar           TEXT NOT NULL,
    metar_type          TEXT,                   -- METAR or SPECI
    temp_c              REAL,
    dewpoint_c          REAL,
    wind_dir_deg        INTEGER,
    wind_speed_kt       REAL,
    wind_gust_kt        REAL,
    visibility_sm       REAL,
    altimeter_inhg      REAL,
    precip_1hr_in       REAL,
    present_weather     TEXT,                   -- JSON array, e.g. '["TSRA","BR"]'
    cloud_layers        TEXT,                   -- JSON: [{"cover":"BKN","base_ft":3500}, ...]
    ceiling_ft          INTEGER,                -- derived: lowest BKN/OVC base
    flight_category     TEXT,                   -- VFR/MVFR/IFR/LIFR (derived)
    radar_image_path    TEXT,                   -- relative path to radar PNG/WebP frame; NULL until v1 radar ingester runs
    ingested_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    PRIMARY KEY (station_id, observed_at)
);

CREATE INDEX idx_obs_observed_at ON observations(observed_at);

CREATE TABLE tafs (
    taf_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    station_id          TEXT NOT NULL REFERENCES stations(station_id),
    issued_at           TEXT NOT NULL,
    valid_from          TEXT NOT NULL,
    valid_to            TEXT NOT NULL,
    raw_taf             TEXT NOT NULL,
    amendment_type      TEXT,                   -- NULL, AMD, COR, RTD
    parse_method        TEXT NOT NULL DEFAULT 'deterministic',  -- deterministic | llm_fallback | failed
    parse_confidence    REAL,                   -- only set for llm_fallback (0-1)
    parse_warnings      TEXT,                   -- JSON array, e.g. '["unrecognized_change_group"]'
    ingested_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE (station_id, issued_at, amendment_type)
);

CREATE INDEX idx_tafs_station_issued ON tafs(station_id, issued_at);
CREATE INDEX idx_tafs_valid_range ON tafs(valid_from, valid_to);

CREATE TABLE taf_groups (
    taf_id              INTEGER NOT NULL REFERENCES tafs(taf_id) ON DELETE CASCADE,
    group_index         INTEGER NOT NULL,       -- 0 = base, 1+ for change groups
    group_type          TEXT NOT NULL,          -- BASE, FM, BECMG, TEMPO, PROB30, PROB40
    group_from          TEXT NOT NULL,
    group_to            TEXT NOT NULL,
    probability_pct     INTEGER,                -- 30, 40, or NULL
    wind_dir_deg        INTEGER,
    wind_speed_kt       REAL,
    wind_gust_kt        REAL,
    visibility_sm       REAL,
    weather             TEXT,                   -- JSON array
    cloud_layers        TEXT,                   -- JSON
    ceiling_ft          INTEGER,
    flight_category     TEXT,
    PRIMARY KEY (taf_id, group_index)
);

CREATE INDEX idx_taf_groups_temporal ON taf_groups(group_from, group_to);
```

Notes:

- `present_weather`, `weather`, and `parse_warnings` are stored as JSON array text because METAR/TAF can list multiple weather phenomena (e.g. `+TSRA BR FG`). Application layer serializes/deserializes; SQLite's `json_each()` is available if needed.
- `cloud_layers` is JSON object text rather than a separate table because we always query layers together with the parent observation/group.
- `flight_category` is denormalized for easy querying of VFR/MVFR/IFR/LIFR distributions.
- `taf_site` and `active` use `INTEGER 0/1` (SQLite's boolean convention).
- All timestamps are ISO 8601 UTC text with the `Z` suffix. They sort correctly as strings, and SQLite's `datetime()` and `julianday()` functions work on this format.
- The `tafs` UNIQUE constraint on `(station_id, issued_at, amendment_type)` allows a routine TAF and its later amendment to coexist.
- Foreign keys require `PRAGMA foreign_keys = ON;` at every connection — set this in the SQLAlchemy connect args, easy to forget.

### Required SQLite pragmas

Set these on every connection (SQLAlchemy `connect_args` or a `connect` event listener):

```python
PRAGMA journal_mode = WAL;          # readers don't block writers, durable
PRAGMA synchronous = NORMAL;        # relaxed durability vs FULL, much faster
PRAGMA foreign_keys = ON;           # enforce FK constraints
PRAGMA cache_size = -64000;         # 64MB page cache
PRAGMA temp_store = MEMORY;         # temp tables/indexes in RAM
PRAGMA mmap_size = 268435456;       # 256MB memory-mapped I/O
PRAGMA busy_timeout = 5000;         # wait up to 5s for locks
```

The `auto_vacuum = INCREMENTAL` pragma must be set *before* any tables exist, so include it in the very first migration as a `PRAGMA auto_vacuum = INCREMENTAL;` statement before any CREATE TABLE.

---

## Service Architecture

Single Flask app, four background jobs, three API endpoints for v0.

### Background jobs (APScheduler)

1. **`refresh_stations`** — runs once at startup and weekly thereafter. Pulls the AWC station list, upserts into `stations`. Filters to the active scope: ASOS/AWOS within the configured bounding box, plus any station within the box that has issued a TAF in the last 30 days. For v0 this is Florida (~59 stations); the bounding box and state filter are config-driven.

2. **`ingest_metars`** — runs every 30 minutes at `:25` and `:55`. Bounding-box query for CONUS, parses each METAR, upserts into `observations`. Idempotent on `(station_id, observed_at)`.

3. **`ingest_tafs`** — runs every 30 minutes (offset from METARs by 5 minutes to spread load). Bounding-box query for CONUS TAFs. For each TAF, parses the change groups, inserts the parent row plus group rows. The UNIQUE constraint handles duplicates.

4. **`prune_old`** — runs daily at 04:00 UTC. Deletes raw_metar/raw_taf strings older than 30 days (we keep the parsed columns indefinitely; raw text is only useful for re-parsing if the parser improves). Optional for v0.

### API endpoints

1. **`GET /api/stations`** — returns GeoJSON FeatureCollection of all active stations. Cached 5 minutes. Used to render map markers.

2. **`GET /api/stations/<station_id>/snapshot`** — returns the convergence panel for the station. Convergence and forward arrays have variable length per station, matching the actual TAF issuance cadence rather than fixed lead times. Shape:

```json
{
  "station": {"id": "KMIA", "name": "Miami Intl", "lat": ..., "lon": ...},
  "now": {
    "observed_at": "2026-05-01T17:53:00Z",
    "wind": "180/12G18", "vis": 10, "weather": [],
    "ceiling_ft": null, "flight_category": "VFR"
  },
  "convergence": [
    {
      "issued_at": "2026-04-30T17:32:00Z",
      "amendment_type": null,
      "lead_hours": 24.4,
      "forecast_source": "TAF",
      "wind": "...", "vis": ..., "weather": [], "flight_category": "..."
    },
    {
      "issued_at": "2026-04-30T23:28:00Z",
      "amendment_type": null,
      "lead_hours": 18.4,
      "forecast_source": "TAF",
      "wind": "...", ...
    },
    {
      "issued_at": "2026-05-01T05:31:00Z",
      "amendment_type": null,
      "lead_hours": 12.4,
      "forecast_source": "TAF",
      "wind": "...", ...
    },
    {
      "issued_at": "2026-05-01T11:30:00Z",
      "amendment_type": null,
      "lead_hours": 6.4,
      "forecast_source": "TAF",
      "wind": "...", ...
    },
    {
      "issued_at": "2026-05-01T14:18:00Z",
      "amendment_type": "AMD",
      "lead_hours": 3.6,
      "forecast_source": "TAF",
      "wind": "...", ...
    }
  ],
  "forward": [
    {
      "valid_at": "2026-05-01T18:00:00Z",
      "lead_hours": 0.1,
      "forecast_source": "TAF",
      "group_type": "BASE",
      "wind": "...", ...
    },
    {
      "valid_at": "2026-05-01T22:00:00Z",
      "lead_hours": 4.1,
      "forecast_source": "TAF",
      "group_type": "FM",
      "wind": "...", ...
    },
    {
      "valid_at": "2026-05-02T00:00:00Z",
      "lead_hours": 6.1,
      "forecast_source": "TAF",
      "group_type": "TEMPO",
      "probability_implicit": true,
      "wind": "...", "weather": ["TSRA"], ...
    }
  ]
}
```

Notes on the shape:
- `convergence` is an array of every distinct TAF issuance (routine + amendments) that was active during the last 24 hours. Length is variable per station — typically 4-5 in quiet weather, more during active weather with amendments.
- `forward` is an array of the *change groups* in the currently active TAF, evaluated at their respective valid times. The `group_type` field carries the TAF semantics (BASE/FM/BECMG/TEMPO/PROB30/PROB40) so the frontend can render TEMPO/PROB groups as caveats rather than primary forecasts.
- All forecast objects are wrapped with a `forecast_source` field so v1's NWS gridpoint additions can use the same response shape without breaking the contract (resolves Open Question #2).
- `lead_hours` is precise (decimal), computed from the actual issuance/observation timestamps. The frontend can display this as "23 hours ago" or similar.

3. **`GET /`** — serves the static HTML+JS Leaflet frontend.

### TAF resolution logic

This is the only non-trivial piece of business logic. Given a station, a target time `T`, and a TAF issuance time, return the predicted state at `T`:

1. Find the TAF for that station whose `issued_at` is the latest at or before the issuance time, AND whose `(valid_from, valid_to)` covers `T`. If amendments exist, prefer the latest amendment whose `issued_at` is still ≤ the issuance time.
2. Start with the BASE group's state.
3. Walk groups in order:
   - If group is `FM` and `group_from <= T`: replace state with this group's state.
   - If group is `BECMG` and `group_from <= T <= group_to`: blend (in v0, just use this group's state if `T >= midpoint`).
   - If group is `BECMG` and `T > group_to`: replace state with this group's state.
4. Skip `TEMPO`, `PROB30`, `PROB40` for the deterministic state — but return them separately as "alternate states" so the frontend can render them as caveats ("30% chance of TSRA between 21Z-23Z").

For the convergence query (cadence-matched):

- Find every TAF for the station whose `issued_at` falls in the window `[now - 24h, now]`. This includes both routine TAFs and amendments.
- For each such TAF, resolve its predicted state at time `now` using the resolution logic above. Skip TAFs whose `valid_to < now` (they don't cover the current moment) — these are stale forecasts that were superseded.
- Return chronologically by `issued_at`, oldest first. The leftmost column in the convergence panel is the oldest forecast; the rightmost is the most recent forecast issued (or amendment).
- Each entry carries its own `lead_hours` (computed from issuance time vs. now) and `amendment_type`, so the frontend can label routine TAFs vs. AMD/COR explicitly.

For the forward query:

- Identify the currently active TAF (the latest TAF whose `(valid_from, valid_to)` covers `now`, preferring amendments).
- Walk its change groups in order. For each group, evaluate the predicted state at the group's natural anchor time (the `group_from` for FM/BECMG; the start of the window for TEMPO/PROB; `now` for BASE if no later groups apply).
- Return chronologically. The frontend renders BASE/FM/BECMG as the primary forecast trajectory and TEMPO/PROB groups as caveats overlaid on the relevant time windows.

---

## Frontend (v0)

Single HTML page served from Flask. Vanilla JS, Leaflet from CDN, CartoDB tiles.

### Map

- Center on Florida for v0, zoom level 6 (`[28.0, -83.5]`). When the scope expands in v0.5, change to CONUS center at zoom 4.
- One `L.circleMarker` per station, fillColor by `flight_category` (VFR=green, MVFR=blue, IFR=red, LIFR=magenta) — same color scheme as aviation weather convention.
- Marker size constant. Click opens a popup; popup loads snapshot data on demand.

### Popup layout

Three vertical sections inside the popup:

1. **Now (METAR observation):** wind, vis, weather, ceiling, flight category. Anchored to the most recent METAR's timestamp (displayed: "Conditions at 17:53Z, 12 minutes ago").
2. **Convergence:** a horizontal strip of cells, one per TAF issuance in the last 24 hours, oldest left to newest right. Variable column count per station — typically 4-5 in quiet weather, more during active weather with amendments. Each cell shows the issuance time, lead time ("23h ago"), amendment marker if any (AMD/COR badge), and the predicted state (wind, vis, weather, ceiling, flight category). Cells where the predicted state diverges from the observed `Now` are highlighted (e.g. red border if the predicted flight category differed from observed).
3. **Forward forecast:** a horizontal strip of cells representing the current TAF's change groups in chronological order. Each cell shows the group type (BASE/FM/BECMG), the time window it applies to, and the predicted state. TEMPO and PROBnn groups render as smaller "caveat" cells overlaid on the relevant time window, visually distinct from the deterministic groups.

The variable column count is intentional — it makes amendment behavior visible. When a TAF gets amended, an AMD column appears in the convergence strip, and the user can immediately see what changed between the routine TAF and the amendment.

### Future frontend (not v0)

- Convergence sparkline charts using uPlot or D3 (lightweight)
- Forward forecast skill envelope shaded by historical MAE at this station
- Reliability diagrams on a separate `/calibration/<station_id>` page
- "Trust dial" computed via fuzzy inference (see roadmap)

---

## Parsers

METAR parsing: use the `metar` Python library (PyPI: `metar`). It is mature, handles edge cases, and produces structured output. Wrap it to map onto our schema.

TAF parsing: there is no battle-tested Python TAF parser. Options:

- **Recommended for v0:** write a focused parser that handles the subset we need. The TAF grammar is well-specified (FAA Order 7900.5 / WMO 49). Parse the header (`issued_at`, `valid_from`, `valid_to`, `amendment_type`), then iterate change groups. For each group, parse: type (`FM`, `BECMG`, `TEMPO`, `PROBnn`), time window, wind, visibility, weather codes, cloud layers. Skip wind shear, icing, turbulence for v0.
- **Alternative:** use `pytaf` from PyPI as a starting point and patch as needed. It is older but functional.

The parser must be deterministic and lossless on the fields we extract. Round-trip test: parse a known TAF, serialize the structured output, compare key fields. Build a small fixture set of real TAFs (10-20 from various stations including amendments and multiple change groups) for unit tests.

Both parsers should be in `soonstone/parsers/` with clean separation: `metar_parser.py`, `taf_parser.py`. Each exports a single function that takes raw text and returns a typed dict matching the database schema.

### LLM strategy

The deterministic parser is the **only** code path that writes verification-grade data. LLMs are used in the development loop, not the runtime hot path. Specific allowed uses:

**Development-time (always OK):**

- Generating the parser code itself from the FAA/WMO spec — this is what Claude Code is doing.
- Labeling and categorizing the fixture corpus (e.g. "tag each of these 200 real TAFs with the change-group types it contains") to ensure test coverage of the long tail.
- Periodic analysis of accumulated parse failures to identify recurring patterns worth handling deterministically.

**Runtime fallback (v1, NOT v0):**

When the deterministic parser fails on a TAF, the row is still inserted with `parse_method = 'llm_fallback'`, `parse_confidence` set by the LLM, and `parse_warnings` listing what the LLM was uncertain about. This preserves the data point without polluting the deterministic dataset.

Verification queries default to `WHERE parse_method = 'deterministic'`. Fallback rows are explicitly opt-in. The fallback path is rate-limited (e.g. max 50/hour) and disabled entirely by a config flag for environments that should never call out.

**Forbidden:**

- LLM as the primary parser for any TAF.
- LLM output overriding deterministic output for the same TAF.
- LLM-parsed rows being included in calibration math without an explicit flag.

### v0 parser scope

For v0, the deterministic parser is the only path. Parse failures are logged with the raw TAF text and dropped — no row is inserted. The LLM fallback infrastructure (`parse_method` column, fallback handler, config flag) is wired up in the schema and code skeleton but the fallback handler is a no-op stub that just logs. v1 implements the actual LLM fallback call.

---

## Project Layout

```
soonstone/
├── README.md
├── pyproject.toml                  # uses uv or pip-tools
├── Dockerfile
├── docker-compose.yml              # single app service + volume
├── install.sh                      # follows existing pattern
├── DEPLOYMENT.md                   # follows existing pattern
├── data/                           # gitignored; holds soonstone.db (host-side mount target)
├── alembic/                        # database migrations (Alembic supports SQLite)
│   ├── env.py
│   └── versions/
│       └── 0001_initial.py
├── soonstone/
│   ├── __init__.py
│   ├── app.py                      # Flask app factory
│   ├── config.py                   # env-driven config
│   ├── db.py                       # SQLAlchemy session, engine, pragma listener
│   ├── models.py                   # SQLAlchemy ORM models
│   ├── parsers/
│   │   ├── __init__.py
│   │   ├── metar_parser.py
│   │   └── taf_parser.py
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── awc_client.py           # HTTP client for aviationweather.gov
│   │   ├── stations.py             # refresh_stations job
│   │   ├── metars.py               # ingest_metars job
│   │   └── tafs.py                 # ingest_tafs job
│   ├── verification/
│   │   ├── __init__.py
│   │   └── taf_resolve.py          # resolve TAF to state at time T
│   ├── api/
│   │   ├── __init__.py
│   │   ├── stations.py             # GET /api/stations
│   │   └── snapshot.py             # GET /api/stations/<id>/snapshot
│   ├── scheduler.py                # APScheduler setup
│   └── static/
│       └── index.html              # the entire frontend, single file
├── tests/
│   ├── fixtures/
│   │   ├── metars/
│   │   └── tafs/
│   ├── test_metar_parser.py
│   ├── test_taf_parser.py
│   └── test_taf_resolve.py
└── scripts/
    ├── seed_stations.py            # one-time bootstrap
    └── backfill_metars.py          # optional: pull historical from IEM
```

### docker-compose.yml shape

```yaml
services:
  soonstone:
    build: .
    container_name: soonstone
    restart: unless-stopped
    volumes:
      - ./data:/data
      - ./logs:/var/log/soonstone
    environment:
      - DATABASE_URL=sqlite:////data/soonstone.db
      - TZ=UTC
    networks:
      - cloudflare-tunnel

networks:
  cloudflare-tunnel:
    external: true
```

The database is a single file at `./data/soonstone.db` on the host, mounted into the container. Backups are file-level operations on the host. No second container, no networked database, no port management.

---

## v0 Acceptance Criteria

The prototype is done when:

1. The Flask app starts cleanly via `install.sh` and `docker-compose up`.
2. Background jobs run on schedule and populate the database without errors for at least 24 consecutive hours.
3. The map renders at `https://weather.hexcaliper.com` with all Florida ASOS stations visible.
4. Clicking a station that has both a recent METAR and a TAF from ~24h ago shows a populated three-section popup.
5. The convergence strip shows at least one column for stations with sufficient TAF history (i.e., any station that has had at least one TAF issuance in the last 24 hours), with column count varying per station based on actual TAF issuances during the window.
6. The forward strip shows the change groups of the currently active TAF in chronological order, with TEMPO/PROB groups visually distinct from BASE/FM/BECMG groups.
7. Parsers pass unit tests against the fixture set.

What v0 does *not* need:

- Reliability diagrams, Brier scores, or any calibration math
- NWS gridpoint forecasts, MRMS, SPC outlooks
- Radar imagery (the `radar_image_path` column exists, defaults to NULL; v1 adds the IEM ingester and the daily WebP archival job)
- Charts or visualizations beyond the text-based popup
- Multi-provider comparison
- Fuzzy trust inference
- Historical backfill (start fresh from deployment time)
- Active LLM fallback for parse failures (the schema column and stub handler exist; the actual LLM call is v1)
- LLM-generated TAF summaries (v2)

---

## Roadmap Beyond v0

These are not for Claude Code's first pass. Listed so the architecture choices in v0 do not foreclose them.

**v1 — NWS Public Forecast layer + radar imagery + LLM fallback parser.** Three additions, all hanging off the existing METAR/TAF infrastructure.

NWS gridpoint forecasts: extends the forecast model with PoP, QPF, temp, dewpoint, sky cover. Requires a `points` lookup per station (cached). New row in the popup for "NWS public forecast" alongside the TAF row.

Per-station historical radar imagery via IEM (Iowa Environmental Mesonet): on each METAR ingest (hourly cadence; SPECIs skipped in v1), fetch a pre-rendered radar reflectivity image from IEM centered on the station at the METAR timestamp (matched to the closest 5-minute radar frame). Save as PNG to hot storage at `./data/radar/hot/{station_id}/{YYYYMMDDHH}Z.png`. Update `observations.radar_image_path` to point at the file. Failed fetches log a warning and leave the path NULL — radar is decoration, METAR ingestion is canonical and must not block on it. The popup's Now section renders this image alongside the textual METAR fields, giving the user visual context for what the observation captured.

A new daily APScheduler job runs at 04:00 UTC: for each station, gather hot PNGs older than 24 hours, encode them into a single animated WebP at `./data/radar/archive/{station_id}/{YYYY-MM-DD}.webp`, atomically update `observations.radar_image_path` to point at frames within the WebP using a `#frame=N` URL convention, and delete the source PNGs. The Flask static-file route handles both formats transparently. Animated WebP delta encoding compresses the daily set ~4-6x over the sum of individual PNGs and renders natively as a radar loop in the browser, which is itself a feature for v3+ historical viewing.

LLM fallback for TAF parse failures: failed parses fire a single LLM call to extract structured fields, row is inserted with `parse_method = 'llm_fallback'`. Rate-limited and toggleable via config.

**v1.1 — Live radar tile overlay on the map.** Add a translucent radar reflectivity layer to the Leaflet map showing live conditions across the Florida bounding box. Frontend-only feature: ~50 lines of JavaScript, no backend changes, no new ingestion. Source is RainViewer's free public tile API (`api.rainviewer.com/public/weather-maps.json` for the timestamp manifest, `tilecache.rainviewer.com` for the tiles themselves). The user's browser fetches tiles directly from RainViewer's CDN — Soonstone's server is not in the data path.

UI elements: an opacity-0.6 radar layer toggleable via a Leaflet layer-control widget; a small time scrubber showing the last ~2 hours of radar history (RainViewer's free tier limit), defaulted to "now"; auto-refresh every 10 minutes to pull in new frames.

Attribution: "Radar © RainViewer" added to the map's attribution corner alongside the existing OSM/CARTO line. Required by their terms.

Why a third-party tile source rather than self-hosted: live radar tile rendering from MRMS GRIB2 is several weeks of engineering work involving GRIB2 parsing, raster tile generation, and a tile server. Not v1 worthy. RainViewer is purpose-built for this use case, free, reliable, and replaceable — if the dependency ever becomes a concern, swapping in IEM's tile service or self-hosted tiles is a localized frontend change.

The user flow this enables: glance at the map, see a storm forming over central Florida, click the nearest station, see the popup confirming via METAR + per-station radar history that the forecast did or didn't anticipate it. The live overlay is convenience and context; the popup remains where the verification thesis lives.

**v1.5 — Parser hardening loop.** Weekly job pulls `parse_method = 'llm_fallback'` rows from the past week, summarizes recurring patterns via LLM analysis, generates a dev task list of edge cases to add to the deterministic parser. Manual triage; no automatic code generation.

**v2 — Convergence visualization + plain-English TAF summaries.** Replace text-based popup with sparkline charts showing the forecast trajectory converging on the observation. uPlot is the right library. Also adds an optional one-sentence LLM-generated summary of the current TAF ("Current forecast predicts deteriorating conditions with thunderstorms possible 21Z-00Z, then improving overnight"). Cached per-TAF-issuance so each TAF is summarized exactly once. This is a display feature only and never feeds verification math.

**v3 — Calibration page.** Per-station `/calibration/<station_id>` page with reliability diagrams for PoP, lead-time skill curves for temp/wind, Brier decomposition. Requires a nightly aggregation job that precomputes per-station, per-variable, per-lead-time stats.

**v4 — Fuzzy trust inference.** Mamdani fuzzy system combining forecast volatility, convergence direction, and historical skill into a "trust score" rendered as a dial on each forward forecast. Rule base in plain English; membership functions tuned against held-out verification data.

**v5 — SPC convective outlook scoring.** Ingest SPC Day 1/2/3 outlooks. Score categorical and probabilistic outlooks against Local Storm Reports. New page for convective forecast performance.

**v6 — Multi-provider comparison.** Add Open-Meteo, Pirate Weather, OpenWeatherMap as additional forecast sources. Score each against the same ground truth. Public-facing reliability scoreboard.

---

## Operational Notes

- **Time zones:** UTC everywhere in the database and in API responses. Stored as ISO 8601 text with `Z` suffix. Convert to local time only at render time in the frontend, using the browser's locale.
- **Idempotency:** every ingestion job must be safe to re-run. The composite primary keys and UNIQUE constraints handle this; use SQLite's `INSERT OR IGNORE` (or SQLAlchemy's `on_conflict_do_nothing`) for the natural insert path. The only legitimate update is the `last_seen` timestamp on stations.
- **Rate limits:** AWC does not document explicit rate limits, but be respectful — one bounding-box query per ingestion cycle, not per-station polling.
- **Logging:** structured JSON logging. Each ingestion run logs counts (stations updated, METARs ingested, TAFs ingested, parse errors). Errors include the raw text that failed to parse for offline debugging.
- **Monitoring:** `/health` returns 200 if both the METAR ingestion job and the TAF ingestion job have completed successfully (no exception raised, end-to-end success) within the last 90 minutes. This checks job health, not data freshness — a station with no amendments will routinely have its most recent TAF be older than 90 minutes, and that is normal. Cloudflare Tunnel can health-check this endpoint.
- **Database backups (v0):** nightly file-level copy of `./data/soonstone.db` to the existing NAS path used by other Hexcaliper services. SQLite's safe online backup is `sqlite3 soonstone.db ".backup '/nas/path/soonstone.$(date +%Y%m%d).db'"`. Plain `cp` while WAL is active is *not* safe; use the `.backup` command or stop ingestion briefly.
- **Database backups (v1.5+):** when the database crosses ~1GB, switch to Litestream for continuous replication to NAS or S3-compatible object storage. Single binary, runs as a sidecar process, supports point-in-time recovery, no impact on application performance. Configuration is a single YAML file.

### Scaling considerations

SQLite is the right choice for v0 (Florida, ~59 stations) and remains the right choice through v0.5 (full CONUS, ~900 stations) and beyond. Volume math:

- v0 (Florida): ~500K rows/year across all tables
- v0.5 (CONUS): ~20M rows/year (observations + tafs + taf_groups)
- v0.5 + 5 years: ~100M rows total

This is well inside SQLite's working envelope. Production SQLite databases routinely run 1B+ rows. The access patterns for Soonstone — sequential ingestion, point lookups by `(station_id, time)`, narrow time-range queries — are exactly what SQLite indexes efficiently.

The pragmas in the schema section (especially WAL, mmap, and 64MB cache) matter more as the database grows. They are not optional at CONUS scale.

`VACUUM` becomes expensive once the database is large (10+ minutes at 100M rows, with a write lock for the duration). The `auto_vacuum = INCREMENTAL` pragma in the initial migration enables `PRAGMA incremental_vacuum;` to reclaim space in small chunks without long locks. Run `PRAGMA incremental_vacuum(1000);` weekly to release a few thousand pages at a time. Run `ANALYZE` weekly as well so the query planner has fresh statistics.

The threshold to migrate to Postgres is *not* row count or database size. It is concurrency: when Soonstone has multiple concurrent writers (e.g. a separate analytics service writing back computed calibration scores while ingestion is running), or when long-running analytics queries start blocking ingestion in practice, that is the signal. None of this is plausible before v3+. Migration when needed is a known one-day operation: dump SQLite → load Postgres → swap the connection string.

### Radar storage (v1+)

Radar imagery is stored on the filesystem, not in SQLite. SQLite holds only the relative path on `observations.radar_image_path`. Two-tier storage:

- **Hot:** `./data/radar/hot/{station_id}/{YYYYMMDDHH}Z.png` — last 24 hours, individual PNG per hourly METAR. Served directly by Flask static-file route.
- **Cold:** `./data/radar/archive/{station_id}/{YYYY-MM-DD}.webp` — daily animated WebP, ~24 frames per day per station, frame-delta compressed. Path on observation rows uses `#frame=N` suffix (e.g. `archive/KMIA/2026-05-02.webp#frame=17`); the Flask route parses this and extracts the requested frame from the WebP on demand.

Volume estimates per year, assuming ~50KB per hot PNG and ~300KB per daily archive WebP per station:

- v0/v1 (Florida, ~59 stations): hot ~70MB rolling, archive ~6.5GB/year
- v0.5 (CONUS, ~900 stations): hot ~1GB rolling, archive ~100GB/year

The daily archival job (runs 04:00 UTC) handles compression atomically: encode WebP, update observation rows in a single transaction, delete hot PNGs only after the WebP is durably written. Idempotent on partial failure.

Retention policy is configurable. v1 keeps everything indefinitely; if storage becomes a concern at CONUS scope, drop archives older than N years or downsample to 3-hourly frames for old data. Not a v1 concern.

---

## Getting Started for Claude Code

Suggested order of operations:

1. Set up the project skeleton (`pyproject.toml`, directory structure, empty modules).
2. Write `models.py` and the initial Alembic migration. The first migration must include `PRAGMA auto_vacuum = INCREMENTAL;` before any CREATE TABLE. Verify schema by running migrations against a local SQLite database file.
3. Write `awc_client.py` with one method per endpoint (METAR, TAF, station list). Hit the real API and inspect responses; commit fixture JSON files for offline testing.
4. Write `metar_parser.py` using the `metar` library. Unit-test against the fixtures.
5. Write `taf_parser.py` from scratch or by adapting `pytaf`. Unit-test against the fixtures including amendments and multiple change groups.
6. Write the ingestion jobs (`stations.py`, `metars.py`, `tafs.py`) as plain functions; wire them into APScheduler in `scheduler.py`.
7. Write `taf_resolve.py` with the resolution logic. Unit-test edge cases: TAF with only BASE, TAF with FM groups, TAF with BECMG, TAF with TEMPO, amended TAF.
8. Write the API endpoints. Test with curl against a database that has been ingesting for at least an hour.
9. Write `static/index.html` — Leaflet map, fetch stations, click handler for popup. Verify against a running backend.
10. Write `install.sh`, `docker-compose.yml`, `DEPLOYMENT.md`. Deploy to the R730. Configure the Cloudflare Tunnel route.

Any deviation from this plan is fine if there is a good reason — but document the deviation in the README's design log so the next handoff knows what changed and why.

---

## Resolved Decisions

These were open questions that have been answered. Listed here so the rationale is preserved.

1. **Project name:** `Soonstone`. After the Norse *sólarsteinn*, with a pun on "soon" — the original instrument cut through cloud cover to find the present sun, this project cuts through forecast noise to find the future weather. Pratchett-flavored register fits the existing Hexcaliper naming family. Repo at `/GitHub/soonstone/`, Python package `soonstone`, served at `weather.hexcaliper.com`.
2. **Domain:** `weather.hexcaliper.com`.
3. **Database engine and deployment:** SQLite with WAL mode, single application container, volume-mounted database file at `./data/soonstone.db`. Consistent with other Hexcaliper projects. Volume math (5K rows/day at v0, 50K/day at full CONUS, ~100M rows after 5 years at full scale) sits comfortably inside SQLite's working envelope. SQLite is in-process and not amenable to its own container — a separate "database container" would either be a no-op (volume-only) or would turn SQLite into a worse Postgres via a network protocol. Migration to Postgres is a known one-day operation if concurrency requirements ever justify it; see Operational Notes for the threshold.
4. **Initial station scope:** Florida ASOS/AWOS only, ~59 stations. Chosen because Florida gets frequent convective weather, so the verification angle has signal from day one. Convective TAFs (TEMPO TSRA, PROB30/40 groups) will appear in the dataset within hours of deployment most days from late spring through early fall. Expanding to full CONUS (~900 stations) is a one-line config change once the parser and ingestion are verified working — planned for v0.5 once v0 has run cleanly for ~72 hours.
5. **Backfill posture:** no backfill at deployment. The first 24 hours of operation will show empty or partial convergence panels while data accumulates. Acceptable tradeoff to avoid IEM integration work in v0; a clean start also gives us a clean test of the ingestion pipeline without confounding it with imported data of different provenance. IEM backfill remains an option for a later version if early operational experience shows it would meaningfully improve the user experience.
6. **Convergence cadence:** match the meteorological cadence rather than fixing arbitrary lead times. The convergence panel shows the *distinct TAF issuances* that were active during the last 24 hours leading up to `now`, in chronological order. For a station with no amendments, this is typically 4-5 columns (the routine TAFs at 00/06/12/18Z that fall within the 24h window). For a station with amendments, additional columns appear as they were issued. This is more honest about what TAFs actually offer and makes amendment behavior visible — when a TAF gets amended, you literally see the new column appear in the convergence panel and you can compare what the routine TAF said versus what the amendment changed. The variable column count is a feature, not a bug: stations in active weather will have richer convergence panels than stations in quiet weather. The forward panel uses the same logic in reverse — show the current TAF's change groups as the forecast trajectory, not arbitrary fixed lead times.
7. **"Now" definition:** the most recent METAR (or SPECI) for the station, period. Not a mixed source that prefers fresher raw sensor data when available. METAR is the ground truth for verification because it has uniform sensor suites, consistent QC, and predictable issuance cadence. Mixing in raw current-conditions feeds would introduce silent biases — different stations would have different sensor coverage in their "Now" cell, and present-weather codes (TSRA, etc.) would be inconsistently reported. The "Now" cell must be uniform across stations because everything else in the popup is measured against it. Freshness is not the metric to optimize; consistency is. The METAR's actual timestamp is displayed prominently in the popup ("Conditions at 17:53Z, 12 minutes ago"), and the convergence panel's lead times anchor to that timestamp rather than wall-clock now.
8. **TAF parser strategy:** Claude Code's judgment. Recommendation in the Parsers section is hand-rolled to keep the dependency surface small and the parsing logic transparent for the verification math; `pytaf` is acceptable as a starting point if its code quality looks good on inspection.
9. **Public exposure:** Cloudflare Tunnel only, behind Cloudflare Access like other Hexcaliper services. Private to start. v0 does not need rate limiting or a robots.txt. If the project later becomes public-facing, those concerns get added then.
10. **Health check semantics:** `/health` returns 200 if both the METAR ingestion job and the TAF ingestion job have run successfully (not raised an exception, completed end-to-end) within the last 90 minutes. This checks job health, not data freshness. A station with no amendments will routinely have its most recent TAF be older than 90 minutes; that is normal and not a health issue.

The forecast table unification question is resolved by the cadence-matched convergence design — the API response shape already uses a `forecast_source` wrapper field, so v1's NWS gridpoint additions slot in without breaking the v0 contract.

All open questions are resolved. The roadmap is ready for handoff to Claude Code.
