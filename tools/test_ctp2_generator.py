"""test_ctp2_generator.py -- pure helpers in ctp2_generator.

NO GOVERNING SPEC. Basis: operator instruction 2026-09-26 ("iterate on those
items until they are resolved") -- items-to-work.md: CATAPULT / GALLEY sprite
id reassignment, the SETTLER id found reverting on regen, and the MINOTAUR_BOWMAN
clone row that re-scaled ~30 other units' attack.
"""
from __future__ import annotations

import ctp2_generator as G

BASE = ["# base\n", "SPRITE_SETTLER 2\n", "SPRITE_CATAPULT 11\n",
        "SPRITE_GALLEY 26\n", "SPRITE_WARRIOR 40\n"]


def _ids(customs):
    return dict(customs)


def test_custom_ids_stay_pinned_and_new_names_get_fresh_ids():
    scen = BASE + ["SPRITE_ORC 150\n", "SPRITE_TROLL 160\n"]
    kept, customs = G.merge_newsprite(BASE, scen,
                                      ["SPRITE_ORC", "SPRITE_TROLL", "SPRITE_NEWBIE"],
                                      set())
    assert kept == BASE
    assert _ids(customs) == {"SPRITE_ORC": 150, "SPRITE_TROLL": 160,
                             "SPRITE_NEWBIE": 161}


def test_without_an_override_a_scenario_id_for_a_base_name_is_lost():
    """The pre-fix behaviour, kept as a fact: the stock line wins."""
    scen = ["SPRITE_SETTLER 178\n"]
    kept, customs = G.merge_newsprite(BASE, scen, ["SPRITE_SETTLER"], set())
    assert "SPRITE_SETTLER 2\n" in kept
    assert "SPRITE_SETTLER" not in _ids(customs)


def test_override_keeps_its_pinned_custom_id():
    scen = BASE[:1] + ["SPRITE_SETTLER 178\n", "SPRITE_ORC 150\n"]
    kept, customs = G.merge_newsprite(BASE, scen, ["SPRITE_SETTLER", "SPRITE_ORC"],
                                      {"SPRITE_SETTLER"})
    assert "SPRITE_SETTLER 2\n" not in kept
    assert _ids(customs)["SPRITE_SETTLER"] == 178


def test_override_still_on_the_stock_id_is_given_a_fresh_one():
    scen = BASE + ["SPRITE_ORC 150\n"]
    kept, customs = G.merge_newsprite(BASE, scen,
                                      ["SPRITE_CATAPULT", "SPRITE_GALLEY", "SPRITE_ORC"],
                                      {"SPRITE_CATAPULT", "SPRITE_GALLEY"})
    ids = _ids(customs)
    assert "SPRITE_CATAPULT 11\n" not in kept and "SPRITE_GALLEY 26\n" not in kept
    assert ids["SPRITE_CATAPULT"] == 151 and ids["SPRITE_GALLEY"] == 152
    assert "SPRITE_WARRIOR 40\n" in kept          # untouched stock line


def test_merge_is_stable_on_its_own_output():
    """Second regen must not renumber: feed the first result back in."""
    over = {"SPRITE_CATAPULT", "SPRITE_SETTLER"}
    units = ["SPRITE_CATAPULT", "SPRITE_SETTLER", "SPRITE_ORC"]
    kept, c1 = G.merge_newsprite(BASE, BASE + ["SPRITE_ORC 150\n"], units, over)
    scen2 = kept + [f"{n} {i}\n" for n, i in c1]
    _, c2 = G.merge_newsprite(BASE, scen2, units, over)
    assert _ids(c1) == _ids(c2)
    assert len(set(_ids(c2).values())) == len(c2)   # no id collisions


# ---- _stat_source_dist: clones do not move the scale ----------------------

def _dist_with(monkeypatch, rows, exclude):
    monkeypatch.setattr(G, "_policy_csv_rows", lambda name: rows)
    monkeypatch.setattr(G, "_STAT_SOURCE_CACHE", {})
    pol = {**G.MOD_POLICY["unit_stat_scaling"]["stat_curve"], "source_exclude": exclude}
    monkeypatch.setitem(G.MOD_POLICY["unit_stat_scaling"], "stat_curve", pol)
    return G._stat_source_dist("attack")


ROSTER = [{"name": n, "attack": a} for n, a in
          (("Spearmen", "1a"), ("Swordsmen", "3a"), ("Knights", "4a"),
           ("Dragon", "9a"), ("Infernal Device", "99a"))]
CLONES = ROSTER + [{"name": "Spear Bowman", "attack": "1a"},
                   {"name": "Spear Guard", "attack": "1a"}]


def test_clone_rows_would_move_the_median_without_exclusion(monkeypatch):
    base = _dist_with(monkeypatch, ROSTER, [])
    moved = _dist_with(monkeypatch, CLONES, [])
    assert base == (1.0, 3.5, 9.0)          # 99a is past the outlier cutoff
    assert moved[1] < base[1]               # the whole roster would re-scale


def test_excluded_clones_leave_the_distribution_unchanged(monkeypatch):
    got = _dist_with(monkeypatch, CLONES, ["Spear Bowman", "Spear Guard"])
    assert got == (1.0, 3.5, 9.0)
