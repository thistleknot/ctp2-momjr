"""Encode a Civ2 mod into the xlsx/csv control plane consumed by ctp2_generator.

Purpose:
    Stage 1 of the universal mod encoder: civ2 mod -> per-dimension CSVs (with
    image cell indices transcribed) + policy scaffold + xlsx workbook. Output
    is a fresh csv dir in the same schemas as momjr_csv, ready for hand-curation
    and then ctp2_generator (pointed at it via CTP2_GENERATOR_CSV_DIR).

Inputs:
    --pair <id>    a mod_pairs.json entry with parser == "civ2" (its `mod` dir
                   must contain RULES.TXT), or --mod-dir <path> directly.
    --out <dir>    destination csv dir (created; refuses to overwrite unless --force).

What is auto-derived vs scaffolded:
    - advances.csv      full: @CIVILIZE rows (code from trailing ; comment,
                        cell_index = section ordinal, prereqs, epoch, category)
    - units.csv         full: @UNITS rows (civ2 stat suffixes preserved,
                        icon/sprite/sound ids by naming convention)
    - improvements.csv  full: @IMPROVE minus the trailing wonder rows
    - wonders_civ2.csv  raw material only: wonder name/cost/prereq/expiry.
                        wonders.csv (CTP2 block_text) must be authored per mod.
    - players.csv       skeleton: civ2 leaders/tribes; ctp2 columns left blank
    - policy files      MoM defaults via dump_mod_policy (edit for the new mod)
    - workbook          export_mod_workbook over the new csv dir

Failure modes:
    - SystemExit if RULES.TXT or the requested pair is missing, or if --out
      exists non-empty without --force.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent

# Section column schemas (civ2 RULES.TXT). Trailing comment is captured
# separately as `_comment` (it carries the advance short-code in @CIVILIZE).
CIV2_UNIT_COLS = [
    "name", "until", "domain", "move", "range", "attack", "defense",
    "hits", "firepower", "cost", "hold", "role", "prereq", "flags",
]
CIV2_CIVILIZE_COLS = [
    "name", "ai_value", "modifier", "prereq1", "prereq2", "epoch", "category",
]
CIV2_IMPROVE_COLS = ["name", "cost", "upkeep", "prereq"]
CIV2_LEADER_COLS = [
    "leader_male", "leader_female", "female_flag", "color", "style",
    "tribe_name", "adjective", "attack", "expand", "civilize",
]


def sanitize(name: str) -> str:
    """Identifier sanitizer — MUST match ctp2_generator.sanitize exactly."""
    s = name.upper().replace(" ", "_").replace("'", "").replace("-", "_")
    s = re.sub(r'[^A-Z0-9_]', '', s)
    return s


def parse_rules(text: str) -> dict[str, list[dict[str, str]]]:
    """Parse RULES.TXT into {section: rows}; keeps trailing comments.

    Row dicts are keyed by ordinal (`c0`, `c1`, ...) plus `_comment` for any
    trailing `;` comment. Schema naming is applied by the emitters, keeping
    this parser section-agnostic.
    """
    sections: dict[str, list[dict[str, str]]] = {}
    current: str | None = None
    rows: list[dict[str, str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith("@"):
            if current is not None:
                sections[current] = rows
            current = line.split()[0].upper()
            rows = []
            continue
        if current is None:
            continue
        comment = ""
        if ";" in line:
            line, comment = line.split(";", 1)
            line = line.rstrip()
            comment = comment.strip()
        parts = [p.strip() for p in line.split(",")]
        row = {f"c{i}": v for i, v in enumerate(parts)}
        row["_comment"] = comment
        rows.append(row)
    if current is not None:
        sections[current] = rows
    return sections


def named(row: dict[str, str], cols: list[str]) -> dict[str, str]:
    out = {col: row.get(f"c{i}", "") for i, col in enumerate(cols)}
    out["_comment"] = row.get("_comment", "")
    return out


def data_rows(sections, section: str, min_cols: int) -> list[dict[str, str]]:
    """Section rows that look like data (>= min_cols comma fields).

    Some mods carry stray prose lines inside sections (non-`;` comment styles
    the civ2 engine happens to ignore); arity is the discriminator.
    """
    rows = []
    for raw in sections.get(section, []):
        n = len([k for k in raw if k.startswith("c")])
        if n >= min_cols:
            rows.append(raw)
        else:
            text = raw.get("c0", "")[:60]
            print(f"  [skip] {section} non-data line: {text!r}")
    return rows


def write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\r\n")
        writer.writerow(header)
        writer.writerows(rows)
    print(f"  wrote {path.name} ({len(rows)} rows)")


def emit_advances(sections, out: Path) -> None:
    rows = []
    for idx, raw in enumerate(data_rows(sections, "@CIVILIZE", 6)):
        r = named(raw, CIV2_CIVILIZE_COLS)
        ident = sanitize(r["name"])
        rows.append([
            str(idx), r["name"], r["_comment"], r["prereq1"], r["prereq2"],
            r["epoch"], r["category"],
            f"ICON_ADVANCE_{ident}",
            f"ADVANCE_{ident}_GAMEPLAY", f"ADVANCE_{ident}_HISTORICAL",
            f"ADVANCE_{ident}_PREREQ", f"ADVANCE_{ident}_STATISTICS",
            f"ADVANCE_{ident}_PREREQ",
        ])
    write_csv(out / "advances.csv",
              ["cell_index", "name", "code", "prereq1", "prereq2", "epoch",
               "category", "icon", "gameplay_str", "historical_str",
               "prereq_str", "vari_str", "stattext_str"], rows)


def emit_units(sections, out: Path) -> None:
    rows = []
    for idx, raw in enumerate(data_rows(sections, "@UNITS", 13)):
        r = named(raw, CIV2_UNIT_COLS)
        ident = sanitize(r["name"])
        move = r["move"].rstrip(".")
        rows.append([
            str(idx), r["name"], r["domain"], move, r["attack"], r["defense"],
            r["hits"], r["firepower"], r["cost"], r["prereq"],
            f"ICON_UNIT_{ident}", f"SPRITE_{ident}",
            f"SOUND_SELECT1_{ident}", f"SOUND_MOVE_{ident}", f"SOUND_ATTACK_{ident}",
        ])
    write_csv(out / "units.csv",
              ["cell_index", "name", "domain", "move", "attack", "defense",
               "hp", "firepower", "cost", "prereq", "icon", "sprite",
               "sound_select1", "sound_move", "sound_attack"], rows)


def emit_improvements_and_wonders(sections, out: Path) -> None:
    improve_rows = data_rows(sections, "@IMPROVE", 4)
    n_wonders = len(sections.get("@ENDWONDER", []))
    boundary = len(improve_rows) - n_wonders if n_wonders else len(improve_rows)

    rows = []
    for idx, raw in enumerate(improve_rows[:boundary]):
        r = named(raw, CIV2_IMPROVE_COLS)
        if r["name"].strip().lower() == "nothing":
            continue
        ident = sanitize(r["name"])
        rows.append([str(idx), r["name"], r["cost"], r["upkeep"], r["prereq"],
                     f"ICON_IMPROVE_{ident}"])
    write_csv(out / "improvements.csv",
              ["cell_index", "name", "cost", "upkeep", "prereq", "icon"], rows)

    rows = []
    endwonder = sections.get("@ENDWONDER", [])
    for widx, raw in enumerate(improve_rows[boundary:]):
        r = named(raw, CIV2_IMPROVE_COLS)
        expiry_row = named(endwonder[widx], ["expiry"]) if widx < len(endwonder) else {"expiry": ""}
        rows.append([str(boundary + widx), r["name"], r["cost"], r["upkeep"],
                     r["prereq"], expiry_row["expiry"]])
    write_csv(out / "wonders_civ2.csv",
              ["cell_index", "name", "cost", "upkeep", "prereq", "expiry"], rows)


def emit_advance_code_map(sections, out: Path) -> None:
    """Derive the mod's own short-code -> ADVANCE_* map from @CIVILIZE comments.

    Civ2 prereq columns reference advances by 3-letter code; each @CIVILIZE row
    carries its own code as the trailing `;` comment. Both lanes (improvement
    prereqs and unit prereqs) share this code space. Overwrites the MoM-default
    scaffold written by dump_mod_policy.
    """
    rows = []
    for raw in data_rows(sections, "@CIVILIZE", 6):
        r = named(raw, CIV2_CIVILIZE_COLS)
        code = r["_comment"].split()[0] if r["_comment"] else ""
        if not code:
            continue
        advance = f"ADVANCE_{sanitize(r['name'])}"
        rows.append(["prereq", code, advance])
        rows.append(["unit", code, advance])
    if rows:
        write_csv(out / "advance_code_map.csv", ["lane", "code", "advance"], rows)
        print("  (advance_code_map.csv derived from this mod's @CIVILIZE codes)")


def emit_players(sections, out: Path) -> None:
    rows = []
    for idx, raw in enumerate(data_rows(sections, "@LEADERS", 7), start=1):
        r = named(raw, CIV2_LEADER_COLS)
        male = "" if r["leader_male"] == "..." else r["leader_male"]
        female = "" if r["leader_female"] == "..." else r["leader_female"]
        rows.append([str(idx), r["tribe_name"], male, female, "civ2_leader",
                     "", "", "", "", "", "", "", "", ""])
    write_csv(out / "players.csv",
              ["civ2_index", "civ2_tribe_name", "civ2_leader_male",
               "civ2_leader_female", "civ2_type", "ctp2_civ_id", "ctp2_is_new",
               "parchment", "city_style", "personality_male",
               "personality_female", "emissary_photo", "nation_flag", "notes"],
              rows)


def scaffold_policy(out: Path) -> None:
    import dump_mod_policy
    saved = sys.argv
    try:
        sys.argv = ["dump_mod_policy.py", "--csv-dir", str(out)]
        dump_mod_policy.main()
    finally:
        sys.argv = saved

    # Atlas geometry scaffold: MOMJR rows as a template to edit for this mod's
    # BMP sheets (the extractor prefers the csv-dir copy via CTP2_GENERATOR_CSV_DIR).
    atlas_src = TOOLS_DIR / "sprite_atlas_config.csv"
    if atlas_src.exists():
        (out / "sprite_atlas_config.csv").write_bytes(atlas_src.read_bytes())
        print("  scaffolded sprite_atlas_config.csv (edit geometry for this mod's sheets)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--pair", help="mod_pairs.json id with parser == civ2")
    src.add_argument("--mod-dir", type=Path, help="civ2 mod directory containing RULES.TXT")
    parser.add_argument("--pairs-file", type=Path, default=TOOLS_DIR / "mod_pairs.json")
    parser.add_argument("--out", type=Path, required=True, help="destination csv dir")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--no-policy", action="store_true",
                        help="skip scaffolding the policy files")
    parser.add_argument("--no-workbook", action="store_true",
                        help="skip the xlsx workbook export")
    args = parser.parse_args()

    if args.pair:
        pairs = json.loads(args.pairs_file.read_text(encoding="utf-8"))["mod_pairs"]
        match = [p for p in pairs if p["id"] == args.pair]
        if not match:
            raise SystemExit(f"pair '{args.pair}' not found in {args.pairs_file}")
        if match[0].get("parser") != "civ2":
            raise SystemExit(f"pair '{args.pair}' is not a civ2 mod (parser={match[0].get('parser')})")
        mod_dir = Path(match[0]["mod"])
    else:
        mod_dir = args.mod_dir

    rules_path = next((p for p in (mod_dir / "RULES.TXT", mod_dir / "rules.txt") if p.exists()), None)
    if rules_path is None:
        raise SystemExit(f"RULES.TXT not found in {mod_dir}")

    out = args.out
    if out.exists() and any(out.iterdir()) and not args.force:
        raise SystemExit(f"output dir {out} is not empty (use --force)")
    out.mkdir(parents=True, exist_ok=True)

    print(f"Encoding {rules_path}")
    sections = parse_rules(rules_path.read_text(encoding="latin-1"))
    for name in ("@CIVILIZE", "@UNITS", "@IMPROVE", "@LEADERS"):
        print(f"  {name}: {len(sections.get(name, []))} rows")

    emit_advances(sections, out)
    emit_units(sections, out)
    emit_improvements_and_wonders(sections, out)
    emit_players(sections, out)

    if not args.no_policy:
        scaffold_policy(out)
        emit_advance_code_map(sections, out)

    if not args.no_workbook:
        from export_mod_workbook import export_workbook
        wb_path, sheets = export_workbook(out / "mod_inventory.xlsx", csv_root=out)
        print(f"  wrote {wb_path.name} ({sheets} sheets)")

    print("\nEncoded. Hand-curation TODO for a playable conversion:")
    print("  - wonders.csv: author CTP2 block_text per wonder (see momjr_csv/wonders.csv)")
    print("  - players.csv: fill ctp2_* columns (civ id, city style, personalities, flags)")
    print("  - policy files: edit the scaffolded MoM defaults for this mod")
    print("  - sprite_atlas_config.csv: add this mod's BMP sheet geometry rows")
    print("  - terrain/tileimp/goods/orders/concepts: KEEP dimensions; curate if needed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
