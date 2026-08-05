#!/usr/bin/env python3
"""
Regression test for the MoM sphere-magic SLIC layer (per element, then dimension).

Purpose:
  SLIC runs only inside the CTP2 engine, so this cannot execute handlers. Instead
  it LINTS the deployed .slc against the base-verified API contract, locking in each
  proven "element" (one sphere) and guarding the specific mistakes that cost launches
  during B1a:
    - `playerTurn` is NOT a base SLIC symbol (undefined at load) -> use player[0].
    - `TRIBES_*` are civilisation-DB record names, NOT SLIC symbols -> use the numeric
      player index (p == 1 for Life).
    - AddGold takes an integer player index, NOT a player[] object.
    - CityHasBuilding takes a BuildingDB() reference, NOT a quoted "IMPROVE_..." string.
    - mom_func.slc must be #included before mom_turns.slc (helpers defined first).

Run:  PYTHONIOENCODING=utf-8 python Scenarios/mom/tools/test_mom_slic.py
Exit: 0 = all pass; 1 = failure(s) printed.

Extend for B1b: add each sphere to SPHERES as it is proven in-game.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

GD = Path(__file__).resolve().parents[1] / "scen0000" / "default" / "gamedata"

# The 5-sphere per-turn-gold dimension. B1a proved Life; B1b fanned out the rest.
#   name, faction player index, predicate, counter (None if the branch uses no counter),
#   per-turn gold formula (verbatim), blessing/focus buildings counted via BuildingDB.
SPHERES = [
    {
        "name": "Life", "index": 1, "predicate": "MomPlayerIsLife",
        "counter": "MomCountLifeBlessings",
        "formula": "6 + player[0].cities * 3 + MomCountLifeBlessings(p) * 4",
        "buildings": ["IMPROVE_TEMPLE", "IMPROVE_CITY_WALLS", "IMPROVE_WIZARDS_FORTRESS"],
        # B2 milestone: advance -> (blessing building, blessing unit); burst = buildings above.
        "advance": "ADVANCE_LIFE_MAGIC",
        "blessing_building": "IMPROVE_TEMPLE", "blessing_unit": "UNIT_GUARDIAN_SPIRIT",
    },
    {
        "name": "Nature", "index": 2, "predicate": "MomPlayerIsNature",
        "counter": "MomCountNatureFoci",
        "formula": "4 + player[0].cities * 2 + MomCountNatureFoci(p) * 3",
        "buildings": ["IMPROVE_GRANARY", "IMPROVE_PRIMAL_SOURCE", "IMPROVE_FANTASTIC_STABLE"],
        "advance": "ADVANCE_NATURE_MAGIC",
        "blessing_building": "IMPROVE_GRANARY", "blessing_unit": "UNIT_WARBEARS",
    },
    {
        "name": "Sorcery", "index": 3, "predicate": "MomPlayerIsSorcery",
        "counter": "MomCountSorceryFoci",
        "formula": "4 + player[0].cities * 2 + MomCountSorceryFoci(p) * 3",
        "buildings": ["IMPROVE_LIBRARY", "IMPROVE_BEACON_OF_WISDOM"],
        "advance": "ADVANCE_SORCERY",
        "blessing_building": "IMPROVE_LIBRARY", "blessing_unit": "UNIT_MAGE",
    },
    {
        "name": "Death", "index": 4, "predicate": "MomPlayerIsDeath",
        "counter": None,
        "formula": "4 + player[0].cities * 2 + (player[0].units / 3)",
        "buildings": [],
        # Death has no per-turn building counter (B1 income is unit-based), but its B2
        # milestone burst set is military buildings.
        "advance": "ADVANCE_DEATH_MAGIC",
        "blessing_building": "IMPROVE_BARRACKS", "blessing_unit": "UNIT_ZOMBIES",
        "burst_buildings": ["IMPROVE_BARRACKS", "IMPROVE_MECHANICIANS_GUILD"],
    },
    {
        "name": "Chaos", "index": 5, "predicate": "MomPlayerIsChaos",
        "counter": None,
        "formula": "4 + Random(6 + player[0].cities * 10)",
        "buildings": [],
        # Chaos milestone = random gold windfall (no building/unit, no burst) per its theme.
        "advance": "ADVANCE_CHAOS_MAGIC",
        "blessing_building": None, "blessing_unit": None, "chaos_windfall": True,
    },
]

_failures: list[str] = []


def _check(cond: bool, msg: str) -> None:
    if not cond:
        _failures.append(msg)


def _read(name: str) -> str:
    p = GD / name
    _check(p.exists(), f"{name}: MISSING from live gamedata")
    return p.read_text(encoding="latin-1") if p.exists() else ""


def main() -> int:
    func = _read("mom_func.slc")
    turns = _read("mom_turns.slc")
    effects = _read("mom_city_effects.slc") if (GD / "mom_city_effects.slc").exists() else ""
    msg = _read("mom_msg.slc") if (GD / "mom_msg.slc").exists() else ""
    magic = _read("mom_magic.slc") if (GD / "mom_magic.slc").exists() else ""
    scenario = _read("scenario.slc")

    ascii_files = [("mom_func.slc", func), ("mom_turns.slc", turns), ("scenario.slc", scenario)]
    if effects:
        ascii_files.append(("mom_city_effects.slc", effects))
    if msg:
        ascii_files.append(("mom_msg.slc", msg))
    if magic:
        ascii_files.append(("mom_magic.slc", magic))
    for name, text in ascii_files:
        raw = (GD / name).read_bytes() if (GD / name).exists() else b""
        _check(all(b < 128 for b in raw), f"{name}: contains non-ASCII bytes (SLIC lexer is ASCII-only)")
        # NO CRLF ASSERTION. mom_city_effects.slc, mom_magic.slc and
        # mom_spells.slc all ship with CRLF and the engine loads them on every
        # run, so the old "use LF" rule was asserting a preference as a defect.
        # The ASCII rule above IS evidenced -- the SLIC lexer is byte-oriented.

    # Strip comments so token checks only see code.
    code = "\n".join(re.sub(r"//.*$", "", ln) for ln in (func + "\n" + turns + "\n" + effects).splitlines())

    # --- guards against the B1a mistakes (must never reappear) ---
    _check("playerTurn" not in code,
           "code uses `playerTurn` (undefined SLIC symbol) -> use player[0]")
    # INVERTED 2026-08-05. This used to assert `TRIBES_*` must NEVER appear,
    # on the belief that a tribe's identity is its SEAT (p == 1 is Life). That
    # belief was FALSE -- the New Game EMPIRE selector decides the civ, so a
    # Nature player at seat 1 was handed Life's magic -- and the assertion was
    # actively defending the bug. Identity now comes from the civilisation, and
    # the quoted record name is how you name one.
    _check(re.search(r'CivilizationIndex\s*\(\s*"TRIBES_[A-Z]+"\s*\)', code) is not None,
           "sphere identity must come from CivilizationIndex(\"TRIBES_*\"), not the "
           "player's seat index -- see mom-sphere-is-seat-index-not-civ")
    _check(not re.search(r"int_f MomPlayerIs[A-Za-z]+\(int_t (p_\d)\)\s*\{\s*if\s*\(\s*\1\s*==\s*\d", code),
           "a MomPlayerIs* predicate compares its argument to a literal seat number "
           "-- read MomSphere[] instead; the seat is not the sphere")

    _check(not re.search(r"AddGold\s*\(\s*player\s*\[", code),
           "AddGold called with a player[] object -> pass the integer index (AddGold(p, ...))")

    # INVERTED 2026-08-05. The engine REQUIRES a hard quoted string literal here
    # (slicfunc.cpp: SA_TYPE_HARD_STRING, looked up via StringDB); a BuildingDB()
    # reference or a variable raises "Wrong type of argument" at runtime. The old
    # assertion demanded exactly the form that fails.
    _check(not re.search(r"CityHasBuilding\s*\([^)]*BuildingDB\s*\(", code),
           "CityHasBuilding called with BuildingDB(...) -> the engine needs a hard "
           'quoted string: CityHasBuilding(city, "IMPROVE_X")')
    _check(not re.search(r"CreateUnit\s*\(\s*player\s*\[", code),
           "CreateUnit called with a player[] object -> pass the integer index (CreateUnit(p, UnitDB(...), ...))")

    # --- per-sphere element contract ---
    for s in SPHERES:
        _check(re.search(rf"int_f\s+{s['predicate']}\s*\(\s*int_t\s+p_\d\s*\)", func) is not None,
               f"{s['name']}: predicate {s['predicate']}(int_t p_N) not defined")
        # SPHERE, NOT SEAT. This used to assert `p == <index>`, i.e. that a
        # tribe's identity is which seat it occupies. That is false and cost a
        # full day: the EMPIRE selector decides the civ, so the predicate must
        # read the resolved MomSphere[] array.
        _check(re.search(rf"MomSphere\s*\[\s*p_\d\s*\]\s*==\s*{s['index']}\b", func) is not None,
               f"{s['name']}: predicate must test MomSphere[p_N] == {s['index']}, "
               f"not the player's seat number")
        if s["counter"]:
            _check(s["counter"] in func, f"{s['name']}: counter {s['counter']} not defined")
        norm = re.sub(r"\s+", " ", turns)
        _check(re.sub(r"\s+", " ", s["formula"]) in norm,
               f"{s['name']}: per-turn gold formula not found: {s['formula']}")
        for b in s["buildings"]:
            _check(re.search(rf'CityHasBuilding\s*\([^)]*"{b}"', func) is not None,
                   f"{s['name']}: blessing building {b} not counted via "
                   f'CityHasBuilding(city, "{b}") -- the engine requires a hard '
                   f"quoted string here")

    # --- include order: func -> turns -> city_effects -> msg (msg LAST) ---
    fi = scenario.find('#include "mom_func.slc"')
    ti = scenario.find('#include "mom_turns.slc"')
    _check(fi != -1 and ti != -1 and fi < ti,
           "scenario.slc must #include mom_func.slc BEFORE mom_turns.slc")
    if msg:
        ci = scenario.find('#include "mom_city_effects.slc"')
        mi = scenario.find('#include "mom_msg.slc"')
        _check(mi != -1 and ci != -1 and ti < ci < mi,
               "scenario.slc include order must be func -> turns -> city_effects -> msg (msg last)")

    # --- B2 milestone-event handlers (mom_city_effects.slc), once present ---
    if effects:
        _check("HandleEvent(GrantAdvance)" in effects,
               "mom_city_effects.slc: missing GrantAdvance blessing handler")
        _check("HandleEvent(CreateBuilding)" in effects,
               "mom_city_effects.slc: missing CreateBuilding burst handler")
        _check("city[0].owner" in effects,
               "CreateBuilding handler must derive the player from city[0].owner")
        _check("MomSpawnSphereUnit" in func,
               "mom_func.slc missing milestone helper MomSpawnSphereUnit")
        # Fanned out per sphere rather than one generic helper: CityHasBuilding
        # requires a hard string literal, so a generic BuildingDB() parameter is
        # impossible. There is no MomGrantSphereBuilding and there cannot be one.
        for s in SPHERES:
            if s.get("blessing_building"):
                h = f"MomGrant{s['name']}Building"
                _check(h in func, f"mom_func.slc missing milestone helper {h}")
        ecode = "\n".join(re.sub(r"//.*$", "", ln) for ln in effects.splitlines())
        enorm = re.sub(r"\s+", " ", ecode)
        for s in SPHERES:
            # every sphere gates its milestone on its own predicate + magic advance
            _check(re.search(rf"{s['predicate']}\s*\(\s*p\s*\).*?AdvanceDB\s*\(\s*{s['advance']}\s*\)",
                             enorm) is not None,
                   f"{s['name']}: GrantAdvance branch for {s['advance']} not gated by {s['predicate']}")
            if s.get("chaos_windfall"):
                _check(re.search(rf"{s['predicate']}\s*\(\s*p\s*\).*?AddGold\s*\(\s*p\s*,[^)]*Random",
                                 enorm) is not None,
                       f"{s['name']}: expected a Random gold windfall on {s['advance']}")
                continue
            _check(re.search(rf"MomGrant{s['name']}Building\s*\(\s*p\s*\)", ecode) is not None,
                   f"{s['name']}: MomGrant{s['name']}Building(p) not called on advance")
            _check(re.search(rf"MomSpawnSphereUnit\s*\(\s*p\s*,\s*UnitDB\s*\(\s*{s['blessing_unit']}\s*\)",
                             ecode) is not None,
                   f"{s['name']}: blessing unit {s['blessing_unit']} not spawned on advance")
            for b in s.get("burst_buildings", s["buildings"]):
                _check(re.search(rf"value\[0\]\s*==\s*BuildingDB\s*\(\s*{b}\s*\)", ecode) is not None,
                       f"{s['name']}: burst building {b} not rewarded -- compare "
                       f"value[0] == BuildingDB({b}); CreateBuilding does not "
                       f"populate building[]")

    # --- Phase C sphere blessing popups (mom_msg.slc), once present ---
    if msg:
        mcode = "\n".join(re.sub(r"//.*$", "", ln) for ln in msg.splitlines())
        mnorm = re.sub(r"\s+", " ", mcode)
        _check("HandleEvent(GrantAdvance)" in msg,
               "mom_msg.slc: missing GrantAdvance blessing-message handler")
        _check("IsHumanPlayer" in msg,
               "mom_msg.slc: blessing popups must be gated by IsHumanPlayer (human-only)")
        strtext = (GD.parents[1] / "english" / "gamedata" / "scen_str.txt").read_text(encoding="latin-1")
        for s in SPHERES:
            key = "MomBless" + s["name"]
            _check(re.search(rf"Message\s*\(\s*g\.player\s*,\s*'{key}'\s*\)", mnorm) is not None,
                   f"{s['name']}: mom_msg.slc does not Message('{key}') for its advance")
            # The scen_str KEY is the segment's Text() id without the ID_
            # prefix -- MomBlessLife is a segment name and was never a key.
            skey = "MOM_MSG_BLESS_" + s["name"].upper()
            _check(re.search(rf'^{skey}\s', strtext, re.M) is not None,
                   f"{s['name']}: scen_str.txt missing string key {skey}")

    # --- M1 magic-power pool (mom_magic.slc), once present ---
    if magic:
        mgcode = "\n".join(re.sub(r"//.*$", "", ln) for ln in magic.splitlines())
        _check("HandleEvent(BeginTurn)" in magic and "MomMagicPoolTick" in magic,
               "mom_magic.slc: missing BeginTurn 'MomMagicPoolTick' handler")
        # Declared in mom_func.slc (include 48), not mom_magic.slc (56):
        # mom_msg.slc reads them at 55, so declaring them in mom_magic would be
        # too late. Search both rather than assuming a home.
        decls = func + "\n" + magic
        for arr in ("MomMagicCur", "MomMagicMax", "MomMagicPerTurn"):
            _check(re.search(rf"int_t\s+{arr}\s*\[\s*31\s*\]", decls) is not None,
                   f"missing file-scope pool array {arr}[31] (expected in mom_func.slc)")
        _check("MomRecalcMagicPerTurn" in magic,
               "mom_magic.slc: missing MomRecalcMagicPerTurn helper")
        # FLOOD SAFETY: the popup Message must be a single call, NOT inside a for-loop
        # (unlatched Message in a repeat context = 0xC0000005, the B1a lesson). Assert the
        # global interpolation index is set immediately before a single Message.
        # The property that matters is that this Message happens ONCE per tick,
        # not that a particular scalar is assigned on the line above it.
        #
        # The old assertion demanded `MomMagicGenDisp = MomMagicPerTurn[p];`
        # immediately before the Message. That assignment was REMOVED on purpose:
        # MomMagicPerTurn holds NET income since upkeep landed, so copying it into
        # the gross 'Income' scalar printed net twice and made the panel's
        # Income - Upkeep = Net line fail to add up. MomRecalcMagicPerTurn is now
        # the sole writer of all three scalars. Asserting the adjacency was
        # asserting a display bug.
        _check(mgcode.count("Message(g.player, 'MomMagicPower')") == 1,
               "mom_magic.slc: MomMagicPower must be sent from exactly ONE site "
               "(an unlatched Message in a repeat context is the 0xC0000005 "
               "flood class)")
        _check(re.search(r"for\s*\([^)]*\)\s*\{[^}]*Message\s*\(", mgcode) is None,
               "mom_magic.slc: a Message() appears inside a for-loop — flood risk (0xC0000005)")
        # popup values go through plain int_t display scalars (base-verified {scalar} form)
        for disp in ("MomMagicCurDisp", "MomMagicMaxDisp", "MomMagicGenDisp"):
            _check(re.search(rf"int_t\s+{disp}\s*;", decls) is not None,
                   f"missing display scalar {disp} (expected in mom_func.slc)")
        strtext_m = (GD.parents[1] / "english" / "gamedata" / "scen_str.txt").read_text(encoding="latin-1")
        _check(re.search(r"^MOM_MSG_MAGIC_POWER\s", strtext_m, re.M) is not None,
               "scen_str.txt: missing MOM_MSG_MAGIC_POWER key (MomMagicPower is "
               "the SEGMENT name, not the string key)")
        _check("{MomMagicCurDisp}" in strtext_m and "{MomMagicMaxDisp}" in strtext_m
               and "{MomMagicGenDisp}" in strtext_m,
               "scen_str.txt: MomMagicPower must interpolate scalar {MomMagicCurDisp}/{MomMagicMaxDisp}/{MomMagicGenDisp}")
        # regression guard: array-indexed {Arr[Idx]} interpolation is unsupported (silently drops the message)
        _check("[MomMagicMsgP]" not in strtext_m and "MomMagicMsgP" not in magic,
               "scen_str.txt/mom_magic.slc: array-indexed {Arr[Idx]} interpolation (MomMagicMsgP) must not return")
        # include order: mom_magic.slc after mom_msg.slc
        gi = scenario.find('#include "mom_magic.slc"')
        mi2 = scenario.find('#include "mom_msg.slc"')
        _check(gi != -1 and mi2 != -1 and mi2 < gi,
               "scenario.slc must #include mom_magic.slc after mom_msg.slc")

        # --- M2 school multipliers (mom_magic.slc) ---
        _check(re.search(r"int_t\s+MomMagicSchoolPct\s*\[\s*31\s*\]", decls) is not None,
               "missing file-scope MomMagicSchoolPct[31] (expected in mom_func.slc)")
        _check("HandleEvent(GrantAdvance)" in magic and "MomMagicSchoolGrant" in magic,
               "mom_magic.slc: missing GrantAdvance 'MomMagicSchoolGrant' handler (M2)")
        # recalc must scale gen by the integer-percent multiplier (0 -> 100 baseline)
        _check(re.search(r"MomMagicSchoolPct\s*\[\s*p\s*\]", mgcode) is not None
               and re.search(r"gen\s*=\s*gen\s*\*\s*pct\s*/\s*100", mgcode) is not None,
               "mom_magic.slc: MomRecalcMagicPerTurn must scale gen by MomMagicSchoolPct (gen*pct/100)")
        # each school branch pairs its numeric-index predicate with its own magic advance,
        # and the handler sets both Pct and Max (raising Max must NOT touch MomMagicCur)
        grant = mgcode[mgcode.find("MomMagicSchoolGrant"):] if "MomMagicSchoolGrant" in mgcode else ""
        for pred, adv in (("MomPlayerIsLife", "ADVANCE_LIFE_MAGIC"),
                          ("MomPlayerIsNature", "ADVANCE_NATURE_MAGIC"),
                          ("MomPlayerIsSorcery", "ADVANCE_SORCERY"),
                          ("MomPlayerIsDeath", "ADVANCE_DEATH_MAGIC"),
                          ("MomPlayerIsChaos", "ADVANCE_CHAOS_MAGIC")):
            _check(pred in grant and adv in grant,
                   f"mom_magic.slc: M2 grant handler missing {pred}/{adv} branch")
        _check(re.search(r"MomMagicSchoolPct\s*\[\s*p\s*\]\s*=", grant) is not None,
               "mom_magic.slc: M2 grant handler must assign MomMagicSchoolPct[p]")
        _check(re.search(r"MomMagicMax\s*\[\s*p\s*\]\s*=\s*(200|220|240|260|300)", grant) is not None,
               "mom_magic.slc: M2 grant handler must set MomMagicMax[p] to a school cap")
        _check(re.search(r"MomMagicCur\s*\[\s*p\s*\]\s*=[^=]", grant) is None,
               "mom_magic.slc: M2 grant handler must NOT assign MomMagicCur[p] (pool refills only on tick; reading it for the milestone popup is fine)")

        # --- M3 REGRESSION GUARD: the auto-summon must stay GONE ---
        # mom_magic.slc used to summon a creature whenever the pool filled. That
        # made mana free and the priced spellbook unaffordable by construction --
        # the pool could never sit at a level where a 75-mana working was
        # reachable. Summoning is now an ORDER placed from the menu and paid for
        # (mom_msg.slc), and the AI has its own brain (mom_ai_magic.slc).
        #
        # These assert the old design has not crept back, which is the opposite
        # of what this block used to check.
        _check(re.search(r"MomMagicCur\s*\[\s*p\s*\]\s*>=\s*MomMagicMax\s*\[\s*p\s*\]"
                         r"[^}]*MomSpawnSphereUnit", re.sub(r"\s+", " ", mgcode)) is None,
               "mom_magic.slc: a full pool triggers a summon again -- the "
               "auto-summon was removed because it made priced magic unaffordable")
        # A floor clamp (`if (MomMagicCur[p] < 0) { MomMagicCur[p] = 0; }`) is
        # correct and must stay; what must not return is zeroing the pool as the
        # PRICE of something. Only flag a zeroing with no `< 0` guard above it.
        for m in re.finditer(r"MomMagicCur\s*\[\s*p\s*\]\s*=\s*0\s*;", mgcode):
            preceding = mgcode[max(0, m.start() - 200):m.start()]
            _check("MomMagicCur[p] < 0" in preceding.replace(" ", "").replace(
                       "MomMagicCur[p]<0", "MomMagicCur[p] < 0"
                   ) or re.search(r"MomMagicCur\s*\[\s*p\s*\]\s*<\s*0", preceding) is not None,
                   "mom_magic.slc: the pool is zeroed outside a floor clamp -- "
                   "summons are DEBITED by price (mom_msg.slc), never emptied")
        _check(re.search(r"for\s*\([^)]*\)\s*\{[^}]*CreateUnit\s*\(", mgcode) is None,
               "mom_magic.slc: no CreateUnit inside a for-loop (summon-flood safety)")

        # --- M4 mana-node bonus (mom_magic.slc) ---
        _check(re.search(r"HasGood\s*\(", mgcode) is not None and re.search(r"GetNeighbor\s*\(", mgcode) is not None,
               "mom_magic.slc: M4 must scan tiles via base-verified HasGood + GetNeighbor")
        _check(re.search(r"nodes\s*=\s*nodes\s*\+\s*1", mgcode) is not None,
               "mom_magic.slc: M4 must count mana nodes (nodes = nodes + 1)")
        _check(re.search(r"gen\s*=\s*gen\s*\+\s*nodes\s*\*\s*5", mgcode) is not None,
               "mom_magic.slc: M4 must add MANA_NODE_BONUS (nodes*5) before school scaling")

    # --- every UNIT_/IMPROVE_/ADVANCE_ the modules reference is defined in its DB ---
    for pfx, dbfile in (("IMPROVE_", "buildings.txt"), ("UNIT_", "Units.txt"), ("ADVANCE_", "Advance.txt")):
        dbtext = (GD / dbfile).read_text(encoding="latin-1")
        defined = set(re.findall(rf"^({pfx}[A-Z_0-9]+) \{{", dbtext, re.M))
        for tok in set(re.findall(rf"\b({pfx}[A-Z_0-9]+)\b", code)):
            _check(tok in defined, f"module references {tok} not defined in {dbfile}")

    print("=" * 60)
    print("test_mom_slic — sphere-magic SLIC element lint")
    if not _failures:
        print(f"  ALL PASS — {len(SPHERES)} sphere element(s) verified: "
              + ", ".join(s["name"] for s in SPHERES))
        print("=" * 60)
        return 0
    print(f"  {len(_failures)} FAILURE(S):")
    for f in _failures:
        print(f"    [FAIL] {f}")
    print("=" * 60)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
