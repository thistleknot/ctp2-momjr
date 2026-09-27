#!/usr/bin/env python
"""
harmonize_unit_art.py -- normalize MoM unit art scale and unify its style.

Spec: specs/ctp2-sprites.spec.md -- "functional specs", the :Background-Keying:
      clause ("must make only the border-connected background transparent,
      preserving interior black art"; "Global pure-black keying must not be
      used") and the :Still-Picture: definition (LargeIcon 160x120 TGA).
Task: no ledger task; operator request 2026-09-03 ("unit normalize all my unit
      images ... light transparent mask over a resize, and use denoiser to
      augment the image to look like whatever it's supposed to be").

WHY THIS EXISTS
---------------
The 167 unit TGAs were assembled from mismatched sources. The reported symptom
was "different dimensions", but measured 2026-09-03 every one of them is
already 160x120 opaque RGB on a pure-black key. The actual defect is content
SCALE inside that fixed frame:

    SPRITE_*     (87)  width-frac  min 0.21 / med 0.71 / max 0.94
    ICON_UNIT_*  (80)  width-frac  min 0.21 / med 0.58 / max 0.80

so DWARF_CROSSBOW renders as a speck and STORM_DRAKE fills the tile.

This survives the existing pipeline because build_sprites._normalize_to_stock_extent
-- which DOES normalize extent at build time -- hard-clamps `scale = min(1.0, ...)`.
It never scales content UP. A master at 0.21 arrives in the 96x72 canvas about
30px tall, already under STOCK_CONTENT_H, so it passes through untouched and
stays tiny forever. The fix has to land on the 160x120 master, where the pixels
still exist.

Enlarging a 34x50 creature to fill the frame is exactly where detail dies, which
is why the geometric step is paired with a Z-Image-Turbo img2img pass: the
denoiser rebuilds the detail the upscale cannot, and unifies the art style
across the mismatched sources at the same time.

THE COUPLING THAT GOVERNS THE TARGET
------------------------------------
Pick the master target so it CONVERGES with _normalize_to_stock_extent instead
of fighting it. After a 160x120 master is resized to the 96x72 sprite canvas,
content height must land at or above STOCK_CONTENT_H, or the never-upscale
clamp leaves each unit wherever it was and this whole pass is undone:

    STOCK_CONTENT_H / 72 = 62 / 72 = 0.861  ->  target h-frac must be >= 0.87

TARGET_H_FRAC = 0.88 clears it. TARGET_W_FRAC = 0.78 stays inside
ICON_CONTENT_MAX_FRAC (0.80) so the bottom-UI preview box keeps its margin.
Do not lower either without redoing that arithmetic.

Require:   --in-dir holds SPRITE_*.tga / ICON_UNIT_*.tga in CTP2 icon format
           (type 2, 160x120, 16bpp RGB555, bottom-origin, desc 0x00).
Guarantee: every rewritten file keeps that exact format; its content extent is
           TARGET_W_FRAC x TARGET_H_FRAC of the frame, aspect preserved; its
           background is exactly (0,0,0); originals are copied to
           <in-dir>/_art_backup/ before the first write.
Maintain:  the AI pass can never alter the silhouette -- the geometric mask is
           reapplied verbatim after the round-trip, so the black key stays clean
           and build_sprites' border flood-fill still works.
Failure:   a unit whose content is unreadable (no bbox after keying) is skipped
           and reported, never written blind. A ComfyUI error aborts that unit
           only; --geometry-only skips the server entirely.

Usage:
    # offline geometry check, nothing written
    python harmonize_unit_art.py --geometry-only --dry-run --only DWARF_CROSSBOW

    # pilot a denoise sweep into .tmp/, masters untouched
    python harmonize_unit_art.py --pilot --out-dir ../../../.tmp/harmonize_pilot

    # full batch over the masters
    python harmonize_unit_art.py --family both --denoise 0.42
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import shutil
import sys
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_unit_icon_art import (  # noqa: E402
    ICON_CONTENT_MAX_FRAC,
    ICON_H,
    ICON_W,
    write_icon_tga,
)
from build_sprites import (  # noqa: E402
    BG_KEY_TOLERANCE,
    DARK_FLOOR,
    _key_background,
)

# -- Geometry -----------------------------------------------------------------
# HEIGHT is the normalized axis: it is what _normalize_to_stock_extent keys on
# downstream, and what makes units read at a consistent size on the map. 0.88
# must clear STOCK_CONTENT_H/72 = 0.861 or that pass silently declines to
# rescale (it clamps to <=1.0) and this whole exercise is undone.
TARGET_H_FRAC = 0.88
assert TARGET_H_FRAC >= 62 / 72, "target would be undone by _normalize_to_stock_extent"

# WIDTH is only an overflow guard, and its cap is per-family. Measured
# 2026-09-03, a naive 0.78 cap for both families made the WIDE units (STORM_DRAKE,
# STEAM_CANNON, MINOTAUR) width-bound, dropping them to h=0.67-0.76 -- back under
# the 0.861 threshold, i.e. exactly the units the pass was meant to fix. Icons
# keep the tighter cap because the bottom-UI preview box is a real fixed
# viewport; the sprite canvas has no such box and only needs to stay in frame.
MAX_W_FRAC = {"sprite": 0.95, "icon": ICON_CONTENT_MAX_FRAC}
assert MAX_W_FRAC["icon"] <= ICON_CONTENT_MAX_FRAC, "icons would overrun the preview box"

# -- ComfyUI ------------------------------------------------------------------
COMFY_HOST = "http://192.168.3.17:8188"
# SAMPLING RESOLUTION -- imported from zimage_graph so there is ONE source of
# truth. This file previously hardcoded 512x384 while zimage_graph had already
# moved to 192x144, so the two modules silently disagreed: batches driven
# through zimage_graph sampled correctly while this file's own CLI sampled at
# 4x the pixels, ~5x slower, and measurably WORSE.
#
# Why 192x144: the target is a 96x72 sprite (48x36 mini-frame at normal map
# zoom) from a 160x120 master. 512x384 was 16x the output's pixel count,
# inherited from an untested "Z-Image is trained far above sprite sizes" claim.
# Measured on CRUSADER against the geometry-only baseline:
#     192x144  0.14x px  34s  sharpness 0.90
#     256x192  0.25x px  40s  sharpness 1.05
#     320x240  0.39x px  52s  sharpness 1.09
#     512x384  1.00x px  96s  sharpness 0.98   <- slowest AND among the worst
from zimage_graph import Pipeline as _Pipeline      # noqa: E402
WORK_W, WORK_H = _Pipeline().width, _Pipeline().height
UPSCALE = 1.0                     # single stage at sprite-native resolution

# Retained for the legacy two-stage CLI path; the current default ladder lives
# in zimage_graph.Pipeline.stages.
DENOISE_EARLY, STEPS_EARLY = 0.55, 6
DENOISE_LATE, STEPS_LATE = 0.0, 6


# Floor applied to near-black pixels INSIDE the silhouette so they survive the
# downstream border flood-fill. Two constraints compose here, and missing either
# one silently erodes the figure:
#
#   1. _key_background keys anything within BG_KEY_TOLERANCE *Manhattan* distance
#      of the corner colour, INCLUSIVE, so the pixel must sit strictly outside
#      that ball: 3 * v > 24.
#   2. The CTP2 icon format is 16bpp RGB555 -- 5 bits per channel -- so on write
#      every channel snaps to a multiple of 8. A floor of 9 quantises straight
#      back down to 8, giving distance 24 again and keying after all. Measured:
#      MINOTAUR lost 575 pixels this way, every one of them exactly (8,8,8).
#
# So the floor must be the smallest RGB555-representable value that clears the
# tolerance. build_sprites' own DARK_FLOOR (8) cannot serve: it is applied AFTER
# keying, where alpha is already decided, whereas we lift BEFORE the file is
# written and re-keyed.
RGB555_STEP = 8
EDGE_FLOOR = ((BG_KEY_TOLERANCE // 3 + RGB555_STEP) // RGB555_STEP) * RGB555_STEP
assert EDGE_FLOOR % RGB555_STEP == 0, "floor would not survive RGB555 quantisation"
assert EDGE_FLOOR * 3 > BG_KEY_TOLERANCE, "edge art would still key as background"


def _mul16(v: int, factor: float) -> int:
    """Scale and snap to a multiple of 16 -- Z-Image cannot encode odd latents."""
    return max(16, int(round(v * factor / 16.0)) * 16)

UNET_NAME = "z_image_turbo_fp8_e4m3fn.safetensors"
CLIP_NAME = "qwen_3_4b.safetensors"
CLIP_TYPE = "lumina2"
VAE_NAME = "ae.safetensors"

# Crispness at 96x72 does NOT come from the diffusion model -- no model resolves
# clean at that size. It comes from the DOWNSAMPLE, and from giving the sampler a
# prior that produces hard edges and flat regions in the first place. Measured at
# true sprite size 2026-09-04: without the LoRA the output is smooth and mushy;
# with LoRA + pixel-space upscale + BOX downsample it holds hard edges and
# readable armour segments. At 4x zoom the no-LoRA version looks BETTER, which is
# exactly the trap -- judge these at 96x72 or not at all.
LORA_NAME = "elusarca-pixel-art-zimage.safetensors"   # native Z-Image (lumina2)
LORA_STRENGTH = 0.8                                   # useful band is 0.6-1.0
LORA_TRIGGER = "pixel art"                            # no keyword; just say it
UPSCALE_MODEL = "4x-PixelPerfectV4.pth"               # ESRGAN trained on sprites

# LANCZOS/bicubic reintroduce exactly the softness the upscaler just removed.
DOWNSAMPLE = Image.BOX

# Palette quantisation is OFF. It was added on the theory that flat colour reads
# as period-correct, but scored across 109 units it is the single largest
# remaining gate failure: it crushes the palette to 23-28 colours against
# originals of 79-1288, failing the colour gate on 36 units while producing no
# measurable gain in sharpness or luminance. Kept as a flag for experiments.
QUANTIZE_COLORS = 0

# THE fix for the denoiser's tonal compression. The model darkens every unit
# (measured -16.5 mean luminance, highlights worst hit) and because gradient
# magnitude scales with local contrast, that crushed contrast READS AS BLUR --
# "bigger and blurrier" was substantially "bigger and flatter". Matching the
# output's per-channel histogram back to the ORIGINAL's, over content pixels
# only, took a 109-unit batch from 2 passing all gates to 59, and moved
# sharpness from ~0.52 of the geometry-only baseline to 0.83-0.96.
#
# NOTE it must be histogram MATCHING, not palette mapping. Snapping each pixel
# to its nearest original colour was tried and fails: it preserves the wrong
# tonal distribution, because a dark pixel simply finds the darkest original
# colour. The redistribution is the whole point.
MATCH_LUMINANCE = True

# Silhouette edge softening, in pixels. The mask is binary, so compositing
# through it slices AI content against a hard 1-pixel step -- visible as chewed
# muzzles and wing spars. Feathering lets content fall off into the key instead.
# Applied OUTWARD only (max of hard and blurred), so it never thins the interior.
FEATHER = 0.4

PROMPTS_CSV = Path(__file__).resolve().parent / "momjr_csv" / "unit_art_prompts.csv"

STYLE_SUFFIX = (
    "fantasy strategy game unit sprite, single centered figure, full body, "
    "facing right, painted illustration, clean readable silhouette, "
    "solid pure black background, consistent art style, high detail"
)
NEGATIVE = "text, watermark, border, frame, multiple figures, cropped, blurry"

# Assets under a unit-art filename that are not unit art. SPRITE_B9 is a shield
# glyph beside a green progress bar -- UI chrome, verified by eye 2026-09-03.
# Restyling it as a creature would be actively wrong.
DEFAULT_SKIP = {"SPRITE_B9", "ICON_UNIT_B9"}

PILOT_UNITS = [
    # deliberately spans the measured range, incl. three of the five worst
    "DWARF_CROSSBOW", "VAMPIRE", "EFREET", "MINION", "CRUSADER",
    "MINOTAUR", "UNDEAD_DRAGON", "WYVERN", "STEAM_CANNON", "STORM_DRAKE",
]
PILOT_DENOISE = [0.30, 0.42, 0.55]


# -- Geometry -----------------------------------------------------------------

def despeckle(mask: Image.Image, min_px: int = 6) -> Image.Image:
    """
    Drop lit connected components smaller than `min_px`.

    The shipped masters carry scattered single-pixel blue flecks across the black
    field (visible in every SPRITE_B* file). They are not art: they inflate the
    content bbox, they survive build_sprites' border flood-fill as floating
    opaque dots because the black around them keys but they do not, and as
    img2img input they are noise the model tries to interpret. 4-connectivity,
    iterative flood fill -- the frame is 19200 px, so cost is irrelevant.
    """
    w, h = mask.size
    px = mask.load()
    seen = bytearray(w * h)
    out = Image.new("L", (w, h), 0)
    op = out.load()
    for sy in range(h):
        for sx in range(w):
            if seen[sy * w + sx] or not px[sx, sy]:
                continue
            comp, stack = [], [(sx, sy)]
            seen[sy * w + sx] = 1
            while stack:
                x, y = stack.pop()
                comp.append((x, y))
                for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                    if 0 <= nx < w and 0 <= ny < h and not seen[ny * w + nx] and px[nx, ny]:
                        seen[ny * w + nx] = 1
                        stack.append((nx, ny))
            if len(comp) >= min_px:
                for x, y in comp:
                    op[x, y] = 255
    return out


def content_mask(im: Image.Image, min_px: int = 6) -> Image.Image:
    """
    Return an 'L' mask: 255 where the art is, 0 on the border-connected background.

    Keying delegates to build_sprites._key_background, which is the spec-mandated
    border flood-fill -- a global black threshold would erase the large pure-black
    interiors fantasy units are full of (specs/ctp2-sprites.spec.md).
    """
    rgba = im.convert("RGBA")
    _key_background(rgba, BG_KEY_TOLERANCE)
    mask = rgba.split()[-1].point(lambda v: 255 if v else 0)
    return despeckle(mask, min_px) if min_px > 1 else mask


def robust_extent(mask: Image.Image, keep: float = 0.99) -> tuple[int, int, int, int]:
    """
    Bounding box of the central `keep` fraction of the mask's lit MASS, per axis.

    WHY. A plain getbbox() is decided by the single most extreme lit pixel, and
    several masters carry scattered specks near the frame edge. Measured
    2026-09-03: SPRITE_MINOTAUR's raw bbox spans 151 of 160 px, yet only 71
    columns are lit at all and the box is 18% full; SPRITE_APPRENTICE is a
    0.20-fill band. Scaling off those boxes sizes the unit to its noise, which
    is why the wide outliers kept landing under the 0.861 threshold.

    Used for the SCALE only. The crop still uses the full bbox, so a thin
    protrusion (the SPEARMEN spear tip that a previous over-zoom severed) is
    never cut -- it just no longer dominates the sizing.
    """
    px = mask.load()
    w, h = mask.size
    cols = [sum(1 for y in range(h) if px[x, y]) for x in range(w)]
    rows = [sum(1 for x in range(w) if px[x, y]) for y in range(h)]

    def span(counts: list[int]) -> tuple[int, int]:
        total = sum(counts)
        if total <= 0:
            return 0, len(counts)
        drop = total * (1.0 - keep) / 2.0
        acc, lo = 0.0, 0
        for i, c in enumerate(counts):
            acc += c
            if acc > drop:
                lo = i
                break
        acc, hi = 0.0, len(counts)
        for i in range(len(counts) - 1, -1, -1):
            acc += counts[i]
            if acc > drop:
                hi = i + 1
                break
        return lo, max(lo + 1, hi)

    x0, x1 = span(cols)
    y0, y1 = span(rows)
    return x0, y0, x1, y1


def family_of(stem: str) -> str:
    """'icon' for ICON_UNIT_*, else 'sprite' -- selects the width cap."""
    return "icon" if stem.upper().startswith("ICON_UNIT_") else "sprite"


def normalize_geometry(im: Image.Image, family: str = "sprite",
                       out_w: int = ICON_W, out_h: int = ICON_H
                       ) -> tuple[Image.Image, Image.Image, float] | None:
    """
    Scale the unit's content to TARGET_H_FRAC tall on a black 160x120 canvas,
    aspect preserved, backing off only if that would overrun MAX_W_FRAC[family].

    Unlike build_sprites._normalize_to_stock_extent and build_unit_icon_art.fit_pad,
    this deliberately permits scale > 1.0 -- enlarging the under-scaled masters IS
    the bug being fixed here.

    Returns (rgb_canvas, mask_canvas, clipped_fraction), or None when the source
    has no content at all.
    """
    mask = content_mask(im)
    box = mask.getbbox()
    if box is None:
        return None
    bw, bh = box[2] - box[0], box[3] - box[1]
    if bw <= 0 or bh <= 0:
        return None

    # Scale so the mass-robust extent -- not the outermost speck -- hits target.
    rx0, ry0, rx1, ry1 = robust_extent(mask)
    rw, rh = max(1, rx1 - rx0), max(1, ry1 - ry0)
    scale = min(ICON_W * MAX_W_FRAC[family] / rw, ICON_H * TARGET_H_FRAC / rh)

    # `out_w/out_h` let the caller render this SAME framing straight to the
    # model's working resolution, in ONE resample from the native pixels.
    #
    # WHY IT MATTERS. Building at 160x120 and then enlarging to 512x384 for the
    # model stacks two magnifying interpolations, the first at the lowest
    # resolution in the chain -- so a small unit's detail is already destroyed
    # before the denoiser ever sees it, and it paints over mush. That was the
    # whole cause of the "too blurry" batch of 2026-09-03; measured A/B on
    # SPEARMEN and DWARF_CROSSBOW, one resample at the SAME denoise is visibly
    # sharper (armour plates, helmet, colour accents all survive). NEAREST is
    # used for the magnification because the source is pixel art: it carries the
    # original pixels up intact instead of pre-blending them.
    k = out_w / ICON_W
    scale *= k

    # Crop the FULL bbox so nothing is severed mid-figure, but centre on the
    # robust CENTROID and let whatever still falls outside the canvas clip. A
    # hard "the full bbox must fit" clamp was tried first and defeated the whole
    # point: it let one far-flung speck drag the scale back down, leaving 58 of
    # 87 sprites under the threshold again (measured 2026-09-03).
    nw, nh = max(1, round(bw * scale)), max(1, round(bh * scale))
    kern = Image.NEAREST if scale > 1.0 else Image.LANCZOS
    content = im.convert("RGB").crop(box).resize((nw, nh), kern)
    cmask = mask.crop(box).resize((nw, nh), kern).point(lambda v: 255 if v > 127 else 0)

    # centroid of the robust box, expressed in the scaled crop's coordinates
    cx = (((rx0 + rx1) / 2.0) - box[0]) * scale
    cy = (((ry0 + ry1) / 2.0) - box[1]) * scale
    at = (round(out_w / 2.0 - cx), round(out_h / 2.0 - cy))

    canvas = Image.new("RGB", (out_w, out_h), (0, 0, 0))
    mcanvas = Image.new("L", (out_w, out_h), 0)
    canvas.paste(content, at, cmask)
    mcanvas.paste(cmask, at)

    # How much lit mass fell off the canvas. Both sides are measured AFTER the
    # rescale, so this is a like-for-like ratio. The caller refuses to write a
    # unit that loses real art rather than silently shipping a clipped figure.
    before = sum(cmask.point(lambda v: 1 if v else 0).getdata())
    after = sum(mcanvas.point(lambda v: 1 if v else 0).getdata())
    clip = 0.0 if before <= 0 else max(0.0, 1.0 - after / before)
    return canvas, mcanvas, clip


def match_luminance(cand: Image.Image, orig: Image.Image,
                    mask: Image.Image) -> Image.Image:
    """
    Redistribute the candidate's per-channel histogram onto the ORIGINAL's,
    over content pixels only.

    Require : `cand` and `mask` are the same size; `orig` is the source master.
    Guarantee: returns a same-size RGB image whose content-pixel tonal
               distribution matches the original's; background is untouched.
    Failure  : an empty content region returns the candidate unchanged.

    See MATCH_LUMINANCE for why this exists and why palette mapping is not a
    substitute. Sampling the reference WITH replacement to the candidate's pixel
    count is deliberate -- the two masks differ in area after normalisation, and
    match_histograms compares distributions, not positions.
    """
    import numpy as np
    from skimage.exposure import match_histograms

    om = np.array(content_mask(orig)) > 0
    cm = np.array(mask) > 0
    src = np.array(orig.convert("RGB"))[om]
    dst = np.array(cand.convert("RGB"))[cm]
    if src.size == 0 or dst.size == 0:
        return cand

    ref = src[np.random.default_rng(0).integers(0, len(src), size=len(dst))]
    matched = match_histograms(dst.astype(np.float64).reshape(-1, 1, 3),
                               ref.astype(np.float64).reshape(-1, 1, 3),
                               channel_axis=-1)
    out = np.array(cand.convert("RGB")).astype(np.float64)
    out[cm] = matched.reshape(-1, 3)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


def feather(mask: Image.Image, radius: float = FEATHER) -> Image.Image:
    """
    Soften the silhouette edge so the composite does not read as a cut-out.

    The mask is binary, so pasting through it lands a hard 1-pixel step at every
    boundary -- visible as jagged chewing on fine features (the wolf's muzzle,
    the drake's wing spars). Blurring the alpha lets the AI content fall off
    into the key instead of being sliced against it.

    Only the OUTER edge is softened: the interior stays fully opaque, so this
    cannot thin solid regions. The blend still bottoms out at the background
    key, and compose() lifts the survivors to EDGE_FLOOR afterwards so a
    feathered pixel is never dark enough to be eaten by the downstream
    border flood-fill.
    """
    if radius <= 0:
        return mask
    from PIL import ImageChops, ImageFilter
    soft = mask.filter(ImageFilter.GaussianBlur(radius))
    # max(hard, soft): inside stays fully opaque, outside gains the falloff.
    # A plain blur would also eat INWARD and thin every fine feature.
    return ImageChops.lighter(mask, soft)


def compose(ai_rgb: Image.Image, mask: Image.Image,
            quantize: int = QUANTIZE_COLORS,
            orig: Image.Image | None = None,
            feather_px: float = FEATHER) -> Image.Image:
    """
    Reapply the geometric mask verbatim over the AI output.

    This is the safety property of the whole round-trip: the silhouette cannot
    drift, and the background comes back exactly (0,0,0), so build_sprites'
    border flood-fill still keys it and never eats into the art.
    """
    # DOWNSAMPLE, not LANCZOS. The upscaler's whole job was to harden edges; a
    # smooth kernel here averages them straight back out, which is what made the
    # first full batch read blurry at 96x72. Quantising afterwards collapses the
    # remaining gradients into flat regions -- the thing that actually reads as
    # period-correct sprite art rather than a shrunk painting.
    small = ai_rgb.convert("RGB").resize((ICON_W, ICON_H), DOWNSAMPLE)
    # Tonal correction BEFORE quantisation, so the palette is chosen from the
    # corrected image rather than from the model's compressed range.
    if orig is not None and MATCH_LUMINANCE:
        small = match_luminance(small, orig, mask)
    if quantize:
        small = small.quantize(colors=quantize, dither=Image.Dither.NONE).convert("RGB")

    soft = feather(mask, feather_px)
    out = Image.new("RGB", (ICON_W, ICON_H), (0, 0, 0))
    out.paste(small, (0, 0), soft)

    # Lift near-black art up to DARK_FLOOR, exactly as build_sprites does before
    # encoding. WHY: the mask guarantees the BACKGROUND is (0,0,0), but the model
    # also paints near-black pixels at the figure's own edge, and downstream
    # keying is a border flood-fill with BG_KEY_TOLERANCE -- so those edge pixels
    # are contiguous with the background and get eaten, eroding the silhouette.
    # Measured on the first two-stage batch: MINOTAUR lost 17% of its mask area
    # this way, STORM_DRAKE 6%. Lift ONLY inside the HARD mask.
    #
    # Lifting the FEATHERED rim as well was tried and is wrong: it forces every
    # softened pixel up to EDGE_FLOOR, which against a black key reads as a grey
    # HALO ringing the figure -- clearly visible at feather 1.6. The rim is meant
    # to fade INTO the key; the faintest part keying away is the anti-aliasing
    # working, not erosion. The hard interior is what must never be eaten
    # (specs/ctp2-sprites.spec.md forbids a global black key for that reason).
    px = out.load()
    mp = mask.load()
    for y in range(ICON_H):
        for x in range(ICON_W):
            if not mp[x, y]:
                continue
            r, g, b = px[x, y]
            if r + g + b <= BG_KEY_TOLERANCE:
                px[x, y] = (max(r, EDGE_FLOOR), max(g, EDGE_FLOOR), max(b, EDGE_FLOOR))
    return out


def ident_of(stem: str) -> str:
    """SPRITE_STORM_DRAKE / ICON_UNIT_STORM_DRAKE -> 'STORM_DRAKE'."""
    name = stem.upper()
    for pre in ("ICON_UNIT_", "SPRITE_"):
        if name.startswith(pre):
            return name[len(pre):]
    return name


def load_flips(path: Path = PROMPTS_CSV) -> dict[str, str]:
    """
    ident -> 'vertical' | 'horizontal' | 'both', for source art shipped inverted.

    SPRITE_LAMP shipped UPSIDE DOWN: the lid finial sits underneath the body and
    the shading is dark-on-top, which is an object's underside. Flipped, it is an
    unmistakable genie lamp. The harmoniser faithfully reproduced the error and
    then rendered it in higher fidelity, which is how it got noticed.

    This is a correction to the SOURCE, applied before keying and normalisation,
    so the denoiser is never asked to make sense of an inverted object. Note the
    horizontal case is NOT the same as build_sprites' facing flip, which is about
    a unit appearing to move backwards (specs/ctp2-sprites.spec.md); this one is
    about the art being wrong in the file.
    """
    flips: dict[str, str] = {}
    if not path.exists():
        return flips
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            ident = (row.get("ident") or "").strip().upper()
            val = (row.get("flip") or "").strip().lower()
            if ident and val and val not in ("", "none", "no"):
                flips[ident] = val
    return flips


_FLIPS: dict[str, str] | None = None


def apply_flip(im: Image.Image, stem: str) -> Image.Image:
    """Correct source art that shipped inverted, before anything else touches it."""
    global _FLIPS
    if _FLIPS is None:
        _FLIPS = load_flips()
    how = _FLIPS.get(ident_of(stem))
    if how in ("vertical", "both"):
        im = im.transpose(Image.FLIP_TOP_BOTTOM)
    if how in ("horizontal", "both"):
        im = im.transpose(Image.FLIP_LEFT_RIGHT)
    return im


def load_prompt_notes(path: Path = PROMPTS_CSV) -> dict[str, str]:
    """
    ident -> authored description of what the art actually shows.

    Authored 2026-09-03 by reading all 87 SPRITE_*.tga by eye, because the
    filename is not a reliable description of the art. Two separate problems it
    solves, both observed:

      * the name is right but underspecified -- "undead dragon" left the model to
        decide what the pale blue diagonal streak was, and it chose a LANCE; the
        note says "a streak of ice lightning". Likewise "minotaur" produced a
        skull-like face until the note said "a bull's snout".
      * the name is WRONG -- roughly a fifth of the roster carries proxy art from
        another unit (ORC is a wolf, GOBLIN is a boar, CRYSTAL_GOLEM is a
        fireball, SETTLER is the WRAITH art). Prompting those by name would have
        the denoiser repaint a wolf into an orc, silently replacing the art.

    The csv's art_matches_name column records which is which; the prompt always
    describes what is THERE, never what the name claims.
    """
    notes: dict[str, str] = {}
    if not path.exists():
        return notes
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            ident = (row.get("ident") or "").strip().upper()
            text = (row.get("prompt") or "").strip()
            if ident and text:
                notes[ident] = text
    return notes


_NOTES: dict[str, str] | None = None


def prompt_for(stem: str) -> str:
    """Authored description if we have one, else the filename, else generic."""
    global _NOTES
    if _NOTES is None:
        _NOTES = load_prompt_notes()

    ident = ident_of(stem)
    subject = _NOTES.get(ident)
    if not subject:
        subject = ident.replace("_", " ").strip().lower()
        # SPRITE_B3..B8 are real units whose filenames carry no subject at all;
        # the literal token "b3" would have the model invent something unrelated.
        if not subject or re.fullmatch(r"b?\d+[a-z]?", subject):
            subject = "fantasy creature"
    # The pixel-art LoRA has no trigger token; it keys off the phrase itself.
    return f"{LORA_TRIGGER}, {subject}, {STYLE_SUFFIX}"


# -- ComfyUI client -----------------------------------------------------------

def _post(path: str, data: bytes, content_type: str, timeout: int = 120) -> dict:
    req = urllib.request.Request(
        f"{COMFY_HOST}{path}", data=data, headers={"Content-Type": content_type}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def upload_image(im: Image.Image, name: str) -> str:
    """POST /upload/image as multipart; returns the server-side filename."""
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    b = uuid.uuid4().hex
    parts = []
    for field, value in (("type", "input"), ("overwrite", "true")):
        parts.append(
            f'--{b}\r\nContent-Disposition: form-data; name="{field}"\r\n\r\n{value}\r\n'.encode()
        )
    parts.append(
        f'--{b}\r\nContent-Disposition: form-data; name="image"; filename="{name}"\r\n'
        f"Content-Type: image/png\r\n\r\n".encode()
        + buf.getvalue()
        + b"\r\n"
    )
    parts.append(f"--{b}--\r\n".encode())
    res = _post("/upload/image", b"".join(parts), f"multipart/form-data; boundary={b}")
    sub = res.get("subfolder") or ""
    return f"{sub}/{res['name']}" if sub else res["name"]


def build_graph(filename: str, prompt: str, denoise: float, steps: int, seed: int,
                denoise_late: float = 0.0, steps_late: int = 6,
                upscale: float = 1.5, lora_strength: float = LORA_STRENGTH,
                upscale_model: str = UPSCALE_MODEL) -> dict:
    """
    Z-Image-Turbo img2img, API format. Single- or two-stage.

    z_image_turbo is the diffusion-model-only repack: CheckpointLoaderSimple
    would hand back CLIP=None/VAE=None, so the split loader chain is required.
    cfg=1.0 because the model is distilled -- the negative is structurally
    required by KSampler but ignored at that cfg.

    TWO-STAGE (denoise_late > 0), the ladder proven on the sd-worker 2026-09-03:

        VAEEncode@early -> KSampler(denoise) -> LatentUpscale x`upscale` bislerp
                        -> KSampler(denoise_late) -> VAEDecode

    The restyle happens in the early pass at low resolution, where the model
    actually repaints; the late pass runs at high resolution and low denoise, so
    it adds detail without re-deciding what anything IS. That split is what fixes
    the invented semantics -- one big single-stage jump gave the model enough
    freedom to read an ice-lightning streak as a lance and a bull's snout as a
    skull. Upscaling in LATENT space (not pixel space) keeps the second pass
    anchored on the first pass's composition.

    Measured here 2026-09-03 and consistent with that split: at 640 the model
    fully repaints, at 1024 it comes back near-identity. Those are the two jobs.
    """
    g = {
        "1": {"class_type": "UNETLoader",
              "inputs": {"unet_name": UNET_NAME, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": CLIP_NAME, "type": CLIP_TYPE}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": VAE_NAME}},
        "4": {"class_type": "LoadImage", "inputs": {"image": filename}},
        "5": {"class_type": "VAEEncode", "inputs": {"pixels": ["4", 0], "vae": ["3", 0]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": NEGATIVE, "clip": ["2", 0]}},
    }
    model = ["1", 0]
    if lora_strength > 0:
        g["20"] = {"class_type": "LoraLoaderModelOnly",
                   "inputs": {"model": ["1", 0], "lora_name": LORA_NAME,
                              "strength_model": lora_strength}}
        model = ["20", 0]
    g["8"] = {"class_type": "KSampler",
              "inputs": {"model": model, "seed": seed, "steps": steps, "cfg": 1.0,
                         "sampler_name": "euler", "scheduler": "simple",
                         "positive": ["6", 0], "negative": ["7", 0],
                         "latent_image": ["5", 0], "denoise": denoise}}
    tail = "8"
    if denoise_late > 0:
        g["11"] = {"class_type": "LatentUpscale",
                   "inputs": {"samples": ["8", 0], "upscale_method": "bislerp",
                              "width": _mul16(WORK_W, upscale),
                              "height": _mul16(WORK_H, upscale), "crop": "disabled"}}
        g["12"] = {"class_type": "KSampler",
                   "inputs": {"model": model, "seed": seed + 1, "steps": steps_late,
                              "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple",
                              "positive": ["6", 0], "negative": ["7", 0],
                              "latent_image": ["11", 0], "denoise": denoise_late}}
        tail = "12"
    g["9"] = {"class_type": "VAEDecode", "inputs": {"samples": [tail, 0], "vae": ["3", 0]}}

    # Pixel-space refine before the client downsamples. An ESRGAN trained on
    # sprites hardens edges instead of smoothing them, and those hard edges are
    # what survive the reduction to 96x72. Latent upscale alone cannot do this --
    # it feeds the VAE, which is exactly where the softness comes from.
    img = ["9", 0]
    if upscale_model:
        g["21"] = {"class_type": "UpscaleModelLoader",
                   "inputs": {"model_name": upscale_model}}
        g["22"] = {"class_type": "ImageUpscaleWithModel",
                   "inputs": {"upscale_model": ["21", 0], "image": ["9", 0]}}
        img = ["22", 0]
    g["10"] = {"class_type": "SaveImage",
               "inputs": {"images": img, "filename_prefix": "mom_harmonize"}}
    return g


def run_graph_with_text(graph: dict, timeout: int = 300
                        ) -> tuple[Image.Image, list[str]]:
    """
    Run a graph and return (image, text_outputs).

    Exists because a VLM-captioning graph produces BOTH an image and the caption
    that drove it, and the caption is worth keeping independently of the pixels.
    Fetching it here costs nothing: it is already in the same /history response.
    """
    img, texts = _run(graph, timeout)
    return img, texts


def run_graph(graph: dict, timeout: int = 300) -> Image.Image:
    """Queue the graph, poll /history, fetch the PNG. Raises on server error."""
    return _run(graph, timeout)[0]


def run_graph_text_only(graph: dict, timeout: int = 300
                        ) -> tuple[None, list[str]]:
    """
    Run a graph that produces TEXT and no image (e.g. captioning alone).

    Separate from _run because that one treats a missing image as an error. A
    caption-only graph legitimately has none, and running captioning as its own
    pass is what keeps the VLM resident -- interleaving it with sampling evicts
    a model per unit and costs 4-6x (measured: 65s+45s separately vs 240-380s
    interleaved).
    """
    body = json.dumps({"prompt": graph, "client_id": uuid.uuid4().hex}).encode()
    try:
        res = _post("/prompt", body, "application/json")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"ComfyUI rejected the graph: {e.read().decode()[:600]}") from e
    if res.get("node_errors"):
        raise RuntimeError(f"ComfyUI node_errors: {res['node_errors']}")
    pid = res["prompt_id"]
    deadline = time.time() + timeout
    while time.time() < deadline:
        with urllib.request.urlopen(f"{COMFY_HOST}/history/{pid}", timeout=30) as r:
            hist = json.loads(r.read().decode("utf-8"))
        if pid in hist:
            texts: list[str] = []
            for v in hist[pid].get("outputs", {}).values():
                if isinstance(v, dict) and v.get("text"):
                    texts.extend(t for t in v["text"] if isinstance(t, str))
            return None, texts
        time.sleep(0.5)
    raise RuntimeError(f"prompt {pid} did not finish within {timeout}s")


def _run(graph: dict, timeout: int = 300) -> tuple[Image.Image, list[str]]:
    """Shared implementation: returns the decoded image and any text outputs."""
    body = json.dumps({"prompt": graph, "client_id": uuid.uuid4().hex}).encode()
    try:
        res = _post("/prompt", body, "application/json")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"ComfyUI rejected the graph: {e.read().decode()[:600]}") from e
    if res.get("node_errors"):
        raise RuntimeError(f"ComfyUI node_errors: {res['node_errors']}")
    pid = res["prompt_id"]

    deadline = time.time() + timeout
    while time.time() < deadline:
        with urllib.request.urlopen(f"{COMFY_HOST}/history/{pid}", timeout=30) as r:
            hist = json.loads(r.read().decode("utf-8"))
        if pid in hist:
            # Find the image output by SEARCHING, not by assuming node id "10".
            # zimage_graph names nodes semantically ("save"), and hardcoding the
            # id silently discarded two successful generations.
            all_outs = hist[pid].get("outputs", {})
            outs = next((v["images"] for v in all_outs.values()
                         if isinstance(v, dict) and v.get("images")), [])
            if not outs:
                raise RuntimeError(
                    f"prompt {pid} finished with no image. outputs={list(all_outs)} "
                    f"status={hist[pid].get('status')}")
            info = outs[0]
            texts: list[str] = []
            for v in all_outs.values():
                if isinstance(v, dict) and v.get("text"):
                    texts.extend(t for t in v["text"] if isinstance(t, str))
            q = urllib.parse.urlencode({"filename": info["filename"],
                                        "subfolder": info.get("subfolder", ""),
                                        "type": info.get("type", "output")})
            with urllib.request.urlopen(f"{COMFY_HOST}/view?{q}", timeout=60) as r:
                return Image.open(io.BytesIO(r.read())).convert("RGB"), texts
        time.sleep(0.5)
    raise RuntimeError(f"prompt {pid} did not finish within {timeout}s")


# -- Driver -------------------------------------------------------------------

def restyle(base: Image.Image, mask: Image.Image, stem: str,
            denoise: float, steps: int, seed: int,
            denoise_late: float = 0.0, steps_late: int = STEPS_LATE,
            upscale: float = UPSCALE, lora_strength: float = LORA_STRENGTH,
            upscale_model: str = UPSCALE_MODEL,
            quantize: int = QUANTIZE_COLORS,
            orig: Image.Image | None = None) -> Image.Image:
    # `base` already arrives at WORK_W x WORK_H, rendered in a single resample
    # from the native pixels -- see normalize_geometry. Do NOT enlarge here.
    assert base.size == (WORK_W, WORK_H), f"expected work-res input, got {base.size}"
    fn = upload_image(base, f"mom_{stem}_{seed}.png")
    ai = run_graph(build_graph(fn, prompt_for(stem), denoise, steps, seed,
                               denoise_late, steps_late, upscale,
                               lora_strength, upscale_model))
    return compose(ai, mask, quantize, orig)


def install_from(staged: Path, in_dir: Path, dry_run: bool) -> int:
    """
    Copy verified staged art over the masters, backing each original up first.

    WHY THIS EXISTS. Generation writes to --out-dir so a ~3 hour batch can be
    reviewed before it touches the mod. Without an install step the only way to
    apply the result is to re-run without --out-dir, i.e. pay for the whole batch
    a second time AND get different images, since every unit is sampled afresh.

    Require : `staged` holds files whose names match masters in `in_dir`.
    Guarantee: every file written has its original in <in_dir>/_art_backup/ first;
               a staged file is refused unless it is a readable 160x120 TGA whose
               corner pixel is exactly the background key, so a truncated or
               half-written batch cannot be installed over good art.
    """
    backup = in_dir / "_art_backup"
    files = sorted(staged.glob("*.tga")) + sorted(staged.glob("*.TGA"))
    files = sorted(set(files), key=lambda f: f.name.upper())
    installed = refused = 0
    for f in files:
        dest = in_dir / f.name
        if not dest.exists():
            print(f"  REFUSE {f.name}: no master of that name")
            refused += 1
            continue
        try:
            im = Image.open(f)
            corner = im.convert("RGB").load()[0, 0]
            if im.size != (ICON_W, ICON_H):
                raise ValueError(f"size {im.size}")
            if corner != (0, 0, 0):
                raise ValueError(f"corner {corner} is not the background key")
        except Exception as e:                                  # noqa: BLE001
            print(f"  REFUSE {f.name}: {e}")
            refused += 1
            continue
        if dry_run:
            print(f"  WOULD INSTALL {f.name}")
            continue
        backup.mkdir(exist_ok=True)
        if not (backup / dest.name).exists():
            shutil.copy2(dest, backup / dest.name)
        shutil.copy2(f, dest)
        installed += 1
        print(f"  INSTALL {f.name}")
    print(f"\ninstalled={installed} refused={refused}")
    if installed:
        print(f"originals backed up in {backup}")
        print("next: python tools\\build_sprites.py --force, then rebuild mom.zip")
    return 1 if refused else 0


def select_files(in_dir: Path, family: str, only: list[str], limit: int | None,
                 ext: str = "tga") -> list[Path]:
    """Unit art files of a family, sorted and de-duplicated.

    `ext` exists because the same selection is needed over the shipped .tga
    masters AND over exported .png derivatives; hardcoding "tga" silently
    returned nothing for a PNG directory rather than failing.
    """
    stem = {"sprite": ["SPRITE_*"], "icon": ["ICON_UNIT_*"],
            "both": ["SPRITE_*", "ICON_UNIT_*"]}[family]
    pats = [f"{s}.{ext}" for s in stem]
    files: list[Path] = []
    for p in pats:
        for f in in_dir.glob(p):
            files.append(f)
        for f in in_dir.glob(p.upper()):   # shipped mix of .tga / .TGA
            if f not in files:
                files.append(f)
    if only:
        want = {o.upper() for o in only}
        files = [f for f in files if any(w in f.stem.upper() for w in want)]
    files = [f for f in files if f.stem.upper() not in DEFAULT_SKIP]
    # glob is case-insensitive on this filesystem, so *.tga and *.TGA collide
    files = sorted(set(files), key=lambda f: f.name.upper())
    return files[:limit] if limit else files


def main() -> int:
    default_pics = Path(
        r"H:\Program Files(x86)\Activision\Call To Power 2\Scenarios\mom"
        r"\scen0000\default\graphics\pictures"
    )
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in-dir", type=Path, default=default_pics)
    ap.add_argument("--out-dir", type=Path, default=None,
                    help="write here instead of over the masters (implies no backup)")
    ap.add_argument("--family", choices=["sprite", "icon", "both"], default="both")
    ap.add_argument("--only", default="", help="comma-separated name fragments")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--denoise", type=float, default=DENOISE_EARLY,
                    help="early-pass denoise (the restyle)")
    ap.add_argument("--steps", type=int, default=STEPS_EARLY)
    ap.add_argument("--denoise-late", type=float, default=DENOISE_LATE,
                    help="late-pass denoise after latent upscale; 0 = single-stage")
    ap.add_argument("--steps-late", type=int, default=STEPS_LATE)
    ap.add_argument("--upscale", type=float, default=UPSCALE,
                    help="latent upscale factor between the two passes")
    ap.add_argument("--lora-strength", type=float, default=LORA_STRENGTH,
                    help=f"{LORA_NAME} strength; 0 disables the pixel-art LoRA")
    ap.add_argument("--upscale-model", default=UPSCALE_MODEL,
                    help="ESRGAN model for the pixel-space refine; '' disables")
    ap.add_argument("--quantize", type=int, default=QUANTIZE_COLORS,
                    help="palette-quantise the result to N colours; 0 disables")
    ap.add_argument("--seed", type=int, default=12345)
    ap.add_argument("--max-clip", type=float, default=0.02,
                    help="refuse a unit that would lose more than this fraction of "
                         "its lit art off-canvas (default 2%%)")
    ap.add_argument("--geometry-only", action="store_true",
                    help="skip ComfyUI entirely; fixes the scale bug with no AI")
    ap.add_argument("--pilot", action="store_true",
                    help="PILOT_UNITS x PILOT_DENOISE into --out-dir; masters untouched")
    ap.add_argument("--resume", action="store_true",
                    help="skip outputs that already exist in --out-dir")
    ap.add_argument("--install-from", type=Path, default=None,
                    help="copy verified staged art from this dir over the masters "
                         "(with backup) instead of generating anything")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not args.in_dir.is_dir():
        print(f"FATAL: no such dir {args.in_dir}", file=sys.stderr)
        return 2

    if args.install_from:
        if not args.install_from.is_dir():
            print(f"FATAL: no such dir {args.install_from}", file=sys.stderr)
            return 2
        print(f"installing from {args.install_from} -> {args.in_dir}"
              f"{' [DRY RUN]' if args.dry_run else ''}")
        return install_from(args.install_from, args.in_dir, args.dry_run)

    only = [s for s in args.only.split(",") if s.strip()]
    if args.pilot:
        # --pilot supplies the default unit set, but must not silently discard an
        # explicit --only: doing so made a "finish the last 4" run restart from
        # unit 1 and burn 20 minutes redoing work that was already on disk.
        only = only or PILOT_UNITS
        if not args.out_dir:
            print("FATAL: --pilot requires --out-dir (masters must not be touched)",
                  file=sys.stderr)
            return 2

    files = select_files(args.in_dir, args.family, only, args.limit)
    if not files:
        print("FATAL: no files matched", file=sys.stderr)
        return 2

    denoises = PILOT_DENOISE if args.pilot else [args.denoise]
    if args.out_dir:
        args.out_dir.mkdir(parents=True, exist_ok=True)
    backup = args.in_dir / "_art_backup"

    print(f"{len(files)} file(s), family={args.family}, "
          f"denoise={'pilot ' + str(denoises) if args.pilot else args.denoise}, "
          f"{'GEOMETRY ONLY' if args.geometry_only else COMFY_HOST}"
          f"{' [DRY RUN]' if args.dry_run else ''}")

    written = skipped = failed = 0
    for i, f in enumerate(files, 1):
        try:
            src = Image.open(f)
        except Exception as e:                     # unreadable -> report, never write blind
            print(f"  [{i}/{len(files)}] SKIP {f.name}: unreadable ({e})")
            skipped += 1
            continue

        src = apply_flip(src, f.stem)      # correct inverted source art FIRST
        fam = family_of(f.stem)
        # The MASK is authored at icon size (it composites the final TGA); the
        # model's INPUT is rendered separately at work size, so the native pixels
        # are magnified exactly once. Never enlarge the icon-size canvas.
        got = normalize_geometry(src, fam)
        if got is None:
            print(f"  [{i}/{len(files)}] SKIP {f.name}: no content after keying")
            skipped += 1
            continue
        base, mask, clip = got
        if not args.geometry_only:
            work = normalize_geometry(src, fam, WORK_W, WORK_H)
            if work is None:
                print(f"  [{i}/{len(files)}] SKIP {f.name}: no content at work size")
                skipped += 1
                continue
            base = work[0]
        if clip > args.max_clip:
            print(f"  [{i}/{len(files)}] SKIP {f.name}: would clip {clip:.1%} of the art "
                  f"(> --max-clip {args.max_clip:.1%})")
            skipped += 1
            continue

        for d in denoises:
            tag = f"_d{int(d * 100):02d}" if args.pilot else ""
            dest = (args.out_dir / f"{f.stem}{tag}.tga") if args.out_dir else f
            if args.resume and dest != f and dest.exists():
                print(f"  [{i}/{len(files)}] HAVE {dest.name}")
                continue
            try:
                out = base if args.geometry_only else restyle(
                    base, mask, f.stem, d, args.steps, args.seed + i,
                    args.denoise_late, args.steps_late, args.upscale,
                    args.lora_strength, args.upscale_model, args.quantize,
                    src
                )
            except Exception as e:
                print(f"  [{i}/{len(files)}] FAIL {f.name} d={d}: {e}")
                failed += 1
                continue

            if args.dry_run:
                rx0, ry0, rx1, ry1 = robust_extent(content_mask(out))
                print(f"  [{i}/{len(files)}] DRY {f.name} -> w={(rx1-rx0)/ICON_W:.2f} "
                      f"h={(ry1-ry0)/ICON_H:.2f} clip={clip:.1%}")
                continue

            if dest == f:                          # in-place: back up before first write
                backup.mkdir(exist_ok=True)
                if not (backup / f.name).exists():
                    shutil.copy2(f, backup / f.name)
            write_icon_tga(dest, out)
            written += 1
            print(f"  [{i}/{len(files)}] OK {dest.name}")

    print(f"\nwritten={written} skipped={skipped} failed={failed}")
    if not args.dry_run and not args.out_dir and written:
        print(f"originals backed up in {backup}")
        print("next: python tools\\build_sprites.py --force, then rebuild mom.zip")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
