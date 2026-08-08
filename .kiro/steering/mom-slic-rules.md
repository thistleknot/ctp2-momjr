---
inclusion: fileMatch
fileMatchPattern: "**/*.slc"
---

# MoM SLIC Rules

Included when reading or writing `.slc` files.

## Call-Depth Limit

A `Button` / `trigger` / `HandleEvent` body may descend exactly ONE level of
user-function call. A second level causes 0xC0000005 with no SLIC error.
Every spell effect must be inlined flat.

## Base-Verified Builtins Only

Only use SLIC functions/objects proven by stock scenario scripts:

| Verb | Signature |
|---|---|
| CreateUnit | `CreateUnit(playerIdx, UnitDB(UNIT_X), location, distance)` |
| MakeLocation | `MakeLocation(loc, x, y)` |
| HasGood | `HasGood(loc)` — returns good index, negative if none |
| CityHasBuilding | `CityHasBuilding(city, "IMPROVE_X")` — QUOTED STRING |
| CreateBuilding | `CreateBuilding(city, BuildingDB(IMPROVE_X))` — INTEGER HANDLE |
| GetCityByIndex | `GetCityByIndex(player, idx, city)` |
| IsHumanPlayer | `IsHumanPlayer(player)` |
| Message | `Message(player, 'KEY')` with `{scalar}` interpolation |
| PlayerHasWonder | `PlayerHasWonder(player, WonderDB(WONDER_X))` |

## Forbidden Constructs

- `KeyPress`, `NotifyPlayer`, `ShowMessageBox` — do not exist in stock SLIC
- String-form `CreateUnit("UNIT_X")` — wrong, use `UnitDB(UNIT_X)` integer form
- `.hasBuilding("...")` — momjr idiom, not base-verified
- Array-indexed-by-global interpolation `{Arr[Idx]}` — renderer drops the message silently
- Any second-level user-function call from a handler

## Message Interpolation

Only `{scalar}` and `{obj[lit].member}` forms are proven:
- `{cityScore}`, `{barbNum}`, `{city[0].name}` — all work
- To show a computed number, copy into a plain `int_t` display scalar BEFORE the `Message`

## Globals Start at Zero

SLIC globals initialize to `0`. A rate variable seeded to `0` makes formulas dead.
Always seed globals explicitly before first use (e.g. `MomUpkeepRate` seeded by
`MomRecalcMagicPerTurn`).

## Faction Check

Canonical: numeric player index. `p == 1` Life, `2` Nature, `3` Sorcery, `4` Death, `5` Chaos.
`TRIBES_X` are civ-DB record names, NOT SLIC symbols. `player[p].civ` does not exist.
Helpers take `int_t p`; the event-local player is `player[0]`, passed into helpers as `p`.

## Generator-Emitted Files (DO NOT HAND-EDIT)

- `mom_gating.slc`
- `mom_summon.slc`

## Module Include Order

`scenario.slc` → `mom_func` → `mom_turns` → `mom_city_effects` → `mom_msg` →
`mom_magic` → `mom_summon` → `mom_ai_magic` → `mom_artifacts` → `mom_spells`

## Symbol Surface

Every `UNIT_*`, `IMPROVE_*`, `ADVANCE_*`, `WONDER_*` token in `.slc` files MUST
resolve in the generated DBs. Run `validate_all_surfaces.py` surface 7 before launch.
SLIC parse errors are non-fatal dialogs (load continues), but unknown symbols are
SILENTLY auto-created and no-op — offline audit is mandatory.

## Alertbox Ceiling

Maximum 5 arms per alertbox. A sixth is silently dropped from the tail.
Close is always the first arm declared. Both rules enforced by the build.
