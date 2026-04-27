"""
game_2a.py  ─  Phase 2A: Standalone Combat Tank Debug Window
─────────────────────────────────────────────────────────────
Player 1 (GREEN):  WASD to move/rotate  |  SPACE to shoot
Player 2 (RED):    Random bot — moves + shoots randomly
Close: ESC or window X

Purpose: test the raw game mechanics in isolation before wiring
into the 6-cell main.py layout.
"""

import pygame
import sys
import random
import math

# ── Arena config ──────────────────────────────────────────────────────────────
TILE        = 32          # px per tile
COLS        = 25          # arena width in tiles
ROWS        = 19          # arena height in tiles
WIN_W       = COLS * TILE + 320   # game area + right HUD panel
WIN_H       = ROWS * TILE + 80   # game area + bottom info bar

ARENA_W     = COLS * TILE   # 800 px
ARENA_H     = ROWS * TILE   # 608 px
HUD_X       = ARENA_W       # right panel starts here
HUD_W       = 320
INFO_Y      = ARENA_H       # bottom bar starts here
INFO_H      = 80

# ── Tile types ─────────────────────────────────────────────────────────────────
EMPTY = 0
WALL  = 1

# ── Directions (index into DX/DY) ─────────────────────────────────────────────
UP    = 0
RIGHT = 1
DOWN  = 2
LEFT  = 3

DX = { UP: 0, RIGHT: 1, DOWN: 0, LEFT: -1 }
DY = { UP: -1, RIGHT: 0, DOWN: 1, LEFT:  0 }

DIR_NAMES = { UP: "UP", RIGHT: "RIGHT", DOWN: "DOWN", LEFT: "LEFT" }

# ── Palette ────────────────────────────────────────────────────────────────────
C_BG          = (10,  12,  16)
C_ARENA_BG    = (18,  20,  26)
C_WALL        = (44,  52,  70)
C_WALL_BORDER = (60,  72,  98)
C_HUD_BG      = (14,  16,  22)
C_HUD_LINE    = (38,  42,  58)
C_TEXT_PRI    = (210, 208, 200)
C_TEXT_SEC    = (130, 128, 118)
C_TEXT_DIM    = (60,  58,  54)
C_P1          = (80,  220, 120)   # green
C_P1_DARK     = (40,  140,  70)
C_P2          = (230,  80,  80)   # red
C_P2_DARK     = (160,  40,  40)
C_BULLET_P1   = (160, 255, 180)
C_BULLET_P2   = (255, 160, 140)
C_GRID        = (22,  26,  34)
C_SPAWN_1     = (40,  80,  50)
C_SPAWN_2     = (80,  40,  40)
C_WIN_OVERLAY = (0,   0,   0)

# ── Tank & bullet stats ────────────────────────────────────────────────────────
MAX_HEALTH      = 5
SHOOT_COOLDOWN  = 18    # ticks between shots
BULLET_SPEED    = 1     # tiles per tick (1 = moves 1 tile each tick)
BULLET_LIFETIME = 40    # ticks before auto-despawn
BOT_MOVE_CHANCE = 0.05  # per tick: random bot chance to change direction or move
BOT_SHOOT_CHANCE= 0.04  # per tick: random bot chance to shoot
BOT_TURN_CHANCE = 0.06  # per tick: random bot chance to turn

RESET_DELAY     = 120   # ticks to show result before resetting

# ── Map ────────────────────────────────────────────────────────────────────────
# 19 rows × 25 cols. '#'=wall, ' '=empty, '1'=P1 spawn, '2'=P2 spawn
MAP_STR = [
    "#########################",
    "#  1       #       #   #",
    "#  ###   # # #   ###   #",
    "#    #   #   #   #     #",
    "# ##     #####     ## ##",
    "#  #   #       #   #   #",
    "##   ###  # #  ###   ###",
    "#         # #         ##",
    "# ## ## ##   ## ## ## ##",
    "#         # #         ##",
    "##   ###  # #  ###   ###",
    "#  #   #       #   #   #",
    "# ##     #####     ## ##",
    "#    #   #   #   #     #",
    "#  ###   # # #   ###   #",
    "#     #       #     #  #",
    "#   #   # #####   #    #",
    "#   #       #       2  #",
    "#########################",
]


def parse_map(map_str):
    grid = []
    spawn1 = spawn2 = None
    for r, line in enumerate(map_str):
        row = []
        # Force the loop to run exactly COLS (25) times
        for c in range(COLS):
            # If the line is too short, pretend there's an empty space (' ')
            ch = line[c] if c < len(line) else ' '

            if ch == '#':
                row.append(WALL)
            elif ch == '1':
                row.append(EMPTY)
                spawn1 = (c, r)
            elif ch == '2':
                row.append(EMPTY)
                spawn2 = (c, r)
            else:
                row.append(EMPTY)
        grid.append(row)
    return grid, spawn1, spawn2

