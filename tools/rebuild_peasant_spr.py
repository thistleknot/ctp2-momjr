"""
rebuild_peasant_spr.py  —  Recompile GU104.SPR from SPRITE_PEASANTS.tga.

Improvement over build_sprites.py's pure-black keying: samples the actual
background colour from the four image corners and keys any pixel within
Manhattan distance BG_TOLERANCE of that colour.  This handles Civ2 BMP
extractions where the background is not exactly (0,0,0) but a slightly-off
near-black or dark colour.

Usage:
    cd "H:\Program Files(x86)\Activision\Call To Power 2"
    python Scenarios\mom\tools\rebuild_peasant_spr.py [--tolerance N] [--dry-run]

Options:
    --tolerance N   Manhattan-distance threshold for background keying (default 12)
    --dry-run       Show what would happen without writing any files

Output:
    ctp2_data\default\graphics\sprites\GU104.SPR  (overwritten)
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

# ── Paths ──────────────────────────────────────────────────────────────────────

_CTP2_ROOT   = Path(__file__).resolve().parent.parent.parent.parent
_SCENARIO    = Path(__file__).resolve().parent.parent / "scen0000"
_TGA         = _SCENARIO / "default" / "graphics" / "pictures" / "SPRITE_PEASANTS.tga"
_SPRITES_DIR = _CTP2_ROOT / "ctp2_data" / "default" / "graphics" / "sprites"
_MAKESPR     = _CTP2_ROOT / "makespr.py"

SPRITE_ID   = 104
SPRITE_WIDTH  = 96
SPRITE_HEIGHT = 72
N_FACINGS     = 5

_GU_SCRIPT = """\
0

