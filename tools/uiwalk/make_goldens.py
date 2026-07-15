"""Render golden images for uiwalk asserts straight from the control plane.

Purpose: goldens derive from the contract (advances.csv cell_index over MOMJR
Improvements.bmp), not from blessed screenshots — the harness then closes the
loop contract -> expected pixels -> in-game pixels.

Preconditions: civ2_sprite_extractor.py importable from the parent tools dir;
Improvements.bmp reachable per its sprite_atlas_config.csv entry.

Failure modes: raises if a referenced cell is empty/out of range — that is a
contract violation worth failing loudly on.

Outputs: goldens/cell_<n>.png (160x120 canvas, BGR) for each distinct cell in
advances.csv, plus goldens/advance_map.json (advance display name -> golden id).
"""

import csv
import json
import sys
from pathlib import Path

import numpy as np
import cv2

TOOL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOL_DIR.parent))
from civ2_sprite_extractor import load_sheet_cells, is_cell_empty, _scale_rgba_to_canvas  # noqa: E402

GOLDENS = TOOL_DIR / "goldens"
ADVANCES_CSV = TOOL_DIR.parent / "momjr_csv" / "advances.csv"


def main():
    GOLDENS.mkdir(exist_ok=True)
    cells = load_sheet_cells("advances")
    rows = list(csv.DictReader(open(ADVANCES_CSV, encoding="utf-8-sig")))
    mapping = {}
    written = set()
    for r in rows:
        idx = int(r["cell_index"])
        golden_id = f"cell_{idx}"
        mapping[r["name"]] = golden_id
        if golden_id in written:
            continue
        if idx >= len(cells) or is_cell_empty(cells[idx]):
            raise ValueError(f"contract violation: cell {idx} ({r['name']}) empty or out of range")
        canvas = _scale_rgba_to_canvas(cells[idx], 160, 120)
        rgba = np.array(canvas)
        bgr = cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR)
        cv2.imwrite(str(GOLDENS / f"{golden_id}.png"), bgr)
        written.add(golden_id)
    (GOLDENS / "advance_map.json").write_text(json.dumps(mapping, indent=2))
    print(f"wrote {len(written)} cell goldens + advance_map.json ({len(mapping)} advances)")


if __name__ == "__main__":
    main()
