"""
game.py  ─  Phase 2B: TankGame clean engine
────────────────────────────────────────────
Zero pygame dependency.  This is the RL contract.
Agents only ever call step() and reset().

Action space (per tank):
  0 = rotate left (CCW)
  1 = rotate right (CW)
  2 = move forward
  3 = shoot
  4 = stay
  5 = plant mine
"""

import random
import numpy as np

# ── Arena constants ────────────────────────────────────────────────────────────
COLS = 25
ROWS = 19

SPAWN1 = (3, 1)   # (col, row)
SPAWN2 = (21, 17)

# ── Tile types ─────────────────────────────────────────────────────────────────
EMPTY       = 0
WALL        = 1
CHARGE_TILE = 2

# ── Directions ─────────────────────────────────────────────────────────────────
UP    = 0
RIGHT = 1
DOWN  = 2
LEFT  = 3

DX = {UP: 0, RIGHT: 1, DOWN: 0,  LEFT: -1}
DY = {UP: -1, RIGHT: 0, DOWN: 1, LEFT:  0}

# ── Tunable constants ──────────────────────────────────────────────────────────
MAX_HEALTH     = 5
MAX_AMMO       = 5
MAX_MINES      = 3
SHOOT_COOLDOWN = 25
BULLET_MOVE_EVERY = 2
BULLET_LIFETIME   = 60
CHARGE_TICKS      = 2

# ── Reward constants ───────────────────────────────────────────────────────────
R_HIT_ENEMY      =  50.0
R_MINE_TRIGGER   =  80.0
R_KILL           = 200.0
R_TOOK_HIT       = -30.0
R_DIED           = -200.0
R_CHARGE_PICKUP  =  10.0
R_TIME_PENALTY   =  -1.0

MINE_PENALTY_RANGE = 7       # manhattan tiles — beyond this = pointless drop
R_STUPID_MINE      = -10.0   # penalty for dropping a mine when enemy is far


# ── Templates + Helpers ────────────────────────────────────────────────────────

_SPAWN_TEMPLATES = [
    # Object 1 — single wall, full 3×3 protected ring  (rare — low weight)
    [
        [2, 2, 2],
        [2, 1, 2],
        [2, 2, 2],
    ],
    # Object 2 — two-wall vertical strip
    [
        [0, 2, 2],
        [0, 1, 2],
        [0, 1, 2],
        [0, 2, 2],
    ],
    # Object 3 — two-wall L-stub
    [
        [0, 2, 2],
        [0, 1, 2],
        [0, 1, 0],
        [0, 0, 0],
    ],
    # Object 4 — three-wall vertical strip
    [
        [0, 0, 2],
        [0, 1, 2],
        [0, 1, 2],
        [0, 1, 2],
        [0, 0, 2],
    ],
]
# Weights: object 1 rare, objects 2-4 equal
_SPAWN_WEIGHTS = [1, 3, 3, 3]

_NON_SPAWN_TEMPLATES = [
    # Object 1 — spiral / stepped shape
    [
        [2, 2, 2, 2, 2],
        [0, 1, 1, 1, 2],
        [0, 2, 2, 1, 2],
        [0, 1, 2, 1, 2],
        [2, 0, 0, 0, 2],
    ],
    # Object 2 — double horizontal bar
    [
        [2, 2, 2, 2, 2],
        [0, 1, 1, 1, 0],
        [0, 2, 2, 2, 0],
        [0, 1, 1, 1, 0],
        [2, 2, 2, 2, 2],
    ],
]
_NON_SPAWN_WEIGHTS = [1, 1]


def _rotate_template_90(t):
    rows, cols = len(t), len(t[0])
    return [[t[rows - 1 - r][c] for r in range(rows)] for c in range(cols)]


def _rotate_template(t, times: int):
    for _ in range(times % 4):
        t = _rotate_template_90(t)
    return t


def _place_template(grid, template, origin_col: int, origin_row: int,
                    protected: set):
    """
    Stamp one template onto grid at (origin_col, origin_row).
        1 → WALL
        2 → EMPTY + add to protected
        0 → leave as-is
    """
    for r, row in enumerate(template):
        for c, val in enumerate(row):
            gc = origin_col + c
            gr = origin_row + r
            if not (0 < gc < COLS - 1 and 0 < gr < ROWS - 1):
                continue
            if val == 1:
                grid[gr][gc] = WALL
            elif val == 2:
                grid[gr][gc] = EMPTY
                protected.add((gc, gr))


