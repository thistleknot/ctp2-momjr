"""CTP2 UI-walkthrough harness: launch the game deterministically, drive it with
scripted keys/clicks, screenshot checkpoints, and assert regions against goldens.

Purpose: automated in-game verification of UI/art changes (e.g. Great Library
advance icons) without a human clicking through every build.

Input isolation: the DEFAULT backend posts WM_* messages directly to the game's
window handle and captures via PrintWindow — the game can sit unfocused in the
background and the user's physical mouse/keyboard are never touched. The
`--global-input` fallback uses pyautogui (real cursor; pyautogui FAILSAFE on:
slam the mouse into the top-left corner to abort).

Preconditions:
  - ctp2_program/ctp holds a runnable exe (ctp2-dbg.exe / ctp2-log.exe / ctp2.exe)
    with its runtime overlay already staged (run run-ctp2-dbg-crashcapture.ps1
    -NoRun once if unsure).
  - userprofile.txt has WindowedMode=Yes (client 1024x768 assumed by step coords).
  - A golden save exists for deterministic boot (see --save; engine -l<file>
    auto-skips intro movie and main menu).
  - py310 packages: pyautogui, pygetwindow, pywin32, mss, opencv-python, numpy.

Failure modes:
  - Window never appears within launch timeout -> exit 2 (engine crash or gate).
  - A step raises (bad coords, missing golden) -> teardown by PID, exit 2.
  - Any assert below threshold -> PASS/FAIL table, exit 1.
  - If PostMessage input is ignored by the engine (SDL raw-input edge), rerun
    with --global-input and report it.
"""

import argparse
import ctypes
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import mss
import pygetwindow
import win32api
import win32con
import win32gui
import win32process
import win32ui

TOOL_DIR = Path(__file__).resolve().parent
INSTALL = TOOL_DIR.parents[3]                     # <install>/Scenarios/mom/tools/uiwalk
EXE_DIR = INSTALL / "ctp2_program" / "ctp"
EXE_CANDIDATES = ["ctp2-dbg.exe", "ctp2-log.exe", "ctp2.exe"]  # unused; real
# selection happens in run-ctp2-dbg-crashcapture.ps1 (Resolve-LaunchSource).

# The launcher script stages an exe from this tree into the install dir on every
# run, so THIS is the binary actually under test -- not whatever sits installed.
SOURCE_ROOT = Path(r"H:\Games\civctp2\ctp2_code\ctp")
PREFER_RELEASE = True


INJECT_FILE = r"H:\mom_inject.txt"
INJECT_MSG = 0x8000 + 100          # WM_APP+100, matches k_INJECT_UITRIGGER_MSG


def inject_trigger(hwnd, path: str):
    """Fire a SLIC UI trigger on an in-game control -- the BARE-NAME hook form.

    NOT the same mechanism as inject_press, and the difference is why a press on
    an in-game control looks like it "did nothing":

      press:<path>  -> aui_Button::InjectPress -> the button's C++ m_ActionFunc.
                       Menu buttons are wired that way (SetActionFuncAndCookie).
      <path>        -> SlicEngine::RunUITriggers(path), the path a real
                       left-click takes via HandleGameSpecificLeftClick. This is
                       what `trigger 'X' on "<path>" when(1) {...}` subscribes
                       to (aui_sdl.cpp, bare-name branch).

    A control whose only behaviour is a SLIC trigger has NO m_ActionFunc, so
    InjectPress on it resolves the object, returns OK, and changes nothing --
    measured 2026-07-25 on ShortcutPad.MagicButton (obj non-null, delta=0).
    Use this for in-game SLIC controls; use inject_press for menu buttons.

    RunUITriggers only ENQUEUES; the main loop's ProcessUITriggers drains it, so
    allow a frame or two before asserting on pixels.
    """
    with open(INJECT_FILE, "wb") as f:
        f.write(path.encode("utf-8"))
    win32api.PostMessage(hwnd, INJECT_MSG, 0, 0)


def inject_select(hwnd, path: str, index: int):
    """Select a listbox row by INDEX, headlessly.

    CTP2_LISTBOX is `atomic true` -> rows/scrollbar have no addressable LDL path,
    and aui polls GetCursorPos so PostMessage clicks never reach them (measured:
    0 of 36 grid clicks registered). Index selection avoids coordinates entirely.
    """
    with open(INJECT_FILE, "wb") as f:
        f.write(f"select:{path},{index}".encode("utf-8"))
    win32api.PostMessage(hwnd, INJECT_MSG, 0, 0)


def inject_press(hwnd, path: str):
    """Press a menu button headlessly via the engine's built-in injection hook.

    PostMessage CLICKS DO NOT WORK ON MENUS: aui polls GetCursorPos, so synthetic
    WM_LBUTTONDOWN is invisible there and the screen simply never changes. The
    engine ships MoM_WindowsMessageHook (aui_sdl.cpp) for exactly this: write the
    full LDL control path to INJECT_FILE, post WM_APP+100, and the hook calls
    aui_Button::InjectPress() on it. Works off-screen and never touches the real
    cursor. Example path: InitPlayWindow.NewGameButton
    """
    with open(INJECT_FILE, "wb") as f:
        f.write(("press:" + path).encode("utf-8"))
    win32api.PostMessage(hwnd, INJECT_MSG, 0, 0)


def preflight_exe(marker: str):
    """Abort unless the exe that will really be launched contains `marker`.

    Guards the failure mode that burned five days: build.bat builds only
    Final-SDL (-> ctp2.exe), so ctp2-dbg.exe is never refreshed; the launcher
    prefers ctp2-dbg.exe by default and re-stages that stale binary on every
    run, meaning the harness silently tested a build without the change in it.
    """
    order = (["ctp2.exe", "ctp2-log.exe", "ctp2-dbg.exe"] if PREFER_RELEASE
             else ["ctp2-dbg.exe", "ctp2-log.exe", "ctp2.exe"])
    for name in order:
        p = SOURCE_ROOT / name
        if not p.exists():
            continue
        found = marker.encode("utf-8", "ignore") in p.read_bytes()
        print(f"[preflight] launch candidate: {p} ({p.stat().st_size:,} bytes)")
        print(f"[preflight] marker {marker!r}: {'FOUND' if found else 'MISSING'}")
        if not found:
            raise SystemExit(
                f"ABORT: {p} does not contain {marker!r} -- stale build.\n"
                f"  Rebuild it, or pass --marker none to skip this check."
            )
        return p
    raise SystemExit(f"ABORT: no launch candidate found under {SOURCE_ROOT}")


