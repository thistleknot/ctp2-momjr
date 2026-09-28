"""dimension_sheets.py -- one labelled image sheet per dimension: the art the mod ships.

NO GOVERNING SPEC. Basis: operator 2026-09-28 -- "include all sprite sheets top level
in the readme (whatever the mod uses for the final set of images per dimension top
level so users can see what images the game mod uses)". Promote to a REQ before this
is depended on.

Resolution follows the engine, not filenames:
  record (Units.txt UNIT_X) --DefaultIcon/Icon--> ICON_X block (uniticon.txt, or
  governicon.txt for governments) --Icon "file.tga"--> the image, looked up as a
  loose .tga in the scenario, then in the base game tree, then as a packed .rim in
  the base game's pic555.zfs archives (decoded here; see zfs_entries/decode_rim).
A name found nowhere is drawn as a labelled empty cell and counted. Placeholder art
(UPLG001.TGA, the engine's "no picture" tile) is drawn as itself and counted, so the
sheet shows which records have no art of their own.

Usage: python dimension_sheets.py [--out DIR]      (default: ../docs/img/sheets)
Writes <dimension>.png per dimension and prints a count table (markdown).
"""
from __future__ import annotations

import argparse
import re
import struct
from pathlib import Path

from PIL import Image, ImageDraw

import ctp2_parser as P

HERE = Path(__file__).resolve().parent
SCEN = HERE.parent / "scen0000" / "default"
BASE = HERE.parents[2] / "ctp2_data" / "default"
OUT = HERE.parent / "docs" / "img" / "sheets"
PLACEHOLDER = "uplg001.tga"

# dimension -> (record file, icon field, icon database)
DIMENSIONS = {
    "units": ("Units.txt", "DefaultIcon", "uniticon.txt"),
    "advances": ("Advance.txt", "Icon", "uniticon.txt"),
    "buildings": ("buildings.txt", "DefaultIcon", "uniticon.txt"),
    "wonders": ("Wonder.txt", "DefaultIcon", "uniticon.txt"),
    "governments": ("govern.txt", "Icon", "governicon.txt"),
    "terrain": ("terrain.txt", "Icon", "uniticon.txt"),
    "tile_improvements": ("tileimp.txt", "Icon", "uniticon.txt"),
}
CELL_W, CELL_H, LABEL, COLS = 160, 120, 14, 10
BG, CELL_BG, INK, DIM = (30, 32, 38), (96, 104, 88), (255, 226, 140), (150, 150, 160)


def records(text: str, field: str) -> list[tuple[str, str]]:
    """(record ident, icon key) for every top-level record, in file order.

    Depth-tracked line scan: records nest sub-blocks, so the first `}` after the
    opener is NOT the record's end (a non-greedy regex runs past it)."""
    out, depth, ident, icon = [], 0, None, None
    pat = re.compile(rf"^\s*{field}\s+(ICON_\w+)")
    for line in text.splitlines():
        line = line.split("//", 1)[0]
        if depth == 0:
            m = re.match(r"^\s*([A-Z][A-Z0-9_]*)\s*\{", line)
            if m:
                ident, icon = m.group(1), None
        elif depth == 1 and icon is None:
            m = pat.match(line)
            if m:
                icon = m.group(1)
        depth += line.count("{") - line.count("}")
        if depth == 0 and ident:
            if icon:
                out.append((ident, icon))
            ident = None
    return out


def icon_files(db: str) -> dict[str, str]:
    """ICON_X -> image filename, scenario blocks winning over base blocks."""
    got: dict[str, str] = {}
    for root in (BASE, SCEN):
        path = root / "gamedata" / db
        if not path.exists():
            continue
        f = P.CTP2BlockFile()
        f.parse(path.read_text(encoding="latin-1"))
        for key, fields in f.blocks.items():
            name = fields.get("Icon", "").strip('"')
            if name and name.upper() != "NULL":
                got[key] = name
    return got


def loose_index() -> dict[str, Path]:
    """lowercase filename -> loose .tga; the scenario shadows the base tree.

    Top level of each pictures folder ONLY, as the engine reads it: a recursive
    search let _art_backup/ and _icon_backup/ copies shadow the live art, and the
    first units sheet showed the retired wolf ORC and boar GOBLIN (2026-09-28)."""
    idx: dict[str, Path] = {}
    for root in (BASE / "graphics" / "pictures", SCEN / "graphics" / "pictures"):
        if root.exists():
            for p in root.glob("*"):
                if p.suffix.lower() == ".tga":
                    idx[p.name.lower()] = p
    return idx


