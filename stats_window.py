"""
stats_window.py  —  Live Stats Monitor  (Phase 4 rewrite)
──────────────────────────────────────────────────────────
Run this in a second terminal alongside main.py:
    python stats_window.py

Key improvements over the original:
  • SMOOTHED display — all numbers use exponential moving average so they
    glide instead of jumping, even in headless mode where ticks fly.
  • STALENESS detection — if the JSON file is older than 3 s (main.py died
    without sending shutdown), the window shows "Offline" and stops updating.
  • SHUTDOWN signal — if main.py writes {"shutdown": true} the window closes
    itself automatically (no zombie window left open in PyCharm).
  • Startup wipe — on first read the window ignores stale data from a
    previous run (Stats_io.read_stats() already filters by timestamp age).

Close with ESC or the window X button.
"""

import sys
import time
import pygame
from stats_io import read_stats

# ── Window ────────────────────────────────────────────────────────────────────
SW, SH = 480, 820

# ── Smoothing ─────────────────────────────────────────────────────────────────
# EMA alpha: how fast the displayed value chases the real value.
# 0.08 = slow/smooth glide (good for headless where numbers move 1000x/sec)
# 0.25 = moderate (good for fast mode)
# 1.00 = no smoothing (instant jump, like the old behaviour)
EMA_SLOW   = 0.06   # for loss, epsilon — changes slowly anyway
EMA_FAST   = 0.12   # for episode count, wins, ticks — move faster
EMA_TPS    = 0.08   # TPS and FPS header

# ── Palette ───────────────────────────────────────────────────────────────────
C_BG         = (10,  10,  14)
C_PANEL_BG   = (14,  14,  20)
C_BORDER     = (30,  30,  44)
C_TEXT_PRI   = (210, 208, 200)
C_TEXT_SEC   = (130, 128, 118)
C_TEXT_DIM   = (60,  58,  54)
C_LOSS_LIVE  = (120, 220, 140)
C_WAITING    = (80,  78,  70)
C_OFFLINE    = (200,  60,  60)

GAME_ACCENT = [
    (160, 140, 255),
    ( 72, 210, 168),
    ( 88, 168, 255),
    (255, 192,  72),
    (148, 214,  82),
    (255, 108,  88),
]

MODE_COLOR = {
    "WATCH":    ( 60, 180,  80),
    "FAST":     (220, 180,  40),
    "HEADLESS": (160,  80, 240),
}
SESSION_MODE_COLOR = {
    "NEW_VS_NEW":       (100, 160, 255),
    "NEW_VS_AGENT":     (255, 160,  80),
    "AGENT_VS_AGENT":   (200,  80, 200),
}

REFRESH_HZ  = 30        # stats_window redraws at 30 FPS — always smooth
READ_EVERY  = 1 / 10    # read JSON 10× per second


# ── Smooth value helper ────────────────────────────────────────────────────────

class Smooth:
    """
    Exponential moving average for a single float.
    First call seeds the value instantly (no initial slide from 0).
    """
    def __init__(self, alpha: float):
        self.alpha = alpha
        self.value: float | None = None

    def update(self, target: float) -> float:
        if self.value is None:
            self.value = target          # seed instantly on first data
        else:
            self.value += self.alpha * (target - self.value)
        return self.value

    def reset(self):
        self.value = None


class GameSmooth:
    """One set of smoothed display values per game slot."""
    def __init__(self):
        self.episodes = Smooth(EMA_FAST)
        self.wins_p1  = Smooth(EMA_FAST)
        self.wins_p2  = Smooth(EMA_FAST)
        self.eps1     = Smooth(EMA_SLOW)
        self.eps2     = Smooth(EMA_SLOW)
        self.loss1    = Smooth(EMA_SLOW)
        self.loss2    = Smooth(EMA_SLOW)

    def reset(self):
        for attr in vars(self).values():
            attr.reset()


# ── Drawing helpers ────────────────────────────────────────────────────────────

def draw_bar(surf, x, y, w, h, frac, color, bg=(30, 30, 44)):
    frac = max(0.0, min(1.0, frac))
    pygame.draw.rect(surf, bg,    (x, y, w, h),             border_radius=3)
    pygame.draw.rect(surf, color, (x, y, int(w*frac), h),   border_radius=3)


