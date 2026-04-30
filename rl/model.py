"""
rl/model.py  ─  Phase 4: DQN Neural Network
─────────────────────────────────────────────
"""
import torch
import torch.nn as nn

STATE_SIZE  = 79
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
        return self.net(x)

    def save(self, path: str):
        torch.save(self.state_dict(), path)

    def load(self, path: str, device: torch.device):
        self.load_state_dict(torch.load(path, map_location=device))