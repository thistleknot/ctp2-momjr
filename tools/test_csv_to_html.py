"""Tests for csv_to_html.py -- the scrollable art-vs-caption review page."""
from __future__ import annotations

import base64
import csv
import json
import io
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import csv_to_html as H   # noqa: E402


def _b64(size=(160, 120)) -> str:
    buf = io.BytesIO()
    Image.new("RGB", size, (10, 120, 200)).save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _row(ident="ORC", **kw) -> dict:
    r = {"ident": ident, "subject": "wolf", "race": "canine", "pose": "standing",
         "gear": "", "weapon": "none", "mount": "none", "colours": "black, grey",
         "materials": "fur", "description": "A wolf in profile.",
         "art_format": "png", "art_b64": _b64()}
    r.update(kw)
    return r


def _truth(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "truth.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_flags_read_the_operator_truth_file(tmp_path):
    """The badge now reflects the OPERATOR's dictated verdict, not a model guess.
    The old model-judged column was wrong twice (WARBEARS, AIR_ELEMENTAL)."""
    f = H.name_art_flags(_truth(tmp_path, {
        "_about": {"ignored": True},
        "ORC": {"depicts": "wolf", "verdict": "wrong", "note": "orc is a wolf"},
        "SALAMANDER": {"depicts": "fire salamander", "verdict": "correct"}}))
    assert set(f) == {"ORC", "SALAMANDER"}          # _about is metadata, not a unit
    assert f["ORC"]["verdict"] == "wrong"
    assert f["ORC"]["depicts"] == "wolf"


def test_flags_absent_file_is_empty_not_an_error(tmp_path):
    """No truth file must degrade to 'no verdicts', never crash the page build."""
    assert H.name_art_flags(tmp_path / "nope.json") == {}


def _xref(tmp_path: Path, rows: list[dict]) -> Path:
    p = tmp_path / "xref.csv"
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["unit", "ident", "sprite", "icon",
                                           "art_exists", "art_file"])
        w.writeheader()
        w.writerows(rows)
    return p


def test_game_binding_reads_the_units_crossref(tmp_path):
    b = H.game_binding(_xref(tmp_path, [
        {"unit": "UNIT_ORC", "ident": "ORC", "sprite": "SPRITE_ORC",
         "icon": "ICON_UNIT_ORC", "art_exists": "1", "art_file": "SPRITE_ORC.tga"}]))
    assert b["ORC"]["unit"] == "UNIT_ORC"
    assert b["ORC"]["sprite"] == "SPRITE_ORC"


def test_game_binding_absent_file_degrades_quietly(tmp_path):
    assert H.game_binding(tmp_path / "nope.csv") == {}


def test_card_shows_which_unit_the_engine_binds_the_art_to():
    """The caption says what the pixels look like; this says what the GAME does
    with them. The review needs both to spot a misattribution."""
    out = H.render([_row("ORC")], {}, {
        "ORC": {"unit": "UNIT_ORC", "ident": "ORC", "sprite": "SPRITE_ORC",
                "icon": "ICON_UNIT_ORC", "art_exists": "1"}})
    assert "IN GAME:" in out
    assert "UNIT_ORC" in out and "SPRITE_ORC" in out and "ICON_UNIT_ORC" in out
    assert "sprite file MISSING" not in out


def test_card_flags_a_unit_whose_sprite_file_is_absent():
    out = H.render([_row("CITY")], {}, {
        "CITY": {"unit": "UNIT_CITY", "ident": "CITY", "sprite": "SPRITE_CITY",
                 "icon": "", "art_exists": "0"}})
    assert "sprite file MISSING" in out


def test_art_with_no_unit_is_called_an_orphan_not_left_blank():
    """SPRITE_B4 has art but no unit. Silence would read as 'fine'."""
    out = H.render([_row("B4")], {}, {})
    assert "orphan" in out


def _png(tmp_path: Path, name: str, colour=(200, 40, 40)) -> Path:
    p = tmp_path / name
    Image.new("RGB", (240, 176), colour).save(p)
    return p


def test_generated_art_is_keyed_by_ident(tmp_path):
    d = tmp_path / "intent"
    d.mkdir()
    _png(d, "ORC.png")
    g = H.generated_art([d])
    assert set(g) == {"ORC"}
    assert g["ORC"][1] == "intent"          # records which pass produced it


def test_generated_art_strips_seed_and_style_suffixes(tmp_path):
    """Candidates are written as ORC_s777.png / PRIEST_game_art.png; the card
    keys on the unit, not the experiment that produced it."""
    d = tmp_path / "seeds"
    d.mkdir()
    _png(d, "ORC_s777.png")
    _png(d, "PRIEST_game_art.png")
    assert set(H.generated_art([d])) == {"ORC", "PRIEST"}


