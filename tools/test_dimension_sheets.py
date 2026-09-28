"""Tests for dimension_sheets.py -- per-dimension image sheets for the README.

NO GOVERNING SPEC. Basis: operator 2026-09-28, "include all sprite sheets top level
in the readme". Synthetic inputs only; the real archives are exercised by the tool.
"""
from __future__ import annotations

import struct

import dimension_sheets as D


def test_records_take_the_icon_of_the_record_not_of_a_nested_block():
    text = """UNIT_A {
   DefaultIcon ICON_UNIT_A
   Sub {
      DefaultIcon ICON_WRONG
   }
}
UNIT_B {
   Sub { X 1 }
   DefaultIcon ICON_UNIT_B   // after a nested block
}
UNIT_C {
   Cost 3
}"""
    assert D.records(text, "DefaultIcon") == [("UNIT_A", "ICON_UNIT_A"), ("UNIT_B", "ICON_UNIT_B")]


def test_records_flag_hidden_ones_players_never_see():
    text = """ADVANCE_A {
   Icon ICON_ADVANCE_A
}
ADVANCE_B {
   GLHidden
   Icon ICON_ADVANCE_B
}"""
    assert D.records(text, "Icon", True) == [("ADVANCE_A", "ICON_ADVANCE_A", False),
                                             ("ADVANCE_B", "ICON_ADVANCE_B", True)]


def _rim(w: int, h: int, pixels: list[int]) -> bytes:
    return b"RIMF" + struct.pack("<I3HH", 1, w, h, w * 2, 0) + struct.pack(f"<{w*h}H", *pixels)


def test_decode_rim_reads_rgb555_and_keys_magenta():
    im = D.decode_rim(_rim(2, 1, [0x7C00, 0x7C1F]))       # pure red, then the key
    assert im.size == (2, 1)
    assert im.getpixel((0, 0)) == (255, 0, 0, 255)
    assert im.getpixel((1, 0))[3] == 0


def _zfs(entries: list[tuple[str, bytes]], per: int = 2) -> bytes:
    """Build a ZFS3 archive with `per` entries per directory block."""
    nlen, esz = 16, 36
    blocks = [entries[i:i + per] for i in range(0, len(entries), per)]
    head = 28
    dir_size = len(blocks) * (4 + per * esz)
    data_at, dirs, data = head + dir_size, b"", b""
    for bi, blk in enumerate(blocks):
        nxt = head + (bi + 1) * (4 + per * esz) if bi + 1 < len(blocks) else 0
        d = struct.pack("<I", nxt)
        for name, blob in blk:
            d += name.encode().ljust(nlen, b"\0") + struct.pack(
                "<5I", data_at + len(data), 0, len(blob), 0, 0)
            data += blob
        dirs += d.ljust(4 + per * esz, b"\0")
    return b"ZFS3" + struct.pack("<6I", 1, nlen, per, len(entries), 0, head) + dirs + data


def test_zfs_directory_walk_follows_blocks_and_ignores_stray_names(tmp_path):
    a, b, c = _rim(1, 1, [0x001F]), _rim(1, 1, [0x03E0]), _rim(1, 1, [0x7C00])
    blob = _zfs([("one.rim", a), ("two.rim", b), ("three.rim", c)])
    blob += b"one.rim\0" * 3                                  # stray copies of a name
    arc = tmp_path / "pic555.zfs"
    arc.write_bytes(blob)
    got = D.zfs_entries(arc)
    assert set(got) == {"one.tga", "two.tga", "three.tga"}   # 3rd lives in block 2
    off, size = got["three.tga"]
    assert D.decode_rim(blob[off:off + size]).getpixel((0, 0)) == (255, 0, 0, 255)


def test_backup_subfolders_never_shadow_the_live_art(tmp_path, monkeypatch):
    """The first units sheet showed the retired wolf ORC from _art_backup/."""
    pics = tmp_path / "scen" / "graphics" / "pictures"
    (pics / "_art_backup").mkdir(parents=True)
    (pics / "ICON_UNIT_ORC.TGA").write_bytes(b"live")
    (pics / "_art_backup" / "ICON_UNIT_ORC.tga").write_bytes(b"old")
    monkeypatch.setattr(D, "SCEN", tmp_path / "scen")
    monkeypatch.setattr(D, "BASE", tmp_path / "base")
    assert D.loose_index()["icon_unit_orc.tga"].read_bytes() == b"live"


def test_non_zfs_file_has_no_entries(tmp_path):
    p = tmp_path / "x.zfs"
    p.write_bytes(b"NOPE" + b"\0" * 40)
    assert D.zfs_entries(p) == {}
