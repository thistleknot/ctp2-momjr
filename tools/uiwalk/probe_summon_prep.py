#!/usr/bin/env python
"""probe_summon_prep.py -- prove summon preparation ticks in a RUNNING GAME.

WHAT IT PROVES. A summon is no longer instant: committing one debits the mana,
rolls the creature, and starts a countdown equal to that creature's sphere rung.
Static gates prove the state machine has the right SHAPE -- the countdown is
seeded from the rung, pending is cleared on arrival, the arrival branch is
mutually exclusive with commit. None of that proves the engine actually ticks it.

The assertion is visible on one surface: the 'j' MAGIC STATUS panel prints
`Preparing: N turn(s) left`. Commit a summon, then open the panel EVERY turn and
read N. It must fall 1 per turn and the creature must arrive on the turn it
reaches 0 -- not before, not after.

Sampling every turn is the whole point and is why this is a separate probe from
probe_long_game.py: a rung-1 creature has a ONE turn countdown, so a probe that
samples every 5 or 10 turns would step straight over the entire mechanic and see
nothing, which looks identical to the feature being dead.

WHAT IT MISSES, stated up front: it reads the COUNTDOWN, not the creature. It
cannot show that the arriving unit is the one that was rolled at commit time --
only that something arrived on schedule. It also cannot reach rung 2+ in a short
game, so it exercises the 1-turn case and the state machine, not the long
countdowns; those are covered by the gate and by the rung-seeded assertion.
"""
from __future__ import annotations

import ctypes
import json
import os
import sys
import time
from pathlib import Path

import cv2

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import uiwalk                      # noqa: E402
import turnloop                    # noqa: E402

PROLOGUE = 53
CYCLE = 7
TURNS = int(os.environ.get("PROBE_TURNS", "26"))
FIRST_SUMMON = 6       # ~when 75 mana is first affordable
WATCH = 6              # turns to sample every-turn after a commit


def main() -> int:
    uiwalk.PREFER_RELEASE = True
    uiwalk.preflight_exe("MagicMenu")
    uiwalk.preflight_display()
    ctypes.windll.user32.SetProcessDPIAware()

    steps = json.loads((HERE / "steps/full_game_v3.json").read_text())
    prologue, cycle = steps[:PROLOGUE], steps[PROLOGUE:PROLOGUE + CYCLE]
    assert cycle[4]["do"] == "hover" and cycle[5]["keys"] == "enter", cycle
    # Same diplomacy sweep probe_long_game.py needs -- a proposal modal froze a
    # run dead at turn 55 and `press` on an absent path is a no-op.
    cycle = [{"do": "press", "path": "DipWizard.ViewButtons.RejectButton"}] + cycle

    run_dir = uiwalk.RUNS / (time.strftime("%Y%m%d-%H%M%S") + "-prep")
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"artifacts -> {run_dir}")
    turnloop._CALIB_DEBUG_DIR = run_dir

    game = uiwalk.Game()
    watcher = turnloop.ErrorWatcher(set())
    watcher.start()
    frames: list[Path] = []
    committed = 0

    def go(seq):
        uiwalk.run_steps(game, inp, seq, run_dir, baseline=False, dry=False)

    def clear(tag: str, limit: int = 4) -> int:
        n = 0
        for i in range(limit):
            if not turnloop.alert_box_open(game.screenshot()):
                break
            if not turnloop.click_alert_arm(game, inp, 0, f"{tag}{i}"):
                break
            n += 1
        return n

    def panel(tag: str):
        """Open MAGIC STATUS and capture it. Returns False if it never opened."""
        clear(f"{tag}_pre")
        go([{"do": "key", "keys": "j"}, {"do": "wait_stable", "ms": 7000}])
        if not turnloop.alert_box_open(game.screenshot()):
            print(f"  [prep] {tag}: panel did not open", flush=True)
            return False
        p = run_dir / f"panel_{tag}.png"
        cv2.imwrite(str(p), game.screenshot())
        frames.append(p)
        print(f"  [prep] {tag}: -> {p.name}", flush=True)
        return True

    try:
        # NEW game, never a save: saves cache compiled SLIC, so a stale one would
        # run the OLD instant-summon code and pass for entirely the wrong reason.
        game.launch(None, [])
        inp = uiwalk.PostInput(game)
        go(prologue)

        for turn in range(2, TURNS + 1):
            go(cycle)
            if watcher.hits:
                print(f"SLIC_ERROR_AT_TURN_{turn}: {watcher.hits[-1]}")
                return 3

            if turn == FIRST_SUMMON:
                if panel(f"t{turn:03d}_precommit") and \
                        turnloop.click_alert_arm(game, inp, 0, f"commit{turn}"):
                    committed += 1
                    print(f"  [prep] t{turn}: committed", flush=True)
                else:
                    clear(f"t{turn:03d}miss")
            elif FIRST_SUMMON < turn <= FIRST_SUMMON + WATCH:
                # EVERY turn, no gaps. The countdown is what is under test.
                panel(f"t{turn:03d}_watch")
                clear(f"t{turn:03d}post")
            elif turn == FIRST_SUMMON + WATCH + 1:
                # Second commit, to exercise the busy path and a fresh countdown.
                if panel(f"t{turn:03d}_second"):
                    turnloop.click_alert_arm(game, inp, 0, f"commit2_{turn}")
                    committed += 1
                # Immediately click again: a second order while preparing must be
                # REFUSED, and the pool must not move.
                if panel(f"t{turn:03d}_busy"):
                    turnloop.click_alert_arm(game, inp, 0, f"busy{turn}")
            elif turn > FIRST_SUMMON + WATCH + 1:
                panel(f"t{turn:03d}_after")
                clear(f"t{turn:03d}post")
    finally:
        watcher.stop()
        game.kill()

    print(f"\ncommits: {committed}   frames: {len(frames)}")
    for f in frames:
        print(f"  {f.name}")
    print(f"\nartifacts in {run_dir}")
    print("NEXT: read the _watch frames in turn order. 'Preparing: N turn(s)' "
          "must fall by exactly 1 per turn and reach 0 on the turn the arrival "
          "popup names a creature. A countdown that never moves, or a creature "
          "that arrives while N is still positive, falsifies the mechanic.")
    return 0 if frames else 1


if __name__ == "__main__":
    raise SystemExit(main())
