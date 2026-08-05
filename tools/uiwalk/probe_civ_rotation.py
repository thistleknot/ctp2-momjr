"""probe_civ_rotation.py -- play EVERY tribe in turn and prove the sphere follows.

WHY. Until 2026-08-04 the mod bound a tribe's sphere to its player SEAT
(`MomPlayerIsLife(p)` was `p == 1`), while the New Game screen lets you pick any
EMPIRE. The default is Tribes of Nature seated at index 1, so the human was
Nature and received LIFE's magic -- visible as Guardian Spirit, Life's rung-1
creature, in a Nature player's Build Manager.

The harness never touched the EMPIRE selector, so every run tested one arbitrary
configuration and the defect survived. This rotates the selector and plays each
tribe, which is the control that was missing.

WHAT IT PROVES, per civ, from the 'j' panel:
  * the sphere reported is the sphere CHOSEN, not the seat occupied;
  * that tribe's own creature is what its summon offers;
  * mana, income and rung behave for a tribe that is not seated at 1.

The EMPIRE control is a cycling button: pressing it advances to the next civ, so
civ N is reached with N presses from the default. `# EMPIRES` is raised to 5 the
same way, so all five tribes are dealt in -- the default of 4 is why one sphere
never took a turn in any earlier run.

Usage:  python tools/uiwalk/probe_civ_rotation.py [--turns 50]
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
STRINGS = SCEN / "english/gamedata/scen_str.txt"
PROBE_SRC = HERE / "probe_slic/mom_probe.slc"

PROLOGUE = 53
CYCLE = 7
EMPIRE = "SPNewGameWindow.TribeButton"

# The EMPIRE list, in the order the dropdown shows it -- ALPHABETICAL, not
# sphere order, and "Tribes of Nature" is preselected. Measured from a capture
# of the open list; guessing this order would have silently played the wrong
# tribe and made every per-sphere reading meaningless.
TRIBES = ["Tribes of Chaos", "Tribes of Death", "Tribes of Life",
          "Tribes of Nature", "Tribes of Sorcery"]
DEFAULT_ROW = 3                      # Tribes of Nature
SPHERE_OF = {0: 5, 1: 4, 2: 1, 3: 2, 4: 3}   # list row -> MoM sphere number

# The panel string is swapped for a debug readout that names the SPHERE the mod
# resolved, beside the tribe's own counters. Five body lines: the alertbox is
# fixed height and silently drops a sixth.
DEBUG_MENU = (
    'MOM_MSG_MAGIC_MENU\t\t"MAGIC STATUS\\n'
    'Mana {MomMagicCurDisp}/{MomMagicMaxDisp}  '
    'inc {MomMagicGenDisp} - up {MomUpkeepDisp} = {MomNetDisp}  '
    'rung {MomRungDisp}\\n'
    'units  {MomDbgU1} {MomDbgU2} {MomDbgU3} {MomDbgU4} {MomDbgU5}\\n'
    'summon {MomDbgC1} {MomDbgC2} {MomDbgC3} {MomDbgC4} {MomDbgC5}\\n'
    'mana   {MomDbgM1} {MomDbgM2} {MomDbgM3} {MomDbgM4} {MomDbgM5}\\n'
    'sphere {MomDbgS1} {MomDbgS2} {MomDbgS3} {MomDbgS4} {MomDbgS5}"\n'
)


def _cleanup_stale() -> None:
    scen_slc = GAMEDATA / "scenario.slc"
    probe = GAMEDATA / "mom_probe.slc"
    if probe.exists():
        probe.unlink()
    text = scen_slc.read_text(encoding="latin-1")
    if "mom_probe.slc" in text:
        scen_slc.write_text(
            "".join(l for l in text.splitlines(keepends=True) if "mom_probe.slc" not in l),
            encoding="latin-1")
    if "MomDbgU1" in STRINGS.read_text(encoding="latin-1"):
        raise SystemExit(
            "REFUSING TO RUN: scen_str.txt still carries a debug MAGIC STATUS "
            "string from a killed run. Restore it:\n"
            "  git checkout -- scen0000/english/gamedata/scen_str.txt")


def _install() -> dict[str, bytes]:
    _cleanup_stale()
    scen_slc = GAMEDATA / "scenario.slc"
    backup = {"scenario.slc": scen_slc.read_bytes(), "scen_str.txt": STRINGS.read_bytes()}
    shutil.copy(PROBE_SRC, GAMEDATA / "mom_probe.slc")
    text = scen_slc.read_text(encoding="latin-1")
    if '#include "mom_probe.slc"' not in text:
        scen_slc.write_text(text.rstrip("\n") + '\n#include "mom_probe.slc"\n',
                            encoding="latin-1")
    STRINGS.write_text("".join(
        DEBUG_MENU if l.startswith("MOM_MSG_MAGIC_MENU") else l
        for l in STRINGS.read_text(encoding="latin-1").splitlines(keepends=True)),
        encoding="latin-1")
    return backup


def _restore(backup: dict[str, bytes]) -> None:
    (GAMEDATA / "scenario.slc").write_bytes(backup["scenario.slc"])
    STRINGS.write_bytes(backup["scen_str.txt"])
    probe = GAMEDATA / "mom_probe.slc"
    if probe.exists():
        probe.unlink()


def run_one(civ_step: int, turns: int, root: Path) -> dict:
    """Play one tribe. civ_step = presses of the EMPIRE button from the default."""
    steps = json.loads((HERE / "steps/full_game_v3.json").read_text())
    row = uiwalk.scenario_pack_index("mom")
    for s in steps[:PROLOGUE]:
        if s.get("path") == "ScenarioWindow.AvailableListBox" and s.get("index"):
            s["index"] = row
            break
    prologue, cycle = steps[:PROLOGUE], steps[PROLOGUE:PROLOGUE + CYCLE]
    cycle = [{"do": "press", "path": "DipWizard.ViewButtons.RejectButton"}] + cycle

    # Insert the setup presses immediately before StartButton (step 23).
    start = next(i for i, s in enumerate(prologue)
                 if s.get("path") == "SPNewGameWindow.StartButton")
    # TribeButton opens SPNewGameTribeScreen, a MODAL with its own listbox
    # (CivBox) and a BackButton that commits and closes. Arrow keys do NOT move
    # that list -- measured, the highlight stayed on the preselected row -- so
    # this selects by index and presses Back, the same shape as the scenario
    # picker. The control names come from spnewgamepopups.ldl rather than a
    # guess; my first two guesses (CivButton, NumPlayersButton) did not exist.
    # 4 EMPIRES -> 5, so every tribe is dealt in. The default of 4 is why one
    # sphere never took a turn in any earlier run: with five tribes and four
    # seats, somebody always sits out, and it was Chaos often enough that its
    # column read 0 units AND 0 mana in every sample I took.
    setup = [
        {"do": "press", "path": "SPNewGameWindow.PlayersButton"},
        {"do": "wait_stable", "ms": 6000},
        {"do": "press", "path": "SPNewGamePlayersScreen.NumPlayerSpinner"},
        {"do": "wait", "ms": 500},
        {"do": "press", "path": "SPNewGamePlayersScreen.BackButton"},
        {"do": "wait", "ms": 500},
        {"do": "key", "keys": "esc"},
        {"do": "wait_stable", "ms": 6000},
        {"do": "press", "path": EMPIRE},
        {"do": "wait_stable", "ms": 8000},
        {"do": "select", "path": "SPNewGameTribeScreen.CivBox", "index": civ_step},
        {"do": "wait", "ms": 700},
        {"do": "shot", "name": f"picked_civ{civ_step}"},
        # CLOSING THE MODAL IS WHAT COMMITS THE CHOICE. `press` alone left it
        # open -- both earlier runs launched with the DEFAULT tribe because
        # StartButton was pressed straight through the still-open modal. Try the
        # button, then trigger (the RunUITriggers path a real click takes), then
        # esc; each is a no-op if the modal has already gone.
        {"do": "press", "path": "SPNewGameTribeScreen.BackButton"},
        {"do": "wait", "ms": 700},
        {"do": "trigger", "path": "SPNewGameTribeScreen.BackButton"},
        {"do": "wait", "ms": 700},
        {"do": "key", "keys": "esc"},
        {"do": "wait_stable", "ms": 8000},
        {"do": "shot", "name": f"setup_civ{civ_step}"},
    ]
    prologue = prologue[:start] + setup + prologue[start:]

    run_dir = root / f"civ{civ_step}"
    run_dir.mkdir(parents=True, exist_ok=True)
    turnloop._CALIB_DEBUG_DIR = run_dir

    game = uiwalk.Game()
    watcher = turnloop.ErrorWatcher(set())
    watcher.start()
    reached, panels = 0, []
    try:
        game.launch(None, [])
        inp = uiwalk.PostInput(game)
        uiwalk.run_steps(game, inp, prologue, run_dir, baseline=False, dry=False)
        for t in range(2, turns + 1):
            uiwalk.run_steps(game, inp, cycle, run_dir, baseline=False, dry=False)
            reached = t
            if watcher.hits:
                return {"civ": civ_step, "turns": reached, "panels": panels,
                        "error": watcher.hits[-1]}
            if t % max(1, turns // 2) == 0 or t == turns:
                uiwalk.run_steps(game, inp, [{"do": "key", "keys": "j"},
                                             {"do": "wait_stable", "ms": 7000}],
                                 run_dir, baseline=False, dry=False)
                if turnloop.alert_box_open(game.screenshot()):
                    q = run_dir / f"panel_t{t:03d}.png"
                    cv2.imwrite(str(q), game.screenshot())
                    panels.append(q.name)
    finally:
        watcher.stop()
        game.kill()
    return {"civ": civ_step, "turns": reached, "panels": panels, "error": None}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--turns", type=int, default=50)
    ap.add_argument("--civs", type=int, default=5)
    args = ap.parse_args()

    uiwalk.PREFER_RELEASE = True
    uiwalk.preflight_exe("MagicMenu")
    uiwalk.preflight_display()
    ctypes.windll.user32.SetProcessDPIAware()

    root = uiwalk.RUNS / (time.strftime("%Y%m%d-%H%M%S") + "-civrotation")
    root.mkdir(parents=True, exist_ok=True)
    print(f"artifacts -> {root}")

    backup = _install()
    results = []
    try:
        for civ in range(args.civs):
            print(f"\n===== CIV {civ} : {args.turns} turns =====", flush=True)
            r = run_one(civ, args.turns, root)
            r["tribe"] = TRIBES[civ]; r["expect_sphere"] = SPHERE_OF[civ]
            results.append(r)
            print(f"  turns={r['turns']} panels={len(r['panels'])} "
                  f"error={'YES' if r['error'] else 'no'}", flush=True)
    finally:
        _restore(backup)
        print("[probe] scenario restored (instrument removed)")

    (root / "summary.json").write_text(json.dumps(results, indent=2))
    total = sum(r["turns"] for r in results)
    print(f"\nTOTAL {total} turns across {len(results)} civs")
    print("READ each civ's panel: the 'sphere' row must show the CHOSEN tribe's "
          "sphere at whatever seat it occupies.")
    return 0 if all(r["error"] is None for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
