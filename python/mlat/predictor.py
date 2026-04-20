"""LSTM-based short-horizon trajectory prediction in ECEF space."""

from __future__ import annotations

from typing import Optional

import numpy as np
import torch
import torch.nn as nn


class AircraftTrajectoryPredictor(nn.Module):
    """Predict next ECEF position from recent trajectory history."""

    def __init__(self, sequence_len: int = 5, lr: float = 1e-3) -> None:
        super().__init__()
        self.sequence_len = int(sequence_len)
        self.lstm = nn.LSTM(
            input_size=3,
            hidden_size=64,
            num_layers=2,
            dropout=0.2,
            batch_first=True,
        )
        self.head = nn.Linear(64, 3)

        self._criterion = nn.MSELoss()
        self._optimizer = torch.optim.Adam(self.parameters(), lr=lr)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        output, _ = self.lstm(x)
        return self.head(output[:, -1, :])

    def predict_next(self, position_history: list[np.ndarray]) -> Optional[np.ndarray]:
        """Predict the next ECEF point from history, if at least 5 positions exist."""
        if len(position_history) < 5:
            return None

        tail = position_history[-self.sequence_len :]
        sequence = np.asarray(tail, dtype=np.float32).reshape(len(tail), 3)
        normalized, mean, std = _normalize_sequence(sequence)

        self.eval()
        with torch.no_grad():
            x = torch.from_numpy(normalized).unsqueeze(0)
            predicted_norm = self.forward(x).cpu().numpy().reshape(3)

        predicted = predicted_norm * std + mean
        return predicted.astype(np.float64)

    def train_on_trajectory(self, positions: list[np.ndarray]) -> Optional[float]:
        """Build sliding windows from trajectory and perform one gradient step."""
        if len(positions) <= self.sequence_len:
            return None

        arr = np.asarray(positions, dtype=np.float32).reshape(len(positions), 3)
        windows: list[np.ndarray] = []
        targets: list[np.ndarray] = []

        for start in range(0, len(arr) - self.sequence_len):
            sequence = arr[start : start + self.sequence_len]
            target = arr[start + self.sequence_len]

            normalized, mean, std = _normalize_sequence(sequence)
            target_norm = (target - mean) / std

            windows.append(normalized)
            targets.append(target_norm)

        x_batch = torch.from_numpy(np.stack(windows, axis=0))
        y_batch = torch.from_numpy(np.stack(targets, axis=0))

        self.train()
        self._optimizer.zero_grad()
        predictions = self.forward(x_batch)
        loss = self._criterion(predictions, y_batch)
        loss.backward()
        self._optimizer.step()

        return float(loss.detach().cpu().item())

    def save_checkpoint(self, path: str) -> None:
        """Persist model weights and config."""
        payload = {
            "sequence_len": self.sequence_len,
            "state_dict": self.state_dict(),
        }
        torch.save(payload, path)

    def load_checkpoint(self, path: str) -> None:
        """Load model weights from checkpoint."""
        payload = torch.load(path, map_location="cpu")
        if "sequence_len" in payload:
            self.sequence_len = int(payload["sequence_len"])
        self.load_state_dict(payload["state_dict"])


def _normalize_sequence(sequence: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mean = np.mean(sequence, axis=0)
    std = np.std(sequence, axis=0)
    std = np.where(std < 1e-6, 1.0, std)
    normalized = (sequence - mean) / std
    return normalized.astype(np.float32), mean.astype(np.float32), std.astype(np.float32)
