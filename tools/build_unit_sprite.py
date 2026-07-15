"""
build_unit_sprite.py — Build ONE static unit sprite (GU###.SPR) from a TGA.

The distinct, general-purpose form of the pipeline proven on the Peasants
fix (2026-07-03, in-game confirmed): corner-sampled background keying,
isolated-speck removal, one image cast across all 5 facings (the engine
mirrors the other 3 directions), compiled by makespr.py — which is
byte-for-byte identical to Activision's makespr.exe (see
golden_test_makespr.py).

Usage:
    python Scenarios\\mom\\tools\\build_unit_sprite.py --sprite-id 104 \\
        --source Scenarios\\mom\\...\\ICON_UNIT_PEASANTS.tga
    Options:
        --tolerance N    Manhattan-distance background keying (default 12)
        --min-island N   drop opaque islands smaller than N px (default 20)
        --out-dir DIR    sprites dir (default ctp2_data\\...\\sprites)
        --dry-run        show plan, write nothing

Wiring reminder (this tool builds the SPR only):
    Units.txt: DefaultSprite SPRITE_X  ->  newsprite.txt: SPRITE_X ###
    ->  GU###.SPR (engine tries 3-digit GU0##.SPR first, then GU##.SPR).
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("Pillow required: pip install Pillow")

_CTP2_ROOT   = Path(__file__).resolve().parent.parent.parent.parent
_SPRITES_DIR = _CTP2_ROOT / "ctp2_data" / "default" / "graphics" / "sprites"
_MAKESPR     = _CTP2_ROOT / "makespr.py"

SPRITE_WIDTH  = 96
SPRITE_HEIGHT = 72
N_FACINGS     = 5

# Canonical static-unit script (GU00.txt template shape). ANIM_TRANSPARENCIES
# 0 is a FLAG ("no explicit list"); makespr.py pads omitted entries with 15
# (opaque). 0 in the transparency VALUES would mean invisible.
#
# HOT POINTS: the engine draw anchor (drawX -= hotX*scale, drawY -= hotY*scale;
# larger hotY draws the sprite HIGHER, smaller hotX draws it further RIGHT).
# A static sprite reuses one image for all 5 facings, so all five hot points
# must be IDENTICAL or the unit visibly jumps when its facing changes. (The
# GU00 tutorial values were the Cow's per-facing anchors — wrong for statics.)
_GU_SCRIPT = """\
0

