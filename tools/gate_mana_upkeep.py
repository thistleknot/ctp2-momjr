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


def _a8_disband_is_weighted(srcs: dict[str, str]) -> list[str]:
    """Insolvency must pick its victim by UPKEEP-WEIGHTED draw, not by position.

    Operator, 2026-08-01: "units that cost more are more likely to evaporate."
    The first cut released the NEWEST creature (last-in-first-out), which is
    positional: it frees whatever happens to sit highest in the ledger, so a
    tribe could shield an expensive creature by summoning a cheap one after it,
    and the pool recovers slowest exactly when it is most in deficit.

    Asserted rather than reviewed because a regression to positional selection
    is invisible in play -- both versions disband exactly one creature per turn
    and print the same message. Only the DISTRIBUTION differs.
    """
    fails: list[str] = []
    magic = srcs.get("mom_magic.slc", "")
    if "KillUnit" not in magic:
        return fails
    for label, body in _entry_bodies(magic).items():
        if "KillUnit" not in body:
            continue
        if not re.search(r"\bRandom\s*\(", body):
            fails.append(
                f"mom_magic.slc {label}: the disband path never calls Random() "
                "-- selection is positional, so an expensive creature can be "
                "shielded by summoning a cheap one after it")
        if not re.search(r"MomSummonRung\s*\[[^\]]+\]\s*;?\s*$", body, re.M) \
                and "insTotal" not in body and "Total" not in body:
            fails.append(
                f"mom_magic.slc {label}: the disband draw does not accumulate a "
                "weight total over MomSummonRung[] -- an unweighted draw makes "
                "a rung-1 Warbears as likely to go as a rung-5 Great Wyrm")
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


def _a9_preparation(srcs: dict[str, str]) -> list[str]:
    """Summon preparation: a countdown that must start, tick and CLEAR.

    Operator, 2026-08-01: "some summons should take more than a single turn to
    summon (preparation)". Committing mana starts a countdown equal to the
    creature's rung; the creature arrives when it expires.

    The failure modes are all silent, which is why they are asserted:

      * pending not cleared on arrival -> the creature respawns EVERY turn
        forever. An infinite free army, and the worst bug this machine can have.
      * the arrival branch not mutually exclusive with the commit branch -> a
        rung-1 creature commits and arrives in the same tick and preparation is
        invisible for exactly the tier most summons produce.
      * the AI re-committing while a creature is already on the way -> it pays 75
        every turn for one arrival, a mana leak that just looks like a poor AI.
      * the countdown seeded from something other than the rung -> the feature
        exists but does not scale, which no other check would notice.
    """
    fails: list[str] = []
    msg = srcs.get("mom_msg.slc", "")
    ai = srcs.get("mom_ai_magic.slc", "")
    func = srcs.get("mom_func.slc", "")

    for name in ("MomSummonPrep", "MomSummonPending", "MomSummonPendRung"):
        if not re.search(rf"\bint_t\s+{name}\s*\[\s*31\s*\]", func):
            fails.append(
                f"mom_func.slc: {name}[31] is not declared -- summon "
                "preparation has nowhere to keep its state")
    if not msg:
        return fails

    if not re.search(r"MomSummonPrep\s*\[\s*p\s*\]\s*=\s*MomSummonPendRung", msg):
        fails.append(
            "mom_msg.slc: the countdown is not seeded from the creature's rung "
            "-- preparation would not scale with creature power, which is the "
            "entire point of the mechanic")
    if not re.search(r"MomSummonPending\s*\[\s*p\s*\]\s*=\s*0", msg):
        fails.append(
            "mom_msg.slc: MomSummonPending[] is never cleared -- once a creature "
            "arrives it would respawn on EVERY later turn, an infinite free army")
    if not re.search(r"\belseif\s*\([^)]*MomSummonPrep\s*\[\s*p\s*\]\s*>\s*0", msg):
        fails.append(
            "mom_msg.slc: the arrival branch is not `elseif` against the commit "
            "branch -- a rung-1 creature would commit and arrive in the same "
            "tick and its preparation would never be visible")
    if not re.search(r"MomSummonPrep\s*\[\s*g\.player\s*\]\s*>\s*0", msg):
        fails.append(
            "mom_msg.slc: the summon button does not refuse a second order while "
            "one is preparing -- preparation becomes a queue rather than a plan")
    if ai and not re.search(r"MomSummonPrep\s*\[\s*p\s*\]\s*==\s*0", ai):
        fails.append(
            "mom_ai_magic.slc: the AI does not check MomSummonPrep before "
            "committing -- it would pay 75 every turn while a creature is "
            "already on the way, a silent mana leak")
    if ai and re.search(r"\bMomSpawnSphereUnit\s*\(", ai):
        fails.append(
            "mom_ai_magic.slc: the AI still spawns directly -- arrival must go "
            "through MomSummonOrderTick so one writer owns placement, ledgering "
            "and timing for both sides")
    return fails


