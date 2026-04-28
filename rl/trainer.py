"""
rl/trainer.py  ─  Phase 4: DQN Trainer
─────────────────────────────────────────
One Trainer per agent.  Owns:
  - live network  (updated every training step)
  - target network (frozen copy, synced every TARGET_SYNC_EVERY ticks)
  - replay buffer

Training rhythm (controlled externally via tick()):
  Every tick       : push experience, maybe train
  Every 8 ticks    : one gradient step
  Every 500 ticks  : sync target network
  Min buffer size  : 1000 before training starts

Epsilon schedule:
  start=1.0  end=0.05  decay=0.999 per episode
"""

import copy
import numpy as np
import torch
import torch.nn as nn

from rl.model         import DQNModel
from rl.replay_buffer import ReplayBuffer
from rl.state_encoder import encode_state

# ── Hyper-parameters ──────────────────────────────────────────────────────────
BATCH_SIZE        = 64
GAMMA             = 0.99      # discount factor
LR                = 1e-3      # Adam learning rate
TRAIN_EVERY       = 8         # ticks between gradient steps
TARGET_SYNC_EVERY = 500       # ticks between target net syncs
BUFFER_MIN        = 1_000     # don't train until buffer has this many samples
BUFFER_CAPACITY   = 50_000

EPSILON_START = 1.0
EPSILON_END   = 0.05
EPSILON_DECAY = 0.999         # multiplied per episode


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
        self._tick     = 0       # total ticks seen by this trainer
        self.last_loss = 0.0     # for display in stats panel

    # ── Called once per game tick ──────────────────────────────────────────────

    def get_action(self, state: dict) -> int:
        """Epsilon-greedy action selection."""
        if np.random.random() < self.epsilon:
            return np.random.randint(0, 6)

        enc = encode_state(state)
        t   = torch.tensor(enc, dtype=torch.float32, device=self.device).unsqueeze(0)
        with torch.no_grad():
            q = self.online_net(t)
        return int(q.argmax(dim=1).item())

    def push(self, state: dict, action: int, reward: float,
             next_state: dict, done: bool):
        """Store transition and run training step if due."""
        s  = encode_state(state)
        ns = encode_state(next_state)
        self.buffer.push(s, action, reward, ns, done)

        self._tick += 1

        # ── Training step ──────────────────────────────────────────────────────
        if (len(self.buffer) >= BUFFER_MIN and
                self._tick % TRAIN_EVERY == 0):
            self._train_step()

        # ── Target sync ────────────────────────────────────────────────────────
        if self._tick % TARGET_SYNC_EVERY == 0:
            self.target_net.load_state_dict(self.online_net.state_dict())

    def on_episode_end(self):
        """Decay epsilon at the end of each episode."""
        self.epsilon = max(EPSILON_END, self.epsilon * EPSILON_DECAY)

    # ── Internal ───────────────────────────────────────────────────────────────

    def _train_step(self):
        states, actions, rewards, next_states, dones = \
            self.buffer.sample(BATCH_SIZE, self.device)

        # Current Q-values for the actions actually taken
        q_values = self.online_net(states)                          # (B, 6)
        q_taken  = q_values.gather(1, actions.unsqueeze(1)).squeeze(1)  # (B,)

        # Target Q-values (Bellman)
        with torch.no_grad():
            q_next   = self.target_net(next_states).max(dim=1).values  # (B,)
            q_target = rewards + GAMMA * q_next * (1.0 - dones)

        loss = self.loss_fn(q_taken, q_target)

        self.optimizer.zero_grad()
        loss.backward()
        # Gradient clipping keeps training stable
        nn.utils.clip_grad_norm_(self.online_net.parameters(), max_norm=10.0)
        self.optimizer.step()

        self.last_loss = loss.item()