"""make_vessel_art.py -- draw the artifact VESSEL art the mod has no source for.

WHY THIS EXISTS. Every other unit's art came out of the civ2 MoM tree via
`civ2_sprite_extractor.py`. The vessels are a CTP2-side addition -- civ2 MoM has
no lamp, because it has no artifact mechanic -- so there is nothing to extract
and the art has to be authored. Authoring it as CODE rather than checking in an
opaque TGA keeps it in the control plane: the palette, the proportions and the
anchoring are all readable and re-runnable, and a change is a diff rather than a
binary blob.

THE FORMAT CONTRACT, measured from SPRITE_EFREET.tga rather than assumed:

  * 160x120 RGBA.
  * The background is PURE BLACK (0,0,0) and is chromakeyed out by makespr --
    it is NOT alpha. Every shipped sprite has a fully-opaque alpha channel, so
    transparency comes from the key colour alone.
  * Content is centred horizontally and runs to the BOTTOM of the canvas: a
    unit stands on its tile, so its feet sit at the canvas floor. Efreet's
    content bbox is (59,2)-(99,117), i.e. 0.97 of the height.
  * `gate_sprite_extent.py` bounds content at 0.80 of width and 0.97 of height.
    A vessel is a small ground object, so it sits far inside both -- the bound
    is an upper limit, not a target.

WHY NOT PURE BLACK IN THE ARTWORK. The key colour is black, so any black pixel
INSIDE the drawing is eaten too. Outlines therefore use a very dark brown rather
than black -- the same reason `build_unit_sprite.py` applies its DARK_FLOOR
nudge after a LANCZOS resize.

Failure modes: writing a lamp whose outline is (0,0,0) produces a lamp with
holes in it; drawing content taller than 0.97*120 trips the extent gate; drawing
it top-anchored makes the object float above its tile.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

PICTURES = Path(__file__).resolve().parent.parent / "scen0000/default/graphics/pictures"

W, H = 160, 120
KEY = (0, 0, 0)

# Brass, light to dark. OUTLINE is deliberately not black -- see module docstring.
HILIGHT = (245, 214, 130)
BRASS = (205, 158, 58)
MID = (168, 120, 36)
SHADOW = (112, 76, 20)
OUTLINE = (46, 30, 8)


def _lamp(draw: ImageDraw.ImageDraw, cx: int, floor: int, scale: float = 1.0) -> None:
    """Draw a brass oil lamp standing on `floor`, centred on `cx`.

    Geometry is expressed relative to the body ellipse so the whole object
    scales from one number. Drawn back-to-front: handle, body, spout, lid.
    """
    bw = int(64 * scale)          # body width
    bh = int(34 * scale)          # body height
    left, right = cx - bw // 2, cx + bw // 2
    top, bot = floor - bh, floor

    # Handle -- an open loop off the right shoulder, drawn first so the body
    # overlaps its inner edge and it reads as attached rather than pasted on.
    hx0, hy0 = right - int(16 * scale), top + int(2 * scale)
    hx1, hy1 = right + int(12 * scale), bot - int(4 * scale)
    draw.arc([hx0, hy0, hx1, hy1], start=290, end=110, fill=OUTLINE, width=max(4, int(6 * scale)))
    draw.arc([hx0 + 1, hy0 + 1, hx1 - 1, hy1 - 1], start=295, end=105,
             fill=MID, width=max(2, int(3 * scale)))

    # Spout -- a tapered triangle off the left shoulder.
    sx = left - int(26 * scale)
    draw.polygon([(left + int(6 * scale), top + int(8 * scale)),
                  (sx, top + int(1 * scale)),
                  (sx + int(4 * scale), top + int(11 * scale)),
                  (left + int(8 * scale), top + int(20 * scale))],
                 fill=BRASS, outline=OUTLINE)
    draw.polygon([(left + int(8 * scale), top + int(10 * scale)),
                  (sx + int(3 * scale), top + int(4 * scale)),
                  (sx + int(5 * scale), top + int(9 * scale))],
                 fill=HILIGHT)

    # Body.
    draw.ellipse([left, top, right, bot], fill=BRASS, outline=OUTLINE, width=2)
    # Lower half in shadow: a chord of the same ellipse, so the shading follows
    # the form instead of being a flat band.
    draw.chord([left, top, right, bot], start=15, end=165, fill=MID, outline=None)
    draw.chord([left + 2, top + 2, right - 2, bot - 2], start=30, end=150, fill=SHADOW)
    # Specular arc on the upper left.
    draw.arc([left + int(7 * scale), top + int(4 * scale),
              right - int(18 * scale), bot - int(9 * scale)],
             start=185, end=265, fill=HILIGHT, width=max(2, int(4 * scale)))

    # Lid and knob.
    lw = int(18 * scale)
    draw.ellipse([cx - lw // 2, top - int(7 * scale), cx + lw // 2, top + int(4 * scale)],
                 fill=MID, outline=OUTLINE)
    kr = max(2, int(4 * scale))
    draw.ellipse([cx - kr, top - int(12 * scale), cx + kr, top - int(12 * scale) + 2 * kr],
                 fill=HILIGHT, outline=OUTLINE)


def build(name: str = "LAMP") -> list[Path]:
    """Write SPRITE_<name>.tga and ICON_UNIT_<name>.tga; return what was written.

    Both surfaces are the same 160x120 RGBA format. The sprite is bottom-anchored
    so the lamp sits on its tile; the icon is centred, because an icon is a
    portrait in a box rather than a thing standing on ground.
    """
    written = []

    sprite = Image.new("RGBA", (W, H), KEY + (255,))
    _lamp(ImageDraw.Draw(sprite), cx=W // 2, floor=H - 6, scale=1.0)
    p = PICTURES / f"SPRITE_{name}.tga"
    sprite.save(p)
    written.append(p)

    icon = Image.new("RGBA", (W, H), KEY + (255,))
    _lamp(ImageDraw.Draw(icon), cx=W // 2, floor=H // 2 + 24, scale=1.10)
    p = PICTURES / f"ICON_UNIT_{name}.tga"
    icon.save(p)
    written.append(p)

    return written


def main() -> int:
    for p in build():
        im = Image.open(p).convert("RGB")
        px = im.load()
        xs = [x for x in range(W) for y in range(H) if px[x, y] != KEY]
        ys = [y for x in range(W) for y in range(H) if px[x, y] != KEY]
        wf, hf = (max(xs) - min(xs) + 1) / W, (max(ys) - min(ys) + 1) / H
        ok = "OK" if wf <= 0.80 and hf <= 0.97 else "TRIPS EXTENT GATE"
        print(f"{p.name:28s} content {wf:.2f}w {hf:.2f}h  {ok}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