GRID_TEMPLATE, SPAWN1, SPAWN2 = parse_map(MAP_STR)

# ── Data classes ───────────────────────────────────────────────────────────────
class Tank:
    def __init__(self, x, y, direction, player_id):
        self.x          = x
        self.y          = y
        self.direction  = direction
        self.health     = MAX_HEALTH
        self.cooldown   = 0
        self.player_id  = player_id   # 1 or 2
        self.kills      = 0
        self.deaths     = 0

    @property
    def alive(self):
        return self.health > 0

    def can_shoot(self):
        return self.cooldown <= 0

class Bullet:
    def __init__(self, x, y, direction, owner_id):
        self.x          = float(x)
        self.y          = float(y)
        self.direction  = direction
        self.owner_id   = owner_id
        self.lifetime   = BULLET_LIFETIME
        # sub-tile progress for smooth movement
        self._frac_x    = float(x)
        self._frac_y    = float(y)

# ── Game state ─────────────────────────────────────────────────────────────────
class TankDebugGame:
    def __init__(self):
        self.grid    = [row[:] for row in GRID_TEMPLATE]
        self.tank1   = Tank(SPAWN1[0], SPAWN1[1], UP,   1)
        self.tank2   = Tank(SPAWN2[0], SPAWN2[1], DOWN, 2)
        self.bullets = []
        self.ticks   = 0
        self.episode = 1
        self.result_text = ""
        self.result_timer = 0  # countdown ticks after round ends
        self.done    = False
        self.score1  = 0   # cumulative across episodes
        self.score2  = 0

    # ── movement ──────────────────────────────────────────────────────────────
    def is_walkable(self, x, y):
        if x < 0 or x >= COLS or y < 0 or y >= ROWS:
            return False
        return self.grid[y][x] == EMPTY

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
        # Don't spawn bullet inside a wall
        if not (0 <= bx < COLS and 0 <= by < ROWS):
            return
        self.bullets.append(Bullet(bx, by, tank.direction, tank.player_id))
        tank.cooldown = SHOOT_COOLDOWN

    # ── step ──────────────────────────────────────────────────────────────────
    def step(self, action1, action2):
        """
        Actions: 0=rotate_left  1=rotate_right  2=move_forward  3=shoot  4=stay
        """
        if self.done:
            return

        self.ticks += 1

        # Apply actions
        self._apply_action(self.tank1, action1)
        self._apply_action(self.tank2, action2)

        # Tick cooldowns
        if self.tank1.cooldown > 0: self.tank1.cooldown -= 1
        if self.tank2.cooldown > 0: self.tank2.cooldown -= 1

        # Move bullets + collision
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
        # 4 = stay, nothing

    def _update_bullets(self):
        alive_bullets = []
        for b in self.bullets:
            b.lifetime -= 1
            if b.lifetime <= 0:
                continue

            # Move bullet one tile
            nx = b.x + DX[b.direction]
            ny = b.y + DY[b.direction]

            # Out of bounds or hit wall → despawn
            if not (0 <= nx < COLS and 0 <= ny < ROWS):
                continue
            if self.grid[int(ny)][int(nx)] == WALL:
                continue

            b.x, b.y = nx, ny

            # Hit a tank?
            hit = False
            for tank in [self.tank1, self.tank2]:
                if not tank.alive:
                    continue
                if b.owner_id == tank.player_id:
                    continue   # no friendly fire (same owner)
                if int(b.x) == tank.x and int(b.y) == tank.y:
                    tank.health -= 1
                    hit = True
                    break

            if not hit:
                alive_bullets.append(b)

        self.bullets = alive_bullets

    def _check_done(self):
        t1_dead = not self.tank1.alive
        t2_dead = not self.tank2.alive
        if t1_dead or t2_dead:
            if t1_dead and t2_dead:
                self.result_text = "DRAW!"
            elif t2_dead:
                self.result_text = "PLAYER 1 WINS!"
                self.score1 += 1
                self.tank1.kills += 1
                self.tank2.deaths += 1
            else:
                self.result_text = "BOT WINS!"
                self.score2 += 1
                self.tank2.kills += 1
                self.tank1.deaths += 1
            self.done = True
            self.result_timer = RESET_DELAY

    def reset(self):
        self.grid    = [row[:] for row in GRID_TEMPLATE]
        self.tank1   = Tank(SPAWN1[0], SPAWN1[1], UP,   1)
        self.tank2   = Tank(SPAWN2[0], SPAWN2[1], DOWN, 2)
        # Carry over kills/deaths
        self.tank1.kills  = self.tank1.kills if hasattr(self.tank1, 'kills') else 0
        self.tank2.kills  = self.tank2.kills if hasattr(self.tank2, 'kills') else 0
        self.bullets = []
        self.ticks   = 0
        self.episode += 1
        self.result_text  = ""
        self.result_timer = 0
        self.done    = False


