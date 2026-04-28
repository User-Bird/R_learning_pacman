"""
rl/state_encoder.py  ─  Phase 4: State dict → flat numpy array
───────────────────────────────────────────────────────────────
Converts a TankGame state dict into a fixed-size (77,) float32 array.

Layout:
  [0:19]   Scalar state (pos, dir, health, ammo, mines, charge,
            enemy pos/dir/health, walls x4, flags x3, distance)
  [19:59]  Bullets: up to 10 slots × 4 values (x, y, dir, owner)
  [59:77]  Mines:   up to  6 slots × 3 values (x, y, owner)

All values normalised to roughly [0, 1].
"""

import numpy as np

# Arena dimensions (must match game.py)
COLS = 25
ROWS = 19
MAX_HEALTH  = 5
MAX_AMMO    = 5
MAX_MINES   = 3
MAX_BULLETS = 10
MAX_MINE_SLOTS = 6

STATE_SIZE = 19 + MAX_BULLETS * 4 + MAX_MINE_SLOTS * 3   # = 77


def encode_state(state: dict) -> np.ndarray:
    """
    Convert a state dict (from TankGame._state_for) into a (77,) float32 array.
    Zero-pads bullet/mine lists that are shorter than the slot maximum.
    """
    vec = np.zeros(STATE_SIZE, dtype=np.float32)
    idx = 0

    # ── Scalars [0:19] ────────────────────────────────────────────────────────
    mx, my = state["my_pos"]
    vec[idx]   = mx / (COLS - 1)       # my x
    vec[idx+1] = my / (ROWS - 1)       # my y
    vec[idx+2] = state["my_dir"] / 3.0 # direction 0-3
    vec[idx+3] = state["my_health"]  / MAX_HEALTH
    vec[idx+4] = state["my_ammo"]    / MAX_AMMO
    vec[idx+5] = state["my_mines"]   / MAX_MINES
    vec[idx+6] = state["my_charge_prog"] / 2.0   # max charge_prog = 2

    ex, ey = state["enemy_pos"]
    vec[idx+7]  = ex / (COLS - 1)
    vec[idx+8]  = ey / (ROWS - 1)
    vec[idx+9]  = state["enemy_dir"]    / 3.0
    vec[idx+10] = state["enemy_health"] / MAX_HEALTH

    walls = state["walls_nearby"]
    vec[idx+11] = float(walls["forward"])
    vec[idx+12] = float(walls["back"])
    vec[idx+13] = float(walls["left"])
    vec[idx+14] = float(walls["right"])

    vec[idx+15] = float(state["can_shoot"])
    vec[idx+16] = float(state["can_mine"])
    vec[idx+17] = float(state["on_charge_tile"])

    max_dist = (COLS - 1) + (ROWS - 1)   # Manhattan max = 42
    vec[idx+18] = state["distance_to_enemy"] / max_dist

    idx = 19

    # ── Bullets [19:59]  (up to MAX_BULLETS slots × 4 values) ────────────────
    bullets = state.get("bullets", [])
    for i in range(MAX_BULLETS):
        if i < len(bullets):
            b = bullets[i]
            bx, by = b["pos"]
            vec[idx]   = bx / (COLS - 1)
            vec[idx+1] = by / (ROWS - 1)
            vec[idx+2] = b["dir"] / 3.0
            vec[idx+3] = float(b["owner"] == 1)   # 1.0 = mine, 0.0 = enemy's
        # else: already zero (padding)
        idx += 4

    # ── Mines [59:77]  (up to MAX_MINE_SLOTS slots × 3 values) ───────────────
    mines = state.get("mines", [])
    for i in range(MAX_MINE_SLOTS):
        if i < len(mines):
            m = mines[i]
            mmx, mmy = m["pos"]
            vec[idx]   = mmx / (COLS - 1)
            vec[idx+1] = mmy / (ROWS - 1)
            vec[idx+2] = float(m["owner"] == 1)
        idx += 3

    assert idx == STATE_SIZE, f"encoder bug: idx={idx}, expected {STATE_SIZE}"
    return vec