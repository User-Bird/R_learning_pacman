"""
agent_selector.py  —  Agent file picker + save-on-close logic
──────────────────────────────────────────────────────────────
Provides:
  show_session_mode_picker(screen, fonts)  →  ("NEW_VS_NEW" | "NEW_VS_AGENT" | "AGENT_VS_AGENT",
                                               agent_path_1_or_None, agent_path_2_or_None)

  save_best_agent(sessions, session_mode)  →  saved filename (str) or None

Call show_session_mode_picker() before starting the main loop.
Call save_best_agent() in your shutdown sequence after pygame.quit().
"""

import os
import glob
import time
import datetime
import shutil

import pygame
import torch

# ── Palette (matches the rest of the project) ─────────────────────────────────
C_BG         = (10,  10,  14)
C_PANEL_BG   = (18,  18,  26)
C_BORDER     = (40,  40,  60)
C_TEXT_PRI   = (210, 208, 200)
C_TEXT_SEC   = (130, 128, 118)
C_TEXT_DIM   = (60,  58,  54)
C_HOVER      = (50,  50,  70)
C_SELECT     = (60,  120, 200)
C_BTN_NEW    = (40,  160,  80)
C_BTN_NVA    = (200, 130,  40)
C_BTN_AVA    = (160,  60, 200)
C_BTN_OK     = (40,  160,  80)
C_BTN_CANCEL = (160,  40,  40)

AGENTS_DIR   = "saved_agents"    # folder where .pt files live


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ensure_agents_dir():
    os.makedirs(AGENTS_DIR, exist_ok=True)


def _list_agents() -> list[str]:
    """Return list of .pt filenames (basename only) in saved_agents/."""
    _ensure_agents_dir()
    files = glob.glob(os.path.join(AGENTS_DIR, "*.pt"))
    return sorted([os.path.basename(f) for f in files])


