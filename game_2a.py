"""
game_2a.py  ─  Phase 2A: Standalone Combat Tank Debug Window
─────────────────────────────────────────────────────────────
Player 1 (GREEN):  A/D to rotate  |  W to move  |  SPACE to shoot
Player 2 (RED):    Random bot — moves + shoots randomly
Close: ESC or window X

Changes from original:
  - Bullets move every 2 ticks (half speed) → dodging is now possible
  - Ammo system: 5 shots max, NO passive recharge
  - Charge tiles ('C') on map — stand on one for 2 ticks to refill to 5
  - Map does NOT reset on episode reset (walls stay, charge tiles stay consumed)
  - A/D rotate on KEYDOWN only (no more spinning)
  - SHOOT_COOLDOWN raised to 25 ticks — no infinite shooting
  - Bot respects ammo too
"""

import pygame
import sys
import random
import math

# ── Arena config ──────────────────────────────────────────────────────────────
TILE        = 32
COLS        = 25
ROWS        = 19
WIN_W       = COLS * TILE + 320
WIN_H       = ROWS * TILE + 80

ARENA_W     = COLS * TILE   # 800 px
ARENA_H     = ROWS * TILE   # 608 px
HUD_X       = ARENA_W
HUD_W       = 320
INFO_Y      = ARENA_H
INFO_H      = 80

# ── Tile types ─────────────────────────────────────────────────────────────────
EMPTY        = 0
WALL         = 1
CHARGE_TILE  = 2   # standing here for CHARGE_TICKS refills ammo

# ── Directions ─────────────────────────────────────────────────────────────────
UP    = 0
RIGHT = 1
DOWN  = 2
LEFT  = 3

DX = { UP: 0, RIGHT: 1, DOWN: 0, LEFT: -1 }
DY = { UP: -1, RIGHT: 0, DOWN: 1, LEFT:  0 }
DIR_NAMES = { UP: "UP", RIGHT: "RIGHT", DOWN: "DOWN", LEFT: "LEFT" }

# ── Palette ────────────────────────────────────────────────────────────────────
C_BG           = (10,  12,  16)
C_ARENA_BG     = (18,  20,  26)
C_WALL         = (44,  52,  70)
C_WALL_BORDER  = (60,  72,  98)
C_HUD_BG       = (14,  16,  22)
C_HUD_LINE     = (38,  42,  58)
C_TEXT_PRI     = (210, 208, 200)
C_TEXT_SEC     = (130, 128, 118)
C_TEXT_DIM     = (60,  58,  54)
C_P1           = (80,  220, 120)
C_P1_DARK      = (40,  140,  70)
C_P2           = (230,  80,  80)
C_P2_DARK      = (160,  40,  40)
C_BULLET_P1    = (160, 255, 180)
C_BULLET_P2    = (255, 160, 140)
C_GRID         = (22,  26,  34)
C_SPAWN_1      = (40,  80,  50)
C_SPAWN_2      = (80,  40,  40)
C_CHARGE_TILE  = (60,  50,  10)   # dark gold base
C_CHARGE_GLOW  = (220, 190,  40)  # bright gold glow/border

# ── Tunable constants ──────────────────────────────────────────────────────────
MAX_HEALTH      = 5
MAX_AMMO        = 5
SHOOT_COOLDOWN  = 25      # ticks between shots (raised from 18)
BULLET_MOVE_EVERY = 2     # bullet advances 1 tile every N ticks (half speed)
BULLET_LIFETIME = 60      # ticks before auto-despawn (longer since slower)
CHARGE_TICKS    = 2       # ticks standing on charge tile to refill

BOT_MOVE_CHANCE  = 0.05
BOT_SHOOT_CHANCE = 0.04
BOT_TURN_CHANCE  = 0.06

RESET_DELAY = 120   # ticks to show result overlay before new episode

# ── Map ────────────────────────────────────────────────────────────────────────
# 19 rows × 25 cols.
# '#' = wall   ' ' = empty   '1' = P1 spawn   '2' = P2 spawn   'C' = charge tile
# Fewer internal walls than original — more open for dodging
MAP_STR = [
    "#########################",
    "#  1     C #       #   #",
    "#  ##      #         # #",
    "#    #   #   #   #     #",
    "#        #####         #",
    "#  #   #       #   #   #",
    "##      C # #  C      ##",
    "#         # #         ##",
    "#    ##       ##       #",
    "#         # #         ##",
    "##      C # #  C      ##",
    "#  #   #       #   #   #",
    "#        #####         #",
    "#    #   #   #   #     #",
    "#  ##      #         # #",
    "#     #   C   C  #     #",
    "#   #   #     #   #    #",
    "#   #       #     C 2  #",
    "#########################",
]


