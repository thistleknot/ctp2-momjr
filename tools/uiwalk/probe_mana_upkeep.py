#!/usr/bin/env python
"""probe_mana_upkeep.py -- prove in a RUNNING GAME that mana upkeep is charged.

WHAT THIS PROVES, and what it cannot.

Static gates prove the ledger EXISTS, the arities match and the scan clears dead
slots. None of that proves the engine agrees: `unit_t Arr[N]`, `Arr[i].valid` and
the 5-argument `CreateUnit` out-arg are all read off other mods' usage, not off
this scenario's own history. If any of those three is wrong, SLIC compiles and
the feature silently does nothing -- the engine AUTO-CREATES unknown symbols
rather than erroring. So the only honest test is a running game.

The assertion is arithmetic and visible on ONE surface: the 'j' MAGIC STATUS
panel now prints `Net income:` and `Upkeep:` alongside the pool. Summon a
creature, reopen the panel, and upkeep must rise by that creature's rung rate
(rung * 2). It is captured as pixels and read by a human/model looking at the
frame -- there is no OCR here and none is claimed.

WHAT THIS INSTRUMENT MISSES, stated up front:
  * It reads PIXELS. It cannot see console output, and it cannot read an AI
    player's mana -- that renders for the human alone. Nothing here speaks to
    whether the AI respects its sustainability check.
  * A panel that fails to open looks identical to a panel that opened with no
    upkeep line. `alert_box_open` is checked before any frame is trusted.
  * It cannot prove the DISBAND path; reaching insolvency needs more creatures
    than 20 turns of income can buy. That remains unproven by this probe.

Shape is inherited verbatim from probe_summon_variety.py, whose three failed
predecessors established the rule: every step with a proven steps-JSON form comes
from the steps JSON, and only the alertbox arm click drops into Python, because
alertbox arms are NOT LDL-addressable and must be measured from the live frame.
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
TURNS = 20             # bounded: this must disposition in minutes, not hours
SUMMON_EVERY = 6       # ~+16-19 mana/turn against a 75 cost


def _panel(game, run_dir: Path, tag: str):
    """Capture whatever box is up and report whether one actually opened."""
    frame = game.screenshot()
    ok = turnloop.alert_box_open(frame)
    path = run_dir / f"panel_{tag}.png"
    cv2.imwrite(str(path), frame)
    return ok, path


def _clear_boxes(game, inp, run_dir: Path, tag: str, limit: int = 4) -> int:
    """Dismiss any stacked Message windows by clicking their own arm.

    WHY THIS EXISTS. Run 1 captured the pre-summon panel, clicked the arm, and
    then never saw MAGIC STATUS again -- 'j' silently did nothing at turns 12 and
    18. The cause is the summon RESULT message: it stacks above the alertbox and
    swallows input, which is exactly the v1 failure probe_summon_variety.py
    documents. A summon therefore BLOCKS the very panel that would show its cost.

    Dismissal is a measured arm click, never a speculative one:
    dismiss_message's misses land on the map and pan it (the operator watched
    that happen), so nothing is clicked unless alert_box_open says a box is
    really there.
    """
    cleared = 0
    for i in range(limit):
        if not turnloop.alert_box_open(game.screenshot()):
            break
        if not turnloop.click_alert_arm(game, inp, 0, f"{tag}_clear{i}"):
            break
        cleared += 1
    return cleared


def main() -> int:
    uiwalk.PREFER_RELEASE = True
    uiwalk.preflight_exe("MagicMenu")
    uiwalk.preflight_display()
    ctypes.windll.user32.SetProcessDPIAware()

    steps = json.loads((HERE / "steps/full_game_v3.json").read_text())
    prologue, cycle = steps[:PROLOGUE], steps[PROLOGUE:PROLOGUE + CYCLE]
    assert cycle[4]["do"] == "hover" and cycle[5]["keys"] == "enter", cycle

    run_dir = uiwalk.RUNS / (time.strftime("%Y%m%d-%H%M%S") + "-upkeep")
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"artifacts -> {run_dir}")
    turnloop._CALIB_DEBUG_DIR = run_dir

    game = uiwalk.Game()
    watcher = turnloop.ErrorWatcher(set())
    watcher.start()
    panels: list[Path] = []
    clicked = 0

    def go(seq):
        uiwalk.run_steps(game, inp, seq, run_dir, baseline=False, dry=False)

    try:
        # A NEW game, never a save -- saves cache compiled SLIC, so a stale save
        # would run the OLD no-upkeep code and pass for the wrong reason.
        game.launch(None, [])
        inp = uiwalk.PostInput(game)
        go(prologue)

        for turn in range(2, TURNS + 1):
            go(cycle)
            if watcher.hits:
                # A SLIC compile/runtime error is the single most likely failure
                # here, and it is fatal to the whole claim -- report and stop
                # rather than collecting frames that mean nothing.
                print(f"SLIC_ERROR_AT_TURN_{turn}: {watcher.hits[-1]}")
                return 3
            if turn % SUMMON_EVERY:
                continue

            # Clear any pending result message FIRST -- see _clear_boxes.
            n = _clear_boxes(game, inp, run_dir, f"t{turn:03d}pre")
            if n:
                print(f"  [probe] turn {turn}: cleared {n} stacked message(s)",
                      flush=True)
            go([{"do": "key", "keys": "j"}, {"do": "wait_stable", "ms": 8000}])
            ok, path = _panel(game, run_dir, f"t{turn:03d}_before")
            if not ok:
                print(f"  [probe] turn {turn}: MAGIC STATUS did not open", flush=True)
                continue
            panels.append(path)
            print(f"  [probe] turn {turn}: panel -> {path.name}", flush=True)

            # Arm 0 = Summon Creature (75). Measured from the live frame, never
            # pinned: arms render in REVERSE declaration order and are not
            # LDL-addressable. Its success test is "did the box close".
            if not turnloop.click_alert_arm(game, inp, 0, f"summon@{turn}"):
                print(f"  [probe] turn {turn}: arm click missed", flush=True)
                continue
            clicked += 1

            # The order is PLACED now and RESOLVES next BeginTurn, so the
            # creature -- and therefore its upkeep -- appears one turn later.
            go(cycle)
            # The result message is up NOW -- capture it (it names the creature,
            # which tells us which rung was rolled and therefore what upkeep to
            # expect), then clear it so 'j' can reach the panel underneath.
            ok, rpath = _panel(game, run_dir, f"t{turn:03d}_result")
            if ok:
                panels.append(rpath)
                print(f"  [probe] turn {turn}: result -> {rpath.name}", flush=True)
            _clear_boxes(game, inp, run_dir, f"t{turn:03d}post")

            go([{"do": "key", "keys": "j"}, {"do": "wait_stable", "ms": 8000}])
            ok, path = _panel(game, run_dir, f"t{turn:03d}_after")
            if ok:
                panels.append(path)
                print(f"  [probe] turn {turn}: post-summon panel -> {path.name}",
                      flush=True)
            else:
                print(f"  [probe] turn {turn}: post-summon panel did not open",
                      flush=True)
            _clear_boxes(game, inp, run_dir, f"t{turn:03d}close")
    finally:
        watcher.stop()
        game.kill()

    print(f"\narms clicked: {clicked}   panel frames: {len(panels)}")
    for p in panels:
        print(f"  {p.name}")
    print(f"\nartifacts in {run_dir}")
    print("NEXT: read the before/after panel pairs. Upkeep is charged iff the "
          "'Upkeep:' line is NONZERO after a summon and 'Net income:' has "
          "fallen by the same amount. An upkeep that stays 0 across a "
          "successful summon falsifies the ledger.")
    return 0 if panels else 1


if __name__ == "__main__":
    raise SystemExit(main())
