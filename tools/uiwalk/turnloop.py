"""Headless multi-turn playthrough driver for the MoM scenario.

WHY A SEPARATE DRIVER: uiwalk's steps JSON is a fixed linear script. A turn loop
needs (a) an unbounded repeat, (b) a background assertion channel that fires
between steps, and (c) a stop-on-first-error. Those are control flow, not steps.

It imports uiwalk as a MODULE rather than shelling out, so every invariant that
lives in uiwalk still holds: preflight_exe (L6, assert the binary), the
off-screen stash watchdog started BEFORE the process spawns (HEADLESS is a
continuous invariant, not a one-time move), and Game.launch's argument quoting.
NEVER launch the exe any other way.

THE ASSERTION CHANNEL (the reason this driver can claim anything):
SLIC errors do not render in client pixels. c3errors_ErrorDialog
(ctp2_code/ctp/ctp2_utils/c3errors.cpp:127) calls

    MessageBox(NULL, "<detail>\\n\\nContinue?", "<module> Error",
               MB_YESNO | MB_ICONEXCLAMATION)

-- a parentless native Win32 dialog. Every SLIC failure path routes through it
(SlicFrame.cpp x14, SlicArray.cpp, sliccmd.cpp, SlicEngine.cpp, sliciffile.cpp,
SlicNamedSymbol.cpp). So the error channel is enumerable by window title, with
the exact error TEXT recoverable -- strictly stronger than pixel-diffing for a
modal. It also blocks the game thread and IDNO calls exit(1), which is why the
watcher must answer it promptly (IDYES = continue) instead of leaving it up.

Preconditions: run from the uiwalk tool dir; ctp2.exe contains the marker.
Failure modes: game process dies (crash), a SLIC error dialog appears, or the
frame stops changing across an end-turn (turn did not advance).
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import win32api
import win32con
import win32gui

import uiwalk

MB_YES = 6                      # IDYES -- "Continue?" -> keep running
ERROR_POLL_MS = 150             # matches the stash watchdog cadence
TURN_BUTTON = "ControlPanelWindow.ControlPanel.TurnButton"
MAGIC_BUTTON = "ControlPanelWindow.ControlPanel.ShortcutPad.MagicButton"


def _window_text_tree(hwnd) -> str:
    """Concatenate a dialog's own caption plus every child control's text.

    MessageBox bodies live in a static child (id 0xFFFF), so GetWindowText on
    the dialog alone returns only the title. Reading the whole tree recovers the
    actual SLIC error message, which is the thing worth logging.
    """
    parts = [win32gui.GetWindowText(hwnd)]

    def cb(child, _):
        try:
            parts.append(win32gui.GetWindowText(child))
        except Exception:
            pass
        return True

    try:
        win32gui.EnumChildWindows(hwnd, cb, None)
    except Exception:
        pass
    return " | ".join(p for p in parts if p)


class ErrorWatcher:
    """Background poll for native SLIC error dialogs; records and dismisses.

    Guarantee: any dialog whose class is #32770 and whose caption ends in
    "Error" is captured (title + body) into .hits and answered with IDYES.
    Maintain: the game thread is never left blocked on a modal, so the run stays
    headless and does not hang. Dismissing does NOT hide the failure -- .hits is
    the record and the driver stops on the first entry.
    """

    def __init__(self, own_pids: set[int]):
        self.own_pids = own_pids
        self.hits: list[dict] = []
        self._seen: set[int] = set()
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._loop, daemon=True)

    def start(self):
        self._t.start()

    def stop(self):
        self._stop.set()

    def _consider(self, hwnd):
        if hwnd in self._seen:
            return
        try:
            cls = win32gui.GetClassName(hwnd)
            title = win32gui.GetWindowText(hwnd)
        except Exception:
            return
        if cls != "#32770" or not title.strip().lower().endswith("error"):
            return
        self._seen.add(hwnd)
        body = _window_text_tree(hwnd)
        self.hits.append({"t": time.strftime("%H:%M:%S"), "title": title, "text": body})
        print(f"\n!! ERROR DIALOG: {title}\n   {body}", flush=True)
        # IDYES = "Continue?" yes. IDNO would call exit(1) inside the game.
        win32api.PostMessage(hwnd, win32con.WM_COMMAND, MB_YES, 0)

    def _loop(self):
        while not self._stop.is_set():
            try:
                win32gui.EnumWindows(lambda h, _: (self._consider(h), True)[1], None)
            except Exception:
                pass
            self._stop.wait(ERROR_POLL_MS / 1000)


def frame_delta(a, b) -> int:
    """Count differing pixels between two BGR frames (L4 delta decoder input)."""
    if a is None or b is None or a.shape != b.shape:
        return -1
    return int(cv2.countNonZero(cv2.cvtColor(cv2.absdiff(a, b), cv2.COLOR_BGR2GRAY)))


def end_turn(game: uiwalk.Game, inp, mode: str):
    """Request end-of-turn.

    "button" = inject a press on TurnButton. MEASURED 2026-07-25: the path
    resolves and InjectPress returns OK (H:\\mom_hook.log, 5/5).
    aui_Button::InjectPress (aui_button.cpp:72) calls m_ActionFunc directly with
    NO IsDisabled() check, so a greyed button is not what blocks this. The bound
    handler is EndTurnButtonActionCallback (ui/interface/EndTurnButton.cpp),
    whose only silent early-return is GetCurPlayer() != GetVisiblePlayer().

    "key" = the 'A' keymap action. KNOWN DEAD in this build: the whole
    KEY_FUNCTION_ENDTURN body is inside #ifdef _PLAYTEST (keypress.cpp:857) and
    ctp2.exe is Final-SDL. Kept only as a negative control.
    """
    if mode == "none":
        return                      # negative control: isolates a prior step
    if mode == "key":
        inp.hotkey(["a"])
    else:
        uiwalk.inject_press(game.hwnd, TURN_BUTTON)


MSG_CLOSE_CAPTURE = (497, 61)   # X button of the BeginTurn message box, capture coords
MSG_PROBE_CAPTURE = (250, 120)  # interior of that box: parchment when open, black map when not
# Turn/date widget as FRACTIONS of the frame, not absolute pixels.
# MEASURED 2026-07-25: the absolute (480,1178,560,1200) was authored against a
# 1024-wide capture. On the real 2400x1350 capture it lands in dead black map --
# crop delta 0 between 4000BC and 3975BC, i.e. it reported TURN_DID_NOT_ADVANCE
# on a turn that HAD advanced (gold 106 -> 112 in the same pair of frames).
# Same defect class as the stale click constant: an absolute capture coordinate.
# RE-MEASURED 2026-07-25 after the 1024x768 restore, and now expressed as
# fractions of the RENDERED SURFACE rather than of the capture. At this setting
# the client is 1280x960 (125% DPI) but the engine blits its 1024x768 surface
# UNSCALED into the TOP-LEFT corner, leaving black margins right and bottom
# (measured content bbox 0,0..1021,759). A fraction of the capture therefore is
# NOT a fraction of the UI: the old (0.573,0.719) landed on the unit-command
# buttons, which change on unit selection, so turn advance was scored off a
# widget that has nothing to do with the date. Fractions of the detected render
# rect survive both geometries.
# SUPERSEDED 2026-07-26 by date_rect(), which anchors to the BOTTOM edge instead.
# A height FRACTION is only correct while the render is 768 tall; the engine
# reflows its in-game UI to the client size, so at 1024x1280 the same fraction
# lands ~85px above the widget. Kept only as the provenance of date_rect's
# numbers -- nothing reads it.
# DATE_FRACTION = (0.4668, 0.8568, 0.5430, 0.8984)  # x0,y0,x1,y1 of the RENDER

# END TURN is pressed up to this many times per turn, waiting between attempts.
# A press that resolves the LDL path and returns OK but does not advance the date
# is the engine not being ready yet (EndTurnButtonActionCallback's only silent
# early-return is GetCurPlayer() != GetVisiblePlayer()), which is exactly the
# transient state right after a scenario load. Bounded on purpose: a real stall
# must still fail the run rather than spin. 3 x 3s costs at most ~9s on the one
# turn where it is needed and nothing at all on every other turn.
END_TURN_ATTEMPTS = 3
END_TURN_RETRY_S = 3.0

# ENGINE PING, 2026-07-25. MEASURED, in this order:
#   184516  click the message X, SLIC intact          -> OK 3/3
#   185144  no click at all, both auto-Messages gone  -> no advance at turn 1
#   190138  no click, SLIC restored (box IS on screen) -> no advance at turn 1
#   190445  click restored                            -> OK 4/4, closed=FALSE every turn
# The last row is the one that matters. The click NEVER closes the box, yet the
# turn only advances when it happens -- so what END TURN needs is not a cleared
# modal, it is a mouse message actually reaching the engine. An off-screen window
# that receives no pointer input at all leaves aui in a state where
# EndTurnButtonActionCallback takes its silent early-return, which is why the
# injected press resolved the LDL path and returned OK while nothing advanced.
#
# That falsifies the note I wrote at the top of this file's message branch, which
# asserted the dismissal clicks were pure collateral damage and could simply be
# dropped. They were load-bearing. Corrected rather than defended.
#
# But the user's complaint stands and is separate: those clicks were aimed at a
# close X that cannot be hit, so every one of them fell through onto the MAP and
# scrolled the view into unexplored black ("they would never just keep pushing
# down key into the unexplored area"). The fix is to keep the input, drop the
# aim: ping ONE inert spot every turn. TOP_BAR_INERT is the blank stretch of the
# top status bar between the Options menu and the gold counter -- background
# chrome, no widget, nothing to scroll.
TOP_BAR_INERT = (600, 6)


def engine_ping(inp):
    """Post pointer MOVEMENT (no buttons) so aui sees input before END TURN.

    Require:   inp is the harness input poster for the game window.
    Guarantee: only WM_MOUSEMOVE is posted -- never a button message -- so this
               cannot press, activate, scroll, or select anything, at any client
               geometry.
    Failure:   none.

    MEASURED 2026-07-26, and this is the fix for the turn-0 0xC0000005 that ate
    a whole session. The old body was `inp.click(*TOP_BAR_INERT)` with
    TOP_BAR_INERT = (600, 6) -- an ABSOLUTE capture constant, the documented
    recurring defect class in this file (fifth instance). At the 1024x768-content
    geometry it lands on blank top-bar chrome; at a 1024x1280 client the UI
    REFLOWS (it does not letterbox) and that same point is no longer inert, and
    the posted BUTTON killed the process. Isolation: `UIWALK_NO_PING=1` on the
    identical run turned a hard 0xC0000005 at turn 0 into a clean
    TURN_DID_NOT_ADVANCE_AT_1 -- crash gone, and the turn correctly failing to
    advance, which is exactly what the ping exists to fix.

    The requirement was never "click something". The memory entry says it
    precisely: an injected END TURN press only advances if SOME mouse message
    reached the engine that turn. A move IS a mouse message, carries no button,
    and therefore has no aim to get wrong -- which retires the whole
    stale-absolute-coordinate class here rather than re-tuning the constant.
    """
    if os.environ.get("UIWALK_NO_PING"):
        print("  [ping] SUPPRESSED (UIWALK_NO_PING)", flush=True)
        return
    hwnd = inp.hwnd
    for x, y in (TOP_BAR_INERT, (TOP_BAR_INERT[0] + 3, TOP_BAR_INERT[1] + 3)):
        win32api.PostMessage(hwnd, win32con.WM_MOUSEMOVE, 0,
                             win32api.MAKELONG(int(x), int(y)))
        time.sleep(0.05)

# MEASURED 2026-07-25 (runs/20260725-062519-turnloop/turn_006.png): TWO DIFFERENT
# SURFACES stack, and each has its close control somewhere else. The plain
# Message() window sits at the top with an X at MSG_CLOSE_CAPTURE; an `alertbox`
# segment (MAGIC STATUS) renders BELOW it with a labelled Close button instead.
# Clicking only the X drains the message queue and leaves the alertbox up -- and
# the alertbox is MODAL, so END TURN is dead while it is on screen. That was the
# whole TURN_DID_NOT_ADVANCE_AT_6 stall.
RESEARCH_OK_LDL = "SciAdvanceScreen.Background.BackButton"  # captioned str_ldl_CAPS_OK
_RESEARCH_INJECT_DEAD = False   # latched True once an inject fails to close the box
# (_ALERT_DISMISS_DEAD removed 2026-07-26. It latched "this box can never be
# closed" after one failed minimize, on the false premise that clicking an
# alertbox arm is process-lethal here. There IS a second channel: click the
# frame-measured Close arm centre at the identity send scale. See dismiss_message.)

# In DECLARATION order from messagebox.ldl:10 -- LeftButton (xpix 220) is the
# rightmost on screen and is the OK/close arm for a one-button SLIC message.
# Tried in order; the first one whose press changes the surface signature wins.
# CORRECTED 2026-07-25 from ENGINE SOURCE, not from another guess.
#
# The four MessageBoxDialog.* paths below (kept last, as fallbacks) all resolved
# to nothing, and I concluded from that "a SLIC Message() window is built at
# runtime, so there is no named LDL node to press". That conclusion was WRONG,
# and it was wrong in the way the instrument-before-environment lesson names: I
# inferred a property of the engine from four misses instead of reading the code
# that builds the window.
#
# What the code actually says (ctp2_code/ui/interface/messagewindow.cpp):
#   - InitCommon() line ~114 hard-codes  windowBlock = "StandardMessageWindow"
#     -- MessageBoxDialog is a DIFFERENT, engine-owned dialog, which is why every
#     path under it missed.
#   - line 117 calls CreateStandardMinimizeButton(windowBlock), which at line 330
#     builds the child block "StandardMessageWindow.StandardMinimizeButton" and
#     news an aui_Button on it.
#   - aui_Region::InitCommonLdl (aui_region.cpp:299) calls aui_Ldl::Associate()
#     with that exact string, so the button IS in the by-string lookup table that
#     aui_Ldl::GetObject -- and therefore inject_press -- searches.
#   - CreateStandardDismissButton exists but is NOT called from InitCommon, so
#     the corner glyph a human clicks on one of these windows is the MINIMIZE
#     button. Its action (messageactions.cpp:104) does ShowWindow(FALSE) and then
#     promotes the next unread instant message. That is precisely the human
#     behaviour being asked for: the box goes away, the queue keeps draining.
#
# Injection is also the SAFE channel here: it never touches the mouse, so the
# recorded process-lethal x1.25 click on this surface is not in play at all.
MESSAGE_CLOSE_LDL = (
    "StandardMessageWindow.StandardMinimizeButton",
    "StandardMessageWindow.StandardDismissButton",
    "MessageBoxDialog.DialogBackground.LeftButton",
    "MessageBoxDialog.DialogBackground.RightButton",
    "MessageBoxDialog.LeftButton",
    "MessageBoxDialog.RightButton",
)
_MSG_LDL_LATCH = [None]   # first MESSAGE_CLOSE_LDL path observed to work

# SLIC ALERTBOX ARM -- injection path (added 2026-07-26, replaces the click).
#
# WHY NOT CLICK: a posted mouse BUTTON is process-lethal at the 1024x1280
# client. Measured 3 distinct pixels across 2 surfaces, 3 runs, every one
# 0xC0000005: engine_ping's (600,6) top bar, the Summon arm (302,383), and the
# Close arm (217,383) whose whole SLIC body is `Kill();`. A posted WM_MOUSEMOVE
# at the same geometry is safe. So it is CLICKING that is broken here, not the
# aim and not the send scale -- an identity-first send of x1.00, the exact pixel
# find_alert_buttons measured, died too. Both the "wrong scale" and the "arm
# body is the killer" theories are falsified by those runs.
#
# WHERE THE NAME COMES FROM (engine source, not guesswork):
#   - messagewindow.cpp:115  strcpy(windowBlock, "StandardMessageWindow")
#   - CreateResponses -> CreateSelectResponses -> MessageResponseStandard
#   - messageresponse.cpp:132
#       sprintf(buttonBlock, "%s.%s", ldlBlock, "StandardResponseButton");
#       ctp2_Button *button = new ctp2_Button(&errcode, aui_UniqueId(), buttonBlock);
#     and line 170 button->SetAction(action) -- so aui_Button::InjectPress falls
#     through its m_ActionFunc branch to m_action->Execute(), which is exactly
#     what a real click on the arm runs.
#
# ONLY THE FIRST-DECLARED ARM IS REACHABLE THIS WAY. Every arm is newed inside
# one loop with the SAME block string, and aui_Ldl::Associate keys the by-string
# table on hash(ldlBlock) -- duplicates collapse to a single entry, so
# GetObject() can only ever hand back one of them. Arms are built in
# GetButton(0..n) order, so the surviving entry is declaration index 0. In
# mom_msg.slc's MagicMenu that is Button(ID_MOM_MSG_BTN_SUMMON) -- the arm under
# test. decl_index != 0 has no injection path and falls back to the click.
#
# MEASURED 2026-07-26 (runs/20260725-222727): that path resolves to
# obj=00000000 -- the by-string table has no entry for it while the box is
# open. So the derivation above is right about WHERE the button comes from and
# wrong about it being addressable. The candidates below are a probe: each is
# injected in turn and H:\mom_hook.log records obj per path, so one run tells us
# which alertbox controls are in the table at all. None of them can be the
# Close arm (that arm shares StandardResponseButton's name), so a box that
# closes during this sweep closed because the SUMMON arm fired.
ALERT_ARM_LDL = "StandardMessageWindow.StandardResponseButton"
ALERT_ARM_LDL_CANDIDATES = (
    "StandardMessageWindow.StandardResponseButton",
    "StandardMessageWindow.StandardResponseDropdown",
    "StandardMessageWindow.StandardResponseDropdownItem",
    "StandardMessageWindow.StandardDontShowButton",
)
# MEASURED: of the six probed, only StandardMinimizeButton (obj=12D9C4B0) and
# the window itself (obj=12D88A78) are in the table -- and pressing the WINDOW
# casts an aui_Window to aui_Button and takes the process down (0xFFFFFFFF), so
# it is deliberately not a candidate. The four response-button names all return
# obj=00000000 while the box is visibly open, so a SLIC alertbox arm is not
# reachable by string at all. Minimize is not an arm: it hides the window
# without running any arm body, so it cannot stand in for the Summon press.
ALERT_CLOSE_CAPTURE = (160, 384)  # 'Close' button of the alertbox, capture coords
# The one alertbox control that IS in the aui_Ldl by-string table (obj=12D9C4B0,
# measured with the box open). Dismissal channel -- see dismiss_message().
ALERT_MINIMIZE_LDL = "StandardMessageWindow.StandardMinimizeButton"
ALERT_PROBE_CAPTURE = (200, 300)  # its interior, below the message window's extent


# PER-SURFACE, not global. This is the settled reading (2026-07-25); two earlier
# comment blocks in this file each declared the other "FALSIFIED" -- both were
# overreach, and neither derivation explains the measurement:
#
#   ONE run, 20260725-115723, 7/7 turns OK:
#       message surface  latched x0.80
#       alertbox surface latched x1.25
#
# Same window, same geometry, same run. No pure function of the window size can
# return two different answers, so the send transform is NOT derived from
# geometry. Two separate facts, do not collapse them:
#
#   1. GEOMETRY is 1:1. PrintWindow captures the engine's 1024x768 surface
#      blitted UNSCALED into the client's top-left (content bbox (0,0)-(1021,759)
#      at a 1280x960 client). Capture coords ARE engine coords.
#   2. The SEND scale is EMPIRICAL and per-surface. It is latched by clicking and
#      reading a pixel probe, never computed. See content_scale() -- which
#      measures (1) and must NOT be used as (2).
#
# x1.25 on the MESSAGE surface is process-lethal: 0xC0000005, 2/2 runs
# (20260725-120046 seeded first, 20260725-120210 reached as third candidate),
# 0/7 turns both times. Hence the per-surface candidate order below.
ENGINE_W = 1024   # the engine reasons in its own surface, never the client
SEND_SCALE = {}             # surface kind -> latched capture->send factor
SCALE_CANDIDATES = (0.80, 1.00, 1.25)

# Set by main() so _calibrate can dump one frame per candidate click. Without it
# a failed battery reports only "no candidate closed the box" and the evidence
# for WHY is gone with the process.
_CALIB_DEBUG_DIR = None


def content_scale(frame) -> float:
    """Measure the client/engine GEOMETRY ratio from one frame. Diagnostic only.

    DO NOT use this as the send factor. PrintWindow captures the engine's own
    1024x768 surface blitted UNSCALED into the top-left of the client, with black
    margins right and bottom (runs/20260725-115723 peek_unit_01.png: client
    1280x960, content bbox (0,0)-(1021,759)). That makes capture coords == engine
    coords, and this function returns capture_width/content_width = 1.25, the
    client-vs-engine ratio.

    The SEND transform is a different thing and is NOT a function of this number:
    the same run latched x0.80 on the message surface and x1.25 on the alertbox.
    Feeding this value to the message surface kills the process (0xC0000005, 2/2).
    _calibrate latches the send factor empirically per surface; this is printed
    beside it purely so a failed battery has the geometry on record.
    """
    m = frame.max(axis=2) > 25
    xs = np.nonzero(m.any(axis=0))[0]
    if len(xs) < 2:
        return 1.0
    content_w = int(xs.max()) + 1
    return round(frame.shape[1] / float(content_w), 4)


def _calibrate(game, inp, x, y, probe, what) -> bool:
    """Find the capture->send factor for THIS surface by trying candidates.

    Returns True when it ran (and therefore already issued the clicks), False
    when the factor is already known and the caller should click normally.

    MEASURE, DO NOT DERIVE (settled 2026-07-25). Successive attempts to compute
    this factor from window geometry -- both ENGINE_W/capture_width (x0.80) and
    capture_width/content_width (x1.25) -- are refuted by a single run in which
    the message surface latched x0.80 and the alertbox latched x1.25. Same
    window, same frame, two answers. Geometry is real (see content_scale) but the
    send transform is not a pure function of it.

    So: try candidates, cheapest-safe FIRST, and read a pixel probe after each.
    Never a frame delta -- a missed click lands on the map, repaints, and
    produces a large delta indistinguishable from a hit. A wrong probe is not
    free: an off-panel click kills the process with 0xC0000005, which is why the
    lethal candidate is excluded outright on the message surface rather than
    merely ordered last.
    """
    if what in SEND_SCALE:
        return False
    SEND_SCALE[what] = 1.0      # provisional, so a total failure never re-runs
    frame0 = game.screenshot()
    sig0 = _surface_sig(frame0, what)
    # DO NOT seed the order from content_scale(). It derives x1.25 correctly from
    # the geometry, and sending x1.25 on the MESSAGE surface killed the process
    # with 0xC0000005 on the first click (run 20260725-120046, 0/7 turns). The
    # geometry is real; the send transform is NOT a pure function of it, and it is
    # demonstrably per-surface: message latches x0.80, alertbox latches x1.25 in
    # the same run (20260725-115723, 7/7 OK). Cheapest-safe candidate FIRST, and
    # measure -- a derived value is a hypothesis, and here it is a lethal one.
    derived = content_scale(frame0)
    # PER-SURFACE candidate lists, and x1.25 is BANNED on the message surface:
    # it killed the process with 0xC0000005 twice (20260725-120046 seeded first,
    # 20260725-120210 reached as the third candidate), 0/7 turns both times.
    # x0.80 does not always register on the first post, so try it twice before
    # falling through to x1.00 -- a repeat of a KNOWN-safe candidate is free,
    # whereas advancing to the lethal one ends the run.
    order = (0.80, 0.80, 1.00) if what == "message" else SCALE_CANDIDATES
    # IDENTITY FIRST WHEN THE GEOMETRY IS 1:1, added 2026-07-26.
    # This does NOT re-derive the factor from geometry -- the candidate set is
    # unchanged and the winner is still decided by the pixel probe. It only
    # reorders, and only when capture_w == content_w, i.e. the capture IS the
    # engine surface at 1:1 and x1.00 sends the exact pixel we measured.
    #
    # MEASURED (runs/20260725-221437): at a 1024x1280 client, capture_w=1024 and
    # geometry says x1.000, yet the battery still opened on x0.80 -- (302,383)
    # sent as (241,306) -- and the process died with 0xC0000005 before the first
    # post-candidate screenshot (the calib dump was armed and wrote nothing).
    # The x0.80/x1.25 candidates were latched on runs whose capture and content
    # geometry DISAGREED (1280-wide capture over a 1024-wide surface); at 1:1
    # they are pure misses -- and MISSING is what kills on this surface. The
    # earlier "a posted mouse BUTTON is lethal here on ANY pixel" reading is
    # FALSIFIED: all three deaths behind it were sends this battery produced at
    # x0.80, i.e. off-target, before this reorder existed. With identity first,
    # runs/20260725-232412 clicked the Summon arm centre at x1.00, closed=True,
    # the arm body ran, and the next turn read "A Guardian Spirit manifests in
    # your capital." -- 6/6 turns, 0 SLIC errors, no AV. This reorder is not
    # cosmetic; it is the whole difference between a hit and a crash.
    if abs(derived - 1.0) < 0.01:
        order = tuple([1.00] + [f for f in order if f != 1.00])
    print(f"  [calib] {what}: capture_w={frame0.shape[1]} "
          f"geometry_would_say x{derived:.3f}; order={order}", flush=True)
    for factor in order:
        inp.click(int(x * factor), int(y * factor))
        time.sleep(1.0)
        uiwalk.wait_stable(game, 4000)
        after = game.screenshot()
        if _CALIB_DEBUG_DIR is not None:
            cv2.imwrite(str(_CALIB_DEBUG_DIR /
                            f"calib_{what}_x{factor:.2f}.png"), after)
        # Success is PER-SURFACE (corrected 2026-07-25):
        #   message  -> the signature CHANGED. Unread messages QUEUE, so closing
        #               the top one reveals the next and "no box" is wrong.
        #   alertbox -> the box is GONE. Every arm ends in Kill(), and a MISS
        #               lands on the map, whose repaint can move find_alert_box's
        #               connected region and so flip a signature test. That false
        #               positive is what latched x1.00 in 20260725-115055 and then
        #               reported closed=False one line later.
        if (not alert_box_open(after)) if what == "alertbox" \
                else (_surface_sig(after, what) != sig0):
            SEND_SCALE[what] = factor
            print(f"  [calib] {what}: send = capture x{factor:.2f}", flush=True)
            return True
    print(f"  [calib] {what}: NO candidate closed the box "
          f"(tried {order})", flush=True)
    return True


def find_msg_box(frame):
    """Bounding box of the BeginTurn message window in CAPTURE coords, or None.

    MEASURED 2026-07-25 (runs/20260725-074655-turnloop): the previous version
    took min/max over EVERY bright pixel in the search region, which silently
    unioned the window with anything else bright in frame -- and as fog lifts,
    revealed terrain (sand/grass, all channels > 140) enters that region. The
    box's true right edge is 510; from turn 10 on the union reported 941-1078,
    so the X-button search aimed ~400px right of the real X and every click
    landed on the map. Turn 0 passed only because the map was still black,
    which is why this went unnoticed while it was already broken.

    Fix: take the CONNECTED parchment region anchored at the window's top-left,
    not a global bbox. Terrain elsewhere cannot contribute to it.
    """
    if frame is None:
        return None
    h, w, _ = frame.shape
    # Search region excludes the top ~30 rows (the menu bar is parchment too).
    ry0, rx1 = 30, int(w * 0.45)
    region = frame[ry0:int(h * 0.35), :rx1]
    mask = (region.min(axis=2) > 140).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    best = None
    for i in range(1, n):
        x, y, cw, ch, area = (int(v) for v in stats[i])
        if area < 5000 or cw < 100 or ch < 40:
            continue
        # The window is anchored to the top-left of the client area. Terrain is
        # not: it appears mid/right and low in the region.
        if x > w * 0.05 or y > h * 0.10:
            continue
        if best is None or area > best[4]:
            best = (x, y, cw, ch, area)
    if best is None:
        return None
    x, y, cw, ch, _ = best
    return (x, ry0 + y, x + cw - 1, ry0 + y + ch - 1)


def find_msg_close(frame):
    """Locate the message window's X button in CAPTURE coords, per frame.

    MEASURED 2026-07-25: the same lesson as send_scale, applied to POSITION.
    MSG_CLOSE_CAPTURE was authored against a 1024-wide capture. On a 2400-wide
    capture of the same 1920x1080 client the X sits at (504, 57), while the
    constant scaled to (398, 49) in send space against a true target of
    (403, 46) -- roughly one button-half off, which is exactly the difference
    between a hit and the "closed=False" clicks on the map behind it.

    Derive it instead: find the parchment box (skipping the menu bar in the top
    ~30 rows, which is parchment too), then take the dark X glyph in the box's
    top-right corner. Returns None when no box is visible.

    MEASURED 2026-07-25 (second correction): the mean-of-all-dark-pixels form
    was itself off-target. The band ran to x1+8, so it swallowed the window's
    dark OUTER FRAME column -- a 7x45 slab of dark pixels that outweighs the
    23x15 glyph and drags the centroid right. On turn_002.png that produced
    (506,59) against a true glyph centre of (493,53): past the button's right
    edge, hence every closed=False. Fix: stay INSIDE the box, and take the
    centroid of the best dark CONNECTED COMPONENT rather than of every dark
    pixel, rejecting anything frame-shaped (tall/thin or spanning the band).

    MEASURED 2026-07-25 (third correction -- this is the one that held): keying
    the band off box.x1 was still wrong, because find_msg_box's right edge is not
    the PANEL's right edge. The window casts a dark DROP SHADOW to its right and
    below; on the live frame the box measured x1=575 while the parchment actually
    ends at ~510. The 70px band at x1-70 therefore sat entirely inside the shadow
    -- one solid dark blob, every component rejected, "X never resolved" forever,
    even though the very same detector resolved (493,53) on a saved PNG whose
    shadow happened to fall outside the threshold. Fix: stop trusting the right
    edge. Scan the WHOLE top strip of the box and take the RIGHTMOST glyph-shaped
    dark component. Shadow slabs fail the cw<=40 / ch<=30 test, so they cannot win
    regardless of where the box edge landed.
    """
    box = find_msg_box(frame)
    if box is None:
        return None
    x0, y0, x1, y1 = box
    if os.environ.get("UIWALK_AIM_BODY"):
        # DISCRIMINATOR ONLY (2026-07-25): aim at inert parchment instead of the
        # X. If the engine survives this and dies on the X, the 0xC0000005 is the
        # close path (SLIC/window teardown), not "clicks crash the game".
        return ((x0 + x1) // 2, y0 + 100)
    bx0 = x0
    band = frame[y0:y0 + 45, bx0:x1 + 1]
    mask = (band.max(axis=2) < 110).astype(np.uint8)
    n, _, stats, cen = cv2.connectedComponentsWithStats(mask, 8)
    # LARGEST glyph-shaped component, not the rightmost. MEASURED 2026-07-25:
    # the X is drawn with a drop shadow, so the band holds TWO glyph-shaped
    # blobs -- the glyph itself (23x15, area 186) at (493,53) and its shadow
    # (26x18, area 59) at (501,57). Rightmost picks the shadow, which sits off
    # the button on the window frame; clicking there crashed the engine
    # (0xC0000005) on the very next run. Area discriminates them cleanly.
    best, best_area = None, 0
    for i in range(1, n):
        _, _, cw, ch, area = (int(v) for v in stats[i])
        if area < 40:
            continue
        if ch >= band.shape[0] - 2 or cw < 6 or ch < 6:
            continue          # frame edge / speck
        if cw > 40 or ch > 30:
            continue          # too big to be the glyph (shadow slab, title text)
        if area > best_area:
            best, best_area = i, area
    if best is None:
        # NO GUESSING. MEASURED 2026-07-25: the old corner-inset fallback fired
        # on a transient mid-fade frame whose box measured 60px wider, aimed at
        # (569,57), and the resulting click crashed the engine (0xC0000005) twice
        # in a row. A guessed target is worse than no target -- the caller waits
        # for a settled frame and re-reads instead.
        return None
    return (bx0 + int(round(cen[best][0])), y0 + int(round(cen[best][1])))


def alert_box_open(frame) -> bool:
    """True when an alertbox segment is up.

    DERIVED, not probed (corrected 2026-07-25). The old body sampled the single
    absolute pixel ALERT_PROBE_CAPTURE = (160,384) -- the FOURTH absolute capture
    constant in this file to go stale. At the restored 1280x960 geometry the box
    measures (15,237)-(360,386), so that probe sits 2px inside the bottom border:
    a caption change of one line moves the box and the probe reads the map. It
    then reports "still open" on an arm click that worked, which is exactly the
    SUMMON_ARM_CLICK_FAILED_AT_3 signature. Reuse the same connected-region
    finder the click target comes from, so "open" and "where to click" can never
    disagree.
    """
    return find_alert_box(frame) is not None


def find_alert_box(frame):
    """Bounding box of the alertbox parchment in CAPTURE coords, or None.

    MEASURED 2026-07-25 (runs/20260725-084849-turnloop/turn_005_magic.png):
    (15,237) 346x150. Distinguished from the BeginTurn message window, which is
    the other top-left parchment region, by sitting BELOW it (y > 10% of height);
    find_msg_box requires the opposite. Derived, not constant -- absolute capture
    coordinates are the documented recurring defect class in this file.
    """
    if frame is None:
        return None
    h, w, _ = frame.shape
    mask = (frame.min(axis=2) > 140).astype(np.uint8)
    n, _labels, stats, _c = cv2.connectedComponentsWithStats(mask, 8)
    best = None
    for i in range(1, n):
        x, y, cw, ch, area = (int(v) for v in stats[i])
        if area < 20000 or cw < 150 or ch < 60:
            continue
        if x > w * 0.10 or y < h * 0.10 or y > h * 0.45:
            continue
        if best is None or area > best[4]:
            best = (x, y, cw, ch, area)
    if best is None:
        return None
    x, y, cw, ch, _ = best
    return (x, y, x + cw - 1, y + ch - 1)


def find_alert_buttons(frame):
    """Centres of the alertbox's buttons, LEFT TO RIGHT, in CAPTURE coords.

    Buttons are the dark glyph runs in the bottom band of the parchment. Found
    per frame rather than pinned as fractions so a caption change (which changes
    every button's width AND position) cannot silently move the aim point.

    ORDERING RULE, measured on turn_005_magic.png: the engine lays buttons out in
    REVERSE declaration order. mom_msg.slc declares Random, Research, Goal, Close
    and they render Close, Goal, Research, Random. So declaration index i is
    result[-(i+1)] -- see click_alert_arm.
    """
    box = find_alert_box(frame)
    if box is None:
        return []
    x0, y0, x1, y1 = box
    bh = y1 - y0
    band = frame[y0 + int(bh * 0.84):y0 + int(bh * 0.98), x0:x1 + 1]
    if band.size == 0:
        return []
    dark = (band.max(axis=2) < 120).astype(np.uint8)
    col = dark.sum(axis=0)
    runs, s = [], None
    for i, v in enumerate(list(col) + [0]):
        if v > 0 and s is None:
            s = i
        elif v == 0 and s is not None:
            if i - s > 8:
                runs.append((s, i))
            s = None
    cy = y0 + int(bh * 0.927)
    return [(x0 + (a + b) // 2, cy) for a, b in runs]


def click_alert_arm(game: uiwalk.Game, inp, decl_index: int, label: str) -> bool:
    """Click the alertbox button DECLARED at decl_index (0 = first Button block).

    Returns True when the box closed (every arm ends in Kill()), which is the
    only honest success test -- a missed click lands on the map, repaints, and
    produces a frame delta indistinguishable from a hit.
    """
    frame = game.screenshot()
    buttons = find_alert_buttons(frame)
    if len(buttons) <= decl_index:
        print(f"  [arm] {label}: only {len(buttons)} buttons found, need "
              f"index {decl_index}", flush=True)
        return False
    x, y = buttons[-(decl_index + 1)]
    print(f"  [arm] {label}: buttons={buttons} target_capture=({x},{y})", flush=True)

    # INJECTION FIRST -- see ALERT_ARM_LDL. Only decl_index 0 is addressable.
    if decl_index == 0:
        for path in ALERT_ARM_LDL_CANDIDATES:
            uiwalk.inject_press(game.hwnd, path)
            time.sleep(0.6)
            if not alert_box_open(game.screenshot()):
                print(f"  [arm] {label}: closed=True via inject {path}",
                      flush=True)
                return True
        print(f"  [arm] {label}: all inject candidates missed", flush=True)

    if not _calibrate(game, inp, x, y, alert_box_open, "alertbox"):
        inp.click(int(x * SEND_SCALE["alertbox"]), int(y * SEND_SCALE["alertbox"]))
    time.sleep(1.0)
    uiwalk.wait_stable(game, 6000)
    closed = not alert_box_open(game.screenshot())
    print(f"  [arm] {label}: closed={closed}", flush=True)
    return closed


def message_box_open(frame) -> bool:
    """True when the BeginTurn message box is up.

    Derived from the same connected region the close button is taken from, so
    "open" and "where to click" can never disagree. The old absolute probe pixel
    MSG_PROBE_CAPTURE was authored at 1024 wide -- the third absolute capture
    constant in this file to go stale (click target, date region, this).
    """
    return find_msg_box(frame) is not None


def find_research_box(frame):
    """Bounding box of the modal RESEARCH dialog in CAPTURE coords, or None.

    MEASURED 2026-07-25 (runs/20260725-083632-turnloop/turn_018.png): when an
    advance completes the engine puts up a modal "Select a new Advance to begin
    researching" dialog with a CHANGE-TO listbox and Goal / OK buttons. It is
    NOT the BeginTurn message window -- find_msg_box deliberately requires the
    top-left anchor, and this one is CENTRED -- so dismiss_message had no surface
    for it, broke out of its loop, and the end-turn click landed on the modal.
    That is the whole TURN_DID_NOT_ADVANCE_AT_18 stall.

    Detected by shape, not by absolute pixels (absolute capture constants are
    the documented recurring defect class in this file -- four instances so far):
    a large bright connected region sitting away from the top-left, tall enough
    to exclude the control panel (which is wide but short).
    """
    if frame is None:
        return None
    h, w, _ = frame.shape
    mask = (frame.min(axis=2) > 140).astype(np.uint8)
    n, _labels, stats, _cent = cv2.connectedComponentsWithStats(mask, 8)
    best = None
    for i in range(1, n):
        x, y, cw, ch, area = (int(v) for v in stats[i])
        if cw < w * 0.10 or ch < h * 0.25:
            continue
        if x < w * 0.15 or y < h * 0.10:
            continue        # top-left anchored => that's the message window
        if ch <= cw:
            continue        # the research dialog is PORTRAIT (415x518). The BUILD
                            # MANAGER also passes every other test here (792x345 in
                            # turn_000_founded.png) and is landscape -- without this
                            # the "OK" fraction would land on its Clear button.
        # ASPECT BAND, added 2026-07-26 -- this is the fix for the turn-0
        # 0xC0000005. MEASURED: at a 1024x1280 client the old gates matched a
        # 154x351 sliver of bottom chrome (aspect 0.44, cw/w 0.15). "Portrait"
        # alone is not enough: a SLIVER is portrait too. dismiss_message then
        # injected press:SciAdvanceScreen...BackButton into a screen that was
        # NOT open, and injecting at a UI object on a closed screen is
        # process-lethal (same class as the unbounded SelectItem). The real
        # dialog is 415x518 -> aspect 0.80, so require the aspect to actually
        # look like it.
        #
        # Aspect is the ONLY new gate on purpose. My first attempt also raised
        # the width floor to w*0.25 -- that rejected the known TRUE positive
        # (turn_018.png, a 2400x1350 capture where the 415-wide dialog is only
        # 0.17 of the frame), because a fraction-of-CAPTURE floor is meaningless
        # when the capture size varies. Caught by running the battery, which is
        # why the battery includes a positive and not just the failing case.
        if not (0.60 <= cw / float(ch) <= 0.95):
            continue
        if best is None or area > best[4]:
            best = (x, y, cw, ch, area)
    if best is None:
        return None
    x, y, cw, ch, _ = best
    return (x, y, x + cw - 1, y + ch - 1)


def research_box_open(frame) -> bool:
    return find_research_box(frame) is not None


def find_research_ok(frame):
    """Centre of the dialog's OK button, in CAPTURE coords, or None.

    Expressed as a FRACTION of the detected box, never as a fifth absolute
    constant. Measured from turn_018.png: box (750,273) 415x518, OK centre
    (1110,776) -> (0.867, 0.971) of the box.
    """
    box = find_research_box(frame)
    if box is None:
        return None
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    return (x0 + int(bw * 0.867), y0 + int(bh * 0.965))


def render_rect(frame):
    """Bounding box of the engine's rendered surface inside the capture.

    MEASURED 2026-07-25: at 1024x768 windowed on a 125%-DPI desktop the client
    is 1280x960 but the engine blits its 1024x768 surface UNSCALED into the
    TOP-LEFT corner; everything right of x~1021 and below y~759 is pure black.
    So capture coords == engine coords here. That is a statement about GEOMETRY
    only -- it says nothing about the send scale, which is latched per surface by
    _calibrate. Any fraction meant to address a UI widget must be taken of THIS
    rect, not of the capture.
    Self-calibrating: it is just the bbox of non-black content, which degrades
    to the whole frame when the surface does fill the client.
    """
    if frame is None:
        return (0, 0, 0, 0)
    h, w, _ = frame.shape
    m = frame.max(axis=2) > 30
    ys, xs = np.nonzero(m)
    if len(xs) == 0:
        return (0, 0, w - 1, h - 1)
    return (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))


_BOX_FINDER = {"message": find_msg_box,
               "alertbox": find_alert_box,
               "research": find_research_box}


def _surface_sig(frame, what):
    """Identity of the surface currently up, or None when it is gone.

    MEASURED 2026-07-25: "is a box still open?" is the WRONG success test.
    Unread SLIC messages QUEUE. Closing the top one immediately reveals the next,
    so the probe answers True on a click that worked perfectly -- the loop then
    reports closed=False and breaks one box short. Observed on turn_001.png: the
    click founded the city AND rolled 4000BC -> 3975BC, yet was scored a miss
    because a fresh magic-status window had taken the closed one's place.

    Signature = box geometry + a coarse hash of its interior, so a REPLACEMENT
    reads as progress while an unchanged box still reads as a miss.
    """
    box = _BOX_FINDER[what](frame)
    if box is None:
        return None
    x0, y0, x1, y1 = box
    crop = frame[y0:y1 + 1, x0:x1 + 1]
    if crop.size == 0:
        return (box, 0)
    small = cv2.resize(crop, (16, 16), interpolation=cv2.INTER_AREA)
    return (box, int(small.astype(np.int64).sum()))


def date_rect(rx0, ry0, rx1, ry1):
    """The date widget's box, as BOTTOM-ANCHORED offsets of the render rect.

    MEASURED 2026-07-26. DATE_FRACTION (a fraction of the render HEIGHT) is
    correct only while the render is 768 tall. The engine REFLOWS its in-game UI
    to the client size -- it does not letterbox a fixed surface -- so at a
    1024x1280 client the control panel moves to the BOTTOM of a 1280-tall frame
    while a height-fraction crop stays at 0.857*1280 = y1097, ~85px above the
    widget. That crop sat on static chrome, so date_changed returned False on a
    turn that HAD advanced (gold 106 -> 175, science 0 -> 15, date 4000BC ->
    3925BC in the very same frame pair) and the run failed
    TURN_DID_NOT_ADVANCE_AT_1 on a healthy game.

    The control panel is BOTTOM-anchored chrome of a FIXED pixel height, so the
    widget's distance from the bottom edge is invariant across both geometries
    where a fraction of the height is not. Offsets derived from the known-good
    1024x768 numbers (x 478..556, y 658..690 -> 110..78 px above the bottom) and
    verified to frame the date exactly at 1024x1280.
    """
    h = ry1 - ry0 + 1
    x0, x1 = rx0 + 478, rx0 + 557
    y1 = ry0 + h - 78
    y0 = ry0 + h - 110
    return (x0, y0, x1, y1)


def date_changed(a, b) -> bool:
    """Positive turn-advance assertion: the date widget's pixels differ.

    WHY NOT A WHOLE-FRAME DELTA: a full-frame diff is non-zero for unit
    animation, fog reveal, or a popup opening -- none of which mean the turn
    advanced. MEASURED 2026-07-25: an end-turn blocked by the modal gave
    delta=0, but a *successful* end-turn is only distinguishable from a
    cosmetic change by the date actually rolling (4000BC -> 3975BC). Verdict OK
    must never be reachable without this.
    """
    if a is None or b is None or a.shape != b.shape:
        return False
    rx0, ry0, rx1, ry1 = render_rect(a)
    x0, y0, x1, y1 = date_rect(rx0, ry0, rx1, ry1)
    return frame_delta(a[y0:y1, x0:x1], b[y0:y1, x0:x1]) > 0


def dismiss_message(game: uiwalk.Game, inp) -> int:
    """Close the SLIC message box left open at BeginTurn; return the frame delta.

    WHY THIS IS LOAD-BEARING: mom_magic's BeginTurn Message() puts a message box
    on screen at game start and it STAYS UP. MEASURED 2026-07-25: with it open,
    both an end-turn press (obj resolved, InjectPress OK) and a MagicButton
    uitrigger (trig found, enabled=1, RunUITriggers OK) produced delta=0 for 20-90
    seconds. Two unrelated mechanisms silenced at once is a downstream block, not
    two coincidental control bugs -- the modal is that block.

    L7: clicks DO reach in-game SLIC surfaces (unlike menus, where aui polls
    GetCursorPos and only injection works). The send scale is NOT a fixed law --
    it is latched per surface by _calibrate; see the SEND_SCALE header block.

    MEASURED 2026-07-25: boxes STACK. Once the spellbook prompt starts firing
    (mana crosses 60% of max, ~turn 5), a turn begins with TWO modals up --
    mom_magic's per-turn status and mom_spells' spellbook. Closing one leaves the
    other, the end-turn click lands on it instead of the button, and the loop
    reports TURN_DID_NOT_ADVANCE with a large delta (the delta is the box closing,
    not the turn advancing). So: close until the surface is clear, not once.
    """
    global _RESEARCH_INJECT_DEAD
    total = 0
    misses = 0
    # Cap raised 6 -> 30 (2026-07-25): six was not enough by turn 6. Unread SLIC
    # messages QUEUE, they do not replace each other, so the backlog grows with
    # the turn count. The loop still exits early the moment the surface is clear.
    for _ in range(30):
        before = game.screenshot()
        # Each surface gets its OWN close control -- see ALERT_CLOSE_CAPTURE.
        # ALERTBOX FIRST, measured 2026-07-25: it is MODAL and swallows clicks
        # aimed at the message window behind it, so closing in the other order
        # gives delta=0 with both boxes still up (that read as "click had no
        # effect" and ended the loop one box short, stalling END TURN at turn 6).
        # SEND SCALE IS PER-SURFACE and LATCHED, never assumed. ui_map.json
        # L9_alertbox_interactivity recorded the alertbox as 1:1; the 20260725-115723
        # run latched it at x1.25 while the message surface latched x0.80 in the
        # same run. Both are observations of a value that is measured per surface,
        # not evidence for a constant -- so do not hard-code either here. A wrong
        # factor misses the button and lands on the MAP, which repaints and yields
        # a large frame delta that reads as success. Never take delta alone as a hit.
        if alert_box_open(before):
            x, y = ALERT_CLOSE_CAPTURE
            what = "alertbox"
        elif research_box_open(before):
            # Modal advance-selection dialog: dismissed by OK (keeps the engine's
            # own default pick), not by an X -- it has no close glyph.
            x, y = find_research_ok(before)
            what = "research"
        elif message_box_open(before):
            target = find_msg_close(before)
            if target is None:
                # Unsettled frame: box present, X not resolvable. Re-read rather
                # than click a guess (a guessed target crashed the engine).
                misses += 1
                if misses > 5:
                    print("  [aim] message: X never resolved, giving up "
                          f"(box={find_msg_box(before)} shape={before.shape})",
                          flush=True)
                    cv2.imwrite(str(uiwalk.RUNS / "aim_fail.png"), before)
                    np.save(str(uiwalk.RUNS / "aim_fail.npy"), before)
                    break
                uiwalk.wait_stable(game, 4000)
                time.sleep(1.0)
                continue
            x, y = target
            what = "message"
        else:
            break
        probe = {"alertbox": alert_box_open,
                 "research": research_box_open,
                 "message": message_box_open}[what]
        if what == "research":
            # MEASURED 2026-07-25: every send scale (1.25/1.00/0.80) aimed at the
            # OK button left the dialog up. This is an ENGINE aui window, not a
            # SLIC alertbox -- the settled rule applies (aui polls GetCursorPos,
            # so synthetic clicks are dead here exactly as in the main menus).
            # Drive it by LDL injection instead. Path from science.ldl:421-440,
            # where BackButton is the one captioned str_ldl_CAPS_OK.
            # PROCESS-WIDE latch, added 2026-07-26. `if not gone: break` below
            # only stops re-injection WITHIN one dismiss_message call -- the
            # crashing run injected twice because dismiss_message is called
            # again next turn. A research inject that leaves the box "open" is
            # proof the detection was a false positive (the real dialog always
            # closes), so never inject again this process.
            if _RESEARCH_INJECT_DEAD:
                print("  [aim] research -> SUPPRESSED (a prior inject did not "
                      "close it => detection is a false positive)", flush=True)
                break
            print(f"  [aim] research -> inject press:{RESEARCH_OK_LDL}", flush=True)
            uiwalk.inject_press(game.hwnd, RESEARCH_OK_LDL)
            time.sleep(1.0)
            uiwalk.wait_stable(game, 6000)
            after = game.screenshot()
            d = frame_delta(before, after)
            gone = not probe(after)
            print(f"dismiss research -> delta={d} closed={gone}", flush=True)
            total += d
            if not gone:
                _RESEARCH_INJECT_DEAD = True
                break
            continue
        if what == "alertbox":
            # TRY INJECTION FIRST, THEN CLICK. Injection costs nothing and needs
            # no aim, but it can only ever reach StandardMinimizeButton: a probe
            # with the box visibly open returned obj=00000000 for all four
            # response-button names and obj=12D9C4B0 for minimize, because every
            # arm is newed from the same block string
            # "StandardMessageWindow.StandardResponseButton" and aui_Ldl keys the
            # by-string table on hash(ldlBlock). Minimize also does not reliably
            # clear a SLIC alertbox (the shared entry lands on whichever window
            # registered last), so the click fallback is the one that works.
            #
            # CORRECTED 2026-07-26. The previous body refused to click at all,
            # on the claim that a posted mouse BUTTON is process-lethal at a
            # 1024x1280 client on any pixel. That is FALSIFIED: all three deaths
            # behind it were sent by the calibration battery at x0.80 -- i.e.
            # misses -- and once _calibrate tries the IDENTITY factor first at
            # 1:1 geometry, a click on the arm centre find_alert_buttons measures
            # lands cleanly. Measured runs/20260725-232412: Summon arm clicked
            # at x1.00, closed=True, the arm body ran, and the next turn read
            # "A Guardian Spirit manifests in your capital." 6/6 turns, 0 SLIC
            # errors. It is MISSING that kills on this surface, not clicking.
            print(f"  [aim] alertbox -> inject press:{ALERT_MINIMIZE_LDL}",
                  flush=True)
            uiwalk.inject_press(game.hwnd, ALERT_MINIMIZE_LDL)
            time.sleep(1.0)
            uiwalk.wait_stable(game, 6000)
            after = game.screenshot()
            gone = not probe(after)
            total += frame_delta(before, after)
            if gone:
                print("dismiss alertbox -> closed=True via inject", flush=True)
                continue
            # AIM AT THE LAST-DECLARED ARM, NOT INDEX 0. Index 0 is the FIRST
            # declared arm, which in MagicMenu is Summon Creature -- dismissing a
            # box by firing its side-effecting arm would silently place orders
            # the run never asked for. Close is declared last in these boxes and
            # the engine renders in REVERSE declaration order, so it is the
            # LEFTMOST button and decl_index len-1. Both the count and the centre
            # come from this frame, so a caption change cannot move the aim.
            arms = find_alert_buttons(after)
            if not arms:
                print("  [aim] alertbox: no arms found to click", flush=True)
                break
            print(f"  [aim] alertbox: minimize did not clear it -- clicking the "
                  f"last-declared (Close) arm of {len(arms)}", flush=True)
            gone = click_alert_arm(game, inp, len(arms) - 1, "dismiss")
            total += frame_delta(before, game.screenshot())
            print(f"dismiss alertbox -> closed={gone}", flush=True)
            if not gone:
                break
            continue
        if what == "message" and not os.environ.get("UIWALK_MSG_NOINJECT"):
            # DEFAULT CHANNEL as of 2026-07-25. It was opt-in behind
            # UIWALK_MSG_INJECT while the candidate list held only
            # MessageBoxDialog.* paths, all of which missed -- see the corrected
            # header on MESSAGE_CLOSE_LDL for why they missed (wrong dialog) and
            # what the engine source says the real path is
            # (StandardMessageWindow.StandardMinimizeButton, associated into the
            # aui_Ldl by-string table at construction).
            #
            # Injection is preferred over clicking on this surface for a reason
            # that is measured, not stylistic: a x1.25 posted click here is
            # recorded process-lethal (0xC0000005). inject_press does not move or
            # read the cursor at all, so no send-scale is involved and no
            # candidate can be lethal. The click path is still available behind
            # UIWALK_MSG_CLICK if injection ever regresses.
            hit = False
            # Latch the path that worked and try it FIRST next time. Sweeping all
            # six every message costs ~7s each; on a 25-turn run with a growing
            # queue that dominates the wall clock. Same idea as SEND_SCALE's
            # per-surface latch: measure once, then reuse.
            order = MESSAGE_CLOSE_LDL
            if _MSG_LDL_LATCH[0] is not None:
                order = ((_MSG_LDL_LATCH[0],)
                         + tuple(p for p in MESSAGE_CLOSE_LDL
                                 if p != _MSG_LDL_LATCH[0]))
            for path in order:
                print(f"  [aim] message -> inject press:{path}", flush=True)
                uiwalk.inject_press(game.hwnd, path)
                time.sleep(1.0)
                uiwalk.wait_stable(game, 6000)
                after = game.screenshot()
                if _surface_sig(after, what) != _surface_sig(before, what):
                    d = frame_delta(before, after)
                    print(f"dismiss message -> delta={d} closed=True "
                          f"via {path}", flush=True)
                    total += d
                    hit = True
                    _MSG_LDL_LATCH[0] = path
                    break
            if hit:
                continue
            print("  [aim] message: no injection path cleared the box "
                  "-- falling through to the click path", flush=True)
        if what == "message" and not os.environ.get("UIWALK_MSG_CLICK"):
            # SETTLED 2026-07-25 -- DO NOT ADD ANOTHER CANDIDATE SCALE HERE.
            # A CTP2 Message window is an aui surface, and aui polls GetCursorPos
            # rather than reading posted mouse messages, so a PostMessage click
            # can never dismiss one. Every candidate (x0.80, x1.00, x1.25) left
            # closed=False; x1.25 additionally killed the process with
            # 0xC0000005. The earlier "x0.80 closes it" reading was a false
            # positive of exactly the kind _calibrate's own header warns about:
            # the click MISSED, fell through onto the map, and the resulting
            # repaint changed the surface signature.
            #
            # The DPI story is dead too -- measured capture 1280x960 and client
            # 1280x960, ratio 1.000, so the two spaces are identical and there is
            # no hidden scale factor left to find.
            #
            # The real cost of continuing to try: every miss lands on the map and
            # SCROLLS IT into unexplored black, which is the aimless panning the
            # user saw ("they would never just keep pushing down key into the
            # unexplored area"). So do not AIM here.
            #
            # CORRECTION, 2026-07-25. An earlier version of this comment went one
            # step further and called these clicks pure collateral damage that
            # could simply be dropped. That was WRONG and my own measurement
            # falsified it: removing them took the run from 4/4 to
            # TURN_DID_NOT_ADVANCE_AT_1, while the green run showed closed=False
            # on every turn. The click never dismisses the box, but END TURN
            # still needs a mouse message to have reached the engine. The input
            # is therefore kept -- redirected to TOP_BAR_INERT by engine_ping(),
            # which is fired once per turn right before end_turn(). Keep the
            # input, drop the aim.
            #
            # The upstream fix for the box itself is to not raise it at all --
            # the alive probe (scenario.slc) and the periodic magic popup
            # (mom_magic.slc) are removed for this reason, and player-facing
            # status lives on the 'j' alertbox, which IS dismissable.
            print(f"  [aim] message at ({x},{y}): aui surface, cannot be hit -- "
                  f"not aiming at it (engine_ping supplies the input)",
                  flush=True)
            break
        s = SEND_SCALE.get(what)
        cw, ch = game.client_size()
        print(f"  [aim] capture={before.shape[1]}x{before.shape[0]} "
              f"client={cw}x{ch} ratio={cw / before.shape[1]:.3f} {what} "
              f"target_capture=({x},{y}) scale={s}", flush=True)
        if os.environ.get("UIWALK_NO_CALIB"):
            # Bisect harness: send ONE click at a fixed scale, no sweep. This is
            # what separated "a click in this window crashes" from "the sweep's
            # x1.25 candidate crashes" -- the two were confounded in every run
            # until a single un-swept click isolated them. Verdict: x1.25 is
            # lethal on the message surface, x0.80 is not.
            # UIWALK_NO_CALIB may carry a scale: "1" means 1.0, or give a float.
            raw = os.environ["UIWALK_NO_CALIB"]
            sc = float(raw) if raw not in ("1", "") else 1.0
            print(f"  [aim] NO_CALIB single click scale={sc} -> "
                  f"({int(x * sc)},{int(y * sc)})", flush=True)
            inp.click(int(x * sc), int(y * sc))
        elif not _calibrate(game, inp, x, y, probe, what):
            inp.click(int(x * SEND_SCALE[what]), int(y * SEND_SCALE[what]))
        time.sleep(1.0)
        uiwalk.wait_stable(game, 6000)
        after = game.screenshot()
        d = frame_delta(before, after)
        # SUCCESS TEST IS THE SURFACE SIGNATURE, NOT THE DELTA and not a bare
        # is-open probe: a missed click that lands on the map repaints and gives
        # a big delta while the box is still up, while a HIT often reveals the
        # next queued message and so leaves a box on screen. See _surface_sig.
        gone = _surface_sig(after, what) != _surface_sig(before, what)
        print(f"dismiss {what} -> delta={d} closed={gone}", flush=True)
        total += d
        if not gone:
            break   # click is not reaching this surface; stop rather than spin
    return total


def alive(game: uiwalk.Game) -> bool:
    return game.proc is not None and game.proc.poll() is None


def boot(game: uiwalk.Game, run_dir: Path) -> list:
    """Walk main menu -> MoM scenario -> in-game, asserting each gate.

    Reuses steps/reach_in_game.json verbatim so the boot path stays ONE
    artifact; a divergence here would be a second, silently-drifting copy.
    """
    steps = json.loads((uiwalk.TOOL_DIR / "steps" / "reach_in_game.json").read_text())
    inp = uiwalk.PostInput(game)
    return uiwalk.run_steps(game, inp, steps, run_dir, baseline=False, dry=False)


def main() -> int:
    ap = argparse.ArgumentParser(description="Headless MoM turn-loop playthrough")
    ap.add_argument("--turns", type=int, default=25)
    ap.add_argument("--marker", default="MagicMenu")
    ap.add_argument("--settle-ms", type=int, default=25000, help="wait_stable budget per turn")
    ap.add_argument("--probe-every", type=int, default=5, help="press j (magic status) every N turns")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--diag", type=int, default=0,
                    help="diagnostic: press end-turn ONCE, then sample every 5s for N seconds")
    ap.add_argument("--endturn", choices=["button", "key", "none"], default="button")
    ap.add_argument("--press", default="", help="diag: inject press: on this LDL path instead of end-turn")
    ap.add_argument("--trigger", default="",
                    help="diag: fire the SLIC uitrigger bound to this LDL path (bare-name hook)")
    ap.add_argument("--dismiss", action="store_true",
                    help="click the BeginTurn message box closed before acting")
    ap.add_argument("--summon-arm", type=int, default=0, choices=[0, 1, 2],
                    help="INTERACTIVE SLIC TEST. 1 = MagicMenu's first declared "
                         "arm (Summon Creature). Opens the menu on --summon-turn, "
                         "clicks that arm, then captures the FOLLOWING turn's "
                         "opening frame -- the arm only writes a global, so "
                         "anything visible next turn was produced by the BeginTurn "
                         "consumer reading it across the turn boundary. "
                         "Choice 2 is GONE as of 2026-07-26: the menu used to "
                         "declare two hardcoded summon arms (Guardian, Zombies) "
                         "purely so link 7's readout could discriminate 'the "
                         "ordered unit appeared' from 'the handler always spawns "
                         "that unit'. Link 7 closed, and the leftover second arm "
                         "let a Life tribe raise zombies. One arm now; the "
                         "creature is resolved from the caster's sphere at spawn "
                         "time, and the result popup names it.")
    ap.add_argument("--summon-turn", type=int, default=3,
                    help="turn on which to place the summon order")
    ap.add_argument("--found-city", action="store_true",
                    help="press SETTLE ('b') on the starting peasant before turn 1, "
                         "so the player owns a city and M3's auto-summon can fire")
    ap.add_argument("--build-unit", type=int, default=-1,
                    help="MAP-ART PROBE: with --found-city, select this row of the "
                         "build manager's UnitsList and Add it to the queue instead "
                         "of closing the window empty. A freshly founded city builds "
                         "NOTHING by default (measured: 'Nothing Building', empty "
                         "queue), so without this no unit is ever produced and "
                         "'the unit is missing from the map' is untestable. "
                         "The hook bounds-guards SelectItem (aui_sdl.cpp logs "
                         "'INJECT select REFUSED' and no-ops an out-of-range "
                         "index), so a bad row is a silent no-op, not a crash -- "
                         "but check H:/mom_hook.log for REFUSED before trusting "
                         "an empty-queue result.")
    ap.add_argument("--peek-units", type=int, default=0,
                    help="ART PROBE: on this turn, cycle 'n' and photograph each "
                         "selected unit in the control-panel preview box")
    ap.add_argument("--peek-units-count", type=int, default=4,
                    help="how many units to cycle through for --peek-units")
    args = ap.parse_args()

    uiwalk.PREFER_RELEASE = True
    if args.marker.lower() != "none":
        uiwalk.preflight_exe(args.marker)
    uiwalk.preflight_display()
    ctypes.windll.user32.SetProcessDPIAware()

    run_dir = uiwalk.RUNS / (time.strftime("%Y%m%d-%H%M%S") + "-turnloop")
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"artifacts -> {run_dir}")
    global _CALIB_DEBUG_DIR
    _CALIB_DEBUG_DIR = run_dir

    game = uiwalk.Game()
    watcher = ErrorWatcher(set())
    watcher.start()
    log: list[dict] = []
    verdict = "INCOMPLETE"
    reached = 0

    try:
        game.launch(None, [])            # boot to the menu; a NEW game compiles SLIC fresh (L5)
        boot_results = boot(game, run_dir)
        failed_boot = [r for r in boot_results if not r[3]]
        if failed_boot:
            verdict = "BOOT_FAILED"
            print("boot asserts failed: " + ", ".join(r[0] for r in failed_boot))
            return 2
        if watcher.hits:
            verdict = "SLIC_ERROR_AT_LOAD"
            return 3

        inp = uiwalk.PostInput(game)
        prev = game.screenshot()
        cv2.imwrite(str(run_dir / "turn_000.png"), prev)

        if args.dismiss:
            dismiss_message(game, inp)
            prev = game.screenshot()
            cv2.imwrite(str(run_dir / "turn_000_dismissed.png"), prev)

        if args.found_city:
            # WHY THIS EXISTS (measured 2026-07-25): a pure end-turn loop never
            # founds anything, so player[0].cities stays 0 for the whole run. The
            # magic display proved it -- "+10 per turn" is the bare base with the
            # per-city term contributing nothing. With no city, M3's auto-summon
            # can never fire: its guard is `player[0].cities > 0`, and the spawn
            # location is the first city's tile. So the summon was untestable, not
            # broken-and-silent.
            # 'b' is SETTLE in ctp2_data/default/uidata/keymap.txt; the engine has
            # the starting peasant selected at game start (MoM has no settler unit
            # -- peasants found cities).
            inp.hotkey(["b"])
            time.sleep(2.0)
            uiwalk.wait_stable(game, 8000)
            # MEASURED 2026-07-25: userprofile has AutoOpenCityWindow=Yes, so
            # settling immediately raises the BUILD MANAGER on top of everything.
            # It is an engine aui window, and clicking the SLIC message box's X
            # while it is up crashed the engine (0xC0000005) three runs running.
            # Close it by injection first -- clicks are dead on aui surfaces
            # anyway (L7). Path from editqueue.ldl:186/657.
            if args.build_unit >= 0:
                # The build manager is already up and already on the Units tab
                # by default; press it anyway so the probe does not depend on
                # whatever tab the engine happened to restore.
                uiwalk.inject_press(game.hwnd, "BuildEditorWindow.ItemsBox.UnitsButton")
                time.sleep(1.0)
                cv2.imwrite(str(run_dir / "build_manager.png"), game.screenshot())
                uiwalk.inject_select(game.hwnd, "BuildEditorWindow.ItemsBox.UnitsList",
                                     args.build_unit)
                time.sleep(1.0)
                uiwalk.inject_press(game.hwnd, "BuildEditorWindow.ItemsBox.AddButton")
                time.sleep(1.0)
                cv2.imwrite(str(run_dir / "build_queued.png"), game.screenshot())
                print(f"build queue: added UnitsList row {args.build_unit}", flush=True)
            # MEASURED 2026-07-25: 'BuildEditorWindow.CloseButton' resolved to
            # obj=00000000 on every prior run -- aui_Ldl::GetObject is an EXACT
            # path lookup and the button lives one level deeper. The engine's own
            # RunUITriggers lines name the real path.
            uiwalk.inject_press(game.hwnd,
                                "BuildEditorWindow.NormalModeButtons.CloseButton")
            time.sleep(1.5)
            uiwalk.wait_stable(game, 6000)
            dismiss_message(game, inp)
            prev = game.screenshot()
            cv2.imwrite(str(run_dir / "turn_000_founded.png"), prev)
            print("found city: pressed 'b'", flush=True)

        if args.diag:
            # ISOLATION PROBE. wait_stable cannot distinguish "the turn did not
            # advance" from "the AI is thinking and the screen is frozen": both
            # are two identical frames. So press ONCE and sample on a wall clock
            # instead, which separates a refused press (flat forever) from a slow
            # AI round (flat, then a jump when control returns).
            if args.trigger:
                uiwalk.inject_trigger(game.hwnd, args.trigger)
            elif args.press:
                uiwalk.inject_press(game.hwnd, args.press)
            else:
                end_turn(game, inp, args.endturn)
            t0 = time.time()
            while time.time() - t0 < args.diag:
                time.sleep(5.0)
                if not alive(game):
                    verdict = "CRASH_DURING_DIAG"
                    break
                cur = game.screenshot()
                el = int(time.time() - t0)
                d = frame_delta(prev, cur)
                cv2.imwrite(str(run_dir / f"diag_{el:03d}s.png"), cur)
                log.append({"elapsed_s": el, "delta_vs_prev": d})
                print(f"  +{el:3d}s  delta={d}", flush=True)
                prev = cur
            else:
                verdict = "DIAG_DONE"
            return 0

        for turn in range(1, args.turns + 1):
            if not alive(game):
                verdict = f"CRASH_BEFORE_TURN_{turn}"
                break

            # LINK 7 READOUT, taken BEFORE dismiss_message: the consumer's popup
            # is a message like any other, so dismissing first would destroy the
            # only evidence. Captured on the turn AFTER the click, which is the
            # whole point -- the arm body wrote a global and nothing else.
            # +2, not +1 (MEASURED 2026-07-25, runs/20260725-090521): the arm is
            # clicked at the END of iteration N, i.e. AFTER that iteration's
            # end_turn has already run the next BeginTurn. The first BeginTurn
            # that can see the order is the one end_turn fires in iteration N+1,
            # so its popup is on screen at the start of iteration N+2. Reading at
            # +1 reported msg_box=None on a run where the consumer had not yet
            # had a turn to run -- a harness phase error, not a SLIC failure.
            if args.summon_arm and turn == args.summon_turn + 2:
                res = game.screenshot()
                cv2.imwrite(str(run_dir / f"summon_arm{args.summon_arm}_result.png"), res)
                box = find_msg_box(res)
                log.append({"summon_readout_turn": turn,
                            "arm": args.summon_arm,
                            "msg_box": box,
                            "alert_open": alert_box_open(res)})
                print(f"  [link7] readout turn {turn}: msg_box={box}", flush=True)

            # The BeginTurn Message() puts up a modal EVERY turn, and while it is
            # up the end-turn button is inert (MEASURED: press resolves, OK, and
            # delta=0 for 90s). Clearing it is part of the turn, not cleanup.
            dismiss_message(game, inp)
            pre = game.screenshot()

            # RETRY, added 2026-07-25. This used to press ONCE and hard-break on
            # the first delta=0. I added the retry on a timing-race hypothesis
            # (the engine not being ready yet, EndTurnButtonActionCallback's only
            # silent early-return being GetCurPlayer() != GetVisiblePlayer()).
            #
            # That hypothesis was FALSIFIED by this very loop: three presses with
            # 3s waits all failed identically. The real cause was the missing
            # mouse input, now supplied by engine_ping() at the top of each
            # attempt. The retry is therefore INERT on a healthy run -- kept
            # because it is cheap (0s when the first attempt works) and a human
            # in the same spot does click END TURN again rather than concluding
            # the game is broken. Bounded on purpose so a genuine stall still
            # fails the run instead of spinning.
            advanced = False
            fatal = False
            for attempt in range(1, END_TURN_ATTEMPTS + 1):
                engine_ping(inp)
                end_turn(game, inp, args.endturn)
                time.sleep(1.0)
                uiwalk.wait_stable(game, args.settle_ms)

                if not alive(game):
                    verdict = f"CRASH_DURING_TURN_{turn}"
                    fatal = True
                    break
                if watcher.hits:
                    verdict = f"SLIC_ERROR_TURN_{turn}"
                    fatal = True
                    break

                shot = game.screenshot()
                advanced = date_changed(pre, shot)
                if advanced:
                    if attempt > 1:
                        print(f"  [endturn] advanced on attempt {attempt}",
                              flush=True)
                    break
                if attempt < END_TURN_ATTEMPTS:
                    print(f"  [endturn] no advance on attempt {attempt}/"
                          f"{END_TURN_ATTEMPTS}; waiting for the engine",
                          flush=True)
                    time.sleep(END_TURN_RETRY_S)
            if fatal:
                break

            d = frame_delta(prev, shot)
            cv2.imwrite(str(run_dir / f"turn_{turn:03d}.png"), shot)
            log.append({"turn": turn, "delta": d, "date_changed": advanced})
            print(f"turn {turn:3d}  delta={d}  advanced={advanced}", flush=True)
            prev = shot
            if not advanced:
                # Refuse to keep counting turns that did not happen. This is the
                # exact false-pass the old whole-frame-delta check allowed.
                verdict = f"TURN_DID_NOT_ADVANCE_AT_{turn}"
                break
            reached = turn

            if args.summon_arm and turn == args.summon_turn:
                # Open the menu and place the order. The click is the LAST thing
                # that happens this turn; everything observable must therefore
                # arrive on the next one.
                inp.hotkey(["j"])
                time.sleep(1.5)
                uiwalk.wait_stable(game, 8000)
                cv2.imwrite(str(run_dir / f"summon_arm{args.summon_arm}_menu.png"),
                            game.screenshot())
                ok = click_alert_arm(game, inp, args.summon_arm - 1,
                                     f"summon{args.summon_arm}")
                log[-1]["summon_arm_clicked"] = ok
                if not ok:
                    verdict = f"SUMMON_ARM_CLICK_FAILED_AT_{turn}"
                    break

            if args.peek_units and turn == args.peek_units:
                # ART PROBE (defect 2) -- BROKEN, kept as a placeholder. The
                # diagnosis stands: the control-panel unit-preview box is a FIXED
                # ~77x65 viewport against a 96x72 GU sprite canvas, so a source
                # framed edge-to-edge overflows the box while the map -- which has
                # no box -- draws it fine. That is why it looked wrong in the
                # bottom UI ONLY. But this probe cannot photograph it: 'n' does
                # NOT cycle units (captures came back byte-identical, 57157 bytes
                # each -- the keyboard is dead on in-game surfaces, L7), and the
                # control panel renders pure BLACK under PrintWindow anyway.
                # Verification is ARTIFACT-level instead --
                # tools/gate_sprite_extent.py runs the real _facing_images path
                # over every source and asserts the opaque-bbox fraction.
                for k in range(1, args.peek_units_count + 1):
                    inp.hotkey(["n"])
                    time.sleep(2.0)
                    uiwalk.wait_stable(game, 6000)
                    cv2.imwrite(str(run_dir / f"peek_unit_{k:02d}.png"),
                                game.screenshot())
                print(f"  [peek] captured {args.peek_units_count} unit previews",
                      flush=True)

            if args.probe_every and turn % args.probe_every == 0:
                # Probe ONCE-per-N to keep the map region the visibility checks
                # measure mostly clear. The old extra guard (_ALERT_DISMISS_DEAD:
                # stop probing forever after one failed dismissal) is GONE --
                # it rested on "a SLIC alertbox has no working close channel at
                # this geometry", which is falsified: minimize alone does not
                # clear the box, but clicking the measured Close arm centre at
                # the identity send scale does. dismiss_message now falls back to
                # that click, so a box that opens is a box that closes.
                inp.hotkey(["j"])
                time.sleep(1.5)
                uiwalk.wait_stable(game, 8000)
                probe = game.screenshot()
                cv2.imwrite(str(run_dir / f"turn_{turn:03d}_magic.png"), probe)
                log[-1]["magic_probe_delta"] = frame_delta(shot, probe)
        else:
            verdict = "OK"

    except (RuntimeError, TimeoutError) as e:
        verdict = f"HARNESS_ERROR: {e}"
    finally:
        watcher.stop()
        (run_dir / "turnloop.json").write_text(json.dumps({
            "verdict": verdict,
            "turns_requested": args.turns,
            "turns_reached": reached,
            "slic_errors": watcher.hits,
            "turns": log,
        }, indent=2))
        if not args.keep:
            game.kill()

    print(f"\nVERDICT: {verdict}   turns_reached={reached}/{args.turns}   "
          f"slic_errors={len(watcher.hits)}")
    for h in watcher.hits:
        print(f"  [{h['t']}] {h['title']}: {h['text']}")
    return 0 if verdict == "OK" and not watcher.hits else 1


if __name__ == "__main__":
    sys.exit(main())
