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
    check_tga_assets(scen, fails)

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
