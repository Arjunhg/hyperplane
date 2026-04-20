import numpy as np
import torch

from mlat.predictor import AircraftTrajectoryPredictor


def _build_circular_trajectory(n_points: int = 140) -> list[np.ndarray]:
    t = np.linspace(0.0, 4.0 * np.pi, n_points)
    radius = 1_000.0

    x = 1_000_000.0 + radius * np.cos(t)
    y = -2_000_000.0 + radius * np.sin(t)
    z = 10_000.0 + 50.0 * np.sin(0.5 * t)

    return [np.array([x[i], y[i], z[i]], dtype=float) for i in range(n_points)]


def test_predict_next_requires_minimum_history() -> None:
    predictor = AircraftTrajectoryPredictor(sequence_len=5)
    short_history = [np.zeros(3, dtype=float) for _ in range(4)]
    assert predictor.predict_next(short_history) is None


def test_lstm_training_beats_naive_baseline_on_circular_trajectory() -> None:
    torch.manual_seed(7)
    np.random.seed(7)

    predictor = AircraftTrajectoryPredictor(sequence_len=5, lr=3e-3)
    trajectory = _build_circular_trajectory()

    history = trajectory[:20]
    true_next = trajectory[20]
    baseline_error = float(np.linalg.norm(history[-1] - true_next))

    pre_train_prediction = predictor.predict_next(history)
    assert pre_train_prediction is not None
    pre_train_error = float(np.linalg.norm(pre_train_prediction - true_next))

    for _ in range(50):
        loss = predictor.train_on_trajectory(trajectory[:120])
        assert loss is not None

    post_train_prediction = predictor.predict_next(history)
    assert post_train_prediction is not None
    post_train_error = float(np.linalg.norm(post_train_prediction - true_next))

    assert post_train_error < baseline_error
    assert post_train_error < pre_train_error


def test_predictor_checkpoint_round_trip(tmp_path) -> None:
    torch.manual_seed(19)
    predictor = AircraftTrajectoryPredictor(sequence_len=5, lr=3e-3)

    trajectory = _build_circular_trajectory(n_points=40)
    for _ in range(5):
        predictor.train_on_trajectory(trajectory)

    history = trajectory[:10]
    prediction = predictor.predict_next(history)
    assert prediction is not None

    checkpoint = tmp_path / "predictor.pt"
    predictor.save_checkpoint(str(checkpoint))

    restored = AircraftTrajectoryPredictor(sequence_len=5, lr=3e-3)
    restored.load_checkpoint(str(checkpoint))

    restored_prediction = restored.predict_next(history)
    assert restored_prediction is not None
    assert np.allclose(restored_prediction, prediction)
