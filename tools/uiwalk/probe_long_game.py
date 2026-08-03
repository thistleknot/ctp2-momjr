#!/usr/bin/env python
"""probe_long_game.py -- close the three claims a short run cannot reach.

THE THREE OPEN CLAIMS (v3.5.0):

  1. INSOLVENCY DISBANDS. Unreachable at rung 1 by construction: a summon needs
     75 banked and each creature permanently lowers net income, so a rung-1 tribe
     steps net down 2 at a time and lands exactly ON zero, after which it can
     never bank 75 again. Net only goes negative once a single creature's keep
     exceeds the remaining headroom -- i.e. at rung 2+, where keep is 4..10. Only
     a long game researches that far, which is why this run is long.
  2. THE AI RESPECTS SUSTAINABILITY, not bare affordability. Observable as its
     summoned-creature count PLATEAUING instead of growing without bound.
  3. AN AI ARMY IS MOSTLY BUILT UNITS. This is the original "tribes of nature
     only ever spawn one unit" report, and the discriminator is the ratio of
     summoned creatures to total units per tribe.

INSTRUMENT. The harness reads pixels and no AI's mana is ever rendered, so this
injects probe_slic/mom_probe.slc -- a READ-ONLY sampler that writes display
scalars only -- plus a debug MAGIC STATUS string, runs, and RESTORES both in a
finally block. The scenario is never left instrumented, and because the sampler
takes no branch that game logic observes, the economy measured is the shipped
economy.

WHAT IT STILL MISSES, stated up front: it reports per-tribe COUNTS, not unit
TYPES. It can prove an AI army is mostly built rather than summoned; it cannot
name which units those are. Distinguishing thirteen Nature unit types would need
sprite template matching, which is a separate instrument.

Bounded: TURNS is a single confirmatory run, not a debugging loop. Everything it
asserts is read off captured frames afterwards, not inferred from exit code.
"""
from __future__ import annotations

import ctypes
import json
import os
import shutil
import sys
import time
from pathlib import Path

import cv2

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import uiwalk                      # noqa: E402
import turnloop                    # noqa: E402

SCEN = HERE.parent.parent / "scen0000"
GAMEDATA = SCEN / "default/gamedata"
STRINGS = SCEN / "english/gamedata/scen_str.txt"
PROBE_SRC = HERE / "probe_slic/mom_probe.slc"

PROLOGUE = 53
CYCLE = 7
# 700, because turn 220 is still EARLY GAME (operator, 2026-08-01). The sphere
# ladder is thousands of science deep -- LIFE_ADEPT alone is 2765 behind
# LIFE_LORE 1970 behind LIFE_MAGIC 1035 -- and an AI army needs time to mature
# into a mix. Prior runs put DEFEAT around turn 390 and END_OF_GAME_YEAR at 1000,
# so 700 sits past the first real outcomes without banking on the endgame.
#
# PROBE_TURNS exists so the INSTRUMENT can be smoke-tested in a couple of minutes
# -- validating a two-hour run's plumbing with a two-hour run is how an afternoon
# disappears.
# OBSERVE-ONLY MODE. Every posted click is an access-violation risk on this
# display: the engine renders its 800x600 UI letterboxed inside a 1024x1280
# client, and a posted WM_LBUTTONDOWN faults where injection and keys do not.
# That is what killed the prologue ping (steps 27) and then the alertbox arm
# click at turn 5. Injection (`press`), keys and `hover` are all unaffected, so a
# run that never clicks can still drive the turn loop and read the 'j' panel --
# it simply cannot press a summon arm. Set PROBE_OBSERVE=1 to get the long-run
# telemetry without the click that ends the run.
OBSERVE_ONLY = os.environ.get("PROBE_OBSERVE") == "1"

TURNS = int(os.environ.get("PROBE_TURNS", "20"))
SAMPLE_EVERY = int(os.environ.get("PROBE_SAMPLE", "20"))
SUMMON_EVERY = 5        # push the human toward its own upkeep ceiling

# The alertbox is FIXED HEIGHT and silently drops overflow, so this is right at
# the limit: one header plus four data rows. Adding a sixth line pushes `prep`
# off the bottom with no error and the frame still looks correct -- verify
# against a captured frame before extending it.
DEBUG_MENU = (
    'MOM_MSG_MAGIC_MENU\t\t"MAGIC STATUS\\n'
    'Mana {MomMagicCurDisp}/{MomMagicMaxDisp}  '
    'inc {MomMagicGenDisp} - up {MomUpkeepDisp} = {MomNetDisp}  '
    'rung {MomRungDisp}\\n'
    'units  {MomDbgU1} {MomDbgU2} {MomDbgU3} {MomDbgU4} {MomDbgU5}\\n'
    'summon {MomDbgC1} {MomDbgC2} {MomDbgC3} {MomDbgC4} {MomDbgC5}\\n'
    'mana   {MomDbgM1} {MomDbgM2} {MomDbgM3} {MomDbgM4} {MomDbgM5}\\n'
    'pend   {MomDbgP1} {MomDbgP2} {MomDbgP3} {MomDbgP4} {MomDbgP5}"\n'
)


