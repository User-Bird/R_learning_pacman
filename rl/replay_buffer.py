"""
rl/replay_buffer.py  ─  Phase 4: Experience Replay Buffer
──────────────────────────────────────────────────────────
Circular buffer.  Stores (state, action, reward, next_state, done) tuples.
sample(batch_size) returns random batches as torch tensors.
"""

import numpy as np
import torch

from rl.state_encoder import STATE_SIZE


class ReplayBuffer:
    def __init__(self, capacity: int = 50_000):
        self.capacity  = capacity
        self.size      = 0
        self._ptr      = 0   # write head (wraps around)

        # Pre-allocate numpy arrays for speed
        self._states      = np.zeros((capacity, STATE_SIZE), dtype=np.float32)
        self._actions     = np.zeros((capacity,),            dtype=np.int64)
        self._rewards     = np.zeros((capacity,),            dtype=np.float32)
        self._next_states = np.zeros((capacity, STATE_SIZE), dtype=np.float32)
        self._dones       = np.zeros((capacity,),            dtype=np.float32)

    # ── Write ──────────────────────────────────────────────────────────────────

    def push(self,
             state:      np.ndarray,
             action:     int,
             reward:     float,
             next_state: np.ndarray,
             done:       bool):
        """Store one transition."""
        p = self._ptr
        self._states[p]      = state
        self._actions[p]     = action
        self._rewards[p]     = reward
        self._next_states[p] = next_state
        self._dones[p]       = float(done)

        self._ptr  = (p + 1) % self.capacity
        self.size  = min(self.size + 1, self.capacity)

    # ── Read ───────────────────────────────────────────────────────────────────

    def sample(self, batch_size: int, device: torch.device):
        """
        Returns a tuple of tensors:
            (states, actions, rewards, next_states, dones)
        all on `device`.
        """
        idx = np.random.randint(0, self.size, size=batch_size)
        return (
            torch.tensor(self._states[idx],      device=device),
            torch.tensor(self._actions[idx],     device=device),
            torch.tensor(self._rewards[idx],     device=device),
            torch.tensor(self._next_states[idx], device=device),
            torch.tensor(self._dones[idx],       device=device),
        )

    def __len__(self) -> int:
        return self.size