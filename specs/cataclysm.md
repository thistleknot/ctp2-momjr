# Cataclysm Spec

Status: ACTIVE
Created: 2026-08-07
Disposition: Implementing Phase 1

## Summary

When a player researches their sphere's MASTER advance (the final rung of their
magic ladder), their territory undergoes a cataclysmic terrain transformation.
Land tiles within a radius of their cities permanently change to sphere-themed
terrain. This is the endgame expression of magical mastery — the wizard's power
reshapes the world itself.

## Trigger

`HandleEvent(GrantAdvance)` fires when any player completes research on their
sphere's Master advance:
- Life Master (ADVANCE_LIFE_MASTER)
- Nature Master (ADVANCE_NATURE_MASTER)
- Sorcery Master (ADVANCE_SORCERY_MASTER)
- Death Master (ADVANCE_DEATH_MASTER)
- Chaos Master (ADVANCE_CHAOS_MASTER)

The cataclysm fires ONCE per sphere (first player to reach Master triggers it).
Uses a global flag to prevent re-firing.

## Terrain Mapping

| Sphere | Target Terrain | Index | Visual Theme |
|--------|---------------|-------|--------------|
| Death | TERRAIN_DEAD | 17 | Dark wasteland, bones, decay |
| Life | TERRAIN_SPECIAL1 | 24 | Radiant fields, golden light |
| Chaos | TERRAIN_DESERT | 5 | Scorched volcanic wastes |
| Nature | TERRAIN_JUNGLE | 7 | Primal overgrowth, vines |
| Sorcery | TERRAIN_GLACIER | 3 | Crystalline frozen wastes |

## Radius and Targeting

- Transform all LAND tiles within radius 3 of each city the player owns
- Skip water tiles (index >= 10 and <= 16, or 22-23)
- Skip tiles that are already the target terrain (idempotent)
- Skip mountain tiles (8, 9, 18-21) — mountains resist transformation

## Implementation

```slic
HandleEvent(GrantAdvance) 'MomCataclysm' post {
    // Check if the granted advance is a sphere Master
    // Transform tiles around all cities of that player
    // Set a flag to prevent re-triggering
}
```

Key builtins (all base-verified):
- `Terraform(location, terrain_index)` — changes a tile
- `TerrainType(location)` — reads current terrain
- `GetNeighbor(location, direction, out_location)` — spiral scan
- `GetCityByIndex(player, index, out_city)` — iterate cities

## Radius-3 Scan Pattern

CTP2 has no "get all tiles within radius N" builtin. Scan must be done by
nested neighbor walks:
- Ring 0: city.location itself
- Ring 1: GetNeighbor(center, 0..7) — 8 tiles
- Ring 2: GetNeighbor of each ring-1 tile — up to 16 more
- Ring 3: GetNeighbor of each ring-2 tile — up to 24 more

Total: ~49 tiles per city. With 3-5 cities that's 150-250 Terraform calls.
This runs ONCE per game (on the GrantAdvance event), so performance is fine.

To avoid duplicate transforms (overlapping city radii), just Terraform
unconditionally — transforming an already-transformed tile is a no-op
(same terrain index).

## Simplified Approach (Phase 1)

Instead of a true radius-3 spiral (complex nested loops), use a simpler
approach: transform tiles in rings 0-2 only (center + 8 neighbors + their
neighbors). This gives ~25 tiles per city, stays within SLIC's comfort zone
for loop nesting.

Ring 0: Terraform(city.location)
Ring 1: for d = 0..7: GetNeighbor(city.location, d, loc1); Terraform(loc1)
Ring 2: for each ring-1 loc: for d = 0..7: GetNeighbor(loc1, d, loc2); Terraform(loc2)

## Phase 2 (future)

- Custom terrain graphics for sphere-transformed tiles
- SLIC combat bonus handler: units of the matching sphere get +attack/+defense
  on their own cataclysm terrain
- Spreading: each turn, the cataclysm expands 1 tile further (the world slowly
  converts)
- Counter-cataclysm: opposing sphere's Master advance can RECLAIM transformed
  tiles back to neutral terrain

## Acceptance Criteria

1. Researching a Master advance transforms land tiles around all player cities
2. Each sphere transforms to its designated terrain type
3. Water and mountain tiles are not affected
4. Cataclysm fires exactly once per player (flag prevents repeat)
5. Turnloop passes clean (0 SLIC errors)
6. Transformed tiles are visually distinct on the map