UNIT_SPRITE
{
    UNIT_SPRITE_MOVE    1
    {
        SPRITE_NUM_FRAMES    1
        SPRITE_FIRST_FRAME   0
        SPRITE_WIDTH         96
        SPRITE_HEIGHT        72
        SPRITE_HOT_POINTS
            49 54
            43 51
            50 48
            58 38
            74 53
    }

    ANIM    1
    {
        ANIM_TYPE            1
        ANIM_NUM_FRAMES      1
        ANIM_PLAYBACK_TIME   1000
        ANIM_DELAY           0
        ANIM_FRAME_DATA      0
        ANIM_MOVE_DELTAS     0
        ANIM_TRANSPARENCIES  0
    }

    UNIT_SPRITE_ATTACK          0
    UNIT_SPRITE_IDLE            0
    UNIT_SPRITE_VICTORY         0
    UNIT_SPRITE_WORK            0
    UNIT_SPRITE_FIREPOINTS      0
    UNIT_SPRITE_FIREPOINTS_WORK 0
    UNIT_SPRITE_MOVEOFFSETS     0
    UNIT_SPRITE_SHIELDPOINTS    0
}
"""


# ── Background sampling ────────────────────────────────────────────────────────

def _corner_bg(img: Image.Image) -> tuple[int, int, int]:
    """Return the average colour of the four 3×3 corner patches."""
    w, h = img.size
    samples: list[tuple[int, int, int]] = []
    for xs in (range(min(3, w)), range(max(0, w - 3), w)):
        for ys in (range(min(3, h)), range(max(0, h - 3), h)):
            for x in xs:
                for y in ys:
                    r, g, b, *_ = img.getpixel((x, y))
                    samples.append((r, g, b))
    if not samples:
        return (0, 0, 0)
    return (
        sum(s[0] for s in samples) // len(samples),
        sum(s[1] for s in samples) // len(samples),
        sum(s[2] for s in samples) // len(samples),
    )


def _manhattan(a: tuple[int, int, int], b: tuple[int, int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2])


def _remove_islands(px, width: int, height: int, min_size: int) -> int:
    """
    Key out opaque connected components smaller than min_size pixels
    (8-connectivity).  Removes bright background specks — e.g. star-field
    stars — that survive colour-distance keying because they are far from
    the sampled background colour.  Returns count of pixels removed.
    """
    seen = [[False] * width for _ in range(height)]
    removed = 0
    for sy in range(height):
        for sx in range(width):
            if seen[sy][sx] or px[sx, sy][3] == 0:
                continue
            # BFS this component
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


# ── TGA → TIF conversion ───────────────────────────────────────────────────────

def _make_tifs(tga: Path, work_dir: Path, tolerance: int) -> int:
    """
    Open TGA, resize to 96×72, key background pixels → alpha=0.
    Write 5 facing TIF files into work_dir/{SPRITE_ID}/.
    Returns count of non-background (figure) pixels.
    """
    img = Image.open(str(tga)).convert("RGBA").resize(
        (SPRITE_WIDTH, SPRITE_HEIGHT), Image.LANCZOS
    )

    bg = _corner_bg(img)
    print(f"  Background colour (corner sample): {bg}")

    px      = img.load()
    fig_pix = 0
    for y in range(SPRITE_HEIGHT):
        for x in range(SPRITE_WIDTH):
            r, g, b, a = px[x, y]
            if _manhattan((r, g, b), bg) <= tolerance:
                px[x, y] = (0, 0, 0, 0)    # key out background
            else:
                px[x, y] = (r, g, b, 255)  # force full opacity for figure

    # Drop tiny disconnected specks (star-field stars etc.) that colour
    # keying cannot catch because they are far from the background colour.
    speck_pix = _remove_islands(px, SPRITE_WIDTH, SPRITE_HEIGHT, min_size=20)
    if speck_pix:
        print(f"  Removed {speck_pix} isolated speck pixels (<20 px islands)")

    for y in range(SPRITE_HEIGHT):
        for x in range(SPRITE_WIDTH):
            if px[x, y][3] != 0:
                fig_pix += 1

    facing_dir = work_dir / str(SPRITE_ID)
    facing_dir.mkdir(exist_ok=True)
    nn = f"{SPRITE_ID:02d}"

    for f in range(1, N_FACINGS + 1):
        out = facing_dir / f"GU{nn}MA{f}.0.TIF"
        img.save(str(out), format="TIFF")

    return fig_pix


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tolerance", type=int, default=12,
                        help="Manhattan-distance BG keying threshold (default 12)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show plan without writing files")
    parser.add_argument("--source", type=str, default=None,
                        help="Override source TGA (default SPRITE_PEASANTS.tga); "
                             "e.g. the centred ICON_UNIT_PEASANTS.tga portrait")
    args = parser.parse_args()

    src_tga = Path(args.source).resolve() if args.source else _TGA

    for p, label in ((src_tga, "source TGA"), (_MAKESPR, "makespr.py"),
                     (_SPRITES_DIR, "sprites directory")):
        if not p.exists():
            print(f"[ERROR] {label} not found: {p}")
            return 1

    nn      = f"{SPRITE_ID:02d}"
    out_spr = _SPRITES_DIR / f"GU{nn}.SPR"
    print(f"Source TGA : {src_tga}  ({src_tga.stat().st_size:,} bytes)")
    print(f"Output SPR : {out_spr}")
    print(f"BG tolerance: Manhattan <= {args.tolerance}")

    if args.dry_run:
        print("\n[dry-run] No files written.")
        return 0

    with tempfile.TemporaryDirectory(prefix="mom_peasant_") as tmp:
        work = Path(tmp)

        # 1. Convert TGA → 5 TIFs
        print(f"\nStep 1: TGA -> TIF (tolerance {args.tolerance})")
        fig_pix = _make_tifs(src_tga, work, args.tolerance)
        print(f"  Figure pixels (non-background): {fig_pix} of {SPRITE_WIDTH * SPRITE_HEIGHT}")
        if fig_pix < 10:
            print("  [WARN] Very few figure pixels — source TGA may still be a placeholder.")
            print("         The compiled SPR will likely be blank.")

        # 2. Write script
        print(f"\nStep 2: Write GU{nn}.TXT")
        script_file = work / f"GU{nn}.TXT"
        script_file.write_text(_GU_SCRIPT, encoding="latin-1")

        # 3. Run makespr.py
        print(f"\nStep 3: Run makespr.py -u {SPRITE_ID}")
        result = subprocess.run(
            [sys.executable, str(_MAKESPR), "-u", str(SPRITE_ID)],
            cwd=str(work),
            capture_output=True,
            text=True,
        )
        if result.stdout.strip():
            print(f"  {result.stdout.strip()}")
        if result.returncode != 0:
            print(f"  [ERROR] makespr.py failed (exit {result.returncode})")
            if result.stderr.strip():
                print(f"  stderr: {result.stderr.strip()}")
            return 1

        spr_tmp = work / f"GU{nn}.SPR"
        if not spr_tmp.exists():
            print(f"  [ERROR] makespr.py did not produce GU{nn}.SPR")
            return 1

        # 4. Copy to sprites directory
        print(f"\nStep 4: Copy to sprites directory")
        shutil.copy2(str(spr_tmp), str(out_spr))
        print(f"  Written: {out_spr}  ({out_spr.stat().st_size:,} bytes)")

    print(f"\nDone. Run diagnose_spr.py to verify the SPR has non-empty frames.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
