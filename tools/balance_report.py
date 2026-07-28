"""Balance audit over the MoM control plane: cost-vs-power outliers and sphere parity.

WHY: every other gate in this repo asks "is this legal" -- does the ident exist,
does the prereq resolve, does the file regenerate byte-stable. None of them asks
"is this FAIR". A unit can be perfectly well-formed and still be a 12-attack
dragon that costs the same as zombies.

THE METRIC. CTP2 resolves combat in rounds: each round a side deals `firepower`
damage on a hit, and a unit absorbs `hp` damage before dying -- so in principle
power scales with (attack + defense) x firepower x hp.

`hp` is dropped, on measurement. Every one of the 55 shipped units has
MaxHP 10 (the generator flattens the civ2 1h..6h spread), so the term is a
constant and contributes nothing but noise in the units. power is therefore
(attack + defense) x firepower. This is a PROXY, not the engine's own formula --
it ignores movement, terrain and unit flags. It ranks; it does not price.

THE THRESHOLD IS DERIVED, NOT PICKED. Cost-efficiency (power/cost) is heavily
right-skewed -- a handful of units are worth many times the median -- so a plain
mean+sigma band would be dragged by the very outliers it is meant to find. We
take log(efficiency), then flag on median +/- k*MAD (MAD scaled by 1.4826 so it
estimates sigma for a normal). Median and MAD have a 50% breakdown point: half
the roster could be broken and the band would still sit where the sane half is.
See skill `stat-partitioning` -- no magic constants.

Exit code is 0 always: this REPORTS, it does not gate. Balance is a judgement
call and the numbers are an input to it, not a verdict. Wire it into a gate only
once a specific band has been agreed.

Usage:
    python balance_report.py [--csv-dir tools/momjr_csv] [--top N]
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import re
import statistics as st
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_CSV = HERE / "momjr_csv"

# The sphere ladder rungs, weakest first. A unit's rung is not stored; it is
# inferred from cost banding elsewhere in the pipeline, so here we only use the
# ladder to check that the five spheres are the same SHAPE as each other.
SPHERES = ["life", "nature", "sorcery", "death", "chaos"]

MAD_TO_SIGMA = 1.4826


def _int(v: str, default: int = 0) -> int:
    """Leading integer of a civ2-style stat cell.

    units.csv stores combat stats with their civ2 suffix letter still attached
    -- `attack` is "12a", `hp` is "4h", `firepower` is "2f" -- while `cost` and
    `move` are bare. A plain int() therefore returns the default for every
    combat stat, which silently scores the whole roster at power 0. Parse the
    leading digits and ignore the tag.
    """
    s = str(v or "").strip()
    digits = ""
    for ch in s:
        if ch.isdigit() or (ch == "-" and not digits):
            digits += ch
        else:
            break
    try:
        return int(digits)
    except ValueError:
        return default


def _ident(name: str) -> str:
    """`Undead Dragon` -> `UNDEAD_DRAGON`, to join the CSV onto the shipped DB."""
    return re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_")


def load_units(csv_dir: Path, scen: Path) -> list[dict]:
    """Read the SHIPPED Units.txt, taking only `sphere` from the control plane.

    MEASURE THE MEASURE. The first version of this scored units.csv, which is
    the wrong instrument: the generator rescales on the way out (cost x~100,
    attack x5) and, decisively, FLATTENS MaxHP to 10 for every unit. The civ2
    source spreads hp over 1h..6h, so a csv-based power proxy multiplies by a
    dimension the player never experiences -- it ranked units by a stat the
    shipped game does not have. Units.txt is what the engine loads, so Units.txt
    is what gets measured.

    Because MaxHP is constant, it carries no information and is left out of the
    proxy entirely: power = (attack + defense) x firepower.
    """
    idx: dict[str, dict] = {}
    with (csv_dir / "units.csv").open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            idx[_ident((r.get("name") or ""))] = r

    text = (scen / "default/gamedata/Units.txt").read_text(
        encoding="latin-1", errors="replace")

    out = []
    for m in re.finditer(r"^UNIT_(\w+)\s*\{(.*?)^\}", text, re.S | re.M):
        ident, body = m.group(1), m.group(2)

        def g(key: str, default: int = 0) -> int:
            mm = re.search(r"\b" + key + r"\s+(-?\d+)", body)
            return int(mm.group(1)) if mm else default

        cost = g("ShieldCost")
        a, d, fp = g("Attack"), g("Defense"), g("Firepower", 1)
        power = (a + d) * fp
        csv_row = idx.get(ident, {})
        out.append({
            "ident": ident,
            "name": (csv_row.get("name") or ident.title().replace("_", " ")).strip(),
            "sphere": (csv_row.get("sphere") or "?").strip().lower(),
            "prereq": (csv_row.get("prereq") or "").strip(),
            "domain": (csv_row.get("domain") or "?").strip(),
            "cost": cost, "attack": a, "defense": d,
            "hp": g("MaxHP"), "fp": fp,
            "power": power,
            "eff": (power / cost) if (power > 0 and cost > 0) else 0.0,
        })
    return out


def robust_band(values: list[float], k: float) -> tuple[float, float, float]:
    """Median +/- k*MAD on the LOG scale. Returns (lo, med, hi) in log space."""
    med = st.median(values)
    mad = st.median([abs(v - med) for v in values]) * MAD_TO_SIGMA
    if mad == 0:
        mad = st.pstdev(values) or 1e-9
    return med - k * mad, med, med + k * mad


def report_units(units: list[dict], k: float, top: int) -> None:
    print("=" * 78)
    print("UNIT COST-EFFICIENCY  (power = (atk + def) x firepower, per shield -- SHIPPED Units.txt)")
    print("=" * 78)

    scored = [u for u in units if u["eff"] > 0]
    logs = [math.log(u["eff"]) for u in scored]
    lo, med, hi = robust_band(logs, k)
    print(f"n={len(scored)}  median eff={math.exp(med):.2f}  "
          f"band(k={k} MAD) = [{math.exp(lo):.2f}, {math.exp(hi):.2f}]")
    print()

    over = sorted([u for u in scored if math.log(u["eff"]) > hi],
                  key=lambda u: -u["eff"])
    under = sorted([u for u in scored if math.log(u["eff"]) < lo],
                   key=lambda u: u["eff"])

    print(f"-- OVERPOWERED FOR COST ({len(over)}) "
          "-- more combat value per shield than the roster supports")
    for u in over[:top]:
        print(f"   {u['sphere']:8} {u['name'][:24]:24} cost{u['cost']:>3} "
              f"a{u['attack']:>3} d{u['defense']:>3} hp{u['hp']:>2} fp{u['fp']:>2} "
              f"-> power{u['power']:>4} eff {u['eff']:6.2f}")
    if not over:
        print("   (none)")

    print(f"\n-- UNDERPOWERED FOR COST ({len(under)}) "
          "-- costs more than it can ever be worth")
    for u in under[:top]:
        print(f"   {u['sphere']:8} {u['name'][:24]:24} cost{u['cost']:>3} "
              f"a{u['attack']:>3} d{u['defense']:>3} hp{u['hp']:>2} fp{u['fp']:>2} "
              f"-> power{u['power']:>4} eff {u['eff']:6.2f}")
    if not under:
        print("   (none)")


def report_sphere_parity(units: list[dict]) -> None:
    print()
    print("=" * 78)
    print("SPHERE PARITY  -- the five tribes should be comparable, not identical")
    print("=" * 78)
    by = defaultdict(list)
    for u in units:
        by[u["sphere"]].append(u)

    print(f"{'sphere':9} {'n':>3} {'tot pow':>8} {'med pow':>8} {'med cost':>9} "
          f"{'best unit':>22} {'pow':>5}")
    stats = {}
    for s in SPHERES:
        us = by.get(s, [])
        if not us:
            print(f"{s:9} {'0':>3}   -- NO UNITS --")
            continue
        best = max(us, key=lambda u: u["power"])
        stats[s] = {
            "n": len(us),
            "tot": sum(u["power"] for u in us),
            "medpow": st.median([u["power"] for u in us]),
            "medcost": st.median([u["cost"] for u in us]),
            "best": best,
        }
        v = stats[s]
        print(f"{s:9} {v['n']:>3} {v['tot']:>8} {v['medpow']:>8.0f} "
              f"{v['medcost']:>9.1f} {best['name'][:22]:>22} {best['power']:>5}")

    if len(stats) == len(SPHERES):
        ns = [v["n"] for v in stats.values()]
        tots = [v["tot"] for v in stats.values()]
        print()
        print(f"   roster size   min={min(ns)} max={max(ns)}  "
              f"ratio {max(ns)/max(min(ns),1):.2f}x")
        print(f"   total power   min={min(tots)} max={max(tots)}  "
              f"ratio {max(tots)/max(min(tots),1):.2f}x")
        worst = max(stats.items(), key=lambda kv: kv[1]["tot"])
        least = min(stats.items(), key=lambda kv: kv[1]["tot"])
        print(f"   strongest={worst[0]}  weakest={least[0]}")

    neutral = by.get("neutral", [])
    if neutral:
        best_n = max(neutral, key=lambda u: u["power"])
        print()
        print(f"   NEUTRAL pool: {len(neutral)} units, best = "
              f"{best_n['name']} (power {best_n['power']}, cost {best_n['cost']})")
        print("   Neutral units are available to EVERY tribe, so anything here that "
              "out-powers\n   a sphere's own top unit erases the reason to play that "
              "sphere.")
        for s, v in stats.items():
            if best_n["power"] > v["best"]["power"]:
                print(f"     ! {s}: neutral {best_n['name']} (pow {best_n['power']}) "
                      f"beats its best {v['best']['name']} (pow {v['best']['power']})")


def report_stat_twins(units: list[dict]) -> None:
    """Units with an IDENTICAL combat line but a different price.

    This is the check that catches what an outlier band structurally cannot.
    Cost-efficiency flags a unit that is extreme against the WHOLE roster; it
    says nothing when two units are individually reasonable but priced against
    each other absurdly. Undead Dragon and Storm Drake are the case in point --
    both 60/30/10/2, one costs 1200 and the other 4000 -- and neither is an
    efficiency outlier, so the band reports nothing.

    Identical stats are not themselves a defect (a reskin per sphere is a
    legitimate design). A >1.5x price gap between identical stat lines is,
    because one tribe is paying multiples for the same unit.
    """
    print()
    print("=" * 78)
    print("STAT TWINS  -- identical combat line, different price")
    print("=" * 78)
    # Group WITHIN a domain (0 land / 1 air / 2 sea) and only over units that
    # can actually attack. Without the domain key the check pairs a Galley with
    # Spearmen -- identical 5/5/10/1, but one is a boat, so the price gap is a
    # role difference and not a defect. Without the attack>0 filter it pairs
    # Peasants with a Caravan, where the combat line is incidental to both.
    groups = defaultdict(list)
    for u in units:
        if u["power"] > 0 and u["attack"] > 0:
            groups[(u["domain"], u["attack"], u["defense"], u["hp"], u["fp"])].append(u)

    flagged = 0
    for line, us in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        if len(us) < 2:
            continue
        costs = [u["cost"] for u in us if u["cost"] > 0]
        if not costs:
            continue
        ratio = max(costs) / max(min(costs), 1)
        if ratio <= 1.5:
            continue
        flagged += 1
        dom, a, d, hp, fp = line
        print(f"   domain{dom} a{a} d{d} hp{hp} fp{fp}  --  price spread {ratio:.2f}x")
        for u in sorted(us, key=lambda u: u["cost"]):
            print(f"      {u['sphere']:8} {u['name'][:24]:24} cost {u['cost']:>5}")
    if not flagged:
        print("   (none past 1.5x)")


def report_hygiene(units: list[dict]) -> None:
    print()
    print("=" * 78)
    print("ROSTER HYGIENE")
    print("=" * 78)
    seen = defaultdict(list)
    for u in units:
        seen[u["name"]].append(u)
    dupes = {n: v for n, v in seen.items() if len(v) > 1}
    if dupes:
        print(f"-- DUPLICATE NAMES ({len(dupes)}) -- two rows a player cannot tell apart")
        for n, v in sorted(dupes.items()):
            print(f"   {n!r} x{len(v)}  spheres={sorted({x['sphere'] for x in v})}")
    else:
        print("-- duplicate names: none")

    # `no` is the civ2 NEVER sentinel, distinct from `nil` (= no prerequisite,
    # i.e. buildable from turn one). Confusing the two is a shipped-bug class
    # here ([[civ2-no-vs-nil-sentinel]]), so report the two populations apart.
    never = [u for u in units if u["prereq"] == "no"]
    root = [u for u in units if u["prereq"] == "nil"]
    print(f"\n-- prereq 'no' (NEVER buildable): {len(never)}")
    for u in never:
        print(f"   {u['sphere']:8} {u['name'][:24]:24} cost{u['cost']:>3} "
              f"power{u['power']:>4}  <- carries real stats but can never be built")
    print(f"\n-- prereq 'nil' (buildable turn one): {len(root)}")
    for u in root:
        print(f"   {u['sphere']:8} {u['name'][:24]:24} cost{u['cost']:>3} "
              f"power{u['power']:>4}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv-dir", default=os.environ.get(
        "CTP2_GENERATOR_CSV_DIR", str(DEFAULT_CSV)))
    ap.add_argument("--k", type=float, default=3.0,
                    help="MAD multiplier for the outlier band (default 3)")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--scenario", default=os.environ.get(
        "CTP2_GENERATOR_SCENARIO_DIR", str(HERE.parent / "scen0000")))
    args = ap.parse_args()

    csv_dir = Path(args.csv_dir)
    units = load_units(csv_dir, Path(args.scenario))
    if not units:
        raise SystemExit(f"no units loaded from {csv_dir}")

    report_units(units, args.k, args.top)
    report_sphere_parity(units)
    report_stat_twins(units)
    report_hygiene(units)
    print()
    print("REPORT ONLY -- exit 0. These are inputs to a balance decision, "
          "not a pass/fail gate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
