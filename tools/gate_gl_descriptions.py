"""Gate: every live element has a real GAMEPLAY and HISTORICAL Great Library article.

Thesis
------
An element with a stub article looks fine in every automated check -- the file
parses, the section exists, the game loads -- and is only visible by opening the
Great Library and reading a blank panel. That is exactly the class of defect a
gate exists for.

Run after ctp2_generator.py. Exit 0 when clean, 1 with the offending list.

    python tools/gate_gl_descriptions.py
    python tools/gate_gl_descriptions.py --scenario <dir> --ctp2-data <dir>
    python tools/gate_gl_descriptions.py --list-missing   # csv rows to author

'Missing' is defined by gl_descriptions.is_filler, the same predicate the writer
uses, so the gate and the generator can never disagree about what counts.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import gl_descriptions as G  # noqa: E402

DEFAULT_SCENARIO = Path(os.environ.get(
    "CTP2_GENERATOR_SCENARIO_DIR",
    r"H:\Program Files(x86)\Activision\Call To Power 2\Scenarios\mom\scen0000"))
DEFAULT_CTP2_DATA = Path(os.environ.get(
    "CTP2_GENERATOR_CTP2_DATA_DIR",
    r"H:\Program Files(x86)\Activision\Call To Power 2\ctp2_data"))
DEFAULT_CSV = Path(os.environ.get(
    "CTP2_GENERATOR_CSV_DIR", str(Path(__file__).parent / "momjr_csv")))

SECTIONS = ("GAMEPLAY", "HISTORICAL")


def parse_library(path: Path) -> dict:
    """Great_Library.txt -> {section_id: body}."""
    import re
    if not path.is_file():
        return {}
    text = path.read_text(encoding="latin-1")
    out, cur, buf = {}, None, []
    for line in text.splitlines():
        m = re.match(r"^\[([A-Z0-9_]+)\]\s*$", line)
        if m:
            if cur:
                out[cur] = "\n".join(buf).strip()
            cur, buf = m.group(1), []
        elif cur is not None:
            buf.append(line)
    if cur:
        out[cur] = "\n".join(buf).strip()
    return out


def audit(scenario: Path, ctp2_data: Path, csv_dir: Path):
    def load_text(rel):
        for base in (scenario, ctp2_data):
            p = base / rel
            if p.is_file():
                return p.read_text(encoding="latin-1")
        return None

    library = parse_library(scenario / "english/gamedata/Great_Library.txt")
    live = G.collect_elements(load_text)

    # Authored-only dimensions (concepts, orders, terrain) have no DB file to
    # enumerate; take their element list from the articles that already exist.
    for prefix, (dimension, rel, _db) in G.DIMENSIONS.items():
        if rel is not None:
            continue
        idents = {k.rsplit("_", 1)[0] for k in library
                  if k.startswith(prefix) and k.rsplit("_", 1)[-1] in SECTIONS}
        if idents:
            live.setdefault(dimension, (prefix, {i: "" for i in idents}))

    missing = defaultdict(list)
    total = 0
    for dimension, (_prefix, blocks) in live.items():
        for ident in blocks:
            for suffix in SECTIONS:
                total += 1
                if G.is_filler(library.get(f"{ident}_{suffix}", "")):
                    missing[dimension].append((ident, suffix))
    return live, missing, total


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", type=Path, default=DEFAULT_SCENARIO)
    ap.add_argument("--ctp2-data", type=Path, default=DEFAULT_CTP2_DATA)
    ap.add_argument("--csv-dir", type=Path, default=DEFAULT_CSV)
    ap.add_argument("--list-missing", action="store_true",
                    help="emit gl_descriptions.csv rows for what is missing")
    args = ap.parse_args()

    live, missing, total = audit(args.scenario, args.ctp2_data, args.csv_dir)
    n = sum(len(v) for v in missing.values())

    if args.list_missing:
        w = csv.writer(sys.stdout, lineterminator="\n")
        w.writerow(["element", "gameplay", "historical"])
        for dimension in sorted(missing):
            for ident, _suffix in sorted(set(missing[dimension])):
                w.writerow([ident, "", ""])
        return 0

    print(f"GL description gate: {total - n}/{total} sections have real prose")
    for dimension in sorted(missing, key=lambda d: -len(missing[d])):
        rows = missing[dimension]
        print(f"  {dimension:12s} {len(rows):4d} missing "
              f"(of {len(live[dimension][1]) * len(SECTIONS)})")
        for ident, suffix in sorted(rows)[:8]:
            print(f"      {ident}_{suffix}")
        if len(rows) > 8:
            print(f"      ... and {len(rows) - 8} more")

    if n:
        print(f"\nFAIL: {n} section(s) still stubbed. "
              f"Author them in {args.csv_dir / G.CSV_NAME}.")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
