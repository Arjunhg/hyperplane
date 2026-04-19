from datetime import datetime, timezone

import numpy as np

from mlat.models import PositionFix
from mlat.tracker import AircraftTracker


def _fix(icao: str, lat: float, lon: float, alt_m: float, ts: str = "2026-04-19T00:00:00Z") -> PositionFix:
    return PositionFix(
        icao=icao,
        lat=lat,
        lon=lon,
        alt_m=alt_m,
        alt_ft=alt_m / 0.3048,
        method="MLAT",
        gdop=2.0,
        sensor_count=4,
        timestamp_utc=ts,
        callsign=None,
    )


def test_tracker_update_and_initial_guess() -> None:
    tracker = AircraftTracker()

    first = _fix("abc123", 50.12, -5.55, 10_000.0)
    tracker.update(first)

    guess = tracker.get_initial_guess("abc123")
    assert isinstance(guess, np.ndarray)
    assert guess.shape == (3,)


def test_tracker_returns_smoothed_position() -> None:
    tracker = AircraftTracker()

    tracker.update(_fix("abc123", 50.12, -5.55, 10_000.0))
    tracker.update(_fix("abc123", 50.121, -5.551, 10_010.0))

    smoothed = tracker.get_smoothed_position("abc123")
    assert smoothed is not None
    assert smoothed.icao == "abc123"


def test_tracker_history_and_inactive_purge() -> None:
    tracker = AircraftTracker(history_size=3, inactive_timeout_s=60.0)

    tracker.update(_fix("abc123", 50.10, -5.50, 10000.0))
    tracker.update(_fix("abc123", 50.11, -5.51, 10010.0))
    tracker.update(_fix("abc123", 50.12, -5.52, 10020.0))
    tracker.update(_fix("abc123", 50.13, -5.53, 10030.0))

    assert len(tracker.states["abc123"].history) == 3

    tracker.states["abc123"].last_update_monotonic -= 120.0
    _ = tracker.get_initial_guess("unknown-icao")
    assert "abc123" not in tracker.states