def _draw_btn(surf, font, text, rect, color, hover=False):
    col = tuple(min(255, c + 30) for c in color) if hover else color
    pygame.draw.rect(surf, col, rect, border_radius=6)
    pygame.draw.rect(surf, C_BORDER, rect, 1, border_radius=6)
    t = font.render(text, True, C_TEXT_PRI)
    surf.blit(t, (rect.centerx - t.get_width()//2,
                  rect.centery - t.get_height()//2))


def _draw_list(surf, font, items, selected_idx, rect, scroll_offset):
    """Draw a scrollable file list inside rect. Returns the rects for each visible item."""
    pygame.draw.rect(surf, C_PANEL_BG, rect, border_radius=4)
    pygame.draw.rect(surf, C_BORDER,   rect, 1, border_radius=4)

    row_h   = font.get_linesize() + 6
    visible = rect.height // row_h
    item_rects = []

    for i, name in enumerate(items[scroll_offset: scroll_offset + visible]):
        real_idx = i + scroll_offset
        row_rect = pygame.Rect(rect.left + 2, rect.top + i * row_h,
                               rect.width - 4, row_h)
        if real_idx == selected_idx:
            pygame.draw.rect(surf, C_SELECT, row_rect, border_radius=3)
        t = font.render(name, True, C_TEXT_PRI if real_idx == selected_idx else C_TEXT_SEC)
        surf.blit(t, (row_rect.left + 6, row_rect.top + 3))
        item_rects.append((row_rect, real_idx))

    return item_rects


# ── Agent file picker ─────────────────────────────────────────────────────────

def _pick_agent(screen, fonts, title: str) -> str | None:
    """
    Shows a modal file-list dialog.
    Returns the full path to the chosen .pt file, or None if cancelled.
    """
    font_md, font_sm, font_xs = fonts
    W, H = screen.get_size()

    DW, DH = 420, 400
    dx = (W - DW) // 2
    dy = (H - DH) // 2
    dlg = pygame.Rect(dx, dy, DW, DH)

    agents      = _list_agents()
    selected    = 0 if agents else -1
    scroll      = 0
    list_rect   = pygame.Rect(dx + 14, dy + 60, DW - 28, DH - 120)
    btn_ok      = pygame.Rect(dx + 14,       dy + DH - 46, (DW - 42)//2, 34)
    btn_cancel  = pygame.Rect(btn_ok.right + 14, dy + DH - 46, (DW - 42)//2, 34)

    clock = pygame.time.Clock()
    while True:
        mouse = pygame.mouse.get_pos()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return None
                if event.key == pygame.K_UP and selected > 0:
                    selected -= 1
                if event.key == pygame.K_DOWN and selected < len(agents) - 1:
                    selected += 1
                if event.key == pygame.K_RETURN and selected >= 0:
                    return os.path.join(AGENTS_DIR, agents[selected])
            if event.type == pygame.MOUSEBUTTONDOWN:
                if btn_cancel.collidepoint(mouse):
                    return None
                if btn_ok.collidepoint(mouse) and selected >= 0:
                    return os.path.join(AGENTS_DIR, agents[selected])
                # click on list
                row_h    = font_xs.get_linesize() + 6
                visible  = list_rect.height // row_h
                if list_rect.collidepoint(mouse):
                    rel_y   = mouse[1] - list_rect.top
                    clicked = scroll + rel_y // row_h
                    if 0 <= clicked < len(agents):
                        selected = clicked
            if event.type == pygame.MOUSEWHEEL:
                scroll = max(0, min(scroll - event.y, max(0, len(agents) - 10)))

        # Draw
        overlay = pygame.Surface((W, H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        screen.blit(overlay, (0, 0))

        pygame.draw.rect(screen, C_BG, dlg, border_radius=10)
        pygame.draw.rect(screen, C_BORDER, dlg, 1, border_radius=10)

        ttl = font_md.render(title, True, C_TEXT_PRI)
        screen.blit(ttl, (dlg.centerx - ttl.get_width()//2, dy + 16))

        if not agents:
            nm = font_sm.render("No saved agents found in saved_agents/", True, C_TEXT_DIM)
            screen.blit(nm, (dlg.centerx - nm.get_width()//2, list_rect.centery))
        else:
            _draw_list(screen, font_xs, agents, selected, list_rect, scroll)

        _draw_btn(screen, font_sm, "Select",  btn_ok,     C_BTN_OK,
                  btn_ok.collidepoint(mouse))
        _draw_btn(screen, font_sm, "Cancel",  btn_cancel, C_BTN_CANCEL,
                  btn_cancel.collidepoint(mouse))

        pygame.display.flip()
        clock.tick(30)


# ── Session mode picker (main entry point) ────────────────────────────────────

def show_session_mode_picker(screen, fonts):
    """
    Shows the session-mode selection screen.

    Returns
    -------
    (session_mode, agent1_path, agent2_path)
      session_mode  :  "NEW_VS_NEW" | "NEW_VS_AGENT" | "AGENT_VS_AGENT"
      agent1_path   :  str path to .pt file, or None
      agent2_path   :  str path to .pt file, or None
    """
    font_md, font_sm, font_xs = fonts
    W, H = screen.get_size()
    clock = pygame.time.Clock()

    BW, BH = 340, 64
    bx     = W // 2 - BW // 2

    btn_nvn = pygame.Rect(bx, H//2 - 120, BW, BH)
    btn_nva = pygame.Rect(bx, H//2 -  40, BW, BH)
    btn_ava = pygame.Rect(bx, H//2 +  40, BW, BH)

    MODES = [
        (btn_nvn, "NEW_VS_NEW",       "  New vs New  (6 fresh agents)",         C_BTN_NEW),
        (btn_nva, "NEW_VS_AGENT",     "  New vs Agent  (pick opponent)",         C_BTN_NVA),
        (btn_ava, "AGENT_VS_AGENT",   "  Agent vs Agent  (pick both sides)",     C_BTN_AVA),
    ]

    desc = {
        "NEW_VS_NEW":     "6 games, all agents train from scratch.",
        "NEW_VS_AGENT":   "6 games: fresh P1 trains against a loaded P2.",
        "AGENT_VS_AGENT": "6 games: both sides loaded from saved files.",
    }

    while True:
        mouse = pygame.mouse.get_pos()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                raise SystemExit
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                pygame.quit()
                raise SystemExit
            if event.type == pygame.MOUSEBUTTONDOWN:
                for btn, mode, _, _ in MODES:
                    if btn.collidepoint(mouse):
                        if mode == "NEW_VS_NEW":
                            return mode, None, None

                        elif mode == "NEW_VS_AGENT":
                            path = _pick_agent(screen, fonts,
                                               "Select P2 agent (.pt file)")
                            if path is None:
                                break   # user cancelled — stay on picker
                            return mode, None, path

                        elif mode == "AGENT_VS_AGENT":
                            p1 = _pick_agent(screen, fonts,
                                             "Select P1 agent (.pt file)")
                            if p1 is None:
                                break
                            p2 = _pick_agent(screen, fonts,
                                             "Select P2 agent (.pt file)")
                            if p2 is None:
                                break
                            return mode, p1, p2

        # Draw picker screen
        screen.fill(C_BG)

        title = font_md.render("SELECT SESSION MODE", True, C_TEXT_PRI)
        screen.blit(title, (W//2 - title.get_width()//2, H//2 - 200))

        hovered_mode = None
        for btn, mode, label, color in MODES:
            hover = btn.collidepoint(mouse)
            if hover:
                hovered_mode = mode
            _draw_btn(screen, font_sm, label, btn, color, hover)

        # Description line
        if hovered_mode:
            d = font_xs.render(desc[hovered_mode], True, C_TEXT_DIM)
            screen.blit(d, (W//2 - d.get_width()//2, H//2 + 120))

        sub = font_xs.render("ESC or close window to quit", True, C_TEXT_DIM)
        screen.blit(sub, (W//2 - sub.get_width()//2, H - 40))

        pygame.display.flip()
        clock.tick(30)


# ── Save best agent on close ───────────────────────────────────────────────────

def save_best_agent(sessions, session_mode: str) -> str | None:
    """
    After the main loop ends, find the best performing agent across all 6 games
    and save its weights.

    'Best' = highest win rate (wins / episodes).  Ties broken by epsilon
    (lower is better — more exploitation).

    Filename format:
        saved_agents/agent_<name>_<YYYY-MM-DD>_ep<N>.pt

    Returns the saved filename, or None if nothing was saved.
    """
    _ensure_agents_dir()

    best_session  = None
    best_player   = None     # 1 or 2
    best_winrate  = -1.0

    for s in sessions:
        ep = s.episodes
        if ep == 0:
            continue
        wr1 = s.wins_p1 / ep
        wr2 = s.wins_p2 / ep

        # Pick the better of the two agents in this session
        if wr1 >= wr2:
            wr, pid = wr1, 1
        else:
            wr, pid = wr2, 2

        # Prefer lower epsilon on equal winrate (more trained)
        trainer  = s.trainer1 if pid == 1 else s.trainer2
        eps      = trainer.epsilon

        if (wr > best_winrate or
                (wr == best_winrate and
                 best_session is not None and
                 eps < (s.trainer1 if best_player == 1 else s.trainer2).epsilon)):
            best_winrate  = wr
            best_session  = s
            best_player   = pid

    if best_session is None:
        return None   # no episodes played at all

    trainer   = best_session.trainer1 if best_player == 1 else best_session.trainer2
    total_ep  = best_session.episodes

    # Build a short human-readable name from session mode
    label_map = {
        "NEW_VS_NEW":       "newnew",
        "NEW_VS_AGENT":     "nva",
        "AGENT_VS_AGENT":   "ava",
    }
    label = label_map.get(session_mode, "unknown")
    date  = datetime.datetime.now().strftime("%Y-%m-%d")
    fname = f"agent_{label}_{date}_ep{total_ep}.pt"
    fpath = os.path.join(AGENTS_DIR, fname)

    torch.save(trainer.online_net.state_dict(), fpath)
    print(f"[save] Best agent saved → {fpath}  (win-rate {best_winrate:.2%})")
    return fname