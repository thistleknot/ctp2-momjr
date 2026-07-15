"""Dump the generator's in-code MoM policy defaults into control-plane files.

Purpose:
    One-shot scaffold: writes the per-mod policy surface (mod_policy.json +
    policy csv sheets) into the csv dir from the constants currently defined in
    ctp2_generator.py. Used once to bootstrap the MoM control plane, and
    reusable as a template generator when starting a NEW mod conversion
    (dump, then edit the files for the new mod).

Preconditions:
    - ctp2_generator must be importable (sibling module).

Failure modes:
    - Refuses to overwrite existing policy files unless --force is given.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import ctp2_generator as G

POLICY_FILES = [
    "mod_policy.json",
    "tileimp_mask.csv",
    "order_mask.csv",
    "concept_mask.csv",
    "gl_text_rewrites.csv",
    "advance_code_map.csv",
    "stub_advances.csv",
    "governicon_fallback.csv",
    "advance_cost_bands.csv",
    "sprite_pick_rules.csv",
    "gl_section_overrides.csv",
    "unit_block_overrides.csv",
]


def write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\r\n")
        writer.writerow(header)
        writer.writerows(rows)
    print(f"wrote {path.name} ({len(rows)} rows)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv-dir", type=Path, default=G.MOMJR)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    out = args.csv_dir

    existing = [n for n in POLICY_FILES if (out / n).exists()]
    if existing and not args.force:
        print(f"REFUSED: policy files already exist in {out}: {existing} (use --force)")
        return 1

    # The generator's loaded MOD_POLICY (round-1 + round-2 keys) IS the full
    # policy surface — re-emit it verbatim as the scaffold.
    policy = dict(G.MOD_POLICY)
    (out / "mod_policy.json").write_text(
        json.dumps(policy, indent=2) + "\n", encoding="utf-8")
    print("wrote mod_policy.json")

    # Round-2 csv surfaces are authored data (not derivable from module
    # constants) — scaffold them by copying the source mod's files.
    for name in ("sprite_pick_rules.csv", "gl_section_overrides.csv",
                 "unit_block_overrides.csv"):
        src = G.MOMJR / name
        if src.exists() and src.resolve() != (out / name).resolve():
            (out / name).write_bytes(src.read_bytes())
            print(f"wrote {name} (copied from {G.MOMJR.name})")

    rows = []
    for ident in sorted(G.HIDDEN_SURROGATE_TILEIMPS):
        rows.append([ident, "surrogate", G.SURROGATE_TILEIMP_NOTES.get(ident, "")])
    for ident in sorted(G.HIDDEN_OUT_OF_GENRE_TILEIMPS):
        rows.append([ident, "out_of_genre", G.SURROGATE_TILEIMP_NOTES.get(ident, "")])
    write_csv(out / "tileimp_mask.csv", ["id", "reason", "note"], rows)

    write_csv(out / "order_mask.csv", ["id"],
              [[i] for i in sorted(G.HIDDEN_OUT_OF_GENRE_ORDERS)])
    write_csv(out / "concept_mask.csv", ["id"],
              [[i] for i in sorted(G.HIDDEN_OUT_OF_GENRE_CONCEPTS)])

    # Order matters: rewrites apply sequentially.
    write_csv(out / "gl_text_rewrites.csv", ["find", "replace"],
              [[f, r] for f, r in G.HIDDEN_TILEIMP_GREAT_LIBRARY_TEXT])

    rows = [["prereq", c, a] for c, a in G.PREREQ_CODE_MAP.items()]
    rows += [["unit", c, a] for c, a in G.MOM_UNIT_ADVANCE.items()]
    write_csv(out / "advance_code_map.csv", ["lane", "code", "advance"], rows)

    write_csv(out / "stub_advances.csv", ["advance", "name", "category", "age"],
              [[k, v[0], v[1], v[2]] for k, v in G._BASE_UNIT_STUB_ADVANCES.items()])

    write_csv(out / "governicon_fallback.csv", ["id", "fallback"],
              [[k, v] for k, v in G.GOVERNICON_FALLBACK_IDS.items()])

    bands = G._load_ae_advance_cost_bands()
    write_csv(out / "advance_cost_bands.csv", ["age", "low", "high"],
              [[age, str(lo), str(hi)] for age, (lo, hi) in bands.items()])

    return 0


if __name__ == "__main__":
    sys.exit(main())
