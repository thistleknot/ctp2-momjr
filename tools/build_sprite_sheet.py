#!/usr/bin/env python
"""build_sprite_sheet.py -- one RGBA sprite sheet + index for the whole roster.

Spec: specs/ctp2-sprites.spec.md (:Still-Picture:, :Background-Keying:).
Task: no ledger task; operator request 2026-09-05 -- a sprite sheet, with real
      transparency so it drops into paint.net / ComfyUI without a black box.

WHY A SHEET AND NOT 166 FILES
-----------------------------
A sheet is one thing to open, one thing to edit, one thing to paste. Cells are a
FIXED pitch on a regular grid, so any cell's pixel origin is arithmetic:

    x = col * cell_w        col = index %  cols
    y = row * cell_h        row = index // cols

`--index` writes that mapping out (csv + json) so edits can be sliced back apart
without eyeballing. Nothing is drawn into the cells -- no labels, no gridlines,
no padding tint -- because anything drawn is something you would have to erase.
Use `--labels` for a separate human-readable proof sheet.

TRANSPARENCY IS THE ENGINE'S KEY, NOT A THRESHOLD
-------------------------------------------------
Alpha comes from the border flood-fill in `build_sprites._key_background`, same
as export_transparent_png.py. A global "black is transparent" rule would punch
holes through the black armour, fur and wings that most of this roster is made
of. Consequence: a region fully ENCLOSED by art (the hole inside the Lamp's
handle) stays opaque, which is what the engine draws.

Usage:
    python build_sprite_sheet.py --out sheet.png --index
    python build_sprite_sheet.py --out sheet.png --family icon --scale 2
    python build_sprite_sheet.py --out sheet.png --from-dir .tmp/areanorm --labels
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_transparent_png import DEFAULT_PICS, to_rgba   # noqa: E402
from harmonize_unit_art import ident_of, select_files      # noqa: E402


def build(files, cols, scale, soft_edge):
    """Tile every unit at a fixed pitch. Returns (sheet, index rows)."""
    first = Image.open(files[0])
    cw, ch = first.width * scale, first.height * scale
    rows = (len(files) + cols - 1) // cols
    sheet = Image.new("RGBA", (cw * cols, ch * rows), (0, 0, 0, 0))
    index = []
    for i, f in enumerate(files):
        col, row = i % cols, i // cols
        rgba = to_rgba(Image.open(f), soft_edge)
        if scale > 1:
            rgba = rgba.resize((cw, ch), Image.NEAREST)
        x, y = col * cw, row * ch
        sheet.paste(rgba, (x, y))          # paste, not composite: keep exact alpha
        index.append({"index": i, "unit": ident_of(f.stem), "file": f.name,
                      "col": col, "row": row, "x": x, "y": y,
                      "w": cw, "h": ch})
    return sheet, index


def label_sheet(sheet, index, cw, ch):
    """A separate, opaque proof sheet -- never the deliverable itself."""
    out = Image.new("RGB", (sheet.width, sheet.height), (24, 24, 28))
    out.paste(sheet, (0, 0), sheet)
    d = ImageDraw.Draw(out)
    for e in index:
        d.rectangle([e["x"], e["y"], e["x"] + cw - 1, e["y"] + ch - 1],
                    outline=(70, 70, 84))
        d.text((e["x"] + 3, e["y"] + 3), e["unit"][:22], fill=(255, 220, 120))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--from-dir", type=Path, default=DEFAULT_PICS)
    ap.add_argument("--family", choices=["sprite", "icon", "both"], default="sprite")
    ap.add_argument("--cols", type=int, default=10)
    ap.add_argument("--scale", type=int, default=1)
    ap.add_argument("--soft-edge", type=float, default=0.0)
    ap.add_argument("--ext", default="tga",
                    help="source extension: tga for the shipped masters, png "
                         "for an exported transparent set")
    ap.add_argument("--index", action="store_true", help="write .csv and .json index")
    ap.add_argument("--labels", action="store_true", help="also write a labelled proof")
    args = ap.parse_args()

    files = select_files(args.from_dir, args.family, [], None, args.ext)
    if not files:
        print("FATAL: no source images matched", file=sys.stderr)
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)

    sheet, index = build(files, args.cols, args.scale, args.soft_edge)
    sheet.save(args.out)
    cw, ch = index[0]["w"], index[0]["h"]

    a = sheet.getchannel("A")
    clear = sum(1 for v in a.getdata() if v == 0) / (a.width * a.height)
    print(f"{len(files)} units -> {args.out}")
    print(f"  sheet {sheet.width}x{sheet.height}  grid {args.cols}x"
          f"{(len(files)+args.cols-1)//args.cols}  cell {cw}x{ch}  RGBA")
    print(f"  transparent: {clear:.0%} of the sheet")
    print(f"  slice: x = col*{cw}, y = row*{ch}")

    if args.index:
        stem = args.out.with_suffix("")
        with open(f"{stem}_index.csv", "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(index[0]))
            w.writeheader(); w.writerows(index)
        Path(f"{stem}_index.json").write_text(
            json.dumps({"cell_w": cw, "cell_h": ch, "cols": args.cols,
                        "cells": index}, indent=1), encoding="utf-8")
        print(f"  index -> {stem}_index.csv / .json")
    if args.labels:
        p = args.out.with_name(args.out.stem + "_labelled.png")
        label_sheet(sheet, index, cw, ch).save(p)
        print(f"  labelled proof -> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