def _child_env():
    """Environment for the game process. Forces SDL's SOFTWARE renderer.

    MEASURED root cause of the "black capture" regression: with the default
    accelerated backend, SDL_CreateRenderer(window,-1,0) picks a surface that
    GDI PrintWindow CANNOT read -- captures come back nearly black no matter
    where the window sits or what resolution it uses. Forcing the software
    backend raised non-black pixels 61,040 -> 151,173 on an identical frame
    and produced the first readable capture (the Activision splash).

    NOT the cause, despite an earlier claim in this file: primary-monitor
    orientation. A legal, honoured 1024x1280 window was still black. Display
    mode selection explains window SIZE only. See preflight_display()."""
    env = dict(os.environ)
    env["SDL_RENDER_DRIVER"] = "software"
    env["SDL_FRAMEBUFFER_ACCELERATION"] = "0"
    return env


def profile_screen_res(default=(1024, 768)):
    """The ScreenResWidth/Height the engine will actually ASK for.

    MEASURED 2026-07-26: the preflight used to hardcode (1024, 768), which asks
    the wrong question. The engine's gate is "is the PROFILE's mode legal on the
    primary display", not "is 1024x768 legal" -- so a profile edited to a mode
    that IS legal on a portrait primary (e.g. 1024x1280) was still reported as
    an abort. Read the value the engine reads."""
    prof = EXE_DIR / "userprofile.txt"
    w = h = None
    try:
        for line in prof.read_text(errors="ignore").splitlines():
            k, _, v = line.partition("=")
            k = k.strip()
            if k == "ScreenResWidth":
                w = int(v.strip())
            elif k == "ScreenResHeight":
                h = int(v.strip())
    except Exception:
        return default
    if w and h:
        return (w, h)
    return default


def preflight_display(want=None):
    """ABORT when the PRIMARY display cannot supply `want`.

    `want` defaults to whatever userprofile.txt asks for -- see
    profile_screen_res(). Passing an explicit tuple is for tests only.

    This is a GATE, not decoration. The condition it detects is NOT what makes
    captures black (see _child_env) -- but it IS what makes coordinate clicks
    miss, and a missed click AVs the process at turn 0. Measured 2026-07-25;
    see the abort text at the bottom of this function for the evidence.
    `UIWALK_ALLOW_ILLEGAL_RES=1` downgrades it to a warning for capture-only
    work that never clicks.

    Engine ground truth (ctp2_code/ctp/display.cpp):
      * display_EnumerateDisplayModes() builds the legal-mode list from
        SDL_GetNumDisplayModes(0) -- display 0, i.e. the WINDOWS PRIMARY
        MONITOR ONLY. Modes offered by any secondary monitor are invisible to it.
      * g_ScreenWidth/Height are SEEDED from the monitor, and the userprofile
        ScreenRes* values override them only if display_IsLegalResolution()
        finds an EXACT match in that list. Otherwise the engine silently falls
        back to g_displayModes->GetHead().

    So if the primary monitor is rotated to portrait, 1024x768 is not a legal
    mode, the profile is ignored, and the window is created at the portrait
    size. That much is CONFIRMED -- but it explains window SIZE ONLY.

    FALSIFIED 2026-07-24: an earlier version of this docstring claimed the
    portrait window is "where the engine renders a black client area" and made
    this check a hard abort. Wrong. A legal, honoured 1024x1280 window was
    still black. The two real causes are in _child_env (accelerated SDL surface
    unreadable by PrintWindow) and the nointromovie launch arg (~40s cinematic).
    Both are now applied automatically. What is left is a CLICK-AIM defect,
    which is fatal -- hence the abort.
    """
    import ctypes.wintypes

    if want is None:
        want = profile_screen_res()

    class DEVMODE(ctypes.Structure):
        _fields_ = [("dmDeviceName", ctypes.c_wchar * 32),
                    ("dmSpecVersion", ctypes.c_ushort),
                    ("dmDriverVersion", ctypes.c_ushort),
                    ("dmSize", ctypes.c_ushort),
                    ("dmDriverExtra", ctypes.c_ushort),
                    ("dmFields", ctypes.c_ulong),
                    ("dmPosition_x", ctypes.c_long),
                    ("dmPosition_y", ctypes.c_long),
                    ("dmDisplayOrientation", ctypes.c_ulong),
                    ("dmDisplayFixedOutput", ctypes.c_ulong),
                    ("dmColor", ctypes.c_short),
                    ("dmDuplex", ctypes.c_short),
                    ("dmYResolution", ctypes.c_short),
                    ("dmTTOption", ctypes.c_short),
                    ("dmCollate", ctypes.c_short),
                    ("dmFormName", ctypes.c_wchar * 32),
                    ("dmLogPixels", ctypes.c_ushort),
                    ("dmBitsPerPel", ctypes.c_ulong),
                    ("dmPelsWidth", ctypes.c_ulong),
                    ("dmPelsHeight", ctypes.c_ulong),
                    ("dmDisplayFlags", ctypes.c_ulong),
                    ("dmDisplayFrequency", ctypes.c_ulong),
                    ("dmICMMethod", ctypes.c_ulong),
                    ("dmICMIntent", ctypes.c_ulong),
                    ("dmMediaType", ctypes.c_ulong),
                    ("dmDitherType", ctypes.c_ulong),
                    ("dmReserved1", ctypes.c_ulong),
                    ("dmReserved2", ctypes.c_ulong),
                    ("dmPanningWidth", ctypes.c_ulong),
                    ("dmPanningHeight", ctypes.c_ulong)]

    class DISPLAY_DEVICE(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong),
                    ("DeviceName", ctypes.c_wchar * 32),
                    ("DeviceString", ctypes.c_wchar * 128),
                    ("StateFlags", ctypes.c_ulong),
                    ("DeviceID", ctypes.c_wchar * 128),
                    ("DeviceKey", ctypes.c_wchar * 128)]

    DISPLAY_DEVICE_PRIMARY = 0x4
    ENUM_CURRENT_SETTINGS = -1
    u32 = ctypes.windll.user32

    primary = None
    i = 0
    while True:
        dd = DISPLAY_DEVICE()
        dd.cb = ctypes.sizeof(DISPLAY_DEVICE)
        if not u32.EnumDisplayDevicesW(None, i, ctypes.byref(dd), 0):
            break
        if dd.StateFlags & DISPLAY_DEVICE_PRIMARY:
            primary = dd.DeviceName
            break
        i += 1
    if primary is None:
        print("[preflight] display: could not identify primary monitor; skipping check")
        return

    cur = DEVMODE()
    cur.dmSize = ctypes.sizeof(DEVMODE)
    u32.EnumDisplaySettingsW(primary, ENUM_CURRENT_SETTINGS, ctypes.byref(cur))

    modes = set()
    n = 0
    while True:
        dm = DEVMODE()
        dm.dmSize = ctypes.sizeof(DEVMODE)
        if not u32.EnumDisplaySettingsW(primary, n, ctypes.byref(dm)):
            break
        modes.add((int(dm.dmPelsWidth), int(dm.dmPelsHeight)))
        n += 1

    print(f"[preflight] primary display {primary}: {cur.dmPelsWidth}x{cur.dmPelsHeight} "
          f"orientation={cur.dmDisplayOrientation} ({len(modes)} modes)")

    if tuple(want) in modes:
        print(f"[preflight] {want[0]}x{want[1]}: LEGAL on the primary display")
        return

    print(
        f"[preflight] WARN: {want[0]}x{want[1]} is NOT a legal mode of the primary "
        f"display ({primary}, {cur.dmPelsWidth}x{cur.dmPelsHeight}, "
        f"orientation={cur.dmDisplayOrientation}).\n"
        f"  CTP2 enumerates legal modes from display 0 only (display.cpp\n"
        f"  display_EnumerateDisplayModes), so userprofile ScreenResWidth/Height\n"
        f"  is honoured only if it names a mode of THAT display. The window will\n"
        f"  be some other legal size, and the engine REFLOWS its in-game UI to the\n"
        f"  client (it does NOT letterbox a fixed surface), so every constant and\n"
        f"  every height-fraction aim point authored at 1024x768 is wrong.\n"
        f"  Goldens still match at 1.000 because match_template searches with\n"
        f"  padding -- an assert asks 'is this UI present', not 'is it at this\n"
        f"  exact pixel'. Captures are READABLE (software renderer).\n"
        f"  Captures are fine; POINTING is what breaks."
    )
    # RE-UPGRADED TO AN ABORT 2026-07-25, on a causal chain that is now measured
    # rather than assumed. The 2026-07-24 downgrade was correct about what it
    # tested (this is not what makes captures black) and wrong about the blast
    # radius: three runs on a PORTRAIT primary (\\.\DISPLAY4 1080x1920, where
    # 1024x768 is illegal) all died 0xC0000005 at turns_reached=0 on the FIRST
    # coordinate click, while a sprite-rebuild bisect at identical artifacts
    # crashed too -- falsifying the only competing hypothesis.
    #
    # CORRECTED TWICE. First correction (right): nothing LETTERBOXES -- the
    # engine reflows its in-game UI to the client size -- so aim points authored
    # at 1024x768 are wrong here because the widgets genuinely moved.
    # Second correction (2026-07-26, replacing a wrong one): the claim that "a
    # posted mouse BUTTON is process-lethal at this client on ANY pixel" is
    # FALSIFIED. All three 0xC0000005 deaths behind it were sends produced by
    # turnloop's calibration battery at x0.80 -- i.e. MISSES -- before that
    # battery tried the identity factor first. With identity-first ordering, a
    # click on a frame-measured arm centre lands cleanly (runs/20260725-232412:
    # Summon arm pressed, arm body ran, 6/6 turns, 0 SLIC errors).
    #
    # So the ABORT stands, for the ORIGINAL reason only: authored aim points are
    # off at a reflowed client, and a miss on this surface is what kills. Aim
    # that is DERIVED from the live frame is safe; aim that is PINNED is not.
    # Goldens still PASS (padded search), so a run in this state looks healthy
    # right up until it dies. Fixing it means changing the USER's desktop
    # (primary-display assignment or rotation), which is theirs to do.
    if os.environ.get("UIWALK_ALLOW_ILLEGAL_RES") == "1":
        print("[preflight] UIWALK_ALLOW_ILLEGAL_RES=1 -- continuing anyway "
              "(coordinate clicks are expected to miss).")
        return
    raise SystemExit(
        f"[preflight] ABORT: this geometry is not a valid test surface (the UI\n"
        f"  reflows, so every PINNED aim point is off, and a miss AVs here).\n"
        f"  Make a display with a legal {want[0]}x{want[1]} mode PRIMARY (or rotate\n"
        f"  {primary} back to landscape), then re-run. Set\n"
        f"  UIWALK_ALLOW_ILLEGAL_RES=1 to proceed anyway for capture-only work."
    )