def zfs_entries(archive: Path) -> dict[str, tuple[int, int]]:
    """name.tga (lowercase) -> (offset, size) for every .rim in one ZFS3 archive.

    Layout (read off pic555.zfs, 2026-09-28): header 'ZFS3', u32 version, u32 name
    length (16), u32 entries per block (100), u32 count, u32 0, u32 first block.
    A block is u32 next-block offset + entries of name[16], u32 offset, u32 id,
    u32 size, u32 time, u32 flags. A text search for the name is NOT a lookup --
    stray copies of names occur outside the directory."""
    b = archive.read_bytes()
    if b[:4] != b"ZFS3":
        return {}
    _v, nlen, per, count, _z, block = struct.unpack_from("<6I", b, 4)
    out: dict[str, tuple[int, int]] = {}
    esz = nlen + 20
    while block and len(out) < count:
        nxt = struct.unpack_from("<I", b, block)[0]
        for k in range(per):
            p = block + 4 + k * esz
            name = b[p:p + nlen].split(b"\0", 1)[0].decode("latin-1").lower()
            if not name:
                continue
            off, _id, size, _t, _f = struct.unpack_from("<5I", b, p + nlen)
            if name.endswith(".rim"):
                out.setdefault(name[:-4] + ".tga", (off, size))
        block = nxt
    return out


def decode_rim(blob: bytes) -> Image.Image:
    """RIMF: 'RIMF', u32 version, u16 width, u16 height, u16 pitch, u16 pad, then
    16-bit RGB555 rows (pic555); magenta 0x7C1F is the engine's transparent key."""
    assert blob[:4] == b"RIMF", "not a RIM image"
    w, h, pitch = struct.unpack_from("<3H", blob, 8)
    im = Image.new("RGBA", (w, h))
    px = im.load()
    for y in range(h):
        row = 16 + y * pitch
        for x in range(w):
            v = struct.unpack_from("<H", blob, row + 2 * x)[0]
            r, g, bl = (v >> 10) & 31, (v >> 5) & 31, v & 31
            px[x, y] = (r << 3 | r >> 2, g << 3 | g >> 2, bl << 3 | bl >> 2,
                        0 if v == 0x7C1F else 255)
    return im


def packed_index() -> dict[str, tuple[Path, int, int]]:
    """name.tga -> (archive, offset, size) across the base game's 555 archives."""
    idx: dict[str, tuple[Path, int, int]] = {}
    for lang in ("default", "english"):
        arc = BASE.parent / lang / "graphics" / "pictures" / "pic555.zfs"
        if arc.exists():
            for name, (off, size) in zfs_entries(arc).items():
                idx.setdefault(name, (arc, off, size))
    return idx


Source = Path | tuple[Path, int, int] | None      # loose file, packed entry, or absent


def resolve(dim: str, idx: dict[str, Path],
            packed: dict[str, tuple[Path, int, int]] | None = None) -> list[tuple[str, str, Source]]:
    """(label, image filename, source) per record of one dimension; loose wins over packed."""
    packed = packed or {}
    rec_file, field, db = DIMENSIONS[dim]
    path = SCEN / "gamedata" / rec_file
    if not path.exists():
        path = BASE / "gamedata" / rec_file
    icons = icon_files(db)
    rows = []
    for ident, key in records(path.read_text(encoding="latin-1"), field):
        name = icons.get(key, "")
        label = re.sub(r"^(UNIT|ADVANCE|IMPROVE|WONDER|GOVERNMENT|TERRAIN|TILEIMP)_", "", ident)
        src = (idx.get(name.lower()) or packed.get(name.lower())) if name else None
        rows.append((label, name, src))
    return rows


def load(src: Source) -> Image.Image | None:
    if src is None:
        return None
    if isinstance(src, tuple):
        arc, off, size = src
        with open(arc, "rb") as fh:
            fh.seek(off)
            return decode_rim(fh.read(size))
    return Image.open(src).convert("RGBA")


def draw(rows: list[tuple[str, str, Source]], out: Path) -> None:
    nrows = max(1, (len(rows) + COLS - 1) // COLS)
    sheet = Image.new("RGB", (COLS * CELL_W, nrows * (CELL_H + LABEL)), BG)
    d = ImageDraw.Draw(sheet)
    for i, (label, name, src) in enumerate(rows):
        x, y = (i % COLS) * CELL_W, (i // COLS) * (CELL_H + LABEL)
        d.text((x + 3, y + 1), label[:24], fill=INK)
        cell = Image.new("RGB", (CELL_W - 4, CELL_H - 4), CELL_BG)
        im = load(src)
        if im is not None:
            im.thumbnail(cell.size, Image.NEAREST)
            cell.paste(im, ((cell.width - im.width) // 2, (cell.height - im.height) // 2), im)
        else:
            ImageDraw.Draw(cell).text((6, cell.height // 2 - 6),
                                      f"missing {name}" if name else "no icon", fill=DIM)
        sheet.paste(cell, (x + 2, y + LABEL + 2))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args()
    idx, packed = loose_index(), packed_index()
    print("| Dimension | Records | Mod's own art | Stock game art | No picture (placeholder) | Missing |")
    print("|---|---:|---:|---:|---:|---:|")
    for dim in DIMENSIONS:
        rows = resolve(dim, idx, packed)
        draw(rows, a.out / f"{dim}.png")
        ph = sum(1 for _, n, _ in rows if n.lower() == PLACEHOLDER)
        rest = [s for _, n, s in rows if n.lower() != PLACEHOLDER]
        own = sum(1 for s in rest if isinstance(s, Path) and SCEN in s.parents)
        missing = sum(1 for s in rest if s is None)
        stock = len(rest) - own - missing
        print(f"| {dim} | {len(rows)} | {own} | {stock} | {ph} | {missing} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
