"""
agent_selector.py  —  Agent file picker + save-on-close logic
──────────────────────────────────────────────────────────────
Provides:
  show_session_mode_picker(screen, fonts)  →  ("NEW_VS_NEW" | "NEW_VS_AGENT" | "AGENT_VS_AGENT",
                                               agent_path_1_or_None, agent_path_2_or_None)

  save_agents(sessions, session_mode)  →  list of saved filenames

What gets saved per mode
────────────────────────
  NEW_VS_NEW     → best agent across all 6 games (1 file)
  NEW_VS_AGENT   → best P1 (agentB / new challenger)  +  best P2 (agentAA / battle-hardened)
  AGENT_VS_AGENT → best P1 (agentAAA lineage)         +  best P2 (agentBB lineage)

Each .pt file is a full checkpoint dict:
  version, state_dict, epsilon, tick, episodes, win_rate, player, session_mode, saved_at

Call show_session_mode_picker() before starting the main loop.
Call save_agents() in your shutdown sequence after pygame.quit().
"""

import os
import glob
import datetime

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


# ── Internal: find best trainer per side ──────────────────────────────────────

def _find_best(sessions, player_id: int):
    """
    Among all sessions, find the trainer and stats for the best agent on
    player_id's side (1 or 2).

    'Best' = highest win-rate; ties broken by lower epsilon (more trained).

    Returns (session, trainer, total_ep, win_count, win_rate)  or  None.
    """
    best = None
    best_wr = -1.0

    for s in sessions:
        ep = s.episodes
        if ep == 0:
            continue

        if player_id == 1:
            wins = s.wins_p1
            trainer = s.trainer1
        else:
            wins = s.wins_p2
            trainer = s.trainer2

        wr = wins / ep

        # Prefer higher win-rate; break ties with lower epsilon
        if best is None or wr > best_wr or (
                wr == best_wr and trainer.epsilon < best[2].epsilon):
            best = (s, wins, trainer, ep, wr)
            best_wr = wr

    if best is None:
        return None
    s, wins, trainer, ep, wr = best
    return s, trainer, ep, wins, wr


def _save_one(trainer, ep: int, wins: int, wr: float,
              player_id: int, session_mode: str, tag: str) -> str:
    """
    Save a full checkpoint for one trainer.

    Filename:  saved_agents/agent_{tag}_p{player_id}_{date}_ep{N}.pt
    """
    _ensure_agents_dir()
    date  = datetime.datetime.now().strftime("%Y-%m-%d")
    fname = f"agent_{tag}_p{player_id}_{date}_ep{ep}.pt"
    fpath = os.path.join(AGENTS_DIR, fname)

    trainer.save_checkpoint(fpath, extra_info={
        "episodes":     ep,
        "wins":         wins,
        "win_rate":     wr,
        "player":       player_id,
        "session_mode": session_mode,
        "saved_at":     datetime.datetime.now().isoformat(),
    })
    print(f"[save] P{player_id} → {fpath}  "
          f"(win-rate {wr:.2%}, ε={trainer.epsilon:.4f}, ep={ep})")
    return fname


# ── Public: save agents on shutdown ───────────────────────────────────────────

def save_agents(sessions, session_mode: str) -> list[str]:
    """
    Called by main.py after the main loop ends.

    What gets saved depends on the session mode:

      NEW_VS_NEW
        → 1 file: best agent across all 12 agents (both P1 and P2)

      NEW_VS_AGENT
        → 2 files:
            best P1  (the new challenger — what you'd call agentB)
            best P2  (the battle-hardened loaded agent — what you'd call agentAA)

      AGENT_VS_AGENT
        → 2 files:
            best P1  (agentAAA lineage)
            best P2  (agentBB  lineage)

    Each .pt file is a FULL checkpoint (weights + epsilon + tick + metadata).
    Returns a list of saved filenames (1 or 2 items, or [] if nothing played).
    """
    label_map = {
        "NEW_VS_NEW":     "newnew",
        "NEW_VS_AGENT":   "nva",
        "AGENT_VS_AGENT": "ava",
    }
    tag = label_map.get(session_mode, "unknown")
    saved = []

    if session_mode == "NEW_VS_NEW":
        # ── single best agent across all 12 slots ────────────────────────────
        best_overall = None
        best_wr      = -1.0

        for pid in (1, 2):
            result = _find_best(sessions, pid)
            if result is None:
                continue
            _, trainer, ep, wins, wr = result
            if wr > best_wr or (wr == best_wr and
                    best_overall is not None and
                    trainer.epsilon < best_overall[0].epsilon):
                best_overall = (trainer, ep, wins, wr, pid)
                best_wr = wr

        if best_overall:
            trainer, ep, wins, wr, pid = best_overall
            fname = _save_one(trainer, ep, wins, wr, pid, session_mode, tag)
            saved.append(fname)

    elif session_mode in ("NEW_VS_AGENT", "AGENT_VS_AGENT"):
        # ── save best for each side independently ─────────────────────────────
        for pid in (1, 2):
            result = _find_best(sessions, pid)
            if result is None:
                continue
            _, trainer, ep, wins, wr = result
            fname = _save_one(trainer, ep, wins, wr, pid, session_mode, tag)
            saved.append(fname)

    if not saved:
        print("[save] No episodes played — nothing saved.")

    return saved


# ── Backward-compat alias ─────────────────────────────────────────────────────
# old code called save_best_agent; keep it working as a single-return wrapper.

def save_best_agent(sessions, session_mode: str) -> str | None:
    saved = save_agents(sessions, session_mode)
    return saved[0] if saved else None