WINDOW_TITLE = "Call To Power 2"
LAUNCH_TIMEOUT_S = 90
GOLDENS = TOOL_DIR / "goldens"
RUNS = TOOL_DIR / "runs"

def _stash_position() -> tuple[int, int]:
    """Top-left corner to park the game window at: just past the RIGHT edge of
    the whole virtual desktop, vertically aligned with its top.

    NOT (-32000, -32000).  That pair is Windows' *minimized* sentinel, and a
    window parked there can be treated as minimized.  Note the honest history:
    this was first written up as the cause of a run whose 14 shots were all
    BYTE-IDENTICAL on the startup "Loading..." frame -- that attribution was
    FALSIFIED (re-running from this position froze identically).  The actual
    cause was a modal 'Load save game Error' dialog (class #32770) blocking the
    engine ~2s after launch, raised because --save defaults to the nonexistent
    save "uiwalk_start"; see Game.launch().  Found by enumerating the process's
    top-level windows, not by reasoning about coordinates.

    The position is kept anyway on its own merits, not on that false story:
    just past the virtual right edge is equally invisible to the user (no
    monitor covers it) but is an ordinary coordinate, so it carries no
    minimized semantics at all.

    Guarantee: returned x is >= the right edge of every monitor.
    """
    x = (win32api.GetSystemMetrics(win32con.SM_XVIRTUALSCREEN)
         + win32api.GetSystemMetrics(win32con.SM_CXVIRTUALSCREEN))
    y = win32api.GetSystemMetrics(win32con.SM_YVIRTUALSCREEN)
    return x + 8, y


def _stash_offscreen(hwnd):
    """Move the game window off every monitor so runs are invisible to the user.
    Safe: input is PostMessage with CLIENT-relative coords and capture is
    PrintWindow, so neither depends on the window being on-screen or focused.
    Set UIWALK_VISIBLE=1 to keep it on-screen for debugging."""
    import os
    if os.environ.get("UIWALK_VISIBLE") == "1":
        return
    try:
        x, y = _stash_position()
        win32gui.SetWindowPos(hwnd, 0, x, y, 0, 0,
                              win32con.SWP_NOSIZE | win32con.SWP_NOZORDER
                              | win32con.SWP_NOACTIVATE)
    except Exception:
        pass


_WATCHED_PIDS = set()
_WATCHED_PROCS = set()


def _game_pids(proc):
    """PIDs that may own the game window: our child plus every descendant.

    Direct launch spawns the exe itself, so the child IS the game. The
    UIWALK_LAUNCHER path spawns powershell, and the game is a grandchild --
    keying on proc.pid alone would watch the wrong process there.
    """
    pids = set()
    if proc is None:
        return pids
    pids.add(proc.pid)
    try:
        import psutil
        for c in psutil.Process(proc.pid).children(recursive=True):
            pids.add(c.pid)
    except Exception:
        pass
    return pids


