"""Encode a native CTP2 mod into the xlsx/csv control plane.

Purpose:
    The inverse of ctp2_generator: parse an existing CTP2 mod's gamedata block
    files (Units.txt, Advance.txt, buildings.txt/Improve.txt, Wonder.txt) into
    the SAME per-dimension csv schema that encode_civ2_mod produces, so native
    CTP2 mods (Cradle, Ages of Man, LotR) can join the map-reduce merge on equal
    footing with civ2 mods. This closes the "both engines" gap.

    Cross-engine schema NORMALIZATION applied so a ctp2-sourced row is
    indistinguishable from a civ2-sourced one downstream:
      - stats: ctp2 is pre-scaled; the control plane stores civ2-scale (the
        generator multiplies attack/defense x5, cost x100). So divide back:
        Attack/DEFAULT_ATTACK_SCALE, ShieldCost/DEFAULT_COST_SCALE.
      - domain: MovementType {Sea:2, Air:1, else Land:0} -> civ2 domain int.
      - prereq: EnableAdvance IDENT is used verbatim as the prereq "code"; the
        emitted advance_code_map maps ident->ident (identity), so the merge's
        tag:code namespacing keeps it collision-safe across mods.
      - age: Advance.txt Age (AGE_*) carried through; epoch derived from it.

    Field parsing uses a local block parser (CTP2BlockFile drops repeated keys
    like Prerequisites/MovementType and mis-pairs flag-only lines).

Usage:
    encode_ctp2_mod.py --mod-dir <ctp2 mod root or its ctp2_data/default/gamedata>
        --out <csv dir> [--english <english/gamedata for gl_str names>]
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
DEFAULT_ATTACK_SCALE = 5    # generator does attack/defense x5
DEFAULT_COST_SCALE = 100    # generator does cost x100
AGE_TO_EPOCH = {"AGE_ONE": 0, "AGE_TWO": 1, "AGE_THREE": 2, "AGE_FOUR": 3,
                "AGE_FIVE": 4, "AGE_SIX": 5, "AGE_SEVEN": 6, "AGE_EIGHT": 7,
                "AGE_NINE": 8, "AGE_TEN": 9}


def parse_blocks(text: str) -> list[tuple[str, dict[str, list[str]]]]:
    """CTP2 block file -> [(ident, {field: [values...]})], repeated keys kept,
    flag-only lines recorded as field with empty-string value."""
    out: list[tuple[str, dict[str, list[str]]]] = []
    ident = None
    fields: dict[str, list[str]] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        m = re.match(r"^([A-Z][A-Z0-9_]+)\s*\{", line)
        if m:
            ident, fields = m.group(1), {}
            continue
        if line.startswith("}"):
            if ident is not None:
                out.append((ident, fields))
            ident = None
            continue
        if ident is None:
            continue
        parts = line.split(None, 1)
        key = parts[0].rstrip(":")
        val = parts[1].strip() if len(parts) > 1 else ""
        fields.setdefault(key, []).append(val)
    return out


def dedup_last_wins(blocks: list[tuple[str, dict[str, list[str]]]]
                    ) -> list[tuple[str, dict[str, list[str]]]]:
    """Collapse repeated idents to one block, LAST occurrence winning — mirrors
    CTP2 DB load semantics where a later Parse() of the same ident overwrites
    the earlier one. Multi-file mods (LotR: LOTR_Advance.txt + LOTR2_Advance.txt
    carry the same idents) would otherwise double-count every entry. First-seen
    order is preserved for determinism."""
    order: list[str] = []
    latest: dict[str, dict[str, list[str]]] = {}
    for ident, fields in blocks:
        if ident not in latest:
            order.append(ident)
        latest[ident] = fields
    return [(ident, latest[ident]) for ident in order]


def first(fields: dict[str, list[str]], key: str, default: str = "") -> str:
    v = fields.get(key)
    return v[0] if v else default


def humanize(ident: str, prefix: str) -> str:
    s = ident[len(prefix):] if ident.startswith(prefix) else ident
    return s.replace("_", " ").title()


def load_gl_names(english: Path | None) -> dict[str, str]:
    names: dict[str, str] = {}
    if not english:
        return names
    for fn in ("gl_str.txt",):
        p = english / fn
        if p.exists():
            for m in re.finditer(r'^([A-Za-z_][A-Za-z0-9_]*)\s+"([^"]*)"',
                                 p.read_text(encoding="latin-1"), re.M):
                names[m.group(1)] = m.group(2)
    return names


def num(v: str) -> int:
    return int(re.sub(r"[^0-9-]", "", v) or 0)


def domain_of(fields: dict[str, list[str]]) -> int:
    mts = " ".join(fields.get("MovementType", []))
    if "Sea" in mts or "Water" in mts:
        return 2
    if "Air" in mts or "Space" in mts:
        return 1
    return 0


def write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\r\n")
        w.writerow(header)
        w.writerows(rows)
    print(f"  wrote {path.name} ({len(rows)} rows)")


def resolve_gamedata(mod_dir: Path) -> Path:
    """Accept a gamedata dir or a mod root; find the dir holding *Advance.txt."""
    if find_dimension_files(mod_dir, "Advance.txt"):
        return mod_dir
    for cand in (mod_dir / "default" / "gamedata",
                 mod_dir / "ctp2_data" / "default" / "gamedata"):
        if cand.exists() and find_dimension_files(cand, "Advance.txt"):
            return cand
    for p in mod_dir.rglob("*Advance.txt"):
        return p.parent
    raise SystemExit(f"no gamedata (*Advance.txt) found under {mod_dir}")


def find_dimension_files(gd: Path, suffix: str) -> list[Path]:
    """All files whose name ENDS in the dimension suffix (case-insensitive) —
    handles mods that prefix files (LotR: LOTR_Units.txt, LOTR3_Units.txt) and
    load them via a gamefile manifest. Sorted for determinism."""
    if not gd.exists():
        return []
    sl = suffix.lower()
    return sorted((p for p in gd.iterdir()
                   if p.is_file() and p.name.lower().endswith(sl)),
                  key=lambda p: p.name.lower())


def read_dimension(gd: Path, *suffixes: str) -> str:
    """Concatenate the text of every file matching any suffix (first non-empty
    suffix group wins — e.g. buildings.txt preferred over Improve.txt)."""
    for suffix in suffixes:
        files = find_dimension_files(gd, suffix)
        if files:
            return "\n".join(p.read_text(encoding="latin-1") for p in files)
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mod-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--english", type=Path, default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--no-policy", action="store_true")
    parser.add_argument("--no-workbook", action="store_true")
    args = parser.parse_args()

    gd = resolve_gamedata(args.mod_dir)
    english = args.english
    if english is None:
        cand = gd.parent.parent / "english" / "gamedata"
        english = cand if cand.exists() else None
    names = load_gl_names(english)
    out = args.out
    if out.exists() and any(out.iterdir()) and not args.force:
        raise SystemExit(f"output dir {out} not empty (use --force)")
    out.mkdir(parents=True, exist_ok=True)
    print(f"Encoding CTP2 gamedata {gd}")

    # --- advances ---
    adv_blocks = dedup_last_wins(parse_blocks(read_dimension(gd, "Advance.txt")))
    adv_rows, code_rows = [], []
    for idx, (ident, f) in enumerate(adv_blocks):
        name = names.get(ident, humanize(ident, "ADVANCE_"))
        age = first(f, "Age", "AGE_ONE")
        prereqs = f.get("Prerequisites", [])
        p1 = prereqs[0] if len(prereqs) > 0 else "nil"
        p2 = prereqs[1] if len(prereqs) > 1 else "nil"
        adv_rows.append([str(idx), name, ident, p1, p2, str(AGE_TO_EPOCH.get(age, 0)),
                         age, first(f, "Icon", f"ICON_ADVANCE_{ident[len('ADVANCE_'):]}"),
                         f"{ident}_GAMEPLAY", f"{ident}_HISTORICAL",
                         f"{ident}_PREREQ", f"{ident}_STATISTICS", f"{ident}_STATISTICS"])
        code_rows.append(["prereq", ident, ident])
        code_rows.append(["unit", ident, ident])
    write_csv(out / "advances.csv",
              ["cell_index", "name", "code", "prereq1", "prereq2", "epoch",
               "category", "icon", "gameplay_str", "historical_str",
               "prereq_str", "vari_str", "stattext_str"], adv_rows)

    # --- units ---
    unit_blocks = dedup_last_wins(parse_blocks(read_dimension(gd, "Units.txt")))
    urows = []
    for idx, (ident, f) in enumerate(unit_blocks):
        name = names.get(ident, humanize(ident, "UNIT_"))
        atk = num(first(f, "Attack", "0")) // DEFAULT_ATTACK_SCALE
        dfn = num(first(f, "Defense", "0")) // DEFAULT_ATTACK_SCALE
        hp = num(first(f, "MaxHP", "10"))
        fp = num(first(f, "Firepower", "1"))
        cost = max(1, num(first(f, "ShieldCost", "100")) // DEFAULT_COST_SCALE)
        move = max(1, num(first(f, "MaxMovePoints", "100")) // 100)
        prereq = first(f, "EnableAdvance", "nil") or "nil"
        san = ident[len("UNIT_"):]
        urows.append([str(idx), name, str(domain_of(f)), str(move),
                      f"{atk}a", f"{dfn}d", f"{hp}h", f"{fp}f", str(cost), prereq,
                      first(f, "DefaultIcon", f"ICON_UNIT_{san}"),
                      first(f, "DefaultSprite", f"SPRITE_{san}"),
                      f"SOUND_SELECT1_{san}", f"SOUND_MOVE_{san}", f"SOUND_ATTACK_{san}"])
    write_csv(out / "units.csv",
              ["cell_index", "name", "domain", "move", "attack", "defense",
               "hp", "firepower", "cost", "prereq", "icon", "sprite",
               "sound_select1", "sound_move", "sound_attack"], urows)

    # --- improvements (buildings.txt preferred; else Improve.txt) ---
    imp_blocks = dedup_last_wins(parse_blocks(read_dimension(gd, "buildings.txt", "Improve.txt")))
    irows = []
    for idx, (ident, f) in enumerate(imp_blocks):
        if not ident.startswith("IMPROVE_"):
            continue
        name = names.get(ident, humanize(ident, "IMPROVE_"))
        cost = max(1, num(first(f, "ProductionCost", first(f, "ShieldCost", "100"))) // DEFAULT_COST_SCALE)
        upkeep = num(first(f, "Upkeep", "0"))
        prereq = first(f, "EnableAdvance", "nil") or "nil"
        irows.append([str(idx), name, str(cost), str(upkeep), prereq,
                      first(f, "DefaultIcon", f"ICON_{ident}")])
    write_csv(out / "improvements.csv",
              ["cell_index", "name", "cost", "upkeep", "prereq", "icon"], irows)

    # Policy scaffold FIRST (it writes a default advance_code_map), then
    # overwrite advance_code_map with this mod's identity map.
    if not args.no_policy:
        import dump_mod_policy
        saved = sys.argv
        try:
            sys.argv = ["dump_mod_policy.py", "--csv-dir", str(out)]
            dump_mod_policy.main()
        finally:
            sys.argv = saved

    # --- advance code map (identity for ctp2 idents) ---
    write_csv(out / "advance_code_map.csv", ["lane", "code", "advance"], code_rows)

    if not args.no_workbook:
        from export_mod_workbook import export_workbook
        wb, sheets = export_workbook(out / "mod_inventory.xlsx", csv_root=out)
        print(f"  wrote {wb.name} ({sheets} sheets)")

    print("\nEncoded CTP2 mod. Notes:")
    print("  - stats normalized to control-plane civ2-scale (atk/def /5, cost /100).")
    print("  - prereq = EnableAdvance IDENT; advance_code_map is identity.")
    print("  - wonders/goods/terrain not yet imported (ctp2 Wonder.txt is block_text).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