def parse_map(map_str):
    grid = []
    spawn1 = spawn2 = None
    charge_tiles = []
    for r, line in enumerate(map_str):
        row = []
        for c in range(COLS):
            ch = line[c] if c < len(line) else ' '
            if ch == '#':
                row.append(WALL)
            elif ch == '1':
                row.append(EMPTY)
                spawn1 = (c, r)
            elif ch == '2':
                row.append(EMPTY)
                spawn2 = (c, r)
            elif ch == 'C':
                row.append(CHARGE_TILE)
                charge_tiles.append((c, r))
            else:
                row.append(EMPTY)
        grid.append(row)
    return grid, spawn1, spawn2, charge_tiles


GRID_TEMPLATE, SPAWN1, SPAWN2, CHARGE_TILES_TEMPLATE = parse_map(MAP_STR)


# ── Data classes ───────────────────────────────────────────────────────────────
class Tank:
    def __init__(self, x, y, direction, player_id):
        self.x          = x
        self.y          = y
        self.direction  = direction
        self.health     = MAX_HEALTH
        self.ammo       = MAX_AMMO
        self.cooldown   = 0
        self.charge_progress = 0   # ticks spent on current charge tile
        self.player_id  = player_id

    @property
    def alive(self):
        return self.health > 0

    def can_shoot(self):
        return self.cooldown <= 0 and self.ammo > 0


class Bullet:
    def __init__(self, x, y, direction, owner_id):
        self.x         = float(x)
        self.y         = float(y)
        self.direction = direction
        self.owner_id  = owner_id
        self.lifetime  = BULLET_LIFETIME
        self.move_timer = 0   # counts up to BULLET_MOVE_EVERY