def _a10_rate_is_one_knob(srcs: dict[str, str]) -> list[str]:
    """The upkeep rate must live in MomUpkeepRate and nowhere else.

    It was originally a bare `* 2` at three sites: the upkeep scan, the
    insolvency refund, and the AI's sustainability projection. Three copies of a
    balance constant is a drift hazard in the ordinary case, and specifically a
    correctness hazard in the AI's: if its projection used a different rate from
    the one actually charged, it would compute sustainability against a fiction
    and either starve itself or summon into a deficit.

    Consolidating also makes the rate patchable in ONE line, which is what lets
    tools/uiwalk/probe_insolvency.py reach a disband in a couple of turns on a
    shrunken rig instead of the couple of hundred a shipped-rate game needs.
    """
    fails: list[str] = []
    func = srcs.get("mom_func.slc", "")
    if not re.search(r"\bint_t\s+MomUpkeepRate\s*;", func):
        fails.append(
            "mom_func.slc: MomUpkeepRate is not declared -- the upkeep rate has "
            "no single home and cannot be retuned or patched in one place")
    magic = srcs.get("mom_magic.slc", "")
    if not re.search(r"MomUpkeepRate\s*==\s*0", magic):
        fails.append(
            "mom_magic.slc: MomUpkeepRate is never seeded -- SLIC globals start "
            "at 0, so every creature would be FREE and upkeep silently dead")
    # No bare rate left anywhere it is applied to a rung.
    for mod in ("mom_magic.slc", "mom_ai_magic.slc"):
        src = srcs.get(mod, "")
        for m in re.finditer(r"(MomSummonRung\s*\[[^\]]+\]|pickRung|summonRung)"
                             r"\s*\*\s*(\d+)", src):
            fails.append(
                f"{mod}: rung is multiplied by the literal {m.group(2)} rather "
                "than MomUpkeepRate -- a second copy of the rate that will drift")
    return fails


def _a11_cheap_spend_cannot_starve_summon(srcs: dict[str, str]) -> list[str]:
    """A cheaper AI spend must not starve the more expensive one.

    MEASURED 2026-08-01. The AI's war-chest working costs 50 and its summon
    costs 75, sharing one pool. At war the AI drained the pool at 50 every time
    it could, so it NEVER reached 75 and magic was structurally unreachable for a
    warring tribe -- Sorcery sat at 26 mana on turn 12 with zero creatures and no
    preparation pending, having converted everything to gold.

    Nothing dangled and no gate could see it: both branches were individually
    correct. The defect was only in their INTERACTION, which is why it is
    asserted structurally -- the cheap branch must carry a guard that keeps it
    from firing while a creature is still affordable.
    """
    fails: list[str] = []
    ai = srcs.get("mom_ai_magic.slc", "")
    if not ai:
        return fails
    # The cheap branch is the one that adds gold; find its condition.
    m = re.search(r"elseif\s*\(([^{]*?)\)\s*\{[^}]*AddGold", ai, re.S)
    if not m:
        return fails
    cond = m.group(1)
    if "MomMagicPerTurn" not in cond and "MomUpkeepRate" not in cond:
        fails.append(
            "mom_ai_magic.slc: the cheap gold working has no sustainability "
            "guard, so it fires whenever the pool passes ITS threshold and the "
            "AI can never save for the dearer summon -- the cheaper spend "
            "starves the more expensive one and magic becomes unreachable")
    return fails


