# CIV2 → CTP2 Entity Mapping

Reference for the MoM Jr port. Maps each top-level game dimension from CIV2
to its CTP2 equivalent, including known structural differences and art source
implications.

| CIV2 Dimension | CTP2 Dimension | Notes |
|---|---|---|
| Advances | Advances | Direct 1:1. Icons extracted from `Icons.bmp` (7×8 grid). |
| Units | Units | Direct 1:1. Art extracted from `Units.bmp` via slot detection. |
| City Improvements | City Improvements / Buildings | Direct 1:1. Art from `Improvements.bmp` cells 0–39 (rows 0–4). |
| Wonders *(subtype of Improvements in CIV2)* | Wonders *(separate dimension in CTP2)* | **Key difference**: CIV2 stores wonder art in the same `Improvements.bmp` grid as city improvements (cells 40+ / rows 5–8). CTP2 treats wonders as a fully separate entity with its own GL sections, uniticon blocks, and string keys. The `wonder_atlas` sheet key in `sprite_atlas_config.csv` handles this split — same source BMP, different cell index range. |
| Terrain | Terrain | Tile art; not yet ported. |
| Caravan commodities / trade lane data | Goods | Trade route goods definitions. |
| *(no CIV2 equivalent)* | Tile Improvements | CTP2-only: roads, farms, mines, etc. Art sourced from `Improvements.bmp` via `ICON_TILEIMP_*` identifiers. |
| Governments | Governments | Direct 1:1. |
| Orders / command text | Unit Orders | Button labels and command strings. |
| Leaders / personalities | *(no direct CTP2 equivalent)* | CIV2 leader AI personalities have no clean CTP2 mapping; absorbed into difficulty/AI strategy files. |
| Events | SLIC | CIV2 Events scripting maps to CTP2 SLIC scripting language. |
| Civilopedia / labels / game text | Concepts | Great Library text entries + string files. |
| Scenario art sheets and sounds | Scenario Art | BMP sprite sheets and WAV/sound definitions. |

## Art Source Notes

- **`Improvements.bmp`** (585×370, 8×9 grid, pitch 73×41, `border_inset_lead=3 trail=2`):
  - Rows 0–4 (cells 0–39): City Improvements
  - Rows 5–8 (cells 40–71): Wonders
  - Both dimensions share one BMP; split handled by `sheet_key` (`improvements` vs `wonder_atlas`) and cell index range in the CSV.

- **`Icons.bmp`** (same grid geometry 7×8): Advances only.

- **`Units.bmp`**: Unit portraits; slot geometry detected dynamically (no clean grid).

## CTP2-Only Improvements (no CIV2 art source)

These were added by the porter and have no slot in `Improvements.bmp`. They must
use proxy TGA mappings via `building_uniticon.csv`:

- City Lighting variants (Alchemical, Chaos Magic, Natural Mge, Spellcraft)
- Alchemist Guild, Sages Guild, Animists Guild, Artisans Guild
- Aviary, City Militia, Magic Recharging Center
- Port Facility, Offshore Trading Center
- Explorer Hull, Explorer Crew, Explorer Extraplanar Drive
- City Wide Ward Spell, Magic Roadways, Aerial Warding, City Trolley System