def _can_place(grid, template, origin_col: int, origin_row: int,
               protected: set) -> bool:
    """
    Returns True only if every wall (1) or protected (2) cell in the template
    maps to a currently empty, non-protected grid tile that is inside bounds.
    This prevents two objects from merging or violating each other's buffers.
    """
    for r, row in enumerate(template):
        for c, val in enumerate(row):
            if val == 0:
                continue
            gc = origin_col + c
            gr = origin_row + r
            # Must be strictly inside the border
            if not (0 < gc < COLS - 1 and 0 < gr < ROWS - 1):
                return False
            # No existing wall and not inside another object's protected zone
            if grid[gr][gc] == WALL:
                return False
            if (gc, gr) in protected:
                return False
    return True


def _place_objects_in_quadrant(grid, templates, weights, count: int,
                                qc: int, qr: int, qw: int, qh: int,
                                protected: set):
    """
    Attempt to place `count` objects randomly inside the quadrant
    (qc, qr) with dimensions (qw × qh).

    Each object is randomly chosen (with weights), randomly rotated,
    and placed at a random position with a 1-tile margin.
    Placement is skipped if it would collide with an existing wall or
    protected zone from a previously placed object.

    Up to 300 attempts total across all objects before giving up.
    """
    placed   = 0
    attempts = 0

    while placed < count and attempts < 300:
        attempts += 1

        tmpl = random.choices(templates, weights=weights, k=1)[0]
        tmpl = [row[:] for row in tmpl]                     # deep copy
        tmpl = _rotate_template(tmpl, random.randint(0, 3))
        t_h  = len(tmpl)
        t_w  = len(tmpl[0]) if t_h > 0 else 0

        # Random offset with 1-tile margin inside the quadrant
        max_dc = qw - t_w - 1
        max_dr = qh - t_h - 1
        if max_dc < 0 or max_dr < 0:
            continue                   # template is larger than available space

        off_c = random.randint(0, max_dc)
        off_r = random.randint(0, max_dr)

        abs_c = qc + off_c
        abs_r = qr + off_r

        if _can_place(grid, tmpl, abs_c, abs_r, protected):
            _place_template(grid, tmpl, abs_c, abs_r, protected)
            placed += 1


def _clear_safe_zone(grid, cx: int, cy: int, radius: int = 1):
    """
    Force-clear a square zone around a spawn point.
    Uses  0 < r  and  0 < c  — NEVER touches border wall tiles.
    """
    for dr in range(-radius, radius + 1):
        for dc in range(-radius, radius + 1):
            r, c = cy + dr, cx + dc
            # Strict inequality: skip row 0, row ROWS-1, col 0, col COLS-1
            if 0 < r < ROWS - 1 and 0 < c < COLS - 1:
                grid[r][c] = EMPTY


def generate_random_map():
    """
    Structured-corner map with multiple objects per quadrant.

    TL + BR  (spawn corners)   → 4–7 objects  (object 1 rare)
    TR + BL  (non-spawn)       → 2–4 objects  (equal weight)

    Objects are placed at random positions / rotations within their quadrant.
    Collision detection prevents objects from merging or touching each other.
    Spawn safe zones are cleared last so nothing blocks respawn.
    """
    grid = [[EMPTY] * COLS for _ in range(ROWS)]

    # 1. Border walls
    for c in range(COLS):
        grid[0][c] = WALL
        grid[ROWS - 1][c] = WALL
    for r in range(ROWS):
        grid[r][0] = WALL
        grid[r][COLS - 1] = WALL

    # 2. Quadrant definitions
    #    Centre col 12 and row 9 stay EMPTY — always-open cross corridors.
    protected: set = set()

    # TL — spawn corner
    _place_objects_in_quadrant(
        grid, _SPAWN_TEMPLATES, _SPAWN_WEIGHTS,
        random.randint(4, 7),
        1, 1, 11, 8, protected,
    )
    # TR — non-spawn
    _place_objects_in_quadrant(
        grid, _NON_SPAWN_TEMPLATES, _NON_SPAWN_WEIGHTS,
        random.randint(2, 4),
        13, 1, 11, 8, protected,
    )
    # BL — non-spawn
    _place_objects_in_quadrant(
        grid, _NON_SPAWN_TEMPLATES, _NON_SPAWN_WEIGHTS,
        random.randint(2, 4),
        1, 10, 11, 8, protected,
    )
    # BR — spawn corner
    _place_objects_in_quadrant(
        grid, _SPAWN_TEMPLATES, _SPAWN_WEIGHTS,
        random.randint(4, 7),
        13, 10, 11, 8, protected,
    )

    # 3. Force-clear spawn zones AFTER all objects are placed
    for sx, sy in [SPAWN1, SPAWN2]:
        _clear_safe_zone(grid, sx, sy, radius=1)
        for dr in range(-1, 2):
            for dc in range(-1, 2):
                protected.discard((sx + dc, sy + dr))

    # 4. Charge tiles — skip walls, protected zones, spawn points
    charge_tiles = []
    attempts     = 0
    while len(charge_tiles) < 6 and attempts < 2000:
        attempts += 1
        r = random.randint(1, ROWS - 2)
        c = random.randint(1, COLS - 2)
        if grid[r][c] != EMPTY:
            continue
        if (c, r) in protected:
            continue
        if (c, r) == SPAWN1 or (c, r) == SPAWN2:
            continue
        if any(abs(c - ec) <= 2 and abs(r - er) <= 2 for (ec, er) in charge_tiles):
            continue
        grid[r][c] = CHARGE_TILE
        charge_tiles.append((c, r))

    return grid, charge_tiles