def _a12_no_rung_floor(srcs: dict[str, str]) -> list[str]:
    """Summoning must require the research that building the same creature does.

    MEASURED 2026-08-02, and it is the defect behind "every Nature unit I meet is
    a Warbears". A Warbears costs 1970 science to BUILD (ADVANCE_NATURE_LORE) and
    used to cost 0 science to SUMMON, because MomSummonRoll floored the ladder
    rung at 1:

        if (r < 1) { r = 1; }

    So every tribe had rung-1 summoning from turn one and the summon path skipped
    the tech tree entirely. The tribe's only sphere-flavoured units were ones it
    could never have built.

    The floor was added in v3.2.0 against "a tribe that starts holding its sphere
    root never fires the GrantAdvance that would raise it off 0" -- a premise that
    is FALSE here: nothing in the scenario grants a *_MAGIC or *_LORE advance and
    there is no starting-advance mechanism, so no tribe ever starts holding its
    root. The floor guarded a case that does not exist and cost a whole tech gate.

    Rung 0 must fall through every band so MomSummonRoll returns 0, which every
    caller already reads as "no summon" and which leaves the pool undebited.
    """
    fails: list[str] = []
    summon = srcs.get("mom_summon.slc", "")
    if not summon:
        return fails
    if re.search(r"if\s*\(\s*r\s*<\s*1\s*\)", summon):
        fails.append(
            "mom_summon.slc: MomSummonRoll floors the rung at 1, so a tribe with "
            "NO magic research can still summon -- the summon bypasses the tech "
            "gate that building the same creature respects")
    # Rung 0 must own no band in any sphere.
    if re.search(r"if\s*\(\s*r\s*==\s*0\s*\)", summon):
        fails.append(
            "mom_summon.slc: a band exists for r == 0 -- rung 0 is 'no magic "
            "learned' and must yield no creature at all")
    return fails


def _a13_summon_price_scales(srcs: dict[str, str]) -> list[str]:
    """Assertion 13: the summon price scales with rung and is ONE expression.

    It was a flat 75 for every creature, so a 150-shield Phantom Warriors and a
    4000-shield Storm Drake cost the same -- a 27x swing in what the coin bought.
    Upkeep had scaled by rung since v3.5.0, so acquisition was the missing half:
    summoning was poor value at rung 1 and absurd value at rung 5.

    Now 45 + 30*rung -> 75/105/135/165/195. The ceiling is load-bearing: pools
    cap at Life 200 / Nature 220 / Sorcery 260 / Chaos 300, so a price above 200
    would put rung 5 permanently out of Life's reach.

    THE REAL RISK IS DIVERGENCE, not the formula. The human gate (mom_msg button
    body), the human debit (MomSummonOrderTick), the AI gate and the AI debit
    (mom_ai_magic) must all price the same creature the same way. When the two
    sides drifted on the UPKEEP rate the AI could afford what the player could
    not -- the defect assertion 10 exists for. This is that assertion for price.

    A bare `75` surviving anywhere on the summon path means one of the four sites
    was missed, which is exactly how a flat price comes back one site at a time.
    """
    fails: list[str] = []
    # The full expression, both dials: (45 + 30*rung) * civ percent / 100.
    # Matching only the rung half would let the civ scale be dropped from one
    # site while the gate still passed -- and a gate that a partial edit slips
    # through is the same shape as the flat rate it replaced.
    price = re.compile(r"45\s*\+\s*30\s*\*")
    civ = re.compile(r"MomSummonCivPct\[")
    for mod, what in (("mom_msg.slc", "human"), ("mom_ai_magic.slc", "AI")):
        src = srcs.get(mod, "")
        if not src:
            continue
        body = re.sub(r"//[^\r\n]*", "", src)
        if len(civ.findall(body)) < len(price.findall(body)):
            fails.append(
                f"{mod}: the {what} path applies the rung curve at more sites than "
                "it applies MomSummonCivPct -- every price must carry BOTH dials, "
                "or one civ silently pays the unscaled base curve")
        if len(price.findall(body)) < 2:
            fails.append(
                f"{mod}: the {what} path should price a summon with the shared "
                "'45 + 30 * rung' expression at BOTH its gate and its debit -- "
                "fewer than two occurrences means one site still charges a flat "
                "rate, and gate and debit disagreeing is how a click gets "
                "accepted and then silently refused")
        for m in re.finditer(r"MomMagicCur\[[^\]]+\]\s*(?:>=|-)\s*75\b", body):
            fails.append(
                f"{mod}: `{m.group(0)}` is a flat 75 on the summon path -- price "
                "must derive from the rung (45 + 30 * rung), or a rung-5 creature "
                "costs what a rung-1 creature costs")
    return fails


