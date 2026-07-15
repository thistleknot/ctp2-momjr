"""
build_sprites.py — Compile MoM unit SPR files from SPRITE_*.tga sources.

Discovers every SPRITE_*.tga in the scenario pictures/ directory, cross-
references against newsprite.txt, auto-assigns numbers for unregistered art,
and builds any GU###.SPR that does not yet exist.

Pipeline per sprite:
  1. Convert SPRITE_X.tga → 5 facing 96×72 RGBA TIFs via ImageMagick
       (pure-black background keyed to alpha=0)
  2. Write minimal single-frame GU###.TXT script into a temp work dir
  3. Run makespr.py -u ### from that work dir
  4. Copy GU###.SPR → ctp2_data/default/graphics/sprites/
  5. Append SPRITE_X ### to MoM newsprite.txt when newly registered

Skips base-game sprites (numbers 1–90) that already have stock SPR files.
Idempotent: already-built SPRs are not rebuilt unless --force is passed.

Usage:
    python build_sprites.py [--dry-run] [--force]
"""
from __future__ import annotations

import argparse
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("Pillow required: pip install Pillow")

# ── Paths ──────────────────────────────────────────────────────────────────────

TOOLS_DIR    = Path(__file__).resolve().parent
SCENARIO     = Path(
    os.environ.get(
        "CTP2_GENERATOR_SCENARIO_DIR",
        r"H:\Program Files(x86)\Activision\Call To Power 2\Scenarios\mom\scen0000",
    )
)
REPO_ROOT     = SCENARIO.parent.parent.parent   # scen0000 -> mom -> Scenarios -> CTP2 root
PICTURES_DIR  = SCENARIO / "default" / "graphics" / "pictures"
SPRITES_DIR   = REPO_ROOT / "ctp2_data" / "default" / "graphics" / "sprites"
MAKESPR_PY    = REPO_ROOT / "makespr.py"
MOM_NEWSPRITE = SCENARIO / "default" / "gamedata" / "newsprite.txt"
BASE_NEWSPRITE = REPO_ROOT / "ctp2_data" / "default" / "gamedata" / "newsprite.txt"

MOM_SPRITE_MIN = 91   # custom MoM range starts here

# ── Sprite build tuning ─────────────────────────────────────────────────────────
N_FACINGS        = 5      # makespr unit sprites require 5 authored facings (N,NE,E,SE,S)
BG_KEY_TOLERANCE = 24     # Manhattan distance for border flood-fill background keying
DARK_FLOOR       = 8      # remap surviving pure-black art to this so makespr keeps it opaque
MIN_OPAQUE_WARN  = 50     # fewer surviving pixels than this => likely near-blank source (H1)

# SPRITE_ names whose extracted source art faces LEFT and must be flipped to face
# right (else the unit appears to walk backwards when moving left/right — Kull #2b).
LEFT_FACING: set[str] = set()

# SPR binary constants (mirror makespr.py / diagnose_spr.py)
_FRPS_TAG  = 0x53505246
_EMPTY_ROW = 0xFFFF

# Minimal single-frame unit sprite script (move-only, 5 static facings)
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


# ── Helpers ────────────────────────────────────────────────────────────────────

def _parse_newsprite(path: Path) -> dict[str, int]:
    """Return {SPRITE_NAME: number} parsed from a newsprite.txt."""
    result: dict[str, int] = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="latin-1").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) == 2 and parts[1].isdigit():
            result[parts[0].upper()] = int(parts[1])
    return result


def _next_number(mom: dict[str, int]) -> int:
    existing = [n for n in mom.values() if n >= MOM_SPRITE_MIN]
    return max(existing, default=MOM_SPRITE_MIN - 1) + 1


def _key_background(img: "Image.Image", tol: int = BG_KEY_TOLERANCE) -> int:
    """
    Make ONLY the border-connected background transparent (alpha=0), preserving
    interior art — including legitimately black foreground pixels. Returns the
    count of surviving (opaque) pixels.

    The old rule keyed EVERY pure-black pixel, which erased dark unit art (black
    fur/armor/wings) along with the background and produced empty sprites. Instead
    we sample the corner background colour and flood-fill inward from the frame
    edges, keying only pixels within `tol` Manhattan distance of it. Any pure-black
    pixel that survives the flood-fill is interior art; nudge it to DARK_FLOOR so
    makespr's chromakey test (pixel==0 AND alpha==0) never mistakes it for
    background. Mirrors Kull's GIMP process (see the ctp2-sprite-creation skill).
    """
    w, h = img.size
    px = img.load()

    corners = (px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1])
    bg = (
        sum(c[0] for c in corners) // 4,
        sum(c[1] for c in corners) // 4,
        sum(c[2] for c in corners) // 4,
    )

    def _close(p) -> bool:
        return abs(p[0] - bg[0]) + abs(p[1] - bg[1]) + abs(p[2] - bg[2]) <= tol

    seen = bytearray(w * h)
    stack = [(x, 0) for x in range(w)] + [(x, h - 1) for x in range(w)]
    stack += [(0, y) for y in range(h)] + [(w - 1, y) for y in range(h)]
    while stack:
        x, y = stack.pop()
        if x < 0 or y < 0 or x >= w or y >= h:
            continue
        idx = y * w + x
        if seen[idx]:
            continue
        seen[idx] = 1
        if not _close(px[x, y]):
            continue
        px[x, y] = (0, 0, 0, 0)   # transparent chromakey
        stack.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))

    opaque = 0
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            if r == 0 and g == 0 and b == 0:
                px[x, y] = (DARK_FLOOR, DARK_FLOOR, DARK_FLOOR, 255)
            opaque += 1
    return opaque


