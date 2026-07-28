"""Emit a full-game uiwalk steps file for an arbitrary turn count.

WHY THIS EXISTS: `steps/full_game_v3.json` was a 1553-element hand-built list
pinned at 200 turns. Asking "what happens at turn 600" meant hand-editing 2800
more elements, and any drift between the prologue and the turn cycle would be
invisible in the diff. The turn cycle is a template, so it belongs in code.

THE PROLOGUE is verbatim from full_game_v3.json, which is the version VERIFIED
on 2026-07-27 (run 20260727-181432: 200/200 turns, exit 0, zero stalls). Do not
"tidy" it -- every wait is a measured settle, and the two-level scenario dialog
(index 3 then index 0) is the law recorded in `uiwalk-stale-scenario-index`.

THE TURN CYCLE is three injection-only modal presses (idempotent by absence --
a `press` on a path that is not realised is a no-op, so the sweep costs nothing
on a clean turn), a BUTTON-FREE mouse move, then enter. The move is `hover` with
`fx` (fraction of live client width), never a pinned pixel: a posted CLICK at a
fixed (600,6) access-violates when the client width changes, and a bare `key`
without any mouse input does not satisfy the engine's end-turn gate
([[ctp2-endturn-needs-mouse-input]], [[ctp2-turn-ping-hover-not-click]]).

Shot cadence is every `--shot-every` turns so a 600-turn run does not write
1200 PNGs. decode_run.py sorts shots NUMERICALLY, so a run past 99 shots is
ordered correctly.

Usage:
    python make_full_game.py --turns 600 --out steps/full_game_600.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Verbatim prologue: cold boot -> main menu -> scenario dialog (two levels) ->
# start -> paint the map -> found the city -> queue Spearmen. Ends immediately
# before the first turn cycle.
PROLOGUE_SOURCE = HERE / "steps" / "full_game_v3.json"
PROLOGUE_LEN = 53


def turn_cycle() -> list[dict]:
    """One end-turn: sweep whatever modal is up, ping the mouse, press enter.

    Guarantee: contains no coordinate that is not derived from the live frame.
    """
    return [
        # The research modal blocks the turn loop and renders as zero-delta
        # frames that look exactly like an AI stall
        # ([[ctp2-research-modal-blocks-turn-loop]]).
        {"do": "press", "path": "SciAdvanceScreen.Background.BackButton"},
        {"do": "press", "path": "BattleViewWindow.ExitButton"},
        # THE 600-TURN FREEZE. A rival tribe opens a DIPLOMATIC PROPOSAL
        # ("give us 100 gold or suffer our wrath") and the window is modal --
        # END TURN never fires again. Run 20260727-201217 sat on one from turn
        # ~20 and produced 117 consecutive BYTE-IDENTICAL checkpoints while the
        # script happily pressed enter into a dead window for another 580 turns.
        # Reject rather than accept: an unattended walk must not hand away gold
        # or sign anything, and rejecting always terminates the exchange.
        {"do": "press", "path": "DipWizard.ViewButtons.RejectButton"},
        {"do": "press", "path": "ModalWindow.ModalResponseButton"},
        {"do": "wait", "ms": 400},
        {"do": "hover", "fx": 0.586, "y": 6},
        {"do": "key", "keys": "enter"},
        {"do": "wait_stable", "ms": 25000},
    ]


def depin(steps: list[dict]) -> tuple[list[dict], int]:
    """Rewrite pinned coordinate CLICKS into the derived button-free hover ping.

    Require: steps from the verified prologue.
    Guarantee: no returned step carries a literal `x` pixel on a mouse BUTTON.

    The prologue still carried `{"do":"click","x":600,"y":6}` -- the ORIGINAL
    inert-chrome ping, from before the law that superseded it. The turn cycle was
    fixed on 2026-07-27 ([[ctp2-turn-ping-hover-not-click]]) and the prologue was
    not, so one pinned button-press survived at index 27.

    That single step is what makes the whole script illegal on a reflowed client:
    uiwalk's own preflight aborts because "every PINNED aim point is off, and a
    miss AVs here" -- and its comment states the discriminating rule, that aim
    DERIVED from the live frame is safe. A `hover` at `fx` is derived and carries
    no button, so it satisfies the end-turn mouse-input gate without hit-testing
    into a control that may have moved.
    """
    out, n = [], 0
    for s in steps:
        if s.get("do") == "click" and "x" in s:
            out.append({"do": "hover", "fx": 0.586, "y": s.get("y", 6)})
            n += 1
        else:
            out.append(s)
    return out, n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--turns", type=int, default=600)
    ap.add_argument("--shot-every", type=int, default=5)
    ap.add_argument("--out", required=True)
    ap.add_argument("--keep-pinned", action="store_true",
                    help="keep the prologue's pinned click (reproduces "
                         "full_game_v3.json exactly; only for the repro gate)")
    args = ap.parse_args()

    prologue = json.loads(PROLOGUE_SOURCE.read_text(encoding="utf-8"))[:PROLOGUE_LEN]
    if prologue[0].get("do") is not None:
        raise SystemExit("prologue[0] should be the _comment banner -- source drifted")

    steps: list[dict] = [
        {
            "_comment": (
                f"FULL GAME, {args.turns} turns, shot every {args.shot_every}. "
                "GENERATED by make_full_game.py -- do not hand-edit; regenerate. "
                "Prologue is verbatim from full_game_v3.json (verified 200/200 on "
                "2026-07-27). Per-turn cycle = 3 idempotent modal presses + a "
                "button-free hover ping + enter. Run with --save none; decode "
                "with decode_run.py."
            )
        }
    ]
    body = prologue[1:]
    if not args.keep_pinned:
        body, n_depinned = depin(body)
        print(f"depinned {n_depinned} coordinate click(s) in the prologue")
    steps.extend(body)

    # One cycle per turn advanced, turns 1..N. The shot AFTER cycle k is named
    # `turn{k}` because the game is sitting on turn k+1 by then -- keeping that
    # off-by-one matches the verified full_game_v3.json labels exactly, and
    # decode_run.py's goldens are keyed to those names.
    for turn in range(1, args.turns + 1):
        steps.extend(turn_cycle())
        if turn % args.shot_every == 0 or turn == args.turns:
            steps.append({"do": "shot", "name": f"turn{turn:03d}"})

    out = Path(args.out)
    if not out.is_absolute():
        out = HERE / out
    out.write_text(json.dumps(steps, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {out} -- {len(steps)} steps, {args.turns} turns")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
