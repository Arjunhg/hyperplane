"""Quick script to extract concrete metric numbers for resume."""

import numpy as np
import torch
from mlat.predictor import AircraftTrajectoryPredictor
from mlat.anomaly import TDOAAutoencoder
from mlat.coordinates import geodetic_to_ecef
from mlat.models import MLATGroup, Observation
from mlat.solver import C, solve_mlat_scipy, solve_mlat_torch


# ── 1. LSTM RMSE ──────────────────────────────────────────────────────────────
def lstm_metrics():
    torch.manual_seed(7)
    np.random.seed(7)

    n = 140
    t = np.linspace(0.0, 4.0 * np.pi, n)
    radius = 1_000.0
    x = 1_000_000.0 + radius * np.cos(t)
    y = -2_000_000.0 + radius * np.sin(t)
    z = 10_000.0 + 50.0 * np.sin(0.5 * t)
    trajectory = [np.array([x[i], y[i], z[i]], dtype=float) for i in range(n)]

    predictor = AircraftTrajectoryPredictor(sequence_len=5, lr=3e-3)

    # Train on first 120 points
    for _ in range(50):
        predictor.train_on_trajectory(trajectory[:120])

    # Evaluate on held-out windows (120-134), predict step 120..134
    errors = []
    for start in range(115, 130):
        history = trajectory[start - 5 : start]
        true_next = trajectory[start]
        pred = predictor.predict_next(history)
        if pred is not None:
            errors.append(np.linalg.norm(pred - true_next))

    rmse = float(np.sqrt(np.mean(np.array(errors) ** 2)))
    mae  = float(np.mean(errors))

    # Naive baseline: last-known-position
    naive_errors = []
    for start in range(115, 130):
        last = trajectory[start - 1]
        true_next = trajectory[start]
        naive_errors.append(np.linalg.norm(last - true_next))
    naive_rmse = float(np.sqrt(np.mean(np.array(naive_errors) ** 2)))

    print("── LSTM Trajectory Predictor ──")
    print(f"  RMSE (post-training):  {rmse:.2f} m")
    print(f"  MAE  (post-training):  {mae:.2f} m")
    print(f"  Naive baseline RMSE:   {naive_rmse:.2f} m")
    print(f"  Improvement over naive: {(1 - rmse/naive_rmse)*100:.1f}%")
    print()


# ── 2. Anomaly Detection Precision / Recall ───────────────────────────────────
def anomaly_metrics():
    torch.manual_seed(11)

    model = TDOAAutoencoder(input_dim=6, lr=1e-2)
    normal_vectors = torch.randn(200, 6) * 0.05

    for _ in range(150):
        model.train_on_batch(normal_vectors)

    # Build labelled test set: 100 normal + 100 anomalous
    torch.manual_seed(99)
    test_normal    = torch.randn(100, 6) * 0.05          # same distribution as training
    test_anomalous = torch.randn(100, 6) * 0.5 + 0.3    # clearly out-of-distribution

    threshold = 0.01

    tp = sum(1 for i in range(100) if model.is_anomalous(test_anomalous[i], threshold))
    fp = sum(1 for i in range(100) if model.is_anomalous(test_normal[i],    threshold))
    fn = 100 - tp
    tn = 100 - fp

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1        = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    accuracy  = (tp + tn) / 200

    normal_errors    = [model.reconstruction_error(test_normal[i])    for i in range(100)]
    anomalous_errors = [model.reconstruction_error(test_anomalous[i]) for i in range(100)]

    print("── TDOA Autoencoder Anomaly Detector ──")
    print(f"  Precision: {precision*100:.1f}%")
    print(f"  Recall:    {recall*100:.1f}%")
    print(f"  F1 Score:  {f1*100:.1f}%")
    print(f"  Accuracy:  {accuracy*100:.1f}%")
    print(f"  Avg reconstruction error (normal):    {np.mean(normal_errors):.5f}")
    print(f"  Avg reconstruction error (anomalous): {np.mean(anomalous_errors):.5f}")
    print()


# ── 3. MLAT Solver Position Error ─────────────────────────────────────────────
def solver_metrics():
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
    order = [ref_idx] + [i for i in range(len(sensors_geo)) if i != ref_idx]
    ordered_geo  = [sensors_geo[i] for i in order]
    ordered_ecef = sensor_ecef[order]
    ordered_dist = distances[order]

    def build_group(noise_s=0.0):
        tdoa = (ordered_dist[1:] - ordered_dist[0]) / C
        if noise_s > 0:
            rng = np.random.default_rng(42)
            tdoa = tdoa + rng.uniform(-noise_s, noise_s, size=tdoa.shape)
        base = 10_000_000_000_000
        obs = []
        for i, (geo, delay) in enumerate(zip(ordered_geo, np.concatenate(([0.0], tdoa))), 1):
            lat, lon, alt = geo
            obs.append(Observation(sensor_id=i, sensor_pk="", lat=lat, lon=lon, alt_m=alt,
                                   total_nanos=base + int(round(delay * 1e9)),
                                   hex="20000000000000", df=4, hex_key="20000000000000"))
        return MLATGroup(hex="20000000000000", icao="abc123", observations=obs,
                         reference_sensor=obs[0].sensor_id,
                         sensor_ecef=[tuple(v.tolist()) for v in ordered_ecef],
                         tdoa_seconds=tdoa.tolist()), tdoa

    # Clean geometry
    group_clean, _ = build_group(0.0)
    fix = solve_mlat_scipy(group_clean, true_ecef.copy())
    solved_ecef = geodetic_to_ecef(fix.lat, fix.lon, fix.alt_m)
    clean_error = float(np.linalg.norm(solved_ecef - true_ecef))

    # With µs noise — multiple noise levels
    noise_results = {}
    for noise_us in [0.1, 0.5, 1.0, 5.0]:
        group_noisy, _ = build_group(noise_us * 1e-6)
        fix_n = solve_mlat_scipy(group_noisy, true_ecef.copy())
        if fix_n:
            se = geodetic_to_ecef(fix_n.lat, fix_n.lon, fix_n.alt_m)
            noise_results[noise_us] = float(np.linalg.norm(se - true_ecef))

    print("── MLAT Solver Position Error ──")
    print(f"  Clean geometry error:  {clean_error:.2f} m")
    for us, err in noise_results.items():
        print(f"  Error @ {us} µs noise:  {err:.2f} m")
    print()


if __name__ == "__main__":
    lstm_metrics()
    anomaly_metrics()
    solver_metrics()