def _windows_for_pids(pids):
    """Every visible top-level window owned by `pids`, as (hwnd, w, h)."""
    found = []

    def cb(hwnd, _):
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return
            if win32process.GetWindowThreadProcessId(hwnd)[1] not in pids:
                return
            l, t, r, b = win32gui.GetWindowRect(hwnd)
            found.append((hwnd, r - l, b - t))
        except Exception:
            pass

    try:
        win32gui.EnumWindows(cb, None)
    except Exception:
        pass
    return found


def _stash_all_for_pid(pid):
    """Stash every top-level window owned by `pid`, whatever its title.

    Title matching CANNOT be the primary key: SDL creates the window first and
    sets its caption afterwards, so between those two calls the window is on
    screen and NO title-keyed lookup can find it. That gap is a real, visible
    leak, not a theoretical one -- it is how the window kept appearing after the
    watchdog was added. Ownership by our own child process is known at spawn
    time and is true from the very first CreateWindow call.
    """
    def cb(hwnd, _):
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return
            if win32process.GetWindowThreadProcessId(hwnd)[1] != pid:
                return
            l, t, _r, _b = win32gui.GetWindowRect(hwnd)
            if l > -30000 or t > -30000:
                _stash_offscreen(hwnd)
        except Exception:
            pass
    try:
        win32gui.EnumWindows(cb, None)
    except Exception:
        pass


def _start_stash_watchdog(pid=None):
    """Continuously force every window we own off-screen. HEADLESS IS ABSOLUTE.

    Why a thread and not just get_hwnd(): stashing only on handle access leaves
    the window visible during long `wait` steps and during the video-mode change
    at scenario load, when the engine repositions the window on-screen without
    destroying its handle.

    Why by PID and ONLY by PID: see _stash_all_for_pid. A title-keyed sweep used
    to run alongside this, and it was actively harmful -- WINDOW_TITLE is
    "Call To Power 2", which is also the name of the project DIRECTORY, so any
    Explorer window opened on that folder carries the identical caption. The
    sweep moved the USER's window off-screen, and window acquisition then
    resolved that Explorer window instead of the game. Never key window identity
    on a caption we do not own. (Scope note, 2026-07-24: this misidentification
    is real, but it was NOT the cause of the black-capture regression -- that
    was the accelerated SDL surface plus the intro movie. See _child_env.)

    Poll is 30ms, not 150ms: at 150ms the user sees a clearly perceptible flash
    at window creation and again at the video-mode change. The cost is a cheap
    EnumWindows on a daemon thread.

    Idempotent -- safe to call repeatedly; no-ops under UIWALK_VISIBLE=1.
    """
    if os.environ.get("UIWALK_VISIBLE") == "1":
        return
    if pid is not None:
        _WATCHED_PIDS.add(pid)
    if getattr(_start_stash_watchdog, "_running", False):
        return
    _start_stash_watchdog._running = True

    def loop():
        n = 0
        while True:
            for p in tuple(_WATCHED_PIDS):
                _stash_all_for_pid(p)
            # Descendant refresh, ~1Hz: under UIWALK_LAUNCHER the watched PID is
            # powershell and the game is a grandchild spawned later. Too costly
            # to walk at 30ms, so it rides a counter.
            n += 1
            if n % 33 == 0:
                for pr in tuple(_WATCHED_PROCS):
                    _WATCHED_PIDS.update(_game_pids(pr))
            time.sleep(0.03)

    t = threading.Thread(target=loop, daemon=True)
    t.start()


VK = {
    "enter": win32con.VK_RETURN, "backspace": win32con.VK_BACK, "esc": win32con.VK_ESCAPE,
    "tab": win32con.VK_TAB, "space": win32con.VK_SPACE, "ctrl": win32con.VK_CONTROL,
    "shift": win32con.VK_SHIFT, "alt": win32con.VK_MENU,
    "apostrophe": 0xDE, "tilde": 0xC0, "minus": 0xBD, "equals": 0xBB,
    # Arrow keys scroll the map view. Added 2026-07-26: the in-game viewport only
    # paints damaged regions, so a freshly loaded map is BLACK under intact chrome
    # until something forces a redraw -- scrolling is the cheapest trigger, and
    # without these a map frame cannot be captured at all.
    "left": win32con.VK_LEFT, "right": win32con.VK_RIGHT,
    "up": win32con.VK_UP, "down": win32con.VK_DOWN,
    **{c: ord(c.upper()) for c in "abcdefghijklmnopqrstuvwxyz0123456789"},
}


def find_save(name: str) -> Path:
    """Locate a saved game under the engine save tree by stem or filename.

    Require: name is a save stem ("uiwalk_start") or filename with extension.
    Guarantee: returns an existing file path. Raises FileNotFoundError otherwise.
    """
    root = EXE_DIR / "save"
    hits = [p for p in root.rglob("*") if p.is_file() and (p.stem.lower() == name.lower() or p.name.lower() == name.lower())]
    if not hits:
        raise FileNotFoundError(f"save '{name}' not found under {root}")
    return hits[0]


