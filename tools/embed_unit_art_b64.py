"""embed_unit_art_b64.py -- append the unit's artwork to its caption row as base64.

Spec: no governing spec found. Basis: operator instruction 2026-09-06 -- "turn
      this csv into an excel file with the original artwork inserted into a
      row/column ... cast base64 images to tabular csv and append to the names
      (but normalize all unit sizes to a certain x X y), else use webp? ...
      once it's in this sparse format, we can then write a file just to
      transform it from this csv representation into a useful excel one".
      Promote to a REQ before anything depends on the output.

STEP 1 OF 2. This writes a self-contained CSV: every caption row gains the unit's
own artwork as a base64 payload, so the table carries its pixels with it and the
downstream Excel build needs no access to the TGA tree. Step 2 is csv_to_xlsx.py.

WHY NORMALISE WHEN THE SOURCES ARE ALREADY UNIFORM
Every SPRITE_*.tga measured 160x120, so the resize is a no-op today. It is done
anyway because the guarantee the spreadsheet needs is "every cell is the same
size" -- a single odd-sized master would otherwise silently produce one row of a
different height, and that is discovered visually, late, after the sheet is
built. Enforcing it here makes the property true by construction.

TRANSPARENCY IS PRESERVED; THE VIEWER PICKS THE BACKDROP
An earlier version flattened onto white and it was wrong: B3 is a white-and-
silver knight and B4 a white-and-cyan ice warrior, so their light pixels
vanished into the matte and read as holes punched in the figure. Flattening onto
black fails the same way for the roster's black armour and wings. No single
opaque matte suits art that spans both ends of the value range.

So the payload keeps its alpha channel and each consumer composites: the HTML
card has a mid-grey plate behind it, the spreadsheet flattens onto grey at build
time. `--matte` forces an opaque background when a downstream tool cannot handle
alpha.

The key itself comes from the border flood-fill, not a global black test -- a
global test punches holes in legitimately black interior art.

PNG vs WEBP: PNG is the default because openpyxl embeds it natively. WebP is
offered (--format webp) since the operator raised it -- it is roughly 3-4x
smaller, but Excel cannot display it, so it is only useful if the consumer is
something other than the xlsx builder.
"""
from __future__ import annotations

import argparse
import base64
import csv
import io
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from export_transparent_png import DEFAULT_PICS, to_rgba   # noqa: E402

# unit_art_prompts_units.csv is the maintained caption table (one row per unit,
# new units included). The older _v2 table predates CENTAUR_BOWMAN and
# MINOTAUR_BOWMAN, so a page built from it silently dropped both (2026-09-26).
DEFAULT_CSV = HERE / "momjr_csv" / "unit_art_prompts_units.csv"
DEFAULT_OUT = HERE / "momjr_csv" / "unit_art_prompts_units_with_art.csv"
CELL = (160, 120)
GREY = (110, 110, 118)          # the neutral both dark and light art read against

ART_COLS = ["art_w", "art_h", "art_format", "art_b64"]


def render(path: Path, cell: tuple[int, int], fmt: str,
           matte: tuple[int, int, int] | None = None) -> tuple[str, int, int]:
    """Keyed and normalised to `cell`, returned as base64.

    Alpha survives by default so the viewer chooses the backdrop. `matte`
    flattens onto an opaque colour for consumers that cannot handle alpha.
    """
    img = to_rgba(Image.open(path))
    if img.size != cell:
        # contain, never stretch -- aspect distortion would misrepresent the art
        c = img.copy()
        c.thumbnail(cell, Image.LANCZOS)
        img = Image.new("RGBA", cell, (0, 0, 0, 0))
        img.paste(c, ((cell[0] - c.width) // 2, (cell[1] - c.height) // 2))
    if matte is not None:
        flat = Image.new("RGB", img.size, matte)
        flat.paste(img, (0, 0), img)
        img = flat
    buf = io.BytesIO()
    img.save(buf, "WEBP" if fmt == "webp" else "PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii"), cell[0], cell[1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--pics", type=Path, default=Path(DEFAULT_PICS))
    ap.add_argument("--width", type=int, default=CELL[0])
    ap.add_argument("--height", type=int, default=CELL[1])
    ap.add_argument("--format", choices=("png", "webp"), default="png")
    ap.add_argument("--matte", choices=("none", "grey", "white", "black"),
                    default="none",
                    help="flatten onto an opaque colour; default keeps alpha")
    args = ap.parse_args()
    matte = {"none": None, "grey": GREY, "white": (255, 255, 255),
             "black": (0, 0, 0)}[args.matte]

    rows = list(csv.DictReader(open(args.csv, encoding="utf-8")))
    if not rows:
        print("empty csv", file=sys.stderr)
        return 2
    fields = [f for f in rows[0] if f not in ART_COLS] + ART_COLS
    cell = (args.width, args.height)

    ok = miss = 0
    total_b = 0
    for r in rows:
        src = args.pics / (r.get("file") or f"SPRITE_{r['ident']}.tga")
        if not src.exists():
            r.update(art_w="", art_h="", art_format="", art_b64="")
            miss += 1
            print(f"  MISSING {src.name}")
            continue
        b64, w, h = render(src, cell, args.format, matte)
        r.update(art_w=w, art_h=h, art_format=args.format, art_b64=b64)
        total_b += len(b64)
        ok += 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    print(f"{ok} rows with art, {miss} missing")
    print(f"normalised to {cell[0]}x{cell[1]} {args.format}, "
          f"{total_b/1e6:.1f} MB of base64")
    print(f"-> {args.out}  ({args.out.stat().st_size/1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