# ── Data classes ───────────────────────────────────────────────────────────────

class Tank:
    __slots__ = ("x", "y", "direction", "health", "ammo", "mines",
                 "cooldown", "charge_progress", "player_id")

    def __init__(self, x, y, direction, player_id):
        self.x               = x
        self.y               = y
        self.direction       = direction
        self.health          = MAX_HEALTH
        self.ammo            = MAX_AMMO
        self.mines           = MAX_MINES
        self.cooldown        = 0
        self.charge_progress = 0
        self.player_id       = player_id

    @property
    def alive(self):
        return self.health > 0

    def can_shoot(self):
        return self.cooldown <= 0 and self.ammo > 0


class Bullet:
    __slots__ = ("x", "y", "direction", "owner_id", "lifetime", "move_timer")

    def __init__(self, x, y, direction, owner_id):
        self.x          = float(x)
        self.y          = float(y)
        self.direction  = direction
        self.owner_id   = owner_id
        self.lifetime   = BULLET_LIFETIME
        self.move_timer = 0


class Mine:
    __slots__ = ("x", "y", "owner_id", "health")

    def __init__(self, x, y, owner_id):
        self.x        = x
        self.y        = y
        self.owner_id = owner_id
        self.health   = 2   # 2 bullet hits to destroy


# ── TankGame ───────────────────────────────────────────────────────────────────