class PostInput:
    """Background input: WM_* messages to the game HWND. Never moves the real
    cursor or generates global keystrokes. SDL2 translates WM_KEY*/WM_CHAR/
    WM_*BUTTON* through its message pump and tracks modifier state from the
    posted VK_CONTROL events, so Ctrl+5 style chords work without SetKeyboardState."""

    def __init__(self, game):
        self.game = game

    @property
    def hwnd(self):
        return self.game.get_hwnd()

    @staticmethod
    def _lparam_key(vk, up=False):
        scan = win32api.MapVirtualKey(vk, 0)
        lp = 1 | (scan << 16)
        if up:
            lp |= (1 << 30) | (1 << 31)
        return lp

    def _spoof_focus(self):
        """SDL2 only translates WM_KEY* into key events while its window holds
        SDL_WINDOW_INPUT_FOCUS, which it sets on WM_SETFOCUS. Posting the focus
        messages into the queue flips that flag without stealing the user's
        real foreground focus."""
        hwnd = self.hwnd
        win32api.PostMessage(hwnd, win32con.WM_ACTIVATE, win32con.WA_ACTIVE, 0)
        win32api.PostMessage(hwnd, win32con.WM_SETFOCUS, 0, 0)
        time.sleep(0.05)

    def _key(self, vk, down):
        msg = win32con.WM_KEYDOWN if down else win32con.WM_KEYUP
        win32api.PostMessage(self.hwnd, msg, vk, self._lparam_key(vk, up=not down))

    def hotkey(self, names: list[str]):
        self._spoof_focus()
        vks = [VK[n.lower()] for n in names]
        for vk in vks:
            self._key(vk, True)
            time.sleep(0.03)
        for vk in reversed(vks):
            self._key(vk, False)
            time.sleep(0.03)

    def type_text(self, text: str):
        self._spoof_focus()
        for ch in text:
            win32api.PostMessage(self.hwnd, win32con.WM_CHAR, ord(ch), 1)
            time.sleep(0.03)

    def drag(self, x1: int, y1: int, x2: int, y2: int, steps: int = 12):
        """Press at (x1,y1), move in steps to (x2,y2), release. For slider thumbs."""
        self._spoof_focus()
        lp = win32api.MAKELONG(x1, y1)
        win32api.PostMessage(self.hwnd, win32con.WM_MOUSEMOVE, 0, lp)
        time.sleep(0.05)
        win32api.PostMessage(self.hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lp)
        time.sleep(0.10)
        for i in range(1, steps + 1):
            xi = int(x1 + (x2 - x1) * i / steps)
            yi = int(y1 + (y2 - y1) * i / steps)
            win32api.PostMessage(self.hwnd, win32con.WM_MOUSEMOVE,
                                 win32con.MK_LBUTTON, win32api.MAKELONG(xi, yi))
            time.sleep(0.04)
        time.sleep(0.10)
        win32api.PostMessage(self.hwnd, win32con.WM_LBUTTONUP, 0,
                             win32api.MAKELONG(x2, y2))

    def click(self, x: int, y: int):
        """THESIS (2026-07-24): only the FIRST synthetic click registers unless the
        button state is cleared first -- aui appears to latch 'button still held'
        after a posted down/up pair, swallowing every later click. So post a
        priming LBUTTONUP + move before the real press."""
        self._spoof_focus()
        lp = win32api.MAKELONG(x, y)
        # Release any grab still held at the PREVIOUS click position, then move
        # there first -- releasing at the new position does not clear a grab
        # taken at the old one.
        last = getattr(self, "_last_click", None)
        if last is not None:
            lp_prev = win32api.MAKELONG(*last)
            win32api.PostMessage(self.hwnd, win32con.WM_MOUSEMOVE, 0, lp_prev)
            time.sleep(0.03)
            win32api.PostMessage(self.hwnd, win32con.WM_LBUTTONUP, 0, lp_prev)
            time.sleep(0.06)
        self._last_click = (x, y)
        win32api.PostMessage(self.hwnd, win32con.WM_MOUSEMOVE, 0, lp)
        time.sleep(0.05)
        win32api.PostMessage(self.hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lp)
        time.sleep(0.05)
        win32api.PostMessage(self.hwnd, win32con.WM_LBUTTONUP, 0, lp)


class GlobalInput:
    """Fallback: pyautogui synthetic global input (uses the REAL cursor and
    keyboard focus — only for when PostMessage is ignored). FAILSAFE stays on:
    top-left corner aborts."""

    def __init__(self, game):
        import pyautogui
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.05
        self.pag = pyautogui
        self.game = game
        self._foreground()

    def _foreground(self):
        """Bring the game window to the foreground. Windows denies
        SetForegroundWindow to background processes; the documented workaround
        is a synthetic ALT tap, which lifts the restriction for this call."""
        hwnd = self.game.get_hwnd()
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
            try:
                win32gui.SetForegroundWindow(hwnd)
            except Exception:
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            finally:
                win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
        time.sleep(0.5)

    def hotkey(self, names):
        self._foreground()
        self.pag.hotkey(*names) if len(names) > 1 else self.pag.press(names[0])

    def type_text(self, text):
        self._foreground()
        self.pag.typewrite(text, interval=0.03)

    def click(self, x, y):
        self._foreground()
        self.pag.click(*self.game.to_screen(x, y))


