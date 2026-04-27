"""
main.py  ─  Phase 1: window layout + dummy test
─────────────────────────────────────────────────
Confirmation test: 6 moving yellow dots across sub-surfaces,
right scrollable stats panel, bottom updates-per-frame slider.
Close window (X or ESC) kills everything cleanly.
"""

import pygame
import sys
import math

# ── Layout ────────────────────────────────────────────────────────────────────
SW, SH     = 1920, 1080        # target resolution
PANEL_W    = 400               # right stats panel
BOTTOM_H   = 72                # bottom slider bar
GAP        = 3                 # px gap between cells
COLS, ROWS = 3, 2
NUM_GAMES  = COLS * ROWS

GAME_AREA_W = SW - PANEL_W                            # 1520
GAME_AREA_H = SH - BOTTOM_H                          # 1008
CELL_W = (GAME_AREA_W - GAP * (COLS + 1)) // COLS    # 502
CELL_H = (GAME_AREA_H - GAP * (ROWS + 1)) // ROWS    # 501


def cell_origin(idx: int) -> tuple[int, int]:
    """Top-left pixel of sub-surface idx on the main screen."""
    col = idx % COLS
    row = idx // COLS
    x   = GAP + col * (CELL_W + GAP)
    y   = GAP + row * (CELL_H + GAP)
    return x, y


# ── Palette ───────────────────────────────────────────────────────────────────
C_BG          = ( 12,  12,  16)
C_CELL_BG     = ( 20,  20,  26)
C_PANEL_BG    = ( 16,  16,  22)
C_PANEL_LINE  = ( 40,  40,  55)
C_BORDER      = ( 42,  42,  56)
C_SLIDER_RAIL = ( 35,  35,  48)
C_SLIDER_FILL = ( 72, 196, 138)
C_SLIDER_KNOB = (210, 250, 235)
C_TEXT_PRI    = (210, 208, 200)
C_TEXT_SEC    = (130, 128, 118)
C_TEXT_DIM    = ( 65,  63,  58)
C_LABEL_BRIGHT= (255, 255, 255)

GAME_ACCENT = [          # one accent per game window
    (160, 140, 255),     # 0  purple
    ( 72, 210, 168),     # 1  teal
    ( 88, 168, 255),     # 2  blue
    (255, 192,  72),     # 3  amber
    (148, 214,  82),     # 4  green
    (255, 108,  88),     # 5  coral
]

UPF_MIN, UPF_MAX = 1, 1000   # updates-per-frame range


# ── Dummy game state (replaced by real PacmanGame in phase 2) ─────────────────
class DummyGame:
    """Moving dot that bounces inside a CELL_W × CELL_H box."""
    def __init__(self, idx: int):
        self.idx     = idx
        self.x       = CELL_W  / 2.0
        self.y       = CELL_H  / 2.0
        self.vx      = 1.8 + idx * 0.4
        self.vy      = 1.3 + idx * 0.3
        self.ticks   = 0
        self.episodes= 0
        self.score   = 0

    def step(self):
        self.x  += self.vx
        self.y  += self.vy
        self.ticks += 1
        self.score += 1
        if self.x <= 10 or self.x >= CELL_W - 10:
            self.vx *= -1
        if self.y <= 10 or self.y >= CELL_H - 10:
            self.vy *= -1
        if self.ticks % 400 == 0:
            self.episodes += 1


