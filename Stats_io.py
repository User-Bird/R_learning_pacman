"""
stats_io.py  —  shared stats bridge between main.py and stats_window.py
────────────────────────────────────────────────────────────────────────
main.py       calls  write_stats(sessions)   every ~0.1 s
stats_window.py calls  read_stats()           every ~0.1 s

Uses a local JSON file (stats_data.json) in the project folder.
Atomic write (write to tmp, rename) so the reader never sees half-written data.
"""

import json
import os
import time

STATS_FILE = "stats_data.json"
STATS_TMP  = "stats_data.tmp.json"


def write_stats(sessions, mode: str, tps: float, fps: float):
    """Called by main.py. Serialises all session stats to disk."""
    data = {
        "ts":   time.time(),
        "mode": mode,
        "tps":  tps,
        "fps":  fps,
        "games": [
            {
                "idx":      s.idx,
                "episodes": s.episodes,
                "wins_p1":  s.wins_p1,
                "wins_p2":  s.wins_p2,
                "ticks":    s.ticks,
                "eps1":     s.trainer1.epsilon,
                "eps2":     s.trainer2.epsilon,
                "buf1":     len(s.trainer1.buffer),
                "buf2":     len(s.trainer2.buffer),
                "loss1":    s.trainer1.last_loss,
                "loss2":    s.trainer2.last_loss,
            }
            for s in sessions
        ],
    }
    with open(STATS_TMP, "w") as f:
        json.dump(data, f)
    # Atomic replace — reader never sees incomplete file
    os.replace(STATS_TMP, STATS_FILE)


def read_stats() -> dict | None:
    """Called by stats_window.py. Returns parsed dict or None if unavailable."""
    try:
        with open(STATS_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None