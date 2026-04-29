"""
main.py  ─  Phase 4: Main Entry Point (Updated)
──────────────────────────────────────────────────
Implements the 3-button logic (WATCH, FAST, HEADLESS).
Decouples the stats rendering to a separate process via stats_io.py.
Includes Agent Selection UI and Auto-saving on Quit.
"""

import pygame
import sys
import time

from game import TankGame
from agent import DQNAgent
from rl.trainer import Trainer
from renderer import draw_game

# ── NEW IMPORTS ────────────────────────────────────────────────────────────────
from stats_io import write_stats, write_shutdown, clear_stats
from agent_selector import show_session_mode_picker, save_best_agent


# ── Session Wrapper ────────────────────────────────────────────────────────────

class Session:
    """Wraps a single game and its agents for the main loop."""
    def __init__(self, idx: int, session_mode: str, agent1_path: str, agent2_path: str):
        self.idx = idx
        self.game = TankGame()

        # Initialize two independent trainers for self-play
        self.trainer1 = Trainer()
        self.trainer2 = Trainer()

        # ── LOAD SAVED AGENTS LOGIC ───────────────────────────────────────────
        if session_mode == "NEW_VS_AGENT" and agent2_path:
            self.trainer2.online_net.load(agent2_path, self.trainer2.device)
            self.trainer2.target_net.load_state_dict(self.trainer2.online_net.state_dict())
            self.trainer2.epsilon = 0.05   # Exploit mode

        elif session_mode == "AGENT_VS_AGENT":
            if agent1_path:
                self.trainer1.online_net.load(agent1_path, self.trainer1.device)
                self.trainer1.target_net.load_state_dict(self.trainer1.online_net.state_dict())
                self.trainer1.epsilon = 0.05
            if agent2_path:
                self.trainer2.online_net.load(agent2_path, self.trainer2.device)
                self.trainer2.target_net.load_state_dict(self.trainer2.online_net.state_dict())
                self.trainer2.epsilon = 0.05
        # ──────────────────────────────────────────────────────────────────────

        self.agent1 = DQNAgent(self.trainer1)
        self.agent2 = DQNAgent(self.trainer2)

        self.episodes = 0
        self.wins_p1 = 0
        self.wins_p2 = 0
        self.ticks = 0

        self.states = self.game.reset()

    def step(self):
        s1, s2 = self.states

        # Get actions
        a1 = self.agent1.get_action(s1)
        a2 = self.agent2.get_action(s2)

        # Advance game
        next_states, rewards, done = self.game.step([a1, a2])
        self.ticks += 1

        # Push experience to buffers
        self.agent1.push(s1, a1, rewards[0], next_states[0], done)
        self.agent2.push(s2, a2, rewards[1], next_states[1], done)

        if done:
            self.episodes += 1
            if "1 WINS" in self.game.result_text:
                self.wins_p1 += 1
            elif "2 WINS" in self.game.result_text:
                self.wins_p2 += 1

            self.agent1.on_episode_end()
            self.agent2.on_episode_end()
            self.states = self.game.reset()
        else:
            self.states = next_states

# ── Render Helpers ─────────────────────────────────────────────────────────────

def draw_all_games(screen, sessions, tile=16):
    """Draws 6 games in a 3x2 grid."""
    pad = 10
    cols, rows = 25, 19
    w = cols * tile
    h = rows * tile

    for i, s in enumerate(sessions):
        col = i % 3
        row = i // 3
        x = pad + col * (w + pad)
        y = pad + row * (h + pad)

        surf = pygame.Surface((w, h))
        draw_game(surf, s.game, tile=tile)
        screen.blit(surf, (x, y))

        # Draw border & label
        pygame.draw.rect(screen, (60, 60, 80), (x, y, w, h), 2)
        font = pygame.font.SysFont("consolas", 14, bold=True)
        txt = font.render(f"GAME {i+1}", True, (255, 255, 255))
        screen.blit(txt, (x + 4, y + 4))

