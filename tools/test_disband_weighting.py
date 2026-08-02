#!/usr/bin/env python
"""test_disband_weighting.py -- the insolvency draw is proportional to upkeep.

WHY THIS IS A PYTHON TEST AND NOT A HEADLESS ONE. Insolvency is very hard to
reach in a running game, and that is by DESIGN rather than by accident: a summon
needs 75 banked mana, and each creature permanently lowers net income, so a tribe
summoning at rung 1 walks net down 2 at a time and lands exactly ON zero -- at
which point it can never bank 75 again. Net only goes NEGATIVE when a single
creature's keep exceeds the remaining headroom (a high-rung creature taken on
thin margins) or when income falls afterwards (a city or mana node lost). So the
disband path is a backstop for income LOSS, not a routine event, and a short
rung-1 game cannot exercise it at all.

What can still be tested exactly is the SELECTION MATH, which is the part the
operator specified: "units that cost more are more likely to evaporate." This
ports the roulette walk from mom_magic.slc's MomMagicPoolTick verbatim and
measures the resulting distribution.

Kept as a battery of three VARIED ledgers rather than one case, so it verifies
the rule and not a memorised instance:
  * one creature at each rung -- the ordinary mixed army
  * nine cheap and one dear -- the case the design exists for
  * all equal -- the degenerate case a strict "above average" rule would break,
    where nothing is above the mean and nothing would ever be released

Run: python tools/test_disband_weighting.py
"""
from __future__ import annotations

import collections
import random
import sys

TRIALS = 200_000
TOLERANCE = 0.005


def pick(rungs: list[int]) -> int:
    """The SLIC roulette walk, ported exactly.

    Require: rungs[i] == 0 marks a free slot (SLIC uses rung 0 as the sentinel).
    Guarantee: returns an index with probability rungs[i]/sum(rungs), or -1 when
      the ledger is empty. Never returns -1 while any slot is occupied -- the
      strict `acc > roll` against a 0-based roll makes the last occupied slot
      always satisfy the test, so the walk cannot fall off the end.
    """
    total = sum(rungs)
    if total <= 0:
        return -1
    roll = random.randrange(total)      # SLIC Random(n) yields 0..n-1
    acc = 0
    slot = -1
    for i, r in enumerate(rungs):
        if slot < 0 and r > 0:
            acc += r
            if acc > roll:
                slot = i
    return slot


CASES = {
    "one of each rung 1..5": [1, 2, 3, 4, 5],
    "nine cheap, one dear": [1, 1, 1, 1, 1, 1, 1, 1, 1, 5],
    "all equal (degenerate)": [2, 2, 2, 2],
    "sparse ledger with free slots": [0, 3, 0, 0, 1, 0, 5, 0],
}


def main() -> int:
    failures = 0
    for name, rungs in CASES.items():
        counts = collections.Counter(pick(rungs) for _ in range(TRIALS))
        if counts[-1]:
            print(f"FAIL {name}: walk returned -1 on a non-empty ledger "
                  f"{counts[-1]} time(s)")
            failures += 1
            continue
        total = sum(rungs)
        print(f"\n{name}: {rungs}")
        for i, r in enumerate(rungs):
            expected = r / total
            observed = counts[i] / TRIALS
            bad = abs(observed - expected) >= TOLERANCE
            print(f"  slot {i} rung {r}: observed {observed:.4f} "
                  f"expected {expected:.4f}{'   <-- OFF' if bad else ''}")
            if bad:
                failures += 1
            if r == 0 and counts[i]:
                print(f"  FAIL slot {i} is FREE but was selected {counts[i]}x")
                failures += 1

    if failures:
        print(f"\ndisband weighting: {failures} failure(s).")
        return 1
    print(f"\ndisband weighting: {len(CASES)} ledger(s), draw is proportional to "
          "upkeep, free slots never selected -- PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
