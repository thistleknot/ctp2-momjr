"""probe_artifacts.py -- walk the Artifacts and Wishes spokes headlessly.

WHAT THIS PROVES, and why the earlier runs could not. The 250-turn rotation read
the sphere row off the `j` panel -- a value the fix itself wrote -- so it could
confirm the variable and nothing downstream of it. This probe PRESSES ARMS, so
what it exercises is the consequence: which segment a button body opens, whether
its strings render, and whether the state a wish spends actually moves.

It also covers the one summon site the rotation could never reach: the human
picker at mom_spells.slc, which only runs when a person presses Summon Creature.

THE WALK, one arm per step, each with a capture:

    j              -> the Hub. Four arms now: Artifacts / Workings / Summon / Close
                      (left to right; declaration order is the reverse).
    arm 3          -> Artifacts. Empty-handed this is the "you bear no artifact"
                      gate; holding the lamp it is the real panel.
    arm 2          -> Wishes.
    arm 2          -> Wish: Riches, and the result popup.
    j, arm 1       -> Summon Creature, the human picker.

Arms are addressed by DECLARATION index. `click_alert_arm` maps that to the
screen with buttons[-(index+1)] because the box paints its arms in reverse, so
declaration 0 (`Close`) is the RIGHTMOST button. Getting this backwards presses
Close every time and every panel looks empty.

Reading the result is by capture, not by return code: every arm ends in Kill()
and immediately opens the next segment, so `click_alert_arm`'s "did the box
close" test reports False for a successful navigation. The captures are the
evidence; the booleans are not.

Usage:  python tools/uiwalk/probe_artifacts.py [--turns 6]
"""
from __future__ import annotations

import argparse
import ctypes
import json
import shutil
import sys
import time
from pathlib import Path

import cv2

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import uiwalk      # noqa: E402
import turnloop    # noqa: E402

SCEN = HERE.parent.parent / "scen0000"
GAMEDATA = SCEN / "default/gamedata"
PROBE_SRC = HERE / "probe_slic/artifact_grant.slc"
PROBE_DST = GAMEDATA / "artifact_grant.slc"
SCEN_SLC = GAMEDATA / "scenario.slc"

PROLOGUE = 53
CYCLE = 7


def _strip(text: str) -> str:
    return "".join(l for l in text.splitlines(keepends=True) if "artifact_grant.slc" not in l)


def _install() -> bytes:
    """Install the grant instrument. Strips any leftover FIRST.

    A killed run skips the restore, so startup cannot assume a clean tree --
    a leaked instrument would silently poison the next run's result.
    """
    if PROBE_DST.exists():
        PROBE_DST.unlink()
    backup = SCEN_SLC.read_bytes()
    SCEN_SLC.write_text(_strip(SCEN_SLC.read_text(encoding="latin-1")).rstrip("\n")
                        + '\n#include "artifact_grant.slc"\n', encoding="latin-1")
    shutil.copy(PROBE_SRC, PROBE_DST)
    return backup


def _restore(backup: bytes) -> None:
    SCEN_SLC.write_bytes(backup)
    if PROBE_DST.exists():
        PROBE_DST.unlink()