def test_later_directories_win(tmp_path):
    """Search order encodes 'most recent attempt first' without a manifest."""
    a, b = tmp_path / "intent", tmp_path / "style"
    a.mkdir(); b.mkdir()
    _png(a, "ORC.png", (10, 10, 10))
    _png(b, "ORC.png", (250, 250, 250))
    assert H.generated_art([a, b])["ORC"][1] == "style"


def test_contact_sheets_are_not_mistaken_for_units(tmp_path):
    d = tmp_path / "intent"
    d.mkdir()
    _png(d, "_intent.png")
    _png(d, "ORC.png")
    assert set(H.generated_art([d])) == {"ORC"}


def test_missing_directory_is_skipped_quietly(tmp_path):
    assert H.generated_art([tmp_path / "nope"]) == {}


def test_card_shows_the_proposal_beside_the_current_art(tmp_path):
    d = tmp_path / "style"
    d.mkdir()
    _png(d, "ORC.png")
    out = H.render([_row("ORC")], {}, {}, H.generated_art([d]))
    assert "CURRENT" in out and "PROPOSED" in out
    assert 'data-gen="1"' in out
    assert out.count("<img") == 2           # current + proposed


def test_decided_units_offer_no_candidate_even_when_one_exists(tmp_path):
    d = tmp_path / "style"
    d.mkdir()
    for n in ("ORC", "DROW", "TREANT", "HYDRA"):
        _png(d, f"{n}.png")
    flags = {"ORC": {"verdict": "crafted", "depicts": "orc"},
             "DROW": {"verdict": "keep", "depicts": "drow"},
             "TREANT": {"verdict": "correct", "depicts": "treant",
                        "no_regenerate": True}}
    out = H.render([_row(n) for n in ("ORC", "DROW", "TREANT", "HYDRA")],
                   flags, {}, H.generated_art([d]))
    assert out.count("final &mdash; no candidate") == 3
    assert out.count('data-gen="1"') == 1       # only the undecided HYDRA
    assert out.count("<img") == 4 + 1           # four current + one proposed


def test_card_without_a_proposal_says_so_rather_than_showing_nothing():
    out = H.render([_row("HYDRA")], {}, {}, {})
    assert "not generated" in out
    assert 'data-gen="0"' in out


def test_every_row_becomes_one_card():
    out = H.render([_row("ORC"), _row("HYDRA"), _row("LAMP")], {})
    assert out.count('<article class="row"') == 3


def test_art_is_inlined_as_a_data_uri():
    b = _b64()
    out = H.render([_row(art_b64=b)], {})
    assert f'src="data:image/png;base64,{b}"' in out


def test_missing_art_renders_a_placeholder_not_a_broken_image():
    out = H.render([_row(art_b64="")], {})
    assert "no art" in out
    assert "data:image/png;base64," not in out


def test_corrected_row_is_badged_with_its_verdict_and_shows_what_the_art_is():
    out = H.render([_row("ORC"), _row("HYDRA")],
                   {"ORC": {"depicts": "wolf", "verdict": "wrong",
                            "note": "orc is a wolf"}})
    assert 'data-verdict="wrong"' in out
    assert '<span class="badge wrong">wrong</span>' in out
    assert "ART DEPICTS:</b> wolf" in out
    assert "orc is a wolf" in out
    assert 'data-flag="1"' in out and 'data-flag="0"' in out   # HYDRA unflagged


def test_a_unit_with_no_verdict_shows_no_badge_and_no_truth_line():
    out = H.render([_row("HYDRA")], {})
    assert "ART DEPICTS" not in out
    assert 'class="badge' not in out
    assert 'data-verdict=""' in out


def test_verdict_note_is_escaped():
    out = H.render([_row("ORC")],
                   {"ORC": {"depicts": "wolf", "verdict": "wrong",
                            "note": '<img src=x onerror=1> "q"'}})
    assert "<img src=x" not in out
    assert "&lt;img" in out


def test_html_in_caption_text_is_escaped():
    """A description is untrusted text; it must not be able to inject markup."""
    out = H.render([_row(description='<script>alert(1)</script> & "x"')], {})
    assert "<script>alert(1)</script>" not in out
    assert "&lt;script&gt;" in out


def test_search_haystack_is_lowercased_for_case_insensitive_filtering():
    out = H.render([_row("ORC", subject="Wolf")], {})
    assert 'data-hay="orc wolf canine a wolf in profile."' in out


def test_empty_fields_are_omitted_from_the_detail_grid():
    out = H.render([_row(gear="")], {})
    assert ">gear<" not in out
    assert ">weapon<" in out