def _cleanup_stale() -> None:
    """Remove any instrument left behind by a PREVIOUS run before installing.

    MEASURED 2026-08-01: a finally block is NOT sufficient. Killing this probe
    mid-run (task cancelled, operator interrupt, watchdog) skips finally
    entirely, and the run left mom_probe.slc in place, an #include appended to
    scenario.slc, and the debug string swapped into scen_str.txt. That is worse
    than an ordinary leak -- the next run would silently measure an instrumented
    scenario, and the leak was one `git add -A` away from being committed into
    the mod.

    So installation is IDEMPOTENT: it strips any prior instrument first, and the
    strip is exact (a line-level match on the include, a key match on the string)
    rather than a git checkout, so it cannot discard unrelated edits the operator
    happens to have in the tree.
    """
    scen_slc = GAMEDATA / "scenario.slc"
    probe = GAMEDATA / "mom_probe.slc"
    if probe.exists():
        probe.unlink()
        print("[probe] removed stale mom_probe.slc from a prior run")
    text = scen_slc.read_text(encoding="latin-1")
    if "mom_probe.slc" in text:
        kept = [ln for ln in text.splitlines(keepends=True)
                if "mom_probe.slc" not in ln]
        scen_slc.write_text("".join(kept), encoding="latin-1")
        print("[probe] stripped stale #include from scenario.slc")
    stext = STRINGS.read_text(encoding="latin-1")
    if "MomDbgU1" in stext:
        raise SystemExit(
            "REFUSING TO RUN: scen_str.txt still carries the debug MAGIC STATUS "
            "string from a killed run, and this probe cannot know what the real "
            "one said. Restore it first:\n"
            "  git checkout -- scen0000/english/gamedata/scen_str.txt")


def _install() -> dict[str, bytes]:
    """Inject the sampler. Returns originals for the finally-block restore."""
    _cleanup_stale()
    scen_slc = GAMEDATA / "scenario.slc"
    backup = {
        "scenario.slc": scen_slc.read_bytes(),
        "scen_str.txt": STRINGS.read_bytes(),
    }
    shutil.copy(PROBE_SRC, GAMEDATA / "mom_probe.slc")

    text = scen_slc.read_text(encoding="latin-1")
    if '#include "mom_probe.slc"' not in text:
        scen_slc.write_text(text.rstrip("\n") + '\n#include "mom_probe.slc"\n',
                            encoding="latin-1")

    # Swap the panel string for the debug readout. Same key, so the proven 'j'
    # path is unchanged -- only what it prints differs.
    out = []
    for line in STRINGS.read_text(encoding="latin-1").splitlines(keepends=True):
        out.append(DEBUG_MENU if line.startswith("MOM_MSG_MAGIC_MENU") else line)
    STRINGS.write_text("".join(out), encoding="latin-1")
    return backup


def _restore(backup: dict[str, bytes]) -> None:
    (GAMEDATA / "scenario.slc").write_bytes(backup["scenario.slc"])
    STRINGS.write_bytes(backup["scen_str.txt"])
    probe = GAMEDATA / "mom_probe.slc"
    if probe.exists():
        probe.unlink()
    print("[probe] scenario restored (instrument removed)")


