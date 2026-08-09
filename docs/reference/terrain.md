# Terrain Effects

All terrain types and their properties, generated from `terrain.csv`.

## Terrain Types

| ID | Type | Movement | Resources |
|----|------|----------|-----------|
| TERRAIN_FOREST | Forest | Air; Land | ONE, TWO |
| TERRAIN_PLAINS | Plains | Air; Land | ONE, TWO |
| TERRAIN_TUNDRA | Tundra | Air; Land | ONE |
| TERRAIN_GLACIER | Glacier | Air; Land | — |
| TERRAIN_GRASSLAND | Grassland | Air; Land | TWO, ONE |
| TERRAIN_DESERT | Desert | Air; Land | ONE, TWO |
| TERRAIN_SWAMP | Swamp | Air; Land | ONE, TWO |
| TERRAIN_JUNGLE | Jungle | Air; Land | TWO, ONE |
| TERRAIN_MOUNTAIN | Mountain | Air; Mountain | ONE, TWO |
| TERRAIN_HILL | Hill | Air; Land | TWO, ONE |
| TERRAIN_WATER_SHALLOW | WaterShallow | Air; Sea; ShallowWater | TWO, ONE |
| TERRAIN_WATER_DEEP | WaterDeep | Air; Sea | TWO, ONE |
| TERRAIN_WATER_VOLCANO | WaterVolcano | Air; Sea | ONE, TWO |
| TERRAIN_WATER_BEACH | WaterBeach | Air; Sea; ShallowWater | ONE, TWO |
| TERRAIN_WATER_SHELF | WaterShelf | Air; Sea | ONE, TWO |
| TERRAIN_WATER_TRENCH | WaterTrench | Air; Sea | TWO, ONE |
| TERRAIN_WATER_RIFT | WaterRift | Air; Sea | TWO, ONE |
| TERRAIN_DEAD | Dead | Air; Land | — |
| TERRAIN_BROWN_HILL | BrownHill | Air; Land | ONE, TWO |
| TERRAIN_BROWN_MOUNTAIN | BrownMountain | Air; Mountain | ONE, TWO |
| TERRAIN_WHITE_HILL | WhiteHill | Air; Land | ONE, TWO |
| TERRAIN_WHITE_MOUNTAIN | WhiteMountain | Air; Mountain | ONE, TWO |
| TERRAIN_WATER_KELP | WaterKelp | Air; Sea; ShallowWater | ONE, TWO |
| TERRAIN_WATER_REEF | WaterReef | Air; Sea; ShallowWater | ONE, TWO |
| TERRAIN_SPECIAL1 | Special | Air; Land | — |
| TERRAIN_SPECIAL2 | Special | Air; Land | — |

## Cataclysm Terrain Mapping

When a sphere's Master advance is researched, surrounding tiles transform:

| Sphere | Target Terrain | Index | Theme |
|--------|---------------|-------|-------|
| Death | TERRAIN_DEAD | 17 | Dark wasteland |
| Life | TERRAIN_SPECIAL1 | 25 | Radiant fields |
| Chaos | TERRAIN_DESERT | 5 | Volcanic wastes |
| Nature | TERRAIN_JUNGLE | 7 | Primal overgrowth |
| Sorcery | TERRAIN_GLACIER | 3 | Crystal frozen |

**Total: 26 terrain types**
