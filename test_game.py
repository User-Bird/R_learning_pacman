"""
test_game.py  ─  headless sanity checks for TankGame
Run:  python test_game.py
"""

import sys
sys.path.insert(0, ".")

from game import (
    TankGame, SPAWN1, SPAWN2, UP, DOWN, RIGHT, LEFT,
    MAX_HEALTH, MAX_AMMO, MAX_MINES,
    R_HIT_ENEMY, R_TOOK_HIT, R_MINE_TRIGGER, R_KILL, R_DIED,
    R_CHARGE_PICKUP, R_TIME_PENALTY,
    CHARGE_TILE,
)

PASS = "  ✓"
FAIL = "  ✗ FAIL"

def check(label, cond):
    tag = PASS if cond else FAIL
    print(f"{tag}  {label}")
    if not cond:
        global _failures
        _failures += 1

_failures = 0


# ── 1. reset() gives correct initial state ────────────────────────────────────
print("\n── 1. reset()")
g = TankGame()
states = g.reset()
s1, s2 = states
check("reset returns 2 states",      len(states) == 2)
check("tank1 at SPAWN1",             s1["my_pos"] == SPAWN1)
check("tank2 at SPAWN2",             s2["my_pos"] == SPAWN2)
check("full health",                 s1["my_health"] == MAX_HEALTH)
check("full ammo",                   s1["my_ammo"]   == MAX_AMMO)
check("full mines",                  s1["my_mines"]  == MAX_MINES)
check("can_shoot true at start",     s1["can_shoot"])
check("can_mine true at start",      s1["can_mine"])
check("done=False",                  not g.done)
check("episode incremented",         g.episode >= 1)


# ── 2. Time penalty every tick ────────────────────────────────────────────────
print("\n── 2. time penalty")
g = TankGame(); g.reset()
_, rewards, _ = g.step([4, 4])   # both stay
check(f"reward = time_penalty ({R_TIME_PENALTY})",
      rewards[0] == R_TIME_PENALTY and rewards[1] == R_TIME_PENALTY)


# ── 3. Bullet hits enemy ──────────────────────────────────────────────────────
print("\n── 3. bullet hits enemy")
from game import DX, DY, Bullet, BULLET_MOVE_EVERY, BULLET_LIFETIME, SHOOT_COOLDOWN

g = TankGame(); g.reset()
# Place tanks adjacent: tank1 at (5,5) facing RIGHT, tank2 at (6,5)
g.grid[5][5] = 0; g.grid[5][6] = 0; g.grid[5][7] = 0
g.tank1.x, g.tank1.y, g.tank1.direction = 5, 5, RIGHT
g.tank2.x, g.tank2.y = 7, 5   # 2 tiles to the right
# Manually inject a bullet already at (6,5) heading right
b = Bullet(6, 5, RIGHT, 1)
b.move_timer = BULLET_MOVE_EVERY  # will move this tick
g.bullets = [b]
_, rewards, _ = g.step([4, 4])
check("tank2 took 1 damage",    g.tank2.health == MAX_HEALTH - 1)
check("shooter got R_HIT_ENEMY", rewards[0] == R_TIME_PENALTY + R_HIT_ENEMY)
check("victim got R_TOOK_HIT",   rewards[1] == R_TIME_PENALTY + R_TOOK_HIT)


# ── 4. Mine triggers on enemy ─────────────────────────────────────────────────
print("\n── 4. mine trigger")
from game import Mine

g = TankGame(); g.reset()
g.grid[5][5] = 0; g.grid[5][6] = 0
g.tank1.x, g.tank1.y = 4, 5   # safe
g.tank2.x, g.tank2.y = 6, 5   # will step into mine range
mine = Mine(5, 5, 1)           # owned by tank1
g.active_mines = [mine]
_, rewards, _ = g.step([4, 4])
check("mine triggered (tank2 lost 2 HP)",  g.tank2.health == MAX_HEALTH - 2)
check("mine refunded to owner",            g.tank1.mines == MAX_MINES)
check("mine gone from active list",        len(g.active_mines) == 0)
check("owner got R_MINE_TRIGGER",          rewards[0] == R_TIME_PENALTY + R_MINE_TRIGGER)
check("victim got R_TOOK_HIT",             rewards[1] == R_TIME_PENALTY + R_TOOK_HIT)


