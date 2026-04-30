"""
stats_window.py  —  Live Stats Monitor  (Phase 5 rewrite)
──────────────────────────────────────────────────────────
Run this in a second terminal alongside main.py:
    python stats_window.py

Layout: split window
  LEFT  column (~480 px) — header + 6 game cards
  RIGHT column (~680 px) — P1 chart (top half) + P2 chart (bottom half)

Close with ESC or the window X button.
"""

import sys
import time
import pygame
from stats_io import read_stats

# ── Window ────────────────────────────────────────────────────────────────────
SW, SH    = 1180, 820   # wide enough to show cards + two charts side-by-side
LEFT_W    = 460          # width of the game-cards column
DIVIDER_X = LEFT_W + 6  # 6 px gap before the right column starts
RIGHT_X   = DIVIDER_X + 2
RIGHT_W   = SW - RIGHT_X - 6   # remaining space for charts

# ── Smoothing ─────────────────────────────────────────────────────────────────
EMA_SLOW   = 0.06
EMA_FAST   = 0.12
EMA_TPS    = 0.08

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

# Curve colours
C_P1_REWARD  = (80,  220, 120)   # green — matches in-game P1 colour
C_P2_REWARD  = (230,  80,  80)   # red   — matches in-game P2 colour
C_P1_WR      = (140, 255, 180)   # lighter green for win-rate line
C_P2_WR      = (255, 140, 140)   # lighter red for win-rate line
C_CHART_GRID = (28,  28,  40)
C_CHART_ZERO = (50,  50,  70)

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

REFRESH_HZ = 30
READ_EVERY = 1 / 10


# ── Smooth value helper ────────────────────────────────────────────────────────

class Smooth:
    def __init__(self, alpha: float):
        self.alpha = alpha
        self.value: float | None = None

    def update(self, target: float) -> float:
        if self.value is None:
            self.value = target
        else:
            self.value += self.alpha * (target - self.value)
        return self.value

    def reset(self):
        self.value = None


class GameSmooth:
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
    pygame.draw.rect(surf, bg,    (x, y, w, h),           border_radius=3)
    pygame.draw.rect(surf, color, (x, y, int(w*frac), h), border_radius=3)


def badge(surf, font, text, color, cx, y) -> int:
    t = font.render(f"  {text}  ", True, (10, 10, 14))
    r = pygame.Rect(cx - t.get_width()//2 - 4, y,
                    t.get_width() + 8, t.get_height() + 4)
    pygame.draw.rect(surf, color, r, border_radius=5)
    surf.blit(t, (r.left + 4, r.top + 2))
    return y + r.height + 6


# ── Reward curve chart ────────────────────────────────────────────────────────