# ── Bot AI ─────────────────────────────────────────────────────────────────────
class RandomBot:
    """Moves and shoots randomly."""
    def __init__(self):
        self._queued_action = 4  # stay

    def get_action(self):
        r = random.random()
        if r < BOT_SHOOT_CHANCE:
            return 3   # shoot
        elif r < BOT_SHOOT_CHANCE + BOT_TURN_CHANCE:
            return random.choice([0, 1])  # turn
        elif r < BOT_SHOOT_CHANCE + BOT_TURN_CHANCE + BOT_MOVE_CHANCE:
            return 2   # move
        return 4  # stay


# ── Renderer ───────────────────────────────────────────────────────────────────
def draw_arrow(surf, color, cx, cy, direction, size=10):
    """Draw a directional arrow triangle indicating tank facing."""
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
    body_c  = C_P1      if is_player else C_P2
    dark_c  = C_P1_DARK if is_player else C_P2_DARK

    # Shadow
    shadow_rect = pygame.Rect(cx - tile//2 + 3, cy - tile//2 + 3, tile - 4, tile - 4)
    shadow_surf = pygame.Surface((tile - 4, tile - 4), pygame.SRCALPHA)
    shadow_surf.fill((0, 0, 0, 80))
    surf.blit(shadow_surf, shadow_rect.topleft)

    # Body
    body_rect = pygame.Rect(cx - tile//2 + 1, cy - tile//2 + 1, tile - 2, tile - 2)
    pygame.draw.rect(surf, dark_c, body_rect, border_radius=4)
    pygame.draw.rect(surf, body_c, body_rect.inflate(-4, -4), border_radius=3)

    # Direction arrow
    draw_arrow(surf, (255, 255, 255), cx, cy, tank.direction, size=tile * 0.28)

    # Health pips below tank
    pip_w = 5
    pip_gap = 2
    total_pip_w = MAX_HEALTH * (pip_w + pip_gap) - pip_gap
    pip_x_start = cx - total_pip_w // 2
    pip_y = cy + tile // 2 + 3
    for i in range(MAX_HEALTH):
        color = body_c if i < tank.health else (40, 40, 50)
        pygame.draw.rect(surf, color, (pip_x_start + i * (pip_w + pip_gap), pip_y, pip_w, 4))

def draw_bullet(surf, bullet, tile):
    cx = int(bullet.x * tile + tile // 2)
    cy = int(bullet.y * tile + tile // 2)
    color = C_BULLET_P1 if bullet.owner_id == 1 else C_BULLET_P2
    pygame.draw.circle(surf, color, (cx, cy), 5)
    # glow ring
    pygame.draw.circle(surf, color, (cx, cy), 7, 1)

def draw_arena(surf, game, font_sm, font_xs, tile):
    surf.fill(C_ARENA_BG)

    # Grid lines (subtle)
    for r in range(ROWS):
        for c in range(COLS):
            rect = pygame.Rect(c * tile, r * tile, tile, tile)
            pygame.draw.rect(surf, C_GRID, rect, 1)

    # Spawn zone tint
    for (sx, sy), col in [(SPAWN1, C_SPAWN_1), (SPAWN2, C_SPAWN_2)]:
        tint = pygame.Surface((tile, tile), pygame.SRCALPHA)
        tint.fill((*col, 80))
        surf.blit(tint, (sx * tile, sy * tile))

    # Walls
    for r in range(ROWS):
        for c in range(COLS):
            if game.grid[r][c] == WALL:
                rect = pygame.Rect(c * tile, r * tile, tile, tile)
                pygame.draw.rect(surf, C_WALL, rect)
                pygame.draw.rect(surf, C_WALL_BORDER, rect, 1)

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
    line(f"  Health  {'█' * game.tank1.health}{'░' * (MAX_HEALTH - game.tank1.health)}", C_P1)
    line(f"  Facing  {DIR_NAMES[game.tank1.direction]}", C_TEXT_SEC)
    line(f"  Cooldown {game.tank1.cooldown:>3}", C_TEXT_SEC)
    line(f"  Kills   {game.tank1.kills:>3}", C_TEXT_SEC, gap=10)

    # Player 2
    line("── BOT (P2) ─────────", C_P2, gap=4, font=font_sm)
    line(f"  Health  {'█' * game.tank2.health}{'░' * (MAX_HEALTH - game.tank2.health)}", C_P2)
    line(f"  Facing  {DIR_NAMES[game.tank2.direction]}", C_TEXT_SEC)
    line(f"  Kills   {game.tank2.kills:>3}", C_TEXT_SEC, gap=10)

    sep()

    line(f"Episode   {game.episode:>5}", C_TEXT_SEC)
    line(f"Ticks     {game.ticks:>5}", C_TEXT_DIM)
    line(f"Bullets   {len(game.bullets):>5}", C_TEXT_DIM, gap=10)

    sep()

    line("SCORE", C_TEXT_PRI, gap=4, font=font_sm)
    line(f"  Player 1   {game.score1:>4}", C_P1)
    line(f"  Bot        {game.score2:>4}", C_P2, gap=12)

    sep()

    line("CONTROLS", C_TEXT_PRI, gap=4, font=font_sm)
    line("  W/S   move fwd / backward*", C_TEXT_DIM)
    line("  A/D   rotate left / right", C_TEXT_DIM)
    line("  SPACE shoot", C_TEXT_DIM)
    line("  R     force reset", C_TEXT_DIM)
    line("  ESC   quit", C_TEXT_DIM, gap=4)
    line("  *tank only moves forward;", C_TEXT_DIM)
    line("   S rotates 180°", C_TEXT_DIM)

def draw_result_overlay(surf, text, alpha_frac, font_lg, font_sm):
    """Translucent centered result banner."""
    overlay = pygame.Surface((ARENA_W, ARENA_H), pygame.SRCALPHA)
    a = int(180 * alpha_frac)
    overlay.fill((0, 0, 0, a))
    surf.blit(overlay, (0, 0))

    t1 = font_lg.render(text, True, (255, 255, 220))
    t2 = font_sm.render("Next round starting...", True, (160, 158, 150))
    cx, cy = ARENA_W // 2, ARENA_H // 2
    surf.blit(t1, (cx - t1.get_width() // 2, cy - t1.get_height()))
    surf.blit(t2, (cx - t2.get_width() // 2, cy + 8))

def draw_info_bar(surf, info_rect, font_xs):
    pygame.draw.rect(surf, C_HUD_BG, info_rect)
    pygame.draw.line(surf, C_HUD_LINE,
                     info_rect.topleft, info_rect.topright, 1)
    tips = "Phase 2A — standalone debug  |  Confirm: movement, shooting, collision, win/loss all work correctly before Phase 2B"
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

    # Arena surface (blitted to screen at 0,0)
    arena_surf = pygame.Surface((ARENA_W, ARENA_H))

    hud_rect  = pygame.Rect(HUD_X, 0, HUD_W, WIN_H - INFO_H)
    info_rect = pygame.Rect(0,     INFO_Y, WIN_W, INFO_H)

    game = TankDebugGame()
    bot  = RandomBot()

    clock = pygame.time.Clock()

    # Player action state — held-key style
    player_action = 4  # stay by default

    running = True
    while running:
        # ── events ────────────────────────────────────────────────────────────
        player_action = 4  # reset each frame to STAY
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_r:
                    game.reset()

        if not running:
            break

        # Read held keys → one action per frame (priority: shoot > move > rotate)
        keys = pygame.key.get_pressed()
        if keys[pygame.K_SPACE]:
            player_action = 3   # shoot
        elif keys[pygame.K_w]:
            player_action = 2   # move forward
        elif keys[pygame.K_s]:
            # "reverse" = rotate 180: two right turns queued — simplified: just rotate right
            player_action = 1   # rotate right (press twice to fully reverse)
        elif keys[pygame.K_a]:
            player_action = 0   # rotate left
        elif keys[pygame.K_d]:
            player_action = 1   # rotate right

        # ── game logic ────────────────────────────────────────────────────────
        if game.done:
            game.result_timer -= 1
            if game.result_timer <= 0:
                # Carry kills/deaths over manually
                k1, d1 = game.tank1.kills, game.tank1.deaths
                k2, d2 = game.tank2.kills, game.tank2.deaths
                s1, s2 = game.score1, game.score2
                ep      = game.episode
                game.reset()
                game.tank1.kills, game.tank1.deaths = k1, d1
                game.tank2.kills, game.tank2.deaths = k2, d2
                game.score1, game.score2 = s1, s2
                game.episode = ep
        else:
            bot_action = bot.get_action()
            game.step(player_action, bot_action)

        # ── render ────────────────────────────────────────────────────────────
        screen.fill(C_BG)

        draw_arena(arena_surf, game, font_sm, font_xs, TILE)
        screen.blit(arena_surf, (0, 0))

        # Result overlay
        if game.done and game.result_text:
            alpha_frac = min(1.0, (RESET_DELAY - game.result_timer) / 20)
            draw_result_overlay(screen, game.result_text, alpha_frac, font_lg, font_sm)

        draw_hud(screen, game, hud_rect, font_md, font_sm, font_xs)
        draw_info_bar(screen, info_rect, font_xs)

        pygame.display.flip()
        clock.tick(60)  # 60 fps cap — human-speed debug window

    pygame.quit()
    sys.exit(0)

if __name__ == "__main__":
    main()