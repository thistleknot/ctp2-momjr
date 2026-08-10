# MkDocs Player's Guide — Next Session Prompt

## Current State

The player's guide is live at `mkdocs serve` from `Scenarios/mom/`. All unit icons
are manually reviewed and assigned. The guide has 31+ pages across 5 sections.

Key scripts:
- `docs/gen_reference.py` — generates reference table markdown (units, spells, advances, buildings, terrain)
- `docs/extract_unit_icons.py` — crops unit icons from observer sheet (baseline)
- `docs/final_icon_fix.py` — hybrid: observer sheet base + TGA overrides + special cases
- `docs/extract_dimension_icons.py` — extracts advance/building/terrain icons from named TGA files
- `docs/build_art_review_xlsx.py` — generates Excel review workbooks
- `docs/audit_icons_vision.py` — nemotron-based icon classification (batch async)
- `docs/validate_all_icons.py` — nemotron scoring for individual icons
- `docs/sample_validate.py` — random 20-sample validation pass

Custom art lives at: `C:\Users\user\Documents\wiki\games\ctp2\art\`
(priest.png, crystal golem.png, dwarf crossbow.png, runesmith.png, arch mage.png, drow.tga, Treant.tga)

## Pending Tasks

### 1. Wire advance icons inline in the advances reference table
- 88 icons already extracted to `docs/img/advances/` (slug like `chivalry.png`)
- Update `gen_reference.py` `gen_advances()` to add an Icon column with `![](../img/advances/{slug}.png)`
- The CSV `icon` field is `ICON_ADVANCE_CHIVALRY` → slug = `chivalry`

### 2. Wire building icons inline in the buildings reference table
- 46 icons already extracted to `docs/img/buildings/` (slug like `barracks.png`)
- Update `gen_reference.py` `gen_buildings()` to add an Icon column
- The CSV `icon` field is `ICON_IMPROVE_BARRACKS` → slug = `barracks`

### 3. Fix terrain icon extraction (0 extracted)
- The terrain CSV column is `icon` with values like `ICON_TERRAIN_FORESTS`
- The TGA files are named `ICON_TERRAIN_FORESTS.tga` but might be `.TGA`
- Check case sensitivity and whether the files exist at all
- If they don't exist as named TGAs, check for `TILEIMP_` prefix files (36 exist)

### 4. Add artifact icons using gem artwork
- The crystal/gem LotR images (MGGP025-061) make good artifact placeholders
- Copy a selection to `docs/img/artifacts/` and embed in `docs/systems/artifacts.md`
- Use different colored gems for different artifact types (blue=sorcery, red=chaos, etc.)
- Source: `docs/img/lotr/MGGP028.png` (blue), `MGGP029.png` (green), `MGGP030.png` (gold), etc.

### 5. Clean up stray files
- Remove `docs/img/units/test_centaur.png`
- Remove `*.bak` TGA files from `scen0000/default/graphics/pictures/`

### 6. LotR catalog page verification
- `docs/reference/lotr-catalog.md` exists in nav but may need regeneration
- Individual PNGs are in `docs/img/lotr/` (458 files, RGB mode, visible)
- The catalog should show each image in a table with its LotR unit name from uniticon.txt

### 7. Regenerate after changes
```
cd Scenarios\mom
python docs/extract_dimension_icons.py
python docs/gen_reference.py
mkdocs build --strict
mkdocs serve --livereload
```

## Art Source Reference

| Source | Location | Grid | Notes |
|--------|----------|------|-------|
| MoMJR | `docs/img/momjr_units_sheet.png` | 9x7, 65px cells | Labeled with RULES.TXT names |
| HoMM2 | `docs/img/HoMM2_Units_sheet.png` | 9x8, 65x49px cells | Labeled with RULES.TXT names |
| LotR | `docs/img/lotr_units_sheet.png` | 8 cols, 110px cells | Labeled with uniticon.txt names (CTP2 stock repurposed) |
| Custom | `C:\Users\user\Documents\wiki\games\ctp2\art\` | Individual PNGs | User-created transparent bg |

## Key Extraction Method (MoMJR/HoMM2)

```python
# Remove only these two exact background colors:
magenta = (cell[:,:,0] > 220) & (cell[:,:,1] < 40) & (cell[:,:,2] > 220)
grey_purple = ((cell[:,:,0] > 120) & (cell[:,:,0] < 170) &
               (cell[:,:,1] > 60) & (cell[:,:,1] < 100) &
               (cell[:,:,2] > 120) & (cell[:,:,2] < 170))
cell[magenta] = [24, 24, 24]
cell[grey_purple] = [24, 24, 24]
```

## Validation Gate

Before presenting any icon change, run nemotron validation:
```
python docs/validate_all_icons.py <slug1> <slug2> ...
```
All must score >= 50 before committing.