def draw_reward_chart(surf, rect, history, reward_color, wr_color,
                      player_label: str, font_xs):
    """
    Draw a combined reward + win-rate chart inside rect.

    history : list of [episode, avg_reward, win_rate]

    Reward  → left y-axis, green/red filled area + line
    Win-rate → right y-axis (0–1), thinner lighter line drawn as true pixel-
               level dashes (not connecting every-other data point).
    """
    pygame.draw.rect(surf, C_PANEL_BG, rect, border_radius=6)
    pygame.draw.rect(surf, C_BORDER,   rect, 1, border_radius=6)

    PAD_L, PAD_R, PAD_T, PAD_B = 46, 42, 22, 24
    plot_x = rect.left + PAD_L
    plot_y = rect.top  + PAD_T
    plot_w = rect.width  - PAD_L - PAD_R
    plot_h = rect.height - PAD_T - PAD_B

    # ── Clip all drawing to the plot area so nothing leaks outside ────────────
    clip_rect = pygame.Rect(plot_x, plot_y, plot_w, plot_h)

    # Title
    label_surf = font_xs.render(
        f"AVERAGE {player_label}  —  reward (fill) · win-rate (line)",
        True, reward_color
    )
    surf.blit(label_surf, (rect.left + PAD_L, rect.top + 4))

    if len(history) < 2:
        waiting = font_xs.render("waiting for episodes...", True, C_TEXT_DIM)
        surf.blit(waiting,
                  (rect.centerx - waiting.get_width()//2,
                   rect.centery - waiting.get_height()//2))
        return

    # ── THE FIX: Sort by episode in case any out-of-order points slipped through
    history = sorted(history, key=lambda p: p[0])

    episodes  = [p[0] for p in history]
    rewards   = [p[1] for p in history]
    win_rates = [p[2] for p in history]

    # ── Y range for reward ────────────────────────────────────────────────────
    r_min  = min(rewards)
    r_max  = max(rewards)
    r_span = max(r_max - r_min, 1.0)
    r_lo   = r_min - r_span * 0.08
    r_hi   = r_max + r_span * 0.08
    r_range = r_hi - r_lo

    # ── X range ───────────────────────────────────────────────────────────────
    ep_min   = episodes[0]
    ep_max   = episodes[-1]
    ep_range = max(ep_max - ep_min, 1)

    def r_to_px(ep, reward):
        """Map (episode, reward) → pixel (x, y), clamped to plot area."""
        px = plot_x + int((ep - ep_min) / ep_range * plot_w)
        py = plot_y + plot_h - int((reward - r_lo) / r_range * plot_h)
        px = max(plot_x, min(plot_x + plot_w, px))
        py = max(plot_y, min(plot_y + plot_h, py))
        return px, py

    def wr_to_px(ep, wr):
        """Map (episode, win_rate 0-1) → pixel, clamped."""
        px = plot_x + int((ep - ep_min) / ep_range * plot_w)
        py = plot_y + plot_h - int(wr * plot_h)
        px = max(plot_x, min(plot_x + plot_w, px))
        py = max(plot_y, min(plot_y + plot_h, py))
        return px, py

    # ── Grid + left axis labels ───────────────────────────────────────────────
    for i in range(5):
        gy        = plot_y + int(i * plot_h / 4)
        r_lbl_val = r_hi - i * r_range / 4
        pygame.draw.line(surf, C_CHART_GRID,
                         (plot_x, gy), (plot_x + plot_w, gy), 1)
        r_lbl = font_xs.render(f"{r_lbl_val:+.0f}", True, C_TEXT_DIM)
        surf.blit(r_lbl, (plot_x - r_lbl.get_width() - 4,
                           gy - r_lbl.get_height()//2))

    # ── Right axis labels (win-rate) ──────────────────────────────────────────
    for i in range(5):
        gy     = plot_y + int(i * plot_h / 4)
        wr_val = 1.0 - i * 0.25
        wr_lbl = font_xs.render(f"{wr_val:.0%}", True, C_TEXT_DIM)
        surf.blit(wr_lbl, (plot_x + plot_w + 4,
                            gy - wr_lbl.get_height()//2))

    # ── Zero line for reward ──────────────────────────────────────────────────
    if r_lo < 0 < r_hi:
        _, zero_y = r_to_px(ep_min, 0)
        pygame.draw.line(surf, C_CHART_ZERO,
                         (plot_x, zero_y), (plot_x + plot_w, zero_y), 1)

    # ── Reward filled area + line ─────────────────────────────────────────────
    reward_pts = [r_to_px(ep, rw) for ep, rw in zip(episodes, rewards)]

    if len(reward_pts) >= 2:
        # baseline at zero (or bottom of plot if all positive)
        base_reward = max(r_lo, 0) if r_lo < 0 else r_lo
        _, base_y   = r_to_px(ep_min, base_reward)
        base_y      = min(plot_y + plot_h, max(plot_y, base_y))

        # filled polygon: data points + close along the baseline
        poly = (reward_pts
                + [(reward_pts[-1][0], base_y),
                   (reward_pts[0][0],  base_y)])
        fill_col = tuple(max(0, c - 155) for c in reward_color)
        if len(poly) >= 3:
            # clip fill to plot rect
            old_clip = surf.get_clip()
            surf.set_clip(clip_rect)
            pygame.draw.polygon(surf, fill_col, poly)
            surf.set_clip(old_clip)

        pygame.draw.lines(surf, reward_color, False, reward_pts, 2)

    # ── Win-rate line — true pixel dashes ────────────────────────────────────
    # Build a continuous pixel polyline, then draw every other DASH_LEN pixels.
    wr_pts = [wr_to_px(ep, wr) for ep, wr in zip(episodes, win_rates)]

    if len(wr_pts) >= 2:
        DASH_PX  = 8    # pixels per dash segment
        GAP_PX   = 5    # pixels per gap
        cycle    = DASH_PX + GAP_PX
        dist_acc = 0.0  # accumulated pixel distance along the polyline
        drawing  = True  # start with a dash

        for i in range(len(wr_pts) - 1):
            x0, y0 = wr_pts[i]
            x1, y1 = wr_pts[i + 1]
            seg_len = max(1.0, ((x1-x0)**2 + (y1-y0)**2) ** 0.5)
            remaining = seg_len

            sx, sy = float(x0), float(y0)
            while remaining > 0:
                phase_left = (DASH_PX if drawing else GAP_PX) - (dist_acc % cycle if False else dist_acc % (DASH_PX if drawing else GAP_PX))
                # how far to the end of the current dash/gap phase
                phase_used  = dist_acc % cycle
                phase_in    = phase_used % (DASH_PX + GAP_PX)
                in_dash     = phase_in < DASH_PX
                to_phase_end = (DASH_PX - phase_in) if in_dash else (cycle - phase_in)

                step = min(remaining, to_phase_end)
                frac = step / seg_len
                ex   = sx + (x1 - x0) * frac
                ey   = sy + (y1 - y0) * frac

                if in_dash:
                    pygame.draw.line(surf, wr_color,
                                     (int(sx), int(sy)), (int(ex), int(ey)), 2)

                dist_acc += step
                remaining -= step
                sx, sy = ex, ey

        # Dot at each actual data point
        dot_step = max(1, len(wr_pts) // 80)
        for i in range(0, len(wr_pts), dot_step):
            pygame.draw.circle(surf, wr_color, wr_pts[i], 2)

    # ── Latest value annotations ──────────────────────────────────────────────
    if reward_pts and wr_pts:
        last_r  = rewards[-1]
        last_wr = win_rates[-1]
        ann_r  = font_xs.render(f"{last_r:+.0f}", True, reward_color)
        ann_wr = font_xs.render(f"{last_wr:.0%}", True, wr_color)
        lx, ly = reward_pts[-1]
        wx, wy = wr_pts[-1]
        # reward annotation: above the last point, inside right edge
        surf.blit(ann_r, (min(lx + 3, rect.right - ann_r.get_width() - 2),
                           max(plot_y, ly - ann_r.get_height())))
        # win-rate annotation: to the right, inside right edge
        surf.blit(ann_wr, (min(wx + 3, rect.right - ann_wr.get_width() - 2),
                            max(plot_y, min(plot_y + plot_h - ann_wr.get_height(),
                                            wy - ann_wr.get_height()//2))))

    # ── X axis episode ticks ──────────────────────────────────────────────────
    for i in range(5):
        ep_val = ep_min + int(i * ep_range / 4)
        ep_lbl = font_xs.render(f"{ep_val:,}", True, C_TEXT_DIM)
        ex     = plot_x + int(i * plot_w / 4)
        surf.blit(ep_lbl, (ex - ep_lbl.get_width()//2,
                            plot_y + plot_h + 5))

    # Border redrawn on top so it's crisp over the fill
    pygame.draw.rect(surf, C_BORDER, rect, 1, border_radius=6)


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

    game_smoothers = [GameSmooth() for _ in range(6)]
    tps_smooth     = Smooth(EMA_TPS)
    fps_smooth     = Smooth(EMA_TPS)

    last_data   = None
    last_read_t = 0.0
    was_offline = True

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
                last_data = None
            elif data.get("shutdown"):
                running = False
                break
            else:
                if was_offline:
                    for gs in game_smoothers:
                        gs.reset()
                    tps_smooth.reset()
                    fps_smooth.reset()
                    was_offline = False

                last_data = data
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

        # ── Vertical divider between left and right columns ───────────────────
        pygame.draw.line(screen, C_BORDER,
                         (DIVIDER_X, 8), (DIVIDER_X, SH - 8), 1)

        # ══════════════════════════════════════════════════════════════════════
        # LEFT COLUMN — header + 6 game cards
        # ══════════════════════════════════════════════════════════════════════
        PAD = 8
        CW  = LEFT_W - PAD * 2

        y = 12
        title = font_title.render("COMBAT TANK RL  —  LIVE STATS", True, C_TEXT_PRI)
        screen.blit(title, (LEFT_W//2 - title.get_width()//2, y))
        y += title.get_height() + 6

        mode = last_data.get("mode", "?")
        mc   = MODE_COLOR.get(mode, C_TEXT_SEC)
        y    = badge(screen, font_md, mode, mc, LEFT_W//2, y)

        smode = last_data.get("session_mode", "NEW_VS_NEW")
        sc    = SESSION_MODE_COLOR.get(smode, C_TEXT_SEC)
        slbl  = smode.replace("_", " ")
        y     = badge(screen, font_xs, slbl, sc, LEFT_W//2, y)

        disp_tps = tps_smooth.value or 0.0
        disp_fps = fps_smooth.value or 0.0
        sub = font_xs.render(f"FPS {disp_fps:5.1f}   TPS {disp_tps:,.0f}",
                              True, C_TEXT_DIM)
        screen.blit(sub, (LEFT_W//2 - sub.get_width()//2, y))
        y += sub.get_height() + 8

        pygame.draw.line(screen, C_BORDER, (PAD, y), (LEFT_W - PAD, y), 1)
        y += 6

        games = last_data.get("games", [])
        for g in games:
            idx = g["idx"]
            ac  = GAME_ACCENT[idx]
            gs  = game_smoothers[idx]

            card_h = 90
            card   = pygame.Rect(PAD, y, CW, card_h)
            pygame.draw.rect(screen, C_PANEL_BG, card, border_radius=6)
            pygame.draw.rect(screen, ac,         card, 1, border_radius=6)

            cx = PAD + 8
            cy = y + 6

            t = font_md.render(f"GAME {idx+1}", True, ac)
            screen.blit(t, (cx, cy))
            ep_val = gs.episodes.value or 0
            ep_t   = font_xs.render(f"ep {ep_val:,.0f}", True, C_TEXT_DIM)
            screen.blit(ep_t, (card.right - ep_t.get_width() - 8, cy + 2))
            cy += t.get_height() + 3

            w1       = gs.wins_p1.value or 0
            w2       = gs.wins_p2.value or 0
            wins_str = f"P1 {w1:5,.0f}  —  {w2:5,.0f} P2"
            wt       = font_sm.render(wins_str, True, C_TEXT_SEC)
            screen.blit(wt, (cx, cy))
            cy += wt.get_height() + 3

            bar_w = (CW - 24) // 2 - 8
            e1 = gs.eps1.value if gs.eps1.value is not None else g["eps1"]
            e2 = gs.eps2.value if gs.eps2.value is not None else g["eps2"]

            el1 = font_xs.render(f"ε P1 {e1:.3f}", True, C_TEXT_DIM)
            screen.blit(el1, (cx, cy))
            draw_bar(screen, cx + el1.get_width() + 4, cy + 2,
                     bar_w - el1.get_width() - 4, 6, e1, ac)

            mid = cx + bar_w + 12
            el2 = font_xs.render(f"P2 {e2:.3f}", True, C_TEXT_DIM)
            screen.blit(el2, (mid, cy))
            draw_bar(screen, mid + el2.get_width() + 4, cy + 2,
                     bar_w - el2.get_width() - 4, 6, e2, ac)
            cy += el1.get_height() + 3

            l1 = gs.loss1.value if gs.loss1.value is not None else g["loss1"]
            l2 = gs.loss2.value if gs.loss2.value is not None else g["loss2"]
            lc = C_LOSS_LIVE if (l1 > 0 or l2 > 0) else C_TEXT_DIM
            lt = font_xs.render(f"Loss P1:{l1:.4f}  P2:{l2:.4f}", True, lc)
            screen.blit(lt, (cx, cy))

            y += card_h + 4

        # Footer — data age, bottom of left column
        age = time.time() - last_data.get("ts", time.time())
        ft  = font_xs.render(f"data age: {age*1000:.0f} ms", True, C_TEXT_DIM)
        screen.blit(ft, (PAD, SH - ft.get_height() - 6))

        # ══════════════════════════════════════════════════════════════════════
        # RIGHT COLUMN — P1 chart (top) + P2 chart (bottom)
        # ══════════════════════════════════════════════════════════════════════
        curves  = last_data.get("curves", {})
        p1_hist = curves.get("p1", [])
        p2_hist = curves.get("p2", [])

        CHART_PAD = 8
        CHART_H   = (SH - CHART_PAD * 3) // 2   # two charts fill the full height

        chart_p1 = pygame.Rect(RIGHT_X, CHART_PAD,
                               RIGHT_W, CHART_H)
        draw_reward_chart(screen, chart_p1, p1_hist,
                          C_P1_REWARD, C_P1_WR, "P1", font_xs)

        chart_p2 = pygame.Rect(RIGHT_X, CHART_PAD * 2 + CHART_H,
                               RIGHT_W, CHART_H)
        draw_reward_chart(screen, chart_p2, p2_hist,
                          C_P2_REWARD, C_P2_WR, "P2", font_xs)

        pygame.display.flip()
        clock.tick(REFRESH_HZ)

    pygame.quit()
    sys.exit(0)


if __name__ == "__main__":
    main()