#!/usr/bin/env python
"""fix_profile_res.py -- point userprofile.txt at a mode the CURRENT primary allows.

WHY THIS EXISTS. CTP2 honours `userprofile.txt`'s ScreenResWidth/Height only when
that exact mode appears in the **primary** display's mode list
(`display_IsLegalResolution`, fed by `display_EnumerateDisplayModes`, which reads
display 0 only). The operator's primary display changes -- rotated to portrait,
rotated back, swapped between heads -- and a mode that was legal an hour ago is
illegal now. Observed within a single session on 2026-08-02:

    \\\\.\\DISPLAY4  1080x1920 portrait   -> 1024x1280 LEGAL, 1024x768 illegal
    \\\\.\\DISPLAY1  1920x1080 landscape  -> 1024x768  LEGAL, 1024x1280 illegal

So there is no correct constant to hardcode, and hardcoding one is why this
condition has now cost three sessions. Ask the OS instead.

WHAT IT DOES NOT DO: it never changes the operator's display configuration. It
only edits the game's own profile to agree with whatever the desktop currently
is, which is the harness's config, not the operator's environment.

PREFERENCE ORDER, and each rank is measured rather than assumed:
  1. 1024x768   -- canonical; uiwalk's step coordinates were authored for this
                   client size, so nothing reflows and no aim point moves.
  2. 1024x1280  -- the portrait fallback. Legal on a rotated primary, boots, and
                   advances turns (measured 2026-07-26).
  3. 1280x1024  -- landscape, larger; widgets move but the surface is valid.
  * 768x1024 is DELIBERATELY EXCLUDED even though it is legal in portrait: it
    fails "boot asserts failed: new_game_check" (measured 2026-07-26).

Run standalone, or import `ensure_legal_profile_res()` from a probe's preflight.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as w
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
INSTALL = HERE.parent.parent.parent.parent
# preflight_display() reads EXE_DIR/userprofile.txt, and uiwalk's EXE_DIR is this
# FIXED constant -- not the directory of the exe it actually launches, which may
# be a different tree carrying its own profile. Keep both in step.
PROFILES = [
    INSTALL / "ctp2_program" / "ctp" / "userprofile.txt",
    Path("H:/Games/civctp2/ctp2_code/ctp/userprofile.txt"),
]

# 1280x1024 FIRST -- the operator's stated requirement (2026-08-02: "I need a
# 1280x1024 resolution bro", "windowed"). The rest are fallbacks for when the
# primary cannot supply it, which happens when the primary is rotated to
# portrait; they exist so the harness degrades instead of aborting.
PREFERRED = [(1280, 1024), (1024, 768), (1024, 1280)]


class DEVMODE(ctypes.Structure):
    _fields_ = [
        ("dmDeviceName", ctypes.c_wchar * 32), ("dmSpecVersion", w.WORD),
        ("dmDriverVersion", w.WORD), ("dmSize", w.WORD), ("dmDriverExtra", w.WORD),
        ("dmFields", w.DWORD), ("dmPositionX", ctypes.c_long),
        ("dmPositionY", ctypes.c_long), ("dmDisplayOrientation", w.DWORD),
        ("dmDisplayFixedOutput", w.DWORD), ("dmColor", ctypes.c_short),
        ("dmDuplex", ctypes.c_short), ("dmYResolution", ctypes.c_short),
        ("dmTTOption", ctypes.c_short), ("dmCollate", ctypes.c_short),
        ("dmFormName", ctypes.c_wchar * 32), ("dmLogPixels", w.WORD),
        ("dmBitsPerPel", w.DWORD), ("dmPelsWidth", w.DWORD),
        ("dmPelsHeight", w.DWORD), ("dmDisplayFlags", w.DWORD),
        ("dmDisplayFrequency", w.DWORD), ("dmICMMethod", w.DWORD),
        ("dmICMIntent", w.DWORD), ("dmMediaType", w.DWORD),
        ("dmDitherType", w.DWORD), ("dmReserved1", w.DWORD),
        ("dmReserved2", w.DWORD), ("dmPanningWidth", w.DWORD),
        ("dmPanningHeight", w.DWORD),
    ]


class DISPLAY_DEVICE(ctypes.Structure):
    _fields_ = [
        ("cb", w.DWORD), ("DeviceName", ctypes.c_wchar * 32),
        ("DeviceString", ctypes.c_wchar * 128), ("StateFlags", w.DWORD),
        ("DeviceID", ctypes.c_wchar * 128), ("DeviceKey", ctypes.c_wchar * 128),
    ]


DISPLAY_DEVICE_PRIMARY = 0x4


def primary_modes() -> tuple[str, set[tuple[int, int]], tuple[int, int]]:
    """(device name, its legal modes, its current mode) for the PRIMARY display."""
    u = ctypes.windll.user32
    dd = DISPLAY_DEVICE()
    dd.cb = ctypes.sizeof(dd)
    n = 0
    while u.EnumDisplayDevicesW(None, n, ctypes.byref(dd), 0):
        if dd.StateFlags & DISPLAY_DEVICE_PRIMARY:
            name = dd.DeviceName
            cur = DEVMODE()
            cur.dmSize = ctypes.sizeof(DEVMODE)
            u.EnumDisplaySettingsW(name, -1, ctypes.byref(cur))
            modes: set[tuple[int, int]] = set()
            dm = DEVMODE()
            dm.dmSize = ctypes.sizeof(DEVMODE)
            i = 0
            while u.EnumDisplaySettingsW(name, i, ctypes.byref(dm)):
                modes.add((dm.dmPelsWidth, dm.dmPelsHeight))
                i += 1
            return name, modes, (cur.dmPelsWidth, cur.dmPelsHeight)
        n += 1
    raise SystemExit("no primary display found")


def ensure_legal_profile_res(windowed: bool = True, verbose: bool = True) -> tuple[int, int]:
    """Rewrite every known profile to a mode the current primary allows.

    Require: at least one of PREFERRED is legal on the primary.
    Guarantee: every profile that exists names the same legal mode, and
      WindowedMode is left at Yes unless `windowed` is False -- the harness
      stashes the window off-screen, which a fullscreen surface cannot be.
    """
    name, modes, cur = primary_modes()
    pick = next((m for m in PREFERRED if m in modes), None)
    if verbose:
        print(f"[profile] primary {name} current={cur[0]}x{cur[1]} "
              f"({len(modes)} modes)")
    if pick is None:
        raise SystemExit(
            f"[profile] none of {PREFERRED} is legal on {name}. "
            "Add a mode this display supports to PREFERRED, after checking it "
            "actually boots -- 768x1024 is legal in portrait and still fails "
            "new_game_check.")
    if verbose:
        print(f"[profile] choosing {pick[0]}x{pick[1]}")

    for prof in PROFILES:
        if not prof.exists():
            if verbose:
                print(f"[profile] skip (missing): {prof}")
            continue
        s = prof.read_text(errors="ignore")
        before = s
        s = re.sub(r"(?m)^ScreenResWidth=.*$",  f"ScreenResWidth={pick[0]}",  s, count=1)
        s = re.sub(r"(?m)^ScreenResHeight=.*$", f"ScreenResHeight={pick[1]}", s, count=1)
        if windowed:
            s = re.sub(r"(?m)^WindowedMode=.*$", "WindowedMode=Yes", s, count=1)
        if s != before:
            prof.write_text(s)
        if verbose:
            vals = [l for l in s.splitlines()
                    if l.startswith(("ScreenRes", "WindowedMode"))]
            print(f"[profile] {prof}: {vals}")
    return pick


if __name__ == "__main__":
    ensure_legal_profile_res(windowed="--fullscreen" not in sys.argv)
