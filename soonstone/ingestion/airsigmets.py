"""ingest_airsigmets: fetch AWC's AIRMET/SIGMET FeatureCollection and cache to disk.

Stored as plain JSON at {radar_dir}/../airsigmets/current.json (same /data
volume as everything else). The /api/airsigmets endpoint serves this file
directly, with a 5-min Cache-Control. No DB schema -- AIRMETs/SIGMETs are
fully replaceable on each ingest, no historical accumulation needed for v1.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from soonstone.config import Config
from soonstone.ingestion.awc_client import AwcClient
from soonstone.ingestion.results import AirsigmetsResult

log = logging.getLogger(__name__)


def _target_path(config: Config) -> Path:
    return Path(config.radar_dir).parent / "airsigmets" / "current.json"


def ingest_airsigmets(awc_client: AwcClient, config: Config) -> AirsigmetsResult:
    fc = awc_client.fetch_airsigmets()
    if not isinstance(fc, dict) or "features" not in fc:
        log.warning(
            "airsigmet_unexpected_shape",
            extra={"job": "ingest_airsigmets", "type": str(type(fc))},
        )
        fc = {"type": "FeatureCollection", "features": []}

    target = _target_path(config)
    target.parent.mkdir(parents=True, exist_ok=True)

    # Write atomically via temp + rename so a partial write never serves.
    tmp = target.with_suffix(".json.tmp")
    body = json.dumps(fc)
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, target)

    return AirsigmetsResult(
        features_count=len(fc.get("features") or []),
        bytes_written=len(body),
    )
