"""Capture the scenario picker WITHOUT selecting anything.

Why this exists: ScenarioWindow.AvailableListBox is driven by inject_select,
which calls SelectItem -- and SelectItem has NO bounds check, so a stale index
is an access violation, not an error. full_game_v3.json pins `index: 3`, a
number frozen when the Scenarios directory held fewer packs. Adding `smm`
shifted the list, and every run since has died right after the main-menu shot
with 0xC0000005.

The list is not readable through any injection verb, so the only honest
instrument is a picture of it. This probe walks the proven prologue up to the
point where the picker is realised and STOPS -- no select, nothing that can
fault -- then screenshots. Read the frame, count the rows, and put the real
index back into the steps file.

Run: python tools/uiwalk/probe_scenario_list.py
"""
from __future__ import annotations

import ctypes
import time
from pathlib import Path

import cv2

import uiwalk

HERE = Path(__file__).resolve().parent

# The prologue up to the realised picker, transcribed from full_game_v3.json
# steps 1..12. Deliberately NOT sliced out of that file: this probe must remain
# runnable even while the steps file holds the broken index it exists to fix.
STEPS = [
    {"do": "wait", "ms": 6000},
    {"do": "key", "keys": "esc"},
    {"do": "wait", "ms": 3000},
    {"do": "key", "keys": "esc"},
    {"do": "wait_stable", "ms": 30000},
    {"do": "shot", "name": "main_menu"},
    {"do": "press", "path": "InitPlayWindow.NewGameButton"},
    {"do": "wait", "ms": 4000},
    {"do": "wait_stable", "ms": 20000},
    {"do": "shot", "name": "newgame"},
    {"do": "press", "path": "SPNewGameWindow.ScenarioButton"},
    {"do": "wait", "ms": 4000},
    {"do": "wait_stable", "ms": 20000},
    {"do": "shot", "name": "scenario_list"},
]

# The picker shows three packs at a time and there are more below the fold, so
# the visible frame alone cannot tell you a row number -- which is exactly how
# "mom is row 5" survived one correction and was still wrong (it loaded smm).
# There is no scroll verb, so page with the scrollbar's down-arrow, measured off
# the 03_scenario_list capture: the listbox track ends at x=797 and its arrow
# button sits at y=819. Clicking chrome is safe here; the fault mode being
# avoided is inject_select's unbounded SelectItem, which this probe never calls.
for _i in range(6):
    STEPS += [
        {"do": "click", "x": 797, "y": 819},
        {"do": "wait", "ms": 700},
        {"do": "shot", "name": f"list_scroll{_i}"},
    ]


def main() -> int:
    uiwalk.PREFER_RELEASE = True
    uiwalk.preflight_exe("MagicMenu")
    uiwalk.preflight_display()
    ctypes.windll.user32.SetProcessDPIAware()

    run_dir = uiwalk.RUNS / (time.strftime("%Y%m%d-%H%M%S") + "-scenlist")
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"artifacts -> {run_dir}")

    game = uiwalk.Game()
    try:
        game.launch(None, [])
        inp = uiwalk.PostInput(game)
        uiwalk.run_steps(game, inp, STEPS, run_dir, baseline=False, dry=False)
        cv2.imwrite(str(run_dir / "final.png"), game.screenshot())
    finally:
        game.kill()

    shots = sorted(p.name for p in run_dir.glob("*.png"))
    print(f"frames: {shots}")
    print("READ scenario_list -- the pack rows in order. The row index of 'mom' "
          "is what full_game_v3.json step 13 must select.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
