"""install_crafted_art.py -- put hand-crafted unit art into the mod, correctly formatted.

Spec: no governing spec found. Basis: operator instruction 2026-09-06 -- "por
      over those images to their namesakes". Source folder supplied by them:
      C:\\Users\\user\\Documents\\wiki\\games\\ctp2\\art. Promote to a REQ before
      anything depends on this.

CRAFTED ART OUTRANKS GENERATED ART, ALWAYS. These files are hand-made by the
operator. Nothing here generates, restyles or "improves" them -- the only
transformation is the format conversion the engine requires, and that is lossy
in exactly one controlled way (RGB555), documented below.

THE TARGET FORMAT IS NOT NEGOTIABLE
Measured from a shipping master (SPRITE_PRIEST.tga): 160x120, uncompressed
type-2 TGA, 16bpp RGB555, bottom-origin, descriptor byte 0x00. A descriptor
byte other than 0x00 has previously produced the "fugly" corrupted-texture
class of bug, so it is written explicitly rather than left to a library.

THE BLACK FLOOR IS PICKED IN QUANTISED SPACE
The engine keys black to transparency. Interior art that is legitimately black
must therefore be nudged off pure black, but RGB555 keeps only the top 5 bits:
a floor of 9 becomes 8 on write, which lands ON the flood-fill tolerance and
erodes the silhouette. So the floor is 16 -- the first value that survives
quantisation clear of the key -- and it is applied BEFORE the write, not after.

ALPHA DECIDES WHAT IS ART -- NEVER COLOUR, NEVER BRIGHTNESS
The engine has no alpha channel here; it keys the background colour. So
transparent pixels become the key (pure black) and opaque art is floored off it.
Two bugs came from deciding by appearance instead of by alpha, and both are now
guarded by tests:

  * the dark floor skipped pure-black pixels as "that must be background",
    so a black robe imported as transparent HOLES;
  * framing used harmonize_unit_art.normalize_geometry, whose mask is derived
    from LUMINANCE -- correct for the shipped masters (art on a flat black key)
    but blind to a black robe against a dark background, which it cropped away.
    `_normalize_alpha` reframes from the alpha bbox instead, at the same
    fractions, so artwork colour cannot influence its own framing.

SOURCES ARRIVE IN THREE SHAPES and only one is safe to trust as-is: RGBA with
real transparency. RGB on black is harmless. RGB on WHITE (any .jfif/.jpg
export) has no alpha at all and would import as an opaque box, so `_keyed`
derives a mask by flooding from the border colour when a source carries none.

Every overwrite is backed up next to the original as `<name>.tga.bak-<stamp>`.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from export_transparent_png import DEFAULT_PICS   # noqa: E402

DEFAULT_SRC = Path(r"C:\Users\user\Documents\wiki\games\ctp2\art")
W, H = 160, 120
KEY = (0, 0, 0)
DARK_FLOOR = 16          # first value that survives RGB555 clear of the key

# crafted filename stem -> unit ident. Explicit, because "runesmith.png" is
# DWARF_RUNESMITH and no amount of string munging gets that right.
NAMESAKE = {
    "treant": "TREANT",
    "arch mage": "ARCH_MAGE",
    "crystal golem": "CRYSTAL_GOLEM",
    "drow": "DROW",
    "dwarf crossbow": "DWARF_CROSSBOW",
    "dwarf warrior": "DWARF_WARRIOR",
    # Later revisions the operator saved alongside the originals. Several map to
    # an ident that an earlier file already claims, which is why NEWEST WINS
    # below -- "priest (2).png" is a redraw of "priest.png", not a second unit.
    "priest (2)": "PRIEST",
    "crystal_golem": "CRYSTAL_GOLEM",
    "arch_mage": "ARCH_MAGE",
    "storm_drake": "STORM_DRAKE",
    "settler reimagined": "SETTLER",
    "minotaur_reimagined": "MINOTAUR",
    # DJINN is the genie again now that its centaur-archer tile moved
    # to CENTAUR_BOWMAN.
    "genie_reimagined": "DJINN",
    # 2026-09-26 batch. Several are native pixel sprites (16-40 px) that the
    # framing pass upscales with NEAREST so they stay crisp.
    "lich": "LICH",
    "ogre": "OGRE",
    "orc": "ORC",
    "orc_": "ORC",                    # newest wins -> orc_.png
    "iron golem": "IRON_GOLEM",
    "peasant": "PEASANTS",
    "skeleton warrior reimagined": "SKELETONS",
    "wizard": "MAGE",                 # operator: "I have a good mage image"
    # DRACOLICH: mapped to ONE file on purpose. Four variants exist and
    # newest-wins would pick "green dracolich.png" -- the desaturated grey-green
    # the operator rejected ("the dracolich is now fucking green"). dracolich_.png
    # is the bone-white skeletal dragon that matches the eldritch description
    # they authored. The other three are deliberately NOT mapped.
    "dracolich_": "DRACOLICH",
    # The centaur-archer art now belongs to the NEW unit created from it,
    # not to DJINN, whose tile it used to be.
    "centaur archer reimagined": "CENTAUR_BOWMAN",
    "priest": "PRIEST",
    "runesmith": "DWARF_RUNESMITH",
    # operator 2026-09-26: "centaurs is missing the new version". Same pose as
    # the old tile, but a clean 38x41 sprite instead of a blurred blow-up.
    "centaur": "CENTAURS",
}


def _key_pockets(rgba: Image.Image, bg: tuple[int, int, int], tol: int,
                 min_frac: float) -> int:
    """Key ENCLOSED background: near-bg regions the edge flood could not reach.

    The border flood-fill stops at the silhouette, so background trapped
    between legs or inside a drawn bowstring survives as a black hole that
    shows on the map as a box. Any connected region of background-coloured
    pixels at least `min_frac` of the frame is keyed too.

    OPT-IN, for GENERATED art only: on a flat noisy background a large pure
    near-black region is background. On hand-made art the same test would eat
    a black cloak, which is why crafted files never get this pass. Returns the
    number of pixels keyed.
    """
    w, h = rgba.size
    px = rgba.load()
    near =[[px[x, y][3] and sum(abs(px[x, y][i] - bg[i]) for i in range(3)) <= tol
             for x in range(w)] for y in range(h)]
    seen = [[False] * w for _ in range(h)]
    min_px, keyed = int(w * h * min_frac), 0
    for sy in range(h):
        for sx in range(w):
            if not near[sy][sx] or seen[sy][sx]:
                continue
            comp, stack = [], [(sx, sy)]
            seen[sy][sx] = True
            while stack:
                x, y = stack.pop()
                comp.append((x, y))
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < w and 0 <= ny < h and near[ny][nx] and not seen[ny][nx]:
                        seen[ny][nx] = True
                        stack.append((nx, ny))
            if len(comp) >= min_px:
                for x, y in comp:
                    px[x, y] = (0, 0, 0, 0)
                keyed += len(comp)
    return keyed


def _keyed(src: Path, tol: int | None = None, pockets: float = 0.0) -> Image.Image:
    """Open `src` with a usable alpha channel, deriving one if it has none.

    Crafted files arrive three ways and only one is safe to trust:

        RGBA with real transparency   -> use it
        RGB on a BLACK background     -> harmless; black is already the key
        RGB on a WHITE background     -> DANGEROUS. Composited onto the key it
                                         becomes an opaque white box with the
                                         figure buried in it, and every later
                                         check (size, format, opacity, render)
                                         still passes.

    A .jfif/.jpg export has no alpha at all, so the background must be derived.
    build_sprites._key_background samples the CORNER colour and floods inward,
    which is right for either polarity -- a global "black is transparent" test
    would punch holes through legitimately black art instead.

    `tol` defaults to build_sprites' BG_KEY_TOLERANCE (24), right for flat
    backgrounds. GENERATED art sits on a NOISY near-black background, and at 24
    the noise survives as dark streaks around the figure -- the 2026-09-06 z-image
    workflow keyed at 96 for exactly this reason.
    """
    im = Image.open(src)
    if im.mode == "RGBA":
        a = im.getchannel("A")
        if a.getextrema()[0] < 255:          # genuine transparency present
            return im
    rgba = im.convert("RGBA")
    from build_sprites import _key_background, BG_KEY_TOLERANCE
    t = BG_KEY_TOLERANCE if tol is None else tol
    bg = _corner_colour(rgba)        # sample BEFORE the flood keys the corners
    _key_background(rgba, t)
    if pockets:
        _key_pockets(rgba, bg, t, pockets)
    return rgba


def _corner_colour(im: Image.Image) -> tuple[int, int, int]:
    px, (w, h) = im.load(), im.size
    cs = (px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1])
    return tuple(sum(c[i] for c in cs) // 4 for i in range(3))


def _block_size(im: Image.Image) -> int:
    """Pixel-block size of a sprite that was ENLARGED by a whole number before
    it was saved (every run of identical pixels is a multiple of it), else 1."""
    from functools import reduce
    from math import gcd
    w, h = im.size
    px = im.load()
    runs: list[int] = []
    for line in ([[px[x, y] for x in range(w)] for y in range(h)]
                 + [[px[x, y] for y in range(h)] for x in range(w)]):
        n = 1
        for a, b in zip(line, line[1:]):
            if a == b:
                n += 1
            else:
                runs.append(n)
                n = 1
        runs.append(n)
    k = reduce(gcd, runs) if runs else 1
    return k if k > 1 and w % k == 0 and h % k == 0 else 1


def _to_native_grid(im: Image.Image) -> Image.Image:
    """Undo a whole-number enlargement exactly, so the resize that follows works
    from the real pixels.

    "dwarf warrior.png" is a 45x65 sprite saved at 3x (135x195). Shrinking the
    3x file to frame height with LANCZOS averaged across block edges, so blocks
    came out uneven and blurred and the operator called the unit "incorrect".
    Reducing by the block size with NEAREST is lossless; the frame resize then
    enlarges with NEAREST like every other native sprite.
    """
    k = _block_size(im)
    return im.resize((im.width // k, im.height // k), Image.NEAREST) if k > 1 else im


def _normalize_alpha(im: Image.Image) -> Image.Image:
    """Scale content to the roster's frame fraction USING THE ALPHA CHANNEL.

    harmonize_unit_art.normalize_geometry does the same job but derives its mask
    from LUMINANCE. That is right for the shipped masters, which are art on a
    flat black key -- but wrong for crafted art with a real alpha channel and a
    dark background: a black robe touching a black background is invisible to a
    brightness test, so the robe gets scaled as if it were not there and its
    bottom is cropped away. The operator saw exactly that: "missing black spots
    in the robe".

    Alpha already says what is art. Use it, and nothing about the artwork's
    colour can mislead the framing.

    Fractions match harmonize_unit_art so crafted and generated units agree in
    size (TARGET_H_FRAC 0.88, MAX_W_FRAC["icon"]).
    """
    from harmonize_unit_art import TARGET_H_FRAC, MAX_W_FRAC
    im = _to_native_grid(im)
    box = im.getchannel("A").getbbox()
    if box is None:
        raise ValueError("no content found to normalize (fully transparent)")
    art = im.crop(box)
    scale = min(W * MAX_W_FRAC["icon"] / art.width,
                H * TARGET_H_FRAC / art.height)
    new = (max(1, round(art.width * scale)), max(1, round(art.height * scale)))
    # UPSCALES USE NEAREST. Several crafted files are native pixel sprites
    # (16x31, 18x34, 27x41) that need a 3-6x enlargement to reach the frame.
    # LANCZOS on an upscale smears every hard pixel edge into a gradient and
    # the sprite arrives as a blur; NEAREST keeps the blocks the artist drew.
    # Downscales keep LANCZOS -- there, averaging is what preserves detail.
    art = art.resize(new, Image.NEAREST if scale > 1.0 else Image.LANCZOS)
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    out.paste(art, ((W - art.width) // 2, (H - art.height) // 2))
    return out


def to_master(src: Path, normalize: bool = False,
              key_tol: int | None = None, pockets: float = 0.0) -> Image.Image:
    """Crafted image -> 160x120 RGB on the black key, art floored off pure black.

    `normalize` runs the same geometry pass the shipped roster went through:
    content scaled to a fixed fraction of frame height, aspect preserved,
    centred. Without it each crafted file keeps whatever scale it was drawn at,
    so DWARF_CROSSBOW renders a third the size of DWARF_WARRIOR standing beside
    it -- which is the defect, not a style choice.

    Contain-only (the default) is the honest fallback for art whose framing is
    already deliberate; normalize is for making a set agree.
    """
    if normalize:
        im = _normalize_alpha(_keyed(src, key_tol, pockets))
    else:
        im = _keyed(src, key_tol, pockets)
        im = im.convert("RGBA") if im.mode != "RGBA" else im
        if im.size != (W, H):
            c = im.copy()
            c.thumbnail((W, H), Image.LANCZOS)   # contain: never distort
            im = c
    # ALPHA decides what is art, NOT colour.
    #
    # An earlier version floored only pixels that were near-black but not pure
    # black, skipping (0,0,0) as "that must be background". It is not: a black
    # robe, black armour or a black wing is art that happens to be pure black,
    # and leaving it at the key value punched transparent holes straight through
    # the figure. The operator saw it immediately -- "missing black spots in the
    # robe" -- while every format and size check passed.
    #
    # The mask already knows the answer, so use it: every pixel the source calls
    # opaque is floored off the key, whatever its colour; every pixel it calls
    # transparent becomes the key.
    #
    # HALF-ALPHA IS THE CUT, not "any alpha". The engine key is binary, so a
    # partially transparent pixel must become either art or key. A LANCZOS
    # downscale leaves a rim of low-alpha pixels whose colour is mostly the
    # black they were blended with; calling those opaque painted a dark fringe
    # and horizontal ringing streaks around every downscaled figure.
    ox, oy = (W - im.width) // 2, (H - im.height) // 2
    solid = im.getchannel("A").point(lambda a: 255 if a >= 128 else 0)
    flat = Image.new("RGB", (W, H), KEY)
    flat.paste(im.convert("RGB"), (ox, oy), solid)
    mask = Image.new("L", (W, H), 0)
    mask.paste(solid, (ox, oy))
    px, mk = flat.load(), mask.load()
    for y in range(H):
        for x in range(W):
            if mk[x, y] == 0:
                continue                      # background: stays the key
            r, g, b = px[x, y]
            if r < DARK_FLOOR and g < DARK_FLOOR and b < DARK_FLOOR:
                px[x, y] = (DARK_FLOOR, DARK_FLOOR, DARK_FLOOR)
    return flat


def write_tga(path: Path, im: Image.Image) -> None:
    """160x120 type-2 16bpp RGB555, bottom-origin, descriptor 0x00."""
    im = im.convert("RGB")
    hdr = bytearray(18)
    hdr[2] = 2
    hdr[12:14] = W.to_bytes(2, "little")
    hdr[14:16] = H.to_bytes(2, "little")
    hdr[16] = 16
    hdr[17] = 0x00
    px = im.load()
    rows = []
    for y in range(H - 1, -1, -1):            # bottom-origin
        row = bytearray()
        for x in range(W):
            r, g, b = px[x, y]
            row += (((r >> 3) << 10) | ((g >> 3) << 5) | (b >> 3)).to_bytes(2, "little")
        rows.append(bytes(row))
    path.write_bytes(bytes(hdr) + b"".join(rows))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--pics", type=Path, default=Path(DEFAULT_PICS))
    ap.add_argument("--only", nargs="*", help="limit to these idents")
    ap.add_argument("--apply", action="store_true",
                    help="write into the mod; default is a dry run")
    ap.add_argument("--normalize", action="store_true",
                    help="scale content to the roster's standard frame fraction "
                         "so units agree in size (DWARF_CROSSBOW vs DWARF_WARRIOR)")
    ap.add_argument("--file", nargs="*", default=[], metavar="IDENT=PATH",
                    help="install an explicit image onto a unit (accepted "
                         "generated art); skips the art-folder scan")
    ap.add_argument("--key-tol", type=int, default=None,
                    help="background key tolerance for sources with no alpha "
                         "(default 24; noisy generated backgrounds need more)")
    ap.add_argument("--key-pockets", type=float, default=0.0, metavar="FRAC",
                    help="GENERATED art only: also key enclosed background "
                         "regions at least FRAC of the frame (e.g. 0.004)")
    args = ap.parse_args()

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    found = {}
    for spec in args.file:
        ident, _, path = spec.partition("=")
        if not Path(path).is_file():
            print(f"no such file for {ident}: {path}", file=sys.stderr)
            return 2
        found[ident] = Path(path)
    for p in ([] if args.file else sorted(args.src.iterdir())):
        if p.suffix.lower() not in (".png", ".tga", ".jfif", ".jpg", ".jpeg"):
            continue
        ident = NAMESAKE.get(p.stem.lower())
        if not ident:
            print(f"  SKIP  {p.name}: no namesake mapping")
            continue
        # NEWEST WINS. Several idents are claimed by more than one file because
        # the operator saves redraws beside the originals ("priest (2).png" next
        # to "priest.png", "arch_mage.png" next to "arch mage.png"). Preferring
        # .tga, or taking whichever sorted last, would silently install the
        # STALE version -- and it would look like a successful install.
        if ident in found and found[ident].stat().st_mtime >= p.stat().st_mtime:
            continue
        found[ident] = p
    if args.only:
        found = {k: v for k, v in found.items() if k in set(args.only)}

    print(f"{len(found)} crafted files -> mod "
          f"({'APPLYING' if args.apply else 'dry run'})\n")
    for ident, src in sorted(found.items()):
        dst = args.pics / f"SPRITE_{ident}.tga"
        exists = dst.exists()
        im = to_master(src, normalize=args.normalize, key_tol=args.key_tol,
                       pockets=args.key_pockets)
        note = ""
        if args.apply:
            # THE ICON IS THE SAME ART. uniticon.txt points the build manager
            # and Great Library at ICON_UNIT_<ident>.tga, a separate file in the
            # same 160x120 format. Writing only the SPRITE master left every
            # crafted unit walking the map in new art while its portrait still
            # showed the 2026-09-04 tile -- the name/art mismatch again, one
            # screen over.
            for d in (dst, args.pics / f"ICON_UNIT_{ident}.tga"):
                if d.exists():
                    shutil.copy2(d, d.with_suffix(f".tga.bak-{stamp}"))
                    note = "  (backed up)"
                write_tga(d, im)
        print(f"  {ident:18} <- {src.name:22} {Image.open(src).size} -> {W}x{H}"
              f"{'' if exists else '  NEW FILE'}{note}")

    if not args.apply:
        print("\ndry run only. re-run with --apply to write.")
    else:
        print(f"\nwritten. backups: SPRITE_*.tga.bak-{stamp}")
        print("NOTE: mom.zip must be rebuilt in the same commit as any "
              "scen0000 change (build_mod_zip.py).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
