#!/usr/bin/env python
"""probe_summon_variety.py -- prove in a RUNNING GAME that the summon varies.

WHAT THIS PROVES. The 75-mana summon used to resolve through five per-sphere
CONSTANTS; it now rolls, weighted, over every ladder rung the caster has unlocked
(mom_summon.slc, generated). A static gate proves the POOLS are populated. Only a
running game proves the ROLL varies. This summons repeatedly as one tribe and
counts DISTINCT creatures that appear.

THE DESIGN, and why it is this shape (three earlier attempts failed):

  v1  hardcoded click (290,385) on the arm.
      OBSERVED: mana pinned 100/100 for 60 turns -- a Message() window stacks
      ABOVE the alertbox and swallowed every click.
  v2  dismiss that Message at MSG_CLOSE_CAPTURE (497,61) first.
      OBSERVED: the OPTIONS menu opened. That constant is valid only WHILE a box
      is up; with none there it is live top-bar chrome.
  v3  a hand-written driver using turnloop.end_turn + inp.hotkey.
      OBSERVED: `only 0 buttons found` every time -- MAGIC STATUS never opened,
      and dismiss_message's fall-through clicks PANNED THE MAP once per attempt,
      visible to the operator as the view scrolling in a loop.

The lesson from v3 is the whole design of v4: **every step that has a proven
steps-JSON form must come from the steps JSON.** Boot, found-city, end-turn and
the `j` keypress are all replayed verbatim out of full_game_v3.json, which has
driven 200 turns and whose `j` demonstrably raises MAGIC STATUS (captured frames
prove it). ONLY the arm click drops into Python, because it genuinely cannot be
done any other way: injection is dead for alertbox arms -- all four
ALERT_ARM_LDL_CANDIDATES return obj=00000000 while the box is visibly open -- so
the arm must be measured out of the live frame.

dismiss_message is NEVER called speculatively here. Its misses are map input.

Reads pixels only. It CANNOT see an AI player's mana -- that renders for the
human alone -- so this speaks to the summon roll, never to AI spending.
"""
from __future__ import annotations

import ctypes
import json
import sys
import time
from pathlib import Path

import cv2

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import uiwalk                      # noqa: E402
import turnloop                    # noqa: E402

PROLOGUE = 53          # full_game_v3.json 0..52: boot -> found city -> queue
CYCLE = 7              # one turn: 3 modal presses, wait, hover, enter, settle
TURNS = 300
SUMMON_EVERY = 6       # ~+16-19 mana/turn against a 75 cost


def main() -> int:
    uiwalk.PREFER_RELEASE = True
    uiwalk.preflight_exe("MagicMenu")
    uiwalk.preflight_display()
    ctypes.windll.user32.SetProcessDPIAware()

    steps = json.loads((HERE / "steps/full_game_v3.json").read_text())
    prologue, cycle = steps[:PROLOGUE], steps[PROLOGUE:PROLOGUE + CYCLE]
    assert cycle[4]["do"] == "hover" and cycle[5]["keys"] == "enter", cycle

    run_dir = uiwalk.RUNS / (time.strftime("%Y%m%d-%H%M%S") + "-summonvar")
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"artifacts -> {run_dir}")
    turnloop._CALIB_DEBUG_DIR = run_dir

    game = uiwalk.Game()
    watcher = turnloop.ErrorWatcher(set())
    watcher.start()
    shots: list[Path] = []
    clicked = 0

    def go(seq):
        uiwalk.run_steps(game, inp, seq, run_dir, baseline=False, dry=False)

    try:
        # A NEW game, never a save -- saves cache compiled SLIC, so a stale one
        # would exercise the OLD constant summon and pass for the wrong reason.
        game.launch(None, [])
        inp = uiwalk.PostInput(game)
        go(prologue)

        for turn in range(2, TURNS + 1):
            go(cycle)
            if watcher.hits:
                print(f"SLIC_ERROR_AT_TURN_{turn}: {watcher.hits[-1]}")
                return 3
            if turn % SUMMON_EVERY:
                continue

            # 'j' via the steps executor -- the form that is PROVEN to raise the
            # menu. Do not substitute inp.hotkey here; that is what v3 did.
            go([{"do": "key", "keys": "j"}, {"do": "wait_stable", "ms": 8000}])

            frame = game.screenshot()
            if not turnloop.alert_box_open(frame):
                print(f"  [probe] turn {turn}: MAGIC STATUS did not open", flush=True)
                continue
            cv2.imwrite(str(run_dir / f"menu_t{turn:03d}.png"), frame)

            # Arm 0 = Summon Creature (75). Measured, not pinned; arms render in
            # REVERSE declaration order and click_alert_arm handles that. Its
            # success test is "did the box close", the only honest one -- a miss
            # lands on the map and repaints, which looks identical to a hit.
            if not turnloop.click_alert_arm(game, inp, 0, f"summon@{turn}"):
                print(f"  [probe] turn {turn}: arm click missed", flush=True)
                continue
            clicked += 1

            # The order is PLACED now and RESOLVES next BeginTurn, so the result
            # popup naming the creature is one turn away.
            go(cycle)
            path = run_dir / f"summon_result_t{turn:03d}.png"
            cv2.imwrite(str(path), game.screenshot())
            shots.append(path)
            print(f"  [probe] turn {turn}: result -> {path.name}", flush=True)
    finally:
        watcher.stop()
        game.kill()

    print(f"\narms clicked: {clicked}   result frames: {len(shots)}")
    for s in shots:
        print(f"  {s.name}")
    print(f"\nartifacts in {run_dir}")
    print("NEXT: compare the result frames. The roll VARIES iff more than one "
          "distinct creature appears across them; identical creatures in every "
          "frame falsifies it.")
    return 0 if shots else 1


if __name__ == "__main__":
    raise SystemExit(main())
