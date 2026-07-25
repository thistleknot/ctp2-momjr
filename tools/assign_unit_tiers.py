"""Tech-gate no-prereq units by combat tier so they unlock through research.

Purpose:
    Merged civ2 rosters arrive mostly ungated (prereq='no') -> every unit is
    buildable at turn 1 (40+ units in the Build Manager). This assigns an
    advance prereq CODE to each ungated unit by its cost tier, so only true
    starters remain turn-1 and stronger units unlock as the tech tree advances.
    Gating on magic-sphere advances is on-theme for a magic mod.

    Runs AFTER merge (+ genre mask), BEFORE the generator, editing the merged
    units.csv in place. Idempotent: only rewrites 'no'/'nil'/'' prereqs; units
    with a real prereq (MoM heroes gated on Mys, etc.) are untouched.

Tiers (by unit cost) -> gate code -> advance/age:
    <= STARTER_COST : keep 'no'  (ADVANCE_WARRIOR_CODE, start-guaranteed)
    tier 1          : AGE_ONE gate
    tier 2          : AGE_TWO gate
    tier 3          : AGE_THREE gate

Usage:
    assign_unit_tiers.py --csv <merged csv dir> [--starter-cost 2]
        [--t1 6 --t2 12] [--gate1 Amp --gate2 Gun --gate3 Feu]
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

NO_PREREQ = {"no", "nil", ""}


def cost_num(v: str) -> int:
    return int(re.sub(r"[^0-9]", "", str(v)) or 0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--starter-cost", type=int, default=2,
                        help="units at/below this cost stay turn-1 (default 2)")
    parser.add_argument("--t1", type=int, default=5, help="tier-1 max cost")
    parser.add_argument("--t2", type=int, default=9, help="tier-2 max cost")
    parser.add_argument("--gate1", default="Amp", help="AGE_ONE gate code")
    parser.add_argument("--gate2", default="Gun", help="AGE_TWO gate code")
    parser.add_argument("--gate3", default="Feu", help="AGE_THREE gate code")
    args = parser.parse_args()

    path = args.csv / "units.csv"
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        header = reader.fieldnames
        rows = list(reader)

    gated = {0: 0, 1: 0, 2: 0, 3: 0}
    for r in rows:
        if (r.get("prereq") or "").strip().lower() not in NO_PREREQ:
            continue  # real prereq -> leave it
        c = cost_num(r.get("cost", "0"))
        if c <= args.starter_cost:
            gated[0] += 1
            continue  # true starter, keep 'no'
        if c <= args.t1:
            r["prereq"] = args.gate1; gated[1] += 1
        elif c <= args.t2:
            r["prereq"] = args.gate2; gated[2] += 1
        else:
            r["prereq"] = args.gate3; gated[3] += 1

    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=header, lineterminator="\r\n",
                           extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    print(f"unit tiers: starter(keep)={gated[0]} "
          f"tier1({args.gate1})={gated[1]} tier2({args.gate2})={gated[2]} "
          f"tier3({args.gate3})={gated[3]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