UNIT_SPRITE
{{
    UNIT_SPRITE_MOVE    1
    {{
        SPRITE_NUM_FRAMES    1
        SPRITE_FIRST_FRAME   0
        SPRITE_WIDTH         {w}
        SPRITE_HEIGHT        {h}
        SPRITE_HOT_POINTS
            {hx} {hy}
            {hx} {hy}
            {hx} {hy}
            {hx} {hy}
            {hx} {hy}
    }}

    ANIM    1
    {{
        ANIM_TYPE            1
        ANIM_NUM_FRAMES      1
        ANIM_PLAYBACK_TIME   1000
        ANIM_DELAY           0
        ANIM_FRAME_DATA      0
        ANIM_MOVE_DELTAS     0
        ANIM_TRANSPARENCIES  0
    }}

    UNIT_SPRITE_ATTACK          0
    UNIT_SPRITE_IDLE            0
    UNIT_SPRITE_VICTORY         0
    UNIT_SPRITE_WORK            0
    UNIT_SPRITE_FIREPOINTS      0
    UNIT_SPRITE_FIREPOINTS_WORK 0
    UNIT_SPRITE_MOVEOFFSETS     0
    UNIT_SPRITE_SHIELDPOINTS    0
}}
"""


# ── Keying helpers ─────────────────────────────────────────────────────────────

def corner_bg(img: Image.Image) -> tuple[int, int, int]:
    """Average colour of the four 3x3 corner patches = background colour."""
    w, h = img.size
    samples: list[tuple[int, int, int]] = []
    for xs in (range(min(3, w)), range(max(0, w - 3), w)):
        for ys in (range(min(3, h)), range(max(0, h - 3), h)):
            for x in xs:
                for y in ys:
                    r, g, b, *_ = img.getpixel((x, y))
                    samples.append((r, g, b))
    n = len(samples) or 1
    return (sum(s[0] for s in samples) // n,
            sum(s[1] for s in samples) // n,
            sum(s[2] for s in samples) // n)


def remove_islands(px, width: int, height: int, min_size: int) -> int:
    """
    Key out opaque connected components smaller than min_size pixels
    (8-connectivity). Catches bright specks (star-field stars etc.) that
    colour-distance keying cannot, because they are far from the sampled
    background colour. Returns pixels removed.
    """
    seen = [[False] * width for _ in range(height)]
    removed = 0
    for sy in range(height):
        for sx in range(width):
            if seen[sy][sx] or px[sx, sy][3] == 0:
                continue
            comp = [(sx, sy)]
            seen[sy][sx] = True
            i = 0
            while i < len(comp):
                cx, cy = comp[i]
                i += 1
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        nx, ny = cx + dx, cy + dy
                        if (0 <= nx < width and 0 <= ny < height
                                and not seen[ny][nx] and px[nx, ny][3] != 0):
                            seen[ny][nx] = True
                            comp.append((nx, ny))
            if len(comp) < min_size:
                for cx, cy in comp:
                    px[cx, cy] = (0, 0, 0, 0)
                removed += len(comp)
    return removed


def make_facing_tifs(tga: Path, work_dir: Path, sprite_id: int,
                     tolerance: int, min_island: int) -> int:
    """
    TGA -> 96x72, key background (Manhattan <= tolerance from corner sample),
    drop speck islands, force figure opaque, write the same image as all
    5 facing TIFs. Returns figure pixel count.
    """
    img = Image.open(str(tga)).convert("RGBA").resize(
        (SPRITE_WIDTH, SPRITE_HEIGHT), Image.LANCZOS
    )
    bg = corner_bg(img)
    print(f"  Background colour (corner sample): {bg}")

    px = img.load()
    for y in range(SPRITE_HEIGHT):
        for x in range(SPRITE_WIDTH):
            r, g, b, a = px[x, y]
            if abs(r - bg[0]) + abs(g - bg[1]) + abs(b - bg[2]) <= tolerance:
                px[x, y] = (0, 0, 0, 0)
            else:
                px[x, y] = (r, g, b, 255)

    specks = remove_islands(px, SPRITE_WIDTH, SPRITE_HEIGHT, min_island)
    if specks:
        print(f"  Removed {specks} isolated speck pixels (<{min_island} px islands)")

    # Figure bounding box in the 96x72 frame — drives the auto hot point so
    # every unit gets the same on-tile placement as the golden peasant.
    xs = [x for y in range(SPRITE_HEIGHT) for x in range(SPRITE_WIDTH) if px[x, y][3] != 0]
    ys = [y for y in range(SPRITE_HEIGHT) for x in range(SPRITE_WIDTH) if px[x, y][3] != 0]
    fig = len(xs)
    bbox = (min(xs), min(ys), max(xs), max(ys)) if xs else (0, 0, 0, 0)

    facing_dir = work_dir / str(sprite_id)
    facing_dir.mkdir(exist_ok=True)
    nn = f"{sprite_id:02d}"
    for f in range(1, N_FACINGS + 1):
        img.save(str(facing_dir / f"GU{nn}MA{f}.0.TIF"), format="TIFF")
    return fig, bbox


# Golden peasant relationship (GU104): hot_x == figure horizontal centre,
# hot_y == feet_y - FEET_TO_HOTPOINT. CTP2 anchors a unit at its lower shin,
# not its feet, so the figure straddles the tile diamond correctly.
FEET_TO_HOTPOINT = 16


def hotpoint_from_bbox(bbox: "tuple[int,int,int,int]") -> "tuple[int,int]":
    """Derive the uniform draw anchor from a figure bbox (min_x,min_y,max_x,max_y)."""
    min_x, _min_y, max_x, max_y = bbox
    hot_x = (min_x + max_x) // 2
    hot_y = max(1, max_y - FEET_TO_HOTPOINT)
    return hot_x, hot_y


# ── Build ──────────────────────────────────────────────────────────────────────

def build_sprite(sprite_id: int, source: Path, out_dir: Path,
                 tolerance: int = 12, min_island: int = 20,
                 dry_run: bool = False,
                 hot_x: "int | None" = None, hot_y: "int | None" = None) -> Path | None:
    """Build GU{id}.SPR from source TGA into out_dir. Returns output path.

    hot_x / hot_y default to None = AUTO: derived from the figure's geometry
    (centre-x, feet-16) so every unit lands on the tile like the golden
    peasant. Pass explicit ints only to override for a specific unit.
    """
    nn = f"{sprite_id:02d}"
    out_spr = out_dir / f"GU{nn}.SPR"
    print(f"Source TGA : {source}  ({source.stat().st_size:,} bytes)")
    print(f"Output SPR : {out_spr}")
    print(f"BG tolerance: Manhattan <= {tolerance}; min island {min_island}px")
    if dry_run:
        print("[dry-run] No files written.")
        return None

    with tempfile.TemporaryDirectory(prefix=f"gu{nn}_") as tmp:
        work = Path(tmp)
        print(f"\nStep 1: TGA -> {N_FACINGS} facing TIFs")
        fig, bbox = make_facing_tifs(source, work, sprite_id, tolerance, min_island)
        print(f"  Figure pixels: {fig} of {SPRITE_WIDTH * SPRITE_HEIGHT}; bbox {bbox}")
        if fig < 10:
            print("  [WARN] Very few figure pixels — source may be a placeholder;"
                  " the SPR will likely be blank.")

        auto_x, auto_y = hotpoint_from_bbox(bbox)
        eff_x = auto_x if hot_x is None else hot_x
        eff_y = auto_y if hot_y is None else hot_y
        print(f"  Hot point: ({eff_x},{eff_y})  "
              f"[{'auto from figure' if hot_x is None and hot_y is None else 'manual override'}]")

        print(f"\nStep 2: Write GU{nn}.TXT + run makespr.py -u {sprite_id}")
        (work / f"GU{nn}.TXT").write_text(
            _GU_SCRIPT.format(w=SPRITE_WIDTH, h=SPRITE_HEIGHT,
                              hx=eff_x, hy=eff_y), encoding="latin-1")
        r = subprocess.run([sys.executable, str(_MAKESPR), "-u", str(sprite_id)],
                           cwd=str(work), capture_output=True, text=True)
        if r.stdout.strip():
            print("  " + r.stdout.strip().replace("\n", "\n  "))
        if r.returncode != 0:
            print(f"  [ERROR] makespr.py failed (exit {r.returncode}): "
                  f"{r.stderr.strip()}")
            return None
        spr_tmp = work / f"GU{nn}.SPR"
        if not spr_tmp.exists():
            print("  [ERROR] makespr.py produced no SPR")
            return None

        print("\nStep 3: Install")
        shutil.copy2(str(spr_tmp), str(out_spr))
        print(f"  Written: {out_spr}  ({out_spr.stat().st_size:,} bytes)")
    return out_spr


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--sprite-id", type=int, required=True,
                    help="numeric sprite id from newsprite.txt (e.g. 104)")
    ap.add_argument("--source", type=Path, required=True,
                    help="source TGA (centred art on a plain background)")
    ap.add_argument("--tolerance", type=int, default=12)
    ap.add_argument("--min-island", type=int, default=20)
    ap.add_argument("--out-dir", type=Path, default=_SPRITES_DIR)
    ap.add_argument("--hot-x", type=int, default=None,
                    help="override draw anchor x (default AUTO = figure centre); "
                         "SMALLER draws the unit further RIGHT")
    ap.add_argument("--hot-y", type=int, default=None,
                    help="override draw anchor y (default AUTO = feet-16); "
                         "LARGER draws the unit HIGHER")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    for p, label in ((args.source, "source TGA"), (_MAKESPR, "makespr.py"),
                     (args.out_dir, "sprites directory")):
        if not p.exists():
            print(f"[ERROR] {label} not found: {p}")
            return 1
    ok = build_sprite(args.sprite_id, args.source.resolve(), args.out_dir,
                      args.tolerance, args.min_island, args.dry_run,
                      args.hot_x, args.hot_y)
    if ok or args.dry_run:
        print("\nDone. Verify with diagnose_spr.py / decode the anim "
              "transparencies (must be 15s).")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
