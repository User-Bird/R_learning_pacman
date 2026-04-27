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


# ── Procedural map generator ───────────────────────────────────────────────────

def generate_random_map():
    """Returns (grid: list[list[int]], charge_tiles: list[tuple[int,int]])."""
    grid = [[EMPTY] * COLS for _ in range(ROWS)]

    # 1. Solid border
    for c in range(COLS):
        grid[0][c] = WALL
        grid[ROWS - 1][c] = WALL
    for r in range(ROWS):
        grid[r][0] = WALL
        grid[r][COLS - 1] = WALL

    # 2. Random internal walls
    for _ in range(60):
        r = random.randint(2, ROWS - 3)
        c = random.randint(2, COLS - 3)
        grid[r][c] = WALL

    # 3. Carve 3×3 safe zones around both spawns
    for sx, sy in [SPAWN1, SPAWN2]:
        for r in range(sy - 1, sy + 2):
            for c in range(sx - 1, sx + 2):
                if 0 < r < ROWS - 1 and 0 < c < COLS - 1:
                    grid[r][c] = EMPTY

    # 4. Place charge tiles (min Chebyshev spacing of 3)
    charge_tiles = []
    attempts = 0
    while len(charge_tiles) < 6 and attempts < 2000:
        attempts += 1
        r = random.randint(2, ROWS - 3)
        c = random.randint(2, COLS - 3)
        if grid[r][c] != EMPTY:
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
    """
    Pure-logic tank engine.  No pygame anywhere.

    Public API
    ──────────
    reset()                        → state_dict
    step(actions: list[int])       → (state_dict, rewards: list[float], done: bool)

    Read-only attributes (for renderer)
    ────────────────────────────────────
    grid           list[list[int]]   current tile map
    charge_tiles   list[(cx, cy)]    remaining charge tile positions
    tank1, tank2   Tank              live tank objects
    bullets        list[Bullet]
    active_mines   list[Mine]
    ticks          int
    episode        int
    done           bool
    result_text    str               "DRAW!" / "TANK 1 WINS!" / "TANK 2 WINS!" / ""
    """

    def __init__(self):
        self.episode = 0
        self._new_episode_state()

    # ── Public API ─────────────────────────────────────────────────────────────

    def reset(self):
        """Start a fresh episode.  Returns initial state dict for both tanks."""
        self._new_episode_state()
        return self._state_pair()

    def step(self, actions):
        """
        Advance one tick.

        Parameters
        ----------
        actions : list[int]  length-2  [action_tank1, action_tank2]

        Returns
        -------
        states  : list[dict]     [state_for_tank1, state_for_tank2]
        rewards : list[float]    [reward_tank1, reward_tank2]
        done    : bool
        """
        if self.done:
            return self._state_pair(), [0.0, 0.0], True

        self.ticks += 1
        rewards = [R_TIME_PENALTY, R_TIME_PENALTY]

        # ── actions ────────────────────────────────────────────────────────────
        self._apply_action(self.tank1, actions[0])
        self._apply_action(self.tank2, actions[1])

        # ── cooldowns ──────────────────────────────────────────────────────────
        if self.tank1.cooldown > 0: self.tank1.cooldown -= 1
        if self.tank2.cooldown > 0: self.tank2.cooldown -= 1

        # ── charge tiles ───────────────────────────────────────────────────────
        for tank, idx in ((self.tank1, 0), (self.tank2, 1)):
            if self._update_charge(tank):
                rewards[idx] += R_CHARGE_PICKUP

        # ── bullets ────────────────────────────────────────────────────────────
        hit_rewards = self._update_bullets()   # {player_id: reward_delta}
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

    def _apply_action(self, tank, action):
        if not tank.alive:
            return
        if action == 0:
            tank.direction = (tank.direction - 1) % 4        # rotate left
        elif action == 1:
            tank.direction = (tank.direction + 1) % 4        # rotate right
        elif action == 2:
            self._try_move(tank)
        elif action == 3:
            self._shoot(tank)
        elif action == 5:
            self._plant_mine(tank)
        # 4 = stay → nothing

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

    def _plant_mine(self, tank):
        # 1. Check if they have mines in their inventory
        if tank.mines <= 0:
            return

        # 2. THE FIX: Check how many mines this specific player already has on the board
        active_count = sum(1 for m in self.active_mines if m.owner_id == tank.player_id)
        if active_count >= MAX_MINES:
            return

        # 3. Check if there is already a mine on this exact tile
        if any(m.x == tank.x and m.y == tank.y for m in self.active_mines):
            return

        # 4. Plant the mine and reduce inventory
        self.active_mines.append(Mine(tank.x, tank.y, tank.player_id))
        tank.mines -= 1

    def _update_charge(self, tank):
        """Returns True if a charge tile was collected this tick."""
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
        """Move bullets, check collisions.  Returns {player_id: reward_delta}."""
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

            # Despawn at arena edge or wall
            if not (0 <= nx < COLS and 0 <= ny < ROWS):
                continue
            if self.grid[ny][nx] == WALL:
                continue

            b.x, b.y = float(nx), float(ny)

            # ── bullet hits mine? ──────────────────────────────────────────────
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
                continue   # bullet consumed

            # ── bullet hits enemy tank? ────────────────────────────────────────
            tank_hit = False
            for tank in (self.tank1, self.tank2):
                if not tank.alive:
                    continue
                if b.owner_id == tank.player_id:
                    continue   # no self-damage from bullets
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
        """Trigger proximity mines.  Returns {player_id: reward_delta}."""
        rewards         = {}
        surviving_mines = []

        for m in self.active_mines:
            triggered = False
            for tank in (self.tank1, self.tank2):
                if not tank.alive:
                    continue
                if tank.player_id == m.owner_id:
                    continue   # owner immune
                if abs(tank.x - m.x) <= 1 and abs(tank.y - m.y) <= 1:
                    tank.health -= 2
                    triggered    = True
                    owner = self.tank1 if m.owner_id == 1 else self.tank2
                    owner.mines  = min(MAX_MINES, owner.mines + 1)
                    # Rewards
                    rewards[m.owner_id]        = rewards.get(m.owner_id,        0) + R_MINE_TRIGGER
                    rewards[tank.player_id]    = rewards.get(tank.player_id,    0) + R_TOOK_HIT
                    break

            if not triggered:
                surviving_mines.append(m)

        self.active_mines = surviving_mines
        return rewards

    def _check_done(self):
        """Check win/loss, set done flag.  Returns {player_id: reward_delta}."""
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
        """Build the state dict from one tank's perspective."""
        dx_fwd = DX[my_tank.direction]
        dy_fwd = DY[my_tank.direction]
        dx_bk  = -dx_fwd
        dy_bk  = -dy_fwd
        # Left / right relative to facing
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
            # This tank
            "my_pos":          (my_tank.x, my_tank.y),
            "my_dir":          my_tank.direction,
            "my_health":       my_tank.health,
            "my_ammo":         my_tank.ammo,
            "my_mines":        my_tank.mines,
            "my_charge_prog":  my_tank.charge_progress,
            # Enemy
            "enemy_pos":       (enemy_tank.x, enemy_tank.y),
            "enemy_dir":       enemy_tank.direction,
            "enemy_health":    enemy_tank.health,
            # Bullets (list of dicts)
            "bullets": [
                {"pos": (int(b.x), int(b.y)), "dir": b.direction, "owner": b.owner_id}
                for b in self.bullets
            ],
            # Mines (list of dicts)
            "mines": [
                {"pos": (m.x, m.y), "owner": m.owner_id}
                for m in self.active_mines
            ],
            # Movement booleans (relative to facing)
            "walls_nearby": {
                "forward": blocked(dx_fwd, dy_fwd),
                "back":    blocked(dx_bk,  dy_bk),
                "left":    blocked(dx_l,   dy_l),
                "right":   blocked(dx_r,   dy_r),
            },
            # Convenience flags
            "can_shoot":       my_tank.can_shoot(),
            "can_mine":        (my_tank.mines > 0 and
                                not any(m.x == my_tank.x and m.y == my_tank.y
                                        for m in self.active_mines)),
            "on_charge_tile":  self.grid[my_tank.y][my_tank.x] == CHARGE_TILE,
            "distance_to_enemy": dist,
            # Full arena grid (numpy array, read-only for agent)
            "arena_grid": [row[:] for row in self.grid],
        }

    def _state_pair(self):
        return [
            self._state_for(self.tank1, self.tank2),
            self._state_for(self.tank2, self.tank1),
        ]