# ── Game state ─────────────────────────────────────────────────────────────────
class TankDebugGame:
    def __init__(self):
        # Grid is shared across episodes — only reset manually (R key)
        self.grid        = [row[:] for row in GRID_TEMPLATE]
        self.charge_tiles = list(CHARGE_TILES_TEMPLATE)  # active charge tiles

        # Per-episode stats (persist across episodes)
        self.score1  = 0
        self.score2  = 0
        self.kills1  = 0
        self.kills2  = 0
        self.deaths1 = 0
        self.deaths2 = 0
        self.episode = 1

        self._spawn_tanks()
        self.bullets      = []
        self.ticks        = 0
        self.result_text  = ""
        self.result_timer = 0
        self.done         = False

    def _spawn_tanks(self):
        self.tank1 = Tank(SPAWN1[0], SPAWN1[1], UP,   1)
        self.tank2 = Tank(SPAWN2[0], SPAWN2[1], DOWN, 2)

    # ── movement & shooting ───────────────────────────────────────────────────
    def is_walkable(self, x, y):
        if x < 0 or x >= COLS or y < 0 or y >= ROWS:
            return False
        return self.grid[y][x] != WALL

    def try_move(self, tank):
        nx = tank.x + DX[tank.direction]
        ny = tank.y + DY[tank.direction]
        if self.is_walkable(nx, ny):
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
        tank.ammo    -= 1
        tank.cooldown = SHOOT_COOLDOWN

    # ── charge tile logic ─────────────────────────────────────────────────────
    def _update_charge(self, tank):
        """If tank is on a charge tile, tick progress and refill if ready."""
        tx, ty = tank.x, tank.y
        if self.grid[ty][tx] == CHARGE_TILE:
            tank.charge_progress += 1
            if tank.charge_progress >= CHARGE_TICKS:
                tank.ammo = MAX_AMMO
                tank.charge_progress = 0
                # Consume the charge tile (turns to EMPTY until map reset)
                self.grid[ty][tx] = EMPTY
                if (tx, ty) in self.charge_tiles:
                    self.charge_tiles.remove((tx, ty))
        else:
            tank.charge_progress = 0

    # ── step ──────────────────────────────────────────────────────────────────
    def step(self, action1, action2):
        if self.done:
            return

        self.ticks += 1

        self._apply_action(self.tank1, action1)
        self._apply_action(self.tank2, action2)

        # Cooldowns
        if self.tank1.cooldown > 0: self.tank1.cooldown -= 1
        if self.tank2.cooldown > 0: self.tank2.cooldown -= 1

        # Charge tiles
        self._update_charge(self.tank1)
        self._update_charge(self.tank2)

        # Bullets
        self._update_bullets()

        # Win check
        self._check_done()

    def _apply_action(self, tank, action):
        if not tank.alive:
            return
        if action == 0:
            self.rotate(tank, clockwise=False)
        elif action == 1:
            self.rotate(tank, clockwise=True)
        elif action == 2:
            self.try_move(tank)
        elif action == 3:
            self.shoot(tank)
        # 4 = stay

    def _update_bullets(self):
        alive = []
        for b in self.bullets:
            b.lifetime    -= 1
            b.move_timer  += 1

            if b.lifetime <= 0:
                continue

            # Only advance position every BULLET_MOVE_EVERY ticks
            if b.move_timer < BULLET_MOVE_EVERY:
                alive.append(b)
                continue

            b.move_timer = 0
            nx = int(b.x) + DX[b.direction]
            ny = int(b.y) + DY[b.direction]

            # Out of bounds or wall → despawn
            if not (0 <= nx < COLS and 0 <= ny < ROWS):
                continue
            if self.grid[ny][nx] == WALL:
                continue

            b.x, b.y = float(nx), float(ny)

            # Hit check
            hit = False
            for tank in [self.tank1, self.tank2]:
                if not tank.alive:
                    continue
                if b.owner_id == tank.player_id:
                    continue  # no friendly fire
                if int(b.x) == tank.x and int(b.y) == tank.y:
                    tank.health -= 1
                    hit = True
                    break

            if not hit:
                alive.append(b)

        self.bullets = alive

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

        self.done         = True
        self.result_timer = RESET_DELAY

    def new_episode(self):
        """Start next episode — grid is NOT reset (walls/consumed charges stay)."""
        self._spawn_tanks()
        self.bullets      = []
        self.ticks        = 0
        self.result_text  = ""
        self.result_timer = 0
        self.done         = False
        self.episode     += 1

    def full_reset(self):
        """Hard reset — map goes back to original, all stats cleared."""
        self.grid        = [row[:] for row in GRID_TEMPLATE]
        self.charge_tiles = list(CHARGE_TILES_TEMPLATE)
        self.score1  = self.score2  = 0
        self.kills1  = self.kills2  = 0
        self.deaths1 = self.deaths2 = 0
        self.episode = 1
        self._spawn_tanks()
        self.bullets      = []
        self.ticks        = 0
        self.result_text  = ""
        self.result_timer = 0
        self.done         = False


# ── Bot AI ─────────────────────────────────────────────────────────────────────
class RandomBot:
    def get_action(self, tank):
        r = random.random()
        if r < BOT_SHOOT_CHANCE and tank.ammo > 0:
            return 3
        elif r < BOT_SHOOT_CHANCE + BOT_TURN_CHANCE:
            return random.choice([0, 1])
        elif r < BOT_SHOOT_CHANCE + BOT_TURN_CHANCE + BOT_MOVE_CHANCE:
            return 2
        return 4


# ── Renderer helpers ───────────────────────────────────────────────────────────
def draw_arrow(surf, color, cx, cy, direction, size=10):
    angle = { UP: 90, RIGHT: 0, DOWN: 270, LEFT: 180 }[direction]
    rad   = math.radians(angle)
    pts   = []
    for da, dist in [(0, size), (140, size * 0.6), (-140, size * 0.6)]:
        a = rad + math.radians(da)
        pts.append((cx + math.cos(a) * dist, cy - math.sin(a) * dist))
    pygame.draw.polygon(surf, color, pts)


