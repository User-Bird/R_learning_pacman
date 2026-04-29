"""
main.py  ─  Phase 5: Combat Tank RL Trainer
════════════════════════════════════════════

Three training modes, no slider:

  WATCH    60 fps, every frame rendered.
           See exactly what the agents are doing.
           Good for demos and checking behaviour.

  FAST     Renders every 10th frame, no fps cap.
           Tanks visibly teleport, stays responsive.
           Good for watching training progress quickly.

  HEADLESS Minimises the window, calls pygame.event.pump()
           every 500 ticks to keep the OS happy.
           Pure training — as fast as Python can go.
           Stats panel updates when you restore the window.
           Safe on Linux / Fedora / Windows.
"""

import sys
import time

import numpy as np
import pygame

from game             import TankGame
from renderer         import draw_game
from rl.trainer       import Trainer
from rl.state_encoder import encode_state

# ── Layout ────────────────────────────────────────────────────────────────────
SW, SH       = 1920, 1080
PANEL_W      = 400
BOTTOM_H     = 100          # taller bar — holds 3 big mode buttons
GAP          = 3
GCOLS, GROWS = 3, 2
NUM_GAMES    = GCOLS * GROWS

GAME_AREA_W = SW - PANEL_W
GAME_AREA_H = SH - BOTTOM_H
CELL_W = (GAME_AREA_W - GAP * (GCOLS + 1)) // GCOLS
CELL_H = (GAME_AREA_H - GAP * (GROWS + 1)) // GROWS
TILE_SIZE   = 20

def cell_origin(idx):
    col = idx % GCOLS
    row = idx // GCOLS
    return GAP + col * (CELL_W + GAP), GAP + row * (CELL_H + GAP)

# ── Mode constants ────────────────────────────────────────────────────────────
MODE_WATCH    = "WATCH"
MODE_FAST     = "FAST"
MODE_HEADLESS = "HEADLESS"

# Ticks per frame for each mode
TICKS_WATCH    = 1          # 1 tick then draw
TICKS_FAST     = 10         # 10 ticks then draw
TICKS_HEADLESS = 500        # 500 ticks, then event.pump(), repeat — no draw

# How many fast-mode frames to skip rendering (render every Nth frame)
FAST_RENDER_EVERY = 10

# ── Palette ───────────────────────────────────────────────────────────────────
C_BG         = (12,  12,  16)
C_CELL_BG    = (20,  20,  26)
C_PANEL_BG   = (16,  16,  22)
C_PANEL_LINE = (40,  40,  55)
C_TEXT_PRI   = (210, 208, 200)
C_TEXT_SEC   = (130, 128, 118)
C_TEXT_DIM   = (65,  63,  58)

# Mode button colours  (inactive bg, inactive text, active bg, active text)
MODE_STYLE = {
    MODE_WATCH:    ((30, 50, 35),   (80, 160, 90),   (60, 180, 80),  (12, 12, 16)),
    MODE_FAST:     ((50, 45, 20),   (180, 150, 50),  (220, 180, 40), (12, 12, 16)),
    MODE_HEADLESS: ((40, 20, 50),   (150, 80, 200),  (160, 80, 240), (255, 255, 255)),
}

GAME_ACCENT = [
    (160, 140, 255),
    ( 72, 210, 168),
    ( 88, 168, 255),
    (255, 192,  72),
    (148, 214,  82),
    (255, 108,  88),
]


# ── GameSession ───────────────────────────────────────────────────────────────
class GameSession:
    def __init__(self, idx: int):
        self.idx      = idx
        self.game     = TankGame()
        self.trainer1 = Trainer()
        self.trainer2 = Trainer()
        self.states   = self.game.reset()
        self.ticks    = 0
        self.episodes = 1
        self.wins_p1  = 0
        self.wins_p2  = 0

    def step(self):
        enc1 = encode_state(self.states[0])
        enc2 = encode_state(self.states[1])

        a1 = int(self.trainer1.batch_act(enc1[None],
                  np.array([self.trainer1.epsilon]))[0])
        a2 = int(self.trainer2.batch_act(enc2[None],
                  np.array([self.trainer2.epsilon]))[0])

        next_states, rewards, done = self.game.step([a1, a2])
        self.ticks += 1

        nenc1 = encode_state(next_states[0])
        nenc2 = encode_state(next_states[1])

        self.trainer1.push_encoded(enc1, a1, rewards[0], nenc1, done)
        self.trainer2.push_encoded(enc2, a2, rewards[1], nenc2, done)

        self.states = next_states

        if done:
            if "TANK 1 WINS" in self.game.result_text:
                self.wins_p1 += 1
            elif "TANK 2 WINS" in self.game.result_text:
                self.wins_p2 += 1
            self.trainer1.on_episode_end()
            self.trainer2.on_episode_end()
            self.episodes += 1
            self.states = self.game.reset()


