#!/usr/bin/env python3
"""
Incremental unit-icon probe for silent-crash isolation.

Purpose:
    Patch only the image-file fields in scenario uniticon.txt for the first N
    generator-owned MoM units, leaving all non-image metadata untouched.
    This supports 1 -> 2 -> 4 -> 8 batch probing to isolate corrupt image
    payloads without hand-editing game data.

Usage:
    python Scenarios/mom/tools/unit_icon_batch_probe.py --status
    python Scenarios/mom/tools/unit_icon_batch_probe.py --count 1
    python Scenarios/mom/tools/unit_icon_batch_probe.py --count 2
    python Scenarios/mom/tools/unit_icon_batch_probe.py --restore

Preconditions:
    - Scenarios/mom/tools/momjr_csv/units.csv exists
    - Scenarios/mom/scen0000/default/gamedata/uniticon.txt exists
    - The workspace is a git repo with HEAD containing the blurred proxy baseline
    - Generated ICON_UNIT_*.tga files already exist in pictures dirs

Guarantees:
    - Every --count run starts from the committed HEAD baseline, not the previous patch
    - --restore restores the committed HEAD baseline
    - Only FirstFrame/Icon/LargeIcon/SmallIcon are changed for selected units

Failure modes:
    - Raises FileNotFoundError if uniticon.txt or units.csv is missing
    - Raises RuntimeError if git cannot supply the committed baseline
"""

from __future__ import annotations

import argparse
import csv
import re
import subprocess
from pathlib import Path

import ctp2_parser as P


ROOT = Path(r"H:\Program Files(x86)\Activision\Call To Power 2\Scenarios\mom")
TOOLS = ROOT / "tools"
CSV_PATH = TOOLS / "momjr_csv" / "units.csv"
UNITICON_PATH = ROOT / "scen0000" / "default" / "gamedata" / "uniticon.txt"
UNITICON_GIT_PATH = "Scenarios/mom/scen0000/default/gamedata/uniticon.txt"


def sanitize(name: str) -> str:
    s = name.upper().replace(" ", "_").replace("'", "").replace("-", "_")
    s = re.sub(r"[^A-Z0-9_]", "", s)
    return re.sub(r"_+", "_", s).strip("_")


def is_stub_unit(name: str) -> bool:
    if not name or name.lower() == "blah":
        return True
    if len(name) == 2 and name[0].upper() == "B" and name[1].isdigit():
        return True
    return False


def load_csv_units() -> list[tuple[str, str]]:
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"Missing units.csv: {CSV_PATH}")

    units: list[tuple[str, str]] = []
    with open(CSV_PATH, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            name = row["name"].strip()
            if is_stub_unit(name):
                continue
            units.append((name, f"ICON_UNIT_{sanitize(name)}"))
    return units


def ensure_inputs() -> None:
    if not UNITICON_PATH.exists():
        raise FileNotFoundError(f"Missing uniticon.txt: {UNITICON_PATH}")


def restore_head_baseline() -> None:
    ensure_inputs()
    proc = subprocess.run(
        ["git", "show", f"HEAD:{UNITICON_GIT_PATH}"],
        cwd=ROOT.parents[1],
        capture_output=True,
        text=True,
        encoding="latin-1",
        errors="replace",
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        message = proc.stderr.strip() or "git show returned no content"
        raise RuntimeError(f"Unable to restore committed uniticon baseline: {message}")
    UNITICON_PATH.write_text(proc.stdout.rstrip("\n") + "\n", encoding="latin-1")


def patch_batch(count: int) -> list[tuple[str, str]]:
    restore_head_baseline()

    units = load_csv_units()
    selected = units[:count]

    parser = P.CTP2BlockFile()
    parser.parse(UNITICON_PATH.read_text(encoding="latin-1"))

    for _, icon_id in selected:
        if icon_id not in parser.blocks:
            continue
        icon_tga = f'"{icon_id}.TGA"'
        entry = parser.blocks[icon_id]
        entry["FirstFrame"] = icon_tga
        entry["Icon"] = icon_tga
        entry["LargeIcon"] = icon_tga
        entry["SmallIcon"] = icon_tga

    UNITICON_PATH.write_text(parser.render() + "\n", encoding="latin-1")
    return selected


def main() -> None:
    ap = argparse.ArgumentParser(description="Patch uniticon image refs for the first N CSV-owned unit icons.")
    ap.add_argument("--count", type=int, help="Number of CSV units to patch from the start of units.csv")
    ap.add_argument("--restore", action="store_true", help="Restore uniticon.txt from the batch-probe backup")
    ap.add_argument("--status", action="store_true", help="Print CSV-owned unit icon order")
    args = ap.parse_args()

    if args.restore:
        restore_head_baseline()
        print(f"Restored {UNITICON_PATH} from committed HEAD baseline")
        return

    units = load_csv_units()
    if args.status or args.count is None:
        print(f"CSV-owned units: {len(units)}")
        for idx, (name, icon_id) in enumerate(units, start=1):
            print(f"{idx:02d}. {name} -> {icon_id}")
        return

    if args.count < 0:
        raise ValueError("--count must be >= 0")

    selected = patch_batch(args.count)
    print(f"Patched image refs for {len(selected)} unit icons")
    for idx, (name, icon_id) in enumerate(selected, start=1):
        print(f"{idx:02d}. {name} -> {icon_id}.TGA")


if __name__ == "__main__":
    main()
