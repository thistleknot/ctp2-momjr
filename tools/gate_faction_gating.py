"""Gate: the five tribes actually get different things, and the wall has no holes.

Thesis
------
Faction identity in MoM is enforced in two places that can silently disagree:
the **prereq rewrite** (a sphere'd unit hangs off its sphere's ladder rung) and
the **wall** (`mom_gating.slc`'s four `mod_Can*` hooks). Either one alone looks
correct in isolation. A typo'd ident in the wall is the worst failure mode in
the whole change -- SLIC does not error on `UnitDB(UNIT_TYPO)`, the comparison
simply never matches, and that gate becomes a silent no-op while every other
check stays green.

So this gate owns none of the policy. The predicate lives in the writer
(`ctp2_generator.sphere_gate_targets`), exactly as `gate_gl_descriptions.py`
borrows `gl_descriptions.is_filler`; this file only reports. The two cannot
drift apart.

    python tools/gate_faction_gating.py
    python tools/gate_faction_gating.py --scenario <dir> --csv-dir <dir>
    python tools/gate_faction_gating.py --list-violations

Exit 0 when clean, 1 with the offending list.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import ctp2_generator as G  # noqa: E402

DEFAULT_SCENARIO = Path(os.environ.get(
    "CTP2_GENERATOR_SCENARIO_DIR",
    r"H:\Program Files(x86)\Activision\Call To Power 2\Scenarios\mom\scen0000"))
DEFAULT_CSV = Path(os.environ.get(
    "CTP2_GENERATOR_CSV_DIR", str(Path(__file__).parent / "momjr_csv")))

GATING_SLC = "default/gamedata/mom_gating.slc"

# The scenario declares no starting age, so play begins in AGE_ONE and
# Player.cpp:536-542 grants every advance with Age < startAge for free. A ladder
# rung parked in the start band would therefore be handed to all five tribes
# before the wall ever runs.
START_AGE_BAND = "AGE_ONE"

# Measured inert: these files cite ADVANCE_* idents that the engine never
# resolves in this scenario (dead base-game lists, an un-#included tutorial
# script). Established during item 3; re-deriving the list is not free, so it is
# pinned here and any NEW file with a dangling ref is a real failure.
INERT_FILES = {
    "AdvanceLists.txt", "strategies.txt", "Const.txt", "DiffDB.txt",
    "Units_historic.txt", "Units_release.txt", "tut2_main.slc",
}

SPHERES = tuple(G._SPHERE_PLAYER)

# The 5-column SLIC matrix. One declaration per sphere per family; a missing
# cell is the "ragged column" that let Chaos ship without a milestone building
# and Death without a foci counter. `decl` differs by family: MomBless* are
# messagebox SEGMENTS (`messagebox 'MomBlessLife' {`), not functions -- matching
# them with a call-shape regex reported all five as missing when all five exist.
SLIC_FAMILIES = (
    ("MomPlayerIs{S}", "call"),
    ("MomGrant{S}Building", "call"),
    ("MomBless{S}", "segment"),
)

# Suffixed Great Library STRING keys, not advance references. uniticon.txt is
# full of them (568 in the measured tree) and every one is legitimate.
GL_STRING_SUFFIXES = ("_GAMEPLAY", "_HISTORICAL", "_PREREQ", "_STATISTICS")


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def blocks(path: Path, prefix: str) -> dict[str, str]:
    """`IDENT {...}` records -> {ident: body}. latin-1: the DB files are not UTF-8."""
    if not path.is_file():
        return {}
    text = path.read_text(encoding="latin-1")
    out: dict[str, str] = {}
    for m in re.finditer(rf"^({prefix}[A-Z0-9_]+)\s*\{{(.*?)^\}}", text, re.M | re.S):
        out[m.group(1)] = m.group(2)
    return out


def field(body: str, name: str) -> str:
    m = re.search(rf"^\s*{name}\s+([A-Z0-9_]+)\s*$", body, re.M)
    return m.group(1) if m else ""


def prereqs(body: str) -> list[str]:
    out: list[str] = []
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("Prerequisites"):
            out.extend(re.findall(r"ADVANCE_[A-Z0-9_]+", s))
    return out


# ---------------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------------

def audit(scen: Path) -> list[str]:
    """Nine assertions. Returns the violation list; empty means clean."""
    gd = scen / "default/gamedata"
    adv = blocks(gd / "Advance.txt", "ADVANCE_")
    units = blocks(gd / "Units.txt", "UNIT_")
    bldgs = blocks(gd / "buildings.txt", "IMPROVE_")
    wndrs = blocks(gd / "Wonder.txt", "WONDER_")
    kinds = {"UNIT_": units, "IMPROVE_": bldgs, "WONDER_": wndrs}

    ladder = {s: G._sphere_ladder_idents(s) for s in SPHERES}
    all_rungs = {a for v in ladder.values() for a in v}
    targets = G.sphere_gate_targets()
    slc_path = scen / GATING_SLC
    slc = slc_path.read_text(encoding="latin-1") if slc_path.is_file() else ""

    v: list[str] = []

    # 1. A sphere'd block hangs off its OWN ladder. Phantom idents (the writer
    #    emits both IMPROVE_ and WONDER_ per improvements row) are not failures.
    for ident, gate in sorted(targets.items()):
        prefix = next(p for p in kinds if ident.startswith(p))
        body = kinds[prefix].get(ident)
        if body is None:
            continue
        sphere = next((s for s in SPHERES if gate in ladder[s]), None)
        enable = field(body, "EnableAdvance")
        if sphere and enable not in ladder[sphere]:
            v.append(f"A1 {ident}: EnableAdvance {enable or '<none>'} is off the "
                     f"{sphere} ladder (expected {gate})")

    # 2. Every rung reaches its own root transitively -- otherwise a tribe can
    #    climb into another sphere's ladder from a zero-prereq mundane advance.
    def reaches(start: str, goal: str) -> bool:
        seen, stack = set(), [start]
        while stack:
            cur = stack.pop()
            if cur == goal:
                return True
            if cur in seen or cur not in adv:
                continue
            seen.add(cur)
            stack.extend(prereqs(adv[cur]))
        return False

    for s in SPHERES:
        root = ladder[s][0]
        for rung in ladder[s][1:]:
            if rung in adv and root in adv and not reaches(rung, root):
                v.append(f"A2 {rung} does not reach its root {root} through prerequisites")

    # 3. Complete 6-rung ladder per sphere.
    for s in SPHERES:
        for rung in ladder[s]:
            if rung not in adv:
                v.append(f"A3 {s} ladder is incomplete: {rung} absent from Advance.txt")

    # 4. The wall names every rung -- a straggler rung is an unwalled advance.
    for s in SPHERES:
        for rung in ladder[s]:
            if rung in adv and f"AdvanceDB({rung})" not in slc:
                v.append(f"A4 mom_gating.slc never mentions {rung}")

    # 5. THE ONE THAT MATTERS: every ident the wall cites really exists.
    live = {"ADVANCE_": set(adv), "UNIT_": set(units),
            "IMPROVE_": set(bldgs), "WONDER_": set(wndrs)}
    for ident in sorted(set(re.findall(r"\b(?:ADVANCE|UNIT|IMPROVE|WONDER)_[A-Z0-9_]+", slc))):
        prefix = ident.split("_")[0] + "_"
        if ident not in live[prefix]:
            v.append(f"A5 mom_gating.slc cites {ident}, which is not in the generated DB")

    # 6. No ragged column in the SLIC sphere matrix.
    slic_text = "\n".join(
        p.read_text(encoding="latin-1") for p in sorted(gd.glob("mom_*.slc")))
    for family, shape in SLIC_FAMILIES:
        for s in SPHERES:
            name = family.format(S=s.capitalize())
            pat = rf"\b{name}\s*\(" if shape == "call" else rf"'{name}'"
            if not re.search(pat, slic_text):
                v.append(f"A6 SLIC matrix is ragged: {name} is not declared")
    # The counters are the one family with two legal spellings (Blessings/Foci).
    for s in SPHERES:
        cap = s.capitalize()
        if not re.search(rf"\bMomCount{cap}(?:Blessings|Foci)\s*\(", slic_text):
            v.append(f"A6 SLIC matrix is ragged: no MomCount{cap}Blessings/Foci counter")

    # 7. No rung in the start age band.
    for rung in sorted(all_rungs & set(adv)):
        if field(adv[rung], "Age") == START_AGE_BAND:
            v.append(f"A7 {rung} sits in {START_AGE_BAND} -- granted free at scenario start")

    # 8. Zero dangling ADVANCE_* refs across every live dimension file.
    for path in sorted(gd.iterdir()):
        if not path.is_file() or path.name in INERT_FILES:
            continue
        if path.suffix.lower() not in (".txt", ".slc"):
            continue
        try:
            text = path.read_text(encoding="latin-1")
        except OSError:
            continue
        for ident in sorted(set(re.findall(r"\bADVANCE_[A-Z0-9_]+", text))):
            if ident.endswith(GL_STRING_SUFFIXES):
                continue
            if ident not in adv:
                v.append(f"A8 {path.name} cites {ident}, absent from Advance.txt")

    # 9. Content lands in the intended age band: the rung ages are authoritative
    #    (_RUNG_AGE), and no sphere'd block may resolve to a mundane-band advance.
    age_num = {f"AGE_{w}": i for i, w in enumerate(
        ["ZERO", "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT",
         "NINE", "TEN"])}
    for rung in sorted(all_rungs & set(adv)):
        want = G._ladder_rung_age(rung)
        got = age_num.get(field(adv[rung], "Age"))
        if want is not None and got is not None and got != want:
            v.append(f"A9 {rung} is at age {got}, but its rung age is {want}")
    # Everything the emitted wall actually names, in any of the four hooks.
    walled = set(re.findall(r"\b(?:UNIT|IMPROVE|WONDER)_[A-Z0-9_]+", slc))
    for ident, gate in sorted(targets.items()):
        prefix = next(p for p in kinds if ident.startswith(p))
        if ident not in kinds[prefix]:
            continue
        enable = field(kinds[prefix][ident], "EnableAdvance")
        got = age_num.get(field(adv.get(enable, ""), "Age"), 0)
        # A mundane enabling advance is NOT a leak. There are two independent
        # gates: the advance (tech tree) and mod_CanCityBuildUnit/Building/Wonder
        # in mom_gating.slc (the hard wall). This clause used to treat a mundane
        # advance as proof that "every tribe reaches it", which was true only
        # while EVERY sphere'd block was forced onto a ladder rung.
        #
        # That force was itself the bug (fixed 2026-07-29): it put all 13 Nature
        # units behind NATURE_LORE -- 1865 science, behind GRAND_MASTERY and
        # ELDRITCH_LORE -- so a Nature city could build nothing but the 13 neutral
        # units and produced twelve identical Spearmen. MoM's design splits RACIAL
        # TROOPS (built early, mundane advance, the mainstay) from FANTASTIC
        # creatures (ladder-gated, summoned), and MOMJR encodes which is which in
        # advance_code_map.csv's `unit` lane.
        #
        # So the real invariant is not "sphere'd => ladder advance"; it is
        # "sphere'd => WALLED". Assert that instead, against the emitted wall.
        if got and got <= G._MUNDANE_MAX_AGE and enable not in all_rungs:
            if ident not in walled:
                v.append(
                    f"A9 {ident} is sphere'd and enabled by mundane {enable} "
                    f"(age {got}) but is absent from mom_gating.slc -- with no "
                    "ladder gate AND no wall, every tribe can build it")

    return v


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scenario", type=Path, default=DEFAULT_SCENARIO)
    ap.add_argument("--csv-dir", type=Path, default=DEFAULT_CSV)
    ap.add_argument("--list-violations", action="store_true",
                    help="print every violation, not the first 12 per assertion")
    args = ap.parse_args()

    if not (args.scenario / "default/gamedata").exists():
        raise SystemExit(f"{args.scenario} does not look like a scenario dir")

    v = audit(args.scenario)
    by_code: dict[str, list[str]] = {}
    for line in v:
        by_code.setdefault(line.split(" ", 1)[0], []).append(line)

    print(f"faction gating gate: {len(G.sphere_gate_targets())} target(s), "
          f"{len(v)} violation(s)")
    for code in sorted(by_code):
        rows = by_code[code]
        print(f"  {code}: {len(rows)}")
        shown = rows if args.list_violations else rows[:12]
        for line in shown:
            print(f"      {line}")
        if len(rows) > len(shown):
            print(f"      ... and {len(rows) - len(shown)} more (--list-violations)")

    if v:
        print(f"\nFAIL: {len(v)} violation(s).")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
