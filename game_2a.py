"""
game_2a.py  ─  Phase 2A: Standalone Combat Tank Debug Window
─────────────────────────────────────────────────────────────
Player 1 (GREEN):  A/D to rotate  |  W to move  |  SPACE to shoot | E to plant Mine
Player 2 (RED):    Random bot — moves, shoots, and plants mines randomly
Close: ESC or window X

Changes from original:
  - Procedural Map Generation uses multiple structured templates per quadrant.
  - Proximity Mines added (Max 3, 3x3 range, -2 health damage).
  - UI preserved and updated to track mines.
"""

import pygame
import sys
import random
import math

# ── Arena config ──────────────────────────────────────────────────────────────
TILE = 32
COLS = 25
ROWS = 19
WIN_W = COLS * TILE + 320
WIN_H = ROWS * TILE + 80

ARENA_W = COLS * TILE  # 800 px
ARENA_H = ROWS * TILE  # 608 px
HUD_X = ARENA_W
HUD_W = 320
INFO_Y = ARENA_H
INFO_H = 80

# ── Tile types ─────────────────────────────────────────────────────────────────
EMPTY = 0
WALL = 1
CHARGE_TILE = 2  # standing here for CHARGE_TICKS refills ammo

# ── Directions ─────────────────────────────────────────────────────────────────
UP = 0
RIGHT = 1
DOWN = 2
LEFT = 3

DX = {UP: 0, RIGHT: 1, DOWN: 0, LEFT: -1}
DY = {UP: -1, RIGHT: 0, DOWN: 1, LEFT: 0}
DIR_NAMES = {UP: "UP", RIGHT: "RIGHT", DOWN: "DOWN", LEFT: "LEFT"}

# ── Palette ────────────────────────────────────────────────────────────────────
C_BG = (10, 12, 16)
C_ARENA_BG = (18, 20, 26)
C_WALL = (44, 52, 70)
C_WALL_BORDER = (60, 72, 98)
C_HUD_BG = (14, 16, 22)
C_HUD_LINE = (38, 42, 58)
C_TEXT_PRI = (210, 208, 200)
C_TEXT_SEC = (130, 128, 118)
C_TEXT_DIM = (60, 58, 54)
C_P1 = (80, 220, 120)
C_P1_DARK = (40, 140, 70)
C_P2 = (230, 80, 80)
C_P2_DARK = (160, 40, 40)
C_BULLET_P1 = (160, 255, 180)
C_BULLET_P2 = (255, 160, 140)
C_MINE_P1 = (180, 255, 50)
C_MINE_P2 = (255, 100, 200)
C_GRID = (22, 26, 34)
C_SPAWN_1 = (40, 80, 50)
C_SPAWN_2 = (80, 40, 40)
C_CHARGE_TILE = (60, 50, 10)  # dark gold base
C_CHARGE_GLOW = (220, 190, 40)  # bright gold glow/border

# ── Tunable constants ──────────────────────────────────────────────────────────
MAX_HEALTH = 5
MAX_AMMO = 5
MAX_MINES = 3
SHOOT_COOLDOWN = 25
BULLET_MOVE_EVERY = 2
BULLET_LIFETIME = 60
CHARGE_TICKS = 2

BOT_MOVE_CHANCE = 0.05
BOT_SHOOT_CHANCE = 0.04
BOT_TURN_CHANCE = 0.06
BOT_MINE_CHANCE = 0.01

RESET_DELAY = 120

SPAWN1 = (3, 1)
SPAWN2 = (21, 17)

MINE_PENALTY_RANGE = 7
R_STUPID_MINE      = -10.0


# ── Procedural Map Generation (Structured Templates v3) ────────────────────────

