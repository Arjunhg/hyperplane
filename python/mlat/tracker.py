"""Per-aircraft tracking state and Kalman-smoothed position helpers."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
from filterpy.kalman import KalmanFilter

from .coordinates import ecef_to_geodetic, geodetic_to_ecef
from .kalman import create_aircraft_kalman_filter, predict_and_update
from .models import PositionFix


@dataclass
class AircraftState:
    """Mutable tracking state for a single ICAO address."""

    latest_fix: Optional[PositionFix] = None
    latest_velocity: Optional[dict[str, float]] = None
    callsign: Optional[str] = None
    cpr_buffer_ref: Optional[Any] = None
    kalman_filter: Optional[KalmanFilter] = None
    history: deque[PositionFix] = field(default_factory=lambda: deque(maxlen=30))
    last_update_monotonic: float = field(default_factory=time.monotonic)


class AircraftTracker:
    """Tracks aircraft state and provides initial guesses / smoothed fixes."""

    def __init__(
        self,
        history_size: int = 30,
        inactive_timeout_s: float = 60.0,
        centroid_lat: float = 50.1,
        centroid_lon: float = -5.6,
        centroid_alt_m: float = 10_000.0,
    ) -> None:
        self._history_size = history_size
        self._inactive_timeout_s = inactive_timeout_s
        self._states: dict[str, AircraftState] = {}

        self._centroid_lat = centroid_lat
        self._centroid_lon = centroid_lon
        self._centroid_alt_m = centroid_alt_m
        self._centroid_ecef = geodetic_to_ecef(centroid_lat, centroid_lon, centroid_alt_m)

    @property
    def states(self) -> dict[str, AircraftState]:
        """Expose tracking states for diagnostics/tests."""
        self._purge_inactive()
        return self._states

    def update(self, fix: PositionFix) -> None:
        """Update aircraft state and feed the Kalman filter."""
        self._purge_inactive()

        icao = fix.icao.lower()
        now = time.monotonic()

        state = self._states.get(icao)
        if state is None:
            state = AircraftState(history=deque(maxlen=self._history_size))
            self._states[icao] = state

        measurement_ecef = geodetic_to_ecef(fix.lat, fix.lon, fix.alt_m)

        if state.kalman_filter is None:
            state.kalman_filter = create_aircraft_kalman_filter(measurement_ecef)
        else:
            dt = max(now - state.last_update_monotonic, 1e-3)
            predict_and_update(state.kalman_filter, measurement_ecef, dt)

        state.latest_fix = fix
        if fix.callsign:
            state.callsign = fix.callsign
        state.history.append(fix)
        state.last_update_monotonic = now

    def get_initial_guess(self, icao: str) -> np.ndarray:
        """Return initial ECEF guess: latest fix if known, else network centroid."""
        self._purge_inactive()

        state = self._states.get(icao.lower())
        if state is not None and state.latest_fix is not None:
            fix = state.latest_fix
            return geodetic_to_ecef(fix.lat, fix.lon, fix.alt_m)

        return self._centroid_ecef.copy()

    def get_reference(self, icao: str, fallback_lat: float, fallback_lon: float) -> tuple[float, float]:
        """Return reference lat/lon for CPR decoding compatibility."""
        self._purge_inactive()

        state = self._states.get(icao.lower())
        if state is None or state.latest_fix is None:
            return fallback_lat, fallback_lon

        return state.latest_fix.lat, state.latest_fix.lon

    def get_smoothed_position(self, icao: str) -> Optional[PositionFix]:
        """Return the latest Kalman-smoothed position for ICAO, if available."""
        self._purge_inactive()

        state = self._states.get(icao.lower())
        if state is None or state.kalman_filter is None or state.latest_fix is None:
            return None

        ecef = np.asarray(state.kalman_filter.x[:3]).reshape(3)
        lat, lon, alt_m = ecef_to_geodetic(float(ecef[0]), float(ecef[1]), float(ecef[2]))

        latest = state.latest_fix
        return PositionFix(
            icao=latest.icao,
            lat=lat,
            lon=lon,
            alt_m=alt_m,
            alt_ft=alt_m / 0.3048,
            method=latest.method,
            gdop=latest.gdop,
            sensor_count=latest.sensor_count,
            timestamp_utc=latest.timestamp_utc,
            callsign=state.callsign,
        )

    def set_velocity(self, icao: str, velocity: dict[str, float]) -> None:
        """Store latest velocity metadata for an ICAO."""
        self._purge_inactive()

        key = icao.lower()
        state = self._states.get(key)
        if state is None:
            state = AircraftState(history=deque(maxlen=self._history_size))
            self._states[key] = state

        state.latest_velocity = velocity
        state.last_update_monotonic = time.monotonic()

    def set_callsign(self, icao: str, callsign: str) -> None:
        """Store latest callsign metadata for an ICAO."""
        self._purge_inactive()

        key = icao.lower()
        state = self._states.get(key)
        if state is None:
            state = AircraftState(history=deque(maxlen=self._history_size))
            self._states[key] = state

        state.callsign = callsign
        state.last_update_monotonic = time.monotonic()

    def set_cpr_buffer_ref(self, icao: str, cpr_buffer_ref: Any) -> None:
        """Store a reference to CPR buffer state for this ICAO."""
        self._purge_inactive()

        key = icao.lower()
        state = self._states.get(key)
        if state is None:
            state = AircraftState(history=deque(maxlen=self._history_size))
            self._states[key] = state

        state.cpr_buffer_ref = cpr_buffer_ref
        state.last_update_monotonic = time.monotonic()

    def _purge_inactive(self) -> None:
        now = time.monotonic()
        stale = [icao for icao, state in self._states.items() if now - state.last_update_monotonic > self._inactive_timeout_s]
        for icao in stale:
            self._states.pop(icao, None)
