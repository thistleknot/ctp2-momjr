# Spell Effects Implementation Spec

Status: ACTIVE
Created: 2026-08-07
Disposition: Implementing

## Principle

Every spell should DO something the player can observe. "Your spell takes effect"
with no visible change is a broken promise. Each spell gets either:
- A REAL mechanical effect (using CTP2 SLIC builtins), OR
- An HONEST description + best-available proxy effect

## CTP2 SLIC Capabilities

| Builtin | What It Does | Spells It Serves |
|---------|-------------|-----------------|
| CreateUnit(p, UnitDB(X), loc, dist) | Spawn creature | All summons |
| KillUnit(unit) | Kill a unit | Offensive kill spells |
| Terraform(loc, idx) | Change terrain type | Change Terrain, Raise Volcano, Corruption |
| CreateBuilding(city, BuildingDB(X)) | Add building | Wall of Stone, city enchants |
| AddGold(p, amount) | Give gold | Transmute, prosperity effects |
| MomMagicCur[p] += N | Mana manipulation | Drain/fill pool spells |
| Random(N) | RNG roll | Resistance, variable effects |
| GetUnitsAtLocation + KillUnit | Area damage | AoE kill spells |
| CityHasBuilding + CreateBuilding | Conditional build | Enchant-if-missing |

## Cannot Implement (honest stubs)

| Original Effect | Why | Proxy |
|---|---|---|
| Reveal map tiles | No ExploreArea/RevealTile builtin | Mana deducted, message only |
| Heal unit HP | No SetHP/HealUnit builtin | Mana deducted, message only |
| Buff attack/defense | No SetAttack/SetDefense runtime mod | Mana deducted, message only |
| Move/teleport units | No MoveUnit/Teleport builtin | Mana deducted, message only |
| Modify movement points | No SetMovePoints builtin | Mana deducted, message only |
| Combat-only effects | No combat hook in SLIC overland | Mana deducted, message only |
| Counter enemy casting | No interrupt mechanic | Drain enemy mana instead |

## Implementation Plan by Effect Kind

### SUMMON (42 spells) — ALREADY DONE
All summons work: CreateUnit at capital. No changes needed.

### UNIT_ENCHANT (57 spells) — STUBS (cannot buff stats)
CTP2 has no runtime stat modification. These remain as mana-deduct stubs.
Description: state what the buff WOULD be from the wiki text.

### GLOBAL_ENCHANT (22 spells) — PARTIAL IMPLEMENTATION
Global enchants that we CAN implement:
- Just Cause: AddGold(p, 100) — "popularity brings tribute"
- Crusade: spawn a Paladin at capital — "holy warriors rally"
- Herb Mastery: AddGold(p, 50) per turn (proxy for healing = saved costs)
- Nature Awareness: already a stub (can't reveal map)
- Armageddon/Great Wasting/Meteor Storm: Terraform random enemy tiles to DEAD
- Chaos Surge: spawn Hell Hounds at capital — "chaos energy coalesces"
- Eternal Night/Evil Omens: drain ALL enemy players' mana by 20

The rest remain stubs with wiki descriptions.

### CITY_ENCHANT (16 spells) — IMPLEMENTABLE VIA CreateBuilding
City enchants that we CAN implement (all target player's capital):
- Wall of Stone: CreateBuilding(city, BuildingDB(IMPROVE_CITY_WALLS))
- Heavenly Light: CreateBuilding(city, BuildingDB(IMPROVE_TEMPLE))
- Dark Rituals: CreateBuilding(city, BuildingDB(IMPROVE_BARRACKS))
- Nature's Eye: CreateBuilding(city, BuildingDB(IMPROVE_GRANARY))
- Altar of Battle: CreateBuilding(city, BuildingDB(IMPROVE_COLOSSEUM))
- Gaia's Blessing: CreateBuilding(city, BuildingDB(IMPROVE_FANTASTIC_STABLE))
- Prosperity: AddGold(p, 200)
- Stream of Life: CreateBuilding(city, BuildingDB(IMPROVE_AQUEDUCT))
- Flying Fortress: CreateBuilding(city, BuildingDB(IMPROVE_COASTAL_FORTRESS))
- Spell Ward: CreateBuilding(city, BuildingDB(IMPROVE_CITY_WALLS))

### INSTANT_DAMAGE (55 spells) — MIXED

#### Offensive (require targeting, already partially done):
Kill spells: already have 10 bound signatures. Unbound offensive spells use
the generic "spawn Guardian Spirit at enemy city" proxy.

#### Utility (no targeting):
- Wall of Stone: CreateBuilding(city, IMPROVE_CITY_WALLS)
- Change Terrain: Terraform(capital.location, TERRAIN_GRASSLAND)
- Raise Volcano: Terraform near enemy to TERRAIN_DESERT
- Corruption: Terraform near enemy to TERRAIN_DEAD
- Transmute: AddGold(p, 150) — "transmute base materials to gold"
- Enchant Road: AddGold(p, 100) — "trade flows faster"
- Move Fortress: already stub (can't move cities)
- Nature's Cures: stub (can't heal)
- Resurrection/Raise Dead: stub (can't revive units)
- Healing/Mass Healing: stub (can't heal)
- Earth Lore: stub (can't reveal map)

### DISPEL (3 spells) — MANA DRAIN PROXY
- Dispel Evil: drain 20 mana from nearest enemy
- Disjunction True: drain 50 mana from enemy
- Dispel Magic True: drain 10 mana from enemy

## Summary of Real Effects to Implement

| # | Category | Spells Getting Real Effects |
|---|----------|--------------------------|
| 1 | city_enchant → CreateBuilding | 10 spells |
| 2 | instant_damage → Terraform | 3 spells (Change Terrain, Raise Volcano, Corruption) |
| 3 | instant_damage → AddGold | 3 spells (Transmute, Enchant Road, Prosperity) |
| 4 | instant_damage → CreateBuilding | 1 spell (Wall of Stone) |
| 5 | global_enchant → drain/spawn | 6 spells |
| 6 | dispel → mana drain | 3 spells |
| **Total** | | **26 spells getting real effects** |

## Acceptance Criteria

1. 26 spells have observable mechanical effects beyond mana deduction
2. All descriptions honestly reflect what the spell does in CTP2
3. No description promises something the engine can't deliver
4. Audit passes, turnloop clean
