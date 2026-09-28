"""spritesheet.py -- all unit masters on ONE full-resolution PNG, and back again.

NO GOVERNING SPEC. Basis: operator 2026-09-27 -- "is there a way I can get the full
resolution so I can hand clean these and hand them back to you for reincorporation
as master. It would be nice if I had a single spritesheet with a cross section grid".

  export [--out PNG]    every SPRITE_<unit>.tga master at 160x120 in a 10-column grid,
                        background transparent (the black key becomes alpha 0),
                        cells separated by a 1-px magenta line. Writes a sidecar
                        <PNG>.json naming the unit in every cell.
  import PNG [--apply] [--only UNIT ...]
                        cut the (cleaned) sheet along the same grid and write each
                        cell back as SPRITE_ and ICON_UNIT_<unit>.tga. Transparent
                        pixels become the key; opaque art is floored off pure black
                        (install_crafted_art.to_master). Backups as .bak-<stamp>.
                        Dry run unless --apply. Cells identical to the current
                        master are skipped.

Cleaning rules for the operator: keep each unit inside its cell (the magenta lines
are outside the cells and are ignored); erase to TRANSPARENT, never to black.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import install_crafted_art as I                    # noqa: E402
from export_transparent_png import DEFAULT_PICS    # noqa: E402

W, H = I.W, I.H
COLS = 10
LINE = (255, 0, 255, 255)
DEFAULT_OUT = HERE.parent / "exports" / "mom_units_masters_sheet.png"


def cell_box(i: int) -> tuple[int, int, int, int]:
    """Pixel box of cell i: 1-px grid line before every row and column."""
    c, r = i % COLS, i // COLS
    x, y = 1 + c * (W + 1), 1 + r * (H + 1)
    return x, y, x + W, y + H


def master_rgba(tga: Path) -> Image.Image:
    """Master -> RGBA: exactly the key colour (0,0,0) becomes transparent."""
    im = Image.open(tga).convert("RGBA")
    px = im.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, _ = px[x, y]
            if (r, g, b) == (0, 0, 0):
                px[x, y] = (0, 0, 0, 0)
    return im


def export(units: list[str], pics: Path, out: Path) -> Image.Image:
    rows = (len(units) + COLS - 1) // COLS
    sheet = Image.new("RGBA", (COLS * (W + 1) + 1, rows * (H + 1) + 1), (0, 0, 0, 0))
    d = ImageDraw.Draw(sheet)
    for c in range(COLS + 1):
        d.line((c * (W + 1), 0, c * (W + 1), sheet.height - 1), fill=LINE)
    for r in range(rows + 1):
        d.line((0, r * (H + 1), sheet.width - 1, r * (H + 1)), fill=LINE)
    for i, u in enumerate(units):
        x0, y0, _, _ = cell_box(i)
        sheet.paste(master_rgba(pics / f"SPRITE_{u}.tga"), (x0, y0))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    # The untouched export is kept as the BASELINE: import takes only cells the
    # operator changed relative to it, so an older sheet cannot revert units that
    # were updated after it was exported (14 units, 2026-09-27).
    sheet.save(baseline_of(out))
    out.with_suffix(".json").write_text(json.dumps(
        {"cell": [W, H], "cols": COLS, "grid_px": 1, "units": units}, indent=1),
        encoding="utf-8")
    return sheet


def baseline_of(png: Path) -> Path:
    return png.with_name(png.stem + ".baseline.png")


def import_sheet(png: Path, pics: Path, apply: bool, only: set[str] | None = None) -> list[str]:
    """Write back ONLY the cells the operator edited (differ from the export baseline)."""
    meta = json.loads(png.with_suffix(".json").read_text(encoding="utf-8"))
    assert meta["cell"] == [W, H] and meta["cols"] == COLS, "sheet layout changed"
    # Operator 2026-09-28: "be sure that the spritesheet is for units". Every cell
    # must name a unit in the roster, and the image must be exactly that grid --
    # an advance/wonder/terrain sheet, or a resized one, is refused before any write.
    strangers = [u for u in meta["units"] if u not in set(roster())]
    if strangers:
        raise ValueError(f"not a unit spritesheet: {strangers[:5]} are not units")
    sheet = Image.open(png).convert("RGBA")
    rows = (len(meta["units"]) + COLS - 1) // COLS
    want = (COLS * (W + 1) + 1, rows * (H + 1) + 1)     # 1-px grid, as cell_box
    if sheet.size != want:
        raise ValueError(f"sheet is {sheet.size[0]}x{sheet.size[1]}, a unit sheet of "
                         f"{len(meta['units'])} is {want[0]}x{want[1]}")
    base_path = baseline_of(png)
    assert base_path.exists(), f"no export baseline {base_path.name}; re-export first"
    base = Image.open(base_path).convert("RGBA")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    changed = []
    with tempfile.TemporaryDirectory() as td:
        for i, u in enumerate(meta["units"]):
            if only and u not in only:
                continue
            cell = sheet.crop(cell_box(i))
            if cell.tobytes() == base.crop(cell_box(i)).tobytes():
                continue                      # operator did not touch this cell
            tmp = Path(td) / f"{u}.png"
            cell.save(tmp)
            new = I.to_master(tmp, normalize=False)
            dst = pics / f"SPRITE_{u}.tga"
            probe = Path(td) / f"{u}.tga"
            I.write_tga(probe, new)          # compare the exact bytes that would ship
            if dst.exists() and probe.read_bytes() == dst.read_bytes():
                continue
            changed.append(u)
            if apply:
                for d in (dst, pics / f"ICON_UNIT_{u}.tga"):
                    if d.exists():
                        shutil.copy2(d, d.with_suffix(f".tga.bak-{stamp}"))
                    I.write_tga(d, new)
    return changed


def roster() -> list[str]:
    import csv
    rows = csv.DictReader(open(HERE / "momjr_csv" / "unit_art_prompts_units.csv",
                               encoding="utf-8"))
    return sorted(r["ident"] for r in rows
                  if not (len(r["ident"]) == 2 and r["ident"][0] == "B"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("--out", type=Path, default=DEFAULT_OUT)
    im = sub.add_parser("import")
    im.add_argument("png", type=Path)
    im.add_argument("--apply", action="store_true")
    im.add_argument("--only", nargs="*")
    ap.add_argument("--pics", type=Path, default=Path(DEFAULT_PICS))
    a = ap.parse_args()
    if a.cmd == "export":
        s = export(roster(), a.pics, a.out)
        print(f"{a.out}  {s.size[0]}x{s.size[1]}  ({len(roster())} units, index {a.out.with_suffix('.json').name})")
        return 0
    changed = import_sheet(a.png, a.pics, a.apply, set(a.only) if a.only else None)
    print(f"{len(changed)} unit(s) differ from the current masters: {' '.join(changed) or '-'}")
    print("written (backups .bak-<stamp>); run build_sprites.py next" if a.apply and changed
          else "dry run -- re-run with --apply to write" if changed else "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
