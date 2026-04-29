"""
rl/trainer.py  ─  Phase 5: Optimised DQN Trainer
──────────────────────────────────────────────────
Key change: batch_act(encoded_states, epsilons) → one GPU forward pass for N agents.
"""

import copy
import numpy as np
import torch
import torch.nn as nn

from rl.model         import DQNModel
from rl.replay_buffer import ReplayBuffer
from rl.state_encoder import encode_state

BATCH_SIZE        = 64
GAMMA             = 0.99
LR                = 1e-3
TRAIN_EVERY       = 8
TARGET_SYNC_EVERY = 500
BUFFER_MIN        = 1_000
BUFFER_CAPACITY   = 50_000

EPSILON_START = 1.0
EPSILON_END   = 0.05
EPSILON_DECAY = 0.999


class Trainer:
    def __init__(self):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        self.online_net = DQNModel().to(self.device)
        self.target_net = copy.deepcopy(self.online_net)
        self.target_net.eval()

        self.optimizer = torch.optim.Adam(self.online_net.parameters(), lr=LR)
        self.loss_fn   = nn.MSELoss()
        self.buffer    = ReplayBuffer(BUFFER_CAPACITY)

        self.epsilon   = EPSILON_START
        self._tick     = 0
        self.last_loss = 0.0

    # ── Single-agent fallback ─────────────────────────────────────────────────
    def get_action(self, state: dict) -> int:
        if np.random.random() < self.epsilon:
            return np.random.randint(0, 6)
        enc = encode_state(state)
        t   = torch.tensor(enc, dtype=torch.float32, device=self.device).unsqueeze(0)
        with torch.no_grad():
            q = self.online_net(t)
        return int(q.argmax(dim=1).item())

    # ── BATCHED inference — one GPU call for all N states ────────────────────
    @torch.no_grad()
    def batch_act(self, encoded_states: np.ndarray, epsilons: np.ndarray) -> np.ndarray:
        """
        encoded_states : (N, 77) float32 — pre-encoded states for N agents
        epsilons       : (N,)    float32 — epsilon per agent
        returns        : (N,)    int64   — chosen actions
        """
        t        = torch.tensor(encoded_states, dtype=torch.float32, device=self.device)
        q_values = self.online_net(t)                       # (N, 6) — one pass
        greedy   = q_values.argmax(dim=1).cpu().numpy()    # (N,)
        explore  = np.random.random(len(epsilons)) < epsilons
        random_a = np.random.randint(0, 6, size=len(epsilons))
        return np.where(explore, random_a, greedy)

    # ── Experience storage + training ─────────────────────────────────────────
    def push(self, state: dict, action: int, reward: float,
             next_state: dict, done: bool):
        self.buffer.push(encode_state(state), action, reward,
                         encode_state(next_state), done)
        self._tick += 1
        if len(self.buffer) >= BUFFER_MIN and self._tick % TRAIN_EVERY == 0:
            self._train_step()
        if self._tick % TARGET_SYNC_EVERY == 0:
            self.target_net.load_state_dict(self.online_net.state_dict())

    def push_encoded(self, s: np.ndarray, action: int, reward: float,
                     ns: np.ndarray, done: bool):
        """Push already-encoded states — avoids double encoding in hot path."""
        self.buffer.push(s, action, reward, ns, done)
        self._tick += 1
        if len(self.buffer) >= BUFFER_MIN and self._tick % TRAIN_EVERY == 0:
            self._train_step()
        if self._tick % TARGET_SYNC_EVERY == 0:
            self.target_net.load_state_dict(self.online_net.state_dict())

    def on_episode_end(self):
        self.epsilon = max(EPSILON_END, self.epsilon * EPSILON_DECAY)

    def _train_step(self):
        states, actions, rewards, next_states, dones = \
            self.buffer.sample(BATCH_SIZE, self.device)

        q_values = self.online_net(states)
        q_taken  = q_values.gather(1, actions.unsqueeze(1)).squeeze(1)

        with torch.no_grad():
            q_next   = self.target_net(next_states).max(dim=1).values
            q_target = rewards + GAMMA * q_next * (1.0 - dones)

        loss = self.loss_fn(q_taken, q_target)
        self.optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(self.online_net.parameters(), max_norm=10.0)
        self.optimizer.step()
        self.last_loss = loss.item()