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

    if fails:
        for f in fails:
            print(f"FAIL {f}")
        print(f"\n{len(fails)} failure(s).")
        return 1
    print("all scenario gates pass (newsprite grammar, ident charset, "
          "reserved tokens, string-ref integrity, gl_str grammar)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
