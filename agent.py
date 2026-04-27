"""
agent.py  ─  Phase 2B: Agent base class + RandomAgent
──────────────────────────────────────────────────────
Action space:
  0 = rotate left    1 = rotate right    2 = move forward
  3 = shoot          4 = stay            5 = plant mine
"""

import random


class Agent:
    """Base class.  All agents implement get_action(state) → int."""

    def get_action(self, state: dict) -> int:
        raise NotImplementedError


class RandomAgent(Agent):
    """
    Picks actions randomly with sensible weights.
    Respects ammo / mine availability so it doesn't spam blocked actions.
    """

    def get_action(self, state: dict) -> int:
        pool = [0, 1, 2, 4]                        # always available

        if state.get("can_shoot"):
            pool += [3, 3]                          # double-weight shoot

        if state.get("can_mine"):
            pool += [5]

        return random.choice(pool)


class DQNAgent(Agent):
    """Stub — wired up in Phase 4."""

    def __init__(self):
        self.weights = None    # placeholder

    def get_action(self, state: dict) -> int:
        # Falls back to random until weights are loaded
        return random.randint(0, 5)