def _shot(game, run_dir: Path, name: str) -> Path:
    uiwalk.wait_stable(game, 5000)
    p = run_dir / f"{name}.png"
    cv2.imwrite(str(p), game.screenshot())
    print(f"  [shot] {name}", flush=True)
    return p


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--turns", type=int, default=6)
    args = ap.parse_args()

    uiwalk.PREFER_RELEASE = True
    uiwalk.preflight_exe("MagicMenu")
    uiwalk.preflight_display()
    ctypes.windll.user32.SetProcessDPIAware()

    run_dir = uiwalk.RUNS / (time.strftime("%Y%m%d-%H%M%S") + "-artifacts")
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"artifacts -> {run_dir}")

    steps = json.loads((HERE / "steps/full_game_v3.json").read_text())
    row = uiwalk.scenario_pack_index("mom")
    for s in steps[:PROLOGUE]:
        if s.get("path") == "ScenarioWindow.AvailableListBox" and s.get("index"):
            s["index"] = row
            break
    prologue, cycle = steps[:PROLOGUE], steps[PROLOGUE:PROLOGUE + CYCLE]
    cycle = [{"do": "press", "path": "DipWizard.ViewButtons.RejectButton"}] + cycle

    # SEED THE ALERTBOX SEND FACTOR INSTEAD OF CALIBRATING IT.
    #
    # turnloop._calibrate discovers the factor by clicking and asking "did the
    # box CLOSE". That test is valid for a Close arm and WRONG for a navigation
    # arm, which replaces the box with another one -- so calibration reports
    # failure on every candidate, leaves the provisional 1.0 latched, and every
    # later click in the walk misses. Measured: the Artifacts arm still navigated
    # (one of the trial clicks happened to land) while the Wishes arm did not,
    # which is exactly the signature of a bad latched factor rather than a bad
    # target.
    #
    # x1.25 for the alertbox surface is settled and measured -- it is not derived
    # from geometry, and the message surface latches x0.80 in the same run.
    # Seeding it skips a calibration whose success test cannot work here.
    turnloop.SEND_SCALE["alertbox"] = 1.25

    backup = _install()
    turnloop._CALIB_DEBUG_DIR = run_dir
    game = uiwalk.Game()
    watcher = turnloop.ErrorWatcher(set())
    watcher.start()
    ok = False
    try:
        game.launch(None, [])
        inp = uiwalk.PostInput(game)
        uiwalk.run_steps(game, inp, prologue, run_dir, baseline=False, dry=False)
        for t in range(2, args.turns + 1):
            uiwalk.run_steps(game, inp, cycle, run_dir, baseline=False, dry=False)
            if watcher.hits:
                print(f"  ERROR at turn {t}: {watcher.hits[-1]}", flush=True)
                return 1

        openj = [{"do": "key", "keys": "j"}, {"do": "wait_stable", "ms": 7000}]

        # --- the artifact walk -------------------------------------------------
        uiwalk.run_steps(game, inp, openj, run_dir, baseline=False, dry=False)
        _shot(game, run_dir, "01_hub")
        n = len(turnloop.find_alert_buttons(game.screenshot()))
        print(f"  hub arms rendered: {n} (expect 4)", flush=True)

        turnloop.click_alert_arm(game, inp, 3, "Artifacts")
        _shot(game, run_dir, "02_artifacts")

        turnloop.click_alert_arm(game, inp, 2, "Wishes")
        _shot(game, run_dir, "03_wishes")
        n = len(turnloop.find_alert_buttons(game.screenshot()))
        print(f"  wishes arms rendered: {n} (expect 5 -- this is AT the ceiling)",
              flush=True)

        turnloop.click_alert_arm(game, inp, 2, "Wish: Riches")
        _shot(game, run_dir, "04_wish_result")
        turnloop.click_alert_arm(game, inp, 0, "Close")

        # --- the human summon picker, unreachable from the rotation ------------
        uiwalk.run_steps(game, inp, openj, run_dir, baseline=False, dry=False)
        _shot(game, run_dir, "05_hub_after_wish")
        turnloop.click_alert_arm(game, inp, 1, "Summon Creature")
        _shot(game, run_dir, "06_summon_ordered")
        uiwalk.run_steps(game, inp, cycle, run_dir, baseline=False, dry=False)
        uiwalk.run_steps(game, inp, openj, run_dir, baseline=False, dry=False)
        _shot(game, run_dir, "07_hub_after_summon")

        ok = not watcher.hits
        if watcher.hits:
            print(f"  ERROR: {watcher.hits[-1]}", flush=True)
    finally:
        watcher.stop()
        game.kill()
        _restore(backup)
        print("[probe] scenario restored (instrument removed)")

    print(f"\n{'PASS' if ok else 'FAIL'} -- captures in {run_dir}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