# ── Slider helper ─────────────────────────────────────────────────────────────
class Slider:
    TRACK_H   = 6
    KNOB_R    = 11
    PAD_X     = 180    # horizontal padding inside the bottom bar

    def __init__(self):
        self.value   = 1      # current UPF
        self._drag   = False
        self._track  = pygame.Rect(0, 0, 0, 0)   # set in draw()

    @property
    def upf(self) -> int:
        return int(self.value)

    def _val_to_x(self) -> int:
        t = (math.log(self.value) - math.log(UPF_MIN)) / \
            (math.log(UPF_MAX) - math.log(UPF_MIN))
        return int(self._track.left + t * self._track.width)

    def _x_to_val(self, x: int) -> float:
        t = max(0.0, min(1.0, (x - self._track.left) / self._track.width))
        return math.exp(
            math.log(UPF_MIN) + t * (math.log(UPF_MAX) - math.log(UPF_MIN))
        )

    def handle_event(self, event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            kx = self._val_to_x()
            ky = self._track.centery
            if math.hypot(event.pos[0] - kx, event.pos[1] - ky) <= self.KNOB_R + 4:
                self._drag = True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._drag = False
        elif event.type == pygame.MOUSEMOTION and self._drag:
            self.value = max(UPF_MIN, min(UPF_MAX, self._x_to_val(event.pos[0])))

    def draw(self, surf: pygame.Surface, bar_rect: pygame.Rect,
             font_sm, font_xs) -> None:
        # build track rect (log-scaled slider)
        tx = bar_rect.left + self.PAD_X
        ty = bar_rect.centery
        tw = bar_rect.width - self.PAD_X * 2
        self._track = pygame.Rect(tx, ty - self.TRACK_H // 2, tw, self.TRACK_H)

        # label left
        lbl = font_sm.render("TICK SPEED", True, C_TEXT_DIM)
        surf.blit(lbl, (bar_rect.left + 20,
                        bar_rect.centery - lbl.get_height() // 2))

        # rail
        pygame.draw.rect(surf, C_SLIDER_RAIL, self._track, border_radius=3)

        # filled portion
        kx   = self._val_to_x()
        fill = pygame.Rect(self._track.left, self._track.top,
                           kx - self._track.left, self.TRACK_H)
        pygame.draw.rect(surf, C_SLIDER_FILL, fill, border_radius=3)

        # knob
        pygame.draw.circle(surf, C_SLIDER_KNOB, (kx, ty), self.KNOB_R)
        pygame.draw.circle(surf, C_SLIDER_FILL, (kx, ty), self.KNOB_R - 3)

        # value label right
        upf_lbl = font_sm.render(
            f"{self.upf} UPF  ({'max speed' if self.upf >= UPF_MAX else 'watching' if self.upf == 1 else ''})",
            True, C_TEXT_SEC)
        surf.blit(upf_lbl, (self._track.right + 20,
                            bar_rect.centery - upf_lbl.get_height() // 2))

        # min / max ticks
        for label, xpos in [("1", self._track.left), ("1000", self._track.right)]:
            t = font_xs.render(label, True, C_TEXT_DIM)
            surf.blit(t, (xpos - t.get_width() // 2,
                          self._track.bottom + 6))


# ── Scrollable stats panel ────────────────────────────────────────────────────
class StatsPanel:
    LINE_H      = 20
    PAD_X       = 16
    PAD_TOP     = 14

    def __init__(self):
        self._scroll   = 0       # scroll offset in lines
        self._lines    = []      # list of (text, color, indent)
        self._surf_h   = 0       # total rendered height in px
        self._hover    = False
        self._panel    = pygame.Rect(0, 0, 0, 0)

    # ── public ──────────────────────────────────────────────────────────
    def set_panel_rect(self, r: pygame.Rect):
        self._panel = r

    def rebuild(self, games: list, upf: int, fps: float):
        """Rebuild the full line list from current game states."""
        lines = []
        A = GAME_ACCENT

        def push(text, color=C_TEXT_SEC, indent=0):
            lines.append((text, color, indent))

        push("LIVE STATS", C_TEXT_PRI)
        push(f"FPS  {fps:5.1f}      UPF  {upf}", C_TEXT_DIM)
        push("")

        for g in games:
            ac = A[g.idx]
            push(f"── GAME {g.idx + 1} ──────────────────", ac)
            push(f"Episode     {g.episodes:>6}", C_TEXT_SEC, 4)
            push(f"Score       {g.score:>6}", C_TEXT_SEC, 4)
            push(f"Ticks       {g.ticks:>6}", C_TEXT_DIM, 4)
            push("")

        push("── LOG ──────────────────────────", C_TEXT_DIM)
        for i in range(30):
            push(f"[tick {i*100:>6}]  placeholder log entry {i}", C_TEXT_DIM, 4)

        self._lines   = lines
        self._surf_h  = len(lines) * self.LINE_H

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self._hover = self._panel.collidepoint(event.pos)
        if event.type == pygame.MOUSEWHEEL and self._hover:
            visible_lines = (self._panel.height - self.PAD_TOP) // self.LINE_H
            max_scroll    = max(0, len(self._lines) - visible_lines)
            self._scroll  = max(0, min(max_scroll, self._scroll - event.y * 3))

    def draw(self, surf: pygame.Surface, font_sm, font_xs):
        r = self._panel
        # background
        pygame.draw.rect(surf, C_PANEL_BG, r)
        # left border line
        pygame.draw.line(surf, C_PANEL_LINE,
                         (r.left, r.top), (r.left, r.bottom), 1)

        # clip to panel
        clip = surf.get_clip()
        surf.set_clip(r.inflate(-2, -2))

        y0 = r.top + self.PAD_TOP - self._scroll * self.LINE_H
        for text, color, indent in self._lines:
            if y0 + self.LINE_H < r.top:
                y0 += self.LINE_H
                continue
            if y0 > r.bottom:
                break
            if text:
                t = font_xs.render(text, True, color)
                surf.blit(t, (r.left + self.PAD_X + indent, y0))
            y0 += self.LINE_H

        surf.set_clip(clip)

        # scroll indicator
        if len(self._lines) > 0:
            visible_lines = (r.height - self.PAD_TOP) // self.LINE_H
            if len(self._lines) > visible_lines:
                ratio     = visible_lines / len(self._lines)
                bar_h     = max(30, int(r.height * ratio))
                max_scroll = len(self._lines) - visible_lines
                bar_y = r.top + int((r.height - bar_h) *
                                    (self._scroll / max(1, max_scroll)))
                pygame.draw.rect(surf, C_PANEL_LINE,
                                 (r.right - 5, bar_y, 4, bar_h), border_radius=2)


# ── Game cell renderer ────────────────────────────────────────────────────────
def draw_cell(surf: pygame.Surface, game: DummyGame, font_sm, font_xs):
    """Render one game cell (phase 1 = moving dot placeholder)."""
    surf.fill(C_CELL_BG)

    accent = GAME_ACCENT[game.idx]

    # thin accent border
    pygame.draw.rect(surf, accent, surf.get_rect(), 1)

    # moving dot
    pygame.draw.circle(surf, (255, 220, 30),
                       (int(game.x), int(game.y)), 8)
    # dot glow ring
    pygame.draw.circle(surf, (200, 170, 20),
                       (int(game.x), int(game.y)), 12, 1)

    # label top-left
    lbl = font_sm.render(f"GAME {game.idx + 1}", True, accent)
    surf.blit(lbl, (10, 8))

    # score bottom-left
    sc = font_xs.render(f"ep {game.episodes}  score {game.score}", True, C_TEXT_DIM)
    surf.blit(sc, (10, surf.get_height() - sc.get_height() - 8))


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    pygame.init()
    pygame.display.set_caption("Pac-Man RL Trainer")

    # fullscreen at exact native resolution
    screen = pygame.display.set_mode((SW, SH), pygame.FULLSCREEN | pygame.HWSURFACE | pygame.DOUBLEBUF)

    # fonts
    font_md = pygame.font.SysFont("consolas",   15, bold=True)
    font_sm = pygame.font.SysFont("consolas",   13, bold=True)
    font_xs = pygame.font.SysFont("consolas",   12)

    # sub-surfaces — each game renders here then gets blitted to screen
    cells: list[pygame.Surface] = [
        pygame.Surface((CELL_W, CELL_H)) for _ in range(NUM_GAMES)
    ]

    # rects for layout sections
    panel_rect  = pygame.Rect(GAME_AREA_W, 0, PANEL_W, SH - BOTTOM_H)
    bottom_rect = pygame.Rect(0, SH - BOTTOM_H, SW, BOTTOM_H)

    # components
    games  = [DummyGame(i) for i in range(NUM_GAMES)]
    slider = Slider()
    panel  = StatsPanel()
    panel.set_panel_rect(panel_rect)

    clock    = pygame.time.Clock()
    fps      = 0.0
    tick_ctr = 0

    running = True
    while running:
        # ── events ────────────────────────────────────────────────────────────
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False
            slider.handle_event(event)
            panel.handle_event(event)

        if not running:
            break

        # ── logic: run N updates per frame ────────────────────────────────────
        upf = slider.upf
        for _ in range(upf):
            pygame.event.pump()      # keep OS happy without processing events
            for g in games:
                g.step()
            tick_ctr += 1

        # ── render ────────────────────────────────────────────────────────────
        screen.fill(C_BG)

        # 6 game cells
        for i, (g, surf) in enumerate(zip(games, cells)):
            draw_cell(surf, g, font_sm, font_xs)
            ox, oy = cell_origin(i)
            screen.blit(surf, (ox, oy))

        # right stats panel
        fps = clock.get_fps()
        panel.rebuild(games, upf, fps)
        panel.draw(screen, font_sm, font_xs)

        # bottom slider bar
        pygame.draw.rect(screen, C_PANEL_BG, bottom_rect)
        pygame.draw.line(screen, C_PANEL_LINE,
                         bottom_rect.topleft, bottom_rect.topright, 1)
        slider.draw(screen, bottom_rect, font_sm, font_xs)

        pygame.display.flip()
        clock.tick(144)

    # ── clean exit ────────────────────────────────────────────────────────────
    pygame.quit()
    sys.exit(0)


if __name__ == "__main__":
    main()