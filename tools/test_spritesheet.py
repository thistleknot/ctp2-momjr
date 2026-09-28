"""test_spritesheet.py -- export all masters to one sheet and import them back.

NO GOVERNING SPEC. Basis: operator 2026-09-27, hand-clean round trip.
"""
from __future__ import annotations

from pathlib import Path

import json

import pytest
from PIL import Image, ImageDraw

import install_crafted_art as I
import spritesheet as S


@pytest.fixture(autouse=True)
def _roster(monkeypatch):
    """The fixtures' units ARE the roster; the real one lives in the caption CSV."""
    monkeypatch.setattr(S, "roster", lambda: ["A", "B", "C"])


def _pics(tmp: Path, units: list[str]) -> Path:
    pics = tmp / "pics"
    pics.mkdir()
    for n, u in enumerate(units):
        im = Image.new("RGB", (160, 120), (0, 0, 0))
        ImageDraw.Draw(im).rectangle((40 + n, 20, 119, 109), fill=(200, 40 + n * 20, 40))
        I.write_tga(pics / f"SPRITE_{u}.tga", im)
    return pics


def test_export_places_each_master_in_its_cell_with_transparent_key(tmp_path):
    pics = _pics(tmp_path, ["A", "B", "C"])
    out = tmp_path / "sheet.png"
    sheet = S.export(["A", "B", "C"], pics, out)
    assert sheet.size == (10 * 161 + 1, 1 * 121 + 1)
    x0, y0, _, _ = S.cell_box(1)                      # unit B
    assert sheet.getpixel((x0 + 2, y0 + 2))[3] == 0   # key -> transparent
    got = sheet.getpixel((x0 + 80, y0 + 60))
    # masters are RGB555: each channel is exact to 5 bits (within 8 of the source)
    assert got[3] == 255 and all(abs(a - b) < 8 for a, b in zip(got, (200, 56, 40)))
    assert sheet.getpixel((0, 0)) == S.LINE           # grid line outside cells
    assert out.with_suffix(".json").exists()


def test_unchanged_sheet_imports_as_no_change(tmp_path):
    pics = _pics(tmp_path, ["A", "B"])
    out = tmp_path / "sheet.png"
    S.export(["A", "B"], pics, out)
    assert S.import_sheet(out, pics, apply=True) == []


def test_an_old_sheet_cannot_revert_a_unit_changed_after_export(tmp_path):
    pics = _pics(tmp_path, ["A", "B"])
    out = tmp_path / "sheet.png"
    S.export(["A", "B"], pics, out)
    newer = Image.new("RGB", (160, 120), (0, 0, 0))
    ImageDraw.Draw(newer).rectangle((10, 10, 150, 110), fill=(20, 200, 20))
    I.write_tga(pics / "SPRITE_A.tga", newer)       # A updated after the export
    before = (pics / "SPRITE_A.tga").read_bytes()
    assert S.import_sheet(out, pics, apply=True) == []   # untouched cells ignored
    assert (pics / "SPRITE_A.tga").read_bytes() == before


def test_a_hand_edit_is_imported_into_that_unit_only(tmp_path):
    pics = _pics(tmp_path, ["A", "B"])
    out = tmp_path / "sheet.png"
    sheet = S.export(["A", "B"], pics, out)
    x0, y0, _, _ = S.cell_box(1)
    ImageDraw.Draw(sheet).rectangle((x0 + 40, y0 + 20, x0 + 60, y0 + 40), fill=(0, 0, 0, 0))
    sheet.save(out)                                   # operator erased part of B
    assert S.import_sheet(out, pics, apply=False) == ["B"]
    assert S.import_sheet(out, pics, apply=True) == ["B"]
    b = Image.open(pics / "SPRITE_B.tga").convert("RGB")
    assert b.getpixel((50, 30)) == (0, 0, 0)          # erased -> key
    assert b.getpixel((100, 100)) != (0, 0, 0)        # rest of the art kept
    assert (pics / "ICON_UNIT_B.tga").read_bytes() == (pics / "SPRITE_B.tga").read_bytes()
    assert list(pics.glob("SPRITE_B.tga.bak-*"))
    assert not list(pics.glob("SPRITE_A.tga.bak-*"))


def test_a_sheet_naming_non_units_is_refused_before_any_write(tmp_path):
    """Operator 2026-09-28: 'be sure that the spritesheet is for units'."""
    pics = _pics(tmp_path, ["A", "B"])
    out = tmp_path / "sheet.png"
    sheet = S.export(["A", "B"], pics, out)
    meta = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
    meta["units"] = ["A", "ADVANCE_ALCHEMY"]            # e.g. an advance-icon sheet
    out.with_suffix(".json").write_text(json.dumps(meta), encoding="utf-8")
    x0, y0, _, _ = S.cell_box(0)
    ImageDraw.Draw(sheet).rectangle((x0 + 40, y0 + 20, x0 + 60, y0 + 40), fill=(0, 0, 0, 0))
    sheet.save(out)
    before = (pics / "SPRITE_A.tga").read_bytes()
    with pytest.raises(ValueError, match="not a unit spritesheet"):
        S.import_sheet(out, pics, apply=True)
    assert (pics / "SPRITE_A.tga").read_bytes() == before


def test_a_resized_sheet_is_refused(tmp_path):
    pics = _pics(tmp_path, ["A", "B"])
    out = tmp_path / "sheet.png"
    sheet = S.export(["A", "B"], pics, out)
    sheet.resize((sheet.width // 2, sheet.height // 2)).save(out)   # e.g. a phone export
    with pytest.raises(ValueError, match="a unit sheet of 2 is 1611x122"):
        S.import_sheet(out, pics, apply=False)