# ── 5. Owner is immune to own mine ────────────────────────────────────────────
print("\n── 5. mine owner immunity")
g = TankGame(); g.reset()
g.grid[5][5] = 0
g.tank1.x, g.tank1.y = 5, 5
mine = Mine(5, 5, 1)
g.active_mines = [mine]
_, rewards, _ = g.step([4, 4])
check("owner not damaged",     g.tank1.health == MAX_HEALTH)
check("mine still there",      len(g.active_mines) == 1)


# ── 6. Charge tile refills ammo + mine ───────────────────────────────────────
print("\n── 6. charge tile")
from game import CHARGE_TICKS

g = TankGame(); g.reset()
# Put a charge tile under tank1
g.grid[SPAWN1[1]][SPAWN1[0]] = CHARGE_TILE
g.charge_tiles = [(SPAWN1[0], SPAWN1[1])]
g.tank1.ammo  = 1
g.tank1.mines = 0
# Stand on it for CHARGE_TICKS ticks
for i in range(CHARGE_TICKS - 1):
    g.step([4, 4])
check("not yet charged",  g.tank1.ammo == 1)
_, rewards, _ = g.step([4, 4])
check("ammo refilled to MAX",       g.tank1.ammo  == MAX_AMMO)
check("mine +1",                    g.tank1.mines == 1)
check("tile consumed",              g.grid[SPAWN1[1]][SPAWN1[0]] == 0)
check("reward includes R_CHARGE",   rewards[0] == R_TIME_PENALTY + R_CHARGE_PICKUP)


# ── 7. Kill reward ─────────────────────────────────────────────────────────────
print("\n── 7. kill / die rewards")
g = TankGame(); g.reset()
g.tank2.health = 1
# Place bullet one tile to the LEFT of tank2, heading RIGHT — it will move onto tank2 this tick
bx = g.tank2.x - 1
by = g.tank2.y
g.grid[by][bx]           = 0
g.grid[by][g.tank2.x]    = 0
b = Bullet(bx, by, RIGHT, 1)
b.move_timer = BULLET_MOVE_EVERY
g.bullets = [b]
_, rewards, done = g.step([4, 4])
check("game done",           done)
check("killer got R_KILL",   rewards[0] >= R_KILL)
check("victim got R_DIED",   rewards[1] <= R_DIED)
check("result_text set",     "WINS" in g.result_text or "DRAW" in g.result_text)


# ── 8. step() after done is a no-op ───────────────────────────────────────────
print("\n── 8. step after done is no-op")
_, rewards2, done2 = g.step([3, 3])
check("still done",          done2)
check("rewards both 0",      rewards2 == [0.0, 0.0])


# ── 9. walls_nearby correct ───────────────────────────────────────────────────
print("\n── 9. walls_nearby")
g = TankGame(); g.reset()
states = g.reset()
# tank1 spawns at (3,1) facing UP — row 0 is a border wall above it
check("forward wall when facing UP from row 1",
      states[0]["walls_nearby"]["forward"])


# ── 10. reset() increments episode ───────────────────────────────────────────
print("\n── 10. episode counter")
g = TankGame()
g.reset(); ep1 = g.episode
g.reset(); ep2 = g.episode
check("episode increments on each reset", ep2 == ep1 + 1)


# ── Summary ───────────────────────────────────────────────────────────────────
print()
if _failures == 0:
    print("All tests passed ✓")
else:
    print(f"{_failures} test(s) FAILED")
    sys.exit(1)