"""test_build_mod_zip.py -- what goes into mom.zip.

NO GOVERNING SPEC. Basis: 2026-09-26 measurement -- 232 timestamped .bak files
and 166 _art_backup TGAs were shipping in mom.zip.
"""
from __future__ import annotations

from pathlib import Path

import build_mod_zip as M


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "packicon.tga").write_bytes(b"x")
    (tmp_path / "packlist.txt").write_text("x")
    pics = tmp_path / "scen0000" / "default" / "graphics" / "pictures"
    pics.mkdir(parents=True)
    for name in ("SPRITE_ORC.tga", "SPRITE_ORC.tga.bak-20260926-175952",
                 "SPRITE_ORC.tga.bak", "Units.txt.BAK_old"):
        (pics / name).write_bytes(b"x")
    (pics / "_art_backup").mkdir()
    (pics / "_art_backup" / "ICON_UNIT_ORC.tga").write_bytes(b"x")
    return tmp_path


def test_real_art_ships_and_every_backup_form_is_left_out(tmp_path):
    names = {arc for _, arc in M.members(_repo(tmp_path))}
    assert "mom/scen0000/default/graphics/pictures/SPRITE_ORC.tga" in names
    assert not any(".bak" in n.lower() for n in names)
    assert not any("_art_backup" in n for n in names)
    assert {"mom/packicon.tga", "mom/packlist.txt"} <= names
