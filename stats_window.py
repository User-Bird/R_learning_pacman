"""
stats_window.py  —  Live Stats Monitor
────────────────────────────────────────
Run this in a second terminal alongside main.py:
    python stats_window.py

Reads stats_data.json every 100ms and displays all 6 games' stats.
Always smooth — completely independent of the game's render rate.
Close with ESC or the window X button.
"""

import sys
import time
import pygame
from stats_io import read_stats

# ── Window size ───────────────────────────────────────────────────────────────
SW, SH = 460, 780

# ── Palette ───────────────────────────────────────────────────────────────────
C_BG         = (10,  10,  14)
C_PANEL_BG   = (14,  14,  20)
C_BORDER     = (30,  30,  44)
C_TEXT_PRI   = (210, 208, 200)
C_TEXT_SEC   = (130, 128, 118)
C_TEXT_DIM   = (60,  58,  54)
C_LOSS_LIVE  = (120, 220, 140)
C_WAITING    = (80,  78,  70)

GAME_ACCENT = [
    (160, 140, 255),
    ( 72, 210, 168),
    ( 88, 168, 255),
    (255, 192,  72),
    (148, 214,  82),
    (255, 108,  88),
]

MODE_COLOR = {
    "WATCH":    (60,  180,  80),
    "FAST":     (220, 180,  40),
    "HEADLESS": (160,  80, 240),
}

REFRESH_RATE = 10   # redraws per second (always smooth)


def draw_bar(surf, x, y, w, h, frac, color, bg=(30, 30, 44)):
    """Simple horizontal fill bar."""
    pygame.draw.rect(surf, bg,    (x, y, w, h),              border_radius=3)
    pygame.draw.rect(surf, color, (x, y, int(w * frac), h),  border_radius=3)


def main():
    pygame.init()
    pygame.display.set_caption("Tank RL — Live Stats")
    screen = pygame.display.set_mode((SW, SH))
    clock  = pygame.time.Clock()

    font_title = pygame.font.SysFont("consolas", 15, bold=True)
    font_md    = pygame.font.SysFont("consolas", 13, bold=True)
    font_sm    = pygame.font.SysFont("consolas", 12)
    font_xs    = pygame.font.SysFont("consolas", 11)

    last_data   = None
    last_read_t = 0.0

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        # Read stats file at REFRESH_RATE — not every pygame frame
        now = time.perf_counter()
        if now - last_read_t >= 1.0 / REFRESH_RATE:
            data = read_stats()
            if data:
                last_data = data
            last_read_t = now

        # ── Draw ──────────────────────────────────────────────────────────────
        screen.fill(C_BG)

        if last_data is None:
            # Waiting for main.py to start
            msg  = font_md.render("Waiting for main.py to start...", True, C_WAITING)
            msg2 = font_sm.render("Run:  python main.py", True, C_TEXT_DIM)
            screen.blit(msg,  (SW // 2 - msg.get_width()  // 2, SH // 2 - 20))
            screen.blit(msg2, (SW // 2 - msg2.get_width() // 2, SH // 2 + 12))
            pygame.display.flip()
            clock.tick(REFRESH_RATE)
            continue

        # ── Header ────────────────────────────────────────────────────────────
        y = 12
        title = font_title.render("COMBAT TANK RL  —  LIVE STATS", True, C_TEXT_PRI)
        screen.blit(title, (SW // 2 - title.get_width() // 2, y))
        y += title.get_height() + 6

        mode     = last_data.get("mode", "?")
        tps      = last_data.get("tps",  0)
        fps      = last_data.get("fps",  0)
        mc       = MODE_COLOR.get(mode, C_TEXT_SEC)

        # Mode badge
        badge = font_md.render(f"  {mode}  ", True, (10, 10, 14))
        br    = pygame.Rect(SW // 2 - badge.get_width() // 2 - 4, y,
                            badge.get_width() + 8, badge.get_height() + 4)
        pygame.draw.rect(screen, mc, br, border_radius=5)
        screen.blit(badge, (br.left + 4, br.top + 2))
        y += br.height + 6

        sub = font_xs.render(f"FPS {fps:5.1f}     TPS {tps:,.0f}", True, C_TEXT_DIM)
        screen.blit(sub, (SW // 2 - sub.get_width() // 2, y))
        y += sub.get_height() + 10

        pygame.draw.line(screen, C_BORDER, (16, y), (SW - 16, y), 1)
        y += 8

        # ── Per-game cards ────────────────────────────────────────────────────
        PAD   = 12
        CW    = SW - PAD * 2
        games = last_data.get("games", [])

        for g in games:
            idx  = g["idx"]
            ac   = GAME_ACCENT[idx]

            # Card background
            card_h = 90
            card   = pygame.Rect(PAD, y, CW, card_h)
            pygame.draw.rect(screen, C_PANEL_BG, card, border_radius=6)
            pygame.draw.rect(screen, ac,         card, 1, border_radius=6)

            cx = PAD + 10
            cy = y + 8

            # Title row
            t = font_md.render(f"GAME {idx + 1}", True, ac)
            screen.blit(t, (cx, cy))

            ep_t = font_xs.render(f"ep {g['episodes']:,}", True, C_TEXT_DIM)
            screen.blit(ep_t, (card.right - ep_t.get_width() - 10, cy + 2))
            cy += t.get_height() + 4

            # Wins row
            wins_str = f"P1  {g['wins_p1']:,}  —  {g['wins_p2']:,}  P2"
            wt = font_sm.render(wins_str, True, C_TEXT_SEC)
            screen.blit(wt, (cx, cy))
            cy += wt.get_height() + 4

            # Epsilon bars (P1 and P2 side by side)
            bar_w = (CW - 30) // 2 - 10
            e1, e2 = g["eps1"], g["eps2"]

            el1 = font_xs.render(f"ε P1  {e1:.3f}", True, C_TEXT_DIM)
            screen.blit(el1, (cx, cy))
            draw_bar(screen, cx + el1.get_width() + 6, cy + 2,
                     bar_w - el1.get_width() - 6, 6, e1, ac)

            mid = cx + bar_w + 14
            el2 = font_xs.render(f"P2  {e2:.3f}", True, C_TEXT_DIM)
            screen.blit(el2, (mid, cy))
            draw_bar(screen, mid + el2.get_width() + 6, cy + 2,
                     bar_w - el2.get_width() - 6, 6, e2, ac)
            cy += el1.get_height() + 4

            # Loss row
            l1, l2 = g["loss1"], g["loss2"]
            lc = C_LOSS_LIVE if (l1 > 0 or l2 > 0) else C_TEXT_DIM
            loss_str = f"Loss  P1: {l1:.4f}   P2: {l2:.4f}"
            lt = font_xs.render(loss_str, True, lc)
            screen.blit(lt, (cx, cy))

            y += card_h + 6

        # ── Footer timestamp ──────────────────────────────────────────────────
        age = time.time() - last_data.get("ts", time.time())
        ft  = font_xs.render(f"data age: {age*1000:.0f} ms", True, C_TEXT_DIM)
        screen.blit(ft, (SW - ft.get_width() - 12, SH - ft.get_height() - 8))

        pygame.display.flip()
        clock.tick(REFRESH_RATE)

    pygame.quit()
    sys.exit(0)


if __name__ == "__main__":
    main()