def badge(surf, font, text, color, cx, y) -> int:
    """Draw a pill-shaped coloured badge centred at cx. Returns new y."""
    t   = font.render(f"  {text}  ", True, (10, 10, 14))
    r   = pygame.Rect(cx - t.get_width()//2 - 4, y,
                      t.get_width() + 8, t.get_height() + 4)
    pygame.draw.rect(surf, color, r, border_radius=5)
    surf.blit(t, (r.left + 4, r.top + 2))
    return y + r.height + 6


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    pygame.init()
    pygame.display.set_caption("Tank RL — Live Stats")
    screen = pygame.display.set_mode((SW, SH))
    clock  = pygame.time.Clock()

    font_title = pygame.font.SysFont("consolas", 15, bold=True)
    font_md    = pygame.font.SysFont("consolas", 13, bold=True)
    font_sm    = pygame.font.SysFont("consolas", 12)
    font_xs    = pygame.font.SysFont("consolas", 11)

    # Smoothers — one per game slot, plus header values
    game_smoothers = [GameSmooth() for _ in range(6)]
    tps_smooth     = Smooth(EMA_TPS)
    fps_smooth     = Smooth(EMA_TPS)

    last_data    = None
    last_read_t  = 0.0
    was_offline  = True    # starts True so first good read seeds everything

    running = True
    while running:
        # ── Events ────────────────────────────────────────────────────────────
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        # ── Read stats file ───────────────────────────────────────────────────
        now = time.perf_counter()
        if now - last_read_t >= READ_EVERY:
            data = read_stats()
            last_read_t = now

            if data is None:
                # File gone / stale — show offline
                last_data = None
            elif data.get("shutdown"):
                # main.py asked us to close
                running = False
                break
            else:
                # Good data —————————————————————————————————————————————————
                if was_offline:
                    # Coming back from offline: reset all smoothers so stale
                    # values don't bleed into the new session display
                    for gs in game_smoothers:
                        gs.reset()
                    tps_smooth.reset()
                    fps_smooth.reset()
                    was_offline = False

                last_data = data

                # Feed smoothers
                tps_smooth.update(data.get("tps", 0))
                fps_smooth.update(data.get("fps", 0))
                for g in data.get("games", []):
                    idx = g["idx"]
                    if idx >= len(game_smoothers):
                        continue
                    gs = game_smoothers[idx]
                    gs.episodes.update(g["episodes"])
                    gs.wins_p1.update(g["wins_p1"])
                    gs.wins_p2.update(g["wins_p2"])
                    gs.eps1.update(g["eps1"])
                    gs.eps2.update(g["eps2"])
                    gs.loss1.update(g["loss1"])
                    gs.loss2.update(g["loss2"])

            if last_data is None:
                was_offline = True

        # ── Draw ──────────────────────────────────────────────────────────────
        screen.fill(C_BG)

        if last_data is None:
            # ── Offline / waiting screen ──────────────────────────────────────
            msg  = font_md.render("Waiting for main.py...", True, C_WAITING)
            msg2 = font_xs.render("Run:  python main.py", True, C_TEXT_DIM)
            msg3 = font_xs.render("(or data is stale — relaunch main.py)", True, C_OFFLINE)
            cy = SH // 2 - 30
            for m in (msg, msg2, msg3):
                screen.blit(m, (SW//2 - m.get_width()//2, cy))
                cy += m.get_height() + 8
            pygame.display.flip()
            clock.tick(REFRESH_HZ)
            continue

        # ── Header ────────────────────────────────────────────────────────────
        y = 12
        title = font_title.render("COMBAT TANK RL  —  LIVE STATS", True, C_TEXT_PRI)
        screen.blit(title, (SW//2 - title.get_width()//2, y))
        y += title.get_height() + 6

        # Render mode badge
        mode = last_data.get("mode", "?")
        mc   = MODE_COLOR.get(mode, C_TEXT_SEC)
        y    = badge(screen, font_md, mode, mc, SW//2, y)

        # Session mode badge (smaller, below)
        smode = last_data.get("session_mode", "NEW_VS_NEW")
        sc    = SESSION_MODE_COLOR.get(smode, C_TEXT_SEC)
        slbl  = smode.replace("_", " ")
        y     = badge(screen, font_xs, slbl, sc, SW//2, y)

        # TPS / FPS — use smoothed values
        disp_tps = tps_smooth.value or 0.0
        disp_fps = fps_smooth.value or 0.0
        sub = font_xs.render(f"FPS {disp_fps:5.1f}     TPS {disp_tps:,.0f}", True, C_TEXT_DIM)
        screen.blit(sub, (SW//2 - sub.get_width()//2, y))
        y += sub.get_height() + 10

        pygame.draw.line(screen, C_BORDER, (16, y), (SW-16, y), 1)
        y += 8

        # ── Per-game cards ────────────────────────────────────────────────────
        PAD    = 10
        CW     = SW - PAD * 2
        games  = last_data.get("games", [])

        for g in games:
            idx = g["idx"]
            ac  = GAME_ACCENT[idx]
            gs  = game_smoothers[idx]

            card_h = 96
            card   = pygame.Rect(PAD, y, CW, card_h)
            pygame.draw.rect(screen, C_PANEL_BG, card, border_radius=6)
            pygame.draw.rect(screen, ac,         card, 1, border_radius=6)

            cx = PAD + 10
            cy = y + 7

            # Title + episode count
            t = font_md.render(f"GAME {idx+1}", True, ac)
            screen.blit(t, (cx, cy))
            ep_val = gs.episodes.value or 0
            ep_t = font_xs.render(f"ep {ep_val:,.0f}", True, C_TEXT_DIM)
            screen.blit(ep_t, (card.right - ep_t.get_width() - 10, cy + 2))
            cy += t.get_height() + 4

            # Wins — smoothed so they count up smoothly instead of jumping
            w1 = gs.wins_p1.value or 0
            w2 = gs.wins_p2.value or 0
            wins_str = f"P1 {w1:6,.0f}  —  {w2:6,.0f} P2"
            wt = font_sm.render(wins_str, True, C_TEXT_SEC)
            screen.blit(wt, (cx, cy))
            cy += wt.get_height() + 4

            # Epsilon bars — smoothed glide
            bar_w = (CW - 30) // 2 - 10
            e1 = gs.eps1.value if gs.eps1.value is not None else g["eps1"]
            e2 = gs.eps2.value if gs.eps2.value is not None else g["eps2"]

            el1 = font_xs.render(f"ε P1 {e1:.3f}", True, C_TEXT_DIM)
            screen.blit(el1, (cx, cy))
            draw_bar(screen, cx + el1.get_width() + 6, cy + 2,
                     bar_w - el1.get_width() - 6, 6, e1, ac)

            mid = cx + bar_w + 14
            el2 = font_xs.render(f"P2 {e2:.3f}", True, C_TEXT_DIM)
            screen.blit(el2, (mid, cy))
            draw_bar(screen, mid + el2.get_width() + 6, cy + 2,
                     bar_w - el2.get_width() - 6, 6, e2, ac)
            cy += el1.get_height() + 4

            # Loss — smoothed glide
            l1 = gs.loss1.value if gs.loss1.value is not None else g["loss1"]
            l2 = gs.loss2.value if gs.loss2.value is not None else g["loss2"]
            lc = C_LOSS_LIVE if (l1 > 0 or l2 > 0) else C_TEXT_DIM
            loss_str = f"Loss  P1: {l1:.4f}   P2: {l2:.4f}"
            lt = font_xs.render(loss_str, True, lc)
            screen.blit(lt, (cx, cy))

            y += card_h + 5

        # ── Footer ────────────────────────────────────────────────────────────
        age = time.time() - last_data.get("ts", time.time())
        ft  = font_xs.render(f"data age: {age*1000:.0f} ms", True, C_TEXT_DIM)
        screen.blit(ft, (SW - ft.get_width() - 12, SH - ft.get_height() - 8))

        pygame.display.flip()
        clock.tick(REFRESH_HZ)

    pygame.quit()
    sys.exit(0)


if __name__ == "__main__":
    main()