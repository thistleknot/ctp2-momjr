# Tile Improvement Schema — Field Inventory by Class

**Source:** Original AE Mod `tileimp.txt` canonical format
**Purpose:** Defines every field per `Class:` type. Use this to construct CSVs and validate generated output.
**Canonical location:** `/tileimp_schema.md` (this is a reference copy)

---

## Flat Fields (Common to All Classes)

| Field | Type | Required | Notes |
|---|---|---|---|
| `Icon` | string | Yes | Icon identifier |
| `Tooltip` | string | Yes | Tooltip string key |
| `Statusbar` | string | Yes | Status bar string key |
| `Sound` | string | Yes | Sound effect ID |
| `Level` | int | Yes | Tier level (1-5) |

---

## Class:Farm (3 blocks: TILEIMP_FARMS, TILEIMP_ADVANCED_FARMS, TILEIMP_HYDROPONIC_FARMS)

| Field | Format | Count | Example |
|---|---|---|---|
| `Class:Farm` | bare flag | 1 | `Class:Farm` |
| `ConstructionTiles` | repeated int | 3 | `6`, `7`, `7` |
| `CantBuildOn` | repeated TERRAIN_* | 13 | `TERRAIN_BROWN_MOUNTAIN`, `TERRAIN_GLACIER`, ... |
| `Excludes:` | bare flag repeated | 10 | `ATM`, `Farm`, `LandDetector`, `Mine`, `OceanFarm`, `OceanDetector`, `OceanATM`, `Structure1`, `Structure2`, `OceanMine` |
| `TerrainEffect { ... }` | sub-block | 1 | See TerrainEffect schema below |

**TerrainEffect fields:** Terrain (3 values: DESERT, GRASSLAND, PLAINS), BonusFood, EnableAdvance, ProductionCost, ProductionTime, TilesetIndex

---

## Class:Mine (4 blocks: TILEIMP_MINES, TILEIMP_ADVANCED_MINES, TILEIMP_MEGA_MINES, + TILEIMP_RUINS)

| Field | Format | Count | Notes |
|---|---|---|---|
| `Class:Mine` | bare flag | 1 | |
| `ConstructionTiles` | repeated int | 3 | |
| `CantBuildOn` | repeated TERRAIN_* | 7 | Water terrains only |
| `Excludes:` | bare flag repeated | 10 | Same standard set |
| `GLHidden` | bare flag | 0-1 | Ruins only |
| `IsCityRuin` | bare flag | 0-1 | Ruins only |
| `TerrainEffect { ... }` | sub-block | 3 | One per terrain band |

**TerrainEffect fields:** Terrain (3/3/3 values per band), BonusProduction, [BonusGold], EnableAdvance, ProductionCost, [ProductionTime], TilesetIndex

**Terrain bands:**
- Band 1: DESERT, GRASSLAND, PLAINS
- Band 2: BROWN_HILL, HILL, WHITE_HILL
- Band 3: BROWN_MOUNTAIN, MOUNTAIN, WHITE_MOUNTAIN

---

## Class:OceanMine (3 blocks: TILEIMP_UNDERSEA_MINES, TILEIMP_ADVANCED_UNDERSEA_MINES, TILEIMP_MEGA_UNDERSEA_MINES)

| Field | Format | Count | Notes |
|---|---|---|---|
| `Class:OceanMine` | bare flag | 1 | |
| `ConstructionTiles` | repeated int | 3 | |
| `CantBuildOn` | repeated TERRAIN_* | 14 | All land terrains |
| `Excludes:` | bare flag repeated | 10 | Standard set |
| `TerrainEffect { ... }` | sub-block | 3 | One per water abyss type |

**TerrainEffect:** Terrain (single: WATER_DEEP / WATER_RIFT / WATER_VOLCANO), BonusProduction, [BonusGold], EnableAdvance, ProductionCost, ProductionTime, TilesetIndex

---

## Class:Structure1 (3 blocks: TILEIMP_AIR_BASES, TILEIMP_FORTIFICATIONS, TILEIMP_PROCESSING_TOWER)

| Field | Format | Count | Notes |
|---|---|---|---|
| `Class:Structure1` | bare flag | 1 | |
| `ConstructionTiles` | repeated int | 3 | |
| `CantBuildOn` | repeated TERRAIN_* | 7 | Water terrains; absent in PROCESSING_TOWER |
| `Excludes:` | bare flag repeated | 10 | Standard set |
| `IntBorderRadius` | int | 0-1 | Fortifications only |
| `SquaredBorderRadius` | int | 0-1 | Fortifications only |
| `TerrainEffect { ... }` | sub-block | 1-2 | Varies per block |

**TerrainEffect special flags:** Airport (Air Bases), CanUpgrade (Fort), Endgame (Processing Tower), DefenseBonus (Fort), [VisionRange], [RadarRange]

---

## Class:OceanFarm (3 blocks: TILEIMP_NETS, TILEIMP_FISHERIES, TILEIMP_AUTOMATED_FISHERIES)

| Field | Format | Count | Notes |
|---|---|---|---|
| `Class:OceanFarm` | bare flag | 1 | |
| `ConstructionTiles` | repeated int | 3 | |
| `CantBuildOn` | repeated TERRAIN_* | 14 | All land terrains |
| `Excludes:` | bare flag repeated | 10 | Standard set |
| `TerrainEffect { ... }` | sub-block | 3 | One per water band |

**TerrainEffect:** Terrain (5/3/1 values), BonusFood, EnableAdvance, ProductionCost, ProductionTime, TilesetIndex

---

## Class:ATM (3 blocks: TILEIMP_TRADING_POST, TILEIMP_OUTLET_MALL, TILEIMP_NATURE_PRESERVE)

