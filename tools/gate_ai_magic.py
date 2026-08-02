#!/usr/bin/env python
"""gate_ai_magic.py -- assert the summon ladder and the AI's magic brain hold.

WHAT THIS EXISTS TO CATCH. Two defects found in play on 2026-07-28, each of which
was INVISIBLE to every other gate because both files compiled and ran clean:

  1. The 75-mana summon resolved through five CONSTANTS, one per sphere, so
     Nature summoned Warbears at every rung of a six-rung ladder and 12 of its 13
     creatures were unreachable. Nothing dangled; the mod was simply not doing
     what it claimed.
  2. AI tribes accrued mana forever and could not spend a point, because the only
     thing that authorises a summon was set in a BUTTON body. An unopposed human
     privilege, again with nothing dangling.

So this gate asserts BEHAVIOUR-SHAPED invariants -- pools are populated, the roll
is reachable from every rung, spheres cannot cross -- rather than reference
integrity, which the other gates already cover.

Assertions:
  1. No sphere's summon pool may name a unit belonging to another sphere.
  2. Every sphere must offer MORE THAN ONE creature. This is the one that fails
     on the pre-fix tree, five times, and the one that catches a regression back
     to a constant.
  3. Every UNIT_* ident in mom_summon.slc and mom_ai_magic.slc exists in the
     generated Units.txt. A typo is a SILENT no-op here: the engine auto-creates
     unknown symbols rather than erroring, so an unresolvable name means "this
     branch never fires" with no diagnostic anywhere.
  4. No hero is summonable. Heroes are unique tribe leaders; a repeatable summon
     that could roll one would let a player field an army of its own founder.
  5. The AI handler is bounded and AI-only: `p >= 1 && p <= 5` (player 0 is the
     barbarian, and indexing the magic arrays for it was the original turn-10
     crash) and `!IsHumanPlayer` (else it drains a human pool with no click).
  6. Neither file calls Message() or opens an alertbox on the AI path. A
     messagebox aimed at an AI player is how the message-queue overflow AV was hit.
  7. Every roll band terminates at 100. A ladder whose last comparison stops
     short returns 0 for the tail of the distribution, which the caller reads as
     "no summon" -- a summon that silently does nothing some fraction of the time.

Paths honour the same env vars as ctp2_generator.py.
Exit 0 = clean; 1 = violations (each printed).
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_SCEN = HERE.parent / "scen0000"
DEFAULT_CSV = HERE / "momjr_csv"

# Fixed by the SLIC faction predicates in mom_func.slc (MomPlayerIsLife is
# p == 1 ... MomPlayerIsChaos is p == 5). Player 0 is the barbarian.
SPHERE_PLAYER = {"life": 1, "nature": 2, "sorcery": 3, "death": 4, "chaos": 5}


def _read(path: Path) -> str:
    return path.read_text(encoding="latin-1", errors="replace") if path.exists() else ""


def _strip_comments(text: str) -> str:
    """Drop // and /* */ comments -- the SLIC compiler never sees them.

    Without this, a UNIT_ ident merely NAMED in a doc comment reports as a live
    reference, which is how an illustrative placeholder once made a run
    permanently 'not launch-clean'.
    """
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def _unit_spheres(csv_dir: Path) -> dict[str, str]:
    """UNIT_IDENT -> sphere, read from the control plane, not the scenario."""
    import csv as _csv
    out: dict[str, str] = {}
    path = csv_dir / "units.csv"
    if not path.exists():
        return out
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for row in _csv.DictReader(fh):
            name = (row.get("name") or "").strip()
            sphere = (row.get("sphere") or "").strip().lower()
            if not name or not sphere or sphere == "sphere":
                continue
            ident = "UNIT_" + re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_")
            out[ident] = sphere
    return out


def _heroes(csv_dir: Path) -> set[str]:
    import json
    path = csv_dir / "mod_policy.json"
    if not path.exists():
        return set()
    policy = json.loads(path.read_text(encoding="utf-8"))
    return set(policy.get("unit_roles", {}).get("heroes", []))


def _pools(summon_src: str) -> dict[int, list[str]]:
    """Player index -> every unit its roll can return.

    Read out of the GENERATED roll rather than recomputed from the csv, so this
    measures what actually ships. Recomputing would make the gate agree with the
    generator by construction and prove nothing.
    """
    pools: dict[int, list[str]] = {}
    # SCOPE TO MomSummonRoll'S BODY FIRST. This used to split the whole file,
    # which silently assumed nothing followed the roll -- so when
    # MomSummonRungOf (the upkeep rate table, every creature in one flat list)
    # was emitted after it, all 16 of its idents were attributed to the LAST
    # sphere block and the gate reported CHAOS rolling every other sphere's
    # creatures. The pools live in the roll; read them from the roll.
    m = re.search(r"int_f\s+MomSummonRoll\s*\([^)]*\)\s*\{", summon_src)
    if m:
        start = m.end()
        depth = 1
        i = start
        while i < len(summon_src) and depth:
            if summon_src[i] == "{":
                depth += 1
            elif summon_src[i] == "}":
                depth -= 1
            i += 1
        summon_src = summon_src[start:i - 1]
    # `if (p == N) {` opens a sphere; collect UnitDB(...) until the next one.
    parts = re.split(r"\bif\s*\(\s*p\s*==\s*(\d+)\s*\)\s*\{", summon_src)
    for i in range(1, len(parts) - 1, 2):
        idx = int(parts[i])
        body = parts[i + 1]
        pools.setdefault(idx, [])
        for m in re.finditer(r"UnitDB\(\s*(UNIT_[A-Z0-9_]+)\s*\)", body):
            if m.group(1) not in pools[idx]:
                pools[idx].append(m.group(1))
    return pools


def check(scen: Path, csv_dir: Path) -> list[str]:
    fails: list[str] = []
    gd = scen / "default/gamedata"
    summon_raw = _read(gd / "mom_summon.slc")
    ai_raw = _read(gd / "mom_ai_magic.slc")

    if not summon_raw:
        fails.append(
            "mom_summon.slc is missing -- the summon still resolves through "
            "per-sphere constants, so the six-rung ladder governs nothing")
    if not ai_raw:
        fails.append(
            "mom_ai_magic.slc is missing -- AI tribes accrue mana every turn and "
            "cannot spend a point of it")
    if not summon_raw:
        return fails

    summon = _strip_comments(summon_raw)
    ai = _strip_comments(ai_raw)

    live_units = set(re.findall(r"^(UNIT_[A-Z0-9_]+)\s*\{",
                                _read(gd / "Units.txt"), re.M))
    spheres = _unit_spheres(csv_dir)
    heroes = _heroes(csv_dir)
    pools = _pools(summon)
    player_sphere = {v: k for k, v in SPHERE_PLAYER.items()}

    # 1 + 2 + 4
    for index, sphere in sorted(player_sphere.items()):
        pool = pools.get(index, [])
        if len(pool) < 2:
            fails.append(
                f"mom_summon.slc: {sphere.upper()} (player {index}) offers "
                f"{len(pool)} creature(s) -- a summon that cannot vary makes the "
                "six-rung ladder decorative")
        for unit in pool:
            owner = spheres.get(unit)
            if owner and owner != "neutral" and owner != sphere:
                fails.append(
                    f"mom_summon.slc: {sphere.upper()} can roll {unit}, which "
                    f"belongs to {owner.upper()}")
            if unit in heroes:
                fails.append(
                    f"mom_summon.slc: {sphere.upper()} can roll the hero {unit} "
                    "-- heroes are unique tribe leaders, not summonable troops")

    # 3
    for label, src in (("mom_summon.slc", summon), ("mom_ai_magic.slc", ai)):
        for unit in sorted(set(re.findall(r"\b(UNIT_[A-Z0-9_]+)\b", src))):
            if live_units and unit not in live_units:
                fails.append(
                    f"{label}: {unit} is not a block in Units.txt -- the engine "
                    "auto-creates unknown symbols, so this branch would silently "
                    "never fire")

    # 5
    if ai:
        if not re.search(r"p\s*>=\s*1\s*&&\s*p\s*<=\s*5", ai):
            fails.append(
                "mom_ai_magic.slc: no `p >= 1 && p <= 5` bound -- player 0 is the "
                "barbarian and indexing the magic arrays for it crashes")
        if "!IsHumanPlayer" not in ai:
            fails.append(
                "mom_ai_magic.slc: not guarded by !IsHumanPlayer -- it would "
                "drain a human's pool with no click behind it")

    # 6
    for label, src in (("mom_summon.slc", summon), ("mom_ai_magic.slc", ai)):
        if label == "mom_ai_magic.slc" and re.search(r"\bMessage\s*\(", src):
            fails.append(
                f"{label}: calls Message() on the AI path -- a messagebox aimed "
                "at an AI player is the message-queue overflow AV")

    # 8: call depth. MomSummonRoll is reached FROM a handler body, so if it calls
    # a user function of its own that is a 2-level chain -- the 0xC0000005 class.
    # This is why the roll returns an index instead of spawning: the caller makes
    # its own depth-1 spawn call. Asserted rather than left to review, because the
    # tempting "cleanup" is exactly the thing that crashes.
    body = re.search(r"int_f\s+MomSummonRoll\s*\([^)]*\)\s*\{(.*?)\n\}", summon, re.S)
    if body:
        called = {m for m in re.findall(r"\b(Mom[A-Za-z0-9_]+)\s*\(", body.group(1))
                  if m != "MomSummonRoll"}
        if called:
            fails.append(
                f"mom_summon.slc: MomSummonRoll calls {sorted(called)} -- it is "
                "invoked from a HandleEvent body, so any user-function call "
                "inside it is a 2-level chain and an access violation")

    # 7
    for index, sphere in sorted(player_sphere.items()):
        body = re.split(r"\bif\s*\(\s*p\s*==\s*%d\s*\)\s*\{" % index, summon)
        if len(body) < 2:
            continue
        for rung_body in re.findall(r"if\s*\(\s*r\s*==\s*\d+\s*\)\s*\{(.*?)\n\s*\}",
                                    body[1], re.S):
            bounds = [int(b) for b in re.findall(r"roll\s*<\s*(\d+)", rung_body)]
            if bounds and max(bounds) != 100:
                fails.append(
                    f"mom_summon.slc: {sphere.upper()} has a roll band ending at "
                    f"{max(bounds)}, not 100 -- the tail of the distribution "
                    "returns 0 and the summon silently does nothing")
    return fails


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scenario", default=os.environ.get(
        "CTP2_GENERATOR_SCENARIO_DIR", str(DEFAULT_SCEN)))
    ap.add_argument("--csv-dir", default=os.environ.get(
        "CTP2_GENERATOR_CSV_DIR", str(DEFAULT_CSV)))
    ap.add_argument("--list-violations", action="store_true")
    args = ap.parse_args()

    fails = check(Path(args.scenario), Path(args.csv_dir))
    for f in fails:
        print(f"FAIL {f}")
    if fails:
        print(f"\nai/summon magic gate: {len(fails)} violation(s).")
        return 1
    print("ai/summon magic gate: 5 sphere(s), tiered summon pools, AI spend path "
          "bounded -- 0 violations")
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