def main() -> int:
    uiwalk.PREFER_RELEASE = True
    uiwalk.preflight_exe("MagicMenu")
    uiwalk.preflight_display()
    ctypes.windll.user32.SetProcessDPIAware()

    steps = json.loads((HERE / "steps/full_game_v3.json").read_text())

    # RE-DERIVE THE SCENARIO ROW. The steps file pins one, and that number goes
    # stale whenever a pack is added to Scenarios/ -- creating Scenarios/smm
    # moved mom from row 3 to row 5, after which every run loaded NuclearDetente
    # and died with 0xC0000005 a few steps later. Patch it here rather than
    # editing the file so the 200-turn-validated steps stay byte-identical and
    # the correction is visibly derived from the filesystem.
    _row = uiwalk.scenario_pack_index("mom")
    for _s in steps[:PROLOGUE]:
        if _s.get("path") == "ScenarioWindow.AvailableListBox" and _s.get("index"):
            if _s["index"] != _row:
                print(f"[probe] scenario row {_s['index']} -> {_row} (derived)")
            _s["index"] = _row
            break

    prologue, cycle = steps[:PROLOGUE], steps[PROLOGUE:PROLOGUE + CYCLE]
    assert cycle[4]["do"] == "hover" and cycle[5]["keys"] == "enter", cycle

    # EXTRA MODAL SWEEP, prepended to the proven cycle rather than edited into
    # it, so full_game_v3.json's 200-turn-validated steps stay byte-identical and
    # the addition is visibly additive.
    #
    # WHY: a 700-turn run STALLED DEAD at turn 55 (measured 2026-08-01, watchdog
    # tripped after 900s). The sliced cycle sweeps SciAdvanceScreen,
    # BattleViewWindow and ModalWindow -- and nothing else; full_game_v3.json
    # contains ZERO references to DipWizard. A diplomatic proposal modal is a
    # documented turn-loop freezer here, and earlier 200-turn runs simply never
    # reached AI contact, so the gap never showed.
    #
    # `press` on a path that is not currently realised is a no-op, which is
    # exactly why the other three can sit unconditionally in every single turn.
    cycle = [{"do": "press", "path": "DipWizard.ViewButtons.RejectButton"}] + cycle

    run_dir = uiwalk.RUNS / (time.strftime("%Y%m%d-%H%M%S") + "-longgame")
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"artifacts -> {run_dir}")
    turnloop._CALIB_DEBUG_DIR = run_dir

    backup = _install()
    game = uiwalk.Game()
    watcher = turnloop.ErrorWatcher(set())
    watcher.start()
    panels: list[Path] = []
    disbands: list[Path] = []
    clicked = 0
    reached = 0

    def go(seq):
        uiwalk.run_steps(game, inp, seq, run_dir, baseline=False, dry=False)

    def clear(tag: str, limit: int = 4) -> int:
        n = 0
        if OBSERVE_ONLY:
            # An alertbox left standing does NOT block the turn loop -- the
            # cycle's ModalWindow.ModalResponseButton press (injection, not a
            # click) dismisses what would otherwise stack. Skipping the click
            # trades the ability to answer a summon prompt for the ability to
            # finish the run at all.
            return 0
        for i in range(limit):
            if not turnloop.alert_box_open(game.screenshot()):
                break
            if not turnloop.click_alert_arm(game, inp, 0, f"{tag}{i}"):
                break
            n += 1
        return n

    try:
        game.launch(None, [])
        inp = uiwalk.PostInput(game)
        go(prologue)

        for turn in range(2, TURNS + 1):
            go(cycle)
            reached = turn
            if watcher.hits:
                print(f"SLIC_ERROR_AT_TURN_{turn}: {watcher.hits[-1]}")
                return 3

            # A box standing at the top of a turn is a RESULT -- most often a
            # summon, but the disband notice looks the same from out here. Keep
            # every one: reading them afterwards is how the disband is caught.
            if turnloop.alert_box_open(game.screenshot()):
                p = run_dir / f"msg_t{turn:03d}.png"
                cv2.imwrite(str(p), game.screenshot())
                disbands.append(p)
                clear(f"t{turn:03d}msg")

            # HEARTBEAT. A long detached run needs liveness that is distinct from
            # outcome: a hung turn loop emits nothing, so silence and progress
            # look identical from outside. This line advances the log's mtime
            # every 10 turns whether or not anything interesting happened, which
            # is what makes a staleness watchdog possible at all.
            if turn % 10 == 0:
                print(f"  [hb] t{turn}/{TURNS} {time.strftime('%H:%M:%S')}",
                      flush=True)

            if turn % SAMPLE_EVERY == 0:
                go([{"do": "key", "keys": "j"}, {"do": "wait_stable", "ms": 7000}])
                if turnloop.alert_box_open(game.screenshot()):
                    p = run_dir / f"panel_t{turn:03d}.png"
                    cv2.imwrite(str(p), game.screenshot())
                    panels.append(p)
                    print(f"  [probe] t{turn}: panel -> {p.name}", flush=True)
                    # CHECKPOINT as we go. Killing a two-hour run must cost only
                    # the turns since the last sample, not the whole run -- and
                    # the frames are the actual result, so an index of them is
                    # what makes a partial run still readable.
                    (run_dir / "samples.json").write_text(json.dumps({
                        "turns_reached": turn,
                        "panels": [q.name for q in panels],
                        "result_frames": [q.name for q in disbands],
                        "arms_clicked": clicked,
                    }, indent=2))
                clear(f"t{turn:03d}pan")

            if turn % SUMMON_EVERY == 0 and not OBSERVE_ONLY:
                go([{"do": "key", "keys": "j"}, {"do": "wait_stable", "ms": 7000}])
                if turnloop.alert_box_open(game.screenshot()):
                    if turnloop.click_alert_arm(game, inp, 0, f"sum{turn}"):
                        clicked += 1
                    else:
                        clear(f"t{turn:03d}sum")
    finally:
        watcher.stop()
        game.kill()
        _restore(backup)

    print(f"\nturns reached: {reached}   arms clicked: {clicked}")
    print(f"panels: {len(panels)}   result frames: {len(disbands)}")
    print(f"\nartifacts in {run_dir}")
    print("NEXT: read the panels in order. Rows are Life Nature Sorcery Death "
          "Chaos.\n"
          "  * AI SUSTAINABILITY: the 'summon' row must PLATEAU, not climb.\n"
          "  * MIXED ARMY: 'summon' must stay a small fraction of 'units'.\n"
          "  * DISBAND: a 'summon' count that DROPS while that tribe is alive, "
          "or a result frame naming a creature fading back into the aether.")
    return 0 if panels else 1


if __name__ == "__main__":
    raise SystemExit(main())
