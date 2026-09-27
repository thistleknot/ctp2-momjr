"""test_build_sprites.py -- one-colour keying in build_sprites and the preview.

NO GOVERNING SPEC. Basis: operator 2026-09-26, "pick just one color for alpha
masking and no magic wand, it's just that pixel color only". Supersedes the
border flood + per-unit pocket list.
"""
from __future__ import annotations

from PIL import Image, ImageDraw

import build_sprites as B
import export_transparent_png as E


def _master() -> Image.Image:
    """160x120 master: key background, a figure, an enclosed key-black pocket,
    and near-black art (8,8,8) that must NOT be keyed."""
    im = Image.new("RGB", (160, 120), (0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle((40, 20, 119, 109), fill=(120, 90, 60))
    d.rectangle((70, 50, 89, 79), fill=(0, 0, 0))       # enclosed pocket
    d.rectangle((45, 25, 54, 34), fill=(8, 8, 8))        # near-black art
    return im


def test_exact_key_makes_the_enclosed_pocket_transparent():
    f = B._key_exact(_master())
    assert f.size == (96, 72)
    assert f.getpixel((48, 38))[3] == 0                  # pocket centre
    assert f.getpixel((2, 2))[3] == 0                    # surround
    assert f.getpixel((60, 60))[3] == 255                # figure


def test_exact_key_leaves_near_black_art_opaque():
    f = B._key_exact(_master())
    # (45..54, 25..34) at 160x120 -> about (29, 18) at 96x72
    assert f.getpixel((29, 18))[3] == 255


def test_facing_edges_carry_no_black_fringe():
    f = B._key_exact(_master())
    opaque = [p for p in f.getdata() if p[3]]
    assert all(p[3] == 255 for p in opaque)              # binary key
    assert not any(p[:3] == (0, 0, 0) for p in opaque)   # makespr-safe


def test_preview_keys_the_same_single_colour():
    a = E.to_rgba(_master()).getchannel("A")
    assert a.getpixel((80, 65)) == 0                     # pocket
    assert a.getpixel((50, 30)) == 255                   # near-black art
    assert a.getpixel((100, 100)) == 255


def test_facing_images_use_the_exact_key(tmp_path):
    p = tmp_path / "SPRITE_ANY.tga"
    _master().save(p)
    f = B._facing_images(p, False)[0]
    assert sum(1 for px in f.getdata() if px[3] == 0) > 96 * 72 // 2
