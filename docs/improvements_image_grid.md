# Improvement / Wonder Image Grid — Lessons Learned

## Source File

```
H:\Games\civ2\MOMJR\MOMJR\Improvements.bmp
```

Dimensions: **585 × 370 px**, 24-bit RGB, no palette.

---

## Grid Layout (`sprite_atlas_config.csv` sheet: `improvements` / `wonder_atlas`)

Both improvements (slots 0–39) and wonders (slots 40+) share the **same BMP file**.

| Parameter     | Value |
|---------------|-------|
| bmp_file      | `Improvements.bmp` |
| pitch_w       | 73 px |
| pitch_h       | 41 px |
| cell_w        | 73 px |
| cell_h        | 41 px |
| n_cols        | 8     |
| n_rows        | 9     |
| border_inset_lead  | 3 px (1 magenta + 2 gray) |
| border_inset_trail | 2 px (2 gray; next magenta starts next pitch) |

**Usable cell area:** 68 × 36 px per cell (content starts at pixel 76,3 for cell 1; 3,3 for cell 0).

Pixel anatomy of each pitch boundary:
```
[magenta][gray][gray][...content 68px...][gray][gray] | [magenta of next cell]
    0       1     2   3                70   71    72        73
```

Cell top-left from image origin (0-indexed, y from top):
```
x = col * 73      (col = cell_index % 8)
y = row * 41      (row = cell_index // 8)
```

---

## Cell Index Map (improvements.csv, slots 0–39)

| Index | Col | Row | Top-left px | Name |
|-------|-----|-----|-------------|------|
| 0  | 0 | 0 | (0, 0)     | Nothing |
| 1  | 1 | 0 | (73, 0)    | Wizard's Fortress |
| 2  | 2 | 0 | (146, 0)   | Barracks |
| 3  | 3 | 0 | (219, 0)   | Granary |
| 4  | 4 | 0 | (292, 0)   | Temple |
| 5  | 5 | 0 | (365, 0)   | MarketPlace |
| 6  | 6 | 0 | (438, 0)   | Library |
| 7  | 7 | 0 | (511, 0)   | Courthouse |
| 8  | 0 | 1 | (0, 41)    | City Walls |
| 9  | 1 | 1 | (73, 41)   | Aqueduct |
| 10 | 2 | 1 | (146, 41)  | Bank |
| 11 | 3 | 1 | (219, 41)  | Cathedral |
| 12 | 4 | 1 | (292, 41)  | University |
| 13 | 5 | 1 | (365, 41)  | xMass Transit |
| 14 | 6 | 1 | (438, 41)  | Colosseum |
| 15 | 7 | 1 | (511, 41)  | Mechanician's Guild |
| 16 | 0 | 2 | (0, 82)    | xManufacturing Plant |
| 17 | 1 | 2 | (73, 82)   | xSDI Defense |
| 18 | 2 | 2 | (146, 82)  | xRecycling Center |
| 19 | 3 | 2 | (219, 82)  | xPower Plant |
| 20 | 4 | 2 | (292, 82)  | xHydro Plant |
| **21** | **5** | **2** | **(365, 82)** | **Primal Source** |
| 22 | 6 | 2 | (438, 82)  | Merchant's Guild |
| 23 | 7 | 2 | (511, 82)  | Sewer System |
| 24 | 0 | 3 | (0, 123)   | xSupermarket |
| 25 | 1 | 3 | (73, 123)  | xSuperhighways |
| 26 | 2 | 3 | (146, 123) | Beacon of Wisdom |
| 27 | 3 | 3 | (219, 123) | SAM Missile Battery |
| 28 | 4 | 3 | (292, 123) | Coastal Fortress |
| 29 | 5 | 3 | (365, 123) | Solar Harness |
| 30 | 6 | 3 | (438, 123) | Harbor |
| 31 | 7 | 3 | (511, 123) | Sea Mines |
| 32 | 0 | 4 | (0, 164)   | Fantastic Stable |
| 33 | 1 | 4 | (73, 164)  | xPolice Station |
| 34 | 2 | 4 | (146, 164) | Port |
| 35 | 3 | 4 | (219, 164) | Transporter |
| 36 | 4 | 4 | (292, 164) | xSS Structural |
| 37 | 5 | 4 | (365, 164) | xSS Component |
| 38 | 6 | 4 | (438, 164) | xSS Module |
| 39 | 7 | 4 | (511, 164) | x(Capitalization) |