def draw_tank(surf, tank, tile, is_player):
    cx = tank.x * tile + tile // 2
    cy = tank.y * tile + tile // 2
    body_c = C_P1      if is_player else C_P2
    dark_c = C_P1_DARK if is_player else C_P2_DARK

    # Shadow
    shadow_surf = pygame.Surface((tile - 4, tile - 4), pygame.SRCALPHA)
    shadow_surf.fill((0, 0, 0, 80))
    surf.blit(shadow_surf, (cx - tile//2 + 3, cy - tile//2 + 3))

    # Body
    body_rect = pygame.Rect(cx - tile//2 + 1, cy - tile//2 + 1, tile - 2, tile - 2)
    pygame.draw.rect(surf, dark_c, body_rect, border_radius=4)
    pygame.draw.rect(surf, body_c, body_rect.inflate(-4, -4), border_radius=3)

    # Direction arrow
    draw_arrow(surf, (255, 255, 255), cx, cy, tank.direction, size=tile * 0.28)

    # Health pips
    pip_w   = 5
    pip_gap = 2
    total   = MAX_HEALTH * (pip_w + pip_gap) - pip_gap
    px      = cx - total // 2
    py      = cy + tile // 2 + 3
    for i in range(MAX_HEALTH):
        color = body_c if i < tank.health else (40, 40, 50)
        pygame.draw.rect(surf, color, (px + i * (pip_w + pip_gap), py, pip_w, 4))

    # Ammo pips (below health pips)
    py2 = py + 7
    for i in range(MAX_AMMO):
        color = C_CHARGE_GLOW if i < tank.ammo else (40, 40, 50)
        pygame.draw.rect(surf, color, (px + i * (pip_w + pip_gap), py2, pip_w, 4))

    # Charging indicator ring
    if tank.charge_progress > 0:
        frac = tank.charge_progress / CHARGE_TICKS
        pygame.draw.arc(surf, C_CHARGE_GLOW,
                        pygame.Rect(cx - tile//2, cy - tile//2, tile, tile),
                        0, frac * 2 * math.pi, 3)


def draw_bullet(surf, bullet, tile):
    cx = int(bullet.x * tile + tile // 2)
    cy = int(bullet.y * tile + tile // 2)
    color = C_BULLET_P1 if bullet.owner_id == 1 else C_BULLET_P2
    pygame.draw.circle(surf, color, (cx, cy), 5)
    pygame.draw.circle(surf, color, (cx, cy), 7, 1)


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
                # Lightning bolt symbol (simple lines)
                mx, my = c * tile + tile // 2, r * tile + tile // 2
                pts = [(mx, my - 8), (mx - 4, my), (mx + 1, my), (mx, my + 8), (mx + 4, my), (mx - 1, my)]
                pygame.draw.lines(surf, C_CHARGE_GLOW, False, pts, 2)
            else:
                pygame.draw.rect(surf, C_GRID, rect, 1)

    # Spawn zone tints
    for (sx, sy), col in [(SPAWN1, C_SPAWN_1), (SPAWN2, C_SPAWN_2)]:
        tint = pygame.Surface((tile, tile), pygame.SRCALPHA)
        tint.fill((*col, 80))
        surf.blit(tint, (sx * tile, sy * tile))

    # Bullets
    for b in game.bullets:
        draw_bullet(surf, b, tile)

    # Tanks
    if game.tank1.alive:
        draw_tank(surf, game.tank1, tile, is_player=True)
    if game.tank2.alive:
        draw_tank(surf, game.tank2, tile, is_player=False)


def draw_hud(surf, game, hud_rect, font_md, font_sm, font_xs):
    pygame.draw.rect(surf, C_HUD_BG, hud_rect)
    pygame.draw.line(surf, C_HUD_LINE,
                     (hud_rect.left, hud_rect.top),
                     (hud_rect.left, hud_rect.bottom), 2)

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

    # Player 1
    line("── PLAYER 1 (YOU) ──", C_P1, gap=4, font=font_sm)
    line(f"  Health   {'█' * game.tank1.health}{'░' * (MAX_HEALTH - game.tank1.health)}", C_P1)
    ammo_bar = '◆' * game.tank1.ammo + '◇' * (MAX_AMMO - game.tank1.ammo)
    line(f"  Ammo     {ammo_bar}", C_CHARGE_GLOW)
    chg = f"charging {game.tank1.charge_progress}/{CHARGE_TICKS}" if game.tank1.charge_progress > 0 else "—"
    line(f"  Charge   {chg}", C_TEXT_DIM)
    line(f"  Facing   {DIR_NAMES[game.tank1.direction]}", C_TEXT_SEC)
    line(f"  Cooldown {game.tank1.cooldown:>3}", C_TEXT_SEC, gap=10)

    # Bot
    line("── BOT (P2) ─────────", C_P2, gap=4, font=font_sm)
    line(f"  Health   {'█' * game.tank2.health}{'░' * (MAX_HEALTH - game.tank2.health)}", C_P2)
    ammo_bar2 = '◆' * game.tank2.ammo + '◇' * (MAX_AMMO - game.tank2.ammo)
    line(f"  Ammo     {ammo_bar2}", C_CHARGE_GLOW)
    line(f"  Facing   {DIR_NAMES[game.tank2.direction]}", C_TEXT_SEC, gap=10)

    sep()

    line(f"Episode  {game.episode:>5}", C_TEXT_SEC)
    line(f"Ticks    {game.ticks:>5}", C_TEXT_DIM)
    line(f"Bullets  {len(game.bullets):>5}", C_TEXT_DIM, gap=10)

    sep()

    line("SCORE", C_TEXT_PRI, gap=4, font=font_sm)
    line(f"  P1  W:{game.score1}  K:{game.kills1}  D:{game.deaths1}", C_P1)
    line(f"  Bot W:{game.score2}  K:{game.kills2}  D:{game.deaths2}", C_P2, gap=12)

    sep()

    line("CONTROLS", C_TEXT_PRI, gap=4, font=font_sm)
    line("  W       move forward", C_TEXT_DIM)
    line("  A / D   rotate (tap)", C_TEXT_DIM)
    line("  SPACE   shoot", C_TEXT_DIM)
    line("  R       FULL MAP RESET", C_TEXT_DIM)
    line("  ESC     quit", C_TEXT_DIM, gap=8)
    line("  ◆ = ammo  ◇ = empty", C_CHARGE_GLOW)
    line("  step on ⚡ 2 ticks", C_CHARGE_GLOW)
    line("  to refill ammo", C_CHARGE_GLOW)


def draw_result_overlay(surf, text, alpha_frac, font_lg, font_sm):
    overlay = pygame.Surface((ARENA_W, ARENA_H), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, int(180 * alpha_frac)))
    surf.blit(overlay, (0, 0))

    t1 = font_lg.render(text, True, (255, 255, 220))
    t2 = font_sm.render("Next round starting...", True, (160, 158, 150))
    cx, cy = ARENA_W // 2, ARENA_H // 2
    surf.blit(t1, (cx - t1.get_width() // 2, cy - t1.get_height()))
    surf.blit(t2, (cx - t2.get_width() // 2, cy + 8))


def draw_info_bar(surf, info_rect, font_xs):
    pygame.draw.rect(surf, C_HUD_BG, info_rect)
    pygame.draw.line(surf, C_HUD_LINE, info_rect.topleft, info_rect.topright, 1)
    tips = ("Phase 2A  |  Bullets: half speed  |  Ammo: 5 shots, refill on ⚡ charge tile  "
            "|  Map persists between rounds  |  R = full reset")
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
    hud_rect   = pygame.Rect(HUD_X, 0,      HUD_W, WIN_H - INFO_H)
    info_rect  = pygame.Rect(0,     INFO_Y, WIN_W, INFO_H)

    game = TankDebugGame()
    bot  = RandomBot()
    clock = pygame.time.Clock()

    running = True
    while running:
        # ── events ────────────────────────────────────────────────────────────
        # Default action this frame is STAY
        player_action = 4

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_r:
                    game.full_reset()
                # Rotate on single keypress — no spinning
                elif event.key == pygame.K_a:
                    player_action = 0   # rotate left
                elif event.key == pygame.K_d:
                    player_action = 1   # rotate right

        if not running:
            break

        # Held keys for move + shoot (natural feel)
        keys = pygame.key.get_pressed()
        if player_action == 4:   # don't override a rotate from KEYDOWN
            if keys[pygame.K_SPACE]:
                player_action = 3   # shoot
            elif keys[pygame.K_w]:
                player_action = 2   # move forward

        # ── game logic ────────────────────────────────────────────────────────
        if game.done:
            game.result_timer -= 1
            if game.result_timer <= 0:
                game.new_episode()
        else:
            bot_action = bot.get_action(game.tank2)
            game.step(player_action, bot_action)

        # ── render ────────────────────────────────────────────────────────────
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