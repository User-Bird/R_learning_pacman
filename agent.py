"""
agent.py  ─  Phase 4: Agent base class + RandomAgent + DQNAgent
────────────────────────────────────────────────────────────────
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
            pool += [3] * 2                        # double-weight shoot

        if state.get("can_mine"):
            pool += [5]

        return random.choice(pool)


class DQNAgent(Agent):
    """
    Full DQN agent.  Wraps a Trainer and delegates everything to it.

    Usage (in GameSession):
        agent = DQNAgent()
        action = agent.get_action(state)
        agent.push(state, action, reward, next_state, done)
        if done:
            agent.on_episode_end()
    """

    def __init__(self, trainer):
        """
        Parameters
        ----------
        trainer : rl.trainer.Trainer
            The Trainer instance that owns this agent's network and buffer.
            Two agents in the same game share NO trainer — each has its own.
        """
        self.trainer = trainer

    def get_action(self, state: dict) -> int:
        return self.trainer.get_action(state)

    def push(self, state: dict, action: int, reward: float,
             next_state: dict, done: bool):
        self.trainer.push(state, action, reward, next_state, done)

    def on_episode_end(self):
        self.trainer.on_episode_end()

    @property
    def epsilon(self) -> float:
        return self.trainer.epsilon

    @property
    def last_loss(self) -> float:
        return self.trainer.last_loss