| Field | Format | Count | Notes |
|---|---|---|---|
| `Class:ATM` | bare flag | 1 | |
| `ConstructionTiles` | repeated int | 3 | |
| `CantBuildOn` | repeated TERRAIN_* | 7 | Water terrains |
| `Excludes:` | bare flag repeated | 10 | Standard set |
| `TerrainEffect { ... }` | sub-block | 1 | |

**TerrainEffect:** Terrain (7 land types), BonusGold, EnableAdvance, ProductionCost, ProductionTime, TilesetIndex

---

## Class:OceanATM (2 blocks: TILEIMP_PORT, TILEIMP_DRILLING_PLATFORM)

| Field | Format | Count | Notes |
|---|---|---|---|
| `Class:OceanATM` | bare flag | 1 | |
| `ConstructionTiles` | repeated int | 3 | |
| `CantBuildOn` | repeated TERRAIN_* | 0/19 | DrillingPlatform: none; Port: 19 |
| `Excludes:` | bare flag repeated | 10 | Standard set |
| `TerrainEffect { ... }` | sub-block | 1 | |

---

## Class:LandDetector (2 blocks: TILEIMP_LISTENING_POSTS, TILEIMP_RADAR_STATIONS)

| Field | Format | Count | Notes |
|---|---|---|---|
| `Class:LandDetector` | bare flag | 1 | |
| `CanSee:Standard` | bare flag | 1 | |
| `ConstructionTiles` | repeated int | 3 | |
| `CantBuildOn` | repeated TERRAIN_* | 7 | Water terrains |
| `Excludes:` | bare flag repeated | 10 | Standard set |
| `TerrainEffect { ... }` | sub-block | 1 | |

**TerrainEffect special:** Radar (bare flag), ListeningPost (bare flag), VisionRange, RadarRange

---

## Class:Road (3 blocks: TILEIMP_ROAD, TILEIMP_RAILROAD, TILEIMP_MAGLEV)

| Field | Format | Count | Notes |
|---|---|---|---|
| `Class:Road` | bare flag | 1 | |
| `ConstructionTiles` | repeated int | 3 | |
| `CantBuildOn` | repeated TERRAIN_* | 7 | Water terrains |
| `Excludes:` | bare flag repeated | 2 | `Road`, `OceanRoad` only |
| `TerrainEffect { ... }` | sub-block | 4 | One per difficulty band |

**TerrainEffect:** Terrain (multi-value), MoveCost, Freight, EnableAdvance, ProductionCost, ProductionTime, TilesetIndex

---

## Class:OceanDetector (1 block: TILEIMP_SONAR_BUOYS)

| Field | Format | Count | Notes |
|---|---|---|---|
| `Class:OceanDetector` | bare flag | 1 | |
| `CanSee:Underwater` | bare flag | 1 | |
| `CanSee:Standard` | bare flag | 1 | |
| `ConstructionTiles` | repeated int | 3 | `50`, `50`, `50` |
| `CantBuildOn` | repeated TERRAIN_* | 14 | All land terrains |
| `Excludes:` | bare flag repeated | 10 | Standard set |
| `TerrainEffect { ... }` | sub-block | 1 | |

---

## Class:OceanRoad (1 block: TILEIMP_UNDERSEA_TUNNEL)

| Field | Format | Count | Notes |
|---|---|---|---|
| `Class:OceanRoad` | bare flag | 1 | |
| `ConstructionTiles` | repeated int | 3 | `50`, `50`, `50` |
| `CantBuildOn` | repeated TERRAIN_* | 14 | All land terrains |
| `Excludes:` | bare flag repeated | 2 | `Road`, `OceanRoad` |
| `TerrainEffect { ... }` | sub-block | 3 | |

---

## Class:Terraform (12 blocks: TILEIMP_TERRAFORM_*)

| Field | Format | Count | Notes |
|---|---|---|---|
| `Class:Terraform` | bare flag | 1 | |
| `TerraformTerrain` | TERRAIN_* | 1 | Target terrain type |
| `Column` | int | 1 | UI column position (0-3) |
| `ConstructionTiles` | repeated int | 3 | Always `1`, `1`, `1` |
| `CantBuildOn` | repeated TERRAIN_* | 9 | Water + kelp + reef |
| `Excludes:` | bare flag repeated | 12 | All non-terraform classes |
| `GLHidden` | bare flag | 1 | Always present |
| `TerrainEffect { ... }` | sub-block | 1 | |

**TerrainEffect:** Terrain (single, same as TerraformTerrain), EnableAdvance, TilesetIndex (always 1)

---

## Standard Excludes Set

The standard 10-class Excludes set used by most tile improvement types:
```
Excludes:ATM, Excludes:Farm, Excludes:LandDetector, Excludes:Mine,
Excludes:OceanFarm, Excludes:OceanDetector, Excludes:OceanATM,
Excludes:Structure1, Excludes:Structure2, Excludes:OceanMine
```

Exceptions:
- **Road/OceanRoad** classes: only `Excludes:Road, Excludes:OceanRoad`
- **Terraform** class: all 12 non-terraform classes
- **DrillingPlatform** (OceanATM): no Excludes at all

---

## TerrainEffect Sub-Block Format

```
   TerrainEffect {
      Terrain TERRAIN_* [TERRAIN_* ...]
      [BonusFood N]
      [BonusProduction N]
      [BonusGold N]
      [MoveCost N]
      [Freight N]
      [VisionRange N]
      [RadarRange N]
      [DefenseBonus N.N]
      [Airport]
      [CanUpgrade]
      [Endgame]
      [Radar]
      [ListeningPost]
      EnableAdvance ADVANCE_*
      [ProductionCost N]
      [ProductionTime N]
      TilesetIndex N
   }
```

Fields in `[...]` are optional per Class type (see per-Class tables above).
