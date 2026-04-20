"""Online anomaly detection for TDOA vectors via autoencoder reconstruction."""

from __future__ import annotations

import torch
import torch.nn as nn


class TDOAAutoencoder(nn.Module):
    """Compact autoencoder used to model normal TDOA behavior."""

    def __init__(self, input_dim: int, lr: float = 1e-3) -> None:
        super().__init__()
        self.input_dim = int(input_dim)

        self.encoder = nn.Sequential(
            nn.Linear(self.input_dim, 16),
            nn.ReLU(),
            nn.Linear(16, 8),
            nn.ReLU(),
            nn.Linear(8, 4),
            nn.ReLU(),
        )
        self.decoder = nn.Sequential(
            nn.Linear(4, 8),
            nn.ReLU(),
            nn.Linear(8, 16),
            nn.ReLU(),
            nn.Linear(16, self.input_dim),
        )

        self._criterion = nn.MSELoss()
        self._optimizer = torch.optim.Adam(self.parameters(), lr=lr)

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        latent = self.encoder(inputs)
        return self.decoder(latent)

    def train_on_batch(self, tdoa_vectors: torch.Tensor) -> float:
        """Perform one optimization step on a batch of TDOA vectors."""
        self.train()

        batch = tdoa_vectors.to(dtype=torch.float32)
        if batch.ndim == 1:
            batch = batch.unsqueeze(0)

        self._optimizer.zero_grad()
        reconstructed = self.forward(batch)
        loss = self._criterion(reconstructed, batch)
        loss.backward()
        self._optimizer.step()

        return float(loss.detach().cpu().item())

    def reconstruction_error(self, tdoa_vector: torch.Tensor) -> float:
        """Return reconstruction MSE for a single TDOA vector."""
        self.eval()

        vector = tdoa_vector.to(dtype=torch.float32)
        if vector.ndim == 1:
            vector = vector.unsqueeze(0)

        with torch.no_grad():
            reconstructed = self.forward(vector)
            loss = self._criterion(reconstructed, vector)

        return float(loss.detach().cpu().item())

    def is_anomalous(self, tdoa_vector: torch.Tensor, threshold: float = 0.01) -> bool:
        """Flag vector as anomalous if reconstruction error exceeds threshold."""
        return self.reconstruction_error(tdoa_vector) > threshold

    def save_checkpoint(self, path: str) -> None:
        """Persist model weights and metadata."""
        payload = {
            "input_dim": self.input_dim,
            "state_dict": self.state_dict(),
        }
        torch.save(payload, path)

    def load_checkpoint(self, path: str) -> None:
        """Load model weights from checkpoint."""
        payload = torch.load(path, map_location="cpu")
        if "input_dim" in payload and int(payload["input_dim"]) != self.input_dim:
            raise ValueError("Checkpoint input_dim does not match model input_dim")
        self.load_state_dict(payload["state_dict"])
