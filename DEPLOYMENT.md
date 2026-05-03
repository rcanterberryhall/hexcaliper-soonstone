# Soonstone — Deployment

Self-hosted forecast verification service. Deployed via Docker Compose, exposed at `weather.hexcaliper.com` through the existing Cloudflare Tunnel.

## Prerequisites

- Docker + `docker compose` plugin
- An existing Cloudflare Tunnel container running on a Docker network named `cloudflare-tunnel` (shared with the other Hexcaliper services)
- Outbound HTTPS to `aviationweather.gov` (no inbound ports needed; Cloudflare Tunnel handles ingress)

## First deploy

```bash
git clone https://github.com/rcanterberryhall/hexcaliper-soonstone.git /home/lobulus/GitHub/hexcaliper-soonstone
cd /home/lobulus/GitHub/hexcaliper-soonstone
./install.sh
```

The container will:
1. Apply Alembic migrations against `./data/soonstone.db` (creating the file on first run)
2. Start the Flask app on internal port 5055
3. Start the APScheduler background jobs (`refresh_stations` weekly Mondays 03:00 UTC, `ingest_metars` at :25/:55, `ingest_tafs` at :00/:30, `prune_old` daily 04:00 UTC)

## Cloudflare Tunnel route

Add the following ingress rule to your existing tunnel config (`~/.cloudflared/config.yml` or the Cloudflare dashboard):

```yaml
ingress:
  - hostname: weather.hexcaliper.com
    service: http://soonstone:5055
  # ... your existing rules
  - service: http_status:404
```

Restart the cloudflared container after the change. DNS is managed in the Cloudflare dashboard — `CNAME weather` pointing at the tunnel.

## First-cycle verification

The `/health` endpoint returns 503 until the first `ingest_metars` AND `ingest_tafs` runs both succeed. To skip the wait until the next :25 / :30 mark:

```bash
docker exec soonstone python -m soonstone --run-once refresh_stations
docker exec soonstone python -m soonstone --run-once ingest_metars
docker exec soonstone python -m soonstone --run-once ingest_tafs
curl -s https://weather.hexcaliper.com/health | python3 -m json.tool
```

Then open `https://weather.hexcaliper.com/` in a browser; click any Florida station marker; the three-section popup should populate.

## Updates

```bash
cd /home/lobulus/GitHub/hexcaliper-soonstone
git pull
./install.sh
```

`install.sh` is idempotent. Migrations apply on container start.

## Backups

Nightly file-level backup of `./data/soonstone.db`:

```bash
docker exec soonstone sqlite3 /data/soonstone.db ".backup '/data/backups/soonstone-$(date +%Y%m%d).db'"
```

Plain `cp` while WAL is active is **not** safe; always use `.backup`.

When the database crosses ~1GB, switch to Litestream for continuous replication. See `soonstone_roadmap.md` Operational Notes / Database backups (v1.5+).

## Troubleshooting

- **`/health` stays 503**: check `docker logs soonstone` for `metar_parse_failed` or `taf_parse_failed` lines, or for upstream HTTP errors against aviationweather.gov.
- **Map renders but markers are gray**: `/api/stations` is returning before any METARs have been ingested. Run `docker exec soonstone python -m soonstone --run-once ingest_metars`.
- **Container restarts in a loop**: usually a migration error. `docker compose run --rm soonstone alembic upgrade head` to see the underlying error.
- **Cloudflare returns 502 / no upstream**: the soonstone container isn't on the `cloudflare-tunnel` network. Check `docker network inspect cloudflare-tunnel`; it should list `soonstone` among its containers.
