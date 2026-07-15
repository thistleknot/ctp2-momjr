"""Render per-domain contact sheets of a mod's custom unit sprites.

Purpose:
    One labeled sheet per domain (Land / Sea / Air) showing every CUSTOM unit
    sprite (newsprite id >= MIN_CUSTOM_ID) as its source still, captioned with
    the unit name, stats, and Great-Library gameplay text. Written for the mom
    git repo but scenario-parameterized so it works for any generated scenario.

    Source art is the SPRITE_<X>.tga still each custom sprite is built from
    (build_sprites turns one still into a 5-facing move-only sprite), so no
    RLE SPR decode is needed — the still IS the creature art.

Usage:
    make_sprite_sheets.py --scenario <scen0000 dir> --csv <csv dir> \
        --out <output dir> [--min-custom-id 91]
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

DOMAIN_NAMES = {"0": "Land", "1": "Air", "2": "Sea"}
CELL_W, CELL_H = 210, 250
IMG_BOX = 128
COLS = 5
PAD = 12
BG = (26, 26, 30)
CARD = (42, 42, 50)
TEXT = (230, 230, 235)
SUB = (170, 175, 185)
CHECKER = ((60, 60, 68), (48, 48, 55))


def sanitize(name: str) -> str:
    s = name.upper().replace(" ", "_").replace("'", "").replace("-", "_")
    return re.sub(r"[^A-Z0-9_]", "", s)


def load_font(size: int, bold: bool = False):
    for name in (("arialbd.ttf" if bold else "arial.ttf"), "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def parse_gl_gameplay(scen: Path) -> dict[str, str]:
    """Parse [UNIT_X_GAMEPLAY] bracket sections -> {UNIT_X: text}."""
    path = scen / "english/gamedata/Great_Library.txt"
    out: dict[str, str] = {}
    if not path.exists():
        return out
    text = path.read_text(encoding="latin-1")
    for m in re.finditer(r"\[(UNIT_\w+)_GAMEPLAY\]\s*\n(.*?)(?=\n\[|\Z)",
                         text, re.S):
        out[m.group(1)] = " ".join(m.group(2).split())
    return out


def custom_sprite_ids(scen: Path, min_id: int) -> set[str]:
    path = scen / "default/gamedata/newsprite.txt"
    ids: set[str] = set()
    if not path.exists():
        return ids
    for line in path.read_text(encoding="latin-1").splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].isdigit() and int(parts[1]) >= min_id:
            ids.add(parts[0].upper())
    return ids


def checker(size: int) -> Image.Image:
    img = Image.new("RGB", (size, size), CHECKER[0])
    d = ImageDraw.Draw(img)
    step = 12
    for y in range(0, size, step):
        for x in range(0, size, step):
            if (x // step + y // step) % 2:
                d.rectangle([x, y, x + step, y + step], fill=CHECKER[1])
    return img


def render_cell(unit: dict, pics: Path, gl: dict, fonts) -> Image.Image:
    f_name, f_stat, f_desc = fonts
    cell = Image.new("RGB", (CELL_W, CELL_H), CARD)
    d = ImageDraw.Draw(cell)

    box = checker(IMG_BOX)
    tga = pics / f"{unit['sprite']}.tga"
    if tga.exists():
        try:
            art = Image.open(tga).convert("RGBA")
            art.thumbnail((IMG_BOX - 8, IMG_BOX - 8))
            box.paste(art, ((IMG_BOX - art.width) // 2,
                            (IMG_BOX - art.height) // 2), art)
        except Exception:
            pass
    cell.paste(box, ((CELL_W - IMG_BOX) // 2, 8))

    y = IMG_BOX + 14
    d.text((CELL_W // 2, y), unit["name"], font=f_name, fill=TEXT, anchor="ma")
    y += 20

    def _num(v: str) -> str:  # strip civ2 stat suffix letters ('6a' -> '6')
        return re.sub(r"[a-zA-Z]", "", str(v)) or "0"
    stat = (f"ATK {_num(unit['attack'])}  DEF {_num(unit['defense'])}  "
            f"HP {_num(unit['hp'])}  Cost {_num(unit['cost'])}")
    d.text((CELL_W // 2, y), stat, font=f_stat, fill=SUB, anchor="ma")
    y += 18
    uid = "UNIT_" + sanitize(unit["name"])
    desc = gl.get(uid, "")
    for ln in textwrap.wrap(desc, width=34)[:4]:
        d.text((CELL_W // 2, y), ln, font=f_desc, fill=SUB, anchor="ma")
        y += 13
    return cell


def render_sheet(units: list[dict], domain_label: str, pics: Path, gl: dict,
                 fonts) -> Image.Image:
    n = len(units)
    rows = (n + COLS - 1) // COLS
    title_h = 54
    W = COLS * CELL_W + (COLS + 1) * PAD
    H = title_h + rows * CELL_H + (rows + 1) * PAD
    sheet = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(sheet)
    d.text((PAD, 16), f"Master of Magic — {domain_label} units ({n})",
           font=fonts[0], fill=TEXT)
    for i, u in enumerate(units):
        r, c = divmod(i, COLS)
        x = PAD + c * (CELL_W + PAD)
        y = title_h + PAD + r * (CELL_H + PAD)
        sheet.paste(render_cell(u, pics, gl, fonts), (x, y))
    return sheet


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--min-custom-id", type=int, default=91)
    args = parser.parse_args()

    pics = args.scenario / "default/graphics/pictures"
    gl = parse_gl_gameplay(args.scenario)
    custom = custom_sprite_ids(args.scenario, args.min_custom_id)
    fonts = (load_font(15, bold=True), load_font(12), load_font(11))

    with (args.csv / "units.csv").open(newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))

    by_domain: dict[str, list[dict]] = {"0": [], "1": [], "2": []}
    for r in rows:
        sprite = (r.get("sprite") or "").strip().upper()
        if sprite in custom and r.get("domain", "0") in by_domain:
            by_domain[r["domain"]].append(r)

    args.out.mkdir(parents=True, exist_ok=True)
    total = 0
    for dom, units in by_domain.items():
        if not units:
            continue
        units.sort(key=lambda u: u["name"])
        label = DOMAIN_NAMES[dom]
        sheet = render_sheet(units, label, pics, gl, fonts)
        out = args.out / f"sprite_sheet_{label.lower()}.png"
        sheet.save(out)
        total += len(units)
        print(f"  wrote {out.name}: {len(units)} {label} sprite(s)")
    print(f"sprite sheets: {total} custom sprite(s) across "
          f"{sum(1 for u in by_domain.values() if u)} domain sheet(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
