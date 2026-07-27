"""Generate CTP2 mod files from MOMJR CSV templates."""
import csv, json, os, sys, re
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
ROOT_DIR = TOOLS_DIR.parents[2]
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(TOOLS_DIR))
import ctp2_parser as P
import civ2_sprite_extractor as extractor
import gl_descriptions
from export_mod_workbook import DEFAULT_OUTPUT as MOD_WORKBOOK_PATH, export_workbook

MOMJR = Path(
    os.environ.get(
        "CTP2_GENERATOR_CSV_DIR",
        str(Path(__file__).parent / "momjr_csv"),
    )
)
SCENARIO = Path(
    os.environ.get(
        "CTP2_GENERATOR_SCENARIO_DIR",
        r"H:\Program Files(x86)\Activision\Call To Power 2\Scenarios\mom\scen0000",
    )
)
CTP2_DATA = Path(
    os.environ.get(
        "CTP2_GENERATOR_CTP2_DATA_DIR",
        r"H:\Program Files(x86)\Activision\Call To Power 2\ctp2_data",
    )
)

reg = P.FileRegistry(SCENARIO, CTP2_DATA)

# ---------------------------------------------------------------------------
# Per-mod policy control plane (lives in the mod's csv dir alongside the
# dimension csvs; bootstrap/scaffold with dump_mod_policy.py). The generator
# is the ENGINE; everything a different civ2->ctp2 conversion would choose
# differently is loaded from these files, never hardcoded here.
# ---------------------------------------------------------------------------
def _policy_csv_rows(name: str) -> list[dict[str, str]]:
    """Load a required policy csv from the mod's csv dir; hard error if absent."""
    path = MOMJR / name
    if not path.exists():
        raise SystemExit(
            f"ctp2_generator: missing control-plane policy file {path} "
            f"(bootstrap with dump_mod_policy.py or author one for this mod)")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _load_mod_policy() -> dict:
    path = MOMJR / "mod_policy.json"
    if not path.exists():
        raise SystemExit(
            f"ctp2_generator: missing control-plane policy file {path} "
            f"(bootstrap with dump_mod_policy.py or author one for this mod)")
    return json.loads(path.read_text(encoding="utf-8"))


MOD_POLICY = _load_mod_policy()

_TILEIMP_MASK = _policy_csv_rows("tileimp_mask.csv")
HIDDEN_SURROGATE_TILEIMPS = {r["id"] for r in _TILEIMP_MASK if r["reason"] == "surrogate"}
HIDDEN_OUT_OF_GENRE_TILEIMPS = {r["id"] for r in _TILEIMP_MASK if r["reason"] == "out_of_genre"}
SURROGATE_TILEIMP_NOTES = {r["id"]: r["note"] for r in _TILEIMP_MASK if r.get("note")}

START_GOVERNMENT_ADVANCE = MOD_POLICY["start_government_advance"]
START_GUARANTEED_ADVANCES = list(MOD_POLICY["start_guaranteed_advances"])

# Ordered: rewrites apply sequentially.
HIDDEN_TILEIMP_GREAT_LIBRARY_TEXT = [
    (r["find"], r["replace"]) for r in _policy_csv_rows("gl_text_rewrites.csv")
]

HIDDEN_OUT_OF_GENRE_ORDERS = {r["id"] for r in _policy_csv_rows("order_mask.csv")}
HIDDEN_OUT_OF_GENRE_CONCEPTS = {r["id"] for r in _policy_csv_rows("concept_mask.csv")}

MOD_DISPLAY_NAME = MOD_POLICY["mod_display_name"]

_SPRITE_PICK_RULES = _policy_csv_rows("sprite_pick_rules.csv")
_UNIT_BLOCK_OVERRIDES = {
    r["unit_id"]: r["block_text"] for r in _policy_csv_rows("unit_block_overrides.csv")
}
_GL_SECTION_OVERRIDES = _policy_csv_rows("gl_section_overrides.csv")


def _eval_pick_rules(lane: str, name: str, domain: int, attack: int, hp_raw: int):
    """Evaluate the ordered sprite/size pick rules for one unit; None = no match.

    Rules with a domain only fire for that domain; `default` rows terminate
    their (lane, domain) group, mirroring the original hardcoded branch order.
    """
    n = name.lower()
    for r in _SPRITE_PICK_RULES:
        if r["lane"] != lane:
            continue
        if r["domain"].strip() and int(r["domain"]) != domain:
            continue
        rule = r["rule"]
        if rule == "name":
            if any(k in n for k in r["match"].split("|")):
                return r["result"]
        elif rule == "attack_ge":
            if attack >= int(r["threshold"]):
                return r["result"]
        elif rule == "hp_ge":
            if hp_raw >= int(r["threshold"]):
                return r["result"]
        elif rule == "default":
            return r["result"]
    return None


def _apply_gl_section_overrides(library: "P.LibraryFile", lane: str) -> None:
    """Apply per-mod GL section surgery (set / replace-within / pop) in csv order."""
    for r in _GL_SECTION_OVERRIDES:
        if r["library"] != lane:
            continue
        sid, action = r["section"], r["action"]
        if action == "set":
            library.sections[sid] = r["content"]
        elif action == "pop":
            library.sections.pop(sid, None)
        elif action == "replace":
            current = library.sections.get(sid)
            if current:
                library.sections[sid] = current.replace(r["find"], r["content"])


def sanitize(name):
    s = name.upper().replace(" ", "_").replace("'", "").replace("-", "_")
    s = re.sub(r'[^A-Z0-9_]', '', s)
    return re.sub(r'_+', '_', s).strip('_')


def humanize_ident(ident: str, prefix: str) -> str:
    """Convert a database ID into a readable fallback display name."""
    core = ident[len(prefix):] if ident.startswith(prefix) else ident
    return core.replace('_', ' ').title()


# Building/improvement prereq short-code -> CTP2 advance ID (control-plane
# surface: advance_code_map.csv lane "prereq"; this literal is the MoM default).
_ADVANCE_CODE_ROWS = _policy_csv_rows("advance_code_map.csv")
# Building/improvement prereq short-code -> CTP2 advance ID (lane "prereq").
PREREQ_CODE_MAP = {r["code"]: r["advance"] for r in _ADVANCE_CODE_ROWS if r["lane"] == "prereq"}


def advance_id(code):
    """Map MoM building prereq short codes to CTP2 advance IDs (for improvements).

    Returns empty string for codes that mean 'no prerequisite' (nil, no).
    Raises ValueError for unmapped codes so missing mappings are caught at generation time.
    """
    # Civ2 codes meaning "no prerequisite required" — omit EnableAdvance in CTP2
    _no_prereq = {'nil', 'no', 'nil', ''}
    if code in _no_prereq:
        return ''
    result = PREREQ_CODE_MAP.get(code)
    if result is None:
        raise ValueError(f"advance_id: unmapped Civ2 prereq code '{code}' — add to advance_code_map.csv (lane=prereq)")
    return result


# Complete MoM short-code → CTP2 advance ID mapping for UNITS
MOM_UNIT_ADVANCE = {r["code"]: r["advance"] for r in _ADVANCE_CODE_ROWS if r["lane"] == "unit"}

# The BUILDING-prereq lane of the same control plane. Kept SEPARATE from the
# unit lane rather than merged over it: the two lanes disagree on purpose
# (unit 'MT' -> ADVANCE_THEOLOGY, prereq 'MT' -> ADVANCE_COMMUNE_WITH_GODS) and
# 5 prereq-lane targets are dangling, so consumers must try this lane first and
# FALL THROUGH to the unit lane when the target does not exist or is disabled.
# Reading buildings through the unit lane alone silently dropped prereq-only
# codes to the fallback advance (found 2026-07-26 via Merchant's Guild, 'Eco').
MOM_PREREQ_ADVANCE_LANE = {
    r["code"]: r["advance"] for r in _ADVANCE_CODE_ROWS if r["lane"] == "prereq"
}

# Codes that mean "no advance required" (heroes / starter units)
_NO_ADVANCE = {'nil', 'no', ''}

# Engine-required unit slots that must stay visible even in a MoM-only scenario.
_ENGINE_REQUIRED_UNITS = {
    "UNIT_CITY",
}

# Units the engine validates by display name at startup (hardcoded lookups in
# unitutil.cpp).  These must stay in the unit database but are NOT buildable —
# the auto-hide pass gives them NoIndex + GLHidden.  Never add these to
# unit_mask.csv; doing so removes the DB entry and causes "X not found in
# Unit database" at game startup.
_HARDCODED_DB_UNITS = {
    "UNIT_CLERIC",   # UnitUtil::InitializeClericConversion() looks up "Cleric"
}


def _parse_int_stat(s: str) -> int:
    """Parse MoM stat strings: '3a', '2d', '2h', '1f' → int."""
    return int(s.strip().rstrip('adhf') or '0')


def _parse_move(s: str) -> int:
    """Parse MoM move float string ('1.', '1.5', '2') → CTP2 MaxMovePoints."""
    return int(float(s.strip()) * 100)


_AVAILABLE_SPRITES_CACHE = None


def _available_custom_sprites() -> set:
    """SPRITE_<NAME> names that have real MoM source art in the scenario pictures dir.

    Built-in art means build_sprites.py has (or will) produce a real GU###.SPR for the
    unit, so DefaultSprite should point at the unit's OWN sprite rather than a base proxy.
    Cached; empty set is a safe fallback (every unit keeps its proxy).
    """
    global _AVAILABLE_SPRITES_CACHE
    if _AVAILABLE_SPRITES_CACHE is None:
        pics = TOOLS_DIR.parent / "scen0000" / "default" / "graphics" / "pictures"
        try:
            _AVAILABLE_SPRITES_CACHE = {p.stem.upper() for p in pics.glob("SPRITE_*.tga")}
        except OSError:
            _AVAILABLE_SPRITES_CACHE = set()
    return _AVAILABLE_SPRITES_CACHE


def _pick_sprite(name: str, domain: int, attack: int) -> str:
    """Pick DefaultSprite: the unit's OWN sprite when its art exists, else a base proxy.

    MoM ships real per-unit sprite art (SPRITE_<NAME>.tga → GU###.SPR, golden-parity
    valid). Prefer it. The domain/attack proxy heuristics below are the fallback for units
    that have no custom art (so they still get a sensible base sprite, not a broken ref).
    """
    # sanitize(), not a bare space-replace: names like "Water/Air Elementals"
    # must never leak '/' into DefaultSprite/newsprite (Expected-integer error).
    real = f"SPRITE_{sanitize(name.replace('UNIT_', ''))}"
    if real in _available_custom_sprites():
        return real
    # Proxy heuristics are per-mod policy: sprite_pick_rules.csv (lane=sprite).
    picked = _eval_pick_rules("sprite", name, domain, attack, 0)
    # Fallback: unique custom sprite name for any unmapped unit.
    return picked if picked else real


def _pick_size(name: str, hp_raw: int) -> str:
    return _eval_pick_rules("size", name, 0, 0, hp_raw) or 'Small'


# Maps CSV/stub epoch integers to valid CTP2 age IDs (age.txt: AGE_ONE..AGE_FIVE)
_AGE_MAP = {str(k): v for k, v in MOD_POLICY["epoch_age_map"].items()}

# Advances referenced by base CTP2 units (EnableAdvance) that are MoM-flavoured
# but never in advances.csv.  Generator creates stubs so the engine finds them.
_BASE_UNIT_STUB_ADVANCES = {
    r["advance"]: (r["name"], r["category"], r["age"])
    for r in _policy_csv_rows("stub_advances.csv")
}


def _read_rel(rel: str) -> str:
    import os
    scenario_path = SCENARIO / rel
    print(f"DEBUG _read_rel: rel={rel}, scenario_path={scenario_path}, exists={scenario_path.exists()}")
    if scenario_path.exists():
        try:
            size = os.path.getsize(scenario_path)
            print(f"DEBUG _read_rel: file size is {size} bytes")
            with open(scenario_path, 'r', encoding='latin-1') as f:
                text = f.read()
            print(f"DEBUG _read_rel: read {len(text)} chars from scenario using open()")
            return text
        except Exception as e:
            print(f"DEBUG _read_rel: ERROR reading scenario: {e}")
            return ""
    data_path = CTP2_DATA / rel
    try:
        size = os.path.getsize(data_path)
        print(f"DEBUG _read_rel: data file size is {size} bytes")
        with open(data_path, 'r', encoding='latin-1') as f:
            text = f.read()
        print(f"DEBUG _read_rel: reading {len(text)} chars from data using open()")
        return text
    except Exception as e:
        print(f"DEBUG _read_rel: ERROR reading data: {e}")
        return ""


def _write_rel(rel: str, text: str) -> None:
    path = SCENARIO / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if not text.endswith('\n'):
        text += '\n'
    # Use open() with newline='\n' to write LF-only (not CRLF) to match CTP2 base game file
    # format. Python's default text mode on Windows produces CRLF, which causes the CTP2
    # engine to leave \r on keys/values, breaking string lookups → blank GL list items.
    with path.open('w', encoding='latin-1', newline='') as fh:
        fh.write(text)


def _ensure_diffdb_start_government(rel: str = "default/gamedata/DiffDB.txt") -> bool:
    """Own the scenario DiffDB start-tech surface so MoM never inherits stock zero-government starts.

    Preconditions: the base or scenario DiffDB file contains one or more ADVANCE_CHANCES blocks.
    Guarantee: every difficulty ADVANCE_CHANCES block guarantees each advance in
    START_GUARANTEED_ADVANCES (government escape from anarchy + tier-0 content
    enabler) at 100/100 for both human and AI starts, and the scenario owns a
    DiffDB override on disk.
    Failure mode: raises RuntimeError if the expected ADVANCE_CHANCES surface cannot be found.
    """
    source_text = _read_rel(rel)
    advance_chances_re = re.compile(
        r"(?ms)(^(\s*)ADVANCE_CHANCES\s*\{\s*\n)(.*?)(^\2\})"
    )
    saw_block = False

    def _inject(match: re.Match[str]) -> str:
        nonlocal saw_block
        saw_block = True
        header = match.group(1)
        indent = match.group(2)
        body = match.group(3)
        footer = match.group(4)
        for adv in START_GUARANTEED_ADVANCES:
            if not re.search(rf"(?m)^\s*{re.escape(adv)}\b", body):
                body = f"{indent}\t{adv}\t\t100\t100\n{body}"
        return f"{header}{body}{footer}"

    final_text = advance_chances_re.sub(_inject, source_text)
    if not saw_block:
        raise RuntimeError(f"{rel}: ADVANCE_CHANCES block not found")

    path = SCENARIO / rel
    current_text = path.read_text(encoding='latin-1') if path.exists() else None
    if current_text != final_text:
        _write_rel(rel, final_text)
        return True
    return False


def _retire_x_sentinels() -> int:
    """Retire AE 'X'-prefixed sentinel improvements/wonders (Xpower Plant etc.).

    These are the Apolyton pack's removed-item placeholders; ingestion mistook
    them for MoM content and gated them with the tier-0 advance, so they leak
    into turn-1 build lists. Stamping ObsoleteAdvance = the guaranteed start
    advance makes them obsolete for every player from turn 1 while keeping the
    records in the DB (no index shifts, no dangling GL references).
    Returns the number of blocks stamped.
    """
    total = 0
    for rel in ("default/gamedata/buildings.txt", "default/gamedata/wonder.txt"):
        path = SCENARIO / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="latin-1")
        count = 0

        def _stamp(m: re.Match[str]) -> str:
            nonlocal count
            name, body = m.group(1), m.group(2)
            if "ObsoleteAdvance" in body:
                return m.group(0)
            obsolete_advance = MOD_POLICY["retire_sentinel_obsolete_advance"]
            body2, k = re.subn(
                r"([ \t]*EnableAdvance [A-Z_0-9]+\n)",
                r"\1   ObsoleteAdvance " + obsolete_advance + "\n",
                body, count=1)
            count += k
            return f"{name} {{{body2}}}"

        sentinel_prefix = re.escape(MOD_POLICY["retire_sentinel_prefix"])
        new_text = re.sub(r"^((?:IMPROVE|WONDER)_" + sentinel_prefix + r"[A-Z_0-9]+) \{(.*?)^\}",
                          _stamp, text, flags=re.S | re.M)
        if count:
            path.write_text(new_text, encoding="latin-1")
            total += count
    return total


def _csv_path(name: str) -> Path:
    return MOMJR / name


def _csv_exists(name: str) -> bool:
    return _csv_path(name).exists()