def _a14_fixed_anchor(srcs: dict[str, str]) -> list[str]:
    """Assertion 14: the mana subsystem obeys specs/fixed-anchor-scaling.md.

    ONE value is held constant -- the 200 pool -- and every other number is
    expressed against it. The point is identifiability before balance: if the
    pool may vary AND prices may vary, then (pool x k, prices x k) is the same
    game, so the parameter space has a direction along which nothing observable
    changes. That free parameter cannot be measured and makes two runs
    incomparable. The anchor is the reference level that removes it.

    Four checks, each a defect this mod actually shipped:

      1. ONE anchor, identical for every civ. Caps used to run 200/220/260/240/
         300, which handed the price ceiling to whichever civ had the smallest.
      2. No price exceeds anchor * headroom, so a civ's own best creature is
         never priced out of its own pool.
      3. Every civ can afford its own maximum -- a price a peer cannot reach is
         a feature deleted for that peer, silently.
      4. NO TWO DIALS MAY RANK THE CIVS THE SAME WAY. Independent dials add;
         correlated dials multiply. Pool capacity and the generation multiplier
         used to rank the civs identically, so Chaos held 50% more mana AND
         earned 40% faster -- neither number looking wrong on its own.
    """
    ANCHOR, HEADROOM, RUNGS = 200, 0.90, 5
    fails: list[str] = []
    src = srcs.get("mom_magic.slc", "")
    if not src:
        return fails
    civs = ["Life", "Nature", "Sorcery", "Death", "Chaos"]

    def dial(key: str) -> dict[str, int]:
        out = {}
        for c in civs:
            m = re.search(rf"MomPlayerIs{c}\(p\).*?{key}\[p\] = (\d+);", src, re.S)
            if m:
                out[c] = int(m.group(1))
        return out

    cap, gen, price = dial("MomMagicMax"), dial("MomMagicSchoolPct"), dial("MomSummonCivPct")
    if len(cap) == len(civs) and set(cap.values()) != {ANCHOR}:
        fails.append(
            f"mom_magic.slc: the mana pool is the ANCHOR and must be {ANCHOR} for "
            f"every civ, found {cap} -- a per-civ anchor hands the price ceiling "
            "to the smallest one and makes runs incomparable")
    if len(price) == len(civs):
        top = max(((45 + 30 * RUNGS) * p) // 100 for p in price.values())
        if top > ANCHOR * HEADROOM:
            fails.append(
                f"mom_magic.slc: dearest summon {top} exceeds anchor*headroom "
                f"{int(ANCHOR * HEADROOM)} -- recompress the map, do not raise the anchor")
        for c, p in price.items():
            if ((45 + 30 * RUNGS) * p) // 100 > ANCHOR:
                fails.append(
                    f"mom_magic.slc: {c} cannot afford its own rung-5 creature within "
                    f"the {ANCHOR} pool -- that feature is deleted for {c}")
    if len(gen) == len(civs) and len(price) == len(civs):
        xs = [sorted(price.values()).index(price[c]) for c in civs]
        ys = [sorted(gen.values()).index(gen[c]) for c in civs]
        n = len(civs)
        mx, my = sum(xs) / n, sum(ys) / n
        den = ((sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)) ** 0.5)
        r = (sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den) if den else 0.0
        if abs(r) >= 0.6:
            fails.append(
                f"mom_magic.slc: the price and generation dials rank the civs the same "
                f"way (Spearman {r:+.2f}) -- correlated dials compound into a dominant "
                "tribe instead of adding")
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
    fails += _a8_disband_is_weighted(srcs)
    fails += _a9_preparation(srcs)
    fails += _a10_rate_is_one_knob(srcs)
    fails += _a11_cheap_spend_cannot_starve_summon(srcs)
    fails += _a12_no_rung_floor(srcs)
    fails += _a13_summon_price_scales(srcs)
    fails += _a14_fixed_anchor(srcs)
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
