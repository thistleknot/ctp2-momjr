#!/usr/bin/env python
"""gate_mana_upkeep.py -- assert the mana economy actually tallies and deducts.

WHAT THIS EXISTS TO CATCH. Operator report 2026-08-01: a tribe fields one creature
type forever. The mechanism is that a summon costs 75 mana ONCE and nothing
afterwards, so mana has exactly one sink, that sink is repeatable, and an AI with
no other use for the pool accumulates a pile of identical rung-1 creatures. The
fix is an ongoing per-creature cost -- income MINUS upkeep -- which caps how many
creatures a tribe can SUSTAIN and pushes the rest of its army back into city
production.

That fix has three silent failure modes, and each assertion here targets one:

  * A creature that dies must stop being charged for. The ledger holds unit
    handles; if the scan does not clear a slot whose handle went invalid, the
    player is billed forever for a corpse and income decays to nothing with no
    visible cause. THIS IS THE WORST ONE -- it looks like balance, not a bug.
  * "Only summoned creatures pay" means the spawn helper must record WHICH
    creatures it made. A call site left at the old 2-argument arity compiles
    (SLIC auto-creates unknown symbols rather than erroring) and silently
    ledgers nothing, so that whole spend path becomes free.
  * Hard insolvency disbands creatures. An unbounded disband loop inside a
    BeginTurn handler can wipe an army in one tick and sits right next to the
    known AI end-turn stack-overflow class.

Assertions:
  1. The ledger arrays exist, are sized PLAYERS*SLOTS consistently, and are
     indexed with the matching stride.
  2. Every MomSpawnSphereUnit call site passes 3 arguments, and the definition
     accepts 3. Fails on the pre-fix tree at every call site.
  3. The upkeep scan clears the slot when the stored handle is not .valid.
     Fails on the pre-fix tree -- no scan exists at all.
  4. The disband path is bounded: KillUnit may not appear inside a loop in the
     magic tick.
  5. No user function called from a handler or button body itself calls another
     user function. This is the documented 0xC0000005 crash class, so it is
     asserted rather than reviewed.
  6. The AI summon branch tests sustainability (projected net income), not bare
     affordability. Otherwise the AI summons straight into insolvency and
     disbands what it just paid for.

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

PLAYERS = 5
SLOTS = 32
LEDGER_SIZE = PLAYERS * SLOTS

GAMEDATA = "default/gamedata"

# Every hand-authored MoM module. mom_gating.slc / mom_summon.slc are
# generator-emitted and carry no spawn call sites, but they are still scanned for
# the call-depth assertion because a handler there would crash the same way.
MODULES = [
    "mom_func.slc",
    "mom_magic.slc",
    "mom_msg.slc",
    "mom_spells.slc",
    "mom_city_effects.slc",
    "mom_ai_magic.slc",
    "mom_turns.slc",
    "mom_summon.slc",
    "mom_gating.slc",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="latin-1", errors="replace") if path.exists() else ""


def _strip_comments(text: str) -> str:
    """Drop // and /* */ comments -- the SLIC compiler never sees them.

    Load-bearing here: these modules carry long explanatory comments that name
    the very constructs being asserted on (KillUnit, MomSpawnSphereUnit), so
    without this the gate reports violations against prose.
    """
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def _sources(scen: Path) -> dict[str, str]:
    """module name -> comment-stripped source, for every module that exists."""
    out: dict[str, str] = {}
    for name in MODULES:
        path = scen / GAMEDATA / name
        if path.exists():
            out[name] = _strip_comments(_read(path))
    return out


def _split_args(arglist: str) -> list[str]:
    """Split a call's argument text on TOP-LEVEL commas only.

    A nested call -- MomSpawnSphereUnit(p, UnitDB(UNIT_X), r) -- would otherwise
    report 4 arguments and the arity assertion would fire on correct code.
    """
    args: list[str] = []
    depth = 0
    cur = ""
    for ch in arglist:
        if ch == "(":
            depth += 1
            cur += ch
        elif ch == ")":
            depth -= 1
            cur += ch
        elif ch == "," and depth == 0:
            args.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        args.append(cur.strip())
    return args


def _calls(src: str, fname: str) -> list[list[str]]:
    """Every call to fname in src, as its top-level argument list."""
    out: list[list[str]] = []
    for m in re.finditer(re.escape(fname) + r"\s*\(", src):
        start = m.end()
        depth = 1
        i = start
        while i < len(src) and depth:
            if src[i] == "(":
                depth += 1
            elif src[i] == ")":
                depth -= 1
            i += 1
        if depth == 0:
            out.append(_split_args(src[start:i - 1]))
    return out


def _func_bodies(src: str) -> dict[str, str]:
    """Declared user function name -> its body text."""
    out: dict[str, str] = {}
    for m in re.finditer(r"\b(?:int_f|void_f)\s+([A-Za-z_][A-Za-z_0-9]*)\s*\([^)]*\)\s*\{", src):
        name = m.group(1)
        start = m.end()
        depth = 1
        i = start
        while i < len(src) and depth:
            if src[i] == "{":
                depth += 1
            elif src[i] == "}":
                depth -= 1
            i += 1
        out[name] = src[start:i - 1]
    return out


def _entry_bodies(src: str) -> dict[str, str]:
    """HandleEvent and alertbox/messagebox button bodies -- the depth-0 roots."""
    out: dict[str, str] = {}
    pat = re.compile(
        r"HandleEvent\(\s*([A-Za-z_0-9]+)\s*\)\s*'([^']+)'\s*(?:pre|post)?\s*\{")
    for m in pat.finditer(src):
        label = f"HandleEvent({m.group(1)}) '{m.group(2)}'"
        start = m.end()
        depth = 1
        i = start
        while i < len(src) and depth:
            if src[i] == "{":
                depth += 1
            elif src[i] == "}":
                depth -= 1
            i += 1
        out[label] = src[start:i - 1]
    for m in re.finditer(r"\bbutton\s+'([^']+)'\s*\{", src):
        label = f"button '{m.group(1)}'"
        start = m.end()
        depth = 1
        i = start
        while i < len(src) and depth:
            if src[i] == "{":
                depth += 1
            elif src[i] == "}":
                depth -= 1
            i += 1
        out[label] = src[start:i - 1]
    return out


def _loop_spans(body: str) -> list[tuple[int, int]]:
    """Character spans of every for-loop body in `body`."""
    spans: list[tuple[int, int]] = []
    for m in re.finditer(r"\bfor\s*\(", body):
        i = m.end()
        depth = 1
        while i < len(body) and depth:
            if body[i] == "(":
                depth += 1
            elif body[i] == ")":
                depth -= 1
            i += 1
        while i < len(body) and body[i] in " \t\r\n":
            i += 1
        if i < len(body) and body[i] == "{":
            start = i + 1
            depth = 1
            i = start
            while i < len(body) and depth:
                if body[i] == "{":
                    depth += 1
                elif body[i] == "}":
                    depth -= 1
                i += 1
            spans.append((start, i - 1))
    return spans


# --------------------------------------------------------------------------
# assertions
# --------------------------------------------------------------------------

def _a1_ledger(srcs: dict[str, str]) -> list[str]:
    fails: list[str] = []
    func = srcs.get("mom_func.slc", "")
    decls = dict(re.findall(
        r"\b(?:unit_t|int_t)\s+(MomSummonUnit|MomSummonRung)\s*\[\s*(\d+)\s*\]", func))
    for name in ("MomSummonUnit", "MomSummonRung"):
        if name not in decls:
            fails.append(
                f"mom_func.slc: ledger array {name}[] is not declared -- "
                "'only summoned creatures pay upkeep' has nowhere to record "
                "which creatures were summoned")
        elif int(decls[name]) != LEDGER_SIZE:
            fails.append(
                f"mom_func.slc: {name}[{decls[name]}] should be "
                f"[{LEDGER_SIZE}] ({PLAYERS} players x {SLOTS} slots) -- a "
                "short array silently drops the tail players' creatures")
    if len(decls) == 2 and len({int(v) for v in decls.values()}) != 1:
        fails.append(
            "mom_func.slc: MomSummonUnit[] and MomSummonRung[] have DIFFERENT "
            "sizes -- the parallel arrays would desynchronise and bill one "
            "creature's upkeep against another's handle")
    stride = re.search(r"\*\s*(\d+)\s*\+", "".join(
        srcs.get(m, "") for m in ("mom_func.slc", "mom_magic.slc")))
    if decls and stride and int(stride.group(1)) != SLOTS:
        fails.append(
            f"ledger index stride is {stride.group(1)} but SLOTS is {SLOTS} -- "
            "players would overlap in the ledger")
    return fails


def _a2_spawn_arity(srcs: dict[str, str]) -> list[str]:
    fails: list[str] = []
    func = srcs.get("mom_func.slc", "")
    m = re.search(r"void_f\s+MomSpawnSphereUnit\s*\(([^)]*)\)", func)
    if not m:
        fails.append("mom_func.slc: MomSpawnSphereUnit is not declared")
    else:
        params = _split_args(m.group(1))
        if len(params) != 3:
            fails.append(
                f"mom_func.slc: MomSpawnSphereUnit takes {len(params)} "
                "parameter(s), needs 3 (player, unitType, rung) -- without the "
                "rung it cannot record what upkeep the creature owes")
    for name, src in srcs.items():
        body = src
        if name == "mom_func.slc":
            # skip the definition itself; only call sites are graded
            body = re.sub(r"void_f\s+MomSpawnSphereUnit\s*\([^)]*\)", "", body)
        for args in _calls(body, "MomSpawnSphereUnit"):
            if len(args) != 3:
                fails.append(
                    f"{name}: MomSpawnSphereUnit({', '.join(args)}) passes "
                    f"{len(args)} argument(s), needs 3 -- this spend path "
                    "ledgers nothing, so its creatures are free forever")
    return fails


def _a3_scan_frees_slot(srcs: dict[str, str]) -> list[str]:
    fails: list[str] = []
    magic = srcs.get("mom_magic.slc", "")
    if "MomSummonRung" not in magic:
        fails.append(
            "mom_magic.slc: no upkeep scan -- MomSummonRung[] is never read, so "
            "income is a bare tally with no deduction and summoning stays free")
        return fails
    has_valid = re.search(r"MomSummonUnit\s*\[[^\]]+\]\s*\.valid", magic)
    if not has_valid:
        fails.append(
            "mom_magic.slc: the upkeep scan never tests MomSummonUnit[..].valid "
            "-- dead creatures keep being billed and income decays with no "
            "visible cause")
        return fails
    # the slot must be cleared on the invalid branch
    if not re.search(r"MomSummonRung\s*\[[^\]]+\]\s*=\s*0", magic):
        fails.append(
            "mom_magic.slc: the upkeep scan never clears MomSummonRung[..] = 0 "
            "-- a slot whose creature died is never reclaimed, so the player is "
            "charged for a corpse for the rest of the game")
    return fails


def _a4_disband_bounded(srcs: dict[str, str]) -> list[str]:
    fails: list[str] = []
    magic = srcs.get("mom_magic.slc", "")
    if "KillUnit" not in magic:
        return fails
    for label, body in _entry_bodies(magic).items():
        spans = _loop_spans(body)
        for m in re.finditer(r"\bKillUnit\s*\(", body):
            for start, end in spans:
                if start <= m.start() < end:
                    fails.append(
                        f"mom_magic.slc {label}: KillUnit() sits INSIDE a loop "
                        "-- insolvency could disband an entire army in one "
                        "tick, and an unbounded kill loop in a BeginTurn "
                        "handler is adjacent to the known end-turn "
                        "stack-overflow crash class")
                    break
    return fails


def _a5_call_depth(srcs: dict[str, str]) -> list[str]:
    fails: list[str] = []
    all_funcs: dict[str, str] = {}
    for src in srcs.values():
        all_funcs.update(_func_bodies(src))
    names = set(all_funcs)
    for mod, src in srcs.items():
        for label, body in _entry_bodies(src).items():
            for callee in names:
                if not re.search(r"\b" + re.escape(callee) + r"\s*\(", body):
                    continue
                inner = all_funcs.get(callee, "")
                for deeper in names:
                    if deeper == callee:
                        continue
                    if re.search(r"\b" + re.escape(deeper) + r"\s*\(", inner):
                        fails.append(
                            f"{mod} {label}: calls {callee}(), which calls "
                            f"{deeper}() -- a 2-level user-function chain from "
                            "a handler or button body is the documented "
                            "0xC0000005 access violation")
    return fails


def _a5b_no_nested_arg_calls(srcs: dict[str, str]) -> list[str]:
    """A user function called in another user function's ARGUMENT position.

    Hit while writing this change: MomSpawnSphereUnit(p, pick, MomSummonRungOf(pick))
    reads as one statement but evaluates a user call inside another user call's
    frame, which is the ambiguous form of the 2-level chain that access-violates.
    Two sequential statements with a local in between are unambiguously depth 1,
    so the nested form is banned outright rather than reasoned about per case.
    """
    fails: list[str] = []
    all_funcs: dict[str, str] = {}
    for src in srcs.values():
        all_funcs.update(_func_bodies(src))
    names = set(all_funcs)
    for mod, src in srcs.items():
        for outer in names:
            for args in _calls(src, outer):
                for a in args:
                    for inner in names:
                        if re.search(r"\b" + re.escape(inner) + r"\s*\(", a):
                            fails.append(
                                f"{mod}: {outer}(...) takes {inner}(...) as an "
                                "argument -- resolve it into a local first; a "
                                "user call nested in another user call's "
                                "argument list is the ambiguous 2-level chain")
    return fails


def _a7_builtin_arg_types(srcs: dict[str, str]) -> list[str]:
    """Builtins whose ident argument must be a QUOTED STRING, not a bare ident.

    CAUGHT IN A RUNNING GAME, not by any static gate: the building tally shipped
    as CityHasBuilding(tmpCity, IMPROVE_TEMPLE) and the engine raised "In object
    MomRecalcMagicPerTurn, function _CityHasBuilding: Wrong type of argument" on
    turn 3. Every corpus call site passes a quoted string --
    CityHasBuilding(city[0], "IMPROVE_CAPITOL") -- and the bare form is a type
    error, not an auto-created symbol.

    This is the counterpart to the UnitDB()/AdvanceDB() convention, where the
    ident IS bare, which is exactly why the mistake was easy to make: the two
    families disagree, so the shape has to be asserted rather than remembered.
    """
    fails: list[str] = []
    for mod, src in srcs.items():
        for m in re.finditer(r"\bCityHasBuilding\s*\(([^)]*)\)", src):
            args = _split_args(m.group(1))
            if len(args) == 2 and not (args[1].startswith('"')
                                       and args[1].endswith('"')):
                fails.append(
                    f"{mod}: CityHasBuilding(..., {args[1]}) passes a bare "
                    "ident -- this builtin takes a QUOTED string and the bare "
                    'form is a runtime "Wrong type of argument", not a '
                    'compile error. Write "IMPROVE_X".')
    return fails


def _a6_ai_sustainability(srcs: dict[str, str]) -> list[str]:
    fails: list[str] = []
    ai = srcs.get("mom_ai_magic.slc", "")
    if not ai:
        return ["mom_ai_magic.slc is missing -- the AI has no magic brain"]
    if "MomMagicPerTurn" not in ai and "MomNet" not in ai:
        fails.append(
            "mom_ai_magic.slc: the summon branch tests only the pool balance, "
            "never projected net income -- under upkeep the AI summons into "
            "insolvency and disbands the creature it just bought")
    return fails


def check(scen: Path, csv_dir: Path | None = None) -> list[str]:
    """Return a list of violation strings; empty means the gate passes."""
    srcs = _sources(scen)
    if not srcs:
        return [f"no MoM SLIC modules found under {scen / GAMEDATA}"]
    fails: list[str] = []
    fails += _a1_ledger(srcs)
    fails += _a2_spawn_arity(srcs)
    fails += _a3_scan_frees_slot(srcs)
    fails += _a4_disband_bounded(srcs)
    fails += _a5_call_depth(srcs)
    fails += _a5b_no_nested_arg_calls(srcs)
    fails += _a6_ai_sustainability(srcs)
    fails += _a7_builtin_arg_types(srcs)
    return fails


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scenario", default=os.environ.get(
        "CTP2_GENERATOR_SCENARIO_DIR", str(DEFAULT_SCEN)))
    ap.add_argument("--csv-dir", default=os.environ.get(
        "CTP2_GENERATOR_CSV_DIR", str(HERE / "momjr_csv")))
    args = ap.parse_args()

    fails = check(Path(args.scenario), Path(args.csv_dir))
    for f in fails:
        print(f"FAIL {f}")
    if fails:
        print(f"\nmana upkeep gate: {len(fails)} violation(s).")
        return 1
    print(f"mana upkeep gate: ledger {PLAYERS}x{SLOTS}, spawn arity 3, scan "
          "reclaims dead slots, disband bounded, call depth <= 1 -- 0 violations")
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
