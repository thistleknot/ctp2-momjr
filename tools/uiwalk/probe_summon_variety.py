#!/usr/bin/env python
"""probe_summon_variety.py -- observe that the summon actually VARIES in-game.

WHAT THIS EXISTS TO PROVE. The 75-mana summon used to resolve through five
per-sphere CONSTANTS; it now rolls, weighted, over every ladder rung the caster
has unlocked (mom_summon.slc, generated). The static gate proves the POOLS are
populated. Only a running game proves the ROLL varies, and that is what this
measures: summon repeatedly as one tribe and count DISTINCT result popups.

WHY A DEDICATED DRIVER instead of a steps JSON. Two attempts failed, both from
one root cause -- the alertbox arm is NOT at a fixed pixel:

  * v1 clicked a hardcoded (290,385). A plain Message() window stacks ABOVE the
    MAGIC STATUS alertbox and swallowed every click; mana sat pinned at 100/100
    for 60 turns.
  * v2 tried to dismiss that Message first at MSG_CLOSE_CAPTURE (497,61). That
    constant is valid only WHILE the message box is up; with no box there it is
    live top-bar chrome, and the click opened the OPTIONS menu instead.

Both are the absolute-coordinate defect this harness keeps re-learning. The right
instrument already exists: turnloop.click_alert_arm(), which MEASURES the arm
centres out of the live frame and whose success test is "did the box close?" --
the only honest one, since a missed click lands on the map, repaints, and yields
a frame delta indistinguishable from a hit.

Reads pixels only. It CANNOT see an AI player's mana -- that renders for the
human alone -- so this probe speaks to the summon roll, never to AI spending.

=============================================================================
PARKED 2026-07-29, UNPROVEN. Read this before touching it again.
=============================================================================
Three attempts, three variants of ONE root cause. Recorded so the next attempt
starts from the evidence instead of re-deriving it.

  v1  hardcoded click (290,385) on the arm.
      OBSERVED: mana pinned 100/100 for 60 turns. A plain Message() window
      stacks ABOVE the alertbox and swallowed every click.
  v2  dismiss that Message first at MSG_CLOSE_CAPTURE (497,61).
      OBSERVED: the OPTIONS menu opened. That constant is only valid WHILE the
      message box is up; with no box there it is live top-bar chrome.
  v3  this driver -- turnloop.click_alert_arm(), which MEASURES arm centres.
      OBSERVED: `only 0 buttons found` at turns 8/16/24/32. The MAGIC STATUS
      alertbox never opened at all, so there was nothing to measure, and
      dismiss_message's fall-through clicks PANNED THE MAP once per attempt --
      visible to the operator as the view scrolling repeatedly.

THE REAL BLOCKER is upstream of the click: `inp.hotkey(["j"])` did not raise the
menu here, while the SAME keypress DOES raise it from a steps JSON (two runs
today captured working MAGIC STATUS frames that way, e.g.
runs/20260729-164240/34_magic025.png). So the difference is the driver, not the
mod. Prime suspect: turnloop.end_turn(...,"key") is not advancing turns in this
path either -- turnloop's own loop reports TURN_DID_NOT_ADVANCE_AT_1 on this
build while uiwalk + the full_game_v3 cycle runs 25/25 clean -- so the game may
be sitting behind a modal from turn 1 with 'j' going nowhere.

NEXT ATTEMPT SHOULD: drive boot and END TURN from the full_game_v3 steps cycle
(proven), and only drop into measured-click code for the arm itself. Do NOT call
dismiss_message when no box is known to be up -- its misses are what pan the map.

DO NOT re-try a hardcoded arm coordinate. That is the defect class this harness
keeps re-learning, and it has now cost three runs.
"""
from __future__ import annotations

import ctypes
import sys
import time
from pathlib import Path

import cv2

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import uiwalk                      # noqa: E402
import turnloop                    # noqa: E402

TURNS = 72
SUMMON_EVERY = 8       # ~+19 mana/turn against a 75 cost always clears in 8


def main() -> int:
    uiwalk.PREFER_RELEASE = True
    uiwalk.preflight_exe("MagicMenu")
    uiwalk.preflight_display()
    ctypes.windll.user32.SetProcessDPIAware()

    run_dir = uiwalk.RUNS / (time.strftime("%Y%m%d-%H%M%S") + "-summonvar")
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"artifacts -> {run_dir}")
    turnloop._CALIB_DEBUG_DIR = run_dir

    game = uiwalk.Game()
    watcher = turnloop.ErrorWatcher(set())
    watcher.start()
    captured: list[str] = []

    try:
        # A NEW game, never a save: saves cache compiled SLIC, so a stale one
        # would test the OLD constant-per-sphere summon and pass for the wrong
        # reason (mom-slic-save-cache).
        game.launch(None, [])
        failed = [r for r in turnloop.boot(game, run_dir) if not r[3]]
        if failed:
            print("BOOT_FAILED: " + ", ".join(r[0] for r in failed))
            return 2
        if watcher.hits:
            print("SLIC_ERROR_AT_LOAD")
            return 3

        inp = uiwalk.PostInput(game)

        # Found a city: the summon guard is `player[0].cities > 0` and the spawn
        # anchors on the first city, so with no city the feature is untestable
        # rather than broken. 'b' is SETTLE; MoM has no settler, peasants found.
        inp.hotkey(["b"])
        time.sleep(2.0)
        uiwalk.wait_stable(game, 8000)
        # AutoOpenCityWindow raises the build manager over everything; close by
        # injection, since clicks are dead on aui surfaces.
        uiwalk.inject_press(game.hwnd, "BuildEditorWindow.CloseButton")
        time.sleep(1.0)
        uiwalk.wait_stable(game, 6000)

        for turn in range(1, TURNS + 1):
            turnloop.end_turn(game, inp, "key")
            uiwalk.wait_stable(game, 20000)
            if watcher.hits:
                print(f"SLIC_ERROR_AT_TURN_{turn}: {watcher.hits[-1]}")
                return 3
            if turn % SUMMON_EVERY:
                continue

            turnloop.dismiss_message(game, inp)
            inp.hotkey(["j"])
            time.sleep(1.5)
            uiwalk.wait_stable(game, 8000)
            cv2.imwrite(str(run_dir / f"menu_t{turn:03d}.png"), game.screenshot())

            # Arm 0 is Summon Creature (75). Arms render in REVERSE declaration
            # order; click_alert_arm already accounts for that.
            if not turnloop.click_alert_arm(game, inp, 0, f"summon@{turn}"):
                print(f"  [probe] turn {turn}: arm click missed", flush=True)
                continue

            # The order is PLACED now and RESOLVES on the next BeginTurn, so the
            # popup naming the creature is one turn away.
            turnloop.end_turn(game, inp, "key")
            uiwalk.wait_stable(game, 20000)
            path = run_dir / f"summon_result_t{turn:03d}.png"
            cv2.imwrite(str(path), game.screenshot())
            captured.append(path.name)
            print(f"  [probe] turn {turn}: result -> {path.name}", flush=True)
    finally:
        watcher.stop()
        game.kill()

    print(f"\nsummon results captured: {len(captured)}")
    for c in captured:
        print(f"  {c}")
    print(f"\nartifacts in {run_dir}")
    print("NEXT: compare the result frames. The summon VARIES iff more than one "
          "distinct creature appears. Identical creatures in every frame "
          "falsifies the weighted roll.")
    return 0 if captured else 1


if __name__ == "__main__":
    raise SystemExit(main())