def _csv_rows(name: str) -> list[dict[str, str]]:
    with open(_csv_path(name), newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def _csv_text(value: str) -> str:
    """Normalize CSV prose fields into plain multi-line text."""
    normalized = (value or "").replace("\r\n", "\n").strip()
    replacements = {
        "\u2013": "-",
        "\u2014": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2026": "...",
    }
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    return normalized


def _normalized_gl_compare_text(value: str) -> str:
    """Normalize GL prose for stale-line comparisons."""
    return _csv_text(value).encode("ascii", "ignore").decode("ascii").strip().lower()


GL_VISIBLE_RAW_BLOCK_RELS = {
    "default/gamedata/Orders.txt",
    "default/gamedata/tileimp.txt",
    "default/gamedata/Wonder.txt",  # Engine does NOT support NoIndex/GLHidden in Wonder.txt
}
# Note: Wonder.txt MUST remain in this set to strip invalid hide flags that cause engine parse errors.


def _strip_block_flags(block_text: str, flags: set[str]) -> str:
    kept_lines = [line for line in block_text.splitlines() if line.strip() not in flags]
    return "\n".join(kept_lines).strip("\n")


def _apply_raw_block_csv(csv_name: str, rel: str, counted: bool = False) -> int:
    rows = _csv_rows(csv_name)
    blocks = []
    for row in rows:
        ident = (row.get('id') or '').strip()
        block_text = (row.get('block_text') or '').replace('\r\n', '\n').strip('\n')
        if rel in GL_VISIBLE_RAW_BLOCK_RELS:
            block_text = _strip_block_flags(block_text, {"GLHidden"})
        if not ident or not block_text:
            continue
        blocks.append(block_text)
    body = '\n\n'.join(blocks)
    text = f"{len(blocks)}\n{body}" if counted else body
    if counted and not blocks:
        text = "0\n"
    _write_rel(rel, text)
    return len(blocks)


def _apply_entry_csv(csv_name: str, rel: str, counted: bool = False) -> int:
    rows = _csv_rows(csv_name)
    entries = [(row.get('entry') or '').replace('\r\n', '\n').rstrip() for row in rows]
    entries = [entry for entry in entries if entry.strip()]
    body = '\n'.join(entries)
    text = f"{len(entries)}\n{body}" if counted else body
    if counted and not entries:
        text = "0\n"
    _write_rel(rel, text)
    return len(entries)


def _apply_block_overlay_csv(csv_name: str, rel: str) -> int:
    rows = _csv_rows(csv_name)
    file_obj = reg.load(rel)
    count = 0
    for row in rows:
        ident = (row.get('id') or '').strip()
        block_text = (row.get('block_text') or '').replace('\r\n', '\n').strip()
        if not ident or not block_text:
            continue
        overlay = P.CTP2BlockFile()
        overlay.parse(block_text + "\n")
        if ident not in overlay.blocks:
            continue
        file_obj.blocks[ident] = overlay.blocks[ident]
        count += 1
    reg.save(rel)
    return count


def _load_raw_block_file(rel: str) -> P.RawBlockTextFile:
    file_obj = P.RawBlockTextFile()
    file_obj.parse(_read_rel(rel))
    return file_obj


def _load_base_raw_block_file(rel: str) -> P.RawBlockTextFile:
    file_obj = P.RawBlockTextFile()
    file_obj.parse((CTP2_DATA / rel).read_text(encoding='latin-1'))
    return file_obj


def _load_base_block_file(rel: str) -> P.CTP2BlockFile:
    file_obj = P.CTP2BlockFile()
    file_obj.parse((CTP2_DATA / rel).read_text(encoding='latin-1'))
    return file_obj


def _save_raw_block_file(rel: str, file_obj: P.RawBlockTextFile) -> None:
    _write_rel(rel, file_obj.render())


def _merge_mom_improvements_into_buildings() -> int:
    """Reconstruct buildings.txt STRICTLY from the control plane (improvements.csv).

    CRITICAL: We initialize an EMPTY buildings.txt. We DO NOT load the existing file.
    This guarantees zero base CTP2 artifacts (like "Behavioral Mod Center") leak into
    the scenario. The control plane is the absolute source of truth.
    """
    import re as _re
    import csv
    gl_str = reg.load("english/gamedata/gl_str.txt")
    # Read the LIVE advance tree from the registry, not from disk. This merge
    # runs before save_all(), so _read_rel() here returns the PREVIOUS run's
    # advance.txt: measured 2026-07-26, ADVANCE_COMMUNE_WITH_GODS was absent
    # from it, so Cathedral's real gate was rejected as unknown and silently
    # demoted to the fallback advance (buildable turn 1). Same ordering class
    # as the improvement-cost bug below.
    _adv_file = reg.load("default/gamedata/Advance.txt")
    _advance_text = getattr(_adv_file, "_text", "") or _read_rel("default/gamedata/Advance.txt")
    advances = set(_adv_file.blocks) or set(
        _re.findall(r'^(ADVANCE_[A-Z0-9_]+)', _advance_text, _re.M))
    # Advances disabled by self-prerequisite — see the prereq resolution below.
    _disabled_advances = {
        _m.group(1)
        for _m in _re.finditer(r'^(ADVANCE_\w+) \{(.*?)^\}', _advance_text, _re.S | _re.M)
        if _re.search(r'Prerequisites\s+' + _m.group(1) + r'\b', _m.group(2))
    }

    # RECONSTRUCT FROM NOTHING: Start with a completely empty file.
    bld = P.RawBlockTextFile()
    
    _merge_policy = MOD_POLICY["improvement_merge"]
    _preferred_fallback = _merge_policy["fallback_advance"]
    fallback_adv = (_preferred_fallback if _preferred_fallback in advances
                    else (sorted(advances)[0] if advances else ""))
    remap = dict(_merge_policy["prereq_remap"])
    merged = 0
    _fallback_gates: list[tuple[str, str, str]] = []
    
    # Read directly from improvements.csv, NOT from Improve.txt (which may be base game)
    csv_path = MOMJR / "improvements.csv"
    if csv_path.exists():
        with open(csv_path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row.get("name", "").strip()
                if not name or name.lower() == "blah":
                    continue
                # 'HIDE <name>' rows are MASK DIRECTIVES ("hide the base-game
                # <name>"), not content. Ingesting one literally once produced
                # a buildable improvement called "Hide Supermarket".
                if name.upper().startswith("HIDE ") or row.get("cell_index", "").strip() == "999":
                    print(f"  - mask directive row skipped: {name!r}")
                    continue
                # civ2 spaceship parts ('SS ') and 'Nothing' are never content
                # (matching the Improve.txt emitter). A block emitted here
                # without GL surfaces has a dangling Description ref ->
                # "Expected string ID" -> game exits at scenario load.
                # NOTE: 'x'-prefixed sentinels are deliberately KEPT in this
                # lane — _retire_x_sentinels needs them in the DB (index
                # stability), and their GL surfaces exist.
                if name == 'Nothing' or 'SS ' in name:
                    print(f"  - non-content improvement row skipped: {name!r}")
                    continue
                # Wonder rows (cell_index >= 40) belong ONLY in Wonder.txt. Emitting an
                # IMPROVE_ twin double-loads the concept into BOTH the improvement and
                # wonder DBs -> conflicting indices -> Build Manager render corruption
                # (the "fuglies"; same class as commit 7afc935's Improve.txt double-load,
                # see lessons_learned.md). Wonders are handled by the Wonder.txt pass.
                try:
                    _cell = int((row.get("cell_index", "") or "0").strip() or "0")
                except ValueError:
                    _cell = 0
                if _cell >= 40:
                    continue
                ident = f"IMPROVE_{sanitize(name)}"
                if ident in bld.blocks:
                    continue
                
                icon = f"ICON_{ident}"
                desc = f"DESCRIPTION_{ident}"
                
                prereq = row.get("prereq", "").strip()
                if prereq in _NO_ADVANCE:
                    adv = "ADVANCE_WARRIOR_CODE"
                else:
                    # Resolution CHAIN, most specific first. A flat override of
                    # the unit lane by the prereq lane is wrong: 5 prereq-lane
                    # targets are dangling (ADVANCE_COMMUNE_WITH_GODS et al.
                    # were never generated), and taking them blindly demoted
                    # real gates to the fallback -- Cathedral's 'MT' resolves to
                    # the dangling COMMUNE_WITH_GODS in the prereq lane but to
                    # the live ADVANCE_THEOLOGY in the unit lane.
                    #
                    # A candidate is usable only if it EXISTS and is not
                    # disabled by self-prerequisite, which is CTP2's sanctioned
                    # "advance is unresearchable" form (Advances.cpp:498) and
                    # which MoM applies to 169 base advances. Gating a building
                    # on one makes it permanently unbuildable.
                    adv = fallback_adv
                    for _candidate in (MOM_PREREQ_ADVANCE_LANE.get(prereq),
                                       MOM_UNIT_ADVANCE.get(prereq)):
                        if (_candidate and _candidate in advances
                                and _candidate not in _disabled_advances):
                            adv = _candidate
                            break
                    else:
                        # Falling back is legitimate, but it must never be
                        # SILENT again: an unannounced fallback is what let
                        # every building sit on the wrong gate unnoticed.
                        _fallback_gates.append((name, prereq, adv))
                
                cost = row.get("cost", "100").strip() or "100"
                upkeep = row.get("upkeep", "1").strip() or "1"
                
                lines = [f"{ident} {{", f"	DefaultIcon {icon}", f"	Description {desc}"]
                if adv:
                    lines.append(f"	EnableAdvance {adv}")
                lines += [f"\tProductionCost {cost}", f"\tUpkeep {upkeep}"]
                lines.append("}")
                bld.add_block(ident, "\n".join(lines))
                merged += 1
    
    for ident, fields in {} .items():  # Dummy loop to keep rest of function intact
        if ident in bld.blocks:
            continue  # AE base building — keep verbatim
        icon = fields.get("IMPROVE_DEFAULT_ICON") or fields.get("DefaultIcon") or f"ICON_{ident}"
        desc = fields.get("IMPROVE_DESCRIPTION") or fields.get("Description") or f"DESCRIPTION_{ident}"
        adv = fields.get("ENABLING_ADVANCE") or fields.get("EnableAdvance") or ""
        adv = remap.get(adv, adv)
        if adv and adv not in advances:
            adv = fallback_adv
        cost = fields.get("IMPROVEMENT_PRODUCTION_COST") or fields.get("ProductionCost") or "100"
        upkeep = fields.get("IMPROVEMENT_UPKEEP") or fields.get("Upkeep") or "1"
        lines = [f"{ident} {{", f"\tDefaultIcon {icon}", f"\tDescription {desc}"]
        if adv:
            lines.append(f"\tEnableAdvance {adv}")
        lines += [f"\tProductionCost {cost}", f"\tUpkeep {upkeep}"]
        
        # NOTE: buildings.txt does NOT support NoIndex or GLHidden flags.
        # Injecting them here causes CTP2 parser corruption and Icon database errors.
        # Hidden base improvements are handled by omitting them from build lists instead.
            
        lines.append("}")
        bld.add_block(ident, "\n".join(lines))
        merged += 1
    _save_raw_block_file("default/gamedata/buildings.txt", bld)
    # Improve.txt is never loaded by the engine (not in gamefile.txt) — remove it so it
    # can't be mistaken for the live improvement DB.
    reg._parsed.pop("default/gamedata/Improve.txt", None)
    imp_path = SCENARIO / "default" / "gamedata" / "Improve.txt"
    if imp_path.exists():
        imp_path.unlink()
    print(f"  + reconstructed buildings.txt STRICTLY from control plane ({merged} records); removed dead Improve.txt")
    for _bname, _bcode, _badv in _fallback_gates:
        print(f"  ! prereq code {_bcode!r} for '{_bname}' is dangling or disabled "
              f"in advance_code_map.csv -> gated on fallback {_badv}")
    return merged


def _load_counted_icon_file(rel: str) -> P.CountedIconFile:
    file_obj = P.CountedIconFile()
    file_obj.parse(_read_rel(rel))
    return file_obj


def _load_base_counted_icon_file(rel: str) -> P.CountedIconFile:
    file_obj = P.CountedIconFile()
    file_obj.parse((CTP2_DATA / rel).read_text(encoding='latin-1'))
    return file_obj


def _save_counted_icon_file(rel: str, file_obj: P.CountedIconFile) -> None:
    _write_rel(rel, file_obj.render())


GOVERNICON_FALLBACK_IDS = {
    r["id"]: r["fallback"] for r in _policy_csv_rows("governicon_fallback.csv")
}


def _load_library_file(rel: str) -> P.LibraryFile:
    file_obj = P.LibraryFile()
    file_obj.parse(_read_rel(rel))
    return file_obj


def _load_base_library_file(rel: str) -> P.LibraryFile:
    file_obj = P.LibraryFile()
    file_obj.parse((CTP2_DATA / rel).read_text(encoding='latin-1'))
    return file_obj


def _restore_base_advance_gl_prose(
    gl_library: P.LibraryFile,
    base_gl_library: P.LibraryFile,
    advance_ids: set[str],
) -> int:
    """Restore stock advance gameplay/historical prose for sections that exist in base CTP2 data."""
    restored = 0
    for ident in sorted(advance_ids):
        if not ident.startswith("ADVANCE_"):
            continue
        for suffix in ("GAMEPLAY", "HISTORICAL"):
            section_id = f"{ident}_{suffix}"
            base_content = base_gl_library.sections.get(section_id)
            if not base_content:
                continue
            if gl_library.sections.get(section_id) != base_content:
                gl_library.sections[section_id] = base_content
                restored += 1
    return restored


def _normalize_uniticon_text_ref(value: str) -> str:
    token = (value or "").strip().strip('"')
    if not token or token.upper() == "NULL" or token.lower().endswith(".txt"):
        return ""
    return token


def _restore_missing_uniticon_gl_sections(
    uniticon_blocks: dict[str, dict[str, str]],
    gl_library: P.LibraryFile,
    base_gl_library: P.LibraryFile,
) -> int:
    """Backfill any uniticon-linked GL sections that exist in base data but are missing locally."""
    restored = 0
    seen_refs: set[str] = set()
    for fields in uniticon_blocks.values():
        for key in ("Gameplay", "Historical", "Prereq", "Vari", "StatText"):
            section_id = _normalize_uniticon_text_ref(fields.get(key, ""))
            if not section_id or section_id in seen_refs:
                continue
            seen_refs.add(section_id)
            if section_id in gl_library.sections:
                continue
            base_content = base_gl_library.sections.get(section_id)
            if not base_content:
                continue
            gl_library.sections[section_id] = base_content
            restored += 1
    return restored


def _save_library_file(rel: str, file_obj: P.LibraryFile) -> None:
    _write_rel(rel, file_obj.render())


def _load_string_file(rel: str) -> P.StringDBFile:
    file_obj = P.StringDBFile()
    file_obj.parse(_read_rel(rel))
    return file_obj


def _save_string_file(rel: str, file_obj: P.StringDBFile) -> None:
    _write_rel(rel, file_obj.render())


def _write_surrogate_register() -> None:
    scenario_root = SCENARIO.parent
    register_path = scenario_root / "SURROGATES.txt"
    lines = [
        f"{scenario_root.name} surrogate register",
        "",
        f"Primary structured source: {MOMJR}",
        "",
        "Hidden surrogate-backed tile improvements retained only for compatibility:",
    ]
    for ident in sorted(HIDDEN_SURROGATE_TILEIMPS):
        lines.append(f"- {ident}: {SURROGATE_TILEIMP_NOTES[ident]}")
    lines.extend(
        [
            "",
            "Visible remaps:",
            "- TILEIMP_RAILROAD: remapped to Enchanted Road and ADVANCE_GREATER_ENCHANTMENTS.",
            "",
            "Dynamic logic donor references live under:",
            f"- {Path(__file__).parent / 'slic_translation_artifacts'}",
        ]
    )
    register_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _raw_block_value(block_text: str, key: str) -> str:
    match = re.search(rf"^\s*{re.escape(key)}\s+(.+?)\s*$", block_text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _set_raw_block_value(block_text: str, key: str, value: str) -> str:
    """Set or insert a single-line raw-block field value."""
    pattern = re.compile(rf"^(\s*{re.escape(key)}\s+)(.+?)(\s*)$", re.MULTILINE)
    if pattern.search(block_text):
        return pattern.sub(lambda match: f"{match.group(1)}{value}{match.group(3)}", block_text, count=1)

    lines = block_text.splitlines()
    if len(lines) < 2:
        return block_text
    lines.insert(1, f"   {key} {value}")
    return "\n".join(lines)


def _raw_block_has_flag(block_text: str, flags: tuple[str, ...] = ("NoIndex", "GLHidden")) -> bool:
    pattern = '|'.join(re.escape(flag) for flag in flags)
    return bool(re.search(rf'^\s*(?:{pattern})\s*$', block_text, re.MULTILINE))


def _ensure_runtime_building_gl_surfaces(
    gl_strings: P.StringDBFile,
    gl_library: P.LibraryFile,
) -> tuple[int, int]:
    building_blocks: dict[str, str] = {}
    for rel in ("default/gamedata/Improve.txt", "default/gamedata/buildings.txt"):
        raw_text = _read_rel(rel)
        print(f"DEBUG BUILDING GL: rel={rel}, raw_text length={len(raw_text) if raw_text else 0}")
        if not raw_text:
            continue
        blocks = _load_raw_block_file(rel).blocks
        print(f"DEBUG BUILDING GL: {rel} has {len(blocks)} blocks")
        for ident, block_text in blocks.items():
            if not ident.startswith("IMPROVE_") or _raw_block_has_flag(block_text):
                continue
            building_blocks[ident] = block_text
    
    print(f"DEBUG BUILDING GL: building_blocks has {len(building_blocks)} items")
    print(f"DEBUG BUILDING GL: IMPROVE_AQUEDUCT in building_blocks: {'IMPROVE_AQUEDUCT' in building_blocks}")

    added_strings = 0
    added_sections = 0
    for ident, block_text in building_blocks.items():
        display_name = gl_strings.entries.get(ident, humanize_ident(ident, "IMPROVE_"))
        description_key = _raw_block_value(block_text, "Description")
        description_text = gl_strings.entries.get(
            description_key,
            f"{display_name} is a {MOD_DISPLAY_NAME} city improvement.",
        )
        advance_ident = _raw_block_value(block_text, "EnableAdvance")
        if ident not in gl_strings.entries:
            gl_strings.entries[ident] = display_name
            added_strings += 1
        if description_key and description_key not in gl_strings.entries:
            gl_strings.entries[description_key] = description_text
            added_strings += 1

        advance_label = gl_strings.entries.get(advance_ident, humanize_ident(advance_ident, "ADVANCE_"))
        sections = {
            f"{ident}_GAMEPLAY": description_text,
            f"{ident}_HISTORICAL": (
                f"{display_name} currently uses runtime building proxy data in the MoM scenario build."
            ),
            f"{ident}_PREREQ": f"Requires:\n<L:DATABASE_ADVANCES,{advance_ident}>{advance_label}<e>",
            f"{ident}_STATISTICS": f"<L:DATABASE_BUILDINGS,{ident}>{display_name}<e>",
        }
        for section_id, content in sections.items():
            if section_id not in gl_library.sections:
                gl_library.sections[section_id] = content
                added_sections += 1
    return added_strings, added_sections


def _ensure_runtime_unit_gl_surfaces(
    gl_strings: P.StringDBFile,
    gl_library: P.LibraryFile,
) -> tuple[int, int]:
    """Ensure live UNIT_* blocks have names and all four GL sections (GAMEPLAY, HISTORICAL, PREREQ, STATISTICS).

    This parallels _ensure_runtime_building_gl_surfaces but for units. MoM units from
    units.csv need full GL article generation since they don't exist in base CTP2.
    """
    # CRITICAL: Use the in-memory Units.txt from the registry, NOT from disk.
    # The MoM units are added to the registry object but not yet saved to disk.
    unit_blocks = reg.load("default/gamedata/Units.txt")
    added_strings = 0
    added_sections = 0

    # UnitsFile doesn't have .blocks, it has ._unit_ids and ._text.
    # We extract the block text for each unit using regex.
    # _unit_ids is a set; sorted iteration keeps regen output byte-stable
    # (unsorted set order made gl_str/Great_Library differ between runs).
    for ident in sorted(unit_blocks._unit_ids):
        if not ident.startswith("UNIT_"):
            continue
        
        # Extract block text for this unit
        pattern = rf'^({re.escape(ident)}\s*\{{.*?\n\}})'
        match = re.search(pattern, unit_blocks._text, re.MULTILINE | re.DOTALL)
        if not match:
            continue
        block_text = match.group(1)
        
        # Skip hidden base units (they have NoIndex/GLHidden flags)
        if re.search(r'^\s*(NoIndex|GLHidden)\s*$', block_text, re.MULTILINE):
            continue

        # Get display name from gl_strings or generate fallback
        display_name = gl_strings.entries.get(ident, humanize_ident(ident, "UNIT_"))
        # Ensure the unit has a display string entry
        if ident not in gl_strings.entries:
            gl_strings.entries[ident] = display_name
            added_strings += 1
        # Also ensure the SUMMARY entry exists for uniticon StatText
        summary_ident = f"{ident}_SUMMARY"
        if summary_ident not in gl_strings.entries:
            gl_strings.entries[summary_ident] = f"Summary of {display_name}."
            added_strings += 1

        # Get advance for prerequisite section
        advance_ident = _raw_block_value(block_text, "EnableAdvance") or "ADVANCE_WARRIOR_CODE"
        advance_label = gl_strings.entries.get(advance_ident, humanize_ident(advance_ident, "ADVANCE_"))

        # Build the five standard GL sections for this unit (including SUMMARY for uniticon Vari)
        sections = {
            f"{ident}_GAMEPLAY": f"{display_name} is a {MOD_DISPLAY_NAME} unit.",
            f"{ident}_HISTORICAL": f"{display_name} serves in the armies of {MOD_DISPLAY_NAME}.",
            f"{ident}_PREREQ": f"Requires:\n<L:DATABASE_ADVANCES,{advance_ident}>{advance_label}<e>",
            f"{ident}_STATISTICS": f"<L:DATABASE_UNITS,{ident}>{display_name}<e>",
            f"{ident}_SUMMARY": f"Summary of {display_name}.",
        }

        for section_id, content in sections.items():
            if section_id not in gl_library.sections:
                gl_library.sections[section_id] = content
                added_sections += 1

    return added_strings, added_sections


def _gl_desc_text(rel: str) -> str:
    """Current text of a scenario DB file, preferring unsaved in-memory content.

    reg.text() reads disk, which during a run still holds the PREVIOUS run's
    output -- deriving descriptions from that would quote last run's costs. Use
    the parsed object's render() whenever the file has been loaded this run.
    """
    obj = reg._parsed.get(rel)
    if obj is not None and hasattr(obj, "render"):
        return obj.render()
    return reg.text(rel)


def _section_base_id(section_id: str):
    for suffix in ("_GAMEPLAY", "_HISTORICAL", "_PREREQ", "_STATISTICS"):
        if section_id.endswith(suffix):
            return section_id[:-len(suffix)]
    return section_id


def _prune_gl_sections(library: P.LibraryFile, keep_ids: set[str], prefixes: tuple[str, ...]) -> int:
    removed = 0
    for section_id in list(library.sections):
        base_id = _section_base_id(section_id)
        if base_id.startswith(prefixes) and base_id not in keep_ids:
            del library.sections[section_id]
            removed += 1
    return removed


def _prune_gl_strings(strings: P.StringDBFile, keep_ids: set[str], prefixes: tuple[str, ...]) -> int:
    removed = 0
    for key in list(strings.entries):
        matched_id = None
        if key.startswith("DESCRIPTION_"):
            candidate = key[len("DESCRIPTION_"):]
            if candidate.startswith(prefixes):
                matched_id = candidate
        elif key.startswith(prefixes):
            matched_id = key
        if matched_id and matched_id not in keep_ids:
            del strings.entries[key]
            removed += 1
    return removed


def _strip_stale_database_links(library: P.LibraryFile, keep_ids: set[str], database_name: str, prefixes: tuple[str, ...]) -> int:
    prefix_group = '|'.join(re.escape(prefix) for prefix in prefixes)
    pattern = re.compile(
        rf'<L:{re.escape(database_name)},(({prefix_group})[A-Z0-9_]*)>(.*?)<e>'
    )
    removed = 0
    for section_id, content in list(library.sections.items()):
        def _replace(match):
            nonlocal removed
            ident = match.group(1)
            if ident in keep_ids:
                return match.group(0)
            removed += 1
            return match.group(3)
        library.sections[section_id] = pattern.sub(_replace, content)
    return removed


def _scrub_hidden_tileimp_gl_file(rel_path: str, hidden_tileimp_ids: set[str]) -> int:
    """Final raw-file pass to remove hidden tile-improvement GL sections and index links."""
    text = _read_rel(rel_path)
    removed = 0
    for ident in sorted(hidden_tileimp_ids):
        for suffix in ("PREREQ", "STATISTICS", "GAMEPLAY", "HISTORICAL"):
            section_pattern = re.compile(
                rf'\[{re.escape(ident)}_{suffix}\].*?\[END\](?:\r?\n)?',
                re.DOTALL,
            )
            text, count = section_pattern.subn('', text)
            removed += count
        link_pattern = re.compile(
            rf'<L:DATABASE_TILE_IMPROVEMENTS,{re.escape(ident)}>(.*?)<e>'
        )
        text, count = link_pattern.subn(r'\1', text)
        removed += count
    if removed:
        _write_rel(rel_path, text)
    return removed


def _scrub_dead_tileimp_surfaces() -> int:
    """Re-anchor every AI improvement list off a tile improvement the cap deleted.

    Require: scen tileimp.txt is the live terrain-improvement DB.
    Guarantee: no file the engine parses cites a TILEIMP_* absent from it.
    Why: the scenario ships an aidata/ directory but no ImprovementLists.txt, so
    the engine loaded the BASE copy -- whose IMPROVEMENT_LIST_MISC still pointed
    at TILEIMP_LISTENING_POSTS, one of the 17 industrial tileimps item 3 deleted.
    That surfaced in-game as "Listening Post not found in terrainimprovement
    database". Identical shape to the Pop.txt defect: the blind spot is base-tree
    fallback, not the file. Re-anchor rather than drop the list -- an empty AI
    list is an untested engine path, and TRADING_POST is the live misc-utility
    improvement the MISC list is for.
    """
    rel = "default/gamedata/tileimp.txt"
    live = set(re.findall(r"^(TILEIMP_[A-Z0-9_]+)\s*\{", _read_rel(rel), re.M))
    if not live:
        return 0
    changed = 0
    for rel, repl in (("default/aidata/ImprovementLists.txt",
                       "TILEIMP_TRADING_POST"),):
        text = _read_rel(rel)
        if not text:
            continue
        before = text
        text = re.sub(r"\bTILEIMP_[A-Z0-9_]+\b",
                      lambda m: m.group(0) if m.group(0) in live else repl, text)
        if text != before:
            changed += 1
            _write_rel(rel, text)
    return changed


def _scrub_dead_advance_surfaces() -> int:
    """Remove every Great Library surface naming an advance the tech cap cut.

    Require: Advance.txt is final (mask + re-layout have run).
    Guarantee: no GL section, GL index link, uniticon block or gl_str key names
    an ADVANCE_* absent from the live Advance.txt. Idempotent.
    Why: mom-db-error-class -- an orphan Great Library section referencing a
    missing advance surfaces as 'not found in Advance database' at load. The
    tech cap CREATES this surface, so the scrub ships with it, not after it.
    """
    live = set(re.findall(r"^(ADVANCE_[A-Z0-9_]+)\s*\{",
                          _read_rel("default/gamedata/Advance.txt"), re.M))
    removed = 0

    def _dead(text: str) -> set[str]:
        return {m for m in set(re.findall(r"\bADVANCE_[A-Z0-9_]+\b", text))
                if re.sub(r"_(GAMEPLAY|HISTORICAL|PREREQ|STATISTICS)$", "", m)
                not in live}

    for rel in ("english/gamedata/Great_Library.txt",
                "english/gamedata/WAW_Great_Library.txt"):
        text = _read_rel(rel)
        if not text:
            continue
        before = text
        for ident in sorted({re.sub(r"_(GAMEPLAY|HISTORICAL|PREREQ|STATISTICS)$", "", m)
                             for m in _dead(text)}):
            for suffix in ("PREREQ", "STATISTICS", "GAMEPLAY", "HISTORICAL"):
                text, n = re.subn(rf"\[{re.escape(ident)}_{suffix}\].*?\[END\](?:\r?\n)?",
                                  "", text, flags=re.DOTALL)
                removed += n
            text, n = re.subn(rf"<L:DATABASE_ADVANCES,{re.escape(ident)}>(.*?)<e>",
                              r"\1", text)
            removed += n
        if text != before:
            _write_rel(rel, text)

    # uniticon.txt: one ICON_ADVANCE_* block per line.
    #
    # ICON_ADVANCE_DEFAULT is NOT an advance icon -- it is the engine's fallback,
    # and ADVANCE_NA (the null sentinel the engine always keeps) points at it. Its
    # ident ADVANCE_DEFAULT is never a live advance, so the _dead() sweep pruned
    # it and the scenario died at load with a native "DB Error:
    # ICON_ADVANCE_DEFAULT not found in Icon database" modal -- invisible to every
    # static gate, because no *advance* record referenced it.
    rel = "default/gamedata/uniticon.txt"
    text = _read_rel(rel)
    if text:
        kept_lines = [l for l in text.splitlines(keepends=True)
                      if not (l.lstrip().startswith("ICON_ADVANCE_")
                              and not l.lstrip().startswith("ICON_ADVANCE_DEFAULT")
                              and _dead(l))]
        if len(kept_lines) != len(text.splitlines()):
            removed += len(text.splitlines()) - len(kept_lines)
            _write_rel(rel, "".join(kept_lines))

    # gl_str.txt: one "ADVANCE_X <tab> "Name"" key per line.
    rel = "english/gamedata/gl_str.txt"
    text = _read_rel(rel)
    if text:
        kept_lines = [l for l in text.splitlines(keepends=True)
                      if not (l.lstrip().startswith("ADVANCE_") and _dead(l))]
        if len(kept_lines) != len(text.splitlines()):
            removed += len(text.splitlines()) - len(kept_lines)
            _write_rel(rel, "".join(kept_lines))

    # Pop.txt: the specialist DB, parsed at civapp.cpp:1104 from g_pop_filename.
    #
    # The scenario did not ship this file, so the engine loaded the BASE copy --
    # whose POP_LABORER points at ADVANCE_INDUSTRIAL_REVOLUTION and POP_MERCHANT
    # at ADVANCE_ECONOMICS, both cut by the tech cap. AdvanceRecord's resolver
    # then killed the load with "Industrial Revolution not found in Advance
    # database" (it prints the DISPLAY NAME, not the ident, which is why the
    # ident greps came up empty). Every static gate was blind to it because they
    # only ever looked at files the scenario overrides.
    #
    # Re-anchor rather than delete: all five specialists stay playable, and both
    # replacements are mundane and pre-Renaissance, so the age cap holds.
    rel = "default/gamedata/Pop.txt"
    text = _read_rel(rel)
    if text:
        before = text
        for pop, advance in (("POP_LABORER", "ADVANCE_CONSTRUCTION"),
                             ("POP_MERCHANT", "ADVANCE_TRADE")):
            text = re.sub(
                rf"({re.escape(pop)}\s*\{{[^}}]*?EnableAdvance\s+)(ADVANCE_[A-Z0-9_]+)",
                lambda m, a=advance: m.group(1) + (a if m.group(2) not in live
                                                   else m.group(2)),
                text, flags=re.DOTALL)
        if text != before:
            removed += 1
            _write_rel(rel, text)
    return removed


def _scrub_hidden_tileimp_gl_prose(rel_path: str, hidden_tileimp_ids: set[str]) -> int:
    """Final raw-file pass to remove hidden tile-improvement plain-text mentions."""
    text = _read_rel(rel_path)
    removed = 0
    for ident in sorted(hidden_tileimp_ids):
        name = humanize_ident(ident, "TILEIMP_")
        for phrase in {name, f"{name}s"}:
            pattern = re.compile(rf'(?m)^[ \t]*{re.escape(phrase)}\r?\n')
            text, count = pattern.subn("", text)
            removed += count
    for old, new in HIDDEN_TILEIMP_GREAT_LIBRARY_TEXT:
        text, count = re.subn(re.escape(old), new, text)
        removed += count
    if removed:
        _write_rel(rel_path, text)
    return removed


def _scrub_hidden_order_gl_file(rel_path: str, hidden_order_ids: set[str]) -> int:
    """Final raw-file pass to remove hidden order GL sections and links."""
    text = _read_rel(rel_path)
    removed = 0
    for ident in sorted(hidden_order_ids):
        for suffix in ("PREREQ", "STATISTICS", "GAMEPLAY", "HISTORICAL"):
            section_pattern = re.compile(
                rf'^\[{re.escape(ident)}_{suffix}\]\r?\n.*?^\[END\]\r?\n?',
                re.MULTILINE | re.DOTALL,
            )
            text, count = section_pattern.subn('', text)
            removed += count
        link_pattern = re.compile(
            rf'<L:DATABASE_ORDERS,{re.escape(ident)}>(.*?)<e>'
        )
        text, count = link_pattern.subn(r'\1', text)
        removed += count
    if removed:
        _write_rel(rel_path, text)
    return removed


def _scrub_hidden_concept_gl_file(rel_path: str, hidden_concept_ids: set[str]) -> int:
    """Final raw-file pass to remove hidden concept GL sections and links."""
    text = _read_rel(rel_path)
    removed = 0
    for ident in sorted(hidden_concept_ids):
        for suffix in ("GAMEPLAY", "HISTORICAL"):
            section_pattern = re.compile(
                rf'^\[{re.escape(ident)}_{suffix}\]\r?\n.*?^\[END\]\r?\n?',
                re.MULTILINE | re.DOTALL,
            )
            text, count = section_pattern.subn('', text)
            removed += count
        link_pattern = re.compile(
            rf'<L:DATABASE_CONCEPTS,{re.escape(ident)}>(.*?)<e>'
        )
        text, count = link_pattern.subn(r'\1', text)
        removed += count
    if removed:
        _write_rel(rel_path, text)
    return removed


def _filter_counted_icon_entries(file_obj: P.CountedIconFile, keep_ids: set[str]) -> int:
    kept = []
    removed = 0
    for entry in file_obj.entries:
        icon_id = entry.split('\t', 1)[0].strip()
        if icon_id in keep_ids:
            kept.append(entry)
        else:
            removed += 1
    file_obj.entries = kept
    return removed


def _strip_raw_block_flags(file_obj: P.RawBlockTextFile, flags: set[str]) -> int:
    changed = 0
    for ident, block_text in list(file_obj.blocks.items()):
        lines = block_text.splitlines(keepends=True)
        kept_lines = [line for line in lines if line.strip() not in flags]
        if len(kept_lines) != len(lines):
            file_obj.add_block(ident, ''.join(kept_lines).rstrip('\n'))
            changed += 1
    return changed


def _replace_block_text(file_obj: P.RawBlockTextFile, ident: str, replacements: list[tuple[str, str]]) -> bool:
    block_text = file_obj.blocks.get(ident)
    if not block_text:
        return False

    updated = block_text
    for old, new in replacements:
        updated = updated.replace(old, new)

    if updated == block_text:
        return False

    file_obj.add_block(ident, updated)
    return True


def _parse_goods_numeric_ids() -> dict[str, int]:
    mapping = {}
    for line in _read_rel("default/gamedata/goodsID.txt").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        match = re.match(r'^([A-Z0-9_]+)\s+(\d+)\b', stripped)
        if match:
            mapping[match.group(1)] = int(match.group(2))
    return mapping


def _extract_referenced_ids(rel_paths: list[str], pattern: str) -> set[str]:
    found = set()
    for rel in rel_paths:
        found.update(re.findall(pattern, _read_rel(rel)))
    return found


def _government_ids_enabled_by_live_advances(
    govern_blocks: dict[str, str],
    live_advance_ids: set[str],
) -> set[str]:
    live_governments = {"GOVERNMENT_ANARCHY"}
    for ident, block_text in govern_blocks.items():
        if ident == "GOVERNMENT_ANARCHY":
            continue
        enable_advance = _raw_block_value(block_text, "EnableAdvance")
        if enable_advance and enable_advance in live_advance_ids:
            live_governments.add(ident)
    return live_governments





def _prune_government_advice_lines(rel: str, keep_ids: set[str]) -> int:
    removed = 0
    kept_lines = []
    for line in _read_rel(rel).splitlines():
        stripped = line.strip()
        match = re.match(r'^(GOVERNMENT_[A-Z0-9_]+)_(SAME|HIGHER)_RANK_ADVICE\b', stripped)
        if match and match.group(1) not in keep_ids:
            removed += 1
            continue
        kept_lines.append(line)
    if removed:
        _write_rel(rel, '\n'.join(kept_lines))
    return removed


def _prune_strategy_government_lines(rel: str, keep_ids: set[str]) -> int:
    removed = 0
    kept_lines = []
    for line in _read_rel(rel).splitlines():
        match = re.match(r'^(\s*Government\s+)(GOVERNMENT_[A-Z0-9_]+)(\s*)$', line)
        if match and match.group(2) not in keep_ids:
            removed += 1
            continue
        kept_lines.append(line)
    if removed:
        _write_rel(rel, '\n'.join(kept_lines))
    return removed


def _write_empty_wonder_build_lists() -> None:
    """Write a scenario aidata override so stock wonder AI lists cannot leak in."""
    rel = Path("default/aidata/WonderBuildLists.txt")
    path = SCENARIO / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#----------------------------------------------------------------------------\n"
        "#\n"
        "# MoM scenario override -- do not edit ctp2_data version for scenario changes.\n"
        "# Sync this file whenever the scenario wonder lane changes.\n"
        "#\n"
        "# The current MOMJR translation owns a 28-entry WonderDB lane. Keep these lists\n"
        "# empty so the engine does not fall back to stock aidata wonder references.\n"
        "#\n"
        "#----------------------------------------------------------------------------\n"
        "\n"
        "# 7\n"
        "\n"
        "WONDER_BUILD_LIST_HAPPINESS {\n"
        "}\n"
        "\n"
        "WONDER_BUILD_LIST_GROWTH {\n"
        "}\n"
        "\n"
        "WONDER_BUILD_LIST_PRODUCTION {\n"
        "}\n"
        "\n"
        "WONDER_BUILD_LIST_GOLD {\n"
        "}\n"
        "\n"
        "WONDER_BUILD_LIST_OFFENSE {\n"
        "}\n"
        "\n"
        "WONDER_BUILD_LIST_DEFENSE {\n"
        "}\n"
        "\n"
        "WONDER_BUILD_LIST_SCIENCE {\n"
        "}\n"
        "\n"
        "### ALL WONDERS DONE ###\n",
        encoding='latin-1',
    )


def _scan_unit_blocks(text: str) -> dict[str, str]:
    """Return nested-brace-safe UNIT_* blocks keyed by unit ID."""
    blocks: dict[str, str] = {}
    lines = text.splitlines(keepends=True)
    i = 0
    while i < len(lines):
        match = re.match(r'^(UNIT_[A-Z0-9_]+)\s*\{', lines[i])
        if not match:
            i += 1
            continue
        ident = match.group(1)
        depth = 0
        block_lines = []
        while i < len(lines):
            block_lines.append(lines[i])
            depth += lines[i].count('{') - lines[i].count('}')
            i += 1
            if len(block_lines) > 1 and depth <= 0:
                break
        blocks[ident] = ''.join(block_lines)
    return blocks


def _unit_block_int(block_text: str, key: str, default: int = 0) -> int:
    match = re.search(rf'^\s*{re.escape(key)}\s+(-?\d+)\b', block_text, re.MULTILINE)
    return int(match.group(1)) if match else default


def _unit_block_value(block_text: str, key: str, default: str = "") -> str:
    match = re.search(rf'^\s*{re.escape(key)}\s+(\S+)\b', block_text, re.MULTILINE)
    return match.group(1) if match else default


def _scan_wonder_blocks(text: str) -> dict[str, str]:
    """Return nested-brace-safe WONDER_* blocks keyed by wonder ID."""
    blocks: dict[str, str] = {}
    lines = text.splitlines(keepends=True)
    i = 0
    while i < len(lines):
        match = re.match(r'^(WONDER_[A-Z0-9_]+)\s*\{', lines[i])
        if not match:
            i += 1
            continue
        ident = match.group(1)
        depth = 0
        block_lines = []
        while i < len(lines):
            block_lines.append(lines[i])
            depth += lines[i].count('{') - lines[i].count('}')
            i += 1
            if len(block_lines) > 1 and depth <= 0:
                break
        blocks[ident] = ''.join(block_lines)
    return blocks


def _scan_advance_blocks(text: str) -> dict[str, str]:
    """Return nested-brace-safe ADVANCE_* blocks keyed by advance ID."""
    blocks: dict[str, str] = {}
    lines = text.splitlines(keepends=True)
    i = 0
    while i < len(lines):
        match = re.match(r'^(ADVANCE_[A-Z0-9_]+)\s*\{', lines[i])
        if not match:
            i += 1
            continue
        ident = match.group(1)
        depth = 0
        block_lines = []
        while i < len(lines):
            block_lines.append(lines[i])
            depth += lines[i].count('{') - lines[i].count('}')
            i += 1
            if len(block_lines) > 1 and depth <= 0:
                break
        blocks[ident] = ''.join(block_lines)
    return blocks


def _advance_age_map_from_text(text: str) -> dict[str, str]:
    """Return ADVANCE_* -> AGE_* from generated or base Advance.txt text."""
    return {
        ident: _unit_block_value(block_text, "Age", "AGE_ONE")
        for ident, block_text in _scan_advance_blocks(text).items()
    }


def _base_advance_age_map() -> dict[str, str]:
    """Return base CTP2 ADVANCE_* -> AGE_* mapping."""
    path = CTP2_DATA / "default" / "gamedata" / "Advance.txt"
    if not path.exists():
        return {}
    return _advance_age_map_from_text(path.read_text(encoding="latin-1"))


def _load_ae_advance_cost_bands() -> dict[str, tuple[int, int]]:
    """Return the sane per-Age (low, high) research-cost bands MoM rescales into.

    Previously these were derived from the base Apolyton-Edition Advance.txt, whose bands
    are pathological (AGE_SIX 18876-55927, AGE_TEN 142969-234743). Projecting MoM costs into
    them made mid/late research take thousands of turns, and the AE tail (AGE_FOUR-TEN) plus
    the Cost=1 outlier drove the median to 775 / max to 234743. This replaces them with a
    fixed, monotonic, absolute curve anchored so AGE_ONE first techs cost <640 (<40 turns at
    ~16 science/turn) and AGE_TEN caps in the low tens of thousands (~50-140 turns at
    late-game science). Every advance is now retuned into this curve (the coverage gate in
    _retune_mom_advance_costs is removed), so no raw base/WAW tail survives. Tune here.
    """
    return {
        r["age"]: (int(r["low"]), int(r["high"]))
        for r in _policy_csv_rows("advance_cost_bands.csv")
    }


def _load_ae_unit_cost_bands() -> dict[str, tuple[int, int]]:
    """Return base CTP2 unit ShieldCost bands keyed by Age."""
    units_path = CTP2_DATA / "default" / "gamedata" / "Units.txt"
    advance_ages = _base_advance_age_map()
    if not units_path.exists() or not advance_ages:
        return {}
    bands: dict[str, list[int]] = {}
    for block_text in _scan_unit_blocks(units_path.read_text(encoding="latin-1")).values():
        if re.search(r'^\s*(NoIndex|GLHidden)\s*$', block_text, re.MULTILINE):
            continue
        cost = _unit_block_int(block_text, "ShieldCost")
        if cost <= 0:
            continue
        advance = _unit_block_value(block_text, "EnableAdvance", "ADVANCE_WARRIOR_CODE")
        age = advance_ages.get(advance, "AGE_ONE")
        bands.setdefault(age, []).append(cost)
    return {
        age: (min(values), max(values))
        for age, values in bands.items()
        if values
    }


def _load_ae_wonder_cost_bands() -> dict[str, tuple[int, int]]:
    """Return base CTP2 wonder ProductionCost bands keyed by Age."""
    wonders_path = CTP2_DATA / "default" / "gamedata" / "Wonder.txt"
    advance_ages = _base_advance_age_map()
    if not wonders_path.exists() or not advance_ages:
        return {}
    bands: dict[str, list[int]] = {}
    for block_text in _scan_wonder_blocks(wonders_path.read_text(encoding="latin-1")).values():
        cost = _unit_block_int(block_text, "ProductionCost")
        if cost <= 0:
            continue
        advance = _unit_block_value(block_text, "EnableAdvance", "ADVANCE_WARRIOR_CODE")
        age = advance_ages.get(advance, "AGE_ONE")
        bands.setdefault(age, []).append(cost)
    return {
        age: (min(values), max(values))
        for age, values in bands.items()
        if values
    }


def _scale_cost_into_band(
    source_cost: int,
    source_band: tuple[int, int],
    target_band: tuple[int, int],
    round_to: int,
) -> int:
    """Project a Civ2-side source cost into the target CTP2 age band."""
    source_low, source_high = source_band
    target_low, target_high = target_band
    if source_high <= source_low:
        scaled = (target_low + target_high) / 2.0
    else:
        clamped = max(source_low, min(source_high, source_cost))
        scaled = target_low + (
            (target_high - target_low) * ((clamped - source_low) / float(source_high - source_low))
        )
    rounded = int(round(scaled / float(round_to)) * round_to)
    return max(target_low, min(target_high, rounded))


def _load_mom_unit_source_cost_bands(
    advance_ages: dict[str, str],
) -> tuple[dict[str, tuple[int, str]], dict[str, tuple[int, int]]]:
    """Return raw MOMJR unit costs keyed by UNIT_* plus age bands."""
    bands: dict[str, list[int]] = {}
    specs: dict[str, tuple[int, str]] = {}
    with open(MOMJR / "units.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = row["name"].strip()
            if not name or name.lower() == "blah":
                continue
            if len(name) == 2 and name[0] == "B" and name[1].isdigit():
                continue
            prereq = row["prereq"].strip()
            if prereq in _NO_ADVANCE:
                advance = "ADVANCE_WARRIOR_CODE"
            else:
                advance = MOM_UNIT_ADVANCE.get(prereq, "ADVANCE_WARRIOR_CODE")
                if advance not in advance_ages:
                    advance = "ADVANCE_WARRIOR_CODE"
            age = advance_ages.get(advance, "AGE_ONE")
            source_cost = int(row["cost"].strip() or "1")
            ident = f"UNIT_{sanitize(name)}"
            specs[ident] = (source_cost, age)
            bands.setdefault(age, []).append(source_cost)
    return specs, {
        age: (min(values), max(values))
        for age, values in bands.items()
        if values
    }


def _retune_mom_unit_costs(units_file: "P.UnitsFile", advance_ages: dict[str, str]) -> int:
    """Rewrite live MoM unit ShieldCost values into base CTP2 age bands."""
    ae_bands = _load_ae_unit_cost_bands()
    unit_specs, source_bands = _load_mom_unit_source_cost_bands(advance_ages)
    if not ae_bands or not unit_specs or not source_bands:
        return 0
    changed = 0
    unit_blocks = _scan_unit_blocks(units_file._text)
    for ident, block_text in unit_blocks.items():
        source_spec = unit_specs.get(ident)
        if not source_spec:
            continue
        source_cost, age = source_spec
        source_band = source_bands.get(age)
        if not source_band:
            continue
        target_band = _nearest_ae_cost_band(age, ae_bands)
        new_cost = _scale_cost_into_band(source_cost, source_band, target_band, 10)
        current_cost = _unit_block_int(block_text, "ShieldCost")
        if current_cost == new_cost:
            continue
        updated_block = _set_raw_block_value(block_text, "ShieldCost", str(new_cost))
        updated_block = _set_raw_block_value(updated_block, "PowerPoints", str(max(100, new_cost // 2)))
        units_file._text = units_file._text.replace(block_text, updated_block, 1)
        unit_blocks[ident] = updated_block
        changed += 1
    return changed


def _load_mom_wonder_source_specs(
    advance_ages: dict[str, str],
) -> tuple[dict[str, tuple[int, str]], dict[str, tuple[int, int]]]:
    """Return raw MOMJR wonder costs keyed by WONDER_* plus age bands."""
    specs: dict[str, tuple[int, str]] = {}
    bands: dict[str, list[int]] = {}
    with open(MOMJR / "improvements.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = row.get("name", "").strip()
            if not name:
                continue
            
            # If the name starts with "HIDE ", mark it for removal but keep processing to inject flags
            is_hidden = name.upper().startswith("HIDE ")
            if is_hidden:
                name = name[5:].strip()
            
            cell_index = int(row.get("cell_index", "0").strip() or "0")
            if cell_index < 40 and not is_hidden:
                continue
            
            improve_id = f"IMPROVE_{sanitize(name)}"
            wonder_id = improve_id.replace("IMPROVE_", "WONDER_", 1)
            prereq_code = row.get("prereq", "").strip()
            advance = advance_id(prereq_code) if prereq_code else ""
            age = advance_ages.get(advance, "AGE_ONE") if advance else "AGE_ONE"
            source_cost = int(row.get("cost", "0").strip() or "0")
            
            if cell_index >= 40:
                specs[wonder_id] = (source_cost, age)
                bands.setdefault(age, []).append(source_cost)
            
            # If marked as HIDE, we still register it so the generator can apply GLHidden/NoIndex later
            if is_hidden:
                specs[wonder_id] = (source_cost, age)
                bands.setdefault(age, []).append(source_cost)
    return specs, {
        age: (min(values), max(values))
        for age, values in bands.items()
        if values
    }


def _retune_mom_wonder_costs(advance_ages: dict[str, str]) -> int:
    """Rewrite MoM wonder costs into base CTP2 age bands from raw MOMJR costs."""
    ae_bands = _load_ae_wonder_cost_bands()
    wonder_specs, source_bands = _load_mom_wonder_source_specs(advance_ages)
    if not ae_bands or not wonder_specs or not source_bands:
        return 0
    rel = "default/gamedata/Wonder.txt"
    wonder_file = _load_raw_block_file(rel)
    changed = 0
    for ident, block_text in list(wonder_file.blocks.items()):
        source_spec = wonder_specs.get(ident)
        if not source_spec:
            continue
        source_cost, age = source_spec
        source_band = source_bands.get(age)
        if not source_band:
            continue
        target_band = _nearest_ae_cost_band(age, ae_bands)
        new_cost = _scale_cost_into_band(source_cost, source_band, target_band, 10)
        if _unit_block_int(block_text, "ProductionCost") == new_cost:
            continue
        wonder_file.add_block(ident, _set_raw_block_value(block_text, "ProductionCost", str(new_cost)))
        changed += 1
    if changed:
        _save_raw_block_file(rel, wonder_file)
        refreshed = P.WonderFile()
        refreshed.parse(_read_rel(rel))
        reg._parsed[rel] = refreshed
    return changed


def _scan_improve_blocks(text: str) -> dict[str, str]:
    """Return nested-brace-safe IMPROVE_* blocks keyed by improvement ID."""
    blocks: dict[str, str] = {}
    lines = text.splitlines(keepends=True)
    i = 0
    while i < len(lines):
        match = re.match(r'^(IMPROVE_[A-Z0-9_]+)\s*\{', lines[i])
        if not match:
            i += 1
            continue
        ident = match.group(1)
        depth = 0
        block_lines = []
        while i < len(lines):
            block_lines.append(lines[i])
            depth += lines[i].count('{') - lines[i].count('}')
            i += 1
            if len(block_lines) > 1 and depth <= 0:
                break
        blocks[ident] = ''.join(block_lines)
    return blocks


def _load_ae_improvement_cost_bands() -> dict[str, tuple[int, int]]:
    """Return base CTP2 improvement ProductionCost bands keyed by Age.

    First-age reference points (base/AE buildings.txt): Ballista Towers 525,
    Bazaar 525, Academy 540, Arena 675, Aqueduct 875.
    """
    buildings_path = CTP2_DATA / "default" / "gamedata" / "buildings.txt"
    advance_ages = _base_advance_age_map()
    if not buildings_path.exists() or not advance_ages:
        return {}
    bands: dict[str, list[int]] = {}
    for block_text in _scan_improve_blocks(buildings_path.read_text(encoding="latin-1")).values():
        cost = _unit_block_int(block_text, "ProductionCost")
        if cost <= 0:
            continue
        advance = _unit_block_value(block_text, "EnableAdvance", "ADVANCE_WARRIOR_CODE")
        age = advance_ages.get(advance, "AGE_ONE")
        bands.setdefault(age, []).append(cost)
    return {
        age: (min(values), max(values))
        for age, values in bands.items()
        if values
    }


def _load_mom_improvement_source_specs(
    advance_ages: dict[str, str],
) -> tuple[dict[str, tuple[int, str]], dict[str, tuple[int, int]]]:
    """Return raw MOMJR improvement costs keyed by IMPROVE_* plus age bands.

    ALL improvements.csv rows are included: rows with cell_index >= 40 are
    wonders, but ingestion emits an IMPROVE_ block for every row, so those
    need improvement-band pricing too (they show in the Buildings tab).
    'HIDE X' rows are mask directives, not content.
    """
    specs: dict[str, tuple[int, str]] = {}
    bands: dict[str, list[int]] = {}
    with open(MOMJR / "improvements.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = row.get("name", "").strip()
            if not name or name.lower() == "blah" or name.upper().startswith("HIDE "):
                continue
            source_cost = int(row.get("cost", "0").strip() or "0")
            if source_cost <= 0:
                continue
            prereq_code = row.get("prereq", "").strip()
            advance = advance_id(prereq_code) if prereq_code else ""
            age = advance_ages.get(advance, "AGE_ONE") if advance else "AGE_ONE"
            specs[f"IMPROVE_{sanitize(name)}"] = (source_cost, age)
            bands.setdefault(age, []).append(source_cost)
    return specs, {
        age: (min(values), max(values))
        for age, values in bands.items()
        if values
    }


# --- Sphere gating: move sphere'd content onto its own ladder rung -----------
#
# The five tribes are only distinct if their content is. Faction identity lives
# in the `sphere` column of units.csv / improvements.csv; this pass is what
# turns that column into an enforced tech gate by rewriting EnableAdvance.
#
# The advance ident is DERIVED from (sphere, tier) rather than looked up in
# advance_code_map.csv, deliberately: the map's `prereq` lane is incomplete for
# the ladders and actively wrong for three codes ('Inv' means INVENTION there,
# not LIFE_LORE), so routing improvements through it would mis-gate them. The
# derivation is verified against the generated Advance.txt by the gate.
_SPHERE_TIERS = ["lore", "adept", "mage", "wizard", "master"]

# Short-code -> (sphere, tier). A prereq already sitting on one of these rungs
# is an AUTHORED decision and outranks any cost-derived guess.
_SPHERE_LADDER_CODES = {
    code: (sphere, _SPHERE_TIERS[i])
    for sphere, codes in {
        "life":    ["Inv", "Lab", "Las", "Too", "Mag"],
        "nature":  ["Plu", "PT",  "Rad", "Rec", "Ref"],
        "death":   ["Rfg", "Rob", "SFl", "Sth", "SE"],
        "chaos":   ["MP",  "Med", "Met", "Min", "Mob"],
        "sorcery": ["The", "X2",  "NP",  "Phy", "Pla"],
    }.items()
    for i, code in enumerate(codes)
}


def _sphere_rung_advance(sphere: str, tier: str) -> str:
    """(sphere, tier) -> the ADVANCE_* ident for that ladder rung.

    One irregular name, honoured verbatim because the advance really is called
    this: the Sorcery lore rung is ADVANCE_SORCEROUS_LORE, not
    ADVANCE_SORCERY_LORE. Every other rung is regular.
    """
    if sphere == "sorcery" and tier == "lore":
        return "ADVANCE_SORCEROUS_LORE"
    return f"ADVANCE_{sphere.upper()}_{tier.upper()}"


def _sphere_cost_tier(cost: int) -> str:
    """Seed a tier from production cost. ONLY for rows with no ladder prereq.

    Measured 2026-07-26: against the 20 summon units that DO carry an authored
    ladder prereq, this heuristic disagrees on 8 -- and every disagreement
    demotes a master-tier summon (Undead Dragon, cost 3, would land on `lore`,
    a turn-1 dragon). So it must never override an authored rung.
    """
    if cost <= 4:   return "lore"
    if cost <= 8:   return "adept"
    if cost <= 15:  return "mage"
    if cost <= 40:  return "wizard"
    return "master"


def sphere_gate_targets() -> dict[str, str]:
    """THE SHARED PREDICATE: block ident -> the advance it must gate on.

    Owned here so `gate_faction_gating.py` reports on exactly what this pass
    writes; the two cannot drift apart. Rows whose sphere is `neutral` (or
    blank) are absent from the result -- they are deliberately universal and
    keep whatever prereq they already had.
    """
    targets: dict[str, str] = {}
    for csv_name, prefixes in (("units.csv", ("UNIT_",)),
                               ("improvements.csv", ("IMPROVE_", "WONDER_"))):
        path = MOMJR / csv_name
        if not path.exists():
            continue
        with open(str(path), newline="", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                sphere = (row.get("sphere") or "").strip()
                if sphere not in {"life", "nature", "death", "chaos", "sorcery"}:
                    continue
                prereq = (row.get("prereq") or "").strip()
                if prereq in _SPHERE_LADDER_CODES:
                    # Authored rung wins outright.
                    tier = _SPHERE_LADDER_CODES[prereq][1]
                else:
                    tier = _sphere_cost_tier(
                        int(re.sub(r"[^0-9]", "", str(row.get("cost", "0"))) or 0))
                advance = _sphere_rung_advance(sphere, tier)
                base = sanitize(row.get("name", ""))
                for prefix in prefixes:
                    targets[prefix + base] = advance
    return targets


# Tribe player index, fixed by the SLIC faction predicates (mom_func.slc
# MomPlayerIsLife is p == 1, ... MomPlayerIsChaos is p == 5) and corroborated by
# the summon table in mom_msg.slc. Player 0 is the barbarian.
_SPHERE_PLAYER = {"life": 1, "nature": 2, "sorcery": 3, "death": 4, "chaos": 5}

_GATING_SLC_REL = "default/gamedata/mom_gating.slc"


def _sphere_ladder_idents(sphere: str) -> list[str]:
    """Root + five rungs for one sphere, in ladder order.

    The Sorcery root is ADVANCE_SORCERY (not ..._SORCERY_MAGIC) and its lore
    rung is ADVANCE_SORCEROUS_LORE -- the only two irregular names in the tree.
    """
    root = "ADVANCE_SORCERY" if sphere == "sorcery" else f"ADVANCE_{sphere.upper()}_MAGIC"
    return [root] + [_sphere_rung_advance(sphere, tier) for tier in _SPHERE_TIERS]


def _emit_mom_gating_slc() -> int:
    """Write mom_gating.slc: the per-tribe who-gets-what wall. Returns idents emitted.

    Require: Advance.txt, Units.txt, buildings.txt and Wonder.txt are FINAL --
    every ident is filtered against the live block names, so a stale run would
    emit a dangling ref (mom-db-error-class) or silently drop a real one.
    Guarantee: bodies are FLAT (no user-function call -- a 2-level chain from an
    engine callback is a 0xC0000005), every comparison goes through
    AdvanceDB()/UnitDB()/BuildingDB()/WonderDB(), and the player guard is first
    because ResetCanResearch calls the advance hook once per advance per player.
    Identity: g.player on the advance hook -- the thePlayer PARAMETER is built as
    SLIC_SYM_PLAYER and SetIntValue only writes SLIC_SYM_IVAR, so reading it
    always yields 0 (probe B3). theCity.owner on the build hooks (probe B2).
    """
    def _blocks(rel: str, prefix: str) -> set[str]:
        return set(re.findall(rf"^({prefix}[A-Z0-9_]+)\s*\{{", _read_rel(rel), re.M))

    live_adv = _blocks("default/gamedata/Advance.txt", "ADVANCE_")
    live = {
        "unit":  (_blocks("default/gamedata/Units.txt", "UNIT_"), "UnitDB"),
        "bldg":  (_blocks("default/gamedata/buildings.txt", "IMPROVE_"), "BuildingDB"),
        "wndr":  (_blocks("default/gamedata/Wonder.txt", "WONDER_"), "WonderDB"),
    }

    targets = sphere_gate_targets()
    by_sphere: dict[str, dict[str, list[str]]] = {
        s: {"advance": [], "unit": [], "bldg": [], "wndr": []} for s in _SPHERE_PLAYER}
    for sphere in _SPHERE_PLAYER:
        by_sphere[sphere]["advance"] = [a for a in _sphere_ladder_idents(sphere)
                                        if a in live_adv]
    for ident, advance in sorted(targets.items()):
        # The sphere is read back off the gate advance, so the wall and the
        # prereq rewrite cannot disagree about which tribe owns a block.
        sphere = next((s for s in _SPHERE_PLAYER
                       if advance in _sphere_ladder_idents(s)), None)
        if sphere is None:
            continue
        for kind, (idents, _) in live.items():
            if ident in idents:
                by_sphere[sphere][kind].append(ident)

    def _deny_block(kind: str, var: str, owner: str, indent: str = "    ") -> list[str]:
        db = "AdvanceDB" if kind == "advance" else live[kind][1]
        out: list[str] = []
        for sphere, index in sorted(_SPHERE_PLAYER.items(), key=lambda kv: kv[1]):
            idents = by_sphere[sphere][kind]
            if not idents:
                continue
            terms = [f"{var} == {db}({i})" for i in idents]
            out.append(f"{indent}// {sphere.upper()} -- {len(idents)} block(s)")
            out.append(f"{indent}if ({owner} != {index}) {{")
            out.append(f"{indent}    if ({terms[0]}")
            for term in terms[1:]:
                out.append(f"{indent}    || {term}")
            out.append(f"{indent}    ) {{ return 0; }}")
            out.append(f"{indent}}}")
        return out

    lines = [
        "// mom_gating.slc -- GENERATED by tools/ctp2_generator.py. DO NOT HAND-EDIT.",
        "//",
        "// The per-tribe who-gets-what wall, via the engine's four mod functions",
        "// (SlicEngine::AddModFuncs, gs/slic/SlicEngine.cpp:3092; bound after scenario",
        "// segments compile, :1020). Shipped reference: AlexanderTheGreat/AG_mod.slc.",
        "//",
        "// IDENTITY, settled by the step-0 probe campaign (2026-07-26):",
        "//   * advance hook -> g.player. The thePlayer PARAMETER CANNOT carry identity:",
        "//     CallMod builds it as SLIC_SYM_PLAYER and SetIntValue only writes when the",
        "//     type is SLIC_SYM_IVAR, so the index is never stored and reads return 0.",
        "//   * build hooks -> theCity.owner, proven to resolve (probe B2).",
        "//",
        "// CONSTRAINTS honoured here (slic-two-crash-classes):",
        "//   * bodies are FLAT -- a 2-level user-function chain from an engine callback",
        "//     is an access violation.",
        "//   * every comparison goes through AdvanceDB()/UnitDB()/BuildingDB()/WonderDB().",
        "//   * the player guard is FIRST: ResetCanResearch calls the advance hook once",
        "//     per advance per player.",
        "//",
        "// Every ident below was filtered against the live generated DB at emit time, so",
        "// a typo cannot survive here (mom-db-error-class).",
        "",
        "int_f mod_CanPlayerHaveAdvance(int_t thePlayer, int_t theAdvance)",
        "{",
        "    // Barbarians and any out-of-range player are unrestricted.",
        "    if (g.player < 1 || g.player > 5) { return 1; }",
        *_deny_block("advance", "theAdvance", "g.player"),
        "    return 1;",
        "}",
        "",
        "int_f mod_CanCityBuildUnit(city_t theCity, int_t theUnit)",
        "{",
        "    if (theCity.owner < 1 || theCity.owner > 5) { return 1; }",
        *_deny_block("unit", "theUnit", "theCity.owner"),
        "    return 1;",
        "}",
        "",
        "int_f mod_CanCityBuildBuilding(city_t theCity, int_t theBuilding)",
        "{",
        "    if (theCity.owner < 1 || theCity.owner > 5) { return 1; }",
        *_deny_block("bldg", "theBuilding", "theCity.owner"),
        "    return 1;",
        "}",
        "",
        "int_f mod_CanCityBuildWonder(city_t theCity, int_t theWonder)",
        "{",
        "    if (theCity.owner < 1 || theCity.owner > 5) { return 1; }",
        *_deny_block("wndr", "theWonder", "theCity.owner"),
        "    return 1;",
        "}",
        "",
    ]
    _write_rel(_GATING_SLC_REL, "\n".join(lines))
    return sum(len(v[k]) for v in by_sphere.values() for k in v)


_ADVANCE_MASK ={r["id"] for r in _policy_csv_rows("advance_mask.csv")}
_ADVANCE_REANCHOR = _policy_csv_rows("advance_reanchor.csv")

_AGE_NAMES = ["", "AGE_ONE", "AGE_TWO", "AGE_THREE", "AGE_FOUR", "AGE_FIVE",
              "AGE_SIX", "AGE_SEVEN", "AGE_EIGHT", "AGE_NINE", "AGE_TEN"]
_AGE_NUMBER = {name: n for n, name in enumerate(_AGE_NAMES) if name}

# Renaissance cap: no MUNDANE advance may sit past AGE_FOUR. Ages 5+ are
# purely magical, which is what makes "Masters of Magic tech split across
# ages" true rather than a claim.
_MUNDANE_MAX_AGE = 4
# Ladder rung -> age. The spine of the layout: a rung's age is AUTHORITATIVE
# and is never max()'d against a prerequisite, because the prerequisite chain
# under a sphere root is pre-magic foundation and gets pulled DOWN to fit
# (see _relayout_advance_ages' upper-bound propagation).
_SPHERE_NAMES = ["life", "nature", "death", "chaos", "sorcery"]
_RUNG_AGE = {"MAGIC": 2, "LORE": 3, "ADEPT": 4,
             "MAGE": 5, "WIZARD": 6, "MASTER": 7}


def _ladder_rung_age(ident: str) -> "int | None":
    """Return the fixed age of a sphere-ladder rung, or None if not a rung."""
    # NOTE: iterate the SPHERES, not _SPHERE_TIERS -- the tier list would build
    # ADVANCE_LORE_MAGIC and silently match nothing, dropping every rung into
    # the depth-banding path and shifting all five ladders two ages late.
    for sphere in _SPHERE_NAMES:
        for rung, age in _RUNG_AGE.items():
            if ident == f"ADVANCE_{sphere.upper()}_{rung}":
                return age
    # Sorcery's root and lore rung are irregularly named in the authored tree.
    return {"ADVANCE_SORCERY": 2, "ADVANCE_SORCEROUS_LORE": 3}.get(ident)


def _momjr_advance_idents() -> set[str]:
    """ADVANCE_* idents authored by MoM (as opposed to inherited from base)."""
    idents = set()
    with open(MOMJR / "advances.csv", newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            name = (row.get("name") or "").split(";", 1)[0].strip()
            if (not name or name.startswith("x") or "Extra Advance" in name
                    or name.lower() == "blah"):
                continue
            idents.add(f"ADVANCE_{sanitize(name)}")
    return idents


def _apply_advance_mask(adv_file: "P.AdvanceFile") -> int:
    """Delete every masked advance block and every reference to one.

    Require: all advance INGESTION passes have run, so the tree is final.
    Guarantee: no ADVANCE_* named in advance_mask.csv survives in Advance.txt,
    either as a block or inside another block's Prerequisites. Idempotent --
    a second run finds nothing to remove.
    Why: the mask is the Renaissance tech cap. It carries base CTP2's
    industrial/modern tail (AGE_FIVE..TEN plus 11 advances mis-banded into
    AGE_THREE) and the 30 '*_WAW' duplicate-ladder advances that no MoM
    content ever references. Measured 2026-07-26: 112 removed, 143 kept, and
    ZERO kept advances carry a deleted prerequisite -- the cut is clean.
    """
    blocks = _scan_advance_blocks(adv_file._text)
    removed = 0
    for ident in sorted(_ADVANCE_MASK & set(blocks)):
        text = adv_file._text
        # Swallow the trailing blank line so deletions do not accumulate gaps.
        adv_file._text = re.sub(
            r"^" + re.escape(ident) + r"\s*\{.*?^\}\n*", "",
            text, count=1, flags=re.S | re.M)
        if adv_file._text != text:
            removed += 1
        adv_file.blocks.pop(ident, None)
    if _ADVANCE_MASK:
        # Strip dangling prerequisite lines pointing at anything just removed.
        adv_file._text = "\n".join(
            line for line in adv_file._text.splitlines()
            if not (line.strip().startswith("Prerequisites ")
                    and line.split()[-1] in _ADVANCE_MASK)
        ) + "\n"
    return removed


def _relayout_advance_ages(adv_file: "P.AdvanceFile") -> tuple[int, dict[str, int]]:
    """Re-band every surviving advance so content lands in the intended age.

    Require: _apply_advance_mask has run, so the graph holds only kept advances.
    Guarantee: (a) every sphere-ladder rung sits on its fixed age, MAGIC=2
    through MASTER=7; (b) no mundane (base-CTP2) advance exceeds AGE_FOUR;
    (c) no advance is in an earlier age than one of its own prerequisites.
    Idempotent -- the layout is a pure function of the graph.

    Method (derived, never hand-typed, so a rename cannot desync it):
      1. topologically order the kept advances by prerequisite;
      2. seed an upper bound of the rung age on each rung, 10 elsewhere, and
         propagate it BACKWARD along prerequisite edges -- a prerequisite can
         never be bounded later than the thing it enables;
      3. walk forward: rungs take their fixed age; MoM support advances take
         max(depth band, deepest prerequisite + 1) so long magical chains
         actually climb; base advances keep their authored CTP2 age clamped to
         the Renaissance cap. Everything is finally clamped by its upper bound
         and floored by its prerequisites.
    Step 2 is what makes step 3 consistent: without it, the five *_MAGIC roots
    inherit a deep support chain and drag all 30 rungs into one age -- the
    exact 'all magic crammed into a single band' defect this pass exists to fix.
    """
    blocks = _scan_advance_blocks(adv_file._text)
    prereqs = {
        ident: [p for p in re.findall(r'^\s*Prerequisites\s+(ADVANCE_[A-Z0-9_]+)\s*$',
                                      body, re.M)
                if p != ident and p in blocks]
        for ident, body in blocks.items()
    }
    current = {
        ident: _AGE_NUMBER.get(_unit_block_value(body, "Age", "AGE_ONE"), 1)
        for ident, body in blocks.items()
    }
    momjr = _momjr_advance_idents()

    order: list[str] = []
    seen: set[str] = set()

    def _visit(ident: str, stack: tuple[str, ...] = ()) -> None:
        if ident in seen or ident in stack:
            return          # a prerequisite cycle is not ours to fix; skip it
        for parent in prereqs[ident]:
            _visit(parent, stack + (ident,))
        seen.add(ident)
        order.append(ident)

    for ident in sorted(blocks):
        _visit(ident)

    depth: dict[str, int] = {}
    for ident in order:
        depth[ident] = (0 if not prereqs[ident]
                        else 1 + max(depth.get(p, 0) for p in prereqs[ident]))

    bound = {i: (_ladder_rung_age(i) or len(_AGE_NAMES) - 1) for i in blocks}
    for ident in reversed(order):
        for parent in prereqs[ident]:
            bound[parent] = min(bound[parent], bound[ident])

    ages: dict[str, int] = {}
    for ident in order:
        rung = _ladder_rung_age(ident)
        if rung is not None:
            ages[ident] = rung
            continue
        parent_ages = [ages[p] for p in prereqs[ident] if p in ages]
        if ident in momjr:
            want = max(1 + depth[ident] // 2,
                       (max(parent_ages) + 1) if parent_ages else 1)
        else:
            want = min(_MUNDANE_MAX_AGE, current[ident])
        age = min(bound[ident], want)
        if parent_ages:
            age = max(age, max(parent_ages))
        ages[ident] = max(1, min(len(_AGE_NAMES) - 1, age))

    changed = 0
    for ident, age in ages.items():
        body = blocks[ident]
        new_body = _set_raw_block_value(body, "Age", _AGE_NAMES[age])
        if new_body != body:
            adv_file._text = adv_file._text.replace(body, new_body, 1)
            blocks[ident] = new_body
            changed += 1
    return changed, ages


def _apply_advance_reanchor(reg) -> tuple[int, int]:
    """Re-point or delete every block orphaned by the tech cap.

    Require: _apply_advance_mask has run and tileimp.txt/govern.txt have been
    rebuilt, so this sees final blocks.
    Guarantee: no dimension file cites a masked ADVANCE_*. Idempotent -- each
    row only fires while the stale advance is still present.
    Why: mom-db-error-class -- a dangling advance reference surfaces in-game as
    'not found in Advance database' and takes the scenario down at load.
    """
    by_file: dict[str, list[dict[str, str]]] = {}
    for row in _ADVANCE_REANCHOR:
        by_file.setdefault(row["file"], []).append(row)
    # An orphan is any advance absent from the LIVE tree -- a superset of the
    # mask, because base CTP2 files also cite advances MoM never imported.
    _live = set(re.findall(r"^(ADVANCE_[A-Z0-9_]+)\s*\{",
                           _read_rel("default/gamedata/Advance.txt"), re.M))
    rewritten = deleted = 0
    for name, rows in by_file.items():
        rel = f"default/gamedata/{name}"
        # Units.txt and Wonder.txt are REGISTRY-BACKED: reg.save_all() runs
        # after this pass and rewrites them from the cached parse, so a raw
        # _write_rel here is silently clobbered. Mutate the cached ._text when
        # the file is loaded; fall back to raw I/O for the rest (tileimp.txt,
        # terrain.txt, govern.txt are not registry-written).
        cached = reg._parsed.get(rel)
        text = getattr(cached, "_text", "") if cached is not None else _read_rel(rel)
        if not text:
            continue
        before = text
        for row in rows:
            ident, target = row["block"], row["new_advance"]
            pattern = re.compile(r"^(" + re.escape(ident) + r"\s*\{)(.*?)(^\}\n*)",
                                 re.S | re.M)
            match = pattern.search(text)
            if not match:
                continue
            if target == "DELETE_BLOCK":
                text = text[:match.start()] + text[match.end():]
                deleted += 1
                continue
            body = match.group(2)
            if target == "CLEAR_FIELD":
                new_body = re.sub(r"^\s*ObsoleteAdvance\s+ADVANCE_[A-Z0-9_]+\s*$\n?",
                                  "", body, flags=re.M)
            else:
                # Re-point every masked advance this block still cites,
                # whatever field carries it (EnableAdvance, AddAdvance,
                # RemoveAdvance, ObsoleteAdvance).
                new_body = re.sub(
                    r"\b(ADVANCE_[A-Z0-9_]+)\b",
                    lambda m: target if m.group(1) not in _live else m.group(1),
                    body)
            if new_body != body:
                text = f"{text[:match.start()]}{match.group(1)}{new_body}{match.group(3)}{text[match.end():]}"
                rewritten += 1
        if text != before:
            if cached is not None:
                cached.set_text(text) if hasattr(cached, "set_text") else \
                    setattr(cached, "_text", text)
            else:
                _write_rel(rel, text)
    return rewritten, deleted


def _apply_sphere_gating(reg) -> tuple[int, list[str]]:
    """Rewrite EnableAdvance on every sphere'd block to its ladder rung.

    Require: the unit mask, the unit/improvement cost retunes, and the
    improvement->buildings merge have all already run, so this reads final
    costs and cannot resurrect a masked unit.
    Guarantee: every block named by sphere_gate_targets() that EXISTS in a DB
    file gates on its sphere rung. Idempotent -- a second run changes nothing.
    Note: a target with no matching block is not an error; units.csv carries
    masked placeholder rows and improvements.csv rows split across
    buildings.txt and Wonder.txt.
    """
    targets = sphere_gate_targets()
    # Registry-backed files, rewritten through ._text so reg.save_all() emits
    # them. buildings.txt is deliberately NOT here: it has no PARSER_MAP entry
    # (it is produced wholesale by _merge_mom_improvements_into_buildings and
    # written straight to disk), so it takes the read/modify/write path below.
    reg_files = [
        "default/gamedata/Units.txt",
        "default/gamedata/Units_historic.txt",
        "default/gamedata/Units_release.txt",
        "default/gamedata/Wonder.txt",
    ]
    direct_files = ["default/gamedata/buildings.txt"]
    changed, touched = 0, set()
    for rel in reg_files + direct_files:
        is_direct = rel in direct_files
        if is_direct:
            db, text = None, _read_rel(rel)
        else:
            db = reg.load(rel)
            text = getattr(db, "_text", None)
        if not text:
            continue
        before = text
        for ident in sorted(targets):
            advance = targets[ident]
            block = re.compile(r"^(" + re.escape(ident) + r"\s*\{)(.*?)(^\})",
                               re.S | re.M)

            def _rewrite(m: "re.Match[str]") -> str:
                nonlocal changed
                body = m.group(2)
                new_body = _set_raw_block_value(body, "EnableAdvance", advance)
                if new_body != body:
                    changed += 1
                    touched.add(ident)
                return f"{m.group(1)}{new_body}{m.group(3)}"

            text = block.sub(_rewrite, text)
        if is_direct:
            if text != before:
                _write_rel(rel, text)
        else:
            db._text = text
    return changed, sorted(touched)


def _retune_mom_improvement_costs(advance_ages: dict[str, str]) -> int:
    """Rewrite MoM improvement costs into base CTP2 age bands from raw MOMJR costs.

    Raw Civ2 costs (4..60) render as 1-turn builds in CTP2; base first-age
    improvements sit in ~[525..875]. Retired blocks (ObsoleteAdvance present:
    X-sentinels, HIDE_SUPERMARKET) are skipped — they are never buildable.
    """
    ae_bands = _load_ae_improvement_cost_bands()
    improve_specs, source_bands = _load_mom_improvement_source_specs(advance_ages)
    if not ae_bands or not improve_specs or not source_bands:
        return 0
    # One global source band: raw Civ2 costs form a single 4..60 scale.
    all_costs = [cost for cost, _age in improve_specs.values()]
    global_source_band = (min(all_costs), max(all_costs))
    rel = "default/gamedata/buildings.txt"
    improve_file = _load_raw_block_file(rel)
    changed = 0
    for ident, block_text in list(improve_file.blocks.items()):
        if "ObsoleteAdvance" in block_text:
            continue
        source_spec = improve_specs.get(ident)
        if not source_spec:
            continue
        source_cost, _csv_age = source_spec
        # Target band from the age of the advance that ACTUALLY gates the
        # emitted block — an item buildable at turn 1 (ADVANCE_WARRIOR_CODE)
        # must be priced in the first-age band regardless of its CSV prereq,
        # or a 3500-cost building shows as a 146-turn build in a new city.
        # This bounds MAX turns as well as min within each age's scale.
        gate_advance = _unit_block_value(block_text, "EnableAdvance", "ADVANCE_WARRIOR_CODE")
        age = advance_ages.get(gate_advance, "AGE_ONE")
        target_band = _nearest_ae_cost_band(age, ae_bands)
        new_cost = _scale_cost_into_band(source_cost, global_source_band, target_band, 10)
        if _unit_block_int(block_text, "ProductionCost") == new_cost:
            continue
        improve_file.add_block(ident, _set_raw_block_value(block_text, "ProductionCost", str(new_cost)))
        changed += 1
    if changed:
        _save_raw_block_file(rel, improve_file)
        reg._parsed.pop(rel, None)   # force re-parse on next load
    return changed


def _nearest_ae_cost_band(age: str, bands: dict[str, tuple[int, int]]) -> tuple[int, int]:
    """Return the nearest AE cost band for the requested age."""
    if age in bands:
        return bands[age]
    age_order = {
        "AGE_ONE": 1,
        "AGE_TWO": 2,
        "AGE_THREE": 3,
        "AGE_FOUR": 4,
        "AGE_FIVE": 5,
        "AGE_SIX": 6,
        "AGE_SEVEN": 7,
        "AGE_EIGHT": 8,
        "AGE_NINE": 9,
        "AGE_TEN": 10,
    }
    target_rank = age_order.get(age, 1)
    nearest_age = min(
        bands,
        key=lambda candidate: abs(age_order.get(candidate, target_rank) - target_rank),
    )
    return bands[nearest_age]


def _scaled_mom_advance_cost(weight: int, age: str, prereq_count: int,
                             ae_bands: dict[str, tuple[int, int]]) -> int:
    """Map Civ2-side advance weight into the matching AE age cost band."""
    scaling = MOD_POLICY["advance_cost_scaling"]
    w_min = int(scaling["weight_min"])
    w_max = int(scaling["weight_max"])
    low, high = _nearest_ae_cost_band(age, ae_bands)
    clamped_weight = max(w_min, min(w_max, weight))
    normalized = (clamped_weight - w_min) / float(w_max - w_min)
    base_cost = low + (high - low) * normalized
    prereq_factor = 1.0 + (float(scaling["prereq_factor"]) * max(0, prereq_count))
    round_to = float(scaling["round_to"])
    scaled = int(round((base_cost * prereq_factor) / round_to) * int(round_to))
    return max(low, scaled)


def _retune_mom_advance_costs(adv_file: "P.AdvanceFile") -> int:
    """Rewrite MoM-imported advance costs into AE-scaled research bands."""
    ae_bands = _load_ae_advance_cost_bands()
    if not ae_bands:
        return 0
    changed = 0
    csv_weights: dict[str, int] = {}
    branch_fallback_weights = {
        int(k): int(v) for k, v in MOD_POLICY["branch_fallback_weights"].items()
    }
    advance_blocks = _scan_advance_blocks(adv_file._text)
    with open(MOMJR / "advances.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = (row.get("name") or "").split(";", 1)[0].strip()
            if not name or name.startswith("x") or "Extra Advance" in name or name.lower() == "blah":
                continue
            ident = f"ADVANCE_{sanitize(name)}"
            cell_index_text = (row.get("cell_index") or "").strip()
            if cell_index_text.lstrip("-").isdigit():
                csv_weights[ident] = int(cell_index_text)
    for ident, block_text in advance_blocks.items():
            age_match = re.search(r'^\s*Age\s+(AGE_[A-Z0-9_]+)\s*$', block_text, re.MULTILINE)
            cost_match = re.search(r'^\s*Cost\s+(\d+)\s*$', block_text, re.MULTILINE)
            branch_match = re.search(r'^\s*Branch\s+(\d+)\s*$', block_text, re.MULTILINE)
            if not age_match or not cost_match:
                continue
            low, high = _nearest_ae_cost_band(age_match.group(1), ae_bands)
            current_cost = int(cost_match.group(1))
            # Rescale EVERY advance into the sane per-Age band (coverage gap closed): the
            # old `csv_weights or cost>high*2` gate left ~82 inherited base/WAW AGE_FOUR-TEN
            # techs (and the Cost=1 SUBNEURAL_ADS) at their raw 6-figure costs. MoM-authored
            # advances use their advances.csv cell_index weight; all others fall back to a
            # per-Branch weight so intra-age ordering is preserved.
            if ident in csv_weights:
                weight = csv_weights[ident]
            else:
                branch = int(branch_match.group(1)) if branch_match else 1
                weight = branch_fallback_weights.get(branch, 10)
            # Self-prereqs are the engine-sanctioned disable pattern, not real
            # research dependencies — they must not inflate the cost factor.
            prereq_count = len([p for p in re.findall(r'^\s*Prerequisites\s+(ADVANCE_[A-Z0-9_]+)\s*$', block_text, re.MULTILINE) if p != ident])
            new_cost = _scaled_mom_advance_cost(weight, age_match.group(1), prereq_count, ae_bands)
            if current_cost == new_cost:
                continue
            new_block = re.sub(
                r'^(\s*Cost\s+)\d+(\s*)$',
                rf'\g<1>{new_cost}\g<2>',
                block_text,
                count=1,
                flags=re.MULTILINE,
            )
            adv_file._text = adv_file._text.replace(block_text, new_block, 1)
            advance_blocks[ident] = new_block
            changed += 1
    return changed


def _parse_advance_list_blocks(text: str) -> dict[str, list[str]]:
    """Return ADVANCE_LIST_* blocks keyed to ordered Advance refs."""
    lists: dict[str, list[str]] = {}
    current: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.split("//", 1)[0].rstrip()
        start = re.match(r'^(ADVANCE_LIST_[A-Z0-9_]+)\s*\{', line)
        if start:
            current = start.group(1)
            lists[current] = []
            continue
        if current is None:
            continue
        if line.strip() == "}":
            current = None
            continue
        advance_match = re.match(r'^\s*Advance\s+(ADVANCE_[A-Z0-9_]+)\b', line)
        if advance_match:
            lists[current].append(advance_match.group(1))
    return lists


def _write_mom_advance_lists() -> dict[str, int]:
    """Write scenario AdvanceLists.txt from MoM-visible advances.

    Require: the generated Advance.txt already reflects the live MoM tech tree.
    Guarantee: every strategy-referenced ADVANCE_LIST_* is scenario-owned and
    contains only visible MoM advances. Failure modes: if live advances drift
    out of sync with advances.csv ordering metadata, remaining visible advances
    are appended by live Age/name fallback rather than silently inheriting stock
    CTP2 lists.
    """
    advance_blocks = _scan_advance_blocks(_read_rel("default/gamedata/Advance.txt"))
    hidden_advances = {
        ident
        for ident, block_text in advance_blocks.items()
        if re.search(r'^\s*(NoIndex|GLHidden)\s*$', block_text, re.MULTILINE)
    }

    csv_meta: dict[str, tuple[int, int, int]] = {}
    csv_order: list[str] = []
    with open(MOMJR / "advances.csv", newline="", encoding="utf-8") as f:
        for row_index, row in enumerate(csv.DictReader(f)):
            name = (row.get("name") or "").split(";", 1)[0].strip()
            if not name or name.startswith("x") or "Extra Advance" in name or name.lower() == "blah":
                continue
            ident = f"ADVANCE_{sanitize(name)}"
            if ident in csv_meta:
                continue
            epoch_text = (row.get("epoch") or "").strip()
            try:
                epoch = int(epoch_text)
            except ValueError:
                epoch = 99
            category_field = (row.get("category") or "").strip()
            category_text = category_field.split(";", 1)[0].strip()
            try:
                category = int(category_text)
            except ValueError:
                category = 99
            csv_meta[ident] = (epoch, category, row_index)
            csv_order.append(ident)

    age_rank = {
        "AGE_ONE": 1,
        "AGE_TWO": 2,
        "AGE_THREE": 3,
        "AGE_FOUR": 4,
        "AGE_FIVE": 5,
        "AGE_SIX": 6,
        "AGE_SEVEN": 7,
        "AGE_EIGHT": 8,
        "AGE_NINE": 9,
        "AGE_TEN": 10,
    }

    visible_advances = {
        ident for ident in advance_blocks
        if ident not in hidden_advances
    }
    ordered_visible_advances = [
        ident for ident in csv_order
        if ident in visible_advances
    ]
    remaining_visible_advances = sorted(
        visible_advances - set(ordered_visible_advances),
        key=lambda ident: (
            age_rank.get(_unit_block_value(advance_blocks[ident], "Age"), 99),
            ident,
        ),
    )
    ordered_visible_advances.extend(remaining_visible_advances)

    stock_lists = _parse_advance_list_blocks(_read_rel("default/aidata/AdvanceLists.txt"))
    strategy_refs = sorted(set(re.findall(
        r'\b(?:Research|StopResearch)\s+(ADVANCE_LIST_[A-Z0-9_]+)',
        _read_rel("default/aidata/strategies.txt"),
    )))

    lists: dict[str, list[str]] = {}
    for ident in strategy_refs:
        seen: set[str] = set()
        stock_kept: list[str] = []
        for advance_id in stock_lists.get(ident, []):
            if advance_id in visible_advances and advance_id not in seen:
                stock_kept.append(advance_id)
                seen.add(advance_id)
        if ident == "ADVANCE_LIST_STOP_RESEARCH":
            lists[ident] = stock_kept
            continue
        remainder = [advance_id for advance_id in ordered_visible_advances if advance_id not in seen]
        lists[ident] = stock_kept + remainder

    for ident in stock_lists:
        lists.setdefault(ident, stock_lists[ident] if ident == "ADVANCE_LIST_STOP_RESEARCH" else [])

    lines = [
        "#----------------------------------------------------------------------------",
        "#",
        "# MoM scenario override -- generator-owned.",
        "# Keep AI research on visible MoM advances; do not inherit stock CTP2 lists.",
        "# Preserve stock ordering where it still matches MoM, then append the rest",
        "# of the visible imported tech tree so SetResearch never falls through to",
        "# zero science because the scenario omitted AdvanceLists.txt.",
        "#",
        "#----------------------------------------------------------------------------",
        "",
        f"# {len(lists)}",
        "",
    ]
    for index, ident in enumerate(sorted(lists), start=1):
        lines.append(f"## {index} #########################################################")
        lines.append(f"{ident} {{")
        for advance_id in lists[ident]:
            lines.append(f"  Advance {advance_id}")
        lines.append("}")
        lines.append("")
    lines.append("### ALL ADVANCES DONE ###")

    _write_rel("default/aidata/AdvanceLists.txt", "\n".join(lines))
    return {ident: len(advance_ids) for ident, advance_ids in lists.items()}


def _write_mom_unit_build_lists(units_file: P.UnitsFile) -> dict[str, int]:
    """Write scenario UnitBuildLists.txt from visible MoM units only.

    Require: Units.txt has already been generated and hidden base units carry
    NoIndex/GLHidden. Guarantee: every strategy-referenced UNIT_BUILD_LIST_* is
    scenario-owned and contains no hidden base CTP2 unit IDs. Failure modes:
    malformed unit blocks are skipped by the scanner, causing the audit to fail
    rather than letting stock aidata leak back in.
    """
    blocks = _scan_unit_blocks(units_file.render())

    visible_units: list[tuple[str, str]] = []
    for ident, block_text in blocks.items():
        if ident == "UNIT_CITY":
            continue
        if re.search(r'^\s*(NoIndex|GLHidden)\s*$', block_text, re.MULTILINE):
            continue
        visible_units.append((ident, block_text))

    def by_cost(unit_items: list[tuple[str, str]]) -> list[str]:
        return [
            ident
            for ident, _ in sorted(
                unit_items,
                key=lambda item: (
                    _unit_block_int(item[1], "ShieldCost"),
                    _unit_block_int(item[1], "Attack"),
                    item[0],
                ),
            )
        ]

    land = [
        item for item in visible_units
        if _unit_block_value(item[1], "Category") == "UNIT_CATEGORY_ATTACK"
    ]
    air = [
        item for item in visible_units
        if _unit_block_value(item[1], "Category") == "UNIT_CATEGORY_AERIAL"
    ]
    sea = [
        item for item in visible_units
        if _unit_block_value(item[1], "Category") == "UNIT_CATEGORY_NAVAL"
    ]
    _roles = MOD_POLICY["unit_roles"]
    freight = [item for item in visible_units if item[0] in set(_roles["freight"])]
    land_settlers = [item for item in visible_units if item[0] in set(_roles["land_settlers"])]
    ranged_ids = set(_roles["ranged"])
    ranged = [item for item in visible_units if item[0] in ranged_ids]
    sea_transports = [item for item in sea if item[0] in set(_roles["sea_transports"])]
    air_transports = [item for item in air if item[0] in set(_roles["air_transports"])]

    lists: dict[str, list[str]] = {
        "UNIT_BUILD_LIST_OFFENSE": [
            ident for ident in by_cost(land)
            if _unit_block_int(blocks[ident], "Attack") > 0
        ],
        "UNIT_BUILD_LIST_DEFENSE": by_cost(land),
        "UNIT_BUILD_LIST_RANGED": by_cost(ranged),
        "UNIT_BUILD_LIST_SEA": by_cost(sea),
        "UNIT_BUILD_LIST_AIR": by_cost(air),
        "UNIT_BUILD_LIST_LAND_SETTLER": by_cost(land_settlers),
        "UNIT_BUILD_LIST_SEA_SETTLER": [],
        "UNIT_BUILD_LIST_SEA_TRANSPORT": by_cost(sea_transports),
        "UNIT_BUILD_LIST_AIR_TRANSPORT": by_cost(air_transports),
        "UNIT_BUILD_LIST_NAVAL_SPECIAL": by_cost(sea_transports),
        "UNIT_BUILD_LIST_FREIGHT": by_cost(freight),
        "UNIT_BUILD_LIST_SPECIAL_ANTISLAVERY": [],
        "UNIT_BUILD_LIST_SPECIAL_DIPLOMACY": [],
        "UNIT_BUILD_LIST_SPECIAL_DIPLOMATIC": [],
        "UNIT_BUILD_LIST_SPECIAL_ECONOMIC": [],
        "UNIT_BUILD_LIST_SPECIAL_ECOTOPIAN": [],
        "UNIT_BUILD_LIST_SPECIAL_MILITARIST": [],
        "UNIT_BUILD_LIST_SPECIAL_MISSIONARY": [],
        "UNIT_BUILD_LIST_SPECIAL_NUCLEAR": [],
        "UNIT_BUILD_LIST_SPECIAL_SCIENTIST": [],
        "UNIT_BUILD_LIST_SPECIAL_SLAVERY": [],
        "UNIT_BUILD_LIST_SPECIAL_SPY": [],
    }

    strategy_refs = sorted(set(re.findall(
        r'\b\w+UnitList\s+(UNIT_BUILD_LIST_[A-Z0-9_]+)',
        _read_rel("default/aidata/strategies.txt"),
    )))
    for ident in strategy_refs:
        lists.setdefault(ident, [])

    lines = [
        "#----------------------------------------------------------------------------",
        "#",
        "# MoM scenario override -- generator-owned.",
        "# Keep AI production on visible MoM units; do not inherit stock CTP2 lists.",
        "#",
        "#----------------------------------------------------------------------------",
        "",
        f"# {len(lists)}",
        "",
    ]
    for index, ident in enumerate(sorted(lists), start=1):
        lines.append(f"## {index} #########################################################")
        lines.append(f"{ident} {{")
        for unit_id in lists[ident]:
            lines.append(f"  Unit {unit_id}")
        lines.append("}")
        lines.append("")
    lines.append("### ALL UNITS DONE ###")

    rel = Path("default/aidata/UnitBuildLists.txt")
    path = SCENARIO / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding='latin-1')
    return {ident: len(unit_ids) for ident, unit_ids in lists.items()}


def _write_sanitized_goals_wonder_refs(keep_ids: set[str]) -> int:
    """Write a scenario Goals.txt override with only live wonder protection refs."""
    rel = "default/aidata/Goals.txt"
    removed = 0
    kept_lines = []
    for line in _read_rel(rel).splitlines():
        match = re.match(r'^(\s*TargetProtectionWonder\s+)(WONDER_[A-Z0-9_]+)(\s*)$', line)
        if match and match.group(2) not in keep_ids:
            removed += 1
            continue
        kept_lines.append(line)
    _write_rel(rel, '\n'.join(kept_lines))
    return removed


def _sanitize_omitted_building_refs() -> None:
    """Dynamically replace any omitted base-game IMPROVE_* references in fallback files with a safe MoM equivalent.

    This function loads the generated buildings.txt to determine which IMPROVE_* IDs are valid
    in the MoM scenario. Then it scans a set of fallback files (aidata, GL, etc.) for any
    IMPROVE_* references that are NOT in the valid set and replaces them with IMPROVE_GRANARY.
    This eliminates the "whack-a-mole" problem of manually maintaining a replacement map.

    Guarantee: After this pass, all fallback files contain ZERO references to omitted base
    buildings like IMPROVE_MOVIE_PALACE, IMPROVE_BASILICA, etc.
    """
    # 1. Load the set of valid, live MoM building IDs from generated buildings.txt
    buildings_file = _load_raw_block_file("default/gamedata/buildings.txt")
    valid_building_ids = set(buildings_file.blocks.keys())
    if not valid_building_ids:
        print("  ! WARNING: No valid building IDs found in buildings.txt; skipping sanitization")
        return

    # Choose a safe fallback building that definitely exists in MoM
    fallback_building = MOD_POLICY["building_ref_fallback"]
    if fallback_building not in valid_building_ids:
        fallback_building = next(iter(valid_building_ids))
        print(f"  ! WARNING: IMPROVE_GRANARY not in control plane; using {fallback_building} as fallback")

    # 2. Define the fallback files to sanitize
    fallback_files = [
        "default/aidata/BuildingBuildLists.txt",
        "default/gamedata/tut2_main.slc",
        "default/gamedata/tut2_str.txt",
        "default/gamedata/feat.txt",
        "english/gamedata/Great_Library.txt",
        "english/gamedata/WAW_Great_Library.txt",
        "english/gamedata/gl_str.txt",
        "english/gamedata/junk_str.txt",
    ]

    # 3. Process each file
    total_replacements = 0
    files_modified = 0
    # Match any IMPROVE_* token, even if preceded by underscore (e.g., DESCRIPTION_IMPROVE_*)
    building_ref_pattern = re.compile(r'IMPROVE_[A-Z0-9_]+\b')
    gl_section_suffixes = ('_GAMEPLAY', '_HISTORICAL', '_PREREQ', '_STATISTICS', '_SUMMARY')

    def is_valid_building_ref(token: str) -> bool:
        if token in valid_building_ids:
            return True
        for suffix in gl_section_suffixes:
            if token.endswith(suffix):
                base_id = token[:-len(suffix)]
                if base_id in valid_building_ids:
                    return True
                break
        return False

    for rel in fallback_files:
        content = _read_rel(rel)
        if not content:
            continue

        matches = building_ref_pattern.findall(content)
        invalid_refs = {ref for ref in matches if not is_valid_building_ref(ref)}

        if invalid_refs:
            modified_content = content
            for invalid_ref in invalid_refs:
                modified_content = modified_content.replace(invalid_ref, fallback_building)
                total_replacements += 1

            _write_rel(rel, modified_content)
            files_modified += 1

    print(f"  + sanitized {total_replacements} omitted building reference(s) across {files_modified} file(s)")


def _load_canonical_momjr_wonders() -> list[dict[str, object]]:
    """Load MOMJR wonder records from momjr_csv/wonders.csv + improvements.csv.

    Derives display names from improvements.csv (same icon key pattern) and
    parses EnableAdvance from the stored block_text. No longer depends on the
    civ2_canonical/momjr/wonders.csv artifact.
    """
    # Build display-name lookup from improvements.csv: IMPROVE_KEY -> name
    # A mod without an authored wonders.csv (CTP2 block_text is hand-curated,
    # not derivable from civ2) simply migrates no wonder slots.
    if not _csv_exists("wonders.csv"):
        return []

    imp_names: dict[str, str] = {}
    with open(MOMJR / "improvements.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            icon = (row.get("icon") or "").strip()
            name = (row.get("name") or "").strip()
            if icon.startswith("ICON_IMPROVE_") and name:
                imp_names[icon[len("ICON_"):]] = name  # IMPROVE_KEY -> name

    legacy_wonder_art = _load_legacy_wonder_art_specs()
    wonder_gl_rows = _load_momjr_wonder_gl_rows()
    _enable_adv_re = re.compile(r"EnableAdvance\s+(\S+)")
    wonders = []
    for row in _csv_rows("wonders.csv"):
        wonder_id = (row.get("id") or "").strip()
        if not wonder_id:
            continue
        improve_id = wonder_id.replace("WONDER_", "IMPROVE_", 1)
        name = imp_names.get(improve_id) or humanize_ident(wonder_id, "WONDER_")
        block_text = row.get("block_text") or ""
        m = _enable_adv_re.search(block_text)
        advance_id = m.group(1).strip() if m else "ADVANCE_WARRIOR_CODE"
        no_prereq = not bool(m)
        icon_id = f"ICON_{wonder_id}"
        # Prefer cell_index from wonders.csv (= @IMPROVE slot, set by pipeline);
        # fall back to the legacy canonical_schema/improvements.csv path.
        cell_index_text = (row.get("cell_index") or "").strip()
        legacy_art = legacy_wonder_art.get(improve_id, {})
        if cell_index_text.lstrip("-").isdigit():
            source_cell_index: int | None = int(cell_index_text)
        else:
            source_cell_index = legacy_art.get("source_cell_index")
        gl_row = wonder_gl_rows.get(wonder_id, {})
        wonders.append(
            {
                "name": name,
                "wonder_id": wonder_id,
                "improve_id": improve_id,
                "description_id": f"DESCRIPTION_{wonder_id}",
                "icon_id": icon_id,
                "icon_asset": f"{icon_id}.TGA",
                "advance_id": advance_id,
                "no_prereq": no_prereq,
                "source_cell_index": source_cell_index,
                "gl_description": str(gl_row.get("gl_description") or ""),
                "gl_gameplay": str(gl_row.get("gl_gameplay") or ""),
                "gl_historical": str(gl_row.get("gl_historical") or ""),
                "gl_statistics": str(gl_row.get("gl_statistics") or ""),
            }
        )
    return wonders


def _load_momjr_wonder_gl_rows() -> dict[str, dict[str, str]]:
    """Load wonder prose/stat rows from the scenario-owned wonders CSV."""
    rows: dict[str, dict[str, str]] = {}
    for row in _csv_rows("wonders.csv"):
        ident = (row.get("id") or "").strip()
        if not ident:
            continue
        rows[ident] = {
            "gl_description": _csv_text(row.get("gl_description") or ""),
            "gl_gameplay": _csv_text(row.get("gl_gameplay") or ""),
            "gl_historical": _csv_text(row.get("gl_historical") or ""),
            "gl_statistics": _csv_text(row.get("gl_statistics") or ""),
        }
    return rows


def _load_momjr_advance_ids_by_code() -> dict[str, str]:
    """Map MoM short codes to the live advance IDs generated from advances.csv."""
    advance_ids_by_code: dict[str, str] = {}
    with open(MOMJR / "advances.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = (row.get("name") or "").split(";")[0].strip()
            if not name or "Extra Advance" in name or name.lower() == "blah":
                continue
            category_field = (row.get("category") or "").strip()
            if ";" not in category_field:
                continue
            code = category_field.split(";", 1)[1].split(",", 1)[0].strip()
            if code and code != "...":
                advance_ids_by_code[code] = f"ADVANCE_{sanitize(name)}"
    return advance_ids_by_code


def _load_momjr_advance_idents() -> set[str]:
    """Return the authoritative set of visible MoM advance IDs from advances.csv.

    This is the ONLY set that should appear in the player-facing research tree.
    Uses the same row-skip rules the advance-emission loop applies (blank/'x'/
    'Extra Advance'/'blah' rows are stubs, not real advances). Distinct from the
    generator's ``mom_advance_idents`` working set, which is polluted with base
    CTP2 IDs pulled in via MOM_UNIT_ADVANCE code aliases (e.g. ADVANCE_ECONOMICS)
    and must not be treated as fantasy advances.
    """
    idents: set[str] = set()
    with open(MOMJR / "advances.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = (row.get("name") or "").split(";", 1)[0].strip()
            if (not name or name.startswith("x") or "Extra Advance" in name
                    or name.lower() == "blah"):
                continue
            idents.add(f"ADVANCE_{sanitize(name)}")
    return idents


def _load_legacy_wonder_art_specs() -> dict[str, dict[str, object]]:
    """Load wonder art metadata from the validated Improvements.bmp wonder lane.

    Returns empty dict if the canonical_schema/improvements.csv file is absent
    (source_cell_index is optional — callers use .get() with a None fallback).
    """
    icon_path = Path(__file__).parent / "canonical_schema" / "improvements.csv"
    if not icon_path.exists():
        return {}

    legacy_specs: dict[str, dict[str, object]] = {}
    with open(icon_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ident = (row.get("ctp2_ident") or "").strip()
            source_index_text = (row.get("source_index") or "").strip()
            if not ident.startswith("IMPROVE_") or not source_index_text:
                continue
            legacy_specs[ident] = {
                "source_cell_index": int(source_index_text) - 1,
            }
    return legacy_specs


def _strip_detected_wonder_border(cell):
    """Trim the validated outer frame plus any uniform top-left matte strip."""
    outer_border = 2
    if cell.width <= outer_border * 2 or cell.height <= outer_border * 2:
        raise ValueError(f"Wonder atlas cell too small for outer trim: {cell.size}")

    trimmed = cell.crop(
        (
            outer_border,
            outer_border,
            cell.width - outer_border,
            cell.height - outer_border,
        )
    )

    def edge_stats(strip):
        colors = strip.convert("RGB").getcolors(strip.width * strip.height)
        if not colors:
            return None, 0.0, 0
        dominant_count, dominant_color = max(colors, key=lambda item: item[0])
        return dominant_color, dominant_count / (strip.width * strip.height), len(colors)

    def colors_close(a, b, tolerance=8):
        return all(abs(int(x) - int(y)) <= tolerance for x, y in zip(a, b))

    while trimmed.width > 4 and trimmed.height > 4:
        top_color, top_frac, top_unique = edge_stats(trimmed.crop((0, 0, trimmed.width, 1)))
        left_color, left_frac, left_unique = edge_stats(trimmed.crop((0, 0, 1, trimmed.height)))
        if (
            top_color is None
            or left_color is None
            or top_frac < 0.98
            or left_frac < 0.98
            or top_unique > 2
            or left_unique > 2
            or not colors_close(top_color, left_color)
        ):
            break
        trimmed = trimmed.crop((1, 1, trimmed.width, trimmed.height))

    return trimmed


def _write_momjr_wonder_icon_art(wonder_specs: list[dict[str, object]]) -> int:
    """Extract scenario-owned wonder TGAs from the validated wonder atlas grid."""
    cells = extractor.load_sheet_cells("wonder_atlas")
    picture_dir = SCENARIO / "default" / "graphics" / "pictures"
    picture_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    for spec in wonder_specs:
        source_cell_index = spec.get("source_cell_index")
        if not isinstance(source_cell_index, int):
            continue
        if source_cell_index < 0 or source_cell_index >= len(cells):
            raise IndexError(
                f"Wonder art source index {source_cell_index} out of range for {spec['wonder_id']}"
            )

        cell = cells[source_cell_index].convert("RGBA")
        cell = _strip_detected_wonder_border(cell)
        alpha_bbox = cell.getchannel("A").getbbox()
        if alpha_bbox is None:
            scaled = extractor._scale_rgba_to_canvas(cell, 160, 120)
        else:
            scaled = extractor._scale_rgba_to_canvas(cell.crop(alpha_bbox), 160, 120)

        dest = picture_dir / str(spec["icon_asset"])
        extractor.save_tga_rgb555(scaled, dest, False)
        written += 1

    return written


def _strip_exact_database_links(library: P.LibraryFile, database_name: str, stale_ids: set[str]) -> int:
    """Remove GL database links for a specific set of stale IDs while keeping the display text."""
    if not stale_ids:
        return 0
    pattern = re.compile(
        rf'<L:{re.escape(database_name)},({"|".join(re.escape(i) for i in sorted(stale_ids))})>(.*?)<e>'
    )
    removed = 0
    for section_id, content in list(library.sections.items()):
        def _replace(match):
            nonlocal removed
            removed += 1
            return match.group(2)
        library.sections[section_id] = pattern.sub(_replace, content)
    return removed


def _remove_migrated_wonder_improvements(
    gl_strings: P.StringDBFile,
    gl_library: P.LibraryFile,
    waw_library: P.LibraryFile,
    wonder_specs: list[dict[str, object]],
) -> tuple[int, int, int]:
    """Remove MOMJR wonder-slot concepts from the old IMPROVE_* lane after migration."""
    stale_improves = {spec["improve_id"] for spec in wonder_specs}
    improve_file = reg.load("default/gamedata/Improve.txt")
    removed_improve_blocks = 0
    for ident in sorted(stale_improves):
        if ident in improve_file.blocks:
            del improve_file.blocks[ident]
            removed_improve_blocks += 1

    removed_gl_refs = 0
    for strings in (gl_strings,):
        for ident in sorted(stale_improves):
            for key in (ident, f"DESCRIPTION_{ident}"):
                if key in strings.entries:
                    del strings.entries[key]

    for library in (gl_library, waw_library):
        for ident in sorted(stale_improves):
            for suffix in ("_GAMEPLAY", "_HISTORICAL", "_PREREQ", "_STATISTICS"):
                library.sections.pop(f"{ident}{suffix}", None)
        removed_gl_refs += _strip_exact_database_links(library, "DATABASE_IMPROVEMENTS", stale_improves)

    # NOTE: We intentionally DO NOT delete ICON_IMPROVE_* from uniticon.txt here,
    # because _merge_mom_improvements_into_buildings still needs them to resolve
    # the DefaultIcon reference in buildings.txt. building_uniticon.csv provides
    # the correct mapping to the actual .tga assets.
    return removed_improve_blocks, 0, removed_gl_refs


def _synchronize_runtime_wonder_blocks(wonder_specs: list[dict[str, object]]) -> int:
    """Align live Wonder.txt blocks with the current wonder metadata contract."""
    rel = "default/gamedata/Wonder.txt"
    wonder_file = _load_raw_block_file(rel)
    updated = 0
    for spec in wonder_specs:
        ident = str(spec["wonder_id"])
        block_text = wonder_file.blocks.get(ident)
        if not block_text:
            continue

        synchronized = block_text
        synchronized = _set_raw_block_value(synchronized, "DefaultIcon", str(spec["icon_id"]))
        synchronized = _set_raw_block_value(synchronized, "Description", str(spec["description_id"]))
        synchronized = _set_raw_block_value(synchronized, "EnableAdvance", str(spec["advance_id"]))
        if synchronized != block_text:
            wonder_file.add_block(ident, synchronized)
            updated += 1
    if updated:
        _save_raw_block_file(rel, wonder_file)
        refreshed = P.WonderFile()
        refreshed.parse(_read_rel(rel))
        reg._parsed[rel] = refreshed
    return updated


def _render_wonder_prereq_section(
    advance_ident: str,
    advance_label: str,
    no_prereq: bool,
) -> str:
    """Render a CTP2-style wonder prerequisite section."""
    lines = ["Requires:"]
    if no_prereq or not advance_ident:
        lines.append("Nothing")
    else:
        lines.append(f"<L:DATABASE_ADVANCES,{advance_ident}>{advance_label}<e>")
    lines.extend(
        [
            "",
            "Costs:",
            '{WonderDB(Wonder[0]).ProductionCost} <L:DATABASE_CONCEPTS,CONCEPT_PRODUCTION>Production<e>',
        ]
    )
    return "\n".join(lines)


def _render_wonder_statistics_section(statistics_text: str, ident: str, display_name: str) -> str:
    """Render a CTP2-style wonder statistics section."""
    lines = ["Gives:"]
    if statistics_text:
        lines.extend(statistics_text.splitlines())
    else:
        lines.append(f"<L:DATABASE_WONDERS,{ident}>{display_name}<e>")
    return "\n".join(lines)


def _ensure_runtime_wonder_gl_surfaces(
    gl_strings: P.StringDBFile,
    gl_library: P.LibraryFile,
    waw_library: P.LibraryFile,
    wonder_specs: list[dict[str, object]],
) -> tuple[int, int, int, int]:
    """Ensure live WONDER_* blocks have names, scenario-owned art, and GL sections."""
    wonder_name_map = {spec["wonder_id"]: spec["name"] for spec in wonder_specs}
    wonder_no_prereq = {spec["wonder_id"] for spec in wonder_specs if spec["no_prereq"]}
    wonder_spec_map = {spec["wonder_id"]: spec for spec in wonder_specs}
    wonder_blocks = _load_raw_block_file("default/gamedata/Wonder.txt")
    uniticon = reg.load("default/gamedata/uniticon.txt")
    wondericon = reg.load("default/gamedata/wondericon.txt")

    added_strings = 0
    added_sections = 0
    added_icons = 0
    runtime_art_written = _write_momjr_wonder_icon_art(wonder_specs)
    wondericon_entries: list[str] = []

    for ident, block_text in wonder_blocks.blocks.items():
        if not ident.startswith("WONDER_"):
            continue
        spec = wonder_spec_map.get(ident, {})
        display_name = wonder_name_map.get(ident, humanize_ident(ident, "WONDER_"))
        description_key = _raw_block_value(block_text, "Description") or f"DESCRIPTION_{ident}"
        advance_ident = _raw_block_value(block_text, "EnableAdvance")
        icon_id = _raw_block_value(block_text, "DefaultIcon") or str(spec.get("icon_id") or f"ICON_{ident}")
        icon_asset = str(spec.get("icon_asset") or f"{icon_id}.TGA")

        if gl_strings.entries.get(ident) != display_name:
            if ident not in gl_strings.entries:
                added_strings += 1
            gl_strings.entries[ident] = display_name

        description_text = str(spec.get("gl_description") or "").strip() or gl_strings.entries.get(
            description_key,
            f"{display_name} is a {MOD_DISPLAY_NAME} world wonder.",
        )
        if description_key not in gl_strings.entries:
            gl_strings.entries[description_key] = description_text
            added_strings += 1
        elif gl_strings.entries.get(description_key) != description_text:
            gl_strings.entries[description_key] = description_text

        desired_uniticon = {
            "FirstFrame": f'"{icon_asset}"',
            "Movie": '"NULL"',
            "Gameplay": f'"{ident}_GAMEPLAY"',
            "Historical": f'"{ident}_HISTORICAL"',
            "Prereq": f'"{ident}_PREREQ"',
            "Vari": f'"{ident}_STATISTICS"',
            "Icon": f'"{icon_asset}"',
            "LargeIcon": '"NULL"',
            "SmallIcon": '"NULL"',
            "StatText": f'"{ident}_STATISTICS"',
        }
        if uniticon.blocks.get(icon_id) != desired_uniticon:
            if icon_id not in uniticon.blocks:
                added_icons += 1
            uniticon.blocks[icon_id] = desired_uniticon

        wondericon_entries.append(
            "\t".join(
                [
                    icon_id,
                    f'"{icon_asset}"',
                    '"null"',
                    f'"{ident}_GAMEPLAY"',
                    f'"{ident}_HISTORICAL"',
                    f'"{ident}_PREREQ"',
                    f'"{ident}_STATISTICS"',
                    f'"{icon_asset}"',
                    f'"{ident}_STATISTICS"',
                ]
            )
        )

        if ident in wonder_no_prereq or not advance_ident:
            prereq_text = _render_wonder_prereq_section("", "", True)
        else:
            advance_label = gl_strings.entries.get(advance_ident, humanize_ident(advance_ident, "ADVANCE_"))
            prereq_text = _render_wonder_prereq_section(advance_ident, advance_label, False)

        historical_text = str(spec.get("gl_historical") or "").strip() or (
            f"{display_name} currently uses runtime wonder proxy data in the MoM scenario build."
        )
        statistics_text = _render_wonder_statistics_section(
            str(spec.get("gl_statistics") or "").strip(),
            ident,
            display_name,
        )
        gameplay_text = str(spec.get("gl_gameplay") or "").strip() or description_text

        sections = {
            f"{ident}_GAMEPLAY": gameplay_text,
            f"{ident}_HISTORICAL": historical_text,
            f"{ident}_PREREQ": prereq_text,
            f"{ident}_STATISTICS": statistics_text,
        }
        for library in (gl_library, waw_library):
            for section_id, content in sections.items():
                if library.sections.get(section_id) != content:
                    if section_id not in library.sections:
                        added_sections += 1
                    library.sections[section_id] = content

    wondericon.entries = wondericon_entries
    return added_strings, added_sections, added_icons, runtime_art_written


def _prune_stale_statistics_links(
    library: P.LibraryFile,
    base_library: P.LibraryFile,
    keep_ids: set[str],
    database_name: str,
    prefixes: tuple[str, ...],
) -> int:
    """Remove stale database-derived list items from *_STATISTICS sections."""
    prefix_group = '|'.join(re.escape(prefix) for prefix in prefixes)
    pattern = re.compile(
        rf'^\s*<L:{re.escape(database_name)},((?:{prefix_group})[A-Z0-9_]*)>(.*?)<e>\s*$'
    )
    removed = 0
    for section_id, base_content in base_library.sections.items():
        if not section_id.endswith("_STATISTICS"):
            continue
        current_content = library.sections.get(section_id)
        if current_content is None:
            continue

        stale_line_texts = set()
        stale_rendered_lines = set()
        stale_normalized_lines = set()
        for raw_line in base_content.splitlines():
            match = pattern.match(raw_line.strip())
            if not match:
                continue
            if match.group(1) in keep_ids:
                continue
            stale_rendered_lines.add(raw_line.strip())
            stale_line_texts.add(match.group(2).strip())
            stale_normalized_lines.add(_normalized_gl_compare_text(match.group(2)))

        if not stale_line_texts and not stale_rendered_lines:
            continue

        kept_lines = []
        changed = False
        for line in current_content.splitlines():
            stripped = line.strip()
            normalized = _normalized_gl_compare_text(stripped)
            if (
                stripped in stale_rendered_lines
                or stripped in stale_line_texts
                or normalized in stale_normalized_lines
            ):
                removed += 1
                changed = True
                continue
            kept_lines.append(line)

        if changed:
            library.sections[section_id] = "\n".join(kept_lines)
    return removed


def _prune_wonder_surfaces() -> tuple[int, int, int, int, int, int, int]:
    """Prune stale wonder surfaces to the IDs currently present in Wonder.txt."""
    wonder_file = _load_raw_block_file("default/gamedata/Wonder.txt")
    live_wonders = set(wonder_file.blocks)

    uniticon = reg.load("default/gamedata/uniticon.txt")
    keep_wonder_icons = set()
    for block_text in wonder_file.blocks.values():
        keep_wonder_icons.update(re.findall(r'^\s*DefaultIcon\s+(\S+)', block_text, re.MULTILINE))
    removed_uniticon_wonders = 0
    for icon_id in list(uniticon.blocks):
        if not icon_id.startswith("ICON_WONDER_"):
            continue
        if icon_id not in keep_wonder_icons:
            del uniticon.blocks[icon_id]
            removed_uniticon_wonders += 1

    gl_strings = reg.load("english/gamedata/gl_str.txt")
    removed_gl_strings = _prune_gl_strings(gl_strings, live_wonders, ("WONDER_",))

    gl_library = reg.load("english/gamedata/Great_Library.txt")
    base_gl_library = _load_base_library_file("english/gamedata/Great_Library.txt")
    removed_gl_sections = _prune_gl_sections(gl_library, live_wonders, ("WONDER_",))
    removed_gl_links = _strip_stale_database_links(
        gl_library,
        live_wonders,
        "DATABASE_WONDERS",
        ("WONDER_",),
    )
    removed_gl_stat_lines = _prune_stale_statistics_links(
        gl_library,
        base_gl_library,
        live_wonders,
        "DATABASE_WONDERS",
        ("WONDER_",),
    )

    waw_library = _load_library_file("english/gamedata/WAW_Great_Library.txt")
    removed_waw_sections = _prune_gl_sections(waw_library, live_wonders, ("WONDER_",))
    removed_waw_links = _strip_stale_database_links(
        waw_library,
        live_wonders,
        "DATABASE_WONDERS",
        ("WONDER_",),
    )
    if removed_waw_sections or removed_waw_links:
        _save_library_file("english/gamedata/WAW_Great_Library.txt", waw_library)

    return (
        len(live_wonders),
        removed_uniticon_wonders,
        removed_gl_strings,
        removed_gl_sections + removed_waw_sections,
        removed_gl_links + removed_waw_links,
        removed_gl_stat_lines,
        len(keep_wonder_icons),
    )


def main():
    # ========================================================================
    # RECONSTRUCT FROM NOTHING: Nuke scenario-generated files before starting.
    # This guarantees zero base CTP2 artifacts (like "Behavioral Mod Center") 
    # leak into the scenario. The CSV control plane is the absolute source of truth.
    # ========================================================================
    Scenario_files_to_nuke = [
        # NOTE: "default/gamedata/buildings.txt" is intentionally REMOVED from nuke list.
        # It is reconstructed from improvements.csv earlier in the pipeline (line ~628).
        # Nuking it here and then failing to import buildings.csv (which doesn't exist)
        # leaves it empty, breaking _ensure_runtime_building_gl_surfaces.
        "default/gamedata/Wonder.txt",
        "default/gamedata/Improve.txt",
        "default/gamedata/Units.txt",
        "english/gamedata/gl_str.txt",
        "english/gamedata/Great_Library.txt",
        "english/gamedata/WAW_Great_Library.txt",
    ]
    for rel in Scenario_files_to_nuke:
        fpath = SCENARIO / rel
        # Create an EMPTY file to prevent reg.load() from falling back to base CTP2 data
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text("", encoding="latin-1")
        # Also clear from registry cache so it starts empty
        reg._parsed.pop(rel, None)

    csv_imports = []
    for csv_name, rel, apply_kind in (
        ("buildings.csv", "default/gamedata/buildings.txt", "raw"),
        ("improveicon.csv", "default/gamedata/improveicon.txt", "counted-entry"),
        ("wonders.csv", "default/gamedata/Wonder.txt", "raw"),
        ("wondericon.csv", "default/gamedata/wondericon.txt", "counted-entry"),
        ("wondermovie.csv", "default/gamedata/wondermovie.txt", "entry"),
        ("goods.csv", "default/gamedata/goods.txt", "raw"),
        ("goodsid.csv", "default/gamedata/goodsID.txt", "entry"),
        ("goodsicon.csv", "default/gamedata/goodsicon.txt", "counted-entry"),
        # terrain.csv intentionally NOT imported: terrain is a KEEP dimension per
        # dimension_inventory.md ("Base content retained"). terrain.csv is structured
        # (columns), not raw CTP2 block text, so the "raw" importer wiped terrain.txt
        # to 1 line, dropping all 26 base terrains (e.g. TERRAIN_BROWN_MOUNTAIN /
        # "Desert Mountain") and breaking every <L:DATABASE_TERRAIN,...> GL link.
        ("terrainicon.csv", "default/gamedata/terrainicon.txt", "counted-entry"),
        ("governments.csv", "default/gamedata/govern.txt", "raw"),
        ("governicon.csv", "default/gamedata/governicon.txt", "counted-entry"),
        ("orders.csv", "default/gamedata/Orders.txt", "raw"),
        ("concepts.csv", "default/gamedata/concept.txt", "counted-raw"),
    ):
        if not _csv_exists(csv_name):
            continue
        if apply_kind == "raw":
            count = _apply_raw_block_csv(csv_name, rel)
        elif apply_kind == "counted-raw":
            count = _apply_raw_block_csv(csv_name, rel, counted=True)
        elif apply_kind == "counted-entry":
            count = _apply_entry_csv(csv_name, rel, counted=True)
        else:
            count = _apply_entry_csv(csv_name, rel)
        csv_imports.append((csv_name, rel, count))
    if _csv_exists("building_uniticon.csv"):
        count = _apply_block_overlay_csv("building_uniticon.csv", "default/gamedata/uniticon.txt")
        csv_imports.append(("building_uniticon.csv", "default/gamedata/uniticon.txt", count))
    for csv_name, rel, count in csv_imports:
        print(f"  + csv-owned: {csv_name} -> {rel} ({count} row(s))")

    reg.load("default/gamedata/Wonder.txt")
    reg.load("default/gamedata/uniticon.txt")
    reg.load("default/gamedata/Improve.txt")
    reg.load("default/gamedata/Advance.txt")
    reg.load("default/gamedata/tileimp.txt")
    reg.load("english/gamedata/gl_str.txt")
    reg.load("english/gamedata/Great_Library.txt")

    mom_advance_idents: set[str] = set(MOM_UNIT_ADVANCE.values())

    # Generate stub advances for base-unit EnableAdvance refs not in advances.csv
    adv_file = reg.load("default/gamedata/Advance.txt")
    for ident, (name, cat, age) in _BASE_UNIT_STUB_ADVANCES.items():
        if ident not in adv_file.blocks:
            P.ModAdvance(ident, name, "500", cat, age).register(reg)
            print(f"  + stub advance: {name}")

    with open(str(MOMJR / "advances.csv"), newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            name = row['name'].split(';')[0].strip()
            if not name or name.startswith('x') or 'Extra Advance' in name or name.lower() == 'blah':
                continue
            ident = f"ADVANCE_{sanitize(name)}"
            mom_advance_idents.add(ident)
            epoch = row['epoch'].strip()
            cat = row['category'].strip()
            prereqs = []
            for code_col in ('prereq1', 'prereq2'):
                code = row.get(code_col, '').strip()
                if code and code not in _NO_ADVANCE:
                    adv_id = MOM_UNIT_ADVANCE.get(code)
                    if adv_id:
                        prereqs.append(adv_id)
            is_new = ident not in reg.load("default/gamedata/Advance.txt").blocks
            P.ModAdvance(ident, name, "1000", cat, _AGE_MAP.get(str(epoch), 'AGE_ONE'),
                         prereqs=prereqs).register(reg)
            if is_new:
                print(f"  + advance: {name}")
    retuned_advance_costs = _retune_mom_advance_costs(adv_file)
    if retuned_advance_costs:
        print(f"  + rescaled {retuned_advance_costs} MoM advance cost(s) into AE age bands")
    advance_ages = _advance_age_map_from_text(adv_file._text)

    # Backfill display names for pre-existing advances that still show raw ADVANCE_* IDs
    adv_file = reg.load("default/gamedata/Advance.txt")
    gl_str = reg.load("english/gamedata/gl_str.txt")
    for ident in sorted(adv_file.blocks):
        if ident not in gl_str.entries:
            gl_str.entries[ident] = humanize_ident(ident, "ADVANCE_")
    gl_library = reg.load("english/gamedata/Great_Library.txt")
    base_gl_library = _load_base_library_file("english/gamedata/Great_Library.txt")
    restored_base_advance_gl = _restore_base_advance_gl_prose(
        gl_library,
        base_gl_library,
        set(adv_file.blocks),
    )
    waw_library = _load_library_file("english/gamedata/WAW_Great_Library.txt")
    base_waw_library = _load_base_library_file("english/gamedata/WAW_Great_Library.txt")
    restored_base_waw_advance_gl = _restore_base_advance_gl_prose(
        waw_library,
        base_waw_library,
        set(adv_file.blocks),
    )
    if restored_base_waw_advance_gl:
        _save_library_file("english/gamedata/WAW_Great_Library.txt", waw_library)
    if restored_base_advance_gl or restored_base_waw_advance_gl:
        print(
            "  + restored stock advance GL prose "
            f"({restored_base_advance_gl} base section(s),"
            f" {restored_base_waw_advance_gl} WAW section(s))"
        )

    # Ensure every advance referenced by the Great Library exists in the Advance DB.
    # CTP2 validates each GL [ADVANCE_X_*] section header AND each
    # <L:DATABASE_ADVANCES,ADVANCE_X> prose link against the Advance database at load,
    # hard-erroring "X not found in Advance database" on the first miss. The base GL
    # ships prose/links for ~87 advances the MoM data set doesn't define (Drama,
    # Aerodynamics, ...), and _restore_missing_uniticon_gl_sections re-adds them on
    # every run — so pruning the sections is futile (they come back). Instead create
    # the missing advances as hidden stub blocks; the GLHidden pass below keeps them
    # out of the player-facing tech tree. This mirrors the "hide base records, don't
    # delete them" approach already used for base units.
    gl_referenced_advances: set[str] = set()
    for _gl in (gl_library, waw_library):
        for sid, content in _gl.sections.items():
            base = _section_base_id(sid)
            if base.startswith("ADVANCE_"):
                gl_referenced_advances.add(base)
            gl_referenced_advances.update(
                re.findall(r"<L:DATABASE_ADVANCES,(ADVANCE_[A-Z0-9_]+)>", content)
            )
    gl_stub_added = 0
    for ident in sorted(gl_referenced_advances):
        if ident not in adv_file.blocks:
            P.ModAdvance(ident, humanize_ident(ident, "ADVANCE_"), "999999",
                         "0", "AGE_ONE", icon="ICON_ADVANCE_DEFAULT").register(reg)
            gl_stub_added += 1
    if gl_stub_added:
        print(f"  + created {gl_stub_added} hidden stub advance(s) for GL-referenced advances")

    with open(str(MOMJR / "improvements.csv"), newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            name = row['name'].strip()
            if not name:
                continue
            
            # Check for HIDE prefix
            is_hidden = name.upper().startswith("HIDE ")
            if is_hidden:
                name = name[5:].strip()
            
            if name.startswith('x') or name == 'Nothing' or 'SS ' in name:
                continue
            
            ident = f"IMPROVE_{sanitize(name)}"
            imp = reg.load("default/gamedata/Improve.txt")
            is_new = ident not in imp.blocks
            cost = int(row.get('cost', '0').strip() or '0') * int(MOD_POLICY["improvement_cost_mult"])
            upkeep = row.get('upkeep', '0').strip()
            prereq_code = row.get('prereq', '').strip()
            advance = advance_id(prereq_code) if prereq_code else ""
            if advance:
                mom_advance_idents.add(advance)
            
            # Register the building
            P.ModBuilding(ident, name, str(cost), upkeep, advance).register(reg)
            
            # If hidden, mark it in the Improve.txt fields so _merge_mom_improvements_into_buildings can add flags
            if is_hidden and is_new:
                imp_file = reg.load("default/gamedata/Improve.txt")
                if ident in imp_file.blocks:
                    imp_file.blocks[ident]["HIDDEN"] = "yes"
            
            if is_new and not is_hidden:
                print(f"  + building: {name} (cost {cost})")
            elif is_new and is_hidden:
                print(f"  - hiding base building: {name}")

    # Deduplication: remove any IMPROVE_* from Improve.txt that is already
    # defined in buildings.txt.  CTP2 loads both files sequentially; duplicate
    # IDs produce DB index collisions that cause silent crashes before turn 10.
    _bld_raw = _load_raw_block_file("default/gamedata/buildings.txt")
    _bld_imps = {bid for bid in _bld_raw.blocks if bid.startswith("IMPROVE_")}
    _dup_imp_file = reg.load("default/gamedata/Improve.txt")
    _dup_removed = 0
    for _bid in sorted(_bld_imps):
        if _bid in _dup_imp_file.blocks:
            del _dup_imp_file.blocks[_bid]
            _dup_removed += 1
    if _dup_removed:
        print(f"  - deduped {_dup_removed} improve(s) from Improve.txt (already in buildings.txt)")

    # Reconciliation: ensure every IMPROVE_* in buildings.txt has a uniticon entry.
    # Since Improve.txt is nuked, we now read from buildings.txt to ensure all
    # buildings have a minimal UPLG001.TGA fallback so the icon-coverage audit passes.
    _bld_file  = _load_raw_block_file("default/gamedata/buildings.txt")
    _ui_file   = reg.load("default/gamedata/uniticon.txt")
    _filled_ui = 0
    for _bid, _block_text in _bld_file.blocks.items():
        _icon_id = _raw_block_value(_block_text, "DefaultIcon") or f"ICON_{_bid}"
        if _icon_id not in _ui_file.blocks:
            _ui_file.blocks[_icon_id] = {
                "FirstFrame": '"UPLG001.TGA"',
                "Movie":      '"NULL"',
                "Gameplay":   f'"{_bid}_GAMEPLAY"',
                "Historical": f'"{_bid}_HISTORICAL"',
                "Prereq":     f'"{_bid}_PREREQ"',
                "Vari":       f'"{_bid}_STATISTICS"',
                "Icon":       '"UPLG001.TGA"',
                "LargeIcon":  '"NULL"',
                "SmallIcon":  '"NULL"',
                "StatText":   f'"{_bid}_STATISTICS"',
            }
            _filled_ui += 1
    if _filled_ui:
        print(f"  + backfilled {_filled_ui} missing building uniticon entry(ies) with UPLG001.TGA fallback")
    
    # Cleanup: remove any ICON_IMPROVE_* from uniticon.txt that does NOT exist in buildings.txt.
    # Since buildings.txt is reconstructed strictly from improvements.csv, base-game buildings
    # not in the control plane will be missing, but their uniticon entries may linger and cause
    # "X not found in Building database" errors.
    _valid_building_icons = set()
    for _bid, _block_text in _bld_file.blocks.items():
        _valid_building_icons.add(_raw_block_value(_block_text, "DefaultIcon") or f"ICON_{_bid}")
    
    _removed_stale_ui = 0
    for _icon_id in list(_ui_file.blocks.keys()):
        if _icon_id.startswith("ICON_IMPROVE_") and _icon_id not in _valid_building_icons:
            del _ui_file.blocks[_icon_id]
            _removed_stale_ui += 1
    
    if _removed_stale_ui:
        print(f"  + removed {_removed_stale_ui} stale building uniticon entry(ies) not in control plane")

    wonder_specs = _load_canonical_momjr_wonders()
    gl_str = reg.load("english/gamedata/gl_str.txt")
    gl_library = reg.load("english/gamedata/Great_Library.txt")
    waw_library = _load_library_file("english/gamedata/WAW_Great_Library.txt")
    synchronized_wonder_blocks = _synchronize_runtime_wonder_blocks(wonder_specs)
    (
        removed_wonder_improve_blocks,
        removed_wonder_improve_icons,
        removed_wonder_improve_links,
    ) = _remove_migrated_wonder_improvements(gl_str, gl_library, waw_library, wonder_specs)
    (
        added_runtime_wonder_strings,
        added_runtime_wonder_sections,
        added_runtime_wonder_icons,
        written_runtime_wonder_art,
    ) = _ensure_runtime_wonder_gl_surfaces(gl_str, gl_library, waw_library, wonder_specs)
    retuned_wonder_costs = _retune_mom_wonder_costs(advance_ages)
    retuned_improvement_costs = _retune_mom_improvement_costs(advance_ages)
    if retuned_improvement_costs:
        print(f"  + rescaled {retuned_improvement_costs} improvement cost(s) into base CTP2 age bands")
    if any((
        removed_wonder_improve_blocks,
        removed_wonder_improve_icons,
        removed_wonder_improve_links,
        synchronized_wonder_blocks,
        retuned_wonder_costs,
        added_runtime_wonder_strings,
        added_runtime_wonder_sections,
        added_runtime_wonder_icons,
        written_runtime_wonder_art,
    )):
        print(
            "  + migrated MOMJR wonder slots into the Wonder DB"
            f" ({removed_wonder_improve_blocks} old Improve block(s) removed,"
            f" {removed_wonder_improve_icons} old uniticon block(s) removed,"
            f" {removed_wonder_improve_links} stale GL improve link(s) stripped,"
            f" {synchronized_wonder_blocks} Wonder block(s) synchronized,"
            f" {retuned_wonder_costs} Wonder cost(s) rescaled,"
            f" {added_runtime_wonder_strings} wonder string(s) added,"
            f" {added_runtime_wonder_sections} wonder GL section(s) added,"
            f" {added_runtime_wonder_icons} wonder icon block(s) added,"
            f" {written_runtime_wonder_art} wonder art file(s) written)"
        )
    _save_library_file("english/gamedata/WAW_Great_Library.txt", waw_library)

    # --- Fantasy research-tree isolation ------------------------------------
    # Authoritative fantasy advance set = advances.csv only. Any Advance.txt
    # block outside it is FOREIGN (base CTP2 / WAW) and must not be researchable.
    #
    # Engine truth (verified against ctp2_code):
    #   * ui/interface/sci_advancescreen.cpp::sci_advancescreen_loadList shows an
    #     advance iff Advances::CanResearch()[i] is TRUE. It never consults
    #     GLHidden -- GLHidden is honored ONLY by greatlibrary.cpp. So GLHidden
    #     hides an advance from the Great Library but NOT from the research tree.
    #   * gs/gameobj/Advances.cpp::ResetCanResearch forces canResearch=FALSE for
    #     any advance that lists ITSELF as a Prerequisites entry (lines 498-502),
    #     permanently and irrespective of Either/Government prereqs, while the
    #     block stays in the Advance DB so every cross-reference still resolves
    #     (no "X not found in Advance database" crash, no GL DB-name crash).
    #
    # Therefore, to show ONLY fantasy advances in the research tree:
    #   (a) sever every fantasy advance's prerequisite edges that point at a
    #       foreign advance, so the fantasy tree never depends on a hidden tech
    #       and stays fully researchable; then
    #   (b) give every foreign advance a self-prerequisite so it can never be
    #       researched (removed from the science screen) without deleting it.
    # GLHidden/GoodyHutExcluded are still applied to foreign advances for Great
    # Library cleanliness and to keep them out of goody-hut rewards.
    momjr_visible_idents = _load_momjr_advance_idents()

    severed_edges = 0
    kept_closed = 0
    for ident in sorted(momjr_visible_idents & set(adv_file.blocks)):
        all_prereqs = adv_file.get_prerequisites(ident)
        foreign_prereqs = [
            pr for pr in all_prereqs
            if pr not in momjr_visible_idents
            and not pr.startswith("ADVANCE_HOME_")  # SLIC-granted sphere homes
        ]
        if foreign_prereqs and adv_file.remove_prerequisites(ident, foreign_prereqs):
            severed_edges += len(foreign_prereqs)
            # Source mods gate scenario-granted content behind an unreachable
            # prerequisite (e.g. LotR racial advances -> ADVANCE_GAIA_CONTROLLER).
            # When EVERY prerequisite was foreign, severing must keep the advance
            # closed — not promote it to a free researchable root that un-gates
            # its whole downstream family (56 hero units in SMM).
            if len(foreign_prereqs) == len(all_prereqs) \
                    and adv_file.ensure_self_prerequisite(ident):
                kept_closed += 1
    if severed_edges:
        print(f"  + severed {severed_edges} fantasy->foreign prerequisite edge(s)")
    if kept_closed:
        print(f"  + kept {kept_closed} unreachable-gated advance(s) closed (self-prereq)")

    hidden_advances = 0
    goody_excluded_advances = 0
    unresearchable_foreign = 0
    for ident in sorted(adv_file.blocks):
        if ident in momjr_visible_idents:
            continue
        if adv_file.ensure_flags(ident, ["GLHidden"]):
            hidden_advances += 1
        if adv_file.ensure_flags(ident, ["GoodyHutExcluded"]):
            goody_excluded_advances += 1
        if adv_file.ensure_self_prerequisite(ident):
            unresearchable_foreign += 1
    if hidden_advances:
        print(f"  + hid {hidden_advances} foreign advance(s) from Great Library index")
    if goody_excluded_advances:
        print(f"  + excluded {goody_excluded_advances} foreign advance(s) from goody-hut rewards")
    if unresearchable_foreign:
        print(f"  + made {unresearchable_foreign} foreign advance(s) unresearchable (self-prereq)")

    # Sphere-home exclusivity (mod_policy "sphere_home_exclusivity"): each
    # magic sphere's research ladder additionally requires an unresearchable
    # ADVANCE_HOME_<SPHERE>, granted per player by SLIC at game start — so a
    # tribe can only ever walk ITS OWN sphere's ladder (civ-exclusive rosters),
    # while neutral/human content stays open to everyone. The HOME advances
    # are whitelisted in the sever pass and the closed-gate hygiene pass:
    # self-prereq blocks RESEARCH, but SLIC GrantAdvance bypasses prereqs.
    if MOD_POLICY.get("sphere_home_exclusivity"):
        _SPHERE_LADDER_IDENTS = {
            "LIFE":    ["ADVANCE_LIFE_LORE", "ADVANCE_LIFE_ADEPT", "ADVANCE_LIFE_MAGE",
                        "ADVANCE_LIFE_WIZARD", "ADVANCE_LIFE_MASTER"],
            "NATURE":  ["ADVANCE_NATURE_LORE", "ADVANCE_NATURE_ADEPT", "ADVANCE_NATURE_MAGE",
                        "ADVANCE_NATURE_WIZARD", "ADVANCE_NATURE_MASTER"],
            "SORCERY": ["ADVANCE_SORCEROUS_LORE", "ADVANCE_SORCERY_ADEPT", "ADVANCE_SORCERY_MAGE",
                        "ADVANCE_SORCERY_WIZARD", "ADVANCE_SORCERY_MASTER"],
            "DEATH":   ["ADVANCE_DEATH_LORE", "ADVANCE_DEATH_ADEPT", "ADVANCE_DEATH_MAGE",
                        "ADVANCE_DEATH_WIZARD", "ADVANCE_DEATH_MASTER"],
            "CHAOS":   ["ADVANCE_CHAOS_LORE", "ADVANCE_CHAOS_ADEPT", "ADVANCE_CHAOS_MAGE",
                        "ADVANCE_CHAOS_WIZARD", "ADVANCE_CHAOS_MASTER"],
        }
        homes_created = 0
        wired = 0
        for sphere, ladder in _SPHERE_LADDER_IDENTS.items():
            home = f"ADVANCE_HOME_{sphere}"
            if home not in adv_file.blocks:
                P.ModAdvance(home, f"{sphere.title()} Homeland", "999999",
                             "0", "AGE_ONE", icon="ICON_ADVANCE_DEFAULT").register(reg)
                homes_created += 1
            adv_file = reg.load("default/gamedata/Advance.txt")
            adv_file.ensure_self_prerequisite(home)
            adv_file.ensure_flags(home, ["GLHidden"])
            adv_file.ensure_flags(home, ["GoodyHutExcluded"])
            for ladder_ident in ladder:
                if ladder_ident in adv_file.blocks \
                        and adv_file.ensure_prerequisite(ladder_ident, home):
                    wired += 1
        print(f"  + sphere-home exclusivity: {homes_created} HOME advance(s) created, "
              f"{wired} ladder prereq(s) wired")

    else:
        # Policy OFF (mod_policy.json carries no sphere_home_exclusivity key),
        # so the ADVANCE_HOME_* advances are never created -- but an earlier
        # run left mom_sphere_home.slc on disk AND #include'd from
        # scenario.slc, citing five advances that do not exist. That is the
        # mom-db-error-class crash surface exactly. Sever it; the per-tribe
        # wall is mod_CanPlayerHaveAdvance in mom_gating.slc, not this.
        _home_path = SCENARIO / "default/gamedata/mom_sphere_home.slc"
        _scen_slc = _read_rel("default/gamedata/scenario.slc")
        if '#include "mom_sphere_home.slc"' in _scen_slc:
            _write_rel("default/gamedata/scenario.slc",
                       "".join(l for l in _scen_slc.splitlines(keepends=True)
                               if 'mom_sphere_home.slc' not in l))
            print("  + scenario.slc: severed stale mom_sphere_home.slc include")
        if _home_path.exists():
            _home_path.unlink()
            print("  + removed stale mom_sphere_home.slc (policy off)")

    # --- Tech cap + age re-layout ---------------------------------------
    # ORDERING: after ALL advance ingestion and ladder wiring, and BEFORE the
    # tileimp.txt/govern.txt rebuilds (~:3939-4006). The mask must precede
    # govern's rebuild so the existing _government_ids_enabled_by_live_advances
    # self-heal drops the 7 modern governments off the live Advance.txt.
    masked = _apply_advance_mask(adv_file)
    if masked:
        print(f"  + tech cap: removed {masked} modern/junk advance(s)")
    aged, _age_hist = _relayout_advance_ages(adv_file)
    if aged:
        print(f"  + age re-layout: {aged} advance(s) re-aged; histogram {_age_hist}")
        # Ages changed -> research costs must be re-banded, and advance_ages
        # (which feeds the improvement cost bands) refreshed off the NEW tree.
        _retune_mom_advance_costs(adv_file)
        advance_ages = _advance_age_map_from_text(adv_file._text)

        # SLIC start-of-game grants: player index -> sphere is the scenario
        # contract (players.csv order: 1 Life, 2 Nature, 3 Sorcery, 4 Death,
        # 5 Chaos). GrantAdvance(player, AdvanceDB(...)) is engine-verified
        # (slicfunc.cpp Slic_GrantAdvance). BeginTurn + per-player latch is
        # the base-verified one-shot idiom (scenario.slc MomSlicAliveLatch).
        _HOME_SLC = "\n".join([
            "// GENERATOR-OWNED (sphere_home_exclusivity): per-tribe sphere HOME grants.",
            "// Regenerated by ctp2_generator.py -- edit mod_policy.json, not this file.",
            "int_t SmmHomeGrantLatch[31];",
            "",
            "HandleEvent(BeginTurn) 'SmmSphereHomeGrant' pre {",
            "\tint_t p;",
            "\tp = player[0];",
            "\tif (p >= 1) {",
            "\t\tif (p <= 5) {",
            "\t\t\tif (SmmHomeGrantLatch[p] == 0) {",
            "\t\t\t\tSmmHomeGrantLatch[p] = 1;",
            "\t\t\t\tif (p == 1) { GrantAdvance(player[0], AdvanceDB(ADVANCE_HOME_LIFE)); }",
            "\t\t\t\tif (p == 2) { GrantAdvance(player[0], AdvanceDB(ADVANCE_HOME_NATURE)); }",
            "\t\t\t\tif (p == 3) { GrantAdvance(player[0], AdvanceDB(ADVANCE_HOME_SORCERY)); }",
            "\t\t\t\tif (p == 4) { GrantAdvance(player[0], AdvanceDB(ADVANCE_HOME_DEATH)); }",
            "\t\t\t\tif (p == 5) { GrantAdvance(player[0], AdvanceDB(ADVANCE_HOME_CHAOS)); }",
            "\t\t\t}",
            "\t\t}",
            "\t}",
            "}",
            "",
        ])
        _write_rel("default/gamedata/mom_sphere_home.slc", _HOME_SLC)
        _scen_slc = _read_rel("default/gamedata/scenario.slc")
        if '#include "mom_sphere_home.slc"' not in _scen_slc:
            _write_rel("default/gamedata/scenario.slc",
                       _scen_slc.rstrip("\n") + '\n#include "mom_sphere_home.slc"\n')
            print("  + scenario.slc: included mom_sphere_home.slc")

    # --- Units from units.csv ---
    adv_db = reg.load("default/gamedata/Advance.txt")
    mom_unit_idents: set[str] = set()
    mom_unit_display_names: dict[str, str] = {}  # ident -> display name for gl_str backfill

    with open(str(MOMJR / "units.csv"), newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            name = row['name'].strip()
            # Skip stub rows: blank, 'blah', B+digit shortcodes
            if not name or name.lower() == 'blah':
                continue
            if len(name) == 2 and name[0].upper() == 'B' and name[1].isdigit():
                continue

            ident = f"UNIT_{sanitize(name)}"
            mom_unit_idents.add(ident)
            mom_unit_display_names[ident] = name

            domain     = int(row['domain'].strip())
            move       = _parse_move(row['move'])
            attack_raw = _parse_int_stat(row['attack'])
            def_raw    = _parse_int_stat(row['defense'])
            hp_raw     = _parse_int_stat(row['hp'])
            fp_raw     = _parse_int_stat(row['firepower'])
            cost_raw   = int(row['cost'].strip() or '1')
            prereq     = row['prereq'].strip()
            # Scale to CTP2 internal units (per-mod policy: unit_stat_scaling)
            _scal = MOD_POLICY["unit_stat_scaling"]
            attack     = attack_raw * int(_scal["attack_mult"])
            defense    = max(int(_scal["defense_min"]), def_raw * int(_scal["defense_mult"]))
            shield_cost = cost_raw * int(_scal["shield_cost_mult"])
            shield_hunger = max(int(_scal["shield_hunger_min"]),
                                cost_raw // int(_scal["shield_hunger_div"]))
            _default_advance = _scal["default_advance"]

            # Advance prereq — heroes (nil/no) default to earliest advance so
            # EnableAdvance is always present (required in 97% of reference blocks).
            if prereq in _NO_ADVANCE:
                advance = _default_advance
            else:
                advance = MOM_UNIT_ADVANCE.get(prereq, _default_advance)
                if advance not in adv_db.blocks:
                    advance = _default_advance  # graceful fallback

            # Category, sprite, size, sound
            if domain == 2:
                category = 'UNIT_CATEGORY_NAVAL'
            elif domain == 1:
                category = 'UNIT_CATEGORY_AIR'
            else:
                # Per-mod policy: these units must be able to build cities
                if name in set(MOD_POLICY["settler_category_units"]):
                    category = 'UNIT_CATEGORY_SETTLER'
                else:
                    category = 'UNIT_CATEGORY_ATTACK'

            sprite    = _pick_sprite(name, domain, attack)
            size      = _pick_size(name, hp_raw)
            sound_set = _scal["air_sound_set"] if domain == 1 else _scal["land_sound_set"]

            unit = P.ModUnit(
                ident=ident, name=name, category=category,
                attack=attack, defense=defense,
                sprite=sprite, desc=f"{name}: a {MOD_DISPLAY_NAME} unit.",
                advance=advance, move=move, hp=int(_scal["hp"]),
                firepower=max(int(_scal["firepower_min"]), fp_raw), armor=1, zbrange=0,
                shield_cost=shield_cost, shield_hunger=shield_hunger,
                gold_hunger=0, sound_set=sound_set,
                domain=domain, size=size,
            )
            uni = reg.load("default/gamedata/Units.txt")
            is_new = not uni.has_unit(ident)
            unit.register(reg)
            if is_new:
                print(f"  + unit: {name} ({ident})")
    retuned_unit_costs = _retune_mom_unit_costs(reg.load("default/gamedata/Units.txt"), advance_ages)
    if retuned_unit_costs:
        print(f"  + rescaled {retuned_unit_costs} MoM unit cost(s) into base CTP2 age bands")

    # UNIT_SETTLER is RETIRED in MoM (2026-07-03): peasants are the city
    # builders. The block below stays in the DB only for index/GL-reference
    # safety, but it is CantBuild and carries NO "Settle:" terrain lines —
    # both on purpose. gameinit_PlaceInitalUnits (gameinit.cpp:404) spawns
    # the FIRST unit in the DB with SettleLand as each player's starting
    # units, so with settler stripped of Settle lines the engine spawns
    # UNIT_PEASANTS at game start. Do NOT "fix" this back to the pristine
    # base settler: adding Settle lines here re-enables settler starts and
    # settler city-building.
    uni_text_file = reg._parsed.get("default/gamedata/Units.txt")
    if uni_text_file and hasattr(uni_text_file, '_text'):
        # Remove any mangled UNIT_SETTLER the generator might have created
        uni_text_file._text = re.sub(r'UNIT_SETTLER \{.*?\n\}\n?', '', uni_text_file._text, flags=re.DOTALL)
        
        settler_block = _UNIT_BLOCK_OVERRIDES["UNIT_SETTLER"]
        uni_text_file._text = uni_text_file._text.rstrip() + "\n\n" + settler_block
        print("  + force-imported pristine base game UNIT_SETTLER block into Units.txt")
        
        # Also fix the uniticon.txt entry to use a valid MoM TGA to pass audit
        uic = reg.load("default/gamedata/uniticon.txt")
        if "ICON_UNIT_SETTLER" in uic.blocks:
            # Use the actual extracted MoM Settler icon that exists on disk
            uic.blocks["ICON_UNIT_SETTLER"]["FirstFrame"] = '"ICON_UNIT_SETTLER.TGA"'
            uic.blocks["ICON_UNIT_SETTLER"]["Icon"] = '"ICON_UNIT_SETTLER.TGA"'
            uic.blocks["ICON_UNIT_SETTLER"]["LargeIcon"] = '"ICON_UNIT_SETTLER.TGA"'
            uic.blocks["ICON_UNIT_SETTLER"]["SmallIcon"] = '"ICON_UNIT_SETTLER.TGA"'
            print("  + updated ICON_UNIT_SETTLER to use extracted MoM TGA asset")

        # Patch UNIT_PEASANTS: fix DefaultSprite and add Settle: terrain entries.
        # The generator's append-only UnitsFile won't re-render this block automatically;
        # force-replace it using the same pattern as UNIT_SETTLER above.
        # Use ^} with MULTILINE to safely skip the nested CanReform { } sub-block.
        uni_text_file._text = re.sub(
            r'^UNIT_PEASANTS \{.*?^}\n?', '', uni_text_file._text, flags=re.DOTALL | re.MULTILINE
        )
        peasant_block = _UNIT_BLOCK_OVERRIDES["UNIT_PEASANTS"]
        uni_text_file._text = uni_text_file._text.rstrip() + "\n\n" + peasant_block
        print("  + patched UNIT_PEASANTS: DefaultSprite=SPRITE_PEASANTS, Settle: Land/Mountain")

    # CRITICAL: Ensure UNIT_CITY exists in Units.txt, uniticon.txt, and gl_str.txt.
    # The engine requires this internal unit for settlers to build cities.
    if uni_text_file and hasattr(uni_text_file, '_text'):
        if "UNIT_CITY {" not in uni_text_file._text:
            # Complete base-game UNIT_CITY block (verbatim from
            # ctp2_data/default/gamedata/Units.txt). The earlier truncated
            # stub lacked the terrain classes (MovementType/Size/VisionClass)
            # and flags, which can make GEV_CreateCity city placement fail
            # silently after a settle order.
            unit_city_block = """UNIT_CITY {
   Description DESCRIPTION_UNIT_CITY
   DefaultIcon ICON_UNIT_CITY
   DefaultSprite SPRITE_CITY
   Category UNIT_CATEGORY_GENERIC
   Attack 0
   Defense 0
   ZBRangeAttack 0
   Firepower 0
   Armor 0
   MaxHP 0
   ShieldCost 0
   PowerPoints 1000
   ShieldHunger 0
   FoodHunger 0
   MaxMovePoints 0
   VisionRange 2
   ActiveDefenseRange 0
   LossMoveToDmgNone
   MaxFuel 0
   HasPopAndCanBuild
   CantBuild
   CityGrowthCoefficient 1
   NoIndex
   GLHidden
   CantCaptureCity
   NeedsNoSupport
   SoundSelect1 SOUND_SELECT1_CITY
   SoundSelect2 SOUND_SELECT2_CITY
   SoundMove SOUND_MOVE_CITY
   SoundAcknowledge SOUND_ACKNOWLEDGE_CITY
   SoundCantMove SOUND_CANTMOVE_CITY
   SoundAttack SOUND_ATTACK_CITY
   SoundWork SOUND_WORK_CITY
   SoundVictory SOUND_VICTORY_CITY
   SoundDeath SOUND_DEATH_CITY

   CanAttack: Land
   CanAttack: Mountain
   CanSee: Standard
   MovementType: Land
   MovementType: Mountain
   MovementType: Sea
   MovementType: ShallowWater
   Size: Medium
   VisionClass: Standard

   Revolution {
      Sound SOUND_ID_REVOLUTION
      Effect SPECEFFECT_REVOLUTION
   }
}
"""
            uni_text_file._text = uni_text_file._text.rstrip() + "\n\n" + unit_city_block
            print("  + injected missing UNIT_CITY block into Units.txt")
            
            # Also ensure it's in uniticon.txt
            uic = reg.load("default/gamedata/uniticon.txt")
            if "ICON_UNIT_CITY" not in uic.blocks:
                uic.blocks["ICON_UNIT_CITY"] = {
                    "FirstFrame": '"UPUP002L.TGA"',
                    "Movie": '"NULL"',
                    "Gameplay": '"UNIT_CITY_GAMEPLAY"',
                    "Historical": '"UNIT_CITY_HISTORICAL"',
                    "Prereq": '"UNIT_CITY_PREREQ"',
                    "Vari": '"UNIT_CITY_STATISTICS"',
                    "Icon": '"UPUP002A.TGA"',
                    "LargeIcon": '"UPUP002L.TGA"',
                    "SmallIcon": '"UPUP002B.TGA"',
                    "StatText": '"UNIT_CITY_SUMMARY"',
                }
                print("  + injected missing ICON_UNIT_CITY into uniticon.txt")
                
            # And in gl_str.txt
            gl_str = reg.load("english/gamedata/gl_str.txt")
            if "UNIT_CITY" not in gl_str.entries:
                gl_str.entries["UNIT_CITY"] = "City"
                gl_str.entries["DESCRIPTION_UNIT_CITY"] = "The center of your civilization."
                print("  + injected missing UNIT_CITY strings into gl_str.txt")

    # CRITICAL: Strip invalid UpgradeTo references from Units.txt.
    # If a unit (like UNIT_CLERIC) references a target unit that isn't in the 
    # control plane, the engine will crash with "X not found in Unit database".
    uni_text_file = reg._parsed.get("default/gamedata/Units.txt")
    if uni_text_file and hasattr(uni_text_file, '_text'):
        live_units_for_upgrade = set(_load_raw_block_file("default/gamedata/Units.txt").blocks)
        original_text = uni_text_file._text
        
        def _strip_invalid_upgrade(match):
            target_unit = match.group(1)
            if target_unit not in live_units_for_upgrade:
                return "" # Remove the line entirely
            return match.group(0)
        
        # Match "   UpgradeTo UNIT_XXXX" with optional trailing whitespace and newline
        uni_text_file._text = re.sub(
            r'^[ \t]*UpgradeTo[ \t]+(UNIT_[A-Z0-9_]+)[ \t]*\r?\n',
            _strip_invalid_upgrade,
            original_text,
            flags=re.MULTILINE
        )
        if uni_text_file._text != original_text:
            print("  + stripped invalid UpgradeTo references from Units.txt")

    # Backfill display names for MoM units missing from gl_str.txt.
    # Use the exact name from units.csv (not the humanized fallback) so the
    # Build Manager shows "Gargoyles" instead of "UNIT_GARGOYLES".
    _unit_gl_str = reg.load("english/gamedata/gl_str.txt")
    added_unit_strings = 0
    for _uid, _display in sorted(mom_unit_display_names.items()):
        if _uid not in _unit_gl_str.entries:
            _unit_gl_str.entries[_uid] = _display
            added_unit_strings += 1
    if added_unit_strings:
        print(f"  + added {added_unit_strings} unit display string(s) to gl_str.txt")

    # Backfill missing UNIT_*_SUMMARY strings — the Build Manager summary box
    # renders the raw string ID (e.g. "UNIT_WARRIOR_SUMMARY") when absent.
    added_unit_summaries = 0
    for _uid, _display in sorted(mom_unit_display_names.items()):
        _sid = f"{_uid}_SUMMARY"
        if _sid not in _unit_gl_str.entries:
            _unit_gl_str.entries[_sid] = f"Summary of {_display}."
            added_unit_summaries += 1
    if added_unit_summaries:
        print(f"  + added {added_unit_summaries} unit summary string(s) to gl_str.txt")

    # Auto-hide all base CTP2 units that are not MoM CSV units.
    # Engine-required slots (UNIT_CITY etc.) are exempt.
    # This is generator-owned so regeneration never reintroduces GL entries.
    uni = reg.load("default/gamedata/Units.txt")


    hidden_count = 0
    for ident in sorted(uni._unit_ids):
        if ident in mom_unit_idents or ident in _ENGINE_REQUIRED_UNITS:
            continue
        if uni.ensure_flags(ident, ["NoIndex", "GLHidden"]):
            hidden_count += 1
    if hidden_count:
        print(f"  + hid {hidden_count} base CTP2 unit(s) from Great Library index")

    # Closed-gate GL hygiene: an advance is CLOSED when it can never be
    # researched — it self-prereqs (unreachable-gate idiom kept closed by the
    # sever pass) or ANY of its prerequisites is closed (Prerequisites are AND).
    # Content gated on closed advances is permanently dormant; without this
    # pass it still clutters the Great Library index (LotR "Angmar H1..H4"
    # hero slots, per-faction tech variants) as browsable dead records.
    adv_closed_file = reg.load("default/gamedata/Advance.txt")
    _prereq_map = {a: adv_closed_file.get_prerequisites(a)
                   for a in adv_closed_file.blocks}
    _closed = {a for a, pr in _prereq_map.items()
               if a in pr and not a.startswith("ADVANCE_HOME_")}
    _grew = True
    while _grew:
        _grew = False
        for a, pr in _prereq_map.items():
            if a.startswith("ADVANCE_HOME_"):
                continue  # SLIC-granted at game start — an open root, not a wall
            if a not in _closed and pr and any(p in _closed for p in pr):
                _closed.add(a)
                _grew = True
    closed_adv_hidden = 0
    for a in sorted(_closed):
        flagged = adv_closed_file.ensure_flags(a, ["GLHidden"])
        flagged = adv_closed_file.ensure_flags(a, ["GoodyHutExcluded"]) or flagged
        if flagged:
            closed_adv_hidden += 1
    closed_unit_hidden = 0
    for ident in sorted(uni._unit_ids):
        if ident in _ENGINE_REQUIRED_UNITS:
            continue
        _m = re.search(r'^\s*EnableAdvance\s+(ADVANCE_[A-Z0-9_]+)\s*$',
                       uni.block_text(ident), re.MULTILINE)
        if _m and _m.group(1) in _closed \
                and uni.ensure_flags(ident, ["NoIndex", "GLHidden"]):
            closed_unit_hidden += 1
    if closed_adv_hidden or closed_unit_hidden:
        print(f"  + closed-gate GL hygiene: hid {closed_adv_hidden} advance(s), "
              f"{closed_unit_hidden} unit(s) gated on unresearchable advances")

    # Remove stock CTP2 / test units listed in unit_mask.csv using the
    # proper nested-brace-aware parser.  Never use regex for block removal.
    # The mask is applied to ALL three unit files the engine can load:
    # Units.txt (active), Units_historic.txt and Units_release.txt (backup
    # copies the engine may load in some scenario paths).  Not applying the
    # mask to the backup files causes "X not found in Unit database" errors
    # at game startup even when Units.txt is correct.
    unit_mask_path = MOMJR / "unit_mask.csv"
    if unit_mask_path.exists():
        masked_ids = []
        with open(str(unit_mask_path), newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                uid = row['unit_id'].strip()
                if not uid:
                    continue
                if uid in _HARDCODED_DB_UNITS:
                    print(f"  ! SKIP: {uid} is engine-hardcoded (must stay in DB hidden); remove from unit_mask.csv")
                    continue
                masked_ids.append(uid)

        _UNIT_FILES_TO_MASK = [
            "default/gamedata/Units.txt",
            "default/gamedata/Units_historic.txt",
            "default/gamedata/Units_release.txt",
        ]
        for rel_path in _UNIT_FILES_TO_MASK:
            uf = reg.load(rel_path)
            removed_masked = [uid for uid in masked_ids if uf.remove_unit(uid)]
            if removed_masked:
                print(f"  + removed {len(removed_masked)} masked unit(s) from {rel_path.split('/')[-1]}: {', '.join(removed_masked)}")

    unit_build_list_counts = _write_mom_unit_build_lists(uni)
    populated_unit_build_lists = sum(1 for count in unit_build_list_counts.values() if count)
    total_unit_build_refs = sum(unit_build_list_counts.values())
    print(
        "  + wrote scenario-level UnitBuildLists.txt override"
        f" ({populated_unit_build_lists}/{len(unit_build_list_counts)} populated list(s),"
        f" {total_unit_build_refs} visible MoM unit ref(s))"
    )
    advance_list_counts = _write_mom_advance_lists()
    populated_advance_lists = sum(1 for ident, count in advance_list_counts.items() if count and ident != "ADVANCE_LIST_STOP_RESEARCH")
    total_advance_refs = sum(advance_list_counts.values())
    print(
        "  + wrote scenario-level AdvanceLists.txt override"
        f" ({populated_advance_lists}/{len(advance_list_counts)} populated list(s),"
        f" {total_advance_refs} visible MoM advance ref(s))"
    )

    # --- Tile improvements from tileimp.csv ---
    # First row of each tileimp has name + base fields; continuation rows (empty
    # name) add terrain variants with fields shifted left into class/tooltip/etc.
    tileimp_db = reg.load("default/gamedata/tileimp.txt")
    tileimp_groups = {}
    current_name = None
    if _csv_exists("tileimp.csv"):
        _tileimp_handle = open(str(MOMJR / "tileimp.csv"), newline='', encoding='utf-8')
    else:
        # A mod without a tileimp sheet keeps the base tile improvements as-is.
        import io as _io
        print("  + tileimp.csv absent — no tile-improvement overrides for this mod")
        _tileimp_handle = _io.StringIO("name\n")
    with _tileimp_handle as f:
        for row in csv.DictReader(f):
            name = row['name'].strip()
            if name:
                if name.startswith('x') or name == 'Nothing':
                    current_name = None
                    continue
                current_name = name
                ident = f"TILEIMP_{sanitize(name)}"
                if ident in HIDDEN_OUT_OF_GENRE_TILEIMPS:
                    current_name = None
                    continue
                tileimp_groups[ident] = {
                    "name": name, "ident": ident,
                    "level": row['level'].strip(),
                    "tile_class": row['class'].strip(),
                    "icon": row['icon'].strip(),
                    "tooltip": row['tooltip'].strip(),
                    "statusbar": row['statusbar'].strip(),
                    "sound": row['sound'].strip(),
                    "construction_tiles": row['construction_tiles'].strip(),
                    "cant_build_on": row['cant_build_on'].strip(),
                    "excludes": row['excludes'].strip(),
                    "terrain_effects": [],
                }
                terrain = (row.get('terrain') or '').strip()
                if not terrain:
                    continue
            else:
                if current_name is None:
                    continue
                ident = f"TILEIMP_{sanitize(current_name)}"
                if ident not in tileimp_groups:
                    continue
                terrain = row['class'].strip()
                if not terrain:
                    continue

            te = {"terrain": terrain}
            if name:
                te["bonus_food"] = (row.get('terrain_bonus_food') or '').strip()
                te["bonus_production"] = (row.get('terrain_bonus_production') or '').strip()
                te["bonus_gold"] = (row.get('terrain_bonus_gold') or '').strip()
                te["enable_advance"] = (row.get('terrain_enable_advance') or '').strip()
                te["production_cost"] = (row.get('terrain_production_cost') or '').strip()
                te["production_time"] = (row.get('terrain_production_time') or '').strip()
                te["tileset_index"] = (row.get('terrain_tileset_index') or '').strip()
            else:
                te["bonus_food"] = ''
                te["bonus_production"] = (row['tooltip'] or '').strip()
                te["enable_advance"] = (row['statusbar'] or '').strip()
                te["production_cost"] = (row['sound'] or '').strip()
                te["production_time"] = (row['construction_tiles'] or '').strip()
                te["tileset_index"] = (row['cant_build_on'] or '').strip()
            tileimp_groups[ident]["terrain_effects"].append(te)

    tileimp_db = reg.load("default/gamedata/tileimp.txt")
    for ident, g in tileimp_groups.items():
        tileimp = P.ModTileImp(
            ident=g["ident"], name=g["name"], level=g["level"],
            tile_class=g["tile_class"], icon=g["icon"], tooltip=g["tooltip"],
            statusbar=g["statusbar"], sound=g["sound"],
            construction_tiles=g["construction_tiles"],
            cant_build_on=g["cant_build_on"], excludes=g["excludes"],
            terrain_effects=g["terrain_effects"],
        )
        is_new = ident not in tileimp_db.blocks
        tileimp.register(reg)
        if is_new:
            n_terrains = len(g["terrain_effects"])
            print(f"  + tileimp: {g['name']} ({ident}) [{n_terrains} terrain variant(s)]")

    # Reconcile: any Advance.txt block whose Icon ref is missing from uniticon.txt
    # gets a stub entry so the engine doesn't raise "not found in Icon database".
    # If an extracted MoMJR TGA (ICON_ADVANCE_*.tga) exists on disk, use it;
    # otherwise fall back to UPLG001.TGA.
    _pics_dir = SCENARIO / "default" / "graphics" / "pictures"
    adv_file = reg.load("default/gamedata/Advance.txt")
    uic_file  = reg.load("default/gamedata/uniticon.txt")
    _icon_re  = re.compile(r'^\s+Icon\s+(ICON_ADVANCE_\S+)', re.MULTILINE)
    patched = 0
    patched_with_mom = 0
    for icon_id in _icon_re.findall(adv_file._text):
        adv_id = icon_id[len("ICON_"):]
        extracted_tga = f"{icon_id}.tga"
        has_mom_art = (_pics_dir / extracted_tga).exists()
        tga_token = f'"{extracted_tga}"' if has_mom_art else '"UPLG001.TGA"'
        desired = {
            "FirstFrame": tga_token,
            "Movie": '"NULL"',
            "Gameplay": f'"{adv_id}_GAMEPLAY"',
            "Historical": f'"{adv_id}_HISTORICAL"',
            "Prereq": f'"{adv_id}_PREREQ"',
            "Vari": f'"{adv_id}_STATISTICS"',
            "Icon": tga_token,
            "LargeIcon": '"NULL"',
            "SmallIcon": '"NULL"',
            "StatText": f'"{adv_id}_PREREQ"',
        }
        if uic_file.blocks.get(icon_id) != desired:
            if icon_id not in uic_file.blocks:
                patched += 1
            uic_file.blocks[icon_id] = desired
            if has_mom_art:
                patched_with_mom += 1
    normalized_stub_icons = 0
    for icon_id, block in uic_file.blocks.items():
        if not icon_id.startswith("ICON_ADVANCE_"):
            continue
        bad_icon_tokens = set(MOD_POLICY["icon_bad_tokens"])
        if block.get("FirstFrame") in bad_icon_tokens or block.get("Icon") in bad_icon_tokens:
            block["FirstFrame"] = MOD_POLICY["icon_placeholder"]
            block["Icon"] = MOD_POLICY["icon_placeholder"]
            normalized_stub_icons += 1
    if patched:
        print(f"  + patched {patched} missing advance icon entries in uniticon.txt ({patched_with_mom} with MoMJR art)")
    if normalized_stub_icons:
        print(f"  + normalized {normalized_stub_icons} advance icon block(s) off the bad fallback TGA")

    # Reconcile: any Improve.txt / buildings.txt block whose uniticon entry still
    # uses a stock CTP2 TGA → swap in the extracted MoMJR TGA if it exists on disk.
    # Blocks already updated by building_uniticon.csv (proxy TGAs) are left alone.
    import os
    bld_path = SCENARIO / "default/gamedata/buildings.txt"
    print(f"DEBUG BEFORE READ: buildings.txt exists={bld_path.exists()}, size={os.path.getsize(bld_path) if bld_path.exists() else 'N/A'}")
    _imp_text = _read_rel("default/gamedata/Improve.txt")
    _bld_text = _read_rel("default/gamedata/buildings.txt")
    _imp_icon_re = re.compile(r'(?:DefaultIcon|Icon)\s+(ICON_IMPROVE_\S+)', re.MULTILINE)
    _stock_tga_pat = re.compile(r'^"(?:CM2_|UPLG001\.TGA")', re.IGNORECASE)
    _all_improve_icons = (
        set(_imp_icon_re.findall(_imp_text))
        | set(_imp_icon_re.findall(_bld_text))
    )
    patched_improve = 0
    for icon_id in _all_improve_icons:
        block = uic_file.blocks.get(icon_id)
        if block is None:
            continue
        first_frame = (block.get("FirstFrame") or "").strip()
        if not _stock_tga_pat.match(first_frame):
            continue  # already set to MoM art (e.g., via building_uniticon.csv)
        extracted_tga = f"{icon_id}.tga"
        if not (_pics_dir / extracted_tga).exists():
            continue  # no MoM art on disk — leave the stock CTP2 fallback
        block["FirstFrame"] = f'"{extracted_tga}"'
        block["Icon"] = f'"{extracted_tga}"'
        patched_improve += 1
    if patched_improve:
        print(f"  + patched {patched_improve} improvement icon block(s) to use MoMJR art")

    # Reconcile: any UNIT block whose uniticon entry can be upgraded to the extracted MoMJR TGA.
    # If the extracted MoM art exists on disk, use it instead of whatever stock CTP2 fallback is present.
    uic_file_units = reg.load("default/gamedata/uniticon.txt")
    patched_units = 0
    for _uid in mom_unit_idents:
        _icon_id = f"ICON_{_uid}"
        _block = uic_file_units.blocks.get(_icon_id)
        if _block is None:
            continue
        _extracted_tga = f"{_icon_id}.tga"
        if (_pics_dir / _extracted_tga).exists():
            # MoM art exists on disk - use this single extracted TGA for all UI icon sizes
            _block["FirstFrame"] = f'"{_extracted_tga}"'
            _block["Icon"] = f'"{_extracted_tga}"'
            _block["LargeIcon"] = f'"{_extracted_tga}"'
            _block["SmallIcon"] = f'"{_extracted_tga}"'
            patched_units += 1
    if patched_units:
        print(f"  + patched {patched_units} stock unit icon entries in uniticon.txt with MoMJR art")

    # CRITICAL: Remove base CTP2 unit icon entries from uniticon.txt to prevent seed leakage.
    # If a unit is not in mom_unit_idents and not engine-required, its icon should not exist in the scenario.
    uic_file = reg.load("default/gamedata/uniticon.txt")
    removed_base_icons = 0
    for icon_id in list(uic_file.blocks.keys()):
        if icon_id.startswith("ICON_UNIT_"):
            unit_ident = icon_id.replace("ICON_", "", 1)
            if unit_ident not in mom_unit_idents and unit_ident not in _ENGINE_REQUIRED_UNITS:
                del uic_file.blocks[icon_id]
                removed_base_icons += 1
    
    if removed_base_icons:
        print(f"  + removed {removed_base_icons} base CTP2 unit icon entries from uniticon.txt to prevent seed leakage")

    gl_library = reg.load("english/gamedata/Great_Library.txt")
    base_gl_library = _load_base_library_file("english/gamedata/Great_Library.txt")
    restored_uniticon_gl_sections = _restore_missing_uniticon_gl_sections(
        uic_file.blocks,
        gl_library,
        base_gl_library,
    )
    waw_library = _load_library_file("english/gamedata/WAW_Great_Library.txt")
    base_waw_library = _load_base_library_file("english/gamedata/WAW_Great_Library.txt")
    restored_uniticon_waw_sections = _restore_missing_uniticon_gl_sections(
        uic_file.blocks,
        waw_library,
        base_waw_library,
    )
    if restored_uniticon_waw_sections:
        _save_library_file("english/gamedata/WAW_Great_Library.txt", waw_library)
    if restored_uniticon_gl_sections or restored_uniticon_waw_sections:
        print(
            "  + restored missing uniticon-linked GL sections "
            f"({restored_uniticon_gl_sections} base section(s),"
            f" {restored_uniticon_waw_sections} WAW section(s))"
        )

    goods_file = _load_raw_block_file("default/gamedata/goods.txt")
    goods_numeric_ids = _parse_goods_numeric_ids()
    seen_good_numbers = set()
    hidden_goods = 0
    for ident in goods_file.blocks:
        good_number = goods_numeric_ids.get(ident)
        if good_number in (None, 0) or good_number in seen_good_numbers:
            if goods_file.ensure_flags(ident, ["GLHidden"]):
                hidden_goods += 1
            continue
        seen_good_numbers.add(good_number)
    if hidden_goods:
        _save_raw_block_file("default/gamedata/goods.txt", goods_file)
        print(f"  + hid {hidden_goods} duplicate/placeholder goods from Great Library index")

    restored_wonders = _load_raw_block_file("default/gamedata/Wonder.txt")
    # SAFETY: The CTP2 engine does not support NoIndex or GLHidden in Wonder.txt.
    # If the control plane accidentally injects them, we MUST strip them to prevent
    # "Unknown token" engine crashes on game launch.
    stripped_invalid_wonder_flags = _strip_raw_block_flags(restored_wonders, {"NoIndex", "GLHidden"})
    if stripped_invalid_wonder_flags:
        _save_raw_block_file("default/gamedata/Wonder.txt", restored_wonders)
        print(f"  + stripped {stripped_invalid_wonder_flags} invalid flag(s) from Wonder.txt (engine does not support them)")
        restored_wonders = _load_raw_block_file("default/gamedata/Wonder.txt")

    stripped_wonder_flags = _strip_raw_block_flags(restored_wonders, {"GLHidden"})
    if stripped_wonder_flags:
        _save_raw_block_file("default/gamedata/Wonder.txt", restored_wonders)
        print(f"  + restored {stripped_wonder_flags} wonder block(s) to Great Library index")
    (
        live_wonder_count,
        removed_uniticon_wonders,
        removed_wonder_strings,
        removed_wonder_sections,
        removed_wonder_links,
        removed_wonder_stat_lines,
        keep_wonder_icon_count,
    ) = _prune_wonder_surfaces()
    if any((
        removed_uniticon_wonders,
        removed_wonder_strings,
        removed_wonder_sections,
        removed_wonder_links,
        removed_wonder_stat_lines,
    )):
        print(
            f"  + reduced wonders to {live_wonder_count} live entry(ies)"
            f" ({keep_wonder_icon_count} icon ref(s) kept,"
            f" {removed_uniticon_wonders} uniticon block(s),"
            f" {removed_wonder_strings} string(s),"
            f" {removed_wonder_sections} GL section(s),"
            f" {removed_wonder_links} stale GL link(s),"
            f" {removed_wonder_stat_lines} stale advance-stat line(s) removed)"
        )
    live_wonder_ids = set(_load_raw_block_file("default/gamedata/Wonder.txt").blocks)
    _write_empty_wonder_build_lists()
    print("  + wrote scenario-level empty WonderBuildLists.txt override")
    _sanitize_omitted_building_refs()
    removed_goal_wonder_refs = _write_sanitized_goals_wonder_refs(live_wonder_ids)
    print(
        "  + wrote scenario-level Goals.txt override"
        f" ({removed_goal_wonder_refs} stale wonder goal ref(s) removed)"
    )

    # ========================================================================
    # STRICT GL PRUNING: Ensure Great Library ONLY contains entries for 
    # improvements, wonders, AND units that were explicitly generated from 
    # the control plane (plus engine-required units).
    # ========================================================================
    live_building_ids = set(_load_raw_block_file("default/gamedata/buildings.txt").blocks)
    live_building_ids.update(live_wonder_ids)
    
    # CRITICAL: Use in-memory Units.txt to get live unit IDs, not disk file
    # The MoM units are added to the registry object but not yet saved to disk.
    live_unit_ids = set(reg.load("default/gamedata/Units.txt")._unit_ids)
    
    gl_library_prune = reg.load("english/gamedata/Great_Library.txt")
    waw_library_prune = _load_library_file("english/gamedata/WAW_Great_Library.txt")
    
    pruned_sections = 0
    pruned_links = 0
    
    for library in (gl_library_prune, waw_library_prune):
        # 1. Remove entire sections for non-control-plane buildings/wonders/units
        sections_to_remove = [
            sec_id for sec_id in library.sections 
            if (sec_id.startswith("IMPROVE_") or sec_id.startswith("WONDER_") or sec_id.startswith("UNIT_"))
            and _section_base_id(sec_id) not in live_building_ids
            and _section_base_id(sec_id) not in live_unit_ids
        ]
        for sec_id in sections_to_remove:
            del library.sections[sec_id]
            pruned_sections += 1
            
        # 2. Strip inline database links to non-control-plane entities
        def _strip_invalid_link(match):
            nonlocal pruned_links
            entity_id = match.group(1)
            if entity_id not in live_building_ids and entity_id not in live_unit_ids:
                pruned_links += 1
                return match.group(2) # Just return the display text
            return match.group(0)
            
        for sec_id, content in list(library.sections.items()):
            library.sections[sec_id] = re.sub(
                r'<L:DATABASE_(?:BUILDINGS|WONDERS|UNITS),((?:IMPROVE_|WONDER_|UNIT_)[A-Z0-9_]+)>([^<]*)<e>',
                _strip_invalid_link,
                content
            )
            
    _save_library_file("english/gamedata/WAW_Great_Library.txt", waw_library_prune)
    print(f"  + strictly pruned {pruned_sections} GL sections and {pruned_links} invalid entity GL links")

    restored_orders = _load_raw_block_file("default/gamedata/Orders.txt")
    stripped_order_flags = _strip_raw_block_flags(restored_orders, {"GLHidden"})
    if stripped_order_flags:
        _save_raw_block_file("default/gamedata/Orders.txt", restored_orders)
        print(f"  + restored {stripped_order_flags} unit order block(s) to Great Library index")

    restored_tileimps = _load_raw_block_file("default/gamedata/tileimp.txt")
    stripped_tileimp_flags = _strip_raw_block_flags(restored_tileimps, {"GLHidden"})
    if stripped_tileimp_flags:
        _save_raw_block_file("default/gamedata/tileimp.txt", restored_tileimps)
        print(f"  + restored {stripped_tileimp_flags} tile improvement block(s) to Great Library index")

    transport_tileimps = _load_raw_block_file("default/gamedata/tileimp.txt")
    base_tileimps = P.RawBlockTextFile()
    base_tileimps.parse(
        (CTP2_DATA / "default" / "gamedata" / "tileimp.txt").read_text(
            encoding='latin-1'
        )
    )
    transport_changed = False
    for _swap in MOD_POLICY["tileimp_block_swaps"]:
        transport_changed |= _replace_block_text(
            transport_tileimps,
            _swap["id"],
            [(_swap["find"], _swap["replace"])],
        )
    # OUT_OF_GENRE: copy block from base if missing, then mark GLHidden.
    # Deleting the block is wrong — base ctp2_data has it without GLHidden, so the
    # game would fall back and show it in the Great Library anyway.
    hidden_out_of_genre_added = 0
    for ident in sorted(HIDDEN_OUT_OF_GENRE_TILEIMPS):
        if ident not in transport_tileimps.blocks and ident in base_tileimps.blocks:
            transport_tileimps.add_block(ident, base_tileimps.blocks[ident])
            hidden_out_of_genre_added += 1
            transport_changed = True
        transport_changed |= transport_tileimps.ensure_flags(ident, ["GLHidden"])
    hidden_tileimps = HIDDEN_SURROGATE_TILEIMPS | HIDDEN_OUT_OF_GENRE_TILEIMPS
    for ident in sorted(HIDDEN_SURROGATE_TILEIMPS):
        transport_changed |= transport_tileimps.ensure_flags(ident, ["GLHidden"])
    if transport_changed:
        _save_raw_block_file("default/gamedata/tileimp.txt", transport_tileimps)
        print(
            "  + remapped the transport lane, added "
            f"{hidden_out_of_genre_added} out-of-genre tile improvement block(s) with GLHidden, "
            "and hid surrogate-only tile improvements from the Great Library"
        )

    live_advance_ids = set(reg.load("default/gamedata/Advance.txt").blocks)
    govern_file = _load_raw_block_file("default/gamedata/govern.txt")
    base_govern_file = _load_base_raw_block_file("default/gamedata/govern.txt")
    govern_source_blocks = dict(base_govern_file.blocks)
    govern_source_blocks.update(govern_file.blocks)
    live_governments = _government_ids_enabled_by_live_advances(
        govern_source_blocks,
        live_advance_ids,
    )
    live_governments.update(
        _extract_referenced_ids(
            ["default/gamedata/Units.txt", "default/gamedata/Improve.txt"],
            r'GOVERNMENT_[A-Z0-9_]+',
        )
    )
    restored_governments = 0
    for ident, block_text in govern_source_blocks.items():
        if ident not in live_governments or ident in govern_file.blocks:
            continue
        govern_file.add_block(ident, block_text)
        restored_governments += 1
    removed_governments = 0
    for ident in list(govern_file.blocks):
        if ident not in live_governments and govern_file.remove_block(ident):
            removed_governments += 1
    if restored_governments or removed_governments:
        _save_raw_block_file("default/gamedata/govern.txt", govern_file)
    govern_icons = _load_counted_icon_file("default/gamedata/governicon.txt")
    base_govern_icons = _load_base_counted_icon_file("default/gamedata/governicon.txt")
    keep_govern_icons = set()
    for ident in live_governments:
        block_text = govern_file.blocks.get(ident, "")
        match = re.search(r'^\s*Icon\s+(\S+)', block_text, re.MULTILINE)
        if match:
            keep_govern_icons.add(match.group(1))
    keep_govern_icons.add("ICON_GOV_DEFAULT")
    existing_govern_icon_ids = {
        entry.split('\t', 1)[0].strip()
        for entry in govern_icons.entries
        if entry.strip()
    }
    restored_icons = 0
    for entry in base_govern_icons.entries:
        icon_id = entry.split('\t', 1)[0].strip()
        if icon_id not in keep_govern_icons or icon_id in existing_govern_icon_ids:
            continue
        govern_icons.entries.append(entry)
        existing_govern_icon_ids.add(icon_id)
        restored_icons += 1
    synthesized_icons = 0
    base_govern_icon_entries = {
        entry.split('\t', 1)[0].strip(): entry
        for entry in base_govern_icons.entries
        if entry.strip()
    }
    for icon_id in sorted(keep_govern_icons - existing_govern_icon_ids):
        donor_id = GOVERNICON_FALLBACK_IDS.get(icon_id)
        donor_entry = base_govern_icon_entries.get(donor_id or "")
        if not donor_entry:
            continue
        govern_icons.entries.append(re.sub(r'^\s*\S+', icon_id, donor_entry, count=1))
        existing_govern_icon_ids.add(icon_id)
        synthesized_icons += 1
    removed_icons = _filter_counted_icon_entries(govern_icons, keep_govern_icons)
    if restored_icons or synthesized_icons or removed_icons:
        _save_counted_icon_file("default/gamedata/governicon.txt", govern_icons)
    uniticon = reg.load("default/gamedata/uniticon.txt")
    base_uniticon = _load_base_block_file("default/gamedata/uniticon.txt")
    restored_uniticon_govs = 0
    for ident in sorted(live_governments):
        icon_id = f"ICON_GOV_{ident[len('GOVERNMENT_'):]}"
        if icon_id in uniticon.blocks or icon_id not in base_uniticon.blocks:
            continue
        uniticon.blocks[icon_id] = base_uniticon.blocks[icon_id]
        restored_uniticon_govs += 1
    removed_uniticon_govs = 0
    for icon_id in list(uniticon.blocks):
        if not icon_id.startswith("ICON_GOV_") or icon_id == "ICON_GOV_DEFAULT":
            continue
        govern_id = f"GOVERNMENT_{icon_id[len('ICON_GOV_'):]}"
        if govern_id not in live_governments:
            del uniticon.blocks[icon_id]
            removed_uniticon_govs += 1
    removed_dip2_government_advice = _prune_government_advice_lines(
        "english/gamedata/dip2_str.txt",
        live_governments,
    )
    removed_strategy_governments = _prune_strategy_government_lines(
        "default/aidata/strategies.txt",
        live_governments,
    )
    gl_strings = reg.load("english/gamedata/gl_str.txt")
    removed_gl_strings = _prune_gl_strings(gl_strings, live_governments, ("GOVERNMENT_",))
    # Ensure every live government has a display string — base gl_str.txt may be missing some
    added_gov_strings = 0
    for gov_id in sorted(live_governments):
        if gov_id not in gl_strings.entries:
            gl_strings.entries[gov_id] = humanize_ident(gov_id, "GOVERNMENT_")
            added_gov_strings += 1
    gl_library = reg.load("english/gamedata/Great_Library.txt")
    removed_gl_sections = _prune_gl_sections(gl_library, live_governments, ("GOVERNMENT_",))
    removed_gl_links = _strip_stale_database_links(
        gl_library,
        live_governments,
        "DATABASE_GOVERNMENTS",
        ("GOVERNMENT_",),
    )
    waw_library = _load_library_file("english/gamedata/WAW_Great_Library.txt")
    removed_waw_sections = _prune_gl_sections(waw_library, live_governments, ("GOVERNMENT_",))
    removed_waw_links = _strip_stale_database_links(
        waw_library,
        live_governments,
        "DATABASE_GOVERNMENTS",
        ("GOVERNMENT_",),
    )
    if removed_waw_sections or removed_waw_links:
        _save_library_file("english/gamedata/WAW_Great_Library.txt", waw_library)
    if any((
        restored_governments,
        restored_icons,
        synthesized_icons,
        removed_governments,
        restored_uniticon_govs,
        removed_icons,
        removed_uniticon_govs,
        removed_dip2_government_advice,
        removed_strategy_governments,
        removed_gl_strings,
        added_gov_strings,
        removed_gl_sections,
        removed_waw_sections,
        removed_gl_links,
        removed_waw_links,
    )):
        print(
            f"  + reduced governments to {len(live_governments)} live entry(ies)"
            f" ({restored_governments} block(s) restored, {removed_governments} block(s) removed,"
            f" {restored_icons} icon(s) restored, {synthesized_icons} fallback icon(s) synthesized, {removed_icons} icon(s) removed,"
            f" {restored_uniticon_govs} uniticon block(s) restored, {removed_uniticon_govs} uniticon block(s) removed,"
            f" {removed_dip2_government_advice} dip2_str line(s),"
            f" {removed_strategy_governments} aidata strategies line(s),"
            f" {removed_gl_strings} string(s) removed, {added_gov_strings} string(s) added,"
            f" {removed_gl_sections + removed_waw_sections} GL section(s) removed,"
            f" {removed_gl_links + removed_waw_links} stale GL link(s) stripped)"
        )

    gl_library = reg.load("english/gamedata/Great_Library.txt")
    waw_library = _load_library_file("english/gamedata/WAW_Great_Library.txt")
    live_concepts = set(re.findall(r'<L:DATABASE_CONCEPTS,(CONCEPT_[A-Z0-9_]+)>', gl_library.render()))
    live_concepts.update(re.findall(r'<L:DATABASE_CONCEPTS,(CONCEPT_[A-Z0-9_]+)>', waw_library.render()))
    live_concepts -= HIDDEN_OUT_OF_GENRE_CONCEPTS
    stripped_hidden_concept_links = _strip_stale_database_links(
        gl_library,
        live_concepts,
        "DATABASE_CONCEPTS",
        ("CONCEPT_",),
    )
    stripped_hidden_waw_concept_links = _strip_stale_database_links(
        waw_library,
        live_concepts,
        "DATABASE_CONCEPTS",
        ("CONCEPT_",),
    )
    concept_text = _read_rel("default/gamedata/concept.txt").splitlines()
    concept_blocks = P.CTP2BlockFile()
    concept_blocks.parse('\n'.join(concept_text[1:]))
    removed_concepts = 0
    for ident in list(concept_blocks.blocks):
        if ident not in live_concepts:
            del concept_blocks.blocks[ident]
            removed_concepts += 1
    if removed_concepts:
        _write_rel(
            "default/gamedata/concept.txt",
            str(len(concept_blocks.blocks)) + "\n" + concept_blocks.render(),
        )
        concept_strings = reg.load("english/gamedata/gl_str.txt")
        removed_concept_strings = _prune_gl_strings(concept_strings, live_concepts, ("CONCEPT_",))
        removed_concept_sections = _prune_gl_sections(gl_library, live_concepts, ("CONCEPT_",))
        removed_waw_concept_sections = _prune_gl_sections(waw_library, live_concepts, ("CONCEPT_",))
        if removed_waw_concept_sections or stripped_hidden_waw_concept_links:
            _save_library_file("english/gamedata/WAW_Great_Library.txt", waw_library)
        print(
            f"  + reduced concepts to {len(live_concepts)} referenced entry(ies)"
            f" ({removed_concepts} block(s), {removed_concept_strings} string(s),"
            f" {removed_concept_sections + removed_waw_concept_sections} GL section(s) removed,"
            f" {stripped_hidden_concept_links + stripped_hidden_waw_concept_links} stale GL link(s) stripped)"
        )

    # Per-mod thematic DB text swaps (e.g. MoM's Railroad -> Greater Enchantments)
    for _swap in MOD_POLICY["db_text_swaps"]:
        _db_file = reg.load(_swap["file"])
        _db_file._text = _db_file._text.replace(
            _swap["find"], _swap["replace"], int(_swap.get("count", 1)))
    advances = reg.load("default/gamedata/Advance.txt")
    wonders = reg.load("default/gamedata/Wonder.txt")

    gl_strings = reg.load("english/gamedata/gl_str.txt")
    for _sid, _val in MOD_POLICY["gl_string_overrides"].items():
        gl_strings.entries[_sid] = _val

    gl_library = reg.load("english/gamedata/Great_Library.txt")
    added_runtime_building_strings, added_runtime_building_sections = _ensure_runtime_building_gl_surfaces(
        gl_strings,
        gl_library,
    )
    added_runtime_unit_strings, added_runtime_unit_sections = _ensure_runtime_unit_gl_surfaces(
        gl_strings,
        gl_library,
    )

    # Self-heal illegal Great Library DB-name links. `DATABASE_IMPROVEMENTS` is NOT
    # one of the engine's 12 legal database names (greatlibrary.cpp s_database_names[]);
    # any <L:DATABASE_IMPROVEMENTS,...> link makes Get_Database_From_Name hit
    # Assert(false) at greatlibrary.cpp:352 -> 0xC0000005 the instant that entry
    # renders. City improvements are IMPROVE_ records that live in DATABASE_BUILDINGS.
    # The building STATISTICS emitter above now writes DATABASE_BUILDINGS, but base GL
    # prose restored from prior runs / scenario disk can still carry the old bad name,
    # so normalize every section here (idempotent) before save. Guarded by
    # validate_all_surfaces surface 2a.
    normalized_gl_dbname = 0
    for _lib in (gl_library, waw_library):
        for _sid, _content in list(_lib.sections.items()):
            if "DATABASE_IMPROVEMENTS" in _content:
                fixed = _content.replace("<L:DATABASE_IMPROVEMENTS,", "<L:DATABASE_BUILDINGS,")
                if fixed != _content:
                    _lib.sections[_sid] = fixed
                    normalized_gl_dbname += 1
    if normalized_gl_dbname:
        print(f"  + normalized {normalized_gl_dbname} illegal DATABASE_IMPROVEMENTS GL link section(s) to DATABASE_BUILDINGS")

    # Ensure masked building icons have GL strings to avoid audit failures
    # (e.g., ICON_IMPROVE_XWOMENS_SUFFRAGE which is masked but may still have uniticon refs)
    masked_building_icons = list(MOD_POLICY["masked_building_icons"])
    for icon_id in masked_building_icons:
        if icon_id in uic_file.blocks:
            for field in ("Gameplay", "Historical", "Prereq", "Vari", "StatText"):
                ref = uic_file.blocks[icon_id].get(field, "")
                if ref and ref not in gl_strings.entries:
                    # Remove quotes from ref for the key, keep them for the value
                    key = ref.strip('"')
                    gl_strings.entries[key] = f"Masked building {icon_id} {field}."
                    added_runtime_building_strings += 1
    # Per-mod GL section surgery (set/replace/pop) from gl_section_overrides.csv
    _apply_gl_section_overrides(gl_library, "gl")

    waw_library = _load_library_file("english/gamedata/WAW_Great_Library.txt")
    _apply_gl_section_overrides(waw_library, "waw")
    hidden_tileimps = HIDDEN_SURROGATE_TILEIMPS | HIDDEN_OUT_OF_GENRE_TILEIMPS
    visible_tileimps = set(tileimp_groups) - hidden_tileimps
    removed_hidden_tileimp_sections = _prune_gl_sections(
        gl_library,
        visible_tileimps,
        ("TILEIMP_",),
    )
    removed_hidden_waw_tileimp_sections = _prune_gl_sections(
        waw_library,
        visible_tileimps,
        ("TILEIMP_",),
    )
    stripped_hidden_tileimp_links = _strip_stale_database_links(
        gl_library,
        visible_tileimps,
        "DATABASE_TILE_IMPROVEMENTS",
        ("TILEIMP_",),
    )
    stripped_hidden_waw_tileimp_links = _strip_stale_database_links(
        waw_library,
        visible_tileimps,
        "DATABASE_TILE_IMPROVEMENTS",
        ("TILEIMP_",),
    )
    _save_library_file("english/gamedata/WAW_Great_Library.txt", waw_library)
    if stripped_hidden_tileimp_links or stripped_hidden_waw_tileimp_links:
        print(
            f"  + stripped {stripped_hidden_tileimp_links + stripped_hidden_waw_tileimp_links}"
            " hidden surrogate tile improvement GL link(s)"
        )
    if removed_hidden_tileimp_sections or removed_hidden_waw_tileimp_sections:
        print(
            "  + removed "
            f"{removed_hidden_tileimp_sections + removed_hidden_waw_tileimp_sections}"
            " hidden surrogate tile-improvement GL section(s)"
        )
    if added_runtime_building_strings or added_runtime_building_sections:
        print(
            "  + filled runtime building GL fallback surfaces "
            f"({added_runtime_building_strings} string(s), {added_runtime_building_sections} section(s))"
        )

    _write_surrogate_register()

    visible_order_sections = ("PREREQ", "STATISTICS", "GAMEPLAY", "HISTORICAL")
    order_visibility = _load_raw_block_file("default/gamedata/Orders.txt")
    # Load base CTP2 order display strings as fallback source
    _base_gl_str_path = CTP2_DATA / "english/gamedata/gl_str.txt"
    _base_order_strings: dict[str, str] = {}
    if _base_gl_str_path.exists():
        _base_gl_raw = _base_gl_str_path.read_text(encoding="latin-1")
        for _m in re.finditer(r'^((?:ORDER_|UNIT_ORDER_)\w+)\s*"([^"]*)"', _base_gl_raw, re.MULTILINE):
            _base_order_strings[_m.group(1)] = _m.group(2)
    # Manual display strings for orders absent from base CTP2 gl_str.txt
    _manual_order_strings: dict[str, str] = dict(MOD_POLICY["order_strings"])
    _base_order_strings.update(_manual_order_strings)
    rehidden_orders = 0
    restored_documented_orders = 0
    forced_hidden_orders = 0
    added_order_strings = 0
    visible_orders = set()
    for ident in list(order_visibility.blocks):
        if not ident.startswith("ORDER_"):
            continue
        if ident in HIDDEN_OUT_OF_GENRE_ORDERS:
            if order_visibility.ensure_flags(ident, ["GLHidden"]):
                forced_hidden_orders += 1
            continue
        alias = ident.replace("ORDER_", "UNIT_ORDER_", 1)
        # Ensure a display string exists in the scenario gl_str — copy from base if missing
        if ident not in gl_strings.entries and alias not in gl_strings.entries:
            base_name = _base_order_strings.get(ident) or _base_order_strings.get(alias)
            if base_name:
                gl_strings.entries[ident] = base_name
                added_order_strings += 1
        # Orders never had full GL articles in CTP2; display string alone is sufficient
        has_display_name = ident in gl_strings.entries or alias in gl_strings.entries
        if has_display_name:
            visible_orders.add(ident)
            if _replace_block_text(order_visibility, ident, [("\n   GLHidden", "")]):
                restored_documented_orders += 1
        elif order_visibility.ensure_flags(ident, ["GLHidden"]):
            rehidden_orders += 1
    removed_hidden_order_sections = _prune_gl_sections(
        gl_library,
        visible_orders,
        ("ORDER_",),
    )
    removed_hidden_waw_order_sections = _prune_gl_sections(
        waw_library,
        visible_orders,
        ("ORDER_",),
    )
    stripped_hidden_order_links = _strip_stale_database_links(
        gl_library,
        visible_orders,
        "DATABASE_ORDERS",
        ("ORDER_",),
    )
    stripped_hidden_waw_order_links = _strip_stale_database_links(
        waw_library,
        visible_orders,
        "DATABASE_ORDERS",
        ("ORDER_",),
    )
    if rehidden_orders or restored_documented_orders or added_order_strings or forced_hidden_orders:
        _save_raw_block_file("default/gamedata/Orders.txt", order_visibility)
        print(
            "  + reconciled unit order visibility against owned GL surfaces "
            f"({restored_documented_orders} restored, {added_order_strings} display string(s) added,"
            f" {rehidden_orders} hidden, {forced_hidden_orders} genre-hidden)"
        )
    if removed_hidden_order_sections or removed_hidden_waw_order_sections:
        print(
            "  + removed "
            f"{removed_hidden_order_sections + removed_hidden_waw_order_sections}"
            " hidden/out-of-genre unit-order GL section(s)"
        )
    if stripped_hidden_order_links or stripped_hidden_waw_order_links:
        print(
            "  + stripped "
            f"{stripped_hidden_order_links + stripped_hidden_waw_order_links}"
            " hidden/out-of-genre unit-order GL link(s)"
        )
    _save_library_file("english/gamedata/WAW_Great_Library.txt", waw_library)

    tips_strings = _load_string_file("english/gamedata/tips_str.txt")
    for _sid, _val in MOD_POLICY["tips_string_overrides"].items():
        tips_strings.entries[_sid] = _val
    _save_string_file("english/gamedata/tips_str.txt", tips_strings)

    # Remove tileimp.txt from cache — we only loaded it for reading above,
    # not for modification. save_all() would corrupt it with the wrong format.
    if "default/gamedata/tileimp.txt" in reg._parsed:
        del reg._parsed["default/gamedata/tileimp.txt"]

    # Improvements load from buildings.txt (per gamefile.txt), NOT Improve.txt. Convert
    # the authored MoM improvements into buildings.txt (AE schema) and drop Improve.txt.
    # Done before save_all so the dead Improve.txt is never written.
    _merge_mom_improvements_into_buildings()

    # ORDERING (fixed 2026-07-26): the merge above writes RAW Civ2 costs (4..60)
    # straight from improvements.csv, and it runs ~1300 lines AFTER the
    # _retune_mom_improvement_costs() call earlier in main() -- so that earlier
    # rescale was always clobbered and every MoM building shipped as a 1-turn
    # build. Wonders and units were never affected: their retunes run after
    # their own ingestion. Re-run the improvement rescale HERE, once the blocks
    # actually exist, so raw Civ2 costs land in the base CTP2 age band that
    # matches the advance which gates each block.
    #
    # ORDERING: tileimp.txt is rebuilt above and evicted from the registry
    # cache, so the orphan re-anchor MUST run here, after that rebuild --
    # anywhere earlier and it is silently clobbered.
    _ra_files, _ra_blocks = _apply_advance_reanchor(reg)
    if _ra_blocks:
        print(f"  + advance re-anchor: {_ra_files} block(s) re-pointed, {_ra_blocks} deleted")

    retuned_improvement_costs = _retune_mom_improvement_costs(advance_ages)
    if retuned_improvement_costs:
        print(f"  + rescaled {retuned_improvement_costs} improvement cost(s) into base CTP2 age bands")

    # Faction gating. Placement is the whole risk here (see: generator pass
    # ordering ate the cost rescale) -- it must land AFTER the unit mask, both
    # cost retunes and the improvement->buildings merge above so it reads final
    # state, and BEFORE gl_descriptions.apply_descriptions() below, which
    # quotes the prereq in derived GAMEPLAY prose.
    sphere_gated, sphere_idents = _apply_sphere_gating(reg)
    if sphere_gated:
        print(f"  + sphere-gated {len(sphere_idents)} block(s) onto their ladder rung "
              f"({sphere_gated} EnableAdvance rewrite(s))")

    # Icon-DB backfill: the runtime Icon database is uniticon.txt (civapp.cpp
    # g_theIconDB->Parse(g_uniticondb_filename) — one DB for unit AND building
    # icons; improveicon.txt is a separate export, NOT consulted here). Every
    # DefaultIcon in buildings.txt must have an ICON_IMPROVE block in uniticon
    # or BuildingRecord::ResolveDBReferences raises "not found in Icon
    # database" and the game exits. Merged-source improvements have no curated
    # icon block — synthesize one pointing FirstFrame/Icon at the placeholder
    # TGA and the GL fields at the building's own runtime GL surfaces.
    _uic = reg.load("default/gamedata/uniticon.txt")
    _bld_final = _read_rel("default/gamedata/buildings.txt")
    _icon_refs = set(re.findall(r"DefaultIcon\s+(ICON_IMPROVE_[A-Z0-9_]+)", _bld_final))
    _placeholder_tga = MOD_POLICY["icon_placeholder"]
    synthesized_improve_icons = 0
    for icon_id in sorted(_icon_refs):
        if icon_id in _uic.blocks:
            continue
        # Retired X-sentinels are never rendered; MoM baseline ships them
        # without icon blocks — leave alone so the byte gate holds.
        if re.match(r"ICON_IMPROVE_X[A-Z]", icon_id):
            continue
        imp_id = "IMPROVE_" + icon_id[len("ICON_IMPROVE_"):]
        _uic.blocks[icon_id] = {
            "FirstFrame": _placeholder_tga,
            "Movie": '"NULL"',
            "Gameplay": f'"{imp_id}_GAMEPLAY"',
            "Historical": f'"{imp_id}_HISTORICAL"',
            "Prereq": f'"{imp_id}_PREREQ"',
            "Vari": f'"{imp_id}_STATISTICS"',
            "Icon": _placeholder_tga,
            "LargeIcon": '"NULL"',
            "SmallIcon": '"NULL"',
            "StatText": f'"{imp_id}_STATISTICS"',
        }
        synthesized_improve_icons += 1
    if synthesized_improve_icons:
        print(f"  + synthesized {synthesized_improve_icons} placeholder improvement icon block(s) in uniticon.txt")

    # Cap Prerequisites per advance at the engine's k_MAX_Prerequisites (4,
    # AdvanceRecord.h). Merged/remapped advances can accumulate more (e.g. the
    # Enchanted Road remap collapses several base RAILROAD prereqs to identical
    # GREATER_ENCHANTMENTS lines); a 5th entry triggers "Advance.txt:N too many
    # entries". Truncate to the first 4 (NOT dedupe — MoM ships legal 4-identical
    # blocks and the byte gate must hold); this only trims the genuine overflow.
    K_MAX_PREREQUISITES = 4
    _adv = reg.load("default/gamedata/Advance.txt")
    _capped_adv = 0

    def _cap_prereqs(m: "re.Match[str]") -> str:
        body = m.group(2)
        lines = body.split("\n")
        kept, seen_prereq = [], 0
        for ln in lines:
            if re.match(r"\s*Prerequisites\s+", ln):
                seen_prereq += 1
                if seen_prereq > K_MAX_PREREQUISITES:
                    continue
            kept.append(ln)
        new_body = "\n".join(kept)
        if new_body != body:
            nonlocal _capped_adv
            _capped_adv += 1
        return f"{m.group(1)}{{{new_body}}}"

    _adv._text = re.sub(r"(ADVANCE_\w+ )\{(.*?)\}", _cap_prereqs, _adv._text, flags=re.S)
    if _capped_adv:
        print(f"  + capped Prerequisites to {K_MAX_PREREQUISITES} on {_capped_adv} advance(s)")

    # Great Library descriptions. Runs LAST, deliberately: GAMEPLAY prose is
    # derived from the live DB blocks, so it has to see the final costs. The
    # improvement rescale above is the cautionary tale -- an earlier pass here
    # would quote production costs that a later pass then rewrote
    # (see: generator pass ordering ate the cost rescale).
    _gl_desc_report = gl_descriptions.apply_descriptions(
        _gl_desc_text, gl_library, gl_str, MOMJR,
    )

    reg.save_all()
    final_gl_scrubbed = 0
    final_gl_scrubbed += _scrub_hidden_tileimp_gl_file(
        "english/gamedata/Great_Library.txt",
        hidden_tileimps,
    )
    final_gl_scrubbed += _scrub_hidden_tileimp_gl_file(
        "english/gamedata/WAW_Great_Library.txt",
        hidden_tileimps,
    )
    final_gl_scrubbed += _scrub_hidden_tileimp_gl_prose(
        "english/gamedata/Great_Library.txt",
        hidden_tileimps,
    )
    final_gl_scrubbed += _scrub_hidden_tileimp_gl_prose(
        "english/gamedata/WAW_Great_Library.txt",
        hidden_tileimps,
    )
    if final_gl_scrubbed:
        print(f"  + final GL scrub removed {final_gl_scrubbed} hidden tile-improvement surface(s)")
    final_order_scrubbed = 0
    final_order_scrubbed += _scrub_hidden_order_gl_file(
        "english/gamedata/Great_Library.txt",
        HIDDEN_OUT_OF_GENRE_ORDERS,
    )
    final_order_scrubbed += _scrub_hidden_order_gl_file(
        "english/gamedata/WAW_Great_Library.txt",
        HIDDEN_OUT_OF_GENRE_ORDERS,
    )
    if final_order_scrubbed:
        print(f"  + final GL scrub removed {final_order_scrubbed} hidden/out-of-genre order surface(s)")
    final_concept_scrubbed = 0
    final_concept_scrubbed += _scrub_hidden_concept_gl_file(
        "english/gamedata/Great_Library.txt",
        HIDDEN_OUT_OF_GENRE_CONCEPTS,
    )
    final_concept_scrubbed += _scrub_hidden_concept_gl_file(
        "english/gamedata/WAW_Great_Library.txt",
        HIDDEN_OUT_OF_GENRE_CONCEPTS,
    )
    if final_concept_scrubbed:
        print(f"  + final GL scrub removed {final_concept_scrubbed} hidden/out-of-genre concept surface(s)")

    dead_adv_scrubbed = _scrub_dead_advance_surfaces()
    if dead_adv_scrubbed:
        print(f"  + final GL scrub removed {dead_adv_scrubbed} dead-advance surface(s)")

    dead_imp_scrubbed = _scrub_dead_tileimp_surfaces()
    if dead_imp_scrubbed:
        print(f"  + re-anchored {dead_imp_scrubbed} dead-tileimp surface(s)")

    # ORDERING: dead last. Every ident is filtered against the live Advance.txt /
    # Units.txt / buildings.txt / Wonder.txt, so this must run after the mask,
    # the re-layout, the prereq rewrite and the improvement merge have all
    # settled -- otherwise the wall cites blocks that no longer exist.
    gated_idents = _emit_mom_gating_slc()
    print(f"  + mom_gating.slc: {gated_idents} ident(s) walled across 5 tribes")

    if _ensure_diffdb_start_government():
        print(f"  + DiffDB.txt: guaranteed {START_GUARANTEED_ADVANCES} across all start-tech blocks")

    retired_x = _retire_x_sentinels()
    if retired_x:
        print(f"  + retired {retired_x} AE 'X' sentinel improvement/wonder(s) (obsolete from turn 1)")

    _generate_civilisation_tribes()
    _generate_civstr_tribes()
    # The workbook mirrors the ACTIVE csv dir: legacy MoM path when running the
    # default control plane, <csv_dir>/mod_inventory.xlsx for any other mod.
    _default_csv_dir = Path(__file__).parent / "momjr_csv"
    if MOMJR.resolve() == _default_csv_dir.resolve():
        workbook_path, workbook_sheet_count = export_workbook(MOD_WORKBOOK_PATH)
    else:
        workbook_path, workbook_sheet_count = export_workbook(
            MOMJR / "mod_inventory.xlsx", csv_root=MOMJR)
    print(f"  + refreshed workbook {workbook_path} ({workbook_sheet_count} sheet(s))")
    
    # CRITICAL: Ensure scenario newsprite.txt contains all base sprites PLUS any custom sprites used in Units.txt
    base_newsprite = str(CTP2_DATA / "default" / "gamedata" / "newsprite.txt")
    scenario_newsprite = str(SCENARIO / "default" / "gamedata" / "newsprite.txt")
    scenario_units = str(SCENARIO / "default" / "gamedata" / "Units.txt")
    try:
        with open(base_newsprite, 'r', encoding='utf-8') as f:
            newsprite_lines = f.readlines()
        
        # Build a set of existing sprite names and find the max ID to avoid collisions
        existing_sprites = set()
        max_id = 0
        for line in newsprite_lines:
            parts = line.strip().split()
            if len(parts) == 2:
                existing_sprites.add(parts[0])
                try:
                    max_id = max(max_id, int(parts[1]))
                except ValueError:
                    pass

        # SPRITE NUMBERS ARE PINNED: each custom number is baked into the GU<id>.SPR
        # filename built by build_sprites.py. Renumbering breaks every custom unit's
        # art (peasant regression, 2026-07-14). Preserve the scenario file's existing
        # custom assignments verbatim; only genuinely new names get fresh ids.
        pinned_customs: list[tuple[str, int]] = []
        try:
            with open(scenario_newsprite, 'r', encoding='utf-8') as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) == 2 and parts[0] not in existing_sprites:
                        try:
                            pinned_customs.append((parts[0], int(parts[1])))
                        except ValueError:
                            continue
        except FileNotFoundError:
            pass
        pinned_names = {name for name, _ in pinned_customs}
        max_id = max([max_id] + [sid for _, sid in pinned_customs])

        # Read Units.txt to find any custom DefaultSprite references not yet registered
        custom_sprites_to_add = list(pinned_customs)
        for line in open(scenario_units, 'r', encoding='utf-8'):
            if 'DefaultSprite' in line:
                sprite_name = line.split('DefaultSprite')[1].strip()
                if sprite_name not in existing_sprites and sprite_name not in pinned_names \
                        and sprite_name not in [s[0] for s in custom_sprites_to_add]:
                    max_id += 1
                    custom_sprites_to_add.append((sprite_name, max_id))

        # Write the complete merged registry (overwrite to prevent duplicate appends)
        with open(scenario_newsprite, 'w', encoding='utf-8') as f:
            f.writelines(newsprite_lines)
            if custom_sprites_to_add:
                f.write("\n# Custom MoM Unit Sprites\n")
                for sprite_name, sprite_id in custom_sprites_to_add:
                    f.write(f"{sprite_name} {sprite_id}\n")
                print(f"  + merged base newsprite.txt with {len(custom_sprites_to_add)} custom sprite definition(s)")
            else:
                print("  + synced base newsprite.txt to scenario")
    except Exception as e:
        print(f"  ! Warning: Could not merge newsprite.txt: {e}")

    print("Done. Run ctp2_csvgen.py to check exports.")


def _civ_tab(key: str, value: str) -> str:
    """Return a tab-aligned field line: KEY<tabs>VALUE matching civilisation.txt convention.

    Preconditions: key is a non-empty identifier; value is the raw token or quoted string.
    Guarantee: produces '\tKEY<tabs>VALUE\n' with enough tabs so value starts at or after col 25.
    """
    # Base file uses 1 tab indent + tabs to align value.  Field name + 1 leading tab;
    # then pad with tabs so the value column lands >= 24 chars in.
    padded = key
    col = len(key)
    while col < 23:
        padded += '\t'
        col = ((col // 8) + 1) * 8
    if col == 23 or col % 8 != 0:
        padded += '\t'
    return f'\t{padded}\t{value}\n'


def _str_tab(key: str, value: str) -> str:
    """Return a tab-aligned string-file line: KEY<tabs>"value" matching civ_str.txt convention.

    Preconditions: key is a non-empty string key; value is unquoted text.
    Guarantee: produces 'KEY<tabs>"value"\n' with value column at or after col 24.
    """
    col = len(key)
    tabs = ''
    while col < 24:
        tabs += '\t'
        col = ((col // 8) + 1) * 8
    if not tabs:
        tabs = '\t'
    return f'{key}{tabs}"{value}"\n'


_CIV_HEADER_RE = re.compile(r'^([A-Z][A-Z0-9_]+)(?:\s+#\d+)?\s*$')


def _civ_record_name(lines: list[str], index: int) -> str | None:
    """Return the top-level civilisation record name at lines[index], if any."""
    match = _CIV_HEADER_RE.match(lines[index].strip())
    if not match:
        return None
    probe = index + 1
    while probe < len(lines) and lines[probe].strip() == '':
        probe += 1
    if probe < len(lines) and lines[probe].strip() == '{':
        return match.group(1)
    return None


def _find_civilisation_record_bounds(lines: list[str], ident: str) -> tuple[int, int]:
    """Return [start, end) line bounds for the named top-level civilisation record block."""
    for i in range(len(lines)):
        if _civ_record_name(lines, i) != ident:
            continue
        depth = 0
        saw_open = False
        probe = i + 1
        while probe < len(lines):
            depth += lines[probe].count('{') - lines[probe].count('}')
            if lines[probe].count('{'):
                saw_open = True
            probe += 1
            if saw_open and depth <= 0:
                while probe < len(lines) and lines[probe].strip() == '':
                    probe += 1
                return i, probe
        break
    raise RuntimeError(f'Could not locate civilisation record {ident!r} in base source')


def _renumber_civilisation_headers(lines: list[str]) -> list[str]:
    """Rewrite civilisation header comment numbers to match final record order."""
    renumbered = list(lines)
    civ_index = 0
    for i in range(len(renumbered)):
        ident = _civ_record_name(renumbered, i)
        if not ident:
            continue
        renumbered[i] = f'{ident}\t#{civ_index}\n'
        civ_index += 1
    return renumbered


def _generate_civilisation_tribes() -> None:
    """Regenerate the MoM tribe blocks into selectable civ order from players.csv.

    Preconditions: players.csv has columns ctp2_is_new, ctp2_civ_id, civ2_leader_male,
        civ2_leader_female, personality_male, personality_female, parchment, city_style,
        emissary_photo, nation_flag. tribe_cities.csv has columns ctp2_civ_id + city_1..city_15.
    Guarantee: civilisation.txt contains only BARBARIAN plus the MoM tribes from players.csv,
        so loading the scenario exposes only MoM selectable civs; file is LF-only.
    Maintain: the file is rebuilt from canonical base BARBARIAN data each run, then renumbered
        so the header comments stay consistent with the actual selectable civ order.
    """
    if not _csv_exists('players.csv') or not _csv_exists('tribe_cities.csv'):
        return

    players = [r for r in _csv_rows('players.csv') if r.get('ctp2_is_new', '').strip() == 'yes']
    if not players:
        return

    cities_by_key = {}
    for row in _csv_rows('tribe_cities.csv'):
        key = row['ctp2_civ_id'].strip()
        cities_by_key[key] = [row.get(f'city_{i}', '').strip() for i in range(1, 16)]

    civ_path = SCENARIO / 'default/gamedata/civilisation.txt'
    SENTINEL = '# == BEGIN GENERATED MOM TRIBES =='

    # Always source the base 70-civ block from the canonical ctp2_data copy.
    # The scenario file is generator output and has no independent base to preserve.
    base_source = CTP2_DATA / 'default/gamedata/civilisation.txt'
    with base_source.open('r', encoding='latin-1') as fh:
        base_lines = fh.readlines()

    blocks = [
        '\n',
        f'{SENTINEL}\n',
        '# Generated by ctp2_generator.py from players.csv + tribe_cities.csv\n',
        '# DO NOT EDIT - re-run the generator to update\n',
        '#----------------------------------------------------------------------------\n',
        '# Masters of Magic Scenario Tribes\n',
        '#----------------------------------------------------------------------------\n',
        '\n',
    ]

    for i, row in enumerate(players):
        key = row['ctp2_civ_id'].strip()
        lm = row['civ2_leader_male'].strip()
        lf = row['civ2_leader_female'].strip()
        pers_m = row['personality_male'].strip()
        pers_f = row['personality_female'].strip()
        parch = row['parchment'].strip()
        cs = row['city_style'].strip()
        emis = row['emissary_photo'].strip()
        flag = row['nation_flag'].strip()
        city_list = cities_by_key.get(key, [])

        blocks.append(f'{key}\n')
        blocks.append('{\n')
        blocks.append(_civ_tab('LeaderNameMale', f'{key}_LEADERM_NAME'))
        if lf:
            blocks.append(_civ_tab('LeaderNameFemale', f'{key}_LEADERF_NAME'))
        else:
            blocks.append(_civ_tab('LeaderNameFemale', f'{key}_LEADERM_NAME'))
        blocks.append(_civ_tab('PersonalityMale', pers_m))
        blocks.append(_civ_tab('PersonalityFemale', pers_f))
        blocks.append(_civ_tab('PersonalityDescription', f'PERSONALITY_DESCRIPTION_{key}'))
        blocks.append(_civ_tab('CountryName', f'{key}_COUNTRY_NAME'))
        blocks.append(_civ_tab('SingularCivName', f'{key}_SINGULAR'))
        blocks.append(_civ_tab('PluralCivName', f'{key}_PLURAL'))
        blocks.append(_civ_tab('EmissaryPhotoMale', emis))
        blocks.append(_civ_tab('EmissaryPhotoFemale', emis))
        blocks.append(_civ_tab('Parchment', parch))
        blocks.append(_civ_tab('CityStyle', cs))
        blocks.append(_civ_tab('NationUnitFlag', flag))
        for i, city in enumerate(city_list, 1):
            if city:
                blocks.append(_civ_tab('CityName', f'{key}_CITY_{i}'))
        blocks.append('}\n\n')

    _, barbarian_end = _find_civilisation_record_bounds(base_lines, 'BARBARIAN')
    content_lines = base_lines[:barbarian_end] + blocks
    content = ''.join(_renumber_civilisation_headers(content_lines))
    with civ_path.open('w', encoding='latin-1', newline='') as fh:
        fh.write(content)
    print(f'  + civilisation.txt: wrote BARBARIAN + {len(players)} MoM tribe civ block(s)')


def _generate_civstr_tribes() -> None:
    """Regenerate the MoM tribe string entries at the end of civ_str.txt from players.csv.

    Preconditions: players.csv has ctp2_is_new, ctp2_civ_id, civ2_leader_male,
        civ2_leader_female, civ2_tribe_name.  tribe_cities.csv has city_1..city_15.
    Guarantee: civ_str.txt ends with exactly the tribe string entries; base entries preserved
        verbatim; file is LF-only.
    Maintain: tribe section is delimited by a sentinel comment so re-runs are idempotent.
    """
    if not _csv_exists('players.csv') or not _csv_exists('tribe_cities.csv'):
        return

    players = [r for r in _csv_rows('players.csv') if r.get('ctp2_is_new', '').strip() == 'yes']
    if not players:
        return

    cities_by_key = {}
    for row in _csv_rows('tribe_cities.csv'):
        key = row['ctp2_civ_id'].strip()
        cities_by_key[key] = [row.get(f'city_{i}', '').strip() for i in range(1, 16)]

    str_path = SCENARIO / 'english/gamedata/civ_str.txt'
    SENTINEL = '# == BEGIN GENERATED MOM TRIBES =='

    # Always source the base string block from the canonical ctp2_data copy.
    base_source = CTP2_DATA / 'english/gamedata/civ_str.txt'
    with base_source.open('r', encoding='latin-1') as fh:
        base_lines = fh.readlines()

    while base_lines and base_lines[-1].strip() == '':
        base_lines.pop()

    blocks = [
        '\n',
        f'{SENTINEL}\n',
        '# Generated by ctp2_generator.py from players.csv + tribe_cities.csv\n',
        '# DO NOT EDIT - re-run the generator to update\n',
        '#----------------------------------------------------------------------------\n',
        '# Masters of Magic Scenario Tribe Strings\n',
        '#----------------------------------------------------------------------------\n',
        '\n',
    ]

    for row in players:
        key = row['ctp2_civ_id'].strip()
        tribe_name = row['civ2_tribe_name'].strip()
        lm = row['civ2_leader_male'].strip()
        lf = row['civ2_leader_female'].strip()
        city_list = cities_by_key.get(key, [])

        singular = tribe_name.replace('Tribes of ', '') + ' Tribe'
        blocks.append(f'# --- {key} ---\n')
        blocks.append(_str_tab(f'{key}_LEADERM_NAME', lm))
        if lf:
            blocks.append(_str_tab(f'{key}_LEADERF_NAME', lf))
        blocks.append(_str_tab(f'{key}_COUNTRY_NAME', tribe_name))
        blocks.append(_str_tab(f'{key}_SINGULAR', singular))
        blocks.append(_str_tab(f'{key}_PLURAL', tribe_name))
        blocks.append(_str_tab(f'PERSONALITY_DESCRIPTION_{key}', tribe_name))
        for i, city in enumerate(city_list, 1):
            if city:
                blocks.append(_str_tab(f'{key}_CITY_{i}', city))
        blocks.append('\n')

    content = ''.join(base_lines) + ''.join(blocks)
    with str_path.open('w', encoding='latin-1', newline='') as fh:
        fh.write(content)
    print(f'  + civ_str.txt: wrote {len(players)} tribe string block(s)')


if __name__ == '__main__':
    main()