Wonders continue at slot 40+ (rows 5–8 of the same BMP).

---

## Known Issues / Lessons Learned

### 1. Improvements and Wonders share one BMP
`Improvements.bmp` contains **both** city improvements (slots 0–39, rows 0–4)
and wonders (slots 40+, rows 5–8). The `improvements` and `wonder_atlas` sheet
keys in `sprite_atlas_config.csv` both point to the same file with different
cell-index windows. Confusing them causes wrong art to be assigned.

### 2. TGA bit-depth mismatch causes green noise
`save_tga_rgb555` writes **16-bit** TGA (X1R5G5B5).
CTP2 Great Library portraits loaded via `uniticon.txt` `FirstFrame` appear to
expect **16-bit** TGA. Any TGA written as 24-bit (e.g., by an older extraction
pass or PIL's default save) will display as green/black noise in-engine.
**Always use `save_tga_rgb555` (not `PIL.Image.save`) for all uniticon TGAs.**

### 3. Green is a transparency sentinel in the extractor
`civ2_sprite_extractor.py` treats pure green `(0, 255, 0)` as a background/
transparency color. Cells in `Improvements.bmp` where the dominant color is
pure green will be skipped by the extractor (no TGA written). If a slot appears
green in the source BMP, the slot was either unused or the BMP uses green as
its palette background.

### 4. building_uniticon.csv is the canonical proxy override path
For CTP2-port improvements that have no CIV2 art (20 buildings.txt-only
additions), use `building_uniticon.csv` to wire proxy TGAs. The generator
applies this CSV before the improvement reconciliation pass, so the
reconciliation skips blocks already pointing to non-stock art.
Never hard-code proxy TGA names directly in `uniticon.txt` — let the generator
own that file entirely.

### 5. Re-extraction wipes existing TGAs
Running `ctp2_generator.py` regenerates all extracted TGAs from the source BMP.
If a TGA on disk was hand-corrected, the next generator run overwrites it.
The correct fix is always to update `improvements.csv` (cell_index) or
`sprite_atlas_config.csv` (crop coords), not the TGA directly.

### 6. Asymmetric border crop — lead=3, trail=2

Each pitch cell in `Improvements.bmp` and `Icons.bmp` has this pixel structure:

```
[magenta][gray][gray][...content...][gray][gray] | [magenta of next cell]
```

The magenta separator is the **first** pixel of each pitch interval (not the last).
This makes the crop asymmetric: strip 3 from the start (1 magenta + 2 gray) and
2 from the end (2 gray; the trailing magenta belongs to the next cell's pitch).

`sprite_atlas_config.csv` encodes this as `border_inset_lead=3, border_inset_trail=2`.
A single symmetric `border_inset` value **cannot** represent this correctly.
Using `border_inset=2` symmetrically left the magenta line and one gray pixel
visible as a gray ring around every portrait in-engine.

### 7. `extract_sheet` must use `save_tga_rgb555`, not `save_tga`

`save_tga` writes 24-bit RGB. `save_tga_rgb555` writes 16-bit X1R5G5B5.
CTP2 uniticon.txt portrait paths require 16-bit or render as green/black noise.
The `extract_icon_units` path already used `save_tga_rgb555`; `extract_sheet`
(used for improvements, advances) was incorrectly using `save_tga`. Now fixed.

---

## Resolution

All three issues (bit depth, wrong grid dimensions, wrong border crop) are fixed
as of commit d56d966 (grid/16-bit) and 71e08c6 (asymmetric crop).
City Lighting Alchemical portrait confirmed clean in-engine: correct art,
no gray border ring, no green noise.
