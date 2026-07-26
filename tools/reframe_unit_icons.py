#!/usr/bin/env python
"""
Reframe the durable ICON_UNIT_*.tga art so it stops over-filling the frame.

WHY THIS EXISTS
---------------
build_unit_icon_art.py used to call fit_pad(crop_to_content(im)) with no cap:
crop tight to the unit, then scale that crop until it FILLS the 160x120 icon.
Measured across all 55 MoM icons on 2026-07-25, the content height extent was
EXACTLY 0.95 for every single one -- a deterministic normalisation, not source
variance -- while the same units' SPRITE art sat at a median 0.66. Symptoms:

  * GUARDIAN_SPIRIT overran the 96x72 bottom-UI preview box and clipped at the
    frame edge ("too big for the unit preview ui");
  * SPEARMEN had its spear tip severed by the frame, leaving a floating white
    sliver, so the preview no longer matched the map unit ("the carpet doesn't
    match the drapes").

The generator is fixed (ICON_CONTENT_MAX_FRAC), but a regen cannot restore
pixels that were already clipped away, and the shipped TGAs are the durable
truth for icon art (same precedent as ICON_ADVANCE_*.tga). So this tool repairs
the artifacts directly.

STRATEGY
--------
The icon and the sprite are the SAME drawing for essentially every unit -- the
low pixel correlation between them was caused by the zoom difference, not by
different art (verified visually across the 8 worst-correlating pairs; 7 of 8
were the same subject). The SPRITE art is complete and unclipped, so where the
subjects agree the icon is rebuilt FROM the sprite: that fixes framing and
clipping in one move, and makes the preview match the map by construction.

Where the subjects genuinely disagree (SETTLER: icon is a robed settler, sprite
is a blue Wraith -- a proxy-art assignment bug, tracked separately) the sprite is
NOT copied over. Those icons are reframed from their own content instead, which
still removes the over-zoom without propagating wrong art.

Require:   --icon-dir holds ICON_UNIT_*.tga and SPRITE_*.tga in CTP2 icon format
           (type 2, 160x120, 16bpp RGB555, bottom-origin, desc 0x00).
Guarantee: every rewritten file keeps that exact format and its content extent
           is <= ICON_CONTENT_MAX_FRAC of the frame; originals are backed up to
           <icon-dir>/_icon_backup/ before the first write.
Failure:   a unit whose content is unreadable (fully black) is skipped and
           reported, never written blind.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_unit_icon_art import (  # noqa: E402
    ICON_CONTENT_MAX_FRAC,
    ICON_H,
    ICON_W,
    write_icon_tga,
)

# Faint single-pixel "stars" speckle the black background of this art. A naive
# low threshold reads them as content and returns a full-frame bbox for every
# file (this produced a bogus uniform "0.97 extent" measurement earlier). 40 plus
# a 3x3 min-filter erases the specks and leaves the real silhouette.
CONTENT_THRESHOLD = 40
DESPECKLE = 3

# Below this correlation the icon and sprite are different subjects and the
# sprite must not be copied over the icon. Calibrated against the measured
# distribution: the same-subject pairs bottom out at 0.26 (ZOMBIES), while the
# one true mismatch (SETTLER) sits at 0.06.
SAME_SUBJECT_MIN_CORR = 0.20

# Vertical margin left below the unit's feet, in icon pixels. The art is drawn
# standing on a ground shadow, so bottom-aligning flush to the frame edge looks
# like the unit is falling out of the box.
FLOOR_MARGIN = 6


def content_bbox(im: Image.Image) -> tuple[int, int, int, int] | None:
    """Bounding box of the non-background silhouette, or None if fully dark."""
    mask = (ImageChops.difference(im.convert("RGB"),
                                  Image.new("RGB", im.size, (0, 0, 0)))
            .convert("L")
            .point(lambda v: 255 if v > CONTENT_THRESHOLD else 0)
            .filter(ImageFilter.MinFilter(DESPECKLE)))
    return mask.getbbox()


def signature(im: Image.Image) -> Image.Image | None:
    """Scale-invariant grey thumbnail of the content, for subject comparison."""
    box = content_bbox(im)
    return im.crop(box).convert("L").resize((48, 48), Image.LANCZOS) if box else None


def correlate(a: Image.Image, b: Image.Image) -> float:
    """Pearson correlation of two equally sized grey images; 0 if either is flat."""
    va, vb = list(a.getdata()), list(b.getdata())
    ma, mb = sum(va) / len(va), sum(vb) / len(vb)
    da, db = [v - ma for v in va], [v - mb for v in vb]
    denom = (sum(v * v for v in da) * sum(v * v for v in db)) ** 0.5
    return sum(x * y for x, y in zip(da, db)) / denom if denom else 0.0


def reframe(src: Image.Image, box: tuple[int, int, int, int]) -> Image.Image:
    """
    Place src's content on a fresh 160x120 black canvas at <= the extent cap.

    Require:   box is src's content bounding box (right/bottom exclusive).
    Guarantee: the result is 160x120 RGB, content horizontally centred and
               standing FLOOR_MARGIN px above the bottom edge, never upscaled
               past its natural size.
    """
    content = src.crop(box)
    scale = min(ICON_W * ICON_CONTENT_MAX_FRAC / content.width,
                ICON_H * ICON_CONTENT_MAX_FRAC / content.height,
                1.0)
    content = content.resize((max(1, round(content.width * scale)),
                              max(1, round(content.height * scale))),
                             Image.LANCZOS)
    canvas = Image.new("RGB", (ICON_W, ICON_H), (0, 0, 0))
    canvas.paste(content, ((ICON_W - content.width) // 2,
                           ICON_H - FLOOR_MARGIN - content.height))
    return canvas


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--icon-dir", type=Path, required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    backup = args.icon_dir / "_icon_backup"
    icons = sorted(args.icon_dir.glob("ICON_UNIT_*.tga"))
    if not icons:
        print(f"no ICON_UNIT_*.tga under {args.icon_dir}", file=sys.stderr)
        return 1

    from_sprite = reframed = skipped = 0
    for icon_path in icons:
        name = icon_path.stem[len("ICON_UNIT_"):]
        icon = Image.open(icon_path).convert("RGB")
        icon_box = content_bbox(icon)
        if icon_box is None:
            print(f"  SKIP {name}: icon has no readable content")
            skipped += 1
            continue

        sprite_path = args.icon_dir / f"SPRITE_{name}.tga"
        source, source_box, origin = icon, icon_box, "icon"
        if sprite_path.exists():
            sprite = Image.open(sprite_path).convert("RGB")
            sprite_box = content_bbox(sprite)
            if sprite_box is not None:
                sig_i, sig_s = signature(icon), signature(sprite)
                corr = correlate(sig_i, sig_s) if sig_i and sig_s else 0.0
                if corr >= SAME_SUBJECT_MIN_CORR:
                    source, source_box, origin = sprite, sprite_box, "sprite"
                else:
                    print(f"  KEEP {name}: sprite is a different subject "
                          f"(corr {corr:.2f}) -- reframing icon art instead")

        out = reframe(source, source_box)
        new_box = content_bbox(out)
        extent = (new_box[3] - new_box[1]) / ICON_H if new_box else 0.0
        print(f"  {name:22s} <- {origin:6s}  extent {extent:.2f}")

        if not args.dry_run:
            backup.mkdir(exist_ok=True)
            target = backup / icon_path.name
            if not target.exists():
                shutil.copy2(icon_path, target)
            write_icon_tga(icon_path, out)

        from_sprite += origin == "sprite"
        reframed += origin == "icon"

    print(f"\n{len(icons)} icons: {from_sprite} rebuilt from sprite art, "
          f"{reframed} reframed in place, {skipped} skipped"
          f"{'  (DRY RUN, nothing written)' if args.dry_run else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
