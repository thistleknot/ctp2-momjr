"""Post-generation scenario validator — the gate between generator and playtest.

Purpose:
    Catch the failure classes that otherwise surface as in-game Database Error
    dialogs or silent exits, for ANY generated scenario (scenario dir is a
    parameter, unlike mom_audit which is MoM-rooted):

      1. newsprite.txt grammar   — every entry must be NAME <int> with a clean
                                   [A-Z0-9_] identifier ("Expected integer").
      2. identifier charset      — DefaultSprite/DefaultIcon values and block
                                   idents in Units.txt must be [A-Za-z0-9_].
      3. reserved engine tokens  — no UNIT_/ADVANCE_/IMPROVE_ ident or gl_str
                                   id may equal a tokenizer keyword
                                   (engine_reserved_tokens.txt; UNIT_SPRITE
                                   crash class -> "Missing string id" exit).
      4. gl_str.txt grammar      — every non-empty line is ID "text".

Usage:
    validate_scenario.py --scenario <scen0000 dir>

Exit codes: 0 = all gates pass; 1 = failures listed on stdout.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent

IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
NEWSPRITE_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s+(\d+)\s*$")
GL_STR_RE = re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s+"([^"]*)"\s*$')


def check_newsprite(scen: Path, fails: list[str]) -> None:
    path = scen / "default/gamedata/newsprite.txt"
    if not path.exists():
        return
    for i, line in enumerate(path.read_text(encoding="latin-1").splitlines(), 1):
        if not line.strip() or line.strip().startswith("#"):
            continue
        if not NEWSPRITE_RE.match(line):
            fails.append(f"newsprite.txt:{i}: bad entry {line.strip()!r}")


def check_units_idents(scen: Path, fails: list[str]) -> set[str]:
    path = scen / "default/gamedata/Units.txt"
    idents: set[str] = set()
    if not path.exists():
        return idents
    text = path.read_text(encoding="latin-1")
    for m in re.finditer(r"^(UNIT_\S+)\s*\{", text, re.M):
        ident = m.group(1)
        idents.add(ident)
        if not IDENT_RE.match(ident):
            fails.append(f"Units.txt: malformed unit ident {ident!r}")
    for key in ("DefaultSprite", "DefaultIcon"):
        for m in re.finditer(rf"{key}\s+(\S+)", text):
            if not IDENT_RE.match(m.group(1)):
                fails.append(f"Units.txt: malformed {key} {m.group(1)!r}")
    return idents


def check_reserved(scen: Path, unit_idents: set[str], fails: list[str]) -> None:
    reserved_path = TOOLS_DIR / "engine_reserved_tokens.txt"
    if not reserved_path.exists():
        return
    reserved = set(reserved_path.read_text(encoding="utf-8").split())

    hits = sorted(unit_idents & reserved)
    for h in hits:
        fails.append(f"Units.txt: ident {h} is an engine tokenizer keyword")

    gl = scen / "english/gamedata/gl_str.txt"
    if gl.exists():
        ids = set(re.findall(r"^([A-Za-z_][A-Za-z0-9_]*)",
                             gl.read_text(encoding="latin-1"), re.M))
        for h in sorted(ids & reserved):
            fails.append(f"gl_str.txt: id {h} is an engine tokenizer keyword")


def check_string_refs(scen: Path, fails: list[str]) -> None:
    """Referential integrity: every Description id in the gamedata DBs must
    resolve in gl_str — a dangling ref is 'Expected string ID' + game exit."""
    gl = scen / "english/gamedata/gl_str.txt"
    if not gl.exists():
        return
    ids = set(re.findall(r"^([A-Za-z_][A-Za-z0-9_]*)",
                         gl.read_text(encoding="latin-1"), re.M))
    for rel in ("default/gamedata/buildings.txt",
                "default/gamedata/Units.txt",
                "default/gamedata/Wonder.txt",
                "default/gamedata/Advance.txt"):
        path = scen / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="latin-1")
        for m in re.finditer(r"Description\s+([A-Za-z_][A-Za-z0-9_]*)", text):
            if m.group(1) not in ids:
                fails.append(f"{Path(rel).name}: Description {m.group(1)} "
                             f"has no gl_str entry (Expected-string-ID crash)")


def check_icon_refs(scen: Path, fails: list[str]) -> None:
    """Icon-DB integrity: every DefaultIcon/Icon ref must exist in its icon
    database ('X not found in Icon database' dialog class)."""
    # The runtime Icon database is uniticon.txt for BOTH unit and building
    # (improve) icons — civapp.cpp g_theIconDB->Parse(g_uniticondb_filename).
    # improveicon.txt / wondericon.txt are separate exports the engine does NOT
    # consult for DefaultIcon resolution, so they are not the lookup source.
    lanes = (
        ("default/gamedata/buildings.txt", r"DefaultIcon\s+(ICON_IMPROVE_[A-Z0-9_]+)",
         "default/gamedata/uniticon.txt"),
        ("default/gamedata/Units.txt", r"DefaultIcon\s+(ICON_UNIT_[A-Z0-9_]+)",
         "default/gamedata/uniticon.txt"),
        ("default/gamedata/Wonder.txt", r"Icon\s+(ICON_WONDER_[A-Z0-9_]+)",
         "default/gamedata/uniticon.txt"),
        # Advance.txt was the blind spot: the advance-deletion prune drops any
        # ICON_ADVANCE_* line whose ident is not a live advance, which ate the
        # engine's fallback ICON_ADVANCE_DEFAULT (referenced by the ADVANCE_NA
        # sentinel, not by any advance record). The scenario then died at load on
        # a native "DB Error" modal that no static gate could see.
        ("default/gamedata/Advance.txt", r"Icon\s+(ICON_ADVANCE_[A-Z0-9_]+)",
         "default/gamedata/uniticon.txt"),
    )
    for src_rel, pattern, db_rel in lanes:
        src, db = scen / src_rel, scen / db_rel
        if not src.exists() or not db.exists():
            continue
        refs = set(re.findall(pattern, src.read_text(encoding="latin-1")))
        # uniticon is block-format: "ICON_X { ... }" — match block idents.
        ids = set(re.findall(r"^\s*(ICON_[A-Z0-9_]+)\s*\{",
                             db.read_text(encoding="latin-1"), re.M))
        for missing in sorted(refs - ids):
            # Retired X-sentinels (IMPROVE_X*/WONDER_X*) are CantBuild and
            # obsolete from turn 1 — their icons are never looked up, and the
            # known-working MoM baseline ships exactly this state.
            if re.match(r"ICON_(IMPROVE|WONDER)_X[A-Z]", missing):
                continue
            fails.append(f"{Path(src_rel).name}: {missing} not in "
                         f"{Path(db_rel).name} (Icon-database crash)")


def check_advance_prereq_cap(scen: Path, fails: list[str]) -> None:
    """No advance may exceed k_MAX_Prerequisites (4, AdvanceRecord.h) — a 5th
    entry triggers 'Advance.txt:N too many entries' at parse."""
    path = scen / "default/gamedata/Advance.txt"
    if not path.exists():
        return
    text = path.read_text(encoding="latin-1")
    for m in re.finditer(r"^(ADVANCE_\w+) \{(.*?)^\}", text, re.M | re.S):
        n = len(re.findall(r"^\s*Prerequisites\s+", m.group(2), re.M))
        if n > 4:
            fails.append(f"Advance.txt: {m.group(1)} has {n} Prerequisites "
                         f"(max 4 — 'too many entries' crash)")


def check_visible_art(scen: Path, fails: list[str]) -> None:
    """Every VISIBLE advance/unit should have real art, not the UPLG001
    placeholder (grey box). Hidden (GLHidden/NoIndex) entities on the
    placeholder are fine — the base game ships them that way."""
    uni_path = scen / "default/gamedata/uniticon.txt"
    if not uni_path.exists():
        return
    uni = uni_path.read_text(encoding="latin-1")
    placeholder = set(re.findall(
        r"^(ICON_(?:ADVANCE|UNIT)_\w+) \{[^}]*UPLG001", uni, re.M))
    for src_rel, prefix, icon_prefix in (
        ("default/gamedata/Advance.txt", "ADVANCE_", "ICON_ADVANCE_"),
        ("default/gamedata/Units.txt", "UNIT_", "ICON_UNIT_"),
    ):
        path = scen / src_rel
        if not path.exists():
            continue
        text = path.read_text(encoding="latin-1")
        for m in re.finditer(rf"^({prefix}\w+) \{{(.*?)^\}}", text, re.M | re.S):
            body = m.group(2)
            if "GLHidden" in body or "NoIndex" in body:
                continue
            icon_id = icon_prefix + m.group(1)[len(prefix):]
            if icon_id in placeholder:
                fails.append(f"{Path(src_rel).name}: visible {m.group(1)} on "
                             f"UPLG001 placeholder (no real/proxy art)")


def check_buildlist_refs(scen: Path, fails: list[str]) -> None:
    """Every Building/Unit ref in the AI build lists must exist in its DB — a
    dangling ref is 'X not found in Building/Unit database' + game exit."""
    checks = (
        ("default/aidata/BuildingBuildLists.txt", r"Building\s+(IMPROVE_\w+)",
         "default/gamedata/buildings.txt", r"^(IMPROVE_\w+)\s*\{"),
        ("default/aidata/UnitBuildLists.txt", r"Unit\s+(UNIT_\w+)",
         "default/gamedata/Units.txt", r"^(UNIT_\w+)\s*\{"),
    )
    for list_rel, ref_re, db_rel, db_re in checks:
        lst, db = scen / list_rel, scen / db_rel
        if not lst.exists() or not db.exists():
            continue
        refs = set(re.findall(ref_re, lst.read_text(encoding="latin-1")))
        ids = set(re.findall(db_re, db.read_text(encoding="latin-1"), re.M))
        for missing in sorted(refs - ids):
            fails.append(f"{Path(list_rel).name}: {missing} not in "
                         f"{Path(db_rel).name} (build-list dangling ref crash)")


def check_city_unit_coverage(scen: Path, fails: list[str]) -> None:
    """There must be a HasPopAndCanBuild city unit reachable on BOTH land and
    sea. unitutil_GetLandCity/GetSeaCity scan for a unit with the pop flag +
    the matching MovementType; if none exists they return index 0 (a flagless
    unit) -> CreateCity makes a non-city -> null CityData -> AV when a city is
    founded on that terrain (the coastal-settle crash)."""
    path = scen / "default/gamedata/Units.txt"
    if not path.exists():
        return
    text = path.read_text(encoding="latin-1")
    land = sea = False
    for m in re.finditer(r"^UNIT_\w+ \{(.*?)^\}", text, re.M | re.S):
        b = m.group(1)
        if "HasPopAndCanBuild" not in b:
            continue
        if re.search(r"MovementType:?\s+Land", b):
            land = True
        if re.search(r"MovementType:?\s+Sea", b):
            sea = True
    if not land:
        fails.append("Units.txt: no HasPopAndCanBuild unit with MovementType Land "
                     "(land-settle crash: GetLandCity returns index 0)")
    if not sea:
        fails.append("Units.txt: no HasPopAndCanBuild unit with MovementType Sea "
                     "(coastal-settle crash: GetSeaCity returns index 0)")


def check_gl_str(scen: Path, fails: list[str]) -> None:
    path = scen / "english/gamedata/gl_str.txt"
    if not path.exists():
        return
    for i, line in enumerate(path.read_text(encoding="latin-1").splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("//"):
            continue
        if not GL_STR_RE.match(line):
            fails.append(f"gl_str.txt:{i}: bad entry {s[:70]!r}")


def check_faction_gating(scen: Path, fails: list[str]) -> None:
    """Gate 10: the five tribes get different things and the wall has no holes.

    Delegates to gate_faction_gating.audit, which borrows its predicate from
    ctp2_generator -- the writer owns the policy, so the wall and the prereq
    rewrite cannot drift apart. Skipped (not failed) when the generator is not
    importable, because this validator is scenario-generic and MoM's control
    plane is not guaranteed to be alongside it.
    """
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        import gate_faction_gating as F
    except Exception:
        return
    fails.extend(F.audit(scen))


def check_ai_magic(scen: Path, fails: list[str]) -> None:
    """Gate 26: the summon ladder varies and the AI can actually spend mana.

    Delegates to gate_ai_magic.check. Skipped (not failed) when that module or
    the control plane is not importable, matching check_faction_gating -- this
    validator is scenario-generic and MoM's csv dir is not guaranteed alongside.

    Both defects this covers were invisible to every other gate because nothing
    dangled: the summon resolved through five per-sphere CONSTANTS, and AI tribes
    accrued mana they could never spend because the only authorisation was set in
    a button body. Reference integrity cannot see either.
    """
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        import gate_ai_magic as A
    except Exception:
        return
    fails.extend(A.check(scen, _momjr_csv()))


def _momjr_csv() -> Path:
    return TOOLS_DIR / "momjr_csv"


def _advance_blocks(scen: Path) -> dict[str, list[str]]:
    """ident -> its Prerequisites values, parsed from the generated Advance.txt."""
    path = scen / "default/gamedata/Advance.txt"
    if not path.exists():
        return {}
    blocks: dict[str, list[str]] = {}
    cur = None
    for line in path.read_text(encoding="latin-1", errors="replace").splitlines():
        s = line.strip()
        m = re.match(r"^(ADVANCE_[A-Za-z0-9_]+)\s*\{", s)
        if m:
            cur = m.group(1)
            blocks[cur] = []
            continue
        if s.startswith("}"):
            cur = None
            continue
        if cur:
            p = re.match(r"^Prerequisites\s+([A-Za-z0-9_]+)", s)
            if p:
                blocks[cur].append(p.group(1))
    return blocks


def check_disabled_advances_closed(scen: Path, fails: list[str]) -> None:
    """Gate 18: an advance civ2 marked `no` must never ship researchable.

    `nil` and `no` are OPPOSITE sentinels in civ2 Rules.txt -- `nil` = no
    prerequisite (a researchable root), `no` = never available. Collapsing them
    once shipped ADVANCE_GLYPHS as a free AGE_ONE root. CTP2's disable idiom is
    the self-prerequisite (Advances.cpp::ResetCanResearch forces
    canResearch=FALSE) with the block still in the DB so references resolve.

    Require: advances.csv alongside this tool and a generated Advance.txt.
    Guarantee: every disabled row's block lists ITSELF as a prerequisite.
    The predicate is imported from ctp2_generator so the gate cannot disagree
    with the writer about what "disabled" means.
    """
    csv_path = _momjr_csv() / "advances.csv"
    if not csv_path.exists():
        return
    try:
        sys.path.insert(0, str(TOOLS_DIR))
        from ctp2_generator import _advance_row_is_disabled, sanitize
    except Exception:
        return
    blocks = _advance_blocks(scen)
    if not blocks:
        return
    import csv as _csv
    with csv_path.open(newline="", encoding="utf-8-sig") as fh:
        for row in _csv.DictReader(fh):
            name = (row.get("name") or "").split(";")[0].strip()
            if not name or not _advance_row_is_disabled(row):
                continue
            ident = f"ADVANCE_{sanitize(name)}"
            if ident not in blocks:
                continue
            if ident not in blocks[ident]:
                fails.append(f"Advance.txt: {ident} is disabled in advances.csv "
                             f"(`no` prerequisite) but ships researchable -- "
                             f"prereqs {blocks[ident] or 'NONE'}")


def check_advance_code_map(scen: Path, fails: list[str]) -> None:
    """Gate 19: every civ2 short code resolves to a live advance.

    advance_code_map.csv carries two lanes, `prereq` and `unit`, which disagree
    ON PURPOSE (the prereq lane holds stock-CTP2 names for several codes).
    Consumers try `prereq` first and fall through to `unit` when the target is
    absent or disabled, so a code is only broken when NEITHER lane lands on an
    advance that exists and is researchable.

    Scoped to codes a consumer actually CITES as a prerequisite. An uncited map
    row whose only target is deliberately disabled (`FP` -> ADVANCE_GLYPHS) is
    dead weight, not a defect; flagging it would train the operator to ignore
    this gate. A cited code that cannot resolve, by contrast, silently falls
    back to ADVANCE_WARRIOR_CODE and ships the wrong tech tree.

    Require: advance_code_map.csv alongside this tool, generated Advance.txt.
    Guarantee: no CITED code is left without a resolvable target.
    """
    csv_path = _momjr_csv() / "advance_code_map.csv"
    if not csv_path.exists():
        return
    blocks = _advance_blocks(scen)
    if not blocks:
        return
    import csv as _csv
    # The three consumers do NOT share a prereq schema: advances.csv carries the
    # civ2 two-slot pair (prereq1/prereq2), units.csv and improvements.csv carry a
    # single `prereq`. Reading the wrong column name yields an empty set and a
    # gate that silently checks nothing, so derive the columns from the header
    # instead of hardcoding one shape.
    cited: set[str] = set()
    for consumer in ("units.csv", "improvements.csv", "advances.csv"):
        cpath = _momjr_csv() / consumer
        if not cpath.exists():
            continue
        with cpath.open(newline="", encoding="utf-8-sig") as fh:
            reader = _csv.DictReader(fh)
            # Exact names only. A substring match on "prereq" also catches
            # `prereq_str`, which holds Great Library STRING KEYS
            # (ADVANCE_X_PREREQ), not civ2 codes -- the same string-key-as-ident
            # confusion that once produced a bogus 619-dangling-ref report.
            cols = [c for c in (reader.fieldnames or [])
                    if c in ("prereq", "prereq1", "prereq2")]
            if not cols:
                fails.append(f"{consumer}: no prerequisite column -- the code-map "
                             f"gate cannot see this consumer")
                continue
            for row in reader:
                for col in cols:
                    v = (row.get(col) or "").split(";")[0].strip()
                    if v and v not in ("nil", "no"):
                        cited.add(v)

    lanes: dict[str, dict[str, str]] = {}
    with csv_path.open(newline="", encoding="utf-8-sig") as fh:
        for row in _csv.DictReader(fh):
            lane = (row.get("lane") or "").strip()
            code = (row.get("code") or "").strip()
            adv = (row.get("advance") or "").strip()
            if lane and code and adv:
                lanes.setdefault(code, {})[lane] = adv

    def live(ident: str) -> bool:
        return ident in blocks and ident not in blocks[ident]

    for code in sorted(cited):
        targets = lanes.get(code)
        if not targets:
            fails.append(f"advance_code_map.csv: code {code!r} is cited as a "
                         f"prerequisite but has no row in either lane")
            continue
        if any(live(t) for t in targets.values()):
            continue
        shown = ", ".join(f"{k}={v}" for k, v in sorted(targets.items()))
        fails.append(f"advance_code_map.csv: code {code!r} has no live target "
                     f"in either lane ({shown})")


def check_disabled_entities_unbuildable(scen: Path, fails: list[str]) -> None:
    """Gate 20: nothing civ2 marks `no` ships buildable.

    `no` is the OPPOSITE of `nil` (see check_disabled_advances_closed): `nil`
    means "no prerequisite", `no` means "never available". The unit and
    improvement lanes collapsed both into the ADVANCE_WARRIOR_CODE fallback,
    which is researched on turn one -- `Coastal Fortress` shipped as a turn-one
    buildable though civ2 marks it unavailable.

    Require: units.csv / improvements.csv alongside this tool, and a generated
    Advance.txt plus the file the entity ships in.
    Guarantee: every `no`-prereq row either does not ship at all, or ships gated
    on an advance closed by self-prerequisite.

    The gate reads the SHIPPED EnableAdvance rather than trusting the generator,
    so a future emitter that reintroduces the union bug fails here even if its
    own predicate says otherwise.
    """
    blocks = _advance_blocks(scen)
    if not blocks:
        return
    disabled = {a for a, prereqs in blocks.items() if a in prereqs}

    import csv as _csv
    try:
        sys.path.insert(0, str(TOOLS_DIR))
        from ctp2_generator import sanitize
    except Exception:
        return

    lanes = (("units.csv", "UNIT_", "default/gamedata/Units.txt"),
             ("improvements.csv", "IMPROVE_", "default/gamedata/buildings.txt"))
    for fname, prefix, rel in lanes:
        csv_path = _momjr_csv() / fname
        target = scen / rel
        if not csv_path.exists() or not target.exists():
            continue
        text = target.read_text(encoding="latin-1", errors="replace")
        gates: dict[str, str] = {}
        cur = None
        for line in text.splitlines():
            s = line.strip()
            m = re.match(rf"^({prefix}[A-Za-z0-9_]+)\s*\{{", s)
            if m:
                cur = m.group(1)
                gates[cur] = ""
                continue
            if s.startswith("}"):
                cur = None
                continue
            if cur:
                e = re.match(r"^EnableAdvance\s+([A-Za-z0-9_]+)", s)
                if e:
                    gates[cur] = e.group(1)
        with csv_path.open(newline="", encoding="utf-8-sig") as fh:
            reader = _csv.DictReader(fh)
            if "prereq" not in (reader.fieldnames or []):
                fails.append(f"{fname}: no `prereq` column -- the disabled-entity "
                             f"gate cannot see this lane")
                continue
            for row in reader:
                if (row.get("prereq") or "").split(";")[0].strip() != "no":
                    continue
                name = (row.get("name") or "").split(";")[0].strip()
                if not name:
                    continue
                ident = f"{prefix}{sanitize(name)}"
                if ident not in gates:
                    continue  # does not ship at all -- fine
                gate = gates[ident]
                if gate and gate in disabled:
                    continue
                fails.append(f"{rel}: {ident} is `no` (never available) in "
                             f"{fname} but ships buildable -- "
                             f"EnableAdvance {gate or 'NONE'}")


def check_wonder_articles(scen: Path, fails: list[str]) -> None:
    """Gate 25: every wonder has the `_ARTICLE` string its messages interpolate.

    Require: generated Wonder.txt and english/gamedata/gl_str.txt.
    Guarantee: every WONDER_* block has a `<IDENT>_ARTICLE` key, and no
      `_ARTICLE` key survives whose wonder is gone.

    `#ARTICLE` is an IDENT-SUFFIX LOOKUP, not a computed article: the engine
    resolves `{wonder[0].name#ARTICLE}` by reading `<IDENT>_ARTICLE` out of
    gl_str.txt, and falls back to the NAME when the key is missing. Eleven
    messages in ctp2_data/english/gamedata/info_str.txt are written as two
    adjacent interpolations --

        WONDER_STARTED "... has begun work on {wonder[0].name#ARTICLE}{wonder[0].name}."

    -- so a missing key renders the name TWICE with nothing between it:
    `Bardic CollegeBardic College`, observed in-game 2026-07-28. Affected:
    WONDER_BUILT, WONDER_BUILT_QUEUE_EMPTY, WONDER_STARTED, WONDER_STOPPED,
    WONDER_ALMOST_FINISHED, WONDER_COMPLETE_OWNER, WONDER_COMPLETE_ALL,
    WONDER_DESTROYED, WONDER_OBSOLETE, NANITE_DEFUSER_ELIMINATES_NUKES,
    PROTECTED_FROM_CONVERSION_BY_WONDER.

    The base tree ships 30 of these keys and wonders are the ONLY database that
    uses the modifier. MoM's gl_str.txt overrides the base file and shipped ZERO,
    because two independent lanes were broken: _prune_gl_strings deleted every
    inherited key (a trailing `_ARTICLE` never matched a keep_id), and the wonder
    writer never emitted MoM's own. Fixing either alone leaves the bug, which is
    why this gate asserts the RESULT rather than either lane.
    """
    wonder_txt = scen / "default/gamedata/Wonder.txt"
    gl_str = scen / "english/gamedata/gl_str.txt"
    if not wonder_txt.exists() or not gl_str.exists():
        return

    wonders = set(re.findall(
        r"^(WONDER_[A-Z0-9_]+)\s*\{",
        wonder_txt.read_text(encoding="latin-1", errors="replace"), re.M))
    keys = set(re.findall(
        r"^(\w+)\s+\"",
        gl_str.read_text(encoding="latin-1", errors="replace"), re.M))

    for ident in sorted(wonders):
        if f"{ident}_ARTICLE" not in keys:
            fails.append(
                f"gl_str.txt: {ident} has no {ident}_ARTICLE key -- every "
                "wonder message will print its name twice")
    for key in sorted(k for k in keys if k.endswith("_ARTICLE")):
        if key[:-len("_ARTICLE")] not in wonders:
            fails.append(
                f"gl_str.txt: {key} has no matching block in Wonder.txt")

    # The civ2 `x` DISABLED SENTINEL must never reach the scenario. MOMJR writes
    # a retired entry as `xLighthouse, 20, 0, no,` -- the x prefix AND the `no`
    # never-buildable prereq -- and neither lane excluded it, so five stock CTP2
    # wonders shipped with the sentinel baked into the DISPLAY NAME. This is not
    # cosmetic-internal: the Great Library's Warrior Code page listed "Xapollo
    # Program, Xcure For Cancer, Xlighthouse, Xstatue Of Liberty and Xwomens
    # Suffrage" to the player as wonders it enables (measured in-game
    # runs/20260729-174823). Culled at the control plane 2026-07-29, 28 -> 23.
    for ident in sorted(wonders):
        stem = ident[len("WONDER_"):]
        if re.match(r"^X[A-Z]", stem):
            fails.append(
                f"Wonder.txt: {ident} carries the civ2 `x` disabled sentinel -- "
                "it was marked `no` (never buildable) in the source and must be "
                "culled from wonders.csv, not shipped")
    for ident, name in re.findall(r"^(WONDER_[A-Z0-9_]+)\s+\"([^\"]+)\"", gl_str.read_text(
            encoding="latin-1", errors="replace"), re.M):
        if re.match(r"^X[a-zA-Z]", name) and ident in wonders:
            fails.append(
                f"gl_str.txt: {ident} display name {name!r} starts with the civ2 "
                "`x` disabled sentinel")


def check_wonder_build_lists(scen: Path, fails: list[str]) -> None:
    """Gate 24: the AI's wonder lists cover every live wonder and nothing else.

    Require: generated Wonder.txt and aidata/WonderBuildLists.txt.
    Guarantee: every ident in the lists is a Wonder.txt block; no self-obsoleting
      sentinel is offered; every live wonder appears in at least one list; and
      the EndGameObjects wonder is among them.

    The last clause is the one with teeth. EndGameObjects.txt makes holding
    WONDER_RUNE_OF_RULERSHIP for 10 turns the scenario's victory, and the AI can
    only choose a wonder that appears in one of these seven lists. The lists
    shipped EMPTY -- deliberately, to stop stock aidata idents dangling -- which
    also meant no AI could ever build any of the 23 MoM wonders, so in an AI-only
    game the victory was unreachable by construction. Two headless playthroughs
    (200 and 600 turns) ended only because the script ran out, never because the
    game did.

    An empty list is therefore not a safe default here: it is silent, it looks
    tidy, and it deletes a win condition. Assert coverage explicitly.
    """
    wonder_txt = scen / "default/gamedata/Wonder.txt"
    lists_txt = scen / "default/aidata/WonderBuildLists.txt"
    if not wonder_txt.exists() or not lists_txt.exists():
        return

    wtext = wonder_txt.read_text(encoding="latin-1", errors="replace")
    ltext = lists_txt.read_text(encoding="latin-1", errors="replace")
    blocks = dict(re.findall(r"^(WONDER_[A-Z0-9_]+)\s*\{(.*?)^\}", wtext,
                             re.S | re.M))
    listed = set(re.findall(r"^\s*Wonder\s+(WONDER_\w+)", ltext, re.M))

    def _adv(body: str, key: str) -> str | None:
        m = re.search(r"\b" + key + r"\s+(\S+)", body)
        return m.group(1) if m else None

    # The disabled idiom: obsolete by the same advance that unlocks it.
    disabled = {n for n, b in blocks.items()
                if _adv(b, "EnableAdvance") is not None
                and _adv(b, "EnableAdvance") == _adv(b, "ObsoleteAdvance")}
    live = set(blocks) - disabled

    for ident in sorted(listed - set(blocks)):
        fails.append(f"WonderBuildLists.txt: {ident} is not a block in Wonder.txt")
    for ident in sorted(listed & disabled):
        fails.append(
            f"WonderBuildLists.txt: {ident} is obsolete the moment it unlocks -- "
            "offering it to the AI burns production on a dead end")
    for ident in sorted(live - listed):
        fails.append(
            f"WonderBuildLists.txt: live wonder {ident} is in no AI list, so no "
            "AI player can ever choose to build it")

    endgame = scen / "default/gamedata/EndGameObjects.txt"
    if endgame.exists():
        want = set(re.findall(
            r"^\s*Wonder\s+(WONDER_\w+)",
            endgame.read_text(encoding="latin-1", errors="replace"), re.M))
        for ident in sorted(want - listed):
            fails.append(
                f"WonderBuildLists.txt: {ident} decides the game in "
                "EndGameObjects.txt but is in no AI build list -- the victory "
                "condition is unreachable for every AI player")


def check_parchment_range(scen: Path, fails: list[str]) -> None:
    """Gate 23: every civ's Parchment resolves to an art file that exists.

    Require: a generated civilisation.txt.
    Guarantee: every `Parchment` value is in 1..41 or is 99.

    `dipwizard.cpp:2673` builds the diplomacy background filename at RUNTIME as
    `UPDG%02d.tga` from this field -- there is no DB reference to dangle, so no
    other gate can see it. A regex scan of every ctp2_data/**/*.zfs returns
    exactly updg01..updg41 plus updg99, so anything outside that is a native
    Targa Load Error modal that stops the engine's message pump: the harness
    sees a frozen frame and no console line ([[ctp2-harness-cannot-see-console
    -output]]). All five MoM tribes shipped 42-46 -- i.e. every tribe was
    broken -- until 2026-07-27.
    """
    civ = scen / "default/gamedata/civilisation.txt"
    if not civ.exists():
        return
    # Block headers carry a trailing `#N` comment and open their brace on the
    # NEXT line, so a `^(\w+)\s*\{` block regex matches nothing here and the
    # gate passes a file it should reject. Track the block by line instead.
    block = "?"
    for line in civ.read_text(encoding="latin-1", errors="replace").splitlines():
        head = re.match(r"^([A-Za-z_]\w*)\b", line)
        if head:
            block = head.group(1)
            continue
        m = re.match(r"^\s*Parchment\s+(\d+)\s*$", line)
        if m:
            n = int(m.group(1))
            if not (1 <= n <= 41 or n == 99):
                fails.append(
                    f"civilisation.txt: {block} Parchment {n} has no UPDG"
                    f"{n:02d}.tga -- legal range is 1-41 or 99")


def check_renaissance_age_cap(scen: Path, fails: list[str]) -> None:
    """Gate 22: ages 5-7 are purely magical; mundane tech ends at AGE_FOUR.

    Require: a generated Advance.txt.
    Guarantee: every advance above AGE_FOUR transitively requires a sphere
    ladder rung (ADVANCE_<SPHERE>_{MAGIC,LORE,ADEPT,MAGE,WIZARD,MASTER}, plus
    Sorcery's irregular ADVANCE_SORCERY / ADVANCE_SORCEROUS_LORE).

    `_relayout_advance_ages` keyed its cap on `ident in momjr` -- but MoM
    authored nearly the whole tree, so the mundane branch was dead code and the
    cap applied to nothing. Ecognomics, Sanitation, Sea Lore and Greater Fauna
    Lore drifted to AGE_FIVE on depth banding alone. This gate reads the SHIPPED
    Advance.txt and re-derives the closure independently of the writer, so a
    future relayout that regresses the discriminator fails here rather than
    quietly shipping mundane tech in the magical ages.
    """
    adv = scen / "default/gamedata/Advance.txt"
    if not adv.exists():
        return
    try:
        sys.path.insert(0, str(TOOLS_DIR))
        from ctp2_generator import _ladder_rung_age, _AGE_NUMBER, _MUNDANE_MAX_AGE
    except Exception:
        return
    text = adv.read_text(encoding="latin-1", errors="replace")
    blocks = dict(re.findall(r"^(ADVANCE_[A-Z0-9_]+)\s*\{(.*?)^\}", text,
                             re.S | re.M))
    prereqs = {
        ident: [p for p in re.findall(
            r"^\s*Prerequisites\s+(ADVANCE_[A-Z0-9_]+)\s*$", body, re.M)
            if p != ident and p in blocks]
        for ident, body in blocks.items()
    }
    magical: dict[str, bool] = {}

    def _magical(ident: str, stack: frozenset = frozenset()) -> bool:
        if ident in magical:
            return magical[ident]
        if ident in stack:
            return False            # a prerequisite cycle is not this gate's job
        result = (_ladder_rung_age(ident) is not None
                  or any(_magical(p, stack | {ident}) for p in prereqs[ident]))
        magical[ident] = result
        return result

    for ident, body in sorted(blocks.items()):
        m = re.search(r"^\s*Age\s+(AGE_[A-Z]+)\s*$", body, re.M)
        age = _AGE_NUMBER.get(m.group(1), 1) if m else 1
        if age > _MUNDANE_MAX_AGE and not _magical(ident):
            fails.append(f"{ident} is mundane but sits at {m.group(1)} -- "
                         f"ages above AGE_{'FOUR'} are reserved for the sphere "
                         f"ladders (Renaissance cap)")


def check_gl_statistics_match_db(scen: Path, fails: list[str]) -> None:
    """Gate 21: the Great Library's printed stats match the advance DB.

    Require: a generated Advance.txt and english/gamedata/Great_Library.txt.
    Guarantee: every ADVANCE_*_STATISTICS section prints the Cost, Age and
    Branch of the block it describes.

    ctp2_parser stamped these lines when the advance was registered, ~1300 lines
    before `_retune_mom_advance_costs` rewrote the costs -- ADVANCE_WRITING
    advertised `Cost: 1000` against a DB `Cost 1025`. The player has no way to
    see the DB, so a drifted line is simply a lie in the encyclopaedia.

    Reads both SHIPPED artifacts rather than the reconcile pass's own output, so
    a future writer that re-stamps stale values still fails here.
    """
    adv = scen / "default/gamedata/Advance.txt"
    gl = scen / "english/gamedata/Great_Library.txt"
    if not adv.exists() or not gl.exists():
        return
    try:
        sys.path.insert(0, str(TOOLS_DIR))
        from ctp2_generator import gl_age_display
    except Exception:
        return
    age_path = scen / "default/gamedata/age.txt"
    ages = gl_age_display(
        age_path.read_text(encoding="latin-1", errors="replace")
        if age_path.exists() else "")

    live: dict[str, dict[str, str]] = {}
    text = adv.read_text(encoding="latin-1", errors="replace")
    for m in re.finditer(r'^(ADVANCE_\w+) \{(.*?)^\}', text, re.S | re.M):
        body, fields = m.group(2), {}
        for key in ("Cost", "Age", "Branch"):
            f = re.search(rf'^\s*{key}\s+(\S+)', body, re.M)
            if f:
                fields[key] = f.group(1)
        live[m.group(1)] = fields

    section = None
    for line in gl.read_text(encoding="latin-1", errors="replace").splitlines():
        s = line.strip()
        m = re.match(r"^\[(ADVANCE_\w+)_STATISTICS\]$", s)
        if m:
            section = m.group(1)
            continue
        if s == "[END]":
            section = None
            continue
        if not section:
            continue
        f = re.match(r'^(?:<[ch]:\d+,\d+,\d+>)*(Cost|Age|Branch):\s*(.*)$', s)
        if not f:
            continue
        key, shown = f.group(1), f.group(2).strip()
        want = (live.get(section) or {}).get(key)
        if want is None:
            continue
        if key == "Age":
            want = ages.get(want, want)
        if shown != want:
            fails.append(f"english/gamedata/Great_Library.txt: "
                         f"{section}_STATISTICS says {key}: {shown} but "
                         f"Advance.txt says {want}")


def check_building_effects(scen: Path, fails: list[str]) -> None:
    """Gate 13: no building charges upkeep and does nothing.

    Two halves, and both matter:

    a) Every live improvement carries at least one effect field. Before this
       gate all 21 shipped blocks were DefaultIcon/Description/EnableAdvance/
       ProductionCost/Upkeep and nothing more -- a 270-production Barracks with
       no mechanical effect at all. Nothing in the pipeline noticed, because an
       inert block is perfectly well-formed.

    b) Every field a block does carry is declared in the engine's own record
       schema (gs/newdb/building.cdb, transcribed as
       ctp2_generator.BUILDING_EFFECT_FIELDS plus the five structural fields).
       An undeclared field aborts scenario load, so a typo here is fatal in
       game and invisible on disk.

    Retired 'x' sentinels are exempt from (a): they exist only to hold their DB
    index and are obsoleted from turn 1, so an effect on one is unreachable.
    """
    path = scen / "default/gamedata/buildings.txt"
    if not path.exists():
        return
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from ctp2_generator import BUILDING_EFFECT_FIELDS
    except Exception:
        return
    structural = {"DefaultIcon", "Description", "EnableAdvance", "ObsoleteAdvance",
                  "PrerequisiteBuilding", "ProductionCost", "Upkeep"}
    text = re.sub(r"//.*", "", path.read_text(encoding="latin-1"))
    for m in re.finditer(r"^(IMPROVE_\w+)\s*\{(.*?)^\}", text, re.S | re.M):
        ident, body = m.group(1), m.group(2)
        fields = [ln.split()[0] for ln in body.splitlines() if ln.strip()]
        unknown = [f for f in fields if f not in structural and f not in BUILDING_EFFECT_FIELDS]
        for f in unknown:
            fails.append(f"buildings.txt: {ident} names field {f!r}, absent from building.cdb")
        if "ObsoleteAdvance" in fields:
            continue  # retired sentinel: unreachable by construction
        if not [f for f in fields if f in BUILDING_EFFECT_FIELDS]:
            fails.append(f"buildings.txt: {ident} has no effect -- it costs upkeep and does nothing")


def check_wonder_effects(scen: Path, fails: list[str]) -> None:
    """Gate 14: the same inert-block check, against Wonder.txt.

    A wonder is 2160-3240 production and one per civilisation; an inert one is
    a worse deal than an inert building by an order of magnitude. Live wonders
    must carry an effect, and every field they carry must be declared in
    gs/newdb/wonder.cdb (transcribed as ctp2_generator.WONDER_EFFECT_FIELDS).

    Retired 'X'-prefixed sentinels hold a DB index only and are exempt.
    """
    path = scen / "default/gamedata/Wonder.txt"
    if not path.exists():
        return
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from ctp2_generator import WONDER_EFFECT_FIELDS, WONDER_STRUCTURAL_FIELDS
    except Exception:
        return
    text = re.sub(r"//.*", "", path.read_text(encoding="latin-1"))
    for m in re.finditer(r"^(WONDER_\w+)\s*\{(.*?)^\}", text, re.S | re.M):
        ident, body = m.group(1), m.group(2)
        fields = [ln.split()[0] for ln in body.splitlines() if ln.strip()]
        for f in fields:
            if f not in WONDER_STRUCTURAL_FIELDS and f not in WONDER_EFFECT_FIELDS:
                fails.append(f"Wonder.txt: {ident} names field {f!r}, absent from wonder.cdb")
        if ident.startswith("WONDER_X"):
            continue  # retired sentinel
        if not [f for f in fields if f in WONDER_EFFECT_FIELDS]:
            fails.append(f"Wonder.txt: {ident} has no effect -- it costs thousands of production and does nothing")


def check_advance_prereqs(scen: Path, fails: list[str]) -> None:
    """Gate 15: every prereq advances.csv declares survives into Advance.txt.

    RawBlockTextFile.add_advance is append-only, so an advance that already
    exists in the seeded tree silently discards its whole CSV-derived block.
    The loss is invisible in-game -- the tech simply researches earlier than the
    design says -- which is exactly why it needs a gate rather than a reading.

    The expected-edge set comes from ctp2_generator.csv_advance_prereq_edges, the
    same function the generator pass uses, so gate and writer cannot disagree.
    """
    path = scen / "default/gamedata/Advance.txt"
    if not path.exists():
        return
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from ctp2_generator import csv_advance_prereq_edges, _scan_advance_blocks
    except Exception:
        return
    text = re.sub(r"//.*", "", path.read_text(encoding="latin-1"))
    blocks = _scan_advance_blocks(text)
    for ident, wanted in csv_advance_prereq_edges().items():
        block = blocks.get(ident)
        if block is None:
            continue  # masked out by the tech cap; not this gate's business
        have = set(re.findall(r"^\s*Prerequisites\s+(ADVANCE_[A-Z0-9_]+)\s*$",
                              block, re.M))
        for prereq in wanted:
            if prereq not in have:
                fails.append(
                    f"Advance.txt: {ident} lost its control-plane prerequisite {prereq}")
    # Second arm, over EVERY block: a prereq naming an advance no block defines
    # is a dangling ref, and dangling refs abort scenario load.
    for ident, block in blocks.items():
        for prereq in re.findall(r"^\s*Prerequisites\s+(ADVANCE_[A-Z0-9_]+)\s*$",
                                 block, re.M):
            if prereq not in blocks:
                fails.append(
                    f"Advance.txt: {ident} requires {prereq}, which no block defines")


def check_gl_icon_keys(scen: Path, fails: list[str]) -> None:
    """Gate 16: an icon record must cite the Great Library section we wrote for it.

    The GL panel key is the icon record's field verbatim -- SetTechMode copies
    iconRec->GetGameplay() and hands it straight to Look_Up_Data
    (greatlibrarywindow.cpp:343,187). Nothing derives `IDENT_GAMEPLAY`. So an icon
    record still carrying a stock `GAMEA011.txt`-style key renders base-tree prose
    (or blank) while our generated section sits unreferenced -- invisible unless
    someone opens that exact entry in-game.

    Scope: only records whose matching `<IDENT>_GAMEPLAY` section exists in our GL.
    A legacy record with no counterpart section is not this gate's business.
    """
    gl = scen / "english/gamedata/Great_Library.txt"
    if not gl.exists():
        return
    sections = set(re.findall(r"^\[([A-Z0-9_]+)\]", gl.read_text(encoding="latin-1"), re.M))
    for name in ("advanceicon.txt", "improveicon.txt", "wondericon.txt", "uniticon.txt"):
        path = scen / "default/gamedata" / name
        if not path.exists():
            continue
        for line in path.read_text(encoding="latin-1").splitlines():
            m = re.match(r"^(ICON_[A-Z0-9_]+)\b", line.strip())
            if not m:
                continue
            ident = m.group(1)[len("ICON_"):]
            want = f"{ident}_GAMEPLAY"
            if want not in sections:
                continue
            # The three icon-file dialects (named fields, tab-quoted, quote-run)
            # all put the key inside double quotes, so compare on quoted tokens.
            # Stock deliberately points some Gameplay tabs at that ident's own
            # HISTORICAL section (the age concepts); text that resolves to a real
            # section of the SAME ident is reachable -- not this gate's business.
            cited = re.findall(r'"([^"]*)"', line)
            if not any(c == want or (c.startswith(ident + "_") and c in sections)
                       for c in cited):
                fails.append(
                    f"{name}: {m.group(1)} does not cite {want}; its Great Library "
                    f"text is unreachable")


def check_tga_assets(scen: Path, fails: list[str]) -> None:
    """Gate 12: every .tga the scenario names resolves, and every .tga it ships loads.

    Require: the scenario's own gamedata/uidata name their art by filename.
    Guarantee: each named .tga resolves to something the engine can open, and no
    shipped .tga has a header the engine would reject.
    Maintain: the base tree is never written -- it is read-only evidence here.

    Two halves, because the engine has two distinct TGA failure modes and an
    existence check alone catches neither reliably:

    ABSENT. Art resolves from three places, not one: a loose .tga under the
    scenario, a loose .tga in the base tree, or -- and this is the half that
    makes a naive sweep useless -- a PACKED entry inside a .zfs archive. The
    archives are `ZFS3` containers whose name table stores `.rim` files, so
    grepping them for `.tga` returns zero and every packed asset reads as
    missing. Scanning scen0000 alone against loose files only reported 256
    missing of 541 referenced, ~100% false positives; counting .rim stems cut
    that to 22, all of them stock refs the base tree makes identically.

    MALFORMED. The engine's only two TGA diagnostics -- `Bad TGA Sprite File(%s)`
    and `TGA Sprite File not 32-bits(%s)` -- both fire on a file that EXISTS.
    A zero-byte or truncated .tga is therefore invisible to an existence gate;
    the base tree ships exactly one (UPCB47X.tga, 0 bytes, dated 2000-11-01,
    referenced by nothing but badTGA.txt). Only scenario-shipped files are
    asserted, since the base tree's oddities are Activision's and unfixable here.

    Scope: references are read from the scenario's own .txt/.ldl/.slc only.
    Base-tree files are not scanned for references -- unlike dangling record
    idents, which abort the load, missing art degrades to a blank cell, so the
    stock tree's own latents are noise rather than a crash class. `//` comments
    are stripped before tokenising, per gate 11.
    """
    base = None
    for anc in scen.resolve().parents:
        if (anc / "ctp2_data/default/gamedata").exists():
            base = anc / "ctp2_data"
            break

    have: set[str] = {p.name.lower() for p in scen.rglob("*.tga")}
    if base is not None:
        have |= {p.name.lower() for p in base.rglob("*.tga")}
        for archive in base.rglob("*.zfs"):
            blob = archive.read_bytes()
            if not blob.startswith(b"ZFS3"):
                continue
            for raw in re.findall(rb"[A-Za-z0-9_\-]{2,40}\.rim", blob):
                have.add(raw.decode("latin-1").lower()[:-4] + ".tga")

    refs: dict[str, str] = {}
    for src in sorted(scen.rglob("*")):
        if src.suffix.lower() not in (".txt", ".ldl", ".slc"):
            continue
        try:
            text = src.read_text(encoding="latin-1")
        except OSError:
            continue
        text = re.sub(r"//[^\n]*", "", text)
        for name in re.findall(r"[A-Za-z0-9_.\-]+\.tga", text):
            refs.setdefault(name.lower(), src.name)

    base_named: set[str] = set()
    if base is not None:
        for rel in ("default/gamedata", "default/uidata"):
            for src in (base / rel).rglob("*"):
                if src.suffix.lower() not in (".txt", ".ldl"):
                    continue
                try:
                    text = re.sub(r"//[^\n]*", "", src.read_text(encoding="latin-1"))
                except OSError:
                    continue
                base_named.update(n.lower() for n in
                                  re.findall(r"[A-Za-z0-9_.\-]+\.tga", text))

    for name, src_name in sorted(refs.items()):
        # A ref the stock tree makes identically is Activision's latent, not the
        # mod's regression -- flagging it would train the operator to ignore this
        # gate, which is how a gate dies.
        if name not in have and name not in base_named:
            fails.append(f"{src_name}: references {name}, which is neither a "
                         f"loose .tga nor a .rim entry in any .zfs archive")

    for art in sorted(scen.rglob("*.tga")):
        blob = art.read_bytes()
        if len(blob) < 18:
            fails.append(f"{art.name}: {len(blob)}-byte .tga -- header is 18 "
                         f"bytes, the engine reports this as a Bad TGA Sprite File")


def check_effective_tree_advance_refs(scen: Path, fails: list[str]) -> None:
    """Gate 11: no DB the ENGINE parses cites a record any prune deleted.

    Require: the scenario's gamedata holds the live DB for each family below.
    Guarantee: for every file in the engine's parse list, the copy the engine
    will actually load -- the scenario's override if it ships one, else the
    base-tree file -- contains no dangling reference in ANY of those families.
    Why: every other gate here only inspects files the scenario overrides, and
    the engine aborts on the FIRST dangling ref, so launching the game finds
    these one at a time at ~5 min each. Three modals came from this one blind
    spot: base Pop.txt -> deleted ADVANCE_INDUSTRIAL_REVOLUTION, base
    aidata/ImprovementLists.txt -> deleted TILEIMP_LISTENING_POSTS, and the
    ICON_ADVANCE_DEFAULT sentinel. Base-tree fallback is the defect, not a file.

    Scope is deliberately narrow on both axes. Files: only DBs Parse()d in
    civapp.cpp plus the aidata lists -- Improve.txt, endgame.txt, order.txt, the
    *icon.txt exports (uniticon.txt is the sole runtime icon DB) and
    Units_{historic,release}.txt all carry dead refs and are harmless because
    nothing parses them. Tokens: `//` comments are stripped first (strategies.txt
    lists seven deleted governments, all commented out), and the exclusion
    regex drops field names (ADVANCE_CHANCES, CONCEPT_DEFAULT_ICON,
    UNIT_RATIONS), enum values (UNIT_CATEGORY_*), Great Library string keys
    (*_GAMEPLAY/_SUMMARY/_ADVICE/...), AI list record names (*_LIST_*), the
    per-good terrain slots (TERRAIN_*_GOOD_ONE..FOUR) and the city styles
    (AGE_*_STYLE_*, defined in agecitystyle.txt rather than age.txt).
    Skipped when the base tree is not locatable, since this validator is
    scenario-generic.
    """
    # Walk up rather than index a fixed depth: --scenario is routinely passed as
    # a relative path, whose .parents chain is one element long, so any fixed
    # index silently no-ops the whole gate.
    base = None
    for anc in scen.resolve().parents:
        if (anc / "ctp2_data/default/gamedata").exists():
            base = anc / "ctp2_data"
            break
    if base is None:
        return
    def effective(rel: str) -> tuple[Path | None, str]:
        if (scen / rel).exists():
            return scen / rel, "scenario"
        if (base / rel).exists():
            return base / rel, "BASE"
        return None, ""

    def body(rel: str) -> str:
        eff, _ = effective(rel)
        if eff is None:
            return ""
        return re.sub(r"//[^\n]*", "",
                      eff.read_text(encoding="latin-1"))

    # family -> the file that DEFINES its records.
    families = {
        "ADVANCE": "Advance.txt", "TILEIMP": "tileimp.txt",
        "UNIT": "Units.txt", "ICON": "uniticon.txt",
        "WONDER": "Wonder.txt", "GOVERNMENT": "govern.txt",
        "IMPROVE": "buildings.txt", "TERRAIN": "terrain.txt",
        "POP": "Pop.txt", "FEAT": "feat.txt", "ORDER": "Orders.txt",
        "CONCEPT": "concept.txt", "AGE": "age.txt",
    }
    live: dict[str, set[str]] = {}
    for fam, defining in families.items():
        found = set(re.findall(rf"^({fam}_[A-Z0-9_]+)\s*\{{",
                               body(f"default/gamedata/{defining}"), re.M))
        if found:
            live[fam] = found
    if "ADVANCE" not in live:
        return
    live["ADVANCE"].add("ADVANCE_NA")

    # Tokens that look like record references but are not. See the docstring.
    noise = re.compile(
        r"_(GAMEPLAY|HISTORICAL|PREREQ|STATISTICS|SUMMARY|DESCRIPTION)$"
        r"|_(HIGHER|SAME)_RANK_ADVICE$"
        r"|^UNIT_CATEGORY_|_LIST_|_STYLE_"
        r"|_GOOD_(ONE|TWO|THREE|FOUR)$"
        r"|^(CONCEPT_DEFAULT_ICON|GOVERNMENT_TYPE|POP_HUNGER)$"
        r"|^UNIT_(RATIONS|WAGES|WORKDAY|RUSH_MODIFIER)$"
        r"|^WONDER_(RUSH_MODIFIER|VICTORY_BONUS)$"
        r"|^ADVANCE_(CHANCES|CHOICES_MAX|CHOICES_MIN)$")

    parsed = [f"default/gamedata/{n}" for n in (
        "Pop.txt", "buildings.txt", "Units.txt", "Wonder.txt", "govern.txt",
        "tileimp.txt", "terrain.txt", "feat.txt", "goods.txt", "concept.txt",
        "age.txt", "Orders.txt", "civilisation.txt", "EndGameObjects.txt",
        "risks.txt", "citysize.txt", "citystyle.txt", "pollution.txt",
        "uniticon.txt", "Advance.txt")]
    parsed += [f"default/aidata/{n}" for n in (
        "AdvanceLists.txt", "BuildingBuildLists.txt", "UnitBuildLists.txt",
        "WonderBuildLists.txt", "ImprovementLists.txt", "Goals.txt",
        "strategies.txt", "buildlistsequences.txt")]
    for rel in parsed:
        eff, src = effective(rel)
        if eff is None:
            continue
        text = body(rel)
        for fam, ls in live.items():
            dead = {m for m in set(re.findall(rf"\b{fam}_[A-Z0-9_]+\b", text))
                    if m not in ls and not noise.search(m)}
            for missing in sorted(dead):
                fails.append(
                    f"{rel} ({src} copy the engine will load): {missing} not in "
                    f"{families[fam]} (DB-Error crash at load)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", type=Path, required=True)
    args = parser.parse_args()
    scen = args.scenario
    if not (scen / "default/gamedata").exists():
        raise SystemExit(f"{scen} does not look like a scenario dir")

    fails: list[str] = []
    check_newsprite(scen, fails)
    unit_idents = check_units_idents(scen, fails)
    check_reserved(scen, unit_idents, fails)
    check_string_refs(scen, fails)
    check_icon_refs(scen, fails)
    check_advance_prereq_cap(scen, fails)
    check_visible_art(scen, fails)
    check_buildlist_refs(scen, fails)
    check_city_unit_coverage(scen, fails)
    check_gl_str(scen, fails)
    check_faction_gating(scen, fails)
    check_effective_tree_advance_refs(scen, fails)
    check_building_effects(scen, fails)
    check_wonder_effects(scen, fails)
    check_gl_icon_keys(scen, fails)
    check_advance_prereqs(scen, fails)
    check_tga_assets(scen, fails)
    check_disabled_advances_closed(scen, fails)
    check_advance_code_map(scen, fails)
    check_disabled_entities_unbuildable(scen, fails)
    check_gl_statistics_match_db(scen, fails)
    check_renaissance_age_cap(scen, fails)
    check_parchment_range(scen, fails)
    check_wonder_build_lists(scen, fails)
    check_wonder_articles(scen, fails)
    check_ai_magic(scen, fails)

    if fails:
        for f in fails:
            print(f"FAIL {f}")
        print(f"\n{len(fails)} failure(s).")
        return 1
    print("all scenario gates pass (newsprite grammar, ident charset, "
          "reserved tokens, string-ref integrity, gl_str grammar, faction gating)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
