"""Audit a merged control plane for un-collapsed semantic duplicates.

Purpose:
    First-wins merge dedup (merge_control_planes.py) only collapses EXACT
    sanitized-name matches. Sources like LotR ship per-faction variants of a
    common concept ("Archery" vs "Archery Elves"/"Archery Orcs") that survive
    the union as separate advances/units. This tool derives the faction-suffix
    token set FROM the data (a trailing word is a faction token when stripping
    it lands on another entry's full name, observed at least twice), stems
    every name, groups rows sharing a stem, and writes the groups to
    collapse_candidates.csv in the csv dir — a reviewable staging sheet in the
    genre_mask.csv pattern. Read-only over every dimension file; the only
    write is the candidates sheet itself.

Preconditions:
    --csv dir contains advances.csv and units.csv with `name` and `source`
    columns (merge output). Advance codes may live in the `code` column OR,
    for curated base rows, in the `category` comment ("3    ; AFl").

Failure modes:
    SystemExit if the csv dir or a dimension file is missing.

Usage:
    audit_collapse_candidates.py --csv <merged csv dir>
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from merge_control_planes import read_rows, sanitize

DIMENSIONS = ("advances.csv", "units.csv")


def row_code(name: str, row: dict[str, str]) -> str:
    """Short code for a row: `code`/`prereq` column, else the base-row
    category-comment form ("3    ; AFl" -> "AFl")."""
    code = (row.get("code") or row.get("prereq") or "").strip()
    if code and code.lower() not in ("nil", "no"):
        return code
    m = re.search(r";\s*(\S+)", row.get("category", "") or "")
    return m.group(1) if m else ""


def derive_faction_tokens(names: list[str]) -> set[str]:
    """A trailing word is a faction token when stripping it yields another
    entry's full sanitized name, observed on >= 2 distinct entries."""
    index = {sanitize(n) for n in names}
    hits: Counter[str] = Counter()
    for name in names:
        words = name.split()
        if len(words) >= 2 and sanitize(" ".join(words[:-1])) in index:
            hits[words[-1]] += 1
    return {tok for tok, count in hits.items() if count >= 2}


def stem_of(name: str, tokens: set[str]) -> str:
    words = name.split()
    if len(words) >= 2 and words[-1] in tokens:
        return " ".join(words[:-1])
    return name


def audit_dimension(path: Path, out: list[list[str]]) -> tuple[int, set[str]]:
    _, rows = read_rows(path)
    names = [r["name"] for r in rows if r.get("name")]
    tokens = derive_faction_tokens(names)
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if row.get("name"):
            groups[sanitize(stem_of(row["name"], tokens))].append(row)
    n_groups = 0
    for stem_key in sorted(k for k, v in groups.items() if len(v) >= 2):
        members = groups[stem_key]
        n_groups += 1
        for row in sorted(members, key=lambda r: r["name"]):
            out.append([path.name, stem_key, row["name"],
                        row.get("source", "base"), row_code(row["name"], row),
                        str(len(members))])
    return n_groups, tokens


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, required=True,
                        help="merged control-plane csv dir")
    args = parser.parse_args()

    out_rows: list[list[str]] = []
    for name in DIMENSIONS:
        path = args.csv / name
        if not path.exists():
            raise SystemExit(f"{args.csv} has no {name}")
        n_groups, tokens = audit_dimension(path, out_rows)
        print(f"  {name}: {n_groups} candidate group(s); "
              f"faction tokens: {', '.join(sorted(tokens)) or '(none)'}")

    out_path = args.csv / "collapse_candidates.csv"
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, lineterminator="\r\n")
        writer.writerow(["dimension", "concept_stem", "member_name",
                         "member_source", "member_code", "group_size"])
        writer.writerows(out_rows)
    print(f"  wrote {out_path.name} ({len(out_rows)} member row(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