# ── Mode button ───────────────────────────────────────────────────────────────
class ModeButton:
    """One of the three mode buttons in the bottom bar."""
    W, H = 220, 60

    def __init__(self, mode: str, label: str, sublabel: str):
        self.mode     = mode
        self.label    = label
        self.sublabel = sublabel
        self.rect     = pygame.Rect(0, 0, self.W, self.H)

    def set_center(self, cx, cy):
        self.rect.center = (cx, cy)

    def hit(self, event) -> bool:
        return (event.type == pygame.MOUSEBUTTONDOWN
                and event.button == 1
                and self.rect.collidepoint(event.pos))

    def draw(self, surf, active: bool, font_md, font_xs):
        inactive_bg, inactive_tx, active_bg, active_tx = MODE_STYLE[self.mode]
        bg  = active_bg    if active else inactive_bg
        tx  = active_tx    if active else inactive_tx
        tx2 = active_tx    if active else C_TEXT_DIM

        pygame.draw.rect(surf, bg, self.rect, border_radius=8)
        if active:
            pygame.draw.rect(surf, tx, self.rect, 2, border_radius=8)

        t1 = font_md.render(self.label, True, tx)
        t2 = font_xs.render(self.sublabel, True, tx2)
        surf.blit(t1, (self.rect.centerx - t1.get_width() // 2,
                       self.rect.centery - t1.get_height() // 2 - 6))
        surf.blit(t2, (self.rect.centerx - t2.get_width() // 2,
                       self.rect.centery + t1.get_height() // 2 - 4))


# ── Stats panel ───────────────────────────────────────────────────────────────
class StatsPanel:
    LINE_H  = 20
    PAD_X   = 16
    PAD_TOP = 14

    def __init__(self):
        self._scroll = 0
        self._lines  = []
        self._hover  = False
        self._panel  = pygame.Rect(0, 0, 0, 0)

    def set_panel_rect(self, r):
        self._panel = r

    def rebuild(self, sessions, fps: float, tps: float, mode: str):
        lines = []
        def push(text, color=C_TEXT_SEC, indent=0):
            lines.append((text, color, indent))

        push("LIVE STATS", C_TEXT_PRI)
        push(f"FPS {fps:5.1f}     TPS {tps:,.0f}", C_TEXT_DIM)
        push(f"Mode: {mode}", C_TEXT_SEC)
        push("")

        for s in sessions:
            ac = GAME_ACCENT[s.idx]
            push(f"── GAME {s.idx + 1} ──────────────────", ac)
            push(f"Episode  {s.episodes:>7}",                      C_TEXT_SEC, 4)
            push(f"P1 Wins  {s.wins_p1:>7}",                      C_TEXT_SEC, 4)
            push(f"P2 Wins  {s.wins_p2:>7}",                      C_TEXT_SEC, 4)
            push(f"Ticks    {s.ticks:>7}",                         C_TEXT_DIM, 4)
            e1 = s.trainer1.epsilon
            e2 = s.trainer2.epsilon
            push(f"ε  P1:{e1:.3f}  P2:{e2:.3f}",                 C_TEXT_SEC, 4)
            b1 = len(s.trainer1.buffer)
            b2 = len(s.trainer2.buffer)
            push(f"Buf  P1:{b1:>5}  P2:{b2:>5}",                 C_TEXT_DIM, 4)
            l1 = s.trainer1.last_loss
            l2 = s.trainer2.last_loss
            lc = C_TEXT_PRI if (l1 > 0 or l2 > 0) else C_TEXT_DIM
            push(f"Loss P1:{l1:6.3f}  P2:{l2:6.3f}",             lc,         4)
            push("")

        self._lines = lines

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self._hover = self._panel.collidepoint(event.pos)
        if event.type == pygame.MOUSEWHEEL and self._hover:
            vis = (self._panel.height - self.PAD_TOP) // self.LINE_H
            self._scroll = max(0, min(max(0, len(self._lines) - vis),
                                      self._scroll - event.y * 3))

    def draw(self, surf, font_xs):
        r = self._panel
        pygame.draw.rect(surf, C_PANEL_BG, r)
        pygame.draw.line(surf, C_PANEL_LINE, r.topleft, (r.left, r.bottom), 1)

        clip = surf.get_clip()
        surf.set_clip(r.inflate(-2, -2))
        y0 = r.top + self.PAD_TOP - self._scroll * self.LINE_H
        for text, color, indent in self._lines:
            if y0 + self.LINE_H < r.top:
                y0 += self.LINE_H; continue
            if y0 > r.bottom:
                break
            if text:
                t = font_xs.render(text, True, color)
                surf.blit(t, (r.left + self.PAD_X + indent, y0))
            y0 += self.LINE_H
        surf.set_clip(clip)

        vis = (r.height - self.PAD_TOP) // self.LINE_H
        if len(self._lines) > vis:
            ratio  = vis / len(self._lines)
            bar_h  = max(30, int(r.height * ratio))
            max_sc = len(self._lines) - vis
            bar_y  = r.top + int((r.height - bar_h) *
                                  (self._scroll / max(1, max_sc)))
            pygame.draw.rect(surf, C_PANEL_LINE,
                             (r.right - 5, bar_y, 4, bar_h), border_radius=2)


# ── Headless overlay ──────────────────────────────────────────────────────────
def draw_headless_cells(screen, sessions, font_md, font_xs):
    """Replace game cells with dark stat cards — drawn even after restore."""
    for i, s in enumerate(sessions):
        ox, oy = cell_origin(i)
        ac = GAME_ACCENT[i]
        pygame.draw.rect(screen, (8, 8, 12), (ox, oy, CELL_W, CELL_H))
        pygame.draw.rect(screen, ac,          (ox, oy, CELL_W, CELL_H), 1)

        lines = [
            (f"GAME {i + 1}",                       font_md, ac),
            ("HEADLESS  —  TRAINING FAST",           font_xs, (40, 200, 90)),
            ("",                                      font_xs, C_TEXT_DIM),
            (f"Episodes   {s.episodes:,}",            font_xs, C_TEXT_SEC),
            (f"Ticks      {s.ticks:,}",               font_xs, C_TEXT_DIM),
            (f"P1  {s.wins_p1:,}   —   {s.wins_p2:,}  P2", font_xs, C_TEXT_SEC),
            (f"ε   {s.trainer1.epsilon:.4f}",         font_xs, C_TEXT_DIM),
            (f"Loss  {s.trainer1.last_loss:.4f}",     font_xs, C_TEXT_DIM),
        ]
        total_h = sum(f.get_height() + 5 for _, f, _ in lines)
        y = oy + CELL_H // 2 - total_h // 2
        for text, font, color in lines:
            t = font.render(text, True, color)
            screen.blit(t, (ox + CELL_W // 2 - t.get_width() // 2, y))
            y += t.get_height() + 5


# ── Bottom bar ────────────────────────────────────────────────────────────────
def draw_bottom_bar(screen, buttons, mode, font_md, font_xs, bar_rect):
    pygame.draw.rect(screen, C_PANEL_BG, bar_rect)
    pygame.draw.line(screen, C_PANEL_LINE,
                     bar_rect.topleft, bar_rect.topright, 1)
    for btn in buttons:
        btn.draw(screen, btn.mode == mode, font_md, font_xs)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    pygame.init()
    pygame.display.set_caption("Combat Tank RL — Phase 5")
    screen = pygame.display.set_mode(
        (SW, SH), pygame.FULLSCREEN | pygame.HWSURFACE | pygame.DOUBLEBUF
    )

    font_md = pygame.font.SysFont("consolas", 14, bold=True)
    font_xs = pygame.font.SysFont("consolas", 12)

    # Pre-allocate surfaces
    cells      = [pygame.Surface((CELL_W, CELL_H)) for _ in range(NUM_GAMES)]
    arena_surf = pygame.Surface((25 * TILE_SIZE, 19 * TILE_SIZE))

    panel_rect  = pygame.Rect(GAME_AREA_W, 0, PANEL_W, SH - BOTTOM_H)
    bottom_rect = pygame.Rect(0, SH - BOTTOM_H, SW, BOTTOM_H)

    # ── Mode buttons ──────────────────────────────────────────────────────────
    buttons = [
        ModeButton(MODE_WATCH,    "▶  WATCH",    "normal speed · 60 fps"),
        ModeButton(MODE_FAST,     "▶▶  FAST",    "10× speed · tanks teleport"),
        ModeButton(MODE_HEADLESS, "⚡  HEADLESS", "training only · max speed"),
    ]
    bar_cx   = (SW - PANEL_W) // 2
    spacing  = ModeButton.W + 30
    starts   = bar_cx - spacing
    for i, btn in enumerate(buttons):
        btn.set_center(starts + i * spacing, bottom_rect.centery)

    # ── Sessions + panel ──────────────────────────────────────────────────────
    sessions = [GameSession(i) for i in range(NUM_GAMES)]
    panel    = StatsPanel()
    panel.set_panel_rect(panel_rect)

    clock   = pygame.time.Clock()
    mode    = MODE_WATCH
    running = True

    # TPS tracking
    tps_ticks   = 0
    tps_last_t  = time.perf_counter()
    tps_display = 0.0
    fast_frame  = 0          # frame counter for FAST render-skip

    # Whether we are currently minimised in headless
    minimised   = False

    while running:

        # ── HEADLESS inner loop ───────────────────────────────────────────────
        # Runs TICKS_HEADLESS ticks then comes back to the outer loop
        # for event polling. This keeps the OS happy on all platforms.
        if mode == MODE_HEADLESS:
            for _ in range(TICKS_HEADLESS):
                for s in sessions:
                    s.step()
            tps_ticks += TICKS_HEADLESS

            # Keep OS event queue alive — mandatory on Linux
            pygame.event.pump()

            # Measure TPS
            now = time.perf_counter()
            if now - tps_last_t >= 1.0:
                tps_display = tps_ticks / (now - tps_last_t)
                tps_ticks   = 0
                tps_last_t  = now

            # Check if user wants to leave headless (ESC or any key)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    else:
                        # Any other key → restore and switch to WATCH
                        mode = MODE_WATCH
                        if minimised:
                            pygame.display.toggle_fullscreen()
                            pygame.display.toggle_fullscreen()
                            minimised = False
                for btn in buttons:
                    if btn.hit(event):
                        mode = btn.mode

            if not running:
                break

            # Draw stats onto the (possibly minimised) window
            # so when user restores it they see current numbers
            screen.fill(C_BG)
            draw_headless_cells(screen, sessions, font_md, font_xs)
            draw_bottom_bar(screen, buttons, mode, font_md, font_xs, bottom_rect)
            panel.rebuild(sessions, 0.0, tps_display, mode)
            panel.draw(screen, font_xs)
            pygame.display.flip()

            continue   # skip the normal event + render path below

        # ── Normal / Fast event handling ──────────────────────────────────────
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False
            panel.handle_event(event)
            for btn in buttons:
                if btn.hit(event):
                    prev_mode = mode
                    mode      = btn.mode
                    # Entering headless — minimise window
                    if mode == MODE_HEADLESS:
                        pygame.display.iconify()
                        minimised   = True
                        tps_ticks   = 0
                        tps_last_t  = time.perf_counter()

        if not running:
            break

        # ── Game logic ────────────────────────────────────────────────────────
        ticks_this_frame = TICKS_WATCH if mode == MODE_WATCH else TICKS_FAST
        for _ in range(ticks_this_frame):
            for s in sessions:
                s.step()
        tps_ticks += ticks_this_frame

        now = time.perf_counter()
        if now - tps_last_t >= 1.0:
            tps_display = tps_ticks / (now - tps_last_t)
            tps_ticks   = 0
            tps_last_t  = now

        # ── Render ────────────────────────────────────────────────────────────
        fast_frame += 1
        skip_render = (mode == MODE_FAST and fast_frame % FAST_RENDER_EVERY != 0)

        if not skip_render:
            screen.fill(C_BG)

            for i, (s, surf) in enumerate(zip(sessions, cells)):
                surf.fill(C_CELL_BG)
                arena_surf.fill((18, 20, 26))
                draw_game(arena_surf, s.game, tile=TILE_SIZE)
                ox_a = (CELL_W - arena_surf.get_width())  // 2
                oy_a = (CELL_H - arena_surf.get_height()) // 2
                surf.blit(arena_surf, (ox_a, oy_a))

                ac = GAME_ACCENT[i]
                pygame.draw.rect(surf, ac, surf.get_rect(), 1)

                lbl = font_md.render(f"GAME {i + 1}", True, ac)
                surf.blit(lbl, (10, 8))

                info = (f"ep {s.episodes}  |  "
                        f"P1 {s.wins_p1} — {s.wins_p2} P2  |  "
                        f"ε {s.trainer1.epsilon:.3f}")
                sc = font_xs.render(info, True, C_TEXT_DIM)
                surf.blit(sc, (10, surf.get_height() - sc.get_height() - 8))

                ox, oy = cell_origin(i)
                screen.blit(surf, (ox, oy))

            draw_bottom_bar(screen, buttons, mode, font_md, font_xs, bottom_rect)
            panel.rebuild(sessions, clock.get_fps(), tps_display, mode)
            panel.draw(screen, font_xs)
            pygame.display.flip()

        if mode == MODE_WATCH:
            clock.tick(60)

    pygame.quit()
    sys.exit(0)


if __name__ == "__main__":
    main()