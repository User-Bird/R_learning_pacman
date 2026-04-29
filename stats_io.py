"""
stats_io.py  —  shared stats bridge between main.py and stats_window.py
────────────────────────────────────────────────────────────────────────
main.py         calls  write_stats(sessions, ...)   every ~0.1 s
stats_window.py calls  read_stats()                 every ~0.1 s

Uses a local JSON file (stats_data.json) in the project folder.
Atomic write (write to tmp, rename) so the reader never sees half-written data.

Staleness: stats_window checks the 'ts' timestamp — if it's older than
STALE_AFTER seconds, main.py is considered dead and the window shows "Offline".

Shutdown: main.py writes {"shutdown": true} before exiting so stats_window
can close itself cleanly instead of waiting for the file to go stale.
"""

import json
import os
import time

STATS_FILE  = "stats_data.json"
STATS_TMP   = "stats_data.tmp.json"
STALE_AFTER = 3.0   # seconds — if data is older than this, main.py is dead


def write_stats(sessions, mode: str, tps: float, fps: float,
                session_mode: str = "NEW_VS_NEW"):
    """
    Called by main.py every ~0.1 s.

    session_mode:  "NEW_VS_NEW" | "NEW_VS_AGENT" | "AGENT_VS_AGENT"
    """
    data = {
        "ts":           time.time(),
        "shutdown":     False,
        "mode":         mode,           # WATCH / FAST / HEADLESS
        "session_mode": session_mode,   # NEW_VS_NEW / NEW_VS_AGENT / AGENT_VS_AGENT
        "tps":          tps,
        "fps":          fps,
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
    _atomic_write(data)


def write_shutdown():
    """
    Called by main.py just before pygame.quit().
    Tells stats_window to close itself.
    """
    _atomic_write({"shutdown": True, "ts": time.time()})


def _atomic_write(data: dict):
    with open(STATS_TMP, "w") as f:
        json.dump(data, f)
    os.replace(STATS_TMP, STATS_FILE)


def read_stats() -> dict | None:
    """
    Called by stats_window.py.
    Returns parsed dict, or None if file missing / corrupt / stale.
    A stale file means main.py has died without writing a shutdown signal.
    """
    try:
        with open(STATS_FILE, "r") as f:
            data = json.load(f)
        # Treat stale data the same as no data
        age = time.time() - data.get("ts", 0)
        if age > STALE_AFTER:
            return None
        return data
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def clear_stats():
    """Delete the stats file (call on main.py startup so old data never shows)."""
    for path in (STATS_FILE, STATS_TMP):
        try:
            os.remove(path)
        except FileNotFoundError:
            pass