# MoM (Master of Magic) CTP2 scenario — work-in-progress handoff

Repo: `H:\Program Files(x86)\Activision\Call To Power 2` (git). Scenario root: `Scenarios/mom`.
Released: **v4.0.0** (tag `xxvA.0.0xx` / see `CHANGELOG.md`).

---

## State of the plan (5 phases)

| # | Phase | Status |
|---|-------|--------|
| 0 | Call-depth spike — flat dispatcher verified | **CLOSED** |
| 1 | Min-maxing — terrain-gated buildings + mana constants → policy | **next** |
| 2 | Import the MoM corpus (spells + units/heroes/buildings/terrain) from the wiki mirror | **partially done** (spells.csv + paged spellbook shipped) |
| 3 | 2022-review QoL pass | pending |
| 4 | Retune mana economy with spells in it | pending |

---

## Phase 0 — CLOSED

The flat dispatcher hypothesis was confirmed and shipped. Key outcomes:

- `mom_spells.slc`: both `MomCastFlameStrike` and `MomCastDemonStrike` flattened (no nested user-function calls from Button bodies).
- `controlpanelwindow.cpp`: `case CP_TARGETING_MODE_SCRIPT_PENDING: break;` prevents idle-clear of script targeting mode.
- `ScriptTargetMode.cpp`: one-shot cancel-before-fire pattern, clean HandleClick → Cancel → Execute ordering.
- Harness: turnloop 5/5 PASS, 7-arm builtin battery PASS (BeginTargetMode, ModifyUnitStat, ClearUnitBuffs, HealUnit, GetUnitHP, GetUnitMaxHP, IsTargetModeActive), ESC cancel PASS, right-click cancel PASS.
- Last-good turnloop: `runs/20260815-092814-turnloop` (verdict OK, 0 SLIC errors).
- Last-good builtins: `runs/20260815-100656-builtins`.

---

## Phase 2 (spells bucket) — already shipped

The wiki import pipeline produced `spells.csv` (216 spells, all 5 spheres + arcane). The generator now emits:

- `mom_spellbook_cast.slc` — flat `MomCastSpell(p, spellId)` if-chain with proximity targeting + unit-spell bindings (mage range tiers: WAR_MAGE=1, ARCH_MAGE=2).
- `mom_spellbook_life.slc`, `..._nature.slc`, `..._sorcery.slc`, `..._death.slc`, `..._chaos.slc` — two-tier paged UI (hub → rarity filter → 3 spells/page with nav).
- Research gating: rarity tiers locked behind sphere ladder rung + `MomSpellHandRarity[]` roll.
- The old `MomMsgSpellbook` / `MomMsgSpellbookChaos` alertboxes redirect into the per-sphere hub page 1.

Remaining Phase 2 buckets (heroes, race-units, buildings, terrain specials, minerals, encounter sites) are NOT yet imported.

---

## Phase 1 — terrain-gated buildings + mana constants → policy (NEXT)

From `mom-feature-roadmap.spec.md`:

1. **Terrain-gating:** add `terrain_prereq` to `improvements.csv`; generator emits gating logic into `mod_CanCityBuildBuilding` (e.g. no forest tiles → Sawmill/Foresters' Guild unbuildable).
2. **Mana constants to policy:** promote all magic literals (pool 200, upkeep rate 2, summon rung pricing `45+30*rung`, school multipliers, etc.) from `mom_magic.slc` inline literals into `mod_policy.json` `mana_economy` block. Generator emits the values; `gate_mana_upkeep.py` asserts pool-200 invariant holds.
3. **Food/growth chain rebalance:** Granary, Farmer's Market, Sawmill, Foresters' Guild — balance their production/growth bonuses against the terrain gate.

### Key files to touch

| File | Change |
|------|--------|
| `tools/momjr_csv/improvements.csv` | Add `terrain_prereq` column |
| `tools/ctp2_generator.py` | Emit terrain gating SLIC from CSV |
| `scen0000/default/gamedata/mom_gating.slc` | Generated output |
| `mod_policy.json` | New `mana_economy` block |
| `tools/ctp2_generator.py` | Emit mana constants from policy |
| `scen0000/default/gamedata/mom_magic.slc` | Consume generated constants |
| `tools/gate_mana_upkeep.py` | Assert policy values = shipped behaviour |

---

## Landmines / conventions worth keeping

- `scen_str.txt` values are byte-oriented; a real newline inside a quoted value silently swallows the next entry. `tools/validate_scenario.py` catches unbalanced quotes.
- CRLF: git normalises on checkout. Harmless noise.
- `mom.zip` must be rebuilt (`tools/build_mod_zip.py`) whenever `gamedata/` changes.
- Sound names must exist in the shipped `cdb` registry; invented names load as silence.
- The generator (`tools/ctp2_generator.py`) owns derived cost/stat curves. Never hand-edit generated files.
- One-call-depth limit from Button/trigger bodies. Inline everything or use array lookups.
- Alertbox ceiling: 5 arms max (6th silently dropped). Paging is mandatory.

## Useful commands

```bash
cd "H:/Program Files(x86)/Activision/Call To Power 2/Scenarios/mom"
python tools/validate_scenario.py --scenario scen0000   # gates: grammar, charset, idents, integrity
python tools/ctp2_generator.py                          # regenerate derived gamedata
python tools/build_mod_zip.py                           # rebuild mom.zip
python tools/uiwalk/uiwalk.py --preflight               # display/geometry sanity before any UI run
python tools/uiwalk/turnloop.py --turns 5               # 5-turn headless gate
python tools/uiwalk/probe_builtins.py                   # 7-arm builtin + targeting battery
python tools/uiwalk/probe_spellbook.py                  # spellbook open/cast headless test
```
