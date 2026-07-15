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
import subprocess
import sys
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
EXE_CANDIDATES = ["ctp2-dbg.exe", "ctp2-log.exe", "ctp2.exe"]
WINDOW_TITLE = "Call To Power 2"
LAUNCH_TIMEOUT_S = 90
GOLDENS = TOOL_DIR / "goldens"
RUNS = TOOL_DIR / "runs"

VK = {
    "enter": win32con.VK_RETURN, "backspace": win32con.VK_BACK, "esc": win32con.VK_ESCAPE,
    "tab": win32con.VK_TAB, "space": win32con.VK_SPACE, "ctrl": win32con.VK_CONTROL,
    "shift": win32con.VK_SHIFT, "alt": win32con.VK_MENU,
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

    def click(self, x: int, y: int):
        self._spoof_focus()
        lp = win32api.MAKELONG(x, y)
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
        win32gui.SetForegroundWindow(game.hwnd)
        time.sleep(0.5)

    def hotkey(self, names):
        self.pag.hotkey(*names) if len(names) > 1 else self.pag.press(names[0])

    def type_text(self, text):
        self.pag.typewrite(text, interval=0.03)

    def click(self, x, y):
        self.pag.click(*self.game.to_screen(x, y))


class Game:
    """Owns the game process and window; all coordinates are client-relative."""

    def __init__(self):
        self.proc = None
        self.hwnd = None

    def launch(self, save: str | None, extra_args: list[str]):
        """Launch through run-ctp2-dbg-crashcapture.ps1 so the patched runtime
        overlay (8MB-stack exe, current DLLs/map) is staged exactly as in manual
        sessions — the restored 'installed' exe is a different, older build that
        stalls during deep load chains. The script blocks until game exit and
        then restores originals, so it runs as our child for the whole session."""
        script = EXE_DIR / "run-ctp2-dbg-crashcapture.ps1"
        if not script.exists():
            raise FileNotFoundError(script)
        game_args = ["runinbackground", *extra_args]
        if save:
            game_args.append(f'-l"{find_save(save)}"')
        # -GameArgs must be passed NAMED: the script's first positional binds to
        # -SourceRoot and would swallow our first game arg.
        ps_args = ",".join("'" + a.replace("'", "''") + "'" for a in game_args)
        cmd = f"& '{script}' -GameArgs {ps_args}"
        self.proc = subprocess.Popen(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd],
            cwd=str(EXE_DIR), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._wait_for_window()

    def _wait_for_window(self):
        deadline = time.time() + LAUNCH_TIMEOUT_S
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"game exited during launch (code {self.proc.returncode})")
            wins = [w for w in pygetwindow.getWindowsWithTitle(WINDOW_TITLE) if w.title == WINDOW_TITLE]
            if wins:
                self.hwnd = wins[0]._hWnd
                return
            time.sleep(1.0)
        raise TimeoutError(f"'{WINDOW_TITLE}' window not found within {LAUNCH_TIMEOUT_S}s")

    def get_hwnd(self):
        """Return a live window handle; the engine destroys and recreates its
        window between the loading phase and the main game — re-find by title
        whenever the cached handle dies."""
        if self.hwnd and win32gui.IsWindow(self.hwnd):
            return self.hwnd
        deadline = time.time() + 30
        while time.time() < deadline:
            wins = [w for w in pygetwindow.getWindowsWithTitle(WINDOW_TITLE) if w.title == WINDOW_TITLE]
            if wins:
                self.hwnd = wins[0]._hWnd
                return self.hwnd
            if self.proc is not None and self.proc.poll() is not None:
                break
            time.sleep(1.0)
        raise RuntimeError("game window gone and did not reappear")

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
        for attempt in (0, 1):
            try:
                return self._grab_printwindow()
            except Exception:
                if attempt:
                    break
                self.hwnd = None          # force re-resolve, then retry
                time.sleep(1.0)
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


def match_template(shot: np.ndarray, golden: np.ndarray, region, scales) -> float:
    """Best normalized cross-correlation of golden inside shot (or a region of it).

    Require: golden smaller than the searched area at every scale.
    Guarantee: returns max TM_CCOEFF_NORMED score across scales in [(-1)..1].
    """
    area = shot
    if region:
        x, y, w, h = region
        area = shot[y:y + h, x:x + w]
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
        verb = step["do"]
        if verb == "key":
            for _ in range(step.get("times", 1)):
                inp.hotkey(step["keys"].split("+"))
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
    ap.add_argument("game_args", nargs="*", help="extra engine args")
    args = ap.parse_args()

    ctypes.windll.user32.SetProcessDPIAware()
    game = Game()
    if args.attach or args.record:
        wins = [w for w in pygetwindow.getWindowsWithTitle(WINDOW_TITLE) if w.title == WINDOW_TITLE]
        if not wins:
            print(f"no running '{WINDOW_TITLE}' window to attach to", file=sys.stderr)
            return 2
        game.hwnd = wins[0]._hWnd
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