class Game:
    """Owns the game process and window; all coordinates are client-relative."""

    def __init__(self):
        self.proc = None
        self.hwnd = None

    def launch(self, save: str | None, extra_args: list[str]):
        """Launch the staged exe DIRECTLY.

        Preconditions: preflight_exe() has already asserted binary identity (L6),
        and the staged exe under EXE_DIR is md5-identical to the preflighted
        source build — measured 2026-07-24, which retires the old rationale that
        the installed exe was "a different, older build".

        CORRECTION (2026-07-24): an earlier version of this docstring blamed
        run-ctp2-dbg-crashcapture.ps1 for killing the process with 0xC0000374
        ~1.5s after window creation. That was a confounded conclusion and is
        FALSE. Switching to direct launch changed TWO variables at once, and the
        one that mattered was the -l quoting below, not the launcher. The real
        cause was `--save` defaulting to uiwalk_start on a menu-entry walk.
        The launcher was innocent. Set UIWALK_LAUNCHER=1 to use it.

        Headless is NOT optional and is NOT satisfied by stashing at window
        discovery: the watchdog is started BEFORE the process is spawned and is
        keyed on our child PID, because SDL creates the window before it sets
        the caption and a title-keyed sweep cannot see it during that gap.
        Never launch outside this method."""
        _start_stash_watchdog()
        env = _child_env()
        save_path = find_save(save) if save else None
        if not os.environ.get("UIWALK_LAUNCHER"):
            exe = EXE_DIR / "ctp2.exe"
            if not exe.exists():
                raise FileNotFoundError(exe)
            # Direct argv: pass -l<path> UNQUOTED. subprocess quotes each list
            # element itself; pre-embedding quotes gets them re-escaped and the
            # engine receives a path truncated at the first space ("H:\Program"),
            # which raises "Could not open" and blocks on a modal.
            # nointromovie: civ3_main.cpp:1104 clears g_useIntroMovie, so
            # civapp.cpp:594 skips intromoviewin_DisplayIntroMovie(). Without
            # it the engine plays a ~40s cinematic over the whole client area
            # -- the actual content of every "black/garbage capture" in the
            # long capture regression.
            direct = ["runinbackground", "nointromovie", *extra_args]
            if save_path:
                direct.append(f"-l{save_path}")
            # Register the PID with the watchdog BEFORE waiting for the window,
            # so the very first CreateWindow is already covered.
            self.proc = subprocess.Popen(
                [str(exe), *direct], cwd=str(EXE_DIR), env=env,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            _WATCHED_PROCS.add(self.proc)
            _start_stash_watchdog(self.proc.pid)
            self._wait_for_window()
            return
        script = EXE_DIR / "run-ctp2-dbg-crashcapture.ps1"
        if not script.exists():
            raise FileNotFoundError(script)
        game_args = ["runinbackground", "nointromovie", *extra_args]
        if save_path:
            game_args.append(f'-l"{save_path}"')
        # -GameArgs must be passed NAMED: the script's first positional binds to
        # -SourceRoot and would swallow our first game arg.
        ps_args = ",".join("'" + a.replace("'", "''") + "'" for a in game_args)
        # -PreferRelease flips the script's candidate order to ctp2.exe first.
        # build.bat only builds Final-SDL (-> ctp2.exe); ctp2-dbg.exe is a
        # Debug-SDL artifact that build.bat NEVER refreshes, so the default
        # debug-first order silently runs a stale binary. See preflight_exe().
        pref = " -PreferRelease" if PREFER_RELEASE else ""
        cmd = f"& '{script}'{pref} -GameArgs {ps_args}"
        self.proc = subprocess.Popen(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd],
            cwd=str(EXE_DIR), env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        _WATCHED_PROCS.add(self.proc)
        _start_stash_watchdog(self.proc.pid)
        self._wait_for_window()

    def _find_window(self):
        """Resolve OUR game window, keyed on process ownership.

        Title is NOT a usable key. WINDOW_TITLE is also the project directory
        name, so an Explorer window opened on that folder is captioned
        identically; resolving by title picked it up and every capture came back
        black at that window's size (1080x1920 portrait) instead of 1024x768.
        Ownership is unambiguous and known at spawn time.

        Among our own windows, prefer the caption match, then the largest --
        SDL creates the window before setting its caption, so during that gap
        size is the only discriminator available.
        """
        pids = _game_pids(self.proc)
        if not pids:
            return None
        wins = [w for w in _windows_for_pids(pids) if w[1] > 1 and w[2] > 1]
        if not wins:
            return None
        titled = [w for w in wins if win32gui.GetWindowText(w[0]) == WINDOW_TITLE]
        pick = max(titled or wins, key=lambda w: w[1] * w[2])
        return pick[0]

    def _wait_for_window(self):
        deadline = time.time() + LAUNCH_TIMEOUT_S
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"game exited during launch (code {self.proc.returncode})")
            hwnd = self._find_window()
            if hwnd:
                self.hwnd = hwnd
                _stash_offscreen(self.hwnd)
                return
            time.sleep(1.0)
        raise TimeoutError(f"'{WINDOW_TITLE}' window not found within {LAUNCH_TIMEOUT_S}s")

    def _assert_no_blocking_modal(self):
        """Fail loudly if the engine has raised a native Win32 modal dialog.

        A modal dialog blocks the engine's message pump, so it stops presenting
        frames and PrintWindow returns the LAST PAINTED bitmap forever.  The
        symptom is byte-identical captures across an entire run -- which reads
        as "the game hung" or "our capture is stale" and sends you hunting in
        the wrong layer.  Measured 2026-07-26: 14/14 identical shots, all on the
        startup "Loading..." frame, caused by a 'Load save game Error' (#32770)
        raised ~3s after launch because --save defaulted to a save the engine
        could not load.  Nothing about the game or the capture path was wrong.

        Checked on EVERY handle access rather than once at launch, because a
        modal can appear at any point (a load error, an assert box).  Our stash
        watchdog also parks the dialog off-screen, so it is invisible to a human
        watching the run -- this check is the only thing that can see it.

        Require: self.proc is the game process.
        Guarantee: returns None, or raises RuntimeError naming the dialog.
        """
        if self.proc is None:
            return
        found = []

        def cb(hwnd, _):
            try:
                if win32gui.GetClassName(hwnd) != "#32770":
                    return
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if pid != self.proc.pid:
                    return
                # The TITLE alone ('DB Error') names the error CLASS but not the
                # offending ident, which is the only thing that shortens the
                # hunt. The body lives in the dialog's static-text children, so
                # collect them too -- a title-only report sends you grepping
                # every gamedata file instead of the one record at fault.
                body = []

                def child(ch, _):
                    try:
                        t = win32gui.GetWindowText(ch).strip()
                        if t and t not in ("OK", "Cancel", "&OK", "&Cancel"):
                            body.append(t)
                    except Exception:
                        pass
                    return True
                try:
                    win32gui.EnumChildWindows(hwnd, child, None)
                except Exception:
                    pass
                title = win32gui.GetWindowText(hwnd)
                found.append(f"{title}: {' | '.join(body)}" if body else title)
            except Exception:
                pass
        try:
            win32gui.EnumWindows(cb, None)
        except Exception:
            return
        if found:
            raise RuntimeError(
                f"game is blocked on a native modal dialog: {found!r}. "
                "The engine's message pump is stopped, so every capture from "
                "here on would be a byte-identical stale frame. Common cause: "
                "--save names a save the engine cannot load (it defaults to "
                "'uiwalk_start'); pass --save none for a menu-entry walk.")

    def get_hwnd(self):
        """Return a live window handle; the engine destroys and recreates its
        window between the loading phase and the main game — re-find by title
        whenever the cached handle dies."""
        self._assert_no_blocking_modal()
        if self.hwnd and win32gui.IsWindow(self.hwnd):
            # HEADLESS INVARIANT: re-assert on EVERY access, not just discovery.
            # The engine repositions its window on-screen during scenario load
            # (video mode change) WITHOUT destroying the handle, so a
            # stash-once-at-discovery policy silently leaks a visible window.
            _stash_offscreen(self.hwnd)
            return self.hwnd
        deadline = time.time() + 30
        while time.time() < deadline:
            hwnd = self._find_window()
            if hwnd:
                self.hwnd = hwnd
                _stash_offscreen(self.hwnd)
                return self.hwnd
            if self.proc is not None and self.proc.poll() is not None:
                break
            time.sleep(1.0)
        # Report the process exit code, not just "window gone". A silent exit and
        # a 0xC0000005 look identical from the window side, and the two need
        # completely different investigations -- 0xC0000005 means read the fault
        # address, a clean 0 means something in the game asked to quit.
        code = self.proc.poll() if self.proc is not None else None
        detail = "process still alive (window destroyed)" if code is None \
            else f"process exited, code={code} (0x{code & 0xFFFFFFFF:08X})"
        raise RuntimeError(f"game window gone and did not reappear -- {detail}")

    def client_origin(self) -> tuple[int, int]:
        return win32gui.ClientToScreen(self.get_hwnd(), (0, 0))

    def client_size(self) -> tuple[int, int]:
        left, top, right, bottom = win32gui.GetClientRect(self.get_hwnd())
        return right - left, bottom - top

    def to_screen(self, x: int, y: int) -> tuple[int, int]:
        ox, oy = self.client_origin()
        return ox + x, oy + y

    def screenshot(self) -> np.ndarray:
        """Capture the client area WITHOUT requiring focus: PrintWindow with
        PW_RENDERFULLCONTENT (flag 2), cropped to the client rect. Retries once
        on a stale handle (the engine recreates its window after loading);
        falls back to an mss desktop grab if PrintWindow yields nothing."""
        why = None
        for attempt in (0, 1):
            try:
                return self._grab_printwindow()
            except Exception as e:
                why = e
                if attempt:
                    break
                self.hwnd = None          # force re-resolve, then retry
                time.sleep(1.0)
        # NEVER fall back silently. A silent fallback is how every frame of an
        # entire run came back black 1080x1920 while the harness reported only
        # "score 0.000" -- a capture failure wearing the costume of a content
        # mismatch. Say what broke, and describe the window we actually hold.
        hwnd = self.get_hwnd()
        print(f"[capture] PrintWindow failed: {why!r}\n"
              f"[capture] hwnd={hwnd} title={win32gui.GetWindowText(hwnd)!r} "
              f"class={win32gui.GetClassName(hwnd)!r} "
              f"pid={win32process.GetWindowThreadProcessId(hwnd)[1]} "
              f"rect={win32gui.GetWindowRect(hwnd)} client={self.client_size()}",
              file=sys.stderr)
        ox, oy = self.client_origin()
        cw, ch = self.client_size()
        with mss.mss() as sct:
            raw = sct.grab({"left": ox, "top": oy, "width": cw, "height": ch})
        return np.array(raw)[:, :, :3].copy()

    def _grab_printwindow(self) -> np.ndarray:
        hwnd = self.get_hwnd()
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        w, h = right - left, bottom - top
        hwnd_dc = win32gui.GetWindowDC(hwnd)
        mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()
        bmp = win32ui.CreateBitmap()
        try:
            bmp.CreateCompatibleBitmap(mfc_dc, w, h)
            save_dc.SelectObject(bmp)
            ok = ctypes.windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 2)
            info = bmp.GetInfo()
            data = bmp.GetBitmapBits(True)
            img = np.frombuffer(data, dtype=np.uint8).reshape((info["bmHeight"], info["bmWidth"], 4))[:, :, :3]
        finally:
            for cleanup in (lambda: win32gui.DeleteObject(bmp.GetHandle()),
                            lambda: save_dc.DeleteDC(),
                            lambda: mfc_dc.DeleteDC(),
                            lambda: win32gui.ReleaseDC(hwnd, hwnd_dc)):
                try:
                    cleanup()
                except Exception:
                    pass
        if not ok or not img.any():
            raise RuntimeError("PrintWindow produced no content")
        cox, coy = self.client_origin()
        cx, cy = cox - left, coy - top
        cw, ch = self.client_size()
        return img[cy:cy + ch, cx:cx + cw].copy()

    def kill(self):
        """Terminate the GAME by the PID owning our window handle (never
        name-based); the launcher script child then restores the runtime
        overlay and exits on its own."""
        if self.hwnd:
            try:
                _, pid = win32process.GetWindowThreadProcessId(self.hwnd)
                handle = win32api.OpenProcess(win32con.PROCESS_TERMINATE, False, pid)
                win32api.TerminateProcess(handle, 0)
                win32api.CloseHandle(handle)
            except Exception:
                pass
        if self.proc and self.proc.poll() is None:
            # The launcher restores the runtime overlay after game exit — never
            # hard-kill it, or the next launch starts from a corrupted runtime.
            try:
                self.proc.wait(timeout=180)
            except subprocess.TimeoutExpired:
                print("WARN: launcher still restoring runtime after 180s; leaving it running", file=sys.stderr)


