---
inclusion: fileMatch
fileMatchPattern: "**/tools/**"
---

# MoM Generator Pipeline

Included when working on files under `Scenarios/mom/tools/`.

## Entry Point

```powershell
cd "H:\Program Files(x86)\Activision\Call To Power 2\Scenarios\mom\tools"
python ctpedit.py patch <dimension>
python ctpedit.py status
python ctpedit.py show <dimension>
```

## Source of Truth

| Dimension | CSV | Output |
|---|---|---|
| Advances | `momjr_csv/advances.csv` | `Advance.txt` |
| Units | `momjr_csv/units.csv` + `unit_mask.csv` | `Units.txt`, `uniticon.txt` |
| Buildings | `momjr_csv/improvements.csv` + `building_uniticon.csv` | `buildings.txt` |
| Wonders | `momjr_csv/wonders.csv` | `Wonder.txt` |
| Tile Improvements | `momjr_csv/tileimp.csv` | `tileimp.txt` |
| Governments | `momjr_csv/governments.csv` | `govern.txt` |
| Terrain | `momjr_csv/terrain.csv` | `Terrain.txt` |

## Generator Owns All Output

Files under `Scenarios/mom/scen0000/` are generated. To change them:
1. Edit the source CSV
2. Or fix `ctpedit.py` / `ctp2_generator.py` / `ctp2_parser.py`
3. Re-run the generator

The workbook `mom_dimension_inventory.xlsx` is also generator-owned output.

## Validation After Every Change

```powershell
python ctp2_generator.py
python mom_audit.py              # FAIL: 0
python verify_all.py             # GL integrity, CRLF, depth
python validate_scenario.py --scenario scen0000  # grammar, charset, idents
python validate_all_surfaces.py  # all 7 reference surfaces
```

## Key Constraints

- `gamefile.txt` is the engine load manifest. Improvements load from `buildings.txt`,
  NOT `Improve.txt`. A file absent from gamefile.txt is never loaded.
- Generator adds but NEVER removes. Removing a record requires surgical grep across
  all generated files (10+ surfaces for advances).
- Cascade contract: masking a unit cascades to Units.txt + Units_historic.txt +
  Units_release.txt. Masking a building cascades to 14+ files (see HARNESS.md).
- Run all tools with `PYTHONIOENCODING=utf-8` on Windows.
- String files must use `open(path, 'w', newline='')` — default `write_text()` produces
  CRLF which the engine reads as trailing `\r` on every key.

## Wiki Sources

- CTP2 modding docs: `C:\Users\user\Documents\wiki\games\ctp2\`
  - `Mod guide.md` (63K), `mom spells.txt`, `mom min maxing.txt`, `Review.txt`
- MoM wiki mirror: `F:\Documents\wiki\games\mom\site\`
  - `index.json` — 878 pages, `{t: title, s: slug, x: flattened text}` format
  - `p/<Slug>__<hash>.html` — rendered pages (fallback when `x` loses tables)
  - `images/<name>__<hash>.<ext>` — 1834 assets (unit/building/spell icons)

## Policy: `mod_policy.json`

The generator reads `mod_policy.json` for genre-filter decisions, mana economy
constants, and hidden-set definitions. Future: terrain gating, spell costs.
