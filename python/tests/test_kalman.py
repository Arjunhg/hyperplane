import numpy as np

from mlat.kalman import create_aircraft_kalman_filter, predict_and_update


def test_kalman_output_is_smoother_than_raw_measurements() -> None:
    rng = np.random.default_rng(7)

    n_steps = 120
    dt = 1.0
    start = np.array([1_000_000.0, -4_000_000.0, 4_000_000.0], dtype=float)
    velocity = np.array([180.0, 120.0, -3.0], dtype=float)

    truth = np.array([start + i * dt * velocity for i in range(n_steps)], dtype=float)
    noisy = truth + rng.normal(loc=0.0, scale=200.0, size=truth.shape)

    kf = create_aircraft_kalman_filter(noisy[0])
    smoothed = [noisy[0]]
    for i in range(1, n_steps):
        smoothed.append(predict_and_update(kf, noisy[i], dt=dt))
    smoothed_arr = np.asarray(smoothed, dtype=float)

    raw_error = noisy - truth
    smoothed_error = smoothed_arr - truth

    raw_variance = float(np.var(raw_error))
    smoothed_variance = float(np.var(smoothed_error))

    assert smoothed_variance < raw_variance
