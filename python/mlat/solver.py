"""MLAT solving utilities (scipy LM and PyTorch Adam variants)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np
import torch
from scipy.optimize import least_squares

from .coordinates import compute_gdop, ecef_to_geodetic, geodetic_to_ecef
from .models import MLATGroup, PositionFix

C = 299_792_458.0
MAX_GDOP = 15.0
MIN_ALT_M = -500.0
MAX_ALT_M = 45_000.0
MIN_LAT = 45.0
MAX_LAT = 62.0
MIN_LON = -15.0
MAX_LON = 5.0

logger = logging.getLogger(__name__)


def solve_mlat_scipy(group: MLATGroup, initial_guess_ecef: np.ndarray) -> Optional[PositionFix]:
    """Solve MLAT position using scipy Levenberg-Marquardt least squares."""
    sensors, tdoa = _extract_sensor_and_tdoa(group)
    if sensors is None or tdoa is None:
        return None

    initial = np.asarray(initial_guess_ecef, dtype=float).reshape(3)
    initial_residual = _rmse(_tdoa_residuals(initial, sensors, tdoa))

    try:
        result = least_squares(
            _tdoa_residuals,
            x0=initial,
            method="lm",
            args=(sensors, tdoa),
        )
    except Exception as exc:
        _log_failure("scipy_exception", group, len(sensors), initial_residual, extra=str(exc))
        return None

    if not result.success:
        _log_failure("scipy_no_convergence", group, len(sensors), initial_residual, extra=result.message)
        return None

    candidate = np.asarray(result.x, dtype=float)
    validated = _validate_solution(candidate, sensors)
    if validated is None:
        _log_failure("scipy_validation_failed", group, len(sensors), initial_residual)
        return None

    lat, lon, alt_m, gdop = validated
    return _build_fix(group, lat, lon, alt_m, gdop, len(sensors))


def solve_mlat_torch(group: MLATGroup, initial_guess_ecef: np.ndarray, n_iters: int = 300) -> Optional[PositionFix]:
    """Solve MLAT position using a differentiable PyTorch optimizer."""
    sensors, tdoa = _extract_sensor_and_tdoa(group)
    if sensors is None or tdoa is None:
        return None

    initial = np.asarray(initial_guess_ecef, dtype=float).reshape(3)
    initial_residual = _rmse(_tdoa_residuals(initial, sensors, tdoa))

    sensors_t = torch.tensor(sensors, dtype=torch.float64)
    tdoa_t = torch.tensor(tdoa, dtype=torch.float64)

    pos = torch.tensor(initial, dtype=torch.float64, requires_grad=True)
    optimizer = torch.optim.Adam([pos], lr=1.0)

    try:
        for _ in range(n_iters):
            optimizer.zero_grad()
            deltas = pos.unsqueeze(0) - sensors_t
            distances = torch.linalg.norm(deltas, dim=1)
            residuals = (distances[1:] - distances[0]) / C - tdoa_t
            loss = torch.mean(residuals * residuals)
            loss.backward()
            optimizer.step()
    except Exception as exc:
        _log_failure("torch_exception", group, len(sensors), initial_residual, extra=str(exc))
        return None

    candidate = pos.detach().cpu().numpy()
    validated = _validate_solution(candidate, sensors)
    if validated is None:
        _log_failure("torch_validation_failed", group, len(sensors), initial_residual)
        return None

    lat, lon, alt_m, gdop = validated
    return _build_fix(group, lat, lon, alt_m, gdop, len(sensors))


def _extract_sensor_and_tdoa(group: MLATGroup) -> tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    sensor_ecef = group.sensor_ecef
    if not sensor_ecef and group.observations:
        sensor_ecef = [
            tuple(geodetic_to_ecef(obs.lat, obs.lon, obs.alt_m).tolist())
            for obs in group.observations
        ]

    if len(sensor_ecef) < 4:
        _log_failure("insufficient_sensors", group, len(sensor_ecef), float("inf"))
        return None, None

    sensors = np.asarray(sensor_ecef, dtype=float)

    if group.tdoa_seconds:
        tdoa = np.asarray(group.tdoa_seconds, dtype=float)
    elif group.observations and len(group.observations) == len(sensor_ecef):
        ordered_obs = sorted(group.observations, key=lambda item: item.total_nanos)
        ref_nanos = ordered_obs[0].total_nanos
        tdoa = np.asarray(
            [(obs.total_nanos - ref_nanos) / 1_000_000_000.0 for obs in ordered_obs[1:]],
            dtype=float,
        )
    else:
        _log_failure("missing_tdoa", group, len(sensor_ecef), float("inf"))
        return None, None

    if len(tdoa) != len(sensor_ecef) - 1:
        _log_failure("tdoa_size_mismatch", group, len(sensor_ecef), float("inf"))
        return None, None

    return sensors, tdoa


def _tdoa_residuals(position_ecef: np.ndarray, sensors: np.ndarray, tdoa: np.ndarray) -> np.ndarray:
    deltas = position_ecef.reshape(1, 3) - sensors
    distances = np.linalg.norm(deltas, axis=1)
    reference_distance = distances[0]

    modeled_tdoa = (distances[1:] - reference_distance) / C
    return modeled_tdoa - tdoa


def _validate_solution(position_ecef: np.ndarray, sensors: np.ndarray) -> Optional[tuple[float, float, float, float]]:
    lat, lon, alt_m = ecef_to_geodetic(*position_ecef.tolist())

    if not (MIN_ALT_M <= alt_m <= MAX_ALT_M):
        return None
    if not (MIN_LAT <= lat <= MAX_LAT and MIN_LON <= lon <= MAX_LON):
        return None

    gdop = compute_gdop(position_ecef, [row for row in sensors])
    if not np.isfinite(gdop) or gdop >= MAX_GDOP:
        return None

    return lat, lon, alt_m, float(gdop)


def _build_fix(group: MLATGroup, lat: float, lon: float, alt_m: float, gdop: float, sensor_count: int) -> PositionFix:
    timestamp_utc = _timestamp_from_group(group)
    icao = group.icao or "unknown"

    return PositionFix(
        icao=icao,
        lat=lat,
        lon=lon,
        alt_m=alt_m,
        alt_ft=alt_m / 0.3048,
        method="MLAT",
        gdop=gdop,
        sensor_count=sensor_count,
        timestamp_utc=timestamp_utc,
        callsign=None,
    )


def _timestamp_from_group(group: MLATGroup) -> str:
    if group.observations:
        total_nanos = min(obs.total_nanos for obs in group.observations)
        now_utc = datetime.now(timezone.utc)
        midnight = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        ts = midnight + timedelta(seconds=total_nanos / 1_000_000_000.0)
        return ts.isoformat().replace("+00:00", "Z")

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _rmse(values: np.ndarray) -> float:
    if values.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(values * values)))


def _log_failure(reason: str, group: MLATGroup, sensor_count: int, initial_residual: float, extra: str = "") -> None:
    icao = group.icao or "unknown"
    message = (
        f"MLAT solve failure reason={reason} icao={icao} sensors={sensor_count} "
        f"initial_residual={initial_residual:.6e}"
    )
    if extra:
        message = f"{message} detail={extra}"
    logger.warning(message)