def match_template(shot: np.ndarray, golden: np.ndarray, region, scales,
                   pad: int = 1 << 20) -> float:
    """Best normalized cross-correlation of golden inside shot (or a region of it).

    Require: golden smaller than the searched area at every scale.
    Guarantee: returns max TM_CCOEFF_NORMED score across scales in [(-1)..1].

    `pad` defaults to effectively-infinite, i.e. SEARCH THE WHOLE FRAME; the step
    `region` then survives only as documentation of where the UI is expected.
    MEASURED 2026-07-25: a finite pad=320 passed 5/5 at a 1024x1280 client and then
    failed 0/5 at 2400x1350 -- the menu sat at x[558..1357] while the padded search
    reached only x=1230. ANY constant pad is a magic number encoding one window
    size. The real invariant: the engine draws a FIXED-SIZE UI (the menu panel
    measures 800x600 at every client size seen) letterboxed at a window-dependent
    offset, so a golden is resolution-INDEPENDENT as long as the search area covers
    it. Full-frame is the only pad that holds for every window size.

    Historical note on the same parameter. MEASURED
    2026-07-25: step regions are authored at exactly the golden's own size, so
    the search had ZERO slack and any translation scored ~0. The engine
    letterboxes its 1024x768 UI inside whatever legal window size the primary
    display allows -- at a 1024x1280 window the whole UI sits +264px down, and
    every assert failed while the goldens still matched at 1.000 once allowed to
    slide. An assert should ask "is this UI present", not "is it at this exact
    pixel". Padding restores that. This was misdiagnosed as "stale goldens /
    monitor rotation"; the goldens were never stale."""
    area = shot
    if region:
        x, y, w, h = region
        x0, y0 = max(0, x - pad), max(0, y - pad)
        x1, y1 = min(shot.shape[1], x + w + pad), min(shot.shape[0], y + h + pad)
        area = shot[y0:y1, x0:x1]
    area = np.ascontiguousarray(area)
    best = -1.0
    for s in scales:
        tw, th = int(golden.shape[1] * s), int(golden.shape[0] * s)
        if tw < 8 or th < 8 or tw > area.shape[1] or th > area.shape[0]:
            continue
        tpl = cv2.resize(golden, (tw, th), interpolation=cv2.INTER_AREA)
        score = float(cv2.matchTemplate(area, tpl, cv2.TM_CCOEFF_NORMED).max())
        best = max(best, score)
    return best


def wait_stable(game: Game, timeout_ms: int, interval_ms: int = 300):
    """Block until two consecutive client screenshots are identical (UI settled)."""
    deadline = time.time() + timeout_ms / 1000
    prev = game.screenshot()
    while time.time() < deadline:
        time.sleep(interval_ms / 1000)
        cur = game.screenshot()
        if prev.shape == cur.shape and not np.any(cv2.absdiff(prev, cur)):
            return
        prev = cur


