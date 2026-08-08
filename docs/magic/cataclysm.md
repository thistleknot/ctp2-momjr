# Cataclysm

## The World Reshapes

When a player researches their sphere's **Master advance** (the final rung of
the magic ladder), a cataclysm triggers: terrain around their cities permanently
transforms into sphere-themed landscape. The endgame isn't just bigger armies —
it's the world itself changing.

## Trigger

The cataclysm fires when a player completes research on:

| Sphere | Master Advance | Prereq |
|--------|---------------|--------|
| Life | Life Master | Life Wizard |
| Nature | Nature Master | Nature Wizard |
| Sorcery | Sorcery Master | Sorcery Wizard |
| Death | Death Master | Death Wizard |
| Chaos | Chaos Master | Chaos Wizard |

The cataclysm fires **once per player**. Multiple players can each trigger their
own cataclysm by researching their respective Master advance.

## Terrain Transformation

| Sphere | Target Terrain | Visual Theme |
|--------|---------------|--------------|
| Death | Dead Land | Dark wasteland, bones, decay |
| Life | Special (Elysian) | Radiant fields, golden light |
| Chaos | Desert (Volcanic) | Scorched volcanic wastes |
| Nature | Jungle (Primal) | Primal overgrowth, thick vines |
| Sorcery | Glacier (Crystal) | Crystalline frozen wastes |

## Radius and Rules

- Transforms all **land tiles** within radius 2-3 of each city the player owns
- **Skips** water tiles (oceans, seas, rivers)
- **Skips** mountain tiles (mountains resist magical transformation)
- **Idempotent** — transforming an already-transformed tile is a no-op
- Overlapping city radii don't cause double-transforms

## What Players See

When another player's cataclysm triggers:
1. Terrain around their cities visibly changes on the map
2. This is a clear signal: "this wizard has reached Master level"
3. Other players know endgame is approaching
4. Adapted terrain gives the cataclysm player home-field advantage

## Future Plans (Phase 2)

- **Combat bonuses**: Units of the matching sphere get +attack/+defense on their
  own cataclysm terrain
- **Spreading**: Each turn, the cataclysm expands 1 tile further
- **Counter-cataclysm**: Opposing sphere's Master advance can reclaim tiles
- **Custom terrain graphics**: Unique visuals for sphere-transformed tiles

## Thematic Inspiration

From Lord of the Rings: Mordor IS death magic, Lothlorien IS life magic. The
landscape belongs to its master and reflects their power. A wizard at the peak
of their sphere doesn't just cast spells — they reshape reality.

From HoMM: Each faction's territory has its own visual identity. You can tell
who controls an area by looking at the terrain. The cataclysm makes this
dynamic rather than static.

## Implementation Notes

Uses base-verified SLIC builtins:
- `Terraform(location, terrain_index)` — changes a tile
- `TerrainType(location)` — reads current terrain
- `GetNeighbor(location, direction, out_location)` — scans adjacent tiles
- `HandleEvent(GrantAdvance)` — triggers on research completion

Performance: ~25 tiles per city, 3-5 cities = 75-125 Terraform calls. Runs once
per game. No performance concern.
