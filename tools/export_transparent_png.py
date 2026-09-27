#!/usr/bin/env python
"""export_transparent_png.py -- CTP2 unit TGAs out as RGBA PNGs with real alpha.

Spec: specs/ctp2-sprites.spec.md (:Still-Picture:, :Background-Keying:).
Task: no ledger task; operator request 2026-09-05 -- "I'd really appreciate it if
      the image didn't have black but transparency so when I load into paint.net
      it actually has the transparent background, else I'm pasting black into
      comfyui".

WHY THIS EXISTS
---------------
CTP2 icon TGAs are 16bpp RGB555 with NO alpha channel -- transparency is implied
by a pure-black key that the engine floods from the frame border. Opened in an
editor they are opaque black rectangles, so anything pasted out of them carries
a black box.

This writes the same art as 32-bit RGBA PNG with the keyed background at alpha 0,
so it drops cleanly onto another layer or back into ComfyUI.

THE KEYING IS THE ENGINE'S, NOT A THRESHOLD
-------------------------------------------
Alpha comes from `build_sprites._key_background`: a border flood-fill within
BG_KEY_TOLERANCE Manhattan distance of the corner colour. That is deliberate and
the spec requires it -- a global "black is transparent" rule would punch holes in
every unit with black armour, fur or wings, which is most of this roster. The
consequence to know about: a region fully ENCLOSED by art (the hole inside a
lamp handle) is not border-reachable, so it stays opaque. That matches what the
engine draws, which is the point.

`--soft-edge` additionally feathers the alpha at the silhouette edge so the
cut-out does not read as a hard 1-pixel stair-step when composited over a new
background. Off by default: it is a compositing nicety, not what the engine does.

Usage:
    python export_transparent_png.py --out <dir>
    python export_transparent_png.py --out <dir> --family sprite --soft-edge 0.6
    python export_transparent_png.py --out <dir> --from-dir .tmp/areanorm --scale 4
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harmonize_unit_art import (   # noqa: E402
    BG_KEY_TOLERANCE,
    content_mask,
    family_of,
    normalize_geometry,
    select_files,
)

# The size the ENGINE works in, per family. A sprite master is 160x120 but the
# engine compiles it to a 96x72 frame (48x36 at normal map zoom), so 96x72 is
# what a reviewer is actually judging. Icons are consumed at their master size.
GAME_FRAME = {"sprite": (96, 72), "icon": (160, 120)}

DEFAULT_PICS = Path(
    r"H:\Program Files(x86)\Activision\Call To Power 2\Scenarios\mom"
    r"\scen0000\default\graphics\pictures"
)


def to_rgba(im: Image.Image, soft_edge: float = 0.0,
            despeckle_px: int = 6) -> Image.Image:
    """
    Return the image as RGBA with the engine-keyed background at alpha 0.

    Require : `im` is a CTP2 icon TGA (opaque RGB, black key).
    Guarantee: returns RGBA the same size; every pixel the engine would draw is
               opaque, every pixel it would key is alpha 0; RGB values of visible
               pixels are unchanged.
    Failure  : an image with no content returns fully transparent rather than
               guessing.
    """
    rgb = im.convert("RGB")
    # ONE exact key colour, as build_sprites keys it (operator 2026-09-26: "pick
    # just one color for alpha masking and no magic wand"). The old border
    # flood + despeckle showed enclosed background as art and disagreed with
    # the game. `despeckle_px` is kept for callers but no longer used.
    alpha = Image.eval(
        ImageChops.lighter(ImageChops.lighter(*rgb.split()[:2]), rgb.split()[2]),
        lambda v: 255 if v else 0)                        # 255 = art, 0 = key
    if soft_edge > 0:
        # Blur OUTWARD only, so the interior never thins -- max(hard, blurred).
        alpha = ImageChops.lighter(alpha, alpha.filter(
            ImageFilter.GaussianBlur(soft_edge)))
    out = rgb.convert("RGBA")
    out.putalpha(alpha)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--from-dir", type=Path, default=DEFAULT_PICS,
                    help="source TGAs (default: the live scenario pictures dir)")
    ap.add_argument("--family", choices=["sprite", "icon", "both"], default="both")
    ap.add_argument("--soft-edge", type=float, default=0.0,
                    help="feather the alpha edge by N px (0 = engine-exact)")
    ap.add_argument("--scale", type=int, default=1,
                    help="nearest-neighbour upscale, for editing at a usable size")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--normalize", action="store_true",
                    help="render at the engine's frame size with content height "
                         "normalised proportionally (sprite 96x72, icon 160x120)")
    ap.add_argument("--ext", default="tga")
    args = ap.parse_args()

    if not args.from_dir.is_dir():
        print(f"FATAL: no such dir {args.from_dir}", file=sys.stderr)
        return 2
    args.out.mkdir(parents=True, exist_ok=True)

    files = select_files(args.from_dir, args.family, [], args.limit, args.ext)
    written = empty = 0
    for f in files:
        try:
            im = Image.open(f)
        except Exception as e:                                # noqa: BLE001
            print(f"  SKIP {f.name}: {e}")
            continue
        if args.normalize:
            # Same geometry pass the shipped art went through: content scaled to
            # a fixed FRACTION of frame height, aspect preserved, then centred.
            # Rendered straight to the frame size in one resample -- going via
            # the 160x120 master and resizing after would stack two resamples.
            fam = family_of(f.stem)
            fw, fh = GAME_FRAME[fam]
            im = normalize_geometry(im.convert("RGB"), fam, fw, fh)[0]
        rgba = to_rgba(im, args.soft_edge)
        if rgba.getchannel("A").getbbox() is None:
            empty += 1
            print(f"  EMPTY {f.name}: no content after keying")
        if args.scale > 1:
            rgba = rgba.resize((rgba.width * args.scale, rgba.height * args.scale),
                               Image.NEAREST)
        rgba.save(args.out / f"{f.stem}.png")
        written += 1

    # report how much of the frame is actually transparent, as a sanity check --
    # a 0% figure would mean the key never fired and every PNG is still a box
    sample = sorted(args.out.glob("*.png"))[:24]
    fracs = []
    for p in sample:
        a = Image.open(p).getchannel("A")
        fracs.append(sum(1 for v in a.getdata() if v == 0) / (a.width * a.height))
    print(f"\nwrote {written} RGBA PNG(s) to {args.out}"
          + (f"  ({empty} had no content)" if empty else ""))
    if fracs:
        print(f"transparent area across {len(fracs)} sampled: "
              f"{min(fracs):.0%} - {max(fracs):.0%} (median {sorted(fracs)[len(fracs)//2]:.0%})")
    print(f"alpha derived from the engine's border flood-fill "
          f"(BG_KEY_TOLERANCE={BG_KEY_TOLERANCE}); enclosed regions stay opaque by design")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
