"""Coordinate utilities for ECEF/geodetic conversions and geometry quality metrics."""

from __future__ import annotations

import math

import numpy as np

WGS84_A = 6_378_137.0
WGS84_E2 = 0.00669437999014
WGS84_B = WGS84_A * math.sqrt(1.0 - WGS84_E2)


def geodetic_to_ecef(lat_deg: float, lon_deg: float, alt_m: float) -> np.ndarray:
    """Convert geodetic coordinates (degrees/meters) to ECEF XYZ meters."""
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)

    sin_lat = math.sin(lat)
    cos_lat = math.cos(lat)
    sin_lon = math.sin(lon)
    cos_lon = math.cos(lon)

    n = WGS84_A / math.sqrt(1.0 - WGS84_E2 * sin_lat * sin_lat)

    x = (n + alt_m) * cos_lat * cos_lon
    y = (n + alt_m) * cos_lat * sin_lon
    z = (n * (1.0 - WGS84_E2) + alt_m) * sin_lat

    return np.array([x, y, z], dtype=float)


def ecef_to_geodetic(x: float, y: float, z: float) -> tuple[float, float, float]:
    """Convert ECEF XYZ meters to geodetic (lat_deg, lon_deg, alt_m) using Bowring iterations."""
    p = math.hypot(x, y)

    if p < 1e-12:
        lat = math.copysign(math.pi / 2.0, z) if z != 0.0 else 0.0
        lon = 0.0
        alt = abs(z) - WGS84_B
        return math.degrees(lat), math.degrees(lon), alt

    lon = math.atan2(y, x)
    lat = math.atan2(z, p * (1.0 - WGS84_E2))
    alt = 0.0

    for _ in range(5):
        sin_lat = math.sin(lat)
        cos_lat = math.cos(lat)
        n = WGS84_A / math.sqrt(1.0 - WGS84_E2 * sin_lat * sin_lat)

        if abs(cos_lat) < 1e-12:
            alt = z / sin_lat - n * (1.0 - WGS84_E2)
        else:
            alt = p / cos_lat - n

        lat = math.atan2(z, p * (1.0 - (WGS84_E2 * n) / (n + alt)))

    sin_lat = math.sin(lat)
    cos_lat = math.cos(lat)
    n = WGS84_A / math.sqrt(1.0 - WGS84_E2 * sin_lat * sin_lat)

    if abs(cos_lat) < 1e-12:
        alt = z / sin_lat - n * (1.0 - WGS84_E2)
    else:
        alt = p / cos_lat - n

    return math.degrees(lat), math.degrees(lon), alt


def compute_gdop(aircraft_ecef: np.ndarray, sensor_ecef_list: list[np.ndarray]) -> float:
    """Compute GDOP for an aircraft ECEF position and a set of sensor ECEF positions."""
    if len(sensor_ecef_list) < 4:
        return float("inf")

    aircraft = np.asarray(aircraft_ecef, dtype=float).reshape(3)

    rows: list[list[float]] = []
    for sensor in sensor_ecef_list:
        sensor_xyz = np.asarray(sensor, dtype=float).reshape(3)
        delta = aircraft - sensor_xyz
        distance = float(np.linalg.norm(delta))

        if distance <= 0.0:
            return float("inf")

        rows.append([
            float(delta[0] / distance),
            float(delta[1] / distance),
            float(delta[2] / distance),
            1.0,
        ])

    h = np.asarray(rows, dtype=float)

    try:
        q = np.linalg.inv(h.T @ h)
    except np.linalg.LinAlgError:
        return float("inf")

    gdop_squared = float(np.trace(q))
    if gdop_squared < 0.0 or not math.isfinite(gdop_squared):
        return float("inf")

    return math.sqrt(gdop_squared)
