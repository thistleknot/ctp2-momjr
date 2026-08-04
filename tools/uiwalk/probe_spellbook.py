"""probe_spellbook.py -- does the spellbook still open, and what is on it?

mom_spells.slc has carried Flame Strike (50) and Demon Strike (100) plus an AI
caster since Phase D, and its ONLY entry point is

    trigger 'MomOpenSpellbook' on "ControlPanelWindow.ControlPanel.ShortcutPad.MagicButton"

The auto-popup that used to open it at 60% pool was removed 2026-07-25 for modal
stacking, so that trigger is the whole surface. It has never been exercised
headlessly, and a stale note claimed the in-game panel was unreachable -- wrong:
run_steps has a `trigger` verb wired to inject_trigger, which is precisely
SlicEngine::RunUITriggers, the path a real left-click takes.

This boots into a game, fires the control, and photographs the result.
"""
from __future__ import annotations

import ctypes, json, sys, time
from pathlib import Path
import cv2

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import uiwalk  # noqa: E402

PROLOGUE = 53
MAGIC = "ControlPanelWindow.ControlPanel.ShortcutPad.MagicButton"


def main() -> int:
    uiwalk.PREFER_RELEASE = True
    uiwalk.preflight_exe("MagicMenu")
    uiwalk.preflight_display()
    ctypes.windll.user32.SetProcessDPIAware()

    steps = json.loads((HERE / "steps/full_game_v3.json").read_text())
    row = uiwalk.scenario_pack_index("mom")
    for s in steps[:PROLOGUE]:
        if s.get("path") == "ScenarioWindow.AvailableListBox" and s.get("index"):
            s["index"] = row
            break
    prologue = steps[:PROLOGUE]

    run_dir = uiwalk.RUNS / (time.strftime("%Y%m%d-%H%M%S") + "-spellbook")
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"artifacts -> {run_dir}")

    game = uiwalk.Game()
    try:
        game.launch(None, [])
        inp = uiwalk.PostInput(game)
        uiwalk.run_steps(game, inp, prologue, run_dir, baseline=False, dry=False)
        before = game.screenshot()
        cv2.imwrite(str(run_dir / "10_before.png"), before)

        uiwalk.run_steps(game, inp, [
            {"do": "trigger", "path": MAGIC},
            {"do": "wait", "ms": 2500},
            {"do": "shot", "name": "spellbook"},
        ], run_dir, baseline=False, dry=False)

        after = game.screenshot()
        cv2.imwrite(str(run_dir / "12_after.png"), after)
        import numpy as np
        delta = int(np.count_nonzero(cv2.absdiff(before, after).max(axis=2) > 12))
        print(f"frame delta after firing MagicButton: {delta} px")
        print("  ~0        = the trigger did not land (or opened nothing)")
        print("  thousands = a panel opened -- READ 11_spellbook.png for its arms")
    finally:
        game.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
