"""Entry point for ``python -m mlat.pipeline`` / ``python -m mlat``."""

from __future__ import annotations

import json
import logging
import sys

from .models import PositionFix, MLATGroup
from .pipeline import Pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    stream=sys.stderr,
)

logger = logging.getLogger("mlat")


def _print_fix(fix: PositionFix) -> None:
    """Print every PositionFix as JSON to stdout."""
    obj = {
        "type": "PositionFix",
        "icao": fix.icao,
        "lat": fix.lat,
        "lon": fix.lon,
        "alt_m": fix.alt_m,
        "alt_ft": fix.alt_ft,
        "method": fix.method,
        "gdop": fix.gdop,
        "sensor_count": fix.sensor_count,
        "timestamp_utc": fix.timestamp_utc,
        "callsign": fix.callsign,
    }
    print(json.dumps(obj), flush=True)
    logger.info(
        "Position Fix  %-6s  method=%-4s  lat=%+10.5f  lon=%+10.5f  alt_m=%.0f",
        fix.icao.upper(),
        fix.method,
        fix.lat,
        fix.lon,
        fix.alt_m,
    )


def _print_mlat_group(group: MLATGroup) -> None:
    """Log MLAT correlation groups to stderr."""
    logger.info(
        "MLAT Group    hex_key=%s  sensors=%d  Δt_max=%.3f ms",
        group.hex,
        len(group.observations),
        (group.observations[-1].total_nanos - group.observations[0].total_nanos) / 1e6,
    )


def main() -> None:
    logger.info("Pipeline starting — reading from stdin …")

    pipeline = Pipeline(
        source="stdin",
        fix_callback=_print_fix,
        mlat_group_callback=_print_mlat_group,
    )

    try:
        pipeline.run()
    except KeyboardInterrupt:
        pass

    logger.info(
        "Pipeline finished — %d fixes, %d MLAT groups emitted.",
        len(pipeline.emitted_fixes),
        len(pipeline.emitted_mlat_groups),
    )


if __name__ == "__main__":
    main()
