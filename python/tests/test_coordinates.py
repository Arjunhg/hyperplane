import math

import numpy as np

from mlat.coordinates import (
    WGS84_A,
    WGS84_B,
    compute_gdop,
    ecef_to_geodetic,
    geodetic_to_ecef,
)


def test_geodetic_to_ecef_known_points() -> None:
    ecef_origin = geodetic_to_ecef(0.0, 0.0, 0.0)
    assert np.allclose(ecef_origin, np.array([WGS84_A, 0.0, 0.0]), atol=1e-6)

    ecef_quadrant = geodetic_to_ecef(0.0, 90.0, 0.0)
    assert np.allclose(ecef_quadrant, np.array([0.0, WGS84_A, 0.0]), atol=1e-6)

    ecef_north_pole = geodetic_to_ecef(90.0, 0.0, 0.0)
    assert np.allclose(ecef_north_pole, np.array([0.0, 0.0, WGS84_B]), atol=1e-6)


def test_ecef_round_trip_sub_millimeter() -> None:
    # Includes one known network location from location-override.json.
    points = [
        (50.12993, -5.5137, 56.3),
        (50.399944, -4.183016, 136.5),
        (49.94662, -6.33149, 55.5),
    ]

    for lat, lon, alt in points:
        start = geodetic_to_ecef(lat, lon, alt)
        lat2, lon2, alt2 = ecef_to_geodetic(*start)
        end = geodetic_to_ecef(lat2, lon2, alt2)

        error_m = float(np.linalg.norm(start - end))
        assert error_m < 1e-3


def test_compute_gdop_valid_and_singular_geometry() -> None:
    aircraft = geodetic_to_ecef(50.1, -5.6, 10_000.0)

    sensors_valid = [
        geodetic_to_ecef(50.12993, -5.5137, 56.3),
        geodetic_to_ecef(50.09916, -5.55674, 153.8),
        geodetic_to_ecef(50.20572, -5.49844, 168.8),
        geodetic_to_ecef(49.94662, -6.33149, 55.5),
    ]
    gdop = compute_gdop(aircraft, sensors_valid)
    assert math.isfinite(gdop)
    assert gdop > 0.0

    sensors_singular = [
        np.array([0.0, 0.0, 0.0]),
        np.array([1.0, 0.0, 0.0]),
        np.array([2.0, 0.0, 0.0]),
        np.array([3.0, 0.0, 0.0]),
    ]
    assert compute_gdop(np.array([1000.0, 1000.0, 1000.0]), sensors_singular) == float("inf")
