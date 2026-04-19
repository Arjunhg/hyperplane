import numpy as np

from mlat.coordinates import geodetic_to_ecef
from mlat.models import MLATGroup, Observation
from mlat.solver import C, solve_mlat_scipy, solve_mlat_torch


def _build_synthetic_group(noise_seconds: float = 0.0) -> tuple[MLATGroup, np.ndarray]:
    # Wide synthetic geometry tuned to produce good GDOP for validation checks.
    sensors_geo = [
        (51.29520572383609, -3.5320485551471075, 65.87051748336592),
        (49.986230018009564, -6.008220395041, 187.7747823717957),
        (51.45834908695481, -7.153250847931178, 156.56802546893047),
        (48.45573448859335, -4.292462469274592, 123.70626824778266),
        (45.58936747048745, -9.724159597297731, 26.25302528410225),
        (45.14969765902795, -1.0685113163026223, 90.5016814406155),
    ]

    true_lat, true_lon, true_alt = 50.0, -6.0, 10_000.0
    true_ecef = geodetic_to_ecef(true_lat, true_lon, true_alt)

    sensor_ecef = np.array([geodetic_to_ecef(lat, lon, alt) for (lat, lon, alt) in sensors_geo], dtype=float)
    distances = np.linalg.norm(sensor_ecef - true_ecef.reshape(1, 3), axis=1)

    ref_idx = int(np.argmin(distances))
    order = [ref_idx] + [idx for idx in range(len(sensors_geo)) if idx != ref_idx]

    ordered_geo = [sensors_geo[idx] for idx in order]
    ordered_ecef = sensor_ecef[order]
    ordered_dist = distances[order]

    tdoa = (ordered_dist[1:] - ordered_dist[0]) / C
    if noise_seconds > 0.0:
        rng = np.random.default_rng(42)
        tdoa = tdoa + rng.uniform(-noise_seconds, noise_seconds, size=tdoa.shape)

    base_nanos = 10_000_000_000_000
    observations: list[Observation] = []
    for i, (geo, delay_s) in enumerate(zip(ordered_geo, np.concatenate(([0.0], tdoa))), start=1):
        lat, lon, alt = geo
        observations.append(
            Observation(
                sensor_id=i,
                sensor_pk="",
                lat=lat,
                lon=lon,
                alt_m=alt,
                total_nanos=base_nanos + int(round(delay_s * 1_000_000_000.0)),
                hex="20000000000000",
                df=4,
                hex_key="20000000000000",
            )
        )

    group = MLATGroup(
        hex="20000000000000",
        icao="abc123",
        observations=observations,
        reference_sensor=observations[0].sensor_id,
        sensor_ecef=[tuple(vec.tolist()) for vec in ordered_ecef],
        tdoa_seconds=tdoa.tolist(),
    )

    return group, true_ecef


def test_solver_exact_geometry_recovers_position_and_torch_agrees() -> None:
    group, truth_ecef = _build_synthetic_group(noise_seconds=0.0)
    initial_guess = truth_ecef.copy()

    fix_scipy = solve_mlat_scipy(group, initial_guess)
    assert fix_scipy is not None

    scipy_ecef = geodetic_to_ecef(fix_scipy.lat, fix_scipy.lon, fix_scipy.alt_m)
    scipy_error = float(np.linalg.norm(scipy_ecef - truth_ecef))
    assert scipy_error < 100.0

    fix_torch = solve_mlat_torch(group, initial_guess, n_iters=400)
    assert fix_torch is not None

    torch_ecef = geodetic_to_ecef(fix_torch.lat, fix_torch.lon, fix_torch.alt_m)
    solver_gap = float(np.linalg.norm(torch_ecef - scipy_ecef))
    assert solver_gap < 500.0


def test_solver_with_microsecond_noise_stays_within_500m() -> None:
    group, truth_ecef = _build_synthetic_group(noise_seconds=1e-6)
    initial_guess = truth_ecef.copy()

    fix = solve_mlat_scipy(group, initial_guess)
    assert fix is not None

    solved_ecef = geodetic_to_ecef(fix.lat, fix.lon, fix.alt_m)
    error = float(np.linalg.norm(solved_ecef - truth_ecef))
    assert error < 500.0

