"""CLI entrypoint for soonstone.

Usage:
    python -m soonstone --run-once <job_name>      # single run, then exit
    python -m soonstone --serve                    # scheduler + Flask, block

job_name is one of: refresh_stations, ingest_metars, ingest_tafs, prune_old
"""
from __future__ import annotations

import argparse
import sys

from soonstone.app import create_app
from soonstone.scheduler import build_scheduler, first_scan, run_once


def _serve(app) -> None:
    """Start scheduler in background thread, then block in Flask serving HTTP."""
    scheduler = build_scheduler(app)
    scheduler.start()
    first_scan(scheduler)
    try:
        app.run(host="0.0.0.0", port=5055, use_reloader=False, threaded=True)
    finally:
        scheduler.shutdown(wait=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="soonstone")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run-once", metavar="JOB", help="run one job and exit")
    group.add_argument("--serve", action="store_true", help="scheduler + Flask, block")
    args = parser.parse_args(argv)

    app = create_app()

    if args.run_once:
        run_once(args.run_once, app)
        return 0

    if args.serve:
        _serve(app)
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