def _facing_images(tga: Path, flip: bool) -> list["Image.Image"]:
    """
    Return one keyed 96×72 RGBA image per facing (N,NE,E,SE,S).

    MoM ships a single still image per unit, so we cast that one image across all
    N_FACINGS (a 1:n mapping). This is the single unroll point: when per-facing art
    exists later, load each facing's own source here and return n distinct images
    (n:n) — nothing else in the pipeline needs to change.
    """
    img = Image.open(str(tga)).convert("RGBA").resize((96, 72), Image.LANCZOS)
    if flip:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)   # left-facing source -> right-facing
    _key_background(img)
    return [img] * N_FACINGS   # 1:n cast; replace with n distinct images for true facings


def _convert_tga_to_tifs(tga: Path, num: int, work_dir: Path, flip: bool = False) -> int:
    """
    Write N_FACINGS facing TIF files into work_dir/{num}/ using Pillow.
    Naming: GU{num:02d}MA{f}.0.TIF  — matches makespr.py's unit_image_path().
    Background is keyed to alpha=0 via border flood-fill; interior art is preserved.
    Returns the surviving opaque-pixel count of the source (for H1 near-blank warning).
    """
    facing_dir = work_dir / str(num)
    facing_dir.mkdir(exist_ok=True)
    nn = f"{num:02d}"

    images = _facing_images(tga, flip)
    opaque = sum(1 for p in images[0].getdata() if p[3] != 0)

    for f, img in enumerate(images, start=1):
        out = facing_dir / f"GU{nn}MA{f}.0.TIF"
        img.save(str(out), format="TIFF")
    return opaque


def _spr_move_nonempty_rows(spr: Path) -> "int | None":
    """
    Count non-empty rows across the MOVE action's frames of a compiled unit SPR.
    Returns 0 if fully empty, None if the header is unparseable. Mirrors the SPR
    walk in diagnose_spr.py (kept local to avoid a cross-module import).
    """
    data = spr.read_bytes()
    if len(data) < 32:
        return 0
    if struct.unpack_from("<I", data, 0)[0] != _FRPS_TAG:
        return None
    move = struct.unpack_from("<5I", data, 12)[0]
    if move == 0xFFFFFFFF or move >= len(data) - 6:
        return 0
    spr_type, width, height = struct.unpack_from("<HHH", data, move)
    hp = 5 * 8 if spr_type == 1 else 8
    ffnf = move + 6 + hp
    _first, num_frames = struct.unpack_from("<HH", data, ffnf)
    n_facings = 5 if spr_type == 1 else 1
    stbl = ffnf + 4
    count = n_facings * num_frames * 2
    sizes = struct.unpack_from(f"<{count}I", data, stbl)
    off = stbl + count * 4
    nonempty = 0
    for j in range(n_facings):
        for fr in range(num_frames):
            sz = sizes[j * num_frames * 2 + fr]
            blob = data[off:off + sz]
            if len(blob) >= 2 + height * 2:
                fh = struct.unpack_from("<H", blob, 0)[0]
                roff = struct.unpack_from(f"<{fh}H", blob, 2)
                nonempty += sum(1 for r in roff if r != _EMPTY_ROW)
            off += sz
        for fr in range(num_frames):
            off += sizes[j * num_frames * 2 + num_frames + fr]
    return nonempty


