"""Correlation buffer for grouping same-pulse observations for MLAT."""

from __future__ import annotations

import time
from typing import Optional

from .coordinates import geodetic_to_ecef
from .models import MLATGroup, Observation
from .router import extract_icao

TIME_WINDOW_NS = 2_000_000_000
CLEANUP_INTERVAL_S = 5.0


class CorrelationBuffer:
    """Groups observations of the same hex payload into MLAT-ready sets."""

    def __init__(self, min_sensors: int = 4, time_window_ns: int = TIME_WINDOW_NS) -> None:
        self.min_sensors = min_sensors
        self.time_window_ns = time_window_ns
        self._groups: dict[str, list[Observation]] = {}
        self._last_cleanup_monotonic = time.monotonic()

    def add(self, obs: Observation) -> Optional[MLATGroup]:
        """Add an observation and return a completed MLAT group when ready."""
        now = time.monotonic()
        if now - self._last_cleanup_monotonic >= CLEANUP_INTERVAL_S:
            self._purge_old_groups(obs.total_nanos)
            self._last_cleanup_monotonic = now

        group = self._groups.setdefault(obs.hex, [])

        # Deduplicate by sensor ID + payload, keeping the earliest timestamp.
        for idx, existing in enumerate(group):
            if existing.sensor_id == obs.sensor_id and existing.hex == obs.hex:
                if obs.total_nanos < existing.total_nanos:
                    group[idx] = obs
                return None

        if group:
            earliest = min(item.total_nanos for item in group)
            if abs(obs.total_nanos - earliest) > self.time_window_ns:
                # Reject this late/out-of-window observation for this group.
                return None

        group.append(obs)

        unique_sensor_count = len({item.sensor_id for item in group})
        if unique_sensor_count < self.min_sensors:
            return None

        ordered = sorted(group, key=lambda item: item.total_nanos)
        reference = ordered[0]

        sensor_ecef = [
            tuple(geodetic_to_ecef(item.lat, item.lon, item.alt_m).tolist())
            for item in ordered
        ]
        tdoa_seconds = [
            (item.total_nanos - reference.total_nanos) / 1_000_000_000.0
            for item in ordered[1:]
        ]

        icao: Optional[str] = None
        for item in ordered:
            maybe_icao = extract_icao(item.hex, item.df)
            if maybe_icao is not None:
                icao = maybe_icao
                break

        completed = MLATGroup(
            hex=obs.hex,
            icao=icao,
            observations=ordered,
            reference_sensor=reference.sensor_id,
            sensor_ecef=sensor_ecef,
            tdoa_seconds=tdoa_seconds,
        )

        del self._groups[obs.hex]
        return completed

    def _purge_old_groups(self, current_total_nanos: int) -> None:
        """Purge stale groups older than 2x window relative to current observation time."""
        max_age_ns = 2 * self.time_window_ns
        stale_keys: list[str] = []

        for payload_hex, observations in self._groups.items():
            if not observations:
                stale_keys.append(payload_hex)
                continue

            earliest = min(item.total_nanos for item in observations)
            if current_total_nanos - earliest > max_age_ns:
                stale_keys.append(payload_hex)

        for key in stale_keys:
            self._groups.pop(key, None)
