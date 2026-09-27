"""test_build_sprites.py -- enclosed-pocket keying in build_sprites.

NO GOVERNING SPEC. Basis: operator items-to-work.md 2026-09-26, "background
boxes that will show in game"; measured 54/88 masters with enclosed black that
the border flood renders as dark floor.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

import build_sprites as B


def _figure_with_pocket(pocket_px: int = 10) -> Image.Image:
    """96x72: black surround, a grey ring figure enclosing a black hole."""
    im = Image.new("RGBA", (96, 72), (0, 0, 0, 255))
    d = ImageDraw.Draw(im)
    d.rectangle((30, 20, 65, 55), fill=(120, 90, 60, 255))
    d.rectangle((48 - pocket_px // 2, 38 - pocket_px // 2,
                 48 + pocket_px // 2 - 1, 38 + pocket_px // 2 - 1),
                fill=(0, 0, 0, 255))
    return im


def test_border_flood_alone_leaves_the_enclosed_pocket_opaque():
    im = _figure_with_pocket()
    B._key_background(im)
    assert im.getpixel((48, 38))[3] == 255          # drawn as a dark box
    assert im.getpixel((2, 2))[3] == 0              # surround is keyed


def test_pocket_pass_keys_the_enclosed_background():
    im = _figure_with_pocket(10)                    # 100 px pocket
    B._key_background(im)
    assert B._key_pockets(im) == 100
    assert im.getpixel((48, 38))[3] == 0
    assert im.getpixel((32, 22))[3] == 255          # the figure survives


def test_small_dark_detail_below_the_minimum_survives():
    im = _figure_with_pocket(4)                     # 16 px < POCKET_MIN_PX
    B._key_background(im)
    assert B._key_pockets(im) == 0
    assert im.getpixel((48, 38))[3] == 255


def test_only_listed_units_get_the_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "_pocket_units", lambda: {"SPRITE_LISTED"})
    for name in ("SPRITE_LISTED", "SPRITE_OTHER"):
        big = _figure_with_pocket(10).resize((160, 120), Image.NEAREST).convert("RGB")
        big.save(tmp_path / f"{name}.tga")
    listed = B._facing_images(tmp_path / "SPRITE_LISTED.tga", False)[0]
    other = B._facing_images(tmp_path / "SPRITE_OTHER.tga", False)[0]
    count = lambda im: sum(1 for p in im.getdata() if p[3] == 0)
    assert count(listed) > count(other)             # the pocket went transparent


def test_policy_list_is_read_from_mod_policy():
    units = B._pocket_units()
    assert "SPRITE_CENTAURS" in units
    assert "SPRITE_SPEARMEN" not in units           # black cloak is real art