def draw_buttons(screen, current_mode, rects):
    font = pygame.font.SysFont("consolas", 18, bold=True)
    modes = ["WATCH", "FAST", "HEADLESS"]
    colors = {
        "WATCH": (60, 180, 80),
        "FAST": (220, 180, 40),
        "HEADLESS": (160, 80, 240)
    }

    for mode, rect in zip(modes, rects):
        bg_color = colors[mode] if current_mode == mode else (40, 40, 50)
        pygame.draw.rect(screen, bg_color, rect, border_radius=8)
        pygame.draw.rect(screen, (200, 200, 200), rect, 2, border_radius=8)
        txt = font.render(mode, True, (255, 255, 255))
        screen.blit(txt, (rect.centerx - txt.get_width() // 2, rect.centery - txt.get_height() // 2))

# ── Main Loop ──────────────────────────────────────────────────────────────────

def main():
    # ── Wipe stale stats from last run before starting
    clear_stats()

    pygame.init()

    # ── Window sizing (3x2 grid of games)
    TILE = 16
    W = 3 * (25 * TILE) + 4 * 10
    H = 2 * (19 * TILE) + 3 * 10
    UI_H = 80

    screen = pygame.display.set_mode((W, H + UI_H))
    pygame.display.set_caption("Combat Tank RL ─ Multi-Agent Training")
    clock = pygame.time.Clock()

    # ── SHOW SESSION PICKER UI ─────────────────────────────────────────────────
    font_md = pygame.font.SysFont("consolas", 18, bold=True)
    font_sm = pygame.font.SysFont("consolas", 14, bold=True)
    font_xs = pygame.font.SysFont("consolas", 12)
    fonts = (font_md, font_sm, font_xs)

    session_mode, agent1_path, agent2_path = show_session_mode_picker(screen, fonts)

    # Initialize the 6 games, passing down our selected modes
    sessions = [Session(i, session_mode, agent1_path, agent2_path) for i in range(6)]

    # ── Button geometry
    bw, bh = 140, 40
    bx_start = W // 2 - (3 * bw + 2 * 20) // 2
    by = H + 20
    rect_watch    = pygame.Rect(bx_start, by, bw, bh)
    rect_fast     = pygame.Rect(bx_start + bw + 20, by, bw, bh)
    rect_headless = pygame.Rect(bx_start + 2 * (bw + 20), by, bw, bh)
    btn_rects = [rect_watch, rect_fast, rect_headless]

    current_mode = "WATCH"

    # ── Tracking state
    last_stats_write = 0.0
    STATS_WRITE_INTERVAL = 0.1
    tick_count_window = 0
    tps_timer = time.perf_counter()
    measured_tps = 0.0
    measured_fps = 0.0
    frame_count = 0

    C_BG = (10, 12, 16)

    running = True
    while running:
        # 1. Events (always poll every frame, even in headless!)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False
            if event.type == pygame.MOUSEBUTTONDOWN:
                if rect_watch.collidepoint(event.pos): current_mode = "WATCH"
                elif rect_fast.collidepoint(event.pos): current_mode = "FAST"
                elif rect_headless.collidepoint(event.pos): current_mode = "HEADLESS"

        # 2. Step Games
        n_ticks = {"WATCH": 1, "FAST": 50, "HEADLESS": 200}[current_mode]
        for _ in range(n_ticks):
            for s in sessions:
                s.step()
        tick_count_window += n_ticks

        # 3. Render
        if current_mode == "WATCH":
            screen.fill(C_BG)
            draw_all_games(screen, sessions, TILE)
            draw_buttons(screen, current_mode, btn_rects)
            pygame.display.flip()

        elif current_mode == "FAST":
            if frame_count % 10 == 0:
                screen.fill(C_BG)
                draw_all_games(screen, sessions, TILE)
                draw_buttons(screen, current_mode, btn_rects)
                pygame.display.flip()

        else:  # HEADLESS
            if frame_count % 30 == 0:
                screen.fill(C_BG)
                draw_buttons(screen, current_mode, btn_rects)
                font = pygame.font.SysFont("consolas", 24, bold=True)
                txt = font.render("HEADLESS MODE ACTIVE - RENDERING PAUSED", True, (160, 80, 240))
                screen.blit(txt, (W // 2 - txt.get_width() // 2, H // 2 - txt.get_height() // 2))
                pygame.display.flip()

        # 4. Write stats to file (always on timer)
        now = time.perf_counter()
        if now - last_stats_write >= STATS_WRITE_INTERVAL:
            elapsed = now - tps_timer
            if elapsed >= 1.0:
                measured_tps = tick_count_window / elapsed
                measured_fps = clock.get_fps()
                tick_count_window = 0
                tps_timer = now

            write_stats(
                sessions,
                mode=current_mode,
                tps=measured_tps,
                fps=measured_fps,
                session_mode=session_mode
            )
            last_stats_write = now

        clock.tick(60)
        frame_count += 1

    # ── SHUTDOWN LOGIC ─────────────────────────────────────────────────────────
    write_shutdown()  # Tell stats_window to close
    saved = save_best_agent(sessions, session_mode)
    if saved:
        print(f"Best agent saved: {saved}")

    pygame.quit()
    sys.exit(0)

if __name__ == "__main__":
    main()