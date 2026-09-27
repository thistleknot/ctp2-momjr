"""test_style_audit.py -- offline parts of style_audit (no server needed).

NO GOVERNING SPEC. Basis: operator 2026-09-27, style-consistency plan.
"""
from __future__ import annotations

from PIL import Image, ImageDraw

import style_audit as S


def _unit(colour, noise=False) -> Image.Image:
    im = Image.new("RGB", (96, 72), S.GROUND)
    d = ImageDraw.Draw(im)
    d.rectangle((30, 10, 65, 65), fill=colour)
    if noise:
        for x in range(30, 66, 2):
            d.line((x, 10, x, 65), fill=(0, 0, 0))
    return im


def test_features_ignore_the_ground_and_see_the_figure():
    f = S.features(_unit((200, 30, 30)))
    assert abs(f["coverage"] - (36 * 56) / (96 * 72)) < 0.01
    assert f["saturation"] > 200                       # vivid red figure
    assert f["contrast"] < 1                           # flat colour


def test_features_separate_flat_from_busy_art():
    flat, busy = S.features(_unit((120, 120, 200))), S.features(_unit((120, 120, 200), True))
    assert busy["edges"] > flat["edges"]
    assert busy["contrast"] > flat["contrast"]


def test_central_picks_the_units_nearest_the_median():
    feats = {f"U{i}": {"a": float(i), "b": 1.0} for i in range(9)}
    feats["OUTLIER"] = {"a": 100.0, "b": 50.0}
    pick = S.central(feats, 3)
    assert pick[0] == "U4" and "OUTLIER" not in pick
    assert set(pick) == {"U3", "U4", "U5"}


def test_parse_letter_takes_the_first_standalone_candidate_letter():
    assert S.parse_letter("D — It most closely matches", "ABCDE") == "D"
    assert S.parse_letter("Candidate A best matches", "ABCDE") == "A"
    assert S.parse_letter("none of them", "ABC") is None
    assert S.parse_letter("F is outside the set", "ABCDE") is None


def test_thumb_fits_any_image_into_a_ship_size_cell():
    t = S.thumb(Image.new("RGBA", (384, 576), (200, 0, 0, 255)))
    assert t.size == (96, 72)
    assert t.getpixel((0, 0)) == S.GROUND                # letterboxed on ground
    assert t.getpixel((48, 36)) == (200, 0, 0)


def test_grid_and_comparison_sheet_sizes():
    cells = [(f"U{i}", _unit((40 * i, 80, 80))) for i in range(4)]
    g = S.grid(cells, cols=2, scale=2)
    assert g.width == 2 * (96 * 2 + 4) + 4
    sheet = S.comparison_sheet([c[1] for c in cells], [("A", cells[0][1]), ("B", cells[1][1])])
    assert sheet.height > g.height                     # refs block + candidates row
