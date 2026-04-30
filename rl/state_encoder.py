"""
rl/state_encoder.py  ─  Phase 4: State dict → flat numpy array
───────────────────────────────────────────────────────────────
"""
import numpy as np

COLS, ROWS = 25, 19
MAX_HEALTH, MAX_AMMO, MAX_MINES = 5, 5, 3
MAX_BULLETS, MAX_MINE_SLOTS = 10, 6

# Base scalars (21) + Bullets (40) + Mines (18) = 79
STATE_SIZE = 21 + MAX_BULLETS * 4 + MAX_MINE_SLOTS * 3

def encode_state(state: dict) -> np.ndarray:
    vec = np.zeros(STATE_SIZE, dtype=np.float32)
    idx = 0

    mx, my = state["my_pos"]
    vec[idx]   = mx / (COLS - 1)
    vec[idx+1] = my / (ROWS - 1)
    vec[idx+2] = state["my_dir"] / 3.0
    vec[idx+3] = state["my_health"]  / MAX_HEALTH
    vec[idx+4] = state["my_ammo"]    / MAX_AMMO
    vec[idx+5] = state["my_mines"]   / MAX_MINES
    vec[idx+6] = state["my_charge_prog"] / 2.0

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

    max_dist = (COLS - 1) + (ROWS - 1)
    vec[idx+18] = state["distance_to_enemy"] / max_dist

    # NEW explicit features
    vec[idx+19] = state["angle_to_enemy"]
    vec[idx+20] = float(state["enemy_in_line_of_sight"])

    idx = 21

    bullets = state.get("bullets", [])
    for i in range(MAX_BULLETS):
        if i < len(bullets):
            b = bullets[i]
            bx, by = b["pos"]
            vec[idx]   = bx / (COLS - 1)
            vec[idx+1] = by / (ROWS - 1)
            vec[idx+2] = b["dir"] / 3.0
            vec[idx+3] = float(b["owner"] == 1)
        idx += 4

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