"""Kalman filtering helpers for aircraft ECEF position smoothing."""

from __future__ import annotations

import numpy as np
from filterpy.kalman import KalmanFilter


def create_aircraft_kalman_filter(
    initial_ecef: np.ndarray,
    dt: float = 1.0,
    measurement_noise: float = 40_000.0,
    process_noise: float = 0.1,
) -> KalmanFilter:
    """Create a 6D constant-velocity Kalman filter in ECEF coordinates."""
    kf = KalmanFilter(dim_x=6, dim_z=3)

    initial = np.asarray(initial_ecef, dtype=float).reshape(3)

    kf.x = np.zeros((6, 1), dtype=float)
    kf.x[0:3, 0] = initial

    kf.F = np.eye(6, dtype=float)
    kf.F[0, 3] = dt
    kf.F[1, 4] = dt
    kf.F[2, 5] = dt

    kf.H = np.zeros((3, 6), dtype=float)
    kf.H[0, 0] = 1.0
    kf.H[1, 1] = 1.0
    kf.H[2, 2] = 1.0

    kf.P *= 1_000_000.0
    kf.R = np.eye(3, dtype=float) * measurement_noise
    kf.Q = np.eye(6, dtype=float) * process_noise

    return kf


def predict_and_update(kf: KalmanFilter, new_ecef: np.ndarray, dt: float) -> np.ndarray:
    """Run one predict/update cycle and return the smoothed ECEF position."""
    effective_dt = max(float(dt), 1e-3)
    kf.F[0, 3] = effective_dt
    kf.F[1, 4] = effective_dt
    kf.F[2, 5] = effective_dt

    kf.predict()

    measurement = np.asarray(new_ecef, dtype=float).reshape(3, 1)
    kf.update(measurement)

    return np.asarray(kf.x[:3]).reshape(3)