_SPAWN_TEMPLATES = [
    # Object 1 — single wall, full 3×3 protected ring (rare)
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

def _place_template(grid, template, origin_col: int, origin_row: int, protected: set):
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

def _can_place(grid, template, origin_col: int, origin_row: int, protected: set) -> bool:
    """
    Returns True only if every wall (1) or protected (2) cell in the template
    maps to a currently empty, non-protected grid tile that is inside bounds.
    """
    for r, row in enumerate(template):
        for c, val in enumerate(row):
            if val == 0:
                continue
            gc = origin_col + c
            gr = origin_row + r
            if not (0 < gc < COLS - 1 and 0 < gr < ROWS - 1):
                return False
            if grid[gr][gc] == WALL:
                return False
            if (gc, gr) in protected:
                return False
    return True

def _place_objects_in_quadrant(grid, templates, weights, count: int,
                                qc: int, qr: int, qw: int, qh: int, protected: set):
    """Attempt to place `count` objects randomly inside the quadrant."""
    placed   = 0
    attempts = 0
    while placed < count and attempts < 300:
        attempts += 1
        tmpl = random.choices(templates, weights=weights, k=1)[0]
        tmpl = [row[:] for row in tmpl]
        tmpl = _rotate_template(tmpl, random.randint(0, 3))
        t_h  = len(tmpl)
        t_w  = len(tmpl[0]) if t_h > 0 else 0

        max_dc = qw - t_w - 1
        max_dr = qh - t_h - 1
        if max_dc < 0 or max_dr < 0:
            continue

        off_c = random.randint(0, max_dc)
        off_r = random.randint(0, max_dr)
        abs_c = qc + off_c
        abs_r = qr + off_r

        if _can_place(grid, tmpl, abs_c, abs_r, protected):
            _place_template(grid, tmpl, abs_c, abs_r, protected)
            placed += 1

def _clear_safe_zone(grid, cx: int, cy: int, radius: int = 1):
    """Force-clear a square zone around a spawn point (doesn't touch borders)."""
    for dr in range(-radius, radius + 1):
        for dc in range(-radius, radius + 1):
            r, c = cy + dr, cx + dc
            if 0 < r < ROWS - 1 and 0 < c < COLS - 1:
                grid[r][c] = EMPTY

def generate_random_map():
    grid = [[EMPTY] * COLS for _ in range(ROWS)]

    for c in range(COLS):
        grid[0][c] = WALL
        grid[ROWS - 1][c] = WALL
    for r in range(ROWS):
        grid[r][0] = WALL
        grid[r][COLS - 1] = WALL

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

    for sx, sy in [SPAWN1, SPAWN2]:
        _clear_safe_zone(grid, sx, sy, radius=1)
        for dr in range(-1, 2):
            for dc in range(-1, 2):
                protected.discard((sx + dc, sy + dr))

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
    def __init__(self, x, y, direction, player_id):
        self.x = x
        self.y = y
        self.direction = direction
        self.health = MAX_HEALTH
        self.ammo = MAX_AMMO
        self.mines = MAX_MINES
        self.cooldown = 0
        self.charge_progress = 0
        self.player_id = player_id

    @property
    def alive(self):
        return self.health > 0

    def can_shoot(self):
        return self.cooldown <= 0 and self.ammo > 0


class Bullet:
    def __init__(self, x, y, direction, owner_id):
        self.x = float(x)
        self.y = float(y)
        self.direction = direction
        self.owner_id = owner_id
        self.lifetime = BULLET_LIFETIME
        self.move_timer = 0


class Mine:
    def __init__(self, x, y, owner_id):
        self.x = x
        self.y = y
        self.owner_id = owner_id
        self.health = 2  # takes 2 bullets to destroy


# ── Game state ─────────────────────────────────────────────────────────────────
class TankDebugGame:
    def __init__(self):
        self.score1 = 0
        self.score2 = 0
        self.kills1 = 0
        self.kills2 = 0
        self.deaths1 = 0
        self.deaths2 = 0
        self.episode = 0

        self.full_reset()

    def _spawn_tanks(self):
        self.tank1 = Tank(SPAWN1[0], SPAWN1[1], UP, 1)
        self.tank2 = Tank(SPAWN2[0], SPAWN2[1], DOWN, 2)

    def is_walkable(self, x, y):
        if x < 0 or x >= COLS or y < 0 or y >= ROWS:
            return False
        return self.grid[y][x] != WALL

    def try_move(self, tank):
        nx = tank.x + DX[tank.direction]
        ny = tank.y + DY[tank.direction]
        if self.is_walkable(nx, ny):
            other = self.tank2 if tank.player_id == 1 else self.tank1
            if other.alive and other.x == nx and other.y == ny:
                return
            tank.x, tank.y = nx, ny

    def rotate(self, tank, clockwise: bool):
        tank.direction = (tank.direction + (1 if clockwise else -1)) % 4

    def shoot(self, tank):
        if not tank.can_shoot():
            return
        bx = tank.x + DX[tank.direction]
        by = tank.y + DY[tank.direction]
        if not (0 <= bx < COLS and 0 <= by < ROWS):
            return
        if self.grid[by][bx] == WALL:
            return
        self.bullets.append(Bullet(bx, by, tank.direction, tank.player_id))
        tank.ammo -= 1
        tank.cooldown = SHOOT_COOLDOWN

    def plant_mine(self, tank) -> bool:
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
                tank.ammo = MAX_AMMO
                tank.mines = min(MAX_MINES, tank.mines + 1)
                tank.charge_progress = 0
                self.grid[ty][tx] = EMPTY
                if (tx, ty) in self.charge_tiles:
                    self.charge_tiles.remove((tx, ty))
        else:
            tank.charge_progress = 0

    def step(self, action1, action2):
        if self.done:
            return

        self.ticks += 1

        mine1 = self._apply_action(self.tank1, action1)
        mine2 = self._apply_action(self.tank2, action2)

        # Optional debug tracking of bad mines, though game_2a doesn't strictly need RL rewards
        enemy_dist = (abs(self.tank1.x - self.tank2.x) + abs(self.tank1.y - self.tank2.y))
        if mine1 and enemy_dist > MINE_PENALTY_RANGE:
            pass  # RL penalty would go here
        if mine2 and enemy_dist > MINE_PENALTY_RANGE:
            pass  # RL penalty would go here

        if self.tank1.cooldown > 0: self.tank1.cooldown -= 1
        if self.tank2.cooldown > 0: self.tank2.cooldown -= 1

        self._update_charge(self.tank1)
        self._update_charge(self.tank2)
        self._update_bullets()
        self._check_mines()
        self._check_done()

    def _apply_action(self, tank, action) -> bool:
        if not tank.alive:
            return False
        if action == 0:
            self.rotate(tank, clockwise=False)
        elif action == 1:
            self.rotate(tank, clockwise=True)
        elif action == 2:
            self.try_move(tank)
        elif action == 3:
            self.shoot(tank)
        elif action == 5:
            return self.plant_mine(tank)
        return False

    def _update_bullets(self):
        alive = []
        for b in self.bullets:
            b.lifetime -= 1
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
                    mine_hit = True
                    if m.health <= 0:
                        owner = self.tank1 if m.owner_id == 1 else self.tank2
                        owner.mines = min(MAX_MINES, owner.mines + 1)
                        self.active_mines.remove(m)
                    break

            if mine_hit:
                continue

            hit = False
            for tank in [self.tank1, self.tank2]:
                if not tank.alive: continue
                if b.owner_id == tank.player_id: continue
                if int(b.x) == tank.x and int(b.y) == tank.y:
                    tank.health -= 1
                    hit = True
                    break

            if not hit:
                alive.append(b)

        self.bullets = alive

    def _check_mines(self):
        surviving_mines = []
        for m in self.active_mines:
            triggered = False
            for tank in [self.tank1, self.tank2]:
                if not tank.alive:
                    continue
                if tank.player_id == m.owner_id:
                    continue
                dx = abs(tank.x - m.x)
                dy = abs(tank.y - m.y)
                if dx <= 1 and dy <= 1:
                    tank.health -= 2
                    triggered = True
                    owner = self.tank1 if m.owner_id == 1 else self.tank2
                    owner.mines = min(MAX_MINES, owner.mines + 1)
                    break
            if not triggered:
                surviving_mines.append(m)
        self.active_mines = surviving_mines

    def _check_done(self):
        t1_dead = not self.tank1.alive
        t2_dead = not self.tank2.alive
        if not (t1_dead or t2_dead):
            return

        if t1_dead and t2_dead:
            self.result_text = "DRAW!"
        elif t2_dead:
            self.result_text = "PLAYER 1 WINS!"
            self.score1 += 1
            self.kills1 += 1
            self.deaths2 += 1
        else:
            self.result_text = "BOT WINS!"
            self.score2 += 1
            self.kills2 += 1
            self.deaths1 += 1

        self.done = True
        self.result_timer = RESET_DELAY

    def new_episode(self):
        self.grid, self.charge_tiles = generate_random_map()
        self._spawn_tanks()
        self.bullets = []
        self.active_mines = []
        self.ticks = 0
        self.result_text = ""
        self.result_timer = 0
        self.done = False
        self.episode += 1

    def full_reset(self):
        self.score1 = self.score2 = 0
        self.kills1 = self.kills2 = 0
        self.deaths1 = self.deaths2 = 0
        self.episode = 0
        self.new_episode()


# ── Bot AI ─────────────────────────────────────────────────────────────────────
class RandomBot:
    def get_action(self, tank):
        r = random.random()
        if r < BOT_MINE_CHANCE and tank.mines > 0:
            return 5
        elif r < BOT_SHOOT_CHANCE + BOT_MINE_CHANCE and tank.ammo > 0:
            return 3
        elif r < BOT_SHOOT_CHANCE + BOT_MINE_CHANCE + BOT_TURN_CHANCE:
            return random.choice([0, 1])
        elif r < BOT_SHOOT_CHANCE + BOT_MINE_CHANCE + BOT_TURN_CHANCE + BOT_MOVE_CHANCE:
            return 2
        return 4


# ── Renderer helpers ───────────────────────────────────────────────────────────
def draw_arrow(surf, color, cx, cy, direction, size=10):
    angle = {UP: 90, RIGHT: 0, DOWN: 270, LEFT: 180}[direction]
    rad = math.radians(angle)
    pts = []
    for da, dist in [(0, size), (140, size * 0.6), (-140, size * 0.6)]:
        a = rad + math.radians(da)
        pts.append((cx + math.cos(a) * dist, cy - math.sin(a) * dist))
    pygame.draw.polygon(surf, color, pts)


def draw_tank(surf, tank, tile, is_player):
    cx = tank.x * tile + tile // 2
    cy = tank.y * tile + tile // 2
    body_c = C_P1 if is_player else C_P2
    dark_c = C_P1_DARK if is_player else C_P2_DARK

    shadow_surf = pygame.Surface((tile - 4, tile - 4), pygame.SRCALPHA)
    shadow_surf.fill((0, 0, 0, 80))
    surf.blit(shadow_surf, (cx - tile // 2 + 3, cy - tile // 2 + 3))

    body_rect = pygame.Rect(cx - tile // 2 + 1, cy - tile // 2 + 1, tile - 2, tile - 2)
    pygame.draw.rect(surf, dark_c, body_rect, border_radius=4)
    pygame.draw.rect(surf, body_c, body_rect.inflate(-4, -4), border_radius=3)

    draw_arrow(surf, (255, 255, 255), cx, cy, tank.direction, size=tile * 0.28)

    pip_w = 5
    pip_gap = 2
    total = MAX_HEALTH * (pip_w + pip_gap) - pip_gap
    px = cx - total // 2
    py = cy + tile // 2 + 3
    for i in range(MAX_HEALTH):
        color = body_c if i < tank.health else (40, 40, 50)
        pygame.draw.rect(surf, color, (px + i * (pip_w + pip_gap), py, pip_w, 4))

    ammo_total = MAX_AMMO * (pip_w + pip_gap) - pip_gap
    apx = cx - ammo_total // 2
    apy = py + 7
    for i in range(MAX_AMMO):
        color = C_CHARGE_GLOW if i < tank.ammo else (40, 40, 50)
        pygame.draw.rect(surf, color, (apx + i * (pip_w + pip_gap), apy, pip_w, 3))

    if tank.charge_progress > 0:
        frac = tank.charge_progress / CHARGE_TICKS
        pygame.draw.arc(surf, C_CHARGE_GLOW,
                        pygame.Rect(cx - tile // 2, cy - tile // 2, tile, tile),
                        0, frac * 2 * math.pi, 3)


def draw_bullet(surf, bullet, tile):
    cx = int(bullet.x * tile + tile // 2)
    cy = int(bullet.y * tile + tile // 2)
    color = C_BULLET_P1 if bullet.owner_id == 1 else C_BULLET_P2
    pygame.draw.circle(surf, color, (cx, cy), 5)
    pygame.draw.circle(surf, color, (cx, cy), 7, 1)


def draw_mine(surf, mine, tile):
    cx = int(mine.x * tile + tile // 2)
    cy = int(mine.y * tile + tile // 2)
    color = C_MINE_P1 if mine.owner_id == 1 else C_MINE_P2

    r4x = max(0, (mine.x - 2) * tile)
    r4y = max(0, (mine.y - 2) * tile)
    r4w = min(ARENA_W, (mine.x + 3) * tile) - r4x
    r4h = min(ARENA_H, (mine.y + 3) * tile) - r4y
    ring4_surf = pygame.Surface((r4w, r4h), pygame.SRCALPHA)
    ring4_surf.fill((100, 100, 100, 12))
    surf.blit(ring4_surf, (r4x, r4y))
    pygame.draw.rect(surf, (100, 100, 100, 35), pygame.Rect(r4x, r4y, r4w, r4h), 1)

    zx = max(0, (mine.x - 1) * tile)
    zy = max(0, (mine.y - 1) * tile)
    zw = min(ARENA_W, (mine.x + 2) * tile) - zx
    zh = min(ARENA_H, (mine.y + 2) * tile) - zy
    zone_surf = pygame.Surface((zw, zh), pygame.SRCALPHA)
    zone_surf.fill((*color, 22))
    surf.blit(zone_surf, (zx, zy))
    pygame.draw.rect(surf, (*color, 55), pygame.Rect(zx, zy, zw, zh), 1)

    pygame.draw.circle(surf, color, (cx, cy), 6)
    pygame.draw.circle(surf, (255, 255, 255), (cx, cy), 2)


def draw_arena(surf, game, tile):
    surf.fill(C_ARENA_BG)

    for r in range(ROWS):
        for c in range(COLS):
            rect = pygame.Rect(c * tile, r * tile, tile, tile)
            t = game.grid[r][c]

            if t == WALL:
                pygame.draw.rect(surf, C_WALL, rect)
                pygame.draw.rect(surf, C_WALL_BORDER, rect, 1)
            elif t == CHARGE_TILE:
                pygame.draw.rect(surf, C_CHARGE_TILE, rect)
                pygame.draw.rect(surf, C_CHARGE_GLOW, rect, 1)
                mx, my = c * tile + tile // 2, r * tile + tile // 2
                pts = [(mx, my - 8), (mx - 4, my), (mx + 1, my), (mx, my + 8), (mx + 4, my), (mx - 1, my)]
                pygame.draw.lines(surf, C_CHARGE_GLOW, False, pts, 2)
            else:
                pygame.draw.rect(surf, C_GRID, rect, 1)

    for (sx, sy), col in [(SPAWN1, C_SPAWN_1), (SPAWN2, C_SPAWN_2)]:
        tint = pygame.Surface((tile, tile), pygame.SRCALPHA)
        tint.fill((*col, 80))
        surf.blit(tint, (sx * tile, sy * tile))

    for m in game.active_mines:
        draw_mine(surf, m, tile)

    for b in game.bullets:
        draw_bullet(surf, b, tile)

    if game.tank1.alive: draw_tank(surf, game.tank1, tile, True)
    if game.tank2.alive: draw_tank(surf, game.tank2, tile, False)


def draw_hud(surf, game, hud_rect, font_md, font_sm, font_xs):
    pygame.draw.rect(surf, C_HUD_BG, hud_rect)
    pygame.draw.line(surf, C_HUD_LINE, (hud_rect.left, hud_rect.top), (hud_rect.left, hud_rect.bottom), 2)

    x = hud_rect.left + 16
    y = 16

    def line(text, color=C_TEXT_SEC, gap=6, font=None):
        nonlocal y
        f = font or font_xs
        t = f.render(text, True, color)
        surf.blit(t, (x, y))
        y += t.get_height() + gap

    def sep():
        nonlocal y
        pygame.draw.line(surf, C_HUD_LINE, (x, y), (hud_rect.right - 16, y), 1)
        y += 10

    line("COMBAT TANK  2A", C_TEXT_PRI, font=font_md)
    line("Debug Window", C_TEXT_DIM, gap=14)
    sep()

    line("── PLAYER 1 (YOU) ──", C_P1, gap=4, font=font_sm)
    line(f"  Health   {'█' * game.tank1.health}{'░' * (MAX_HEALTH - game.tank1.health)}", C_P1)
    line(f"  Ammo     {'◆' * game.tank1.ammo}{'◇' * (MAX_AMMO - game.tank1.ammo)}", C_CHARGE_GLOW)
    line(f"  Mines    {'●' * game.tank1.mines}{'○' * (MAX_MINES - game.tank1.mines)}", C_MINE_P1)
    chg = f"charging {game.tank1.charge_progress}/{CHARGE_TICKS}" if game.tank1.charge_progress > 0 else "—"
    line(f"  Charge   {chg}", C_TEXT_DIM)
    line(f"  Facing   {DIR_NAMES[game.tank1.direction]}", C_TEXT_SEC)
    line(f"  Cooldown {game.tank1.cooldown:>3}", C_TEXT_SEC, gap=10)

    line("── BOT (P2) ─────────", C_P2, gap=4, font=font_sm)
    line(f"  Health   {'█' * game.tank2.health}{'░' * (MAX_HEALTH - game.tank2.health)}", C_P2)
    line(f"  Ammo     {'◆' * game.tank2.ammo}{'◇' * (MAX_AMMO - game.tank2.ammo)}", C_CHARGE_GLOW)
    line(f"  Mines    {'●' * game.tank2.mines}{'○' * (MAX_MINES - game.tank2.mines)}", C_MINE_P2)
    line(f"  Facing   {DIR_NAMES[game.tank2.direction]}", C_TEXT_SEC, gap=10)

    sep()

    line(f"Episode  {game.episode:>5}", C_TEXT_SEC)
    line(f"Ticks    {game.ticks:>5}", C_TEXT_DIM)
    line(f"Bullets  {len(game.bullets):>5}", C_TEXT_DIM)
    line(f"Mines    {len(game.active_mines):>5}", C_TEXT_DIM, gap=10)

    sep()

    line("SCORE", C_TEXT_PRI, gap=4, font=font_sm)
    line(f"  P1  W:{game.score1}  K:{game.kills1}  D:{game.deaths1}", C_P1)
    line(f"  Bot W:{game.score2}  K:{game.kills2}  D:{game.deaths2}", C_P2, gap=12)

    sep()

    line("CONTROLS", C_TEXT_PRI, gap=4, font=font_sm)
    line("  W       move forward", C_TEXT_DIM)
    line("  A / D   rotate (tap)", C_TEXT_DIM)
    line("  SPACE   shoot", C_TEXT_DIM)
    line("  E       drop mine (-2 HP, 3x3)", C_MINE_P1)
    line("  R       FULL RESET", C_TEXT_DIM)
    line("  ESC     quit", C_TEXT_DIM, gap=8)
    line("  ◆ = ammo  ⚡ = refill", C_CHARGE_GLOW)


def draw_result_overlay(surf, text, alpha_frac, font_lg, font_sm):
    overlay = pygame.Surface((ARENA_W, ARENA_H), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, int(180 * alpha_frac)))
    surf.blit(overlay, (0, 0))

    t1 = font_lg.render(text, True, (255, 255, 220))
    t2 = font_sm.render("Generating new map...", True, (160, 158, 150))
    cx, cy = ARENA_W // 2, ARENA_H // 2
    surf.blit(t1, (cx - t1.get_width() // 2, cy - t1.get_height()))
    surf.blit(t2, (cx - t2.get_width() // 2, cy + 8))


def draw_info_bar(surf, info_rect, font_xs):
    pygame.draw.rect(surf, C_HUD_BG, info_rect)
    pygame.draw.line(surf, C_HUD_LINE, info_rect.topleft, info_rect.topright, 1)
    tips = ("Phase 2A  |  Map randomizes every episode  |  Mines: 3x3 range, -2 HP  |  R = full reset")
    t = font_xs.render(tips, True, C_TEXT_DIM)
    surf.blit(t, (16, info_rect.top + (INFO_H - t.get_height()) // 2))


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    pygame.init()
    pygame.display.set_caption("Combat Tank RL — Phase 2A Debug")
    screen = pygame.display.set_mode((WIN_W, WIN_H))

    font_lg = pygame.font.SysFont("consolas", 36, bold=True)
    font_md = pygame.font.SysFont("consolas", 15, bold=True)
    font_sm = pygame.font.SysFont("consolas", 13, bold=True)
    font_xs = pygame.font.SysFont("consolas", 12)

    arena_surf = pygame.Surface((ARENA_W, ARENA_H))
    hud_rect = pygame.Rect(HUD_X, 0, HUD_W, WIN_H - INFO_H)
    info_rect = pygame.Rect(0, INFO_Y, WIN_W, INFO_H)

    game = TankDebugGame()
    bot = RandomBot()
    clock = pygame.time.Clock()

    running = True
    while running:
        player_action = 4

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_r:
                    game.full_reset()
                elif event.key == pygame.K_a:
                    player_action = 0
                elif event.key == pygame.K_d:
                    player_action = 1
                elif event.key == pygame.K_e:
                    player_action = 5

        if not running:
            break

        keys = pygame.key.get_pressed()
        if player_action == 4:
            if keys[pygame.K_SPACE]:
                player_action = 3
            elif keys[pygame.K_w]:
                player_action = 2

        if game.done:
            game.result_timer -= 1
            if game.result_timer <= 0:
                game.new_episode()
        else:
            bot_action = bot.get_action(game.tank2)
            game.step(player_action, bot_action)

        screen.fill(C_BG)

        draw_arena(arena_surf, game, TILE)
        screen.blit(arena_surf, (0, 0))

        if game.done and game.result_text:
            alpha_frac = min(1.0, (RESET_DELAY - game.result_timer) / 20)
            draw_result_overlay(screen, game.result_text, alpha_frac, font_lg, font_sm)

        draw_hud(screen, game, hud_rect, font_md, font_sm, font_xs)
        draw_info_bar(screen, info_rect, font_xs)

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()
    sys.exit(0)


if __name__ == "__main__":
    main()