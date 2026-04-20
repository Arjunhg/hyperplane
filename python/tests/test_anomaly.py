import torch

from mlat.anomaly import TDOAAutoencoder


def test_autoencoder_flags_anomalous_vector_after_training_on_normal_data() -> None:
    torch.manual_seed(11)

    model = TDOAAutoencoder(input_dim=6, lr=1e-2)
    normal_vectors = torch.randn(100, 6) * 0.05

    for _ in range(100):
        model.train_on_batch(normal_vectors)

    normal_error = model.reconstruction_error(normal_vectors[0])

    # Normal data has scale around 0.05, so 0.5 is a clear 10x anomaly.
    anomalous_vector = torch.full((6,), 0.5)
    anomalous_error = model.reconstruction_error(anomalous_vector)

    assert normal_error < 0.01
    assert anomalous_error > normal_error
    assert model.is_anomalous(anomalous_vector, threshold=0.01)


def test_autoencoder_checkpoint_round_trip(tmp_path) -> None:
    torch.manual_seed(17)

    model = TDOAAutoencoder(input_dim=4, lr=1e-2)
    sample = torch.tensor([0.01, -0.03, 0.02, -0.02], dtype=torch.float32)

    for _ in range(20):
        model.train_on_batch(sample.unsqueeze(0))

    checkpoint = tmp_path / "anomaly.pt"
    model.save_checkpoint(str(checkpoint))

    restored = TDOAAutoencoder(input_dim=4, lr=1e-2)
    restored.load_checkpoint(str(checkpoint))

    before = model.reconstruction_error(sample)
    after = restored.reconstruction_error(sample)
    assert abs(before - after) < 1e-8
