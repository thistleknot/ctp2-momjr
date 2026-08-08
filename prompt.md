# MoM (Master of Magic) CTP2 scenario — work-in-progress handoff

Repo: `H:\Program Files(x86)\Activision\Call To Power 2` (git). Scenario root: `Scenarios/mom`.
Released: **v4.0.0** (tag `xxvA.0.0xx` / see `CHANGELOG.md`). Everything below is post-release WIP.

---

## State of the plan (5 phases)

| # | Phase | Status |
|---|-------|--------|
| 0 | Call-depth spike — verify flat `MomCastSpell` dispatcher in-game | **in progress / blocked on harness** |
| 1 | Min-maxing — terrain-gated buildings + mana constants → policy | pending |
| 2 | Import the MoM corpus (spells + units/heroes/buildings/terrain) from the wiki mirror | pending |
| 3 | 2022-review QoL pass | pending |
| 4 | Retune mana economy with spells in it | pending |

Completed earlier in this cycle (already committed): tech-cost config, summon combat balance,
calendar `TIME_SCALE` + `END_OF_GAME_YEAR`, production levers (`shield_cost_mult` 215,
`improvement_cost_mult` 125), csvgen `export_flatlist` signature fix.

---

## Phase 0 — where it actually stands

**Code change is written and shipped in `gamedata/mom_spells.slc`:**
`MomCastFlameStrike` was rewritten from the nested-call shape into a *flat dispatcher* structurally
identical in call depth to the already-proven `Button → MomCastSpell → MomSpellShowBook` path.
`MomCastDemonStrike` was left in the original nested shape as the **control** for the A/B.

**The hypothesis being tested:** the crash on the Flame Strike trigger path is a call-depth /
nested-user-function-dispatch limit in the SLIC VM, not a data problem. Flat dispatch should survive
where the nested one dies.

**It is NOT yet verified in-game.** The verification harness is what's broken.

### Harness status (`tools/uiwalk/`, `tools/turnloop.py`, `probe_spellbook.py`)

Measured facts, do not re-derive:

- The engine is a **fixed linear script**; it does not pump a real Windows message loop the way a
  normal app does. UI automation must inject input that the engine actually consumes.
- `EndTurnButtonActionCallback` **silently early-returns** when `GetCurPlayer() != GetVisiblePlayer()`.
  That mismatch is transient right after scenario load. Hence `END_TURN_ATTEMPTS=3` with a 3s retry.
- END TURN only fires when a mouse message genuinely reaches the engine (`engine_ping`); a synthetic
  click that doesn't ping is a no-op.
- **Known false negative:** the date-rect OCR anchor has previously reported `TURN_DID_NOT_ADVANCE`
  on a turn that *had* advanced, because the rect was anchored against the wrong display geometry.
  Last run showed `delta=148570` (huge frame change) alongside `advanced=False` — that is the
  signature of this same false negative, **not** proof the turn stalled.
- Display geometry has been a recurring source of bad measurements. `\\.\DISPLAY9` at 1920x1080 is
  the primary; earlier preflight rejected 1280x1024 as not legal, current preflight passes.

**Next concrete step:** before touching any SLIC, confirm from the saved run frames whether the date
actually advanced. If it did, the harness verdict is the bug, not the game. Fix the date-rect anchor
to be measured from the *current* primary display at capture time rather than a stored constant.
Only after the harness gives a trustworthy verdict is the Phase 0 A/B meaningful.

---

## Landmines / conventions worth keeping

- `scen_str.txt` values are byte-oriented; a real newline inside a quoted value silently swallows the
  next entry. `tools/validate_scenario.py` now catches unbalanced quotes and stray continuations.
- CRLF: git normalises on checkout; expect `warning: LF will be replaced by CRLF` noise on every
  `gamedata/` touch. Harmless.
- `mom.zip` must be rebuilt from disk (`tools/build_mod_zip.py`) whenever `gamedata/` changes — the
  engine reads the zip, not the loose files, for some paths. Verify with `zipcheck`.
- Sound names must exist in the shipped `cdb` sound registry; invented `SOUND_SELECT1_*` names load
  as silence. Check against `unitpromotion.cdb` / `UnitRecord`.
- Unit/advance/wonder idents are cross-checked by `tools/validate_scenario.py` — run it before every
  commit. `PASS 633 files` is the current clean baseline.
- The generator (`tools/ctp2_generator.py`) owns derived cost/stat curves. Do **not** hand-edit
  generated blocks in `Units.txt` / `Advance.txt` / `DiffDB.txt` — edit the CSV/policy source in
  `tools/mom_csv/` and regenerate.

## Useful commands

```bash
cd "H:/Program Files(x86)/Activision/Call To Power 2/Scenarios/mom"
python tools/validate_scenario.py --scenario scen0000   # gates: grammar, charset, idents, integrity
python tools/ctp2_generator.py                          # regenerate derived gamedata
python tools/build_mod_zip.py                           # rebuild mom.zip
python tools/uiwalk/uiwalk.py --preflight               # display/geometry sanity before any UI run
```
