"""Tests for install_crafted_art.py -- crafted art -> engine master format."""
from __future__ import annotations

import struct
import sys
from pathlib import Path

import pytest
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import install_crafted_art as I   # noqa: E402


def _rgba(tmp_path: Path, size=(140, 120), name="art.png",
          fill=(200, 40, 40, 255)) -> Path:
    im = Image.new("RGBA", size, (0, 0, 0, 0))
    im.paste(Image.new("RGBA", (size[0] // 2, size[1] // 2), fill),
             (size[0] // 4, size[1] // 4))
    p = tmp_path / name
    im.save(p)
    return p


def _read_tga(p: Path):
    b = p.read_bytes()
    hdr = b[:18]
    w = struct.unpack("<H", hdr[12:14])[0]
    h = struct.unpack("<H", hdr[14:16])[0]
    return {"imgtype": hdr[2], "w": w, "h": h, "bpp": hdr[16], "desc": hdr[17],
            "body": b[18:]}


def _run(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["install_crafted_art.py", *argv])
    return I.main()


def test_explicit_file_installs_sprite_and_icon_as_the_same_art(tmp_path, monkeypatch):
    pics = tmp_path / "pics"
    pics.mkdir()
    old = pics / "ICON_UNIT_NEWT.tga"
    old.write_bytes(b"stale icon")
    src = _rgba(tmp_path, name="gen.png")
    assert _run(monkeypatch, "--pics", str(pics), "--file", f"NEWT={src}",
                "--apply") == 0
    spr, ico = pics / "SPRITE_NEWT.tga", pics / "ICON_UNIT_NEWT.tga"
    assert _read_tga(spr)["w"] == 160 and _read_tga(spr)["bpp"] == 16
    assert spr.read_bytes() == ico.read_bytes()          # portrait matches map
    baks = list(pics.glob("ICON_UNIT_NEWT.tga.bak-*"))
    assert len(baks) == 1 and baks[0].read_bytes() == b"stale icon"


def test_explicit_file_that_does_not_exist_is_refused(tmp_path, monkeypatch):
    assert _run(monkeypatch, "--pics", str(tmp_path), "--file",
                f"NEWT={tmp_path / 'nope.png'}", "--apply") == 2
    assert not list(tmp_path.glob("*.tga"))


def test_dry_run_writes_nothing(tmp_path, monkeypatch):
    src = _rgba(tmp_path, name="gen.png")
    assert _run(monkeypatch, "--pics", str(tmp_path), "--file", f"NEWT={src}") == 0
    assert not list(tmp_path.glob("*.tga"))


def _blocky(native=(15, 22), k=3) -> Image.Image:
    """A native sprite with varied pixels, saved enlarged k times."""
    im = Image.new("RGBA", native, (0, 0, 0, 0))
    px = im.load()
    for y in range(2, native[1] - 2):
        for x in range(3, native[0] - 3):
            px[x, y] = ((x * 37) % 256, (y * 53) % 256, 90, 255)
    return im.resize((native[0] * k, native[1] * k), Image.NEAREST)


def test_one_colour_key_takes_exactly_that_colour_and_nothing_near_it(tmp_path):
    """Operator 2026-09-26: "pick just one color for alpha masking and no magic
    wand, it's just that pixel color only". Background (0,0,0); interior pocket
    of (0,0,0) is keyed too; (1,1,1) and (0,0,2) next to it are NOT."""
    im = Image.new("RGB", (40, 30), (0, 0, 0))
    for y in range(5, 25):
        for x in range(5, 35):
            im.putpixel((x, y), (200, 150, 90))
    for y in range(12, 18):
        for x in range(15, 25):
            im.putpixel((x, y), (0, 0, 0))            # enclosed background pocket
    im.putpixel((6, 6), (1, 1, 1))
    im.putpixel((7, 6), (0, 0, 2))
    p = tmp_path / "gen.png"
    im.save(p)
    k = I._keyed(p)
    assert k.getpixel((0, 0))[3] == 0
    assert k.getpixel((20, 15))[3] == 0              # pocket: exact key colour
    assert k.getpixel((6, 6))[3] == 255              # near-black is NOT the key
    assert k.getpixel((7, 6))[3] == 255
    assert k.getpixel((10, 10))[3] == 255


def test_key_colour_is_the_most_common_border_colour(tmp_path):
    im = Image.new("RGB", (20, 20), (255, 255, 255))
    im.putpixel((0, 0), (250, 250, 250))
    assert I.key_colour(im) == (255, 255, 255)


def test_block_size_finds_the_whole_number_enlargement():
    assert I._block_size(_blocky(k=3)) == 3
    assert I._block_size(_blocky(k=2)) == 2
    assert I._block_size(_blocky(k=1)) == 1


def test_native_grid_undo_is_lossless():
    native = _blocky(k=1)
    back = I._to_native_grid(_blocky(k=3))
    assert back.size == native.size
    assert list(back.getdata()) == list(native.getdata())


def test_non_blocky_art_is_left_alone():
    im = Image.effect_noise((60, 40), 60).convert("RGBA")
    assert I._to_native_grid(im) is im


def test_master_is_always_the_engine_frame_size(tmp_path):
    assert I.to_master(_rgba(tmp_path)).size == (160, 120)
    assert I.to_master(_rgba(tmp_path, (300, 90), "b.png")).size == (160, 120)


def test_transparent_pixels_become_the_black_key(tmp_path):
    """The engine has no alpha here -- it keys the background colour, so
    transparency must land on pure black or the tile imports opaque."""
    m = I.to_master(_rgba(tmp_path))
    assert m.getpixel((1, 1)) == (0, 0, 0)


def test_art_is_floored_off_pure_black_so_the_key_cannot_eat_it(tmp_path):
    """Near-black ART must not collide with the key. The floor is picked in
    QUANTISED space: 9 would write as 8 and land on the flood-fill tolerance."""
    src = _rgba(tmp_path, fill=(2, 2, 2, 255))
    m = I.to_master(src)
    assert m.getpixel((80, 60)) == (I.DARK_FLOOR,) * 3
    assert I.DARK_FLOOR >= 16


def test_the_floor_survives_rgb555_quantisation():
    """(v >> 3) << 3 is what the 16bpp write actually keeps."""
    assert ((I.DARK_FLOOR >> 3) << 3) >= 16


def test_opaque_colour_is_preserved(tmp_path):
    assert I.to_master(_rgba(tmp_path)).getpixel((80, 60)) == (200, 40, 40)


def test_aspect_is_contained_never_stretched(tmp_path):
    """A wide crafted image must letterbox; distorting hand-made art is a defect."""
    src = _rgba(tmp_path, (300, 60), "wide.png")
    m = I.to_master(src)
    assert m.getpixel((80, 3)) == (0, 0, 0)      # padded, not stretched


def _content_height(im: Image.Image) -> int:
    """Rows containing anything that is not the black key."""
    bbox = im.convert("L").point(lambda v: 255 if v > 16 else 0).getbbox()
    return 0 if bbox is None else bbox[3] - bbox[1]


def test_normalize_makes_differently_drawn_units_agree_in_size(tmp_path):
    """The reported defect: DWARF_CROSSBOW rendered a third the size of
    DWARF_WARRIOR because each crafted file kept whatever scale it was drawn at."""
    small = tmp_path / "small.png"
    big = tmp_path / "big.png"
    for p, box in ((small, (60, 50, 80, 70)), (big, (20, 10, 120, 110))):
        im = Image.new("RGBA", (140, 120), (0, 0, 0, 0))
        im.paste(Image.new("RGBA", (box[2] - box[0], box[3] - box[1]),
                           (200, 40, 40, 255)), (box[0], box[1]))
        im.save(p)

    raw = [_content_height(I.to_master(p)) for p in (small, big)]
    assert max(raw) - min(raw) > 20        # unnormalised: wildly different

    norm = [_content_height(I.to_master(p, normalize=True)) for p in (small, big)]
    assert abs(norm[0] - norm[1]) <= 4     # normalised: agree


def test_normalize_still_produces_the_engine_frame(tmp_path):
    assert I.to_master(_rgba(tmp_path), normalize=True).size == (160, 120)


def test_normalize_keeps_the_background_as_the_key(tmp_path):
    assert I.to_master(_rgba(tmp_path), normalize=True).getpixel((1, 1)) == (0, 0, 0)


def test_normalize_raises_rather_than_writing_an_empty_tile(tmp_path):
    """An all-transparent source has no content to scale; silently writing an
    empty frame would look like a successful install."""
    p = tmp_path / "blank.png"
    Image.new("RGBA", (140, 120), (0, 0, 0, 0)).save(p)
    with pytest.raises(ValueError):
        I.to_master(p, normalize=True)


def test_default_is_contain_not_normalize(tmp_path):
    """Art whose framing is already deliberate must not be rescaled by accident."""
    src = _rgba(tmp_path, (140, 120))
    assert _content_height(I.to_master(src)) != \
        _content_height(I.to_master(src, normalize=True))


def test_written_tga_header_matches_the_shipping_master(tmp_path):
    out = tmp_path / "SPRITE_X.tga"
    I.write_tga(out, I.to_master(_rgba(tmp_path)))
    h = _read_tga(out)
    assert (h["imgtype"], h["w"], h["h"], h["bpp"]) == (2, 160, 120, 16)
    assert h["desc"] == 0x00        # a non-zero desc byte caused the fugly bug
    assert len(h["body"]) == 160 * 120 * 2


def test_tga_is_bottom_origin(tmp_path):
    """Row 0 of the file is the BOTTOM row of the image."""
    im = Image.new("RGB", (160, 120), (0, 0, 0))
    im.putpixel((0, 119), (255, 0, 0))          # bottom-left red
    out = tmp_path / "o.tga"
    I.write_tga(out, im)
    first = struct.unpack("<H", _read_tga(out)["body"][:2])[0]
    assert (first >> 10) & 0x1F == 31           # red survives in the first row
    assert first & 0x1F == 0


def test_redraws_share_an_ident_with_their_original():
    """'priest (2).png' is a REDRAW of 'priest.png', not a second unit. Both
    must resolve to PRIEST so the newest-wins rule can choose between them."""
    assert I.NAMESAKE["priest"] == I.NAMESAKE["priest (2)"] == "PRIEST"
    assert I.NAMESAKE["arch mage"] == I.NAMESAKE["arch_mage"] == "ARCH_MAGE"
    assert I.NAMESAKE["crystal golem"] == I.NAMESAKE["crystal_golem"] == "CRYSTAL_GOLEM"


def test_newest_file_wins_when_two_files_claim_one_unit(tmp_path):
    """The stale-install trap: preferring .tga or sort order would pick the OLD
    art and still report success."""
    import os
    old = tmp_path / "priest.png"
    new = tmp_path / "priest (2).png"
    for p in (old, new):
        Image.new("RGBA", (60, 120), (200, 40, 40, 255)).save(p)
    os.utime(old, (1_600_000_000, 1_600_000_000))
    os.utime(new, (1_700_000_000, 1_700_000_000))

    found = {}
    for p in sorted(tmp_path.iterdir()):
        ident = I.NAMESAKE.get(p.stem.lower())
        if not ident:
            continue
        if ident in found and found[ident].stat().st_mtime >= p.stat().st_mtime:
            continue
        found[ident] = p
    assert found["PRIEST"].name == "priest (2).png"


def test_black_art_on_a_dark_background_is_not_cropped_away(tmp_path):
    """The operator's actual defect. A luminance-derived mask cannot tell a
    black robe from a black background, so the robe's lower half was scaled as
    if it were not there and got cropped. Alpha can tell, so framing must use
    alpha -- the ART's own colour must not influence its framing at all."""
    p = tmp_path / "darkrobe.png"
    im = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    im.paste(Image.new("RGBA", (40, 40), (220, 30, 30, 255)), (80, 20))   # bright top
    im.paste(Image.new("RGBA", (40, 100), (0, 0, 0, 255)), (80, 60))      # BLACK body
    im.save(p)

    m = I.to_master(p, normalize=True)
    from export_transparent_png import to_rgba
    out = tmp_path / "SPRITE_X.tga"
    I.write_tga(out, m)
    a = to_rgba(Image.open(out)).getchannel("A")
    box = a.getbbox()
    # the black body is ~70% of the figure's height; if it were dropped, the
    # surviving content would be barely a third as tall
    assert box[3] - box[1] >= 0.8 * 120 * 0.88 * 0.9


def test_pure_black_ART_survives_and_does_not_become_a_hole(tmp_path):
    """The defect the operator caught: 'missing black spots in the robe'.

    A black robe is ART that happens to be (0,0,0). Deciding by COLOUR treats it
    as background and leaves it at the key value, punching a transparent hole
    through the figure. ALPHA is what knows the difference.
    """
    p = tmp_path / "blackrobe.png"
    im = Image.new("RGBA", (140, 120), (0, 0, 0, 0))          # transparent bg
    im.paste(Image.new("RGBA", (60, 60), (0, 0, 0, 255)), (40, 30))  # BLACK art
    im.save(p)

    m = I.to_master(p)
    assert m.getpixel((70, 60)) == (I.DARK_FLOOR,) * 3   # art floored off the key
    assert m.getpixel((2, 2)) == (0, 0, 0)               # background still key


def test_black_art_is_not_keyed_away_by_the_engine_keyer(tmp_path):
    """End to end: write the TGA, then key it the way the game does. The robe
    must still be opaque afterwards."""
    from export_transparent_png import to_rgba
    p = tmp_path / "blackrobe2.png"
    im = Image.new("RGBA", (140, 120), (0, 0, 0, 0))
    im.paste(Image.new("RGBA", (60, 60), (0, 0, 0, 255)), (40, 30))
    im.save(p)
    out = tmp_path / "SPRITE_X.tga"
    I.write_tga(out, I.to_master(p))
    assert to_rgba(Image.open(out)).getchannel("A").getpixel((80, 60)) > 0


def _opaque_rgb(tmp_path: Path, bg, name="flat.png", fill=(200, 40, 40)) -> Path:
    """An RGB export with NO alpha -- what a .jfif/.jpg always is."""
    im = Image.new("RGB", (200, 150), bg)
    im.paste(Image.new("RGB", (60, 60), fill), (70, 45))
    p = tmp_path / name
    im.save(p)
    return p


def test_white_background_export_is_keyed_not_imported_as_a_box(tmp_path):
    """The silent failure this guards: a .jfif on white has no alpha, so
    compositing it onto the key yields an opaque white tile with the figure
    buried in it -- and size/format/opacity checks all still pass."""
    src = _opaque_rgb(tmp_path, (255, 255, 255), "white.png")
    m = I.to_master(src)
    assert m.getpixel((2, 2)) == (0, 0, 0)          # border keyed to black
    assert m.getpixel((80, 60)) != (255, 255, 255)  # not a white box


def test_black_background_export_still_works(tmp_path):
    """The other polarity must not regress -- black is already the key."""
    src = _opaque_rgb(tmp_path, (0, 0, 0), "black.png")
    m = I.to_master(src)
    assert m.getpixel((2, 2)) == (0, 0, 0)


def test_existing_alpha_is_trusted_over_re_keying(tmp_path):
    """Art that already carries transparency must not be re-derived; the
    operator's own mask is better than anything inferred from a border."""
    src = _rgba(tmp_path)
    im = I._keyed(src)
    assert im.mode == "RGBA"
    assert im.getchannel("A").getextrema()[0] == 0


def test_fully_opaque_rgba_is_re_keyed(tmp_path):
    """RGBA with a 255-everywhere alpha carries no information -- treat it as
    opaque and derive the background, or it imports as a box."""
    p = tmp_path / "opaque_rgba.png"
    im = Image.new("RGBA", (200, 150), (255, 255, 255, 255))
    im.paste(Image.new("RGBA", (60, 60), (200, 40, 40, 255)), (70, 45))
    im.save(p)
    assert I._keyed(p).getchannel("A").getextrema()[0] == 0


def test_tiny_pixel_sprite_is_upscaled_crisp_not_blurred(tmp_path):
    """A 16x31 sprite needs ~3x to reach the frame. LANCZOS would smear every
    hard edge into a gradient; NEAREST keeps the blocks. The discriminator: a
    two-colour checker stays exactly two colours under NEAREST, and grows
    intermediate values under any interpolating filter."""
    p = tmp_path / "tiny.png"
    # transparent margin like a real sprite; a frame-filling opaque image has
    # no background, and the one-colour key would take its border colour
    im = Image.new("RGBA", (18, 33), (0, 0, 0, 0))
    for y in range(1, 32):
        for x in range(1, 17):
            im.putpixel((x, y), (255, 0, 0, 255) if (x + y) % 2 else (0, 0, 255, 255))
    im.save(p)
    m = I.to_master(p, normalize=True)
    box = m.convert("L").point(lambda v: 255 if v > 16 else 0).getbbox()
    colours = {m.getpixel((x, y)) for x in range(box[0], box[2])
               for y in range(box[1], box[3])}
    # RGB555-safe: only the two source colours, no blends
    assert colours <= {(255, 0, 0), (0, 0, 255)}, colours


def test_dracolich_maps_to_the_bone_white_file_only():
    """Four variants exist; newest-wins would choose the rejected green one."""
    assert I.NAMESAKE["dracolich_"] == "DRACOLICH"
    for stem in ("dracolich", "green dracolich", "dracolich-reimainged"):
        assert stem not in I.NAMESAKE


def test_retired_art_folder_files_are_not_mapped():
    """Units the operator moved to generated art must not be overwritten by the
    next art-folder scan (2026-09-26: "use the image on the right")."""
    for stem in ("centaur", "centaur archer", "dwarf warrior", "dwarf crossbow",
                 "lich", "iron golem", "peasant", "skeleton warrior reimagined",
                 "wizard", "ogre", "orc", "orc_"):
        assert stem not in I.NAMESAKE, stem
    assert I.NAMESAKE["centaur archer reimagined"] == "CENTAUR_BOWMAN"
    assert I.NAMESAKE["minotaur_reimagined"] == "MINOTAUR_WARRIOR"


def test_descriptive_suffixes_still_resolve_to_their_unit():
    """Crafted files carry human labels ('settler reimagined'), not idents. The
    map is explicit for exactly this reason -- no string munging gets there."""
    assert I.NAMESAKE["settler reimagined"] == "SETTLER"
    assert I.NAMESAKE["storm_drake"] == "STORM_DRAKE"


def test_namesake_map_covers_the_non_obvious_names():
    """'runesmith' -> DWARF_RUNESMITH cannot be derived by string munging."""
    assert I.NAMESAKE["runesmith"] == "DWARF_RUNESMITH"
    assert I.NAMESAKE["arch mage"] == "ARCH_MAGE"
    assert I.NAMESAKE["genie_reimagined"] == "DJINN"