def _build_spr(num: int, work_dir: Path) -> Path:
    """Write GU###.TXT and invoke makespr.py -u {num} in work_dir."""
    nn = f"{num:02d}"
    txt = work_dir / f"GU{nn}.TXT"
    txt.write_text(_GU_SCRIPT, encoding="latin-1")

    subprocess.run(
        [sys.executable, str(MAKESPR_PY), "-u", str(num)],
        cwd=str(work_dir),
        check=True,
    )

    spr = work_dir / f"GU{nn}.SPR"
    if not spr.exists():
        raise FileNotFoundError(f"makespr.py did not produce GU{nn}.SPR")
    return spr


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true",
                        help="Print plan without building anything.")
    parser.add_argument("--force", action="store_true",
                        help="Rebuild SPRs even if they already exist.")
    args = parser.parse_args()

    base_sprites = _parse_newsprite(BASE_NEWSPRITE)
    mom_sprites  = _parse_newsprite(MOM_NEWSPRITE)

    tga_files = sorted(PICTURES_DIR.glob("SPRITE_*.tga"),
                       key=lambda p: p.stem.upper())
    if not tga_files:
        print("No SPRITE_*.tga files found in pictures/.")
        return 0

    # ── Plan ──────────────────────────────────────────────────────────────────
    to_build:    list[tuple[str, int, Path]] = []   # (name, num, tga)
    to_register: list[tuple[str, int]]       = []   # new entries for newsprite.txt
    skipped:     list[str]                   = []

    for tga in tga_files:
        name = tga.stem.upper()   # e.g. SPRITE_PEASANTS

        # Resolve effective sprite number from both files.
        # MoM newsprite.txt copies all base entries, so a number < MOM_SPRITE_MIN
        # in mom_sprites still means it's a base-game sprite — filter by value.
        if name in mom_sprites:
            num = mom_sprites[name]
        elif name in base_sprites:
            num = base_sprites[name]
        else:
            num = None

        if num is not None and num < MOM_SPRITE_MIN:
            skipped.append(f"{name} -> base GU{num:02d}.SPR (no MoM override)")
            continue

        # Assign new MoM number for TGAs not yet in the custom range
        if num is None:
            num = _next_number({**mom_sprites, **dict(to_register)})
            to_register.append((name, num))
            mom_sprites[name] = num   # keep next_number moving forward

        nn = f"{num:02d}"
        spr = SPRITES_DIR / f"GU{nn}.SPR"
        if spr.exists() and not args.force:
            continue   # already built

        to_build.append((name, num, tga))

    # ── Report ────────────────────────────────────────────────────────────────
    if skipped:
        print(f"Skipped {len(skipped)} base-game sprite(s):")
        for s in skipped:
            print(f"  {s}")

    if to_register:
        print(f"\nNew registrations ({len(to_register)}):")
        for name, num in to_register:
            print(f"  {name} {num}")

    if not to_build:
        print("\nAll SPR files up to date.")
        return 0

    print(f"\nBuilding {len(to_build)} SPR file(s):")
    for name, num, tga in to_build:
        nn = f"{num:02d}"
        print(f"  {name} -> GU{nn}.SPR  ({tga.name})")

    if args.dry_run:
        print("\n[dry-run] No files written.")
        return 0

    # ── Write new newsprite.txt entries ───────────────────────────────────────
    if to_register:
        with open(str(MOM_NEWSPRITE), "a", encoding="latin-1") as f:
            for name, num in to_register:
                f.write(f"{name} {num}\n")
        print(f"\nAppended {len(to_register)} entry(s) to {MOM_NEWSPRITE.name}.")

    # ── Build loop ────────────────────────────────────────────────────────────
    errors: list[tuple[str, str, str]] = []

    with tempfile.TemporaryDirectory(prefix="mom_sprites_") as tmp:
        work = Path(tmp)
        for name, num, tga in to_build:
            nn = f"{num:02d}"
            print(f"\n  [{name}] GU{nn}.SPR ...")
            try:
                opaque = _convert_tga_to_tifs(tga, num, work, flip=(name in LEFT_FACING))
                if opaque < MIN_OPAQUE_WARN:
                    print(f"    WARNING: only {opaque} opaque pixels after keying — source "
                          f"art may be near-blank/dark (H1). See tools/diagnose_spr.py.")
                spr = _build_spr(num, work)
                rows = _spr_move_nonempty_rows(spr)
                if rows == 0:
                    raise ValueError(
                        f"compiled GU{nn}.SPR is fully EMPTY (all rows transparent) — keying "
                        f"erased the art for {name}; not copying. Diagnose with diagnose_spr.py.")
                dest = SPRITES_DIR / f"GU{nn}.SPR"
                shutil.copy2(str(spr), str(dest))
                print(f"    -> {dest}  ({dest.stat().st_size} bytes)")
            except Exception as exc:
                errors.append((name, f"GU{nn}.SPR", str(exc)))
                print(f"    ERROR: {exc}")

    # ── Summary ───────────────────────────────────────────────────────────────
    built = len(to_build) - len(errors)
    print(f"\nDone: {built}/{len(to_build)} built, {len(errors)} error(s).")
    if errors:
        for name, spr, err in errors:
            print(f"  FAILED  {name} -> {spr}: {err}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
