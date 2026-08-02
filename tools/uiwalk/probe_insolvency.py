#!/usr/bin/env python
"""probe_insolvency.py -- prove the disband path EXECUTES, on a shrunken rig.

THE PROBLEM THIS SOLVES. Insolvency is unreachable in a short game at shipped
rates, and that is by design rather than by accident: a summon needs 75 banked
mana and each creature permanently lowers net income, so a rung-1 tribe steps net
down 2 at a time against ~20-25 income. Reaching a deficit takes on the order of
a hundred turns of aggressive summoning. Long runs are banned here (operator,
2026-08-01) and they are the wrong tool anyway.

SO SHRINK THE RIG, NOT THE QUESTION. `MomUpkeepRate` is a single seeded global
(mom_magic.slc). This probe patches that ONE line from 2 to a rate high enough
that a single creature outruns income immediately, runs a handful of turns, and
restores it. Everything else -- the ledger, the weighted draw, the KillUnit, the
refund, the floor at zero, the message -- is the SHIPPED code path, unmodified.

WHAT THIS PROVES: the insolvency branch runs, selects a creature, kills it,
refunds its charge and floors the pool, and the player is told.

WHAT IT DOES NOT PROVE, stated plainly: that the SHIPPED rate of 2 ever produces
a disband in real play. It almost certainly does not at rung 1, which is the
intended design -- disband is a backstop for income LOSS (a city or mana node
lost), not a routine tax. The selection maths is covered separately and exactly
by tools/test_disband_weighting.py.

Install is idempotent: it strips any patch left by a killed run before applying
its own, because a `finally` does not survive being killed.
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

MAGIC = HERE.parent.parent / "scen0000/default/gamedata/mom_magic.slc"
SHIPPED = "        MomUpkeepRate = 2;"
# 60 per rung against ~20-25 income: ONE rung-1 creature puts net at roughly -40,
# so the very next tick is insolvent and the disband must fire.
TEST_RATE = int(os.environ.get("PROBE_RATE", "60"))
PATCHED = f"        MomUpkeepRate = {TEST_RATE};"

PROLOGUE = 53
CYCLE = 7
TURNS = int(os.environ.get("PROBE_TURNS", "16"))
SUMMON_AT = 6


def _install() -> bytes:
    original = MAGIC.read_bytes()
    text = MAGIC.read_text(encoding="latin-1")
    if SHIPPED not in text:
        raise SystemExit(
            "REFUSING TO RUN: mom_magic.slc does not contain the shipped rate "
            f"line {SHIPPED!r}. Either a previous run was killed mid-patch, or "
            "the seeding moved. Restore first:\n"
            "  git checkout -- scen0000/default/gamedata/mom_magic.slc")
    MAGIC.write_text(text.replace(SHIPPED, PATCHED, 1), encoding="latin-1")
    print(f"[probe] upkeep rate patched 2 -> {TEST_RATE} (shrunken rig)")
    return original


def _restore(original: bytes) -> None:
    MAGIC.write_bytes(original)
    ok = SHIPPED in MAGIC.read_text(encoding="latin-1")
    print(f"[probe] upkeep rate restored to shipped: {ok}")


def main() -> int:
    uiwalk.PREFER_RELEASE = True
    uiwalk.preflight_exe("MagicMenu")
    uiwalk.preflight_display()
    ctypes.windll.user32.SetProcessDPIAware()

    steps = json.loads((HERE / "steps/full_game_v3.json").read_text())
    prologue, cycle = steps[:PROLOGUE], steps[PROLOGUE:PROLOGUE + CYCLE]
    cycle = [{"do": "press", "path": "DipWizard.ViewButtons.RejectButton"}] + cycle

    run_dir = uiwalk.RUNS / (time.strftime("%Y%m%d-%H%M%S") + "-insolvency")
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"artifacts -> {run_dir}")
    turnloop._CALIB_DEBUG_DIR = run_dir

    original = _install()
    game = uiwalk.Game()
    watcher = turnloop.ErrorWatcher(set())
    watcher.start()
    frames: list[Path] = []

    def go(seq):
        uiwalk.run_steps(game, inp, seq, run_dir, baseline=False, dry=False)

    def snap(tag: str) -> bool:
        frame = game.screenshot()
        if not turnloop.alert_box_open(frame):
            return False
        p = run_dir / f"{tag}.png"
        cv2.imwrite(str(p), frame)
        frames.append(p)
        print(f"  [ins] {tag} -> {p.name}", flush=True)
        return True

    def clear(tag: str, limit: int = 4) -> int:
        n = 0
        for i in range(limit):
            if not turnloop.alert_box_open(game.screenshot()):
                break
            if not turnloop.click_alert_arm(game, inp, 0, f"{tag}{i}"):
                break
            n += 1
        return n

    try:
        # NEW game: saves cache compiled SLIC, so a save would run the old rate.
        game.launch(None, [])
        inp = uiwalk.PostInput(game)
        go(prologue)

        for turn in range(2, TURNS + 1):
            go(cycle)
            if watcher.hits:
                print(f"SLIC_ERROR_AT_TURN_{turn}: {watcher.hits[-1]}")
                return 3

            # Any box standing at the top of a turn is a result -- the disband
            # notice looks like any other from out here, so keep every one and
            # read them afterwards.
            snap(f"msg_t{turn:03d}")
            clear(f"t{turn:03d}m")

            if turn == SUMMON_AT:
                clear(f"t{turn:03d}pre")
                go([{"do": "key", "keys": "j"}, {"do": "wait_stable", "ms": 7000}])
                if snap(f"panel_t{turn:03d}_precommit"):
                    turnloop.click_alert_arm(game, inp, 0, f"commit{turn}")
                    print(f"  [ins] t{turn}: committed", flush=True)
            elif turn > SUMMON_AT:
                # Every turn after the commit: the creature arrives, upkeep
                # explodes past income, and the disband must follow.
                clear(f"t{turn:03d}pre")
                go([{"do": "key", "keys": "j"}, {"do": "wait_stable", "ms": 7000}])
                snap(f"panel_t{turn:03d}")
                clear(f"t{turn:03d}post")
    finally:
        watcher.stop()
        game.kill()
        _restore(original)

    print(f"\nframes: {len(frames)}")
    for f in frames:
        print(f"  {f.name}")
    print(f"\nartifacts in {run_dir}")
    print("NEXT: look for the disband message ('fades back into the aether') and "
          "a panel where upkeep DROPS back to 0 after having been high -- that "
          "pair is the creature being released. A pool stuck negative, or an "
          "upkeep that never falls, falsifies the insolvency path.")
    return 0 if frames else 1


if __name__ == "__main__":
    raise SystemExit(main())
