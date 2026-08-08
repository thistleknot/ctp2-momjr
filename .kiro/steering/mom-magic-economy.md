---
inclusion: fileMatch
fileMatchPattern: "**/mom_magic*"
---

# MoM Magic Economy

Included when working on magic system SLIC files.

## Pool Architecture

- Fixed pool: **200** for ALL civs (no per-sphere caps since v3.11.0)
- Generation: `(MAGIC_BASE_PER_TURN + pop*MAGIC_POP_COEF + nodes*MANA_NODE_BONUS) * MomMagicSchoolPct[p] / 100`
- School multipliers: Life 100%, Nature 110%, Death 115%, Sorcery 125%, Chaos 140%
- Constants are literals in `mom_magic.slc`, guarded by `gate_mana_upkeep.py`
- Future: promote to `mod_policy.json` `mana_economy` block (Phase 1)

## Summon System

- Price: `(45 + 30*rung) * MomSummonCivPct[p] / 100`
- Rung advances on successful summon (1–5 ladder)
- Pool-overflow auto-summon (M3): fires when pool reaches cap, discharges fully
- Weighted draw selects creature by rung
- Civ percentages (derived from roster cost at equal rung):
  - Chaos 92%, Nature 68%, Life 64%, Sorcery 54%, Death 54%

## Upkeep

- `MomUpkeepRate` — single seeded global (currently 2)
- Seeded by `MomRecalcMagicPerTurn` — MUST be seeded before first use (starts at 0)
- Insolvency → creature disbanded, mana refunded to floor
- Gate 27 assertion 10: single home + seeding

## Starvation Guard

When two spends share one pool, the cheaper one starves the dearer unless gated.
- War-chest threshold: 50 (cheap branch)
- Summon threshold: 75 (expensive branch)
- Fix: cheap branch only fires when the tribe cannot feed even a rung-1 creature
- Gate 27 assertion 11: guard exists

## AI Magic

- Silent: no `Message()` calls in `mom_ai_magic.slc`
- `!IsHumanPlayer` guards throughout
- Fires on BeginTurn for AI sphere players
- `gate_ai_magic.py` asserts no Message() and IsHumanPlayer guards

## Mana Nodes (M4)

Any good-bearing tile (`HasGood(loc) >= 0`) in a city's radius adds
`MANA_NODE_BONUS` (+5) per turn to that player's generation.
MoM goods ARE terrain minerals (Rubies, Diamonds, etc.) — every good counts.

## Spellbook (Current State)

- 5-arm alertbox ceiling (measured, enforced by build)
- Close is first arm declared
- Two hand-wired spells: Flame Strike + Demon Strike
- Phase 0 spike: `MomCastSpell(int_t p, int_t spellId)` — flat dispatcher, awaiting verify
- Future: paged spellbook driven off `spells.csv` (Phase 2)
