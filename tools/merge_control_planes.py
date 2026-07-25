"""Merge multiple encoded civ2 control planes into one super-mod csv dir.

Purpose:
    Union per-dimension csvs (advances, units, improvements) from an ordered
    list of source csv dirs. First source wins name collisions (key =
    generator-sanitized name); every merged row gains a `source` provenance
    column (extra columns are ignored by the generator's DictReader consumers).
    The base source also donates its policy files and every other sheet the
    generator consumes (buildings, icons, wonders, tileimp, players, ...), so
    the merged dir is a complete, generatable control plane.

    advance_code_map.csv is rebuilt: base map first, then each source's
    code -> ADVANCE_<name> pairs derived from its advances.csv `code` column
    (both prereq and unit lanes). Collisions log and first-wins.

Usage:
    merge_control_planes.py --base <curated csv dir> \
        --source tag=<csv dir> [--source tag=<dir> ...] --out <dir>
        [--display-name "Super Magic"]

Failure modes:
    - SystemExit if base/source dirs or their advances/units csvs are missing.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import sys
from pathlib import Path

MERGE_DIMENSIONS = ("advances.csv", "units.csv", "improvements.csv")


def sanitize(name: str) -> str:
    """Identifier sanitizer — MUST match ctp2_generator.sanitize exactly."""
    s = name.upper().replace(" ", "_").replace("'", "").replace("-", "_")
    s = re.sub(r'[^A-Z0-9_]', '', s)
    return s


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        return list(reader.fieldnames or []), list(reader)


def write_rows(path: Path, header: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=header, lineterminator="\r\n",
                                extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"  wrote {path.name} ({len(rows)} rows)")


_NO_CODE = {"nil", "no", ""}

# Civ2 short codes are POSITIONAL — the same code means a different advance in
# every source. Namespace every non-base source's codes as "tag:code" (in the
# rows AND the code map) so cross-source prereq wiring is impossible.
_CODE_COLUMNS = {
    "advances.csv": ("code", "prereq1", "prereq2"),
    "units.csv": ("prereq",),
    "improvements.csv": ("prereq",),
}


def _namespace_codes(name: str, tag: str, row: dict[str, str]) -> None:
    for col in _CODE_COLUMNS.get(name, ()):
        val = (row.get(col) or "").strip()
        if val and val.lower() not in _NO_CODE:
            row[col] = f"{tag}:{val}"


def merge_dimension(name: str, ordered: list[tuple[str, Path]], out: Path,
                    ledger: list[list[str]]) -> None:
    header: list[str] = []
    merged: list[dict[str, str]] = []
    seen: dict[str, str] = {}
    for tag, src_dir in ordered:
        path = src_dir / name
        if not path.exists():
            continue
        hdr, rows = read_rows(path)
        if not header:
            header = hdr + (["source"] if "source" not in hdr else [])
        for row in rows:
            key = sanitize(row.get("name", ""))
            if not key:
                continue
            if key in seen:
                if seen[key] != tag:
                    print(f"    [collision] {name}: {row['name']!r} ({tag}) "
                          f"shadowed by {seen[key]}")
                    ledger.append([name, row["name"], seen[key], tag,
                                   (row.get("code") or row.get("prereq") or "").strip()])
                continue
            seen[key] = tag
            if tag != "base":
                _namespace_codes(name, tag, row)
            row.setdefault("source", tag)
            merged.append(row)
    write_rows(out / name, header, merged)


def merge_advance_code_maps(ordered: list[tuple[str, Path]], base: Path, out: Path,
                            ledger: list[list[str]]) -> None:
    rows: list[list[str]] = []
    claimed: dict[tuple[str, str], str] = {}

    def claim(lane: str, code: str, advance: str, tag: str) -> None:
        key = (lane, code)
        if key in claimed:
            if claimed[key] != advance:
                print(f"    [collision] code map {lane}:{code} kept {claimed[key]} "
                      f"(dropped {advance} from {tag})")
                ledger.append([f"advance_code_map:{lane}", claimed[key],
                               "(map)", tag, f"{code} -> {advance}"])
            return
        claimed[key] = advance
        rows.append([lane, code, advance])

    base_map = base / "advance_code_map.csv"
    if base_map.exists():
        _, base_rows = read_rows(base_map)
        for r in base_rows:
            claim(r["lane"], r["code"], r["advance"], "base")

    for tag, src_dir in ordered:
        adv = src_dir / "advances.csv"
        if not adv.exists():
            continue
        _, adv_rows = read_rows(adv)
        for r in adv_rows:
            code = (r.get("code") or "").split()[0] if r.get("code") else ""
            if not code:
                continue
            advance = f"ADVANCE_{sanitize(r['name'])}"
            claim("prereq", f"{tag}:{code}", advance, tag)
            claim("unit", f"{tag}:{code}", advance, tag)

    path = out / "advance_code_map.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, lineterminator="\r\n")
        writer.writerow(["lane", "code", "advance"])
        writer.writerows(rows)
    print(f"  wrote advance_code_map.csv ({len(rows)} rows)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True,
                        help="curated base csv dir (highest priority; donates policy + all other sheets)")
    parser.add_argument("--source", action="append", default=[],
                        metavar="TAG=DIR", help="additional source csv dir (ordered)")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--display-name", default=None,
                        help="override mod_policy.json mod_display_name")
    parser.add_argument("--policy-set", action="append", default=[],
                        metavar="KEY=JSON",
                        help="override a mod_policy.json key after the base "
                             "donation (value parsed as JSON; e.g. "
                             "sphere_home_exclusivity=true). Base donation "
                             "otherwise clobbers merged-mod policy flags on "
                             "every re-merge.")
    parser.add_argument("--mask", type=Path, default=None,
                        help="genre_mask.csv staging sheet; rows with mask=yes "
                             "are dropped from the merged dimensions")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if not (args.base / "advances.csv").exists():
        raise SystemExit(f"base {args.base} has no advances.csv")
    sources: list[tuple[str, Path]] = [("base", args.base)]
    for spec in args.source:
        tag, _, d = spec.partition("=")
        path = Path(d)
        if not (path / "advances.csv").exists():
            raise SystemExit(f"source {tag} ({path}) has no advances.csv")
        sources.append((tag, path))

    out = args.out
    if out.exists() and any(out.iterdir()) and not args.force:
        raise SystemExit(f"output dir {out} is not empty (use --force)")
    out.mkdir(parents=True, exist_ok=True)

    # 1. Base donates everything (policy files + every non-merged sheet).
    donated = 0
    for path in sorted(args.base.iterdir()):
        if path.is_file() and path.name not in MERGE_DIMENSIONS \
                and path.name != "advance_code_map.csv" \
                and not path.name.endswith((".xlsx", ".bak")) \
                and ".bak" not in path.name:
            shutil.copy2(path, out / path.name)
            donated += 1
    print(f"  donated {donated} base sheet/policy file(s)")

    # 2. Merge the roster dimensions. Every shadowed (dropped) row is recorded
    # in collision_ledger.csv so first-wins dedup stays auditable after the run.
    ledger: list[list[str]] = []
    for name in MERGE_DIMENSIONS:
        merge_dimension(name, sources, out, ledger)

    # 2b. Genre mask: drop rows the staging sheet flags mask=yes. Applied here
    # (post-merge, pre-generation) so out-of-genre cross-source content never
    # reaches the generator. The base (MoM) is never affected — its rows only
    # appear in the mask sheet if the user adds them.
    if args.mask and args.mask.exists():
        _, mask_rows = read_rows(args.mask)
        masked_ids = {r["id"] for r in mask_rows
                      if (r.get("mask") or "").strip().lower() == "yes"}
        if masked_ids:
            dropped_total = 0
            for name, prefix in (("units.csv", "UNIT_"),
                                 ("advances.csv", "ADVANCE_"),
                                 ("improvements.csv", "IMPROVE_")):
                path = out / name
                if not path.exists():
                    continue
                header, rows = read_rows(path)
                kept = [r for r in rows
                        if f"{prefix}{sanitize(r.get('name', ''))}" not in masked_ids]
                dropped = len(rows) - len(kept)
                if dropped:
                    write_rows(path, header, kept)
                    dropped_total += dropped
            print(f"  genre mask: dropped {dropped_total} out-of-genre row(s) "
                  f"({len(masked_ids)} ids flagged)")

    # 3. Rebuild the advance code map across all sources.
    merge_advance_code_maps(sources[1:], args.base, out, ledger)

    # 3b. Persist the collision ledger (staging-sheet pattern, like genre_mask).
    ledger_path = out / "collision_ledger.csv"
    with ledger_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, lineterminator="\r\n")
        writer.writerow(["dimension", "name", "kept_source", "dropped_source",
                         "dropped_code"])
        writer.writerows(ledger)
    print(f"  wrote collision_ledger.csv ({len(ledger)} dropped row(s))")

    # 4. Engine reserved-token guard: an identifier that equals a keyword in
    # the engine tokenizer (Token.cpp g_allTokens, e.g. UNIT_SPRITE from a unit
    # literally named "Sprite") makes StringDB lex it as a keyword instead of a
    # string id -> "Missing string id" -> the game EXITS at scenario load.
    # Fail here, at merge time, naming the row to rename.
    reserved_path = Path(__file__).parent / "engine_reserved_tokens.txt"
    if reserved_path.exists():
        reserved = set(reserved_path.read_text(encoding="utf-8").split())
        offenders = []
        for name, prefix in (("units.csv", "UNIT_"),
                             ("advances.csv", "ADVANCE_"),
                             ("improvements.csv", "IMPROVE_")):
            _, rows = read_rows(out / name)
            for row in rows:
                ident = f"{prefix}{sanitize(row.get('name', ''))}"
                if ident in reserved:
                    offenders.append(f"{name}: {row['name']!r} -> {ident} "
                                     f"(source {row.get('source', 'base')})")
        if offenders:
            for line in offenders:
                print(f"  [RESERVED-TOKEN] {line}")
            raise SystemExit(
                "merge refused: rename the offending rows — these identifiers "
                "are engine tokenizer keywords and crash the StringDB parse")

    # 5. Optional rebrand + policy overrides.
    if args.display_name or args.policy_set:
        pol_path = out / "mod_policy.json"
        policy = json.loads(pol_path.read_text(encoding="utf-8"))
        if args.display_name:
            policy["mod_display_name"] = args.display_name
            print(f"  mod_display_name -> {args.display_name!r}")
        for spec in args.policy_set:
            key, _, raw = spec.partition("=")
            policy[key] = json.loads(raw)
            print(f"  mod_policy: {key} -> {policy[key]!r}")
        pol_path.write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    sys.exit(main())