def run_steps(game: Game, inp, steps: list[dict], run_dir: Path, baseline: bool, dry: bool):
    """Execute the walkthrough; returns list of (name, score, threshold, ok)."""
    results = []
    shot_n = 0
    for step in steps:
        if "do" not in step:
            continue                      # {"_comment": ...} documentation entry
        verb = step["do"]
        if verb == "key":
            for _ in range(step.get("times", 1)):
                inp.hotkey(step["keys"].split("+"))
        elif verb == "drag":
            inp.drag(step["x1"], step["y1"], step["x2"], step["y2"])
        elif verb == "select":
            inject_select(game.get_hwnd(), step["path"], int(step["index"]))
        elif verb == "press":
            inject_press(game.get_hwnd(), step["path"])
        elif verb == "click":
            inp.click(step["x"], step["y"])
        elif verb == "type":
            inp.type_text(step["text"])
        elif verb == "wait":
            time.sleep(step["ms"] / 1000)
        elif verb == "wait_stable":
            wait_stable(game, step.get("ms", 5000))
        elif verb == "shot":
            shot_n += 1
            cv2.imwrite(str(run_dir / f"{shot_n:02d}_{step['name']}.png"), game.screenshot())
        elif verb == "assert":
            img = game.screenshot()
            shot_n += 1
            cv2.imwrite(str(run_dir / f"{shot_n:02d}_{step['name']}.png"), img)
            if dry:
                continue
            golden_path = GOLDENS / f"{step['golden']}.png"
            region = step.get("region")
            if baseline:
                x, y, w, h = region or (0, 0, *game.client_size())
                GOLDENS.mkdir(exist_ok=True)
                cv2.imwrite(str(golden_path), img[y:y + h, x:x + w])
                results.append((step["name"], 1.0, 0.0, True))
                continue
            if not golden_path.exists():
                raise FileNotFoundError(f"golden missing: {golden_path} (run --baseline or make_goldens.py)")
            golden = cv2.imread(str(golden_path))
            thr = step.get("threshold", 0.8)
            score = match_template(img, golden, region, step.get("scales", [1.0, 1.25, 1.5]))
            results.append((step["name"], score, thr, score >= thr))
        else:
            raise ValueError(f"unknown step verb: {verb}")
    return results


def record(game: Game, stop_key=win32con.VK_F12):
    """Log user's clicks (client coords) and echo them until F12 is pressed.

    Purpose: user guides the path once; the log becomes a steps script. This is
    the ONE mode that reads the user's real mouse — it only observes, never moves.
    """
    print("RECORDING — click through the game; press F12 to stop.")
    log = []
    was_down = False
    while not (win32api.GetAsyncKeyState(stop_key) & 0x8000):
        down = bool(win32api.GetAsyncKeyState(win32con.VK_LBUTTON) & 0x8000)
        if down and not was_down:
            sx, sy = win32api.GetCursorPos()
            ox, oy = game.client_origin()
            entry = {"do": "click", "x": sx - ox, "y": sy - oy, "t": round(time.time(), 2)}
            log.append(entry)
            print(f"  click at client ({entry['x']}, {entry['y']})")
        was_down = down
        time.sleep(0.02)
    out = RUNS / f"recorded_{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(log, indent=2))
    print(f"wrote {out}")


def main():
    ap = argparse.ArgumentParser(description="CTP2 scripted UI walkthrough")
    ap.add_argument("--run", help="steps JSON to execute (e.g. steps/gl_advances.json)")
    ap.add_argument("--save", default="uiwalk_start", help="save stem for deterministic boot (default uiwalk_start); 'none' to boot to menu")
    ap.add_argument("--baseline", action="store_true", help="write goldens instead of asserting")
    ap.add_argument("--dry", action="store_true", help="run steps, take screenshots, skip asserts")
    ap.add_argument("--record", action="store_true", help="attach + log user clicks until F12 (observes only)")
    ap.add_argument("--attach", action="store_true", help="use an already-running game window instead of launching")
    ap.add_argument("--keep", action="store_true", help="leave the game running on exit")
    ap.add_argument("--global-input", action="store_true", help="fallback: real-cursor pyautogui input (FAILSAFE on)")
    ap.add_argument("--marker", default="MagicMenu", help="string that MUST be present in the exe under test ('none' to skip the check)")
    ap.add_argument("--use-debug-exe", action="store_true", help="prefer ctp2-dbg.exe (Debug-SDL); default is ctp2.exe, which build.bat actually refreshes")
    ap.add_argument("--skip-display-check", action="store_true", help="run even if the primary display cannot supply 1024x768 (expect black captures)")
    ap.add_argument("game_args", nargs="*", help="extra engine args")
    args = ap.parse_args()

    global PREFER_RELEASE
    PREFER_RELEASE = not args.use_debug_exe
    if args.marker.lower() != "none" and not args.attach:
        preflight_exe(args.marker)
    if not args.skip_display_check and not args.attach:
        preflight_display()

    # Deliberately NOT SetProcessDPIAware().  ctp2.exe has no DPI manifest, so
    # on a scaled primary (125% here) Windows virtualizes it.  If WE are aware
    # and the game is not, GetClientRect hands back PHYSICAL pixels (1280x960
    # for a 1024x768 client) and PrintWindow reads across the virtualization
    # boundary -- measured 2026-07-26 as 12 BYTE-IDENTICAL frames in one run
    # (all still on the startup "Loading..." dialog while the game had walked
    # to the map).  Staying unaware puts us in the same coordinate space as the
    # game, so rects are logical and the captured bitmap is the live one.
    game = Game()
    if args.attach or args.record:
        wins = [w for w in pygetwindow.getWindowsWithTitle(WINDOW_TITLE) if w.title == WINDOW_TITLE]
        if not wins:
            print(f"no running '{WINDOW_TITLE}' window to attach to", file=sys.stderr)
            return 2
        game.hwnd = wins[0]._hWnd
        _stash_offscreen(game.hwnd)
    else:
        game.launch(None if args.save == "none" else args.save, args.game_args)

    attempt = 0
    try:
        if args.record:
            record(game)
            return 0
        if not args.run:
            print("nothing to do: pass --run or --record", file=sys.stderr)
            return 2
        inp = GlobalInput(game) if args.global_input else PostInput(game)
        steps = json.loads((TOOL_DIR / args.run).read_text())
        run_dir = RUNS / time.strftime("%Y%m%d-%H%M%S")
        run_dir.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                results = run_steps(game, inp, steps, run_dir, args.baseline, args.dry)
                break
            except (RuntimeError, TimeoutError) as e:
                # Known intermittent load/setup crash class: retry once (see
                # lessons_learned / mom-intermittent-setup-crash — retry, don't
                # re-investigate).
                if attempt >= 1 or args.attach:
                    raise
                attempt += 1
                print(f"WARN: run aborted ({e}); retrying once after relaunch", file=sys.stderr)
                game.kill()
                game.hwnd = None
                game.launch(None if args.save == "none" else args.save, args.game_args)
        (run_dir / "report.json").write_text(json.dumps(
            [{"name": n, "score": round(s, 3), "threshold": t, "pass": ok} for n, s, t, ok in results], indent=2))
        print(f"\n{'CHECK':32s} {'SCORE':>6s} {'THR':>5s}  RESULT")
        for n, s, t, ok in results:
            print(f"{n:32s} {s:6.3f} {t:5.2f}  {'PASS' if ok else 'FAIL'}")
        failed = [r for r in results if not r[3]]
        print(f"\n{len(results) - len(failed)}/{len(results)} passed; artifacts in {run_dir}")
        return 1 if failed else 0
    finally:
        if not (args.keep or args.attach or args.record):
            game.kill()


if __name__ == "__main__":
    sys.exit(main())
