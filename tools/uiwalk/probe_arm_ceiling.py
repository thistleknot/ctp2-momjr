"""probe_arm_ceiling.py -- how many arms does an alertbox actually render?

The v4 magic tree (specs/magic-ui-architecture.md) wants spokes of 3 actions +
Back + Close = 5 arms. Shipped segments carry two or three, and the box is FIXED
HEIGHT and drops overflow in SILENCE (ctp2-alertbox-does-not-grow-to-fit), so the
ceiling is a fact the whole design rests on and nobody has measured it.

Injects a six-arm MagicMenu, opens it with `j`, photographs it, restores. Count
the arms that rendered: that is the answer.

INSTALL IS IDEMPOTENT and the restore sits in a finally -- but a killed probe
skips finally, so install REFUSES outright when a prior instrument is still
present rather than measuring an already-instrumented scenario
(harness-finally-is-not-cleanup-make-install-idempotent).
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
import uiwalk  # noqa: E402

SCEN = HERE.parent.parent / "scen0000"
MSG = SCEN / "default/gamedata/mom_msg.slc"
STR = SCEN / "english/gamedata/scen_str.txt"
MARK = "MOM_PROBE_ARM"
PROLOGUE = 53
N_ARMS = 6


def install() -> dict[str, bytes]:
    msg = MSG.read_text(encoding="latin-1")
    st = STR.read_text(encoding="latin-1")
    if MARK in msg or MARK in st:
        raise SystemExit(
            "REFUSING TO RUN: a prior arm-ceiling probe left its instrument in "
            "the scenario. Restore it first:\n"
            "  git checkout -- scen0000/default/gamedata/mom_msg.slc "
            "scen0000/english/gamedata/scen_str.txt")
    backup = {"msg": MSG.read_bytes(), "str": STR.read_bytes()}

    arms = "".join(
        "\tButton(ID_%s%d) { Kill(); }\n" % (MARK, i) for i in range(1, N_ARMS + 1))
    i = msg.index("alertbox 'MagicMenu' {")
    j = msg.index("Button(ID_BUTTON_CLOSE)", i)
    MSG.write_text(msg[:j] + arms + "\t" + msg[j:], encoding="latin-1")

    keys = "".join('%s%d\t\t"ARM %d"\n' % (MARK, i, i) for i in range(1, N_ARMS + 1))
    STR.write_text(st.rstrip("\r\n") + "\n" + keys, encoding="latin-1")
    return backup


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

    run_dir = uiwalk.RUNS / (time.strftime("%Y%m%d-%H%M%S") + "-armceiling")
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"artifacts -> {run_dir}")

    backup = install()
    game = uiwalk.Game()
    try:
        game.launch(None, [])
        inp = uiwalk.PostInput(game)
        uiwalk.run_steps(game, inp, steps[:PROLOGUE], run_dir, baseline=False, dry=False)
        uiwalk.run_steps(game, inp, [
            {"do": "key", "keys": "j"},
            {"do": "wait_stable", "ms": 7000},
            {"do": "shot", "name": "sixarms"},
        ], run_dir, baseline=False, dry=False)
        cv2.imwrite(str(run_dir / "final.png"), game.screenshot())
    finally:
        game.kill()
        MSG.write_bytes(backup["msg"])
        STR.write_bytes(backup["str"])
        print("[probe] scenario restored (instrument removed)")

    print(f"READ 01_sixarms.png -- {N_ARMS} arms declared; count how many rendered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
