---
description: 'MoM total-conversion feature roadmap: shipped systems, active development, and planned phases'
import:
  - ctp2-slic-contracts
  - ctp2-dimension-pipeline
---

***definitions***

- :Sphere: is one of the five magic schools (Life, Nature, Sorcery, Death, Chaos) mapped 1:1 to player indices 1–5 and their civilisations. Each has distinct generation rates, summon rosters, and spell lists.
- :Magic-Pool: is a fixed-200 per-player mana accumulator. Generation = base + pop coefficient + node bonus, scaled by :MagicSchoolPct:. All costs are legible as fractions of 200.
- :Summon-Rung: is the 1–5 ladder position a tribe climbs by summoning. Price = `(45 + 30*rung) * MomSummonCivPct / 100`. Higher rungs yield stronger creatures; the weighted draw rewards persistence.
- :Spellbook: is the in-game alertbox UI (max 5 arms per page) exposing castable spells to the player. Paging is mandatory because a sixth arm is silently dropped.
- :Artifact-Vessel: is a map unit (non-combat, non-settable) representing an ownable magic item. The lamp is the first. Capture moves ownership; wishes spend from the holder's pool.
- :Wiki-Corpus: is the offline MoM wiki mirror at `F:\Documents\wiki\games\mom\site\` (878 pages, 1834 images, `index.json` as parse target). Source data for the Phase 2 import.
- :Terrain-Gating: is the min-max mechanic where building availability depends on worked terrain (forest → Sawmill, mountain → Miners' Guild, coast → Shipwrights).
- :Calendar: is the generator-owned `TIME_SCALE` blocks in DiffDB.txt + `END_OF_GAME_YEAR` constants in Const.txt, derived from `calendar_periods.csv`.

***implementation reqs***

- SLIC entry: `scenario.slc` → includes `mom_func` → `mom_turns` → `mom_city_effects` → `mom_msg` → `mom_magic` → `mom_summon` → `mom_ai_magic` → `mom_artifacts` → `mom_spells`.
- Generator-emitted files (DO NOT HAND-EDIT): `mom_gating.slc`, `mom_summon.slc`.
- Magic constants today: literals in `mom_magic.slc`, guarded by `gate_mana_upkeep.py`. Future: `mod_policy.json` `mana_economy` block (Phase 1).
- Alertbox ceiling: 5 arms max (measured, enforced by build). Close is always first arm.
- One-call-depth limit applies to all Button/HandleEvent bodies.
- Wiki import pipeline: `tools/wiki_import/` → extractor per bucket → CSV under `tools/momjr_csv/`. Idempotent, re-runnable. Corrections in sidecar override files.
- Spell gate: `gate_spells.py`. Wiki import gate: `gate_wiki_import.py`.
- Calendar gate: generator-owned `_write_calendar()` is the single writer for TIME_SCALE.

***test reqs***

- Phase 0 spike: cast Flame Strike + Demon Strike from both spellbook variants; AI Chaos wizard casts on BeginTurn. 0xC0000005 = spike falsified → fallback to one-function-per-spell.
- Phase 1: terrain gating fires (no forest → no Sawmill). Mana constants in `mod_policy.json` match shipped behaviour. Pool-200 invariant holds.
- Phase 2: wiki import CSVs re-derive identically from snapshot. No imported ident violates charset gates. Generated DB passes `validate_all_surfaces.py`.
- General: `mom_audit.py` FAIL: 0, `verify_all.py` clean, `name_audit.py` correct counts, `validate_scenario.py` green.
- Headless playtest (`uiwalk.py`) soak: 20+ turns, no crash, screenshot checkpoints.

***functional specs***

## Shipped Systems (v4.1.0)

- :Magic-Pool: ticks on BeginTurn for players 1–5. Generation = `(MAGIC_BASE + pop*MAGIC_POP_COEF + nodes*MANA_NODE_BONUS) * MomMagicSchoolPct[p] / 100`. Cap = 200 (fixed, all civs).
- :Summon-Rung: advances on successful summon. Pool-overflow auto-summon (M3) fires when pool reaches cap, discharging fully. Weighted draw selects creature by rung.
- Summon price: `(45 + 30*rung) * MomSummonCivPct[p] / 100`. Chaos dearest (92%), Death/Sorcery cheapest (54%).
- Upkeep: `MomUpkeepRate` (single seeded global, currently 2). Insolvency → creature disbanded, mana refunded.
- AI magic: silent, fail-closed. `!IsHumanPlayer` guard. War-chest vs summon starvation guarded (cheap branch only fires when the tribe cannot afford the expensive option).
- :Artifact-Vessel:: lamp grants Riches/Power/Servant/Artifacts via wishes. Wishes enumerated, consumed from holder's pool. Banished to `Site` when unowned.
- Sphere identity: derived from CIVILISATION, not player seat.
- Menu tree: `j` opens hub → spellbook / summon / artifacts / wishes / store. Five-arm ceiling enforced by build.
- :Calendar: derived from `calendar_periods.csv`. Research costs projected into per-Age bands from `advance_cost_bands.csv`.
- Genre filter: 34 orders visible + 13 GLHidden; 13 terraform + trading post visible + 4 tile imps GLHidden.

## Phase 0 — Call-Depth Spike (BUILT, awaiting in-game verify)

- `MomCastSpell(int_t p, int_t spellId)` — one user-function call from Button, all effect bodies inlined as if-chain.
  - Given the spike code deployed, When player casts Flame Strike from spellbook, Then the spell effect fires without 0xC0000005.
  - Given the spike code deployed, When AI Chaos wizard casts on BeginTurn, Then the cast completes without crash.
- If spike crashes → fallback: one generated function per spell, each its own Button, paged spellbook.

## Phase 1 — City Economy & Min-Maxing (PENDING)

- :Terrain-Gating: adds `terrain_prereq` to improvements.csv; generator emits gating into `mod_CanCityBuildBuilding`.
  - Given a city working no forest tiles, When player opens build menu, Then Sawmill/Foresters' Guild are unbuildable.
- Mana constants promoted to `mod_policy.json` `mana_economy` block, generator-emitted.
- Food/growth chain rebalanced (Granary, Farmer's Market, Sawmill, Foresters' Guild).
- `gate_mana_upkeep.py` extended to assert policy-sourced dials preserve ANCHOR-200.

## Phase 2 — Wiki Corpus Import (PENDING)

- Import pipeline reads `index.json` from :Wiki-Corpus:, extracts per bucket:
  - Spells/enchantments (~50+) → `spells.csv`
  - Heroes (~45) → `heroes.csv`
  - Buildings (~35) → fold into `improvements.csv` with `terrain_prereq`
  - Race units (per-race rosters) → `units.csv`
  - Terrain specials (~21) → terrain tables
  - Minerals/goods (~12) → goods tables
  - Encounter sites (~9) → ruins/goody-hut content
  - Retorts (~2+) → captured as data (no CTP2 home yet)
- :Spellbook: rebuilt: paged UI driven off `spells.csv` instead of two hand-wired buttons.
  - Given spells.csv with 40 Life spells, When player opens Life spellbook, Then pages show 5 spells at a time with navigation.
- Spell effect_kinds: `summon`, `unit_enchant`, `city_enchant`, `global_enchant`, `instant_damage`, `dispel`. Others masked but imported.
- Sidecar override files for corrections (re-import never discards overrides).
- Never let wiki numbers bypass balance gates — import as source data, `mod_policy.json` decides what ships.

## Phase 3 — 2022-Review QoL (PENDING)

- Spellbook usability improvements.
- Clearer sphere identity markers.
- Research pacing adjustments.
- Layered on Phase 2 data pipeline.

## Phase 4 — Economy Retune with Spells (PENDING)

- Rebalance `MomMagicSchoolPct` / `MomSummonCivPct` against combined summon + cast demand.
- Fixed 200 pool and flat upkeep rate 2 will not hold with a real spell list.
- Extend gates for new economy shape.
