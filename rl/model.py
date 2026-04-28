"""
rl/model.py  ─  Phase 4: DQN Neural Network
─────────────────────────────────────────────
Architecture:
    Linear(77 → 128) + ReLU
    Linear(128 → 128) + ReLU
    Linear(128 → 6)   ← Q-value per action

Also contains DQNModel.save() / load() helpers.
"""

import torch
import torch.nn as nn


STATE_SIZE  = 77
ACTION_SIZE = 6


class DQNModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(STATE_SIZE, 128),
            nn.ReLU(),
            nn.Linear(128, 128),
            nn.ReLU(),
            nn.Linear(128, ACTION_SIZE),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        x : (batch, 77) float32 tensor
        returns : (batch, 6) Q-values
        """
        return self.net(x)

    def save(self, path: str):
        torch.save(self.state_dict(), path)

    def load(self, path: str, device: torch.device):
        self.load_state_dict(torch.load(path, map_location=device))