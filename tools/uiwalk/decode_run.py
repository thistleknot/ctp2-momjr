"""Decode a uiwalk run directory into a per-turn progress report.

Thesis this exists to enforce: A RUN THAT COMPLETES IS NOT A RUN THAT
PROGRESSED. `ai_stall_40turns.json` v1 "passed" while turns 20-35 were
byte-identical -- the RESEARCH modal had swallowed every injected enter and the
walk happily executed all 263 steps against a frozen game.

So the only question worth asking of a long playthrough is: DID THE GAME CLOCK
MOVE BETWEEN CHECKPOINT FRAMES? This reads the `turnNNN.png` shots a full-game
run drops and reports, per consecutive pair, the pixel delta and the verdict.

Delta decoder (measured, see docs/lessons_learned.md):
    0            input never landed, or a modal swallowed it   -> STALL
    < 2000       cosmetically identical frame                  -> STALL
    ~5k          one row selected / a control enabled
    ~78k         a list scrolled
    ~180k        a panel opened or closed
    60k-300k     normal turn-to-turn map + panel churn          -> LIVE
    > 400000     whole screen replaced: crash, blank, or modal  -> SUSPECT

Usage:
    python decode_run.py                 # newest run under runs/
    python decode_run.py runs/20260727-091500
"""
from __future__ import annotations

import sys
from pathlib import Path

RUNS = Path(__file__).resolve().parent / "runs"

# 2026-07-27 RECALIBRATION.
# The 2000px threshold was measured on a run that checkpointed every FIFTH
# turn, where one interval carried five turns of map + panel churn. Applied to
# a per-turn checkpoint it cried STALL six times on run 20260727-181047 -- a
# run whose in-frame Rush Buy counter read 1200 -> 743 -> 12, i.e. the clock
# was advancing the whole time. A camera parked over unexplored ocean with no
# unit moving legitimately redraws only the build counter: ~300-1200 px.
#
# The ACTUAL stall signature from the bug this file exists to catch was
# BYTE-IDENTICAL frames. Nothing about a real turn boundary can leave zero
# pixels changed -- the turn counter alone moves some. So the honest threshold
# is "essentially nothing", not "not much".
STALL_MAX = 100
SUSPECT_MIN = 400_000


def classify(delta: int) -> str:
    if delta <= STALL_MAX:
        return "STALL"
    if delta >= SUSPECT_MIN:
        return "SUSPECT"
    return "LIVE"


def frame_delta(a: Path, b: Path) -> int:
    """Count differing pixels between two same-size RGB captures."""
    from PIL import Image, ImageChops

    with Image.open(a) as ia, Image.open(b) as ib:
        ia = ia.convert("RGB")
        ib = ib.convert("RGB")
        if ia.size != ib.size:
            # A size change is itself a finding -- the engine reflowed.
            return -1
        diff = ImageChops.difference(ia, ib)
        return sum(1 for px in diff.getdata() if px != (0, 0, 0))


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        run = Path(argv[1])
    else:
        candidates = sorted((d for d in RUNS.iterdir() if d.is_dir()), reverse=True)
        if not candidates:
            print("no runs found under", RUNS)
            return 1
        run = candidates[0]

    # Anchored to uiwalk's own `NN_name.png` shot naming. A loose `*turn*.png`
    # also swept up hand-made debug crops sitting in the run dir and reported
    # two bogus SUSPECT frames off them (2026-07-27).
    # Sort NUMERICALLY on the turn number, not lexically. A 200-turn run writes
    # `100_turn190.png`, which sorts BEFORE `66_turn122.png` as a string -- the
    # first run long enough to pass shot 99 silently reported its last
    # checkpoint as turn 188 and compared the tail out of order (2026-07-27).
    import re
    shots = []
    for p in run.glob("*.png"):
        m = re.fullmatch(r"(\d+)_turn(\d+)", p.stem)
        if m:
            shots.append((int(m.group(2)), p))
    shots = [p for _n, p in sorted(shots)]
    if not shots:
        print(f"{run.name}: no turn shots -- the run never reached the turn loop")
        return 1

    print(f"run {run.name}: {len(shots)} turn checkpoints")
    stalls: list[str] = []
    suspects: list[str] = []
    for prev, cur in zip(shots, shots[1:]):
        d = frame_delta(prev, cur)
        verdict = "RESIZE" if d < 0 else classify(d)
        print(f"  {prev.stem:>24} -> {cur.stem:<24} {d:>9} px  {verdict}")
        if verdict == "STALL":
            stalls.append(cur.stem)
        elif verdict in ("SUSPECT", "RESIZE"):
            suspects.append(cur.stem)

    print()
    print(f"last checkpoint reached: {shots[-1].stem}")
    if stalls:
        print(f"STALLED at {len(stalls)} checkpoint(s): {', '.join(stalls)}")
    if suspects:
        print(f"SUSPECT at {len(suspects)} checkpoint(s): {', '.join(suspects)}")
    if not stalls and not suspects:
        print("no stalls, no suspect frames -- the clock moved at every checkpoint")
    return 1 if stalls else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