class TankGame:
    def __init__(self):
        self.episode = 0
        self._new_episode_state()

    def reset(self):
        """Start a fresh episode.  Returns initial state dict for both tanks."""
        self._new_episode_state()
        return self._state_pair()

    def step(self, actions):
        """Advance one tick."""
        if self.done:
            return self._state_pair(), [0.0, 0.0], True

        self.ticks += 1
        rewards = [R_TIME_PENALTY, R_TIME_PENALTY]

        # ── actions ────────────────────────────────────────────────────────────
        mine1 = self._apply_action(self.tank1, actions[0])
        mine2 = self._apply_action(self.tank2, actions[1])

        # ── mine stupidity penalty ────────────────────────────────────────────
        enemy_dist = (abs(self.tank1.x - self.tank2.x)
                      + abs(self.tank1.y - self.tank2.y))
        if mine1 and enemy_dist > MINE_PENALTY_RANGE:
            rewards[0] += R_STUPID_MINE
        if mine2 and enemy_dist > MINE_PENALTY_RANGE:
            rewards[1] += R_STUPID_MINE

        # ── cooldowns ──────────────────────────────────────────────────────────
        if self.tank1.cooldown > 0: self.tank1.cooldown -= 1
        if self.tank2.cooldown > 0: self.tank2.cooldown -= 1

        # ── charge tiles ───────────────────────────────────────────────────────
        for tank, idx in ((self.tank1, 0), (self.tank2, 1)):
            if self._update_charge(tank):
                rewards[idx] += R_CHARGE_PICKUP

        # ── bullets ────────────────────────────────────────────────────────────
        hit_rewards = self._update_bullets()
        for pid, delta in hit_rewards.items():
            rewards[pid - 1] += delta

        # ── mines ──────────────────────────────────────────────────────────────
        mine_rewards = self._check_mines()
        for pid, delta in mine_rewards.items():
            rewards[pid - 1] += delta

        # ── win / loss ─────────────────────────────────────────────────────────
        kill_rewards = self._check_done()
        for pid, delta in kill_rewards.items():
            rewards[pid - 1] += delta

        return self._state_pair(), rewards, self.done

    # ── Internal logic ─────────────────────────────────────────────────────────

    def _new_episode_state(self):
        self.grid, self.charge_tiles = generate_random_map()
        self.tank1 = Tank(SPAWN1[0], SPAWN1[1], UP,   1)
        self.tank2 = Tank(SPAWN2[0], SPAWN2[1], DOWN, 2)
        self.bullets      = []
        self.active_mines = []
        self.ticks        = 0
        self.done         = False
        self.result_text  = ""
        self.episode     += 1

    def is_walkable(self, x, y):
        if x < 0 or x >= COLS or y < 0 or y >= ROWS:
            return False
        return self.grid[y][x] != WALL

    def _apply_action(self, tank, action) -> bool:
        if not tank.alive:
            return False
        if action == 0:
            tank.direction = (tank.direction - 1) % 4
        elif action == 1:
            tank.direction = (tank.direction + 1) % 4
        elif action == 2:
            self._try_move(tank)
        elif action == 3:
            self._shoot(tank)
        elif action == 5:
            return self._plant_mine(tank)
        return False

    def _try_move(self, tank):
        nx = tank.x + DX[tank.direction]
        ny = tank.y + DY[tank.direction]
        if not self.is_walkable(nx, ny):
            return
        other = self.tank2 if tank.player_id == 1 else self.tank1
        if other.alive and other.x == nx and other.y == ny:
            return
        tank.x, tank.y = nx, ny

    def _shoot(self, tank):
        if not tank.can_shoot():
            return
        bx = tank.x + DX[tank.direction]
        by = tank.y + DY[tank.direction]
        if not (0 <= bx < COLS and 0 <= by < ROWS):
            return
        if self.grid[by][bx] == WALL:
            return
        self.bullets.append(Bullet(bx, by, tank.direction, tank.player_id))
        tank.ammo    -= 1
        tank.cooldown = SHOOT_COOLDOWN

    def _plant_mine(self, tank) -> bool:
        if tank.mines <= 0:
            return False
        active_count = sum(1 for m in self.active_mines if m.owner_id == tank.player_id)
        if active_count >= MAX_MINES:
            return False
        if any(m.x == tank.x and m.y == tank.y for m in self.active_mines):
            return False
        self.active_mines.append(Mine(tank.x, tank.y, tank.player_id))
        tank.mines -= 1
        return True

    def _update_charge(self, tank):
        tx, ty = tank.x, tank.y
        if self.grid[ty][tx] == CHARGE_TILE:
            tank.charge_progress += 1
            if tank.charge_progress >= CHARGE_TICKS:
                tank.ammo            = MAX_AMMO
                tank.mines           = min(MAX_MINES, tank.mines + 1)
                tank.charge_progress = 0
                self.grid[ty][tx]    = EMPTY
                if (tx, ty) in self.charge_tiles:
                    self.charge_tiles.remove((tx, ty))
                return True
        else:
            tank.charge_progress = 0
        return False

    def _update_bullets(self):
        rewards = {}
        alive   = []
        for b in self.bullets:
            b.lifetime   -= 1
            b.move_timer += 1
            if b.lifetime <= 0:
                continue
            if b.move_timer < BULLET_MOVE_EVERY:
                alive.append(b)
                continue

            b.move_timer = 0
            nx = int(b.x) + DX[b.direction]
            ny = int(b.y) + DY[b.direction]

            if not (0 <= nx < COLS and 0 <= ny < ROWS):
                continue
            if self.grid[ny][nx] == WALL:
                continue

            b.x, b.y = float(nx), float(ny)

            mine_hit = False
            for m in self.active_mines:
                if int(b.x) == m.x and int(b.y) == m.y:
                    m.health -= 1
                    mine_hit  = True
                    if m.health <= 0:
                        owner = self.tank1 if m.owner_id == 1 else self.tank2
                        owner.mines = min(MAX_MINES, owner.mines + 1)
                        self.active_mines.remove(m)
                    break

            if mine_hit:
                continue

            tank_hit = False
            for tank in (self.tank1, self.tank2):
                if not tank.alive:
                    continue
                if b.owner_id == tank.player_id:
                    continue
                if int(b.x) == tank.x and int(b.y) == tank.y:
                    tank.health -= 1
                    tank_hit     = True
                    shooter_id   = b.owner_id
                    rewards[shooter_id] = rewards.get(shooter_id, 0) + R_HIT_ENEMY
                    rewards[tank.player_id] = rewards.get(tank.player_id, 0) + R_TOOK_HIT
                    break

            if not tank_hit:
                alive.append(b)

        self.bullets = alive
        return rewards

    def _check_mines(self):
        rewards         = {}
        surviving_mines = []
        for m in self.active_mines:
            triggered = False
            for tank in (self.tank1, self.tank2):
                if not tank.alive:
                    continue
                if tank.player_id == m.owner_id:
                    continue
                if abs(tank.x - m.x) <= 1 and abs(tank.y - m.y) <= 1:
                    tank.health -= 2
                    triggered    = True
                    owner = self.tank1 if m.owner_id == 1 else self.tank2
                    owner.mines  = min(MAX_MINES, owner.mines + 1)
                    rewards[m.owner_id]        = rewards.get(m.owner_id,        0) + R_MINE_TRIGGER
                    rewards[tank.player_id]    = rewards.get(tank.player_id,    0) + R_TOOK_HIT
                    break
            if not triggered:
                surviving_mines.append(m)

        self.active_mines = surviving_mines
        return rewards

    def _check_done(self):
        t1_dead = not self.tank1.alive
        t2_dead = not self.tank2.alive
        if not (t1_dead or t2_dead):
            return {}

        rewards = {}
        if t1_dead and t2_dead:
            self.result_text = "DRAW!"
            rewards[1] = R_DIED
            rewards[2] = R_DIED
        elif t2_dead:
            self.result_text = "TANK 1 WINS!"
            rewards[1] = R_KILL
            rewards[2] = R_DIED
        else:
            self.result_text = "TANK 2 WINS!"
            rewards[1] = R_DIED
            rewards[2] = R_KILL

        self.done = True
        return rewards

    # ── State builder ──────────────────────────────────────────────────────────

    def _state_for(self, my_tank, enemy_tank):
        dx_fwd = DX[my_tank.direction]
        dy_fwd = DY[my_tank.direction]
        dx_bk  = -dx_fwd
        dy_bk  = -dy_fwd
        dx_l = DX[(my_tank.direction - 1) % 4]
        dy_l = DY[(my_tank.direction - 1) % 4]
        dx_r = DX[(my_tank.direction + 1) % 4]
        dy_r = DY[(my_tank.direction + 1) % 4]

        def blocked(tx, ty):
            nx, ny = my_tank.x + tx, my_tank.y + ty
            if not (0 <= nx < COLS and 0 <= ny < ROWS):
                return True
            return self.grid[ny][nx] == WALL

        dist = abs(my_tank.x - enemy_tank.x) + abs(my_tank.y - enemy_tank.y)

        return {
            "my_pos":          (my_tank.x, my_tank.y),
            "my_dir":          my_tank.direction,
            "my_health":       my_tank.health,
            "my_ammo":         my_tank.ammo,
            "my_mines":        my_tank.mines,
            "my_charge_prog":  my_tank.charge_progress,
            "enemy_pos":       (enemy_tank.x, enemy_tank.y),
            "enemy_dir":       enemy_tank.direction,
            "enemy_health":    enemy_tank.health,
            "bullets": [
                {"pos": (int(b.x), int(b.y)), "dir": b.direction, "owner": b.owner_id}
                for b in self.bullets
            ],
            "mines": [
                {"pos": (m.x, m.y), "owner": m.owner_id}
                for m in self.active_mines
            ],
            "walls_nearby": {
                "forward": blocked(dx_fwd, dy_fwd),
                "back":    blocked(dx_bk,  dy_bk),
                "left":    blocked(dx_l,   dy_l),
                "right":   blocked(dx_r,   dy_r),
            },
            "can_shoot":       my_tank.can_shoot(),
            "can_mine":        (my_tank.mines > 0 and
                                not any(m.x == my_tank.x and m.y == my_tank.y
                                        for m in self.active_mines)),
            "on_charge_tile":  self.grid[my_tank.y][my_tank.x] == CHARGE_TILE,
            "distance_to_enemy": dist,
            "arena_grid": [row[:] for row in self.grid],
        }

    def _state_pair(self):
        return [
            self._state_for(self.tank1, self.tank2),
            self._state_for(self.tank2, self.tank1),
        ]