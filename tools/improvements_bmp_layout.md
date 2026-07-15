# Improvements.bmp Layout — Shared Grid Discovery

## TL;DR

`Improvements.bmp` contains **both** city improvement icons **and** wonder icons
in a single flat grid. Slot index in the BMP = `@IMPROVE` line index (0-based,
row-major). Do **not** use pixel content to determine slot usage.

It is **also the advance/tech art source** — the CANONICAL contract (from the
`mom_dimension_inventory*.xlsx` `advances` sheet, mirrored by `advances.csv`
`cell_index`): **87 advances → 11 thematic category cells**, each category lifting
one building/wonder cell:

| cell | art (@IMPROVE slot) | category | advances |
|---|---|---|---|
| 2  | Barracks          | military/heroic        | 9 |
| 7  | Courthouse        | governance/religion    | 7 |
| 10 | Bank              | economy/navigation     | 8 |
| 30 | Harbor            | construction/materials | 5 |
| 40 | Gaia's Shrine     | Nature realm           | 6 |
| 44 | Great Library     | knowledge/arcane       | 27 |
| 45 | Oracle            | Life realm             | 6 |
| 46 | Wall of Bone      | Death realm            | 6 |
| 56 | Eldritch College  | Sorcery realm          | 6 |
| 62 | Forge of Chaos    | Chaos realm            | 6 |
| 66 | Celestial Beacon  | Future Technology      | 1 |

Intra-category shared art is the DESIGN, not a defect — do not de-duplicate.
`cell_index` is deliberately dual-use: the same category value is also the
generator's advance cost weight. `civ2_sprite_extractor.py` additionally supports
an optional `art_cell_index` override column (values beyond the sheet, e.g. 999,
skip extraction) — currently unused; only add it if art ever needs to diverge
from cost buckets. `momjr_csv/advances_cell_remap.csv` is a SUPERSEDED
content-scoring experiment kept for history — do not consume it.

---

## Grid geometry (MoMJR)

| Property | Value |
|---|---|
| File | `H:\Games\civ2\MOMJR\MOMJR\Improvements.bmp` |
| Image size | 585 × 370 px |
| Cell pitch | 73 × 41 px |
| Grid | 8 cols × 9 rows = 72 cells |
| Used cells | 0–67 (68 entries = length of `@IMPROVE` in RULES.TXT) |
| Padding | Cells 68–71 (no `@IMPROVE` entry — skip) |

## Slot → dimension mapping

| Slot range | Dimension | Output icon prefix | CTP2 file |
|---|---|---|---|
| 0–39 | City improvements | `ICON_IMPROVE_*` | `improveicon.txt` |
| 40–67 | Wonders | `ICON_WONDER_*` | `wondericon.txt` |

The split point (slot 40) was derived by counting `@IMPROVE` entries in
`RULES.TXT` where `maintenance == 0` (wonders) cluster at the tail, matching
`@ENDWONDER` slot order exactly.

---

## Rules for any CIV2 mod port

1. **Never use pixel content** to decide whether a cell is used. Inherited
   base-game cells look non-empty even when the mod never overrides them.

2. **Count `@IMPROVE` entries** from `RULES.TXT` to get the total slot count.
   That count is the number of cells to extract — the rest is padding.

3. **Find the wonder split** by scanning from the end of `@IMPROVE` for entries
   where `maintenance == 0`. Those are wonders, in `@ENDWONDER` slot order.

4. **cell_index in CSV = @IMPROVE slot index** (0-based). Set this in both
   `improvements.csv` and `wonders.csv` before running the extractor.
   - `improvements.csv`: `cell_index = row_index` (0 … split−1)
   - `wonders.csv`: `cell_index = row_index + split_offset` (split … total−1)

5. **`improveicon.csv`** (feeds `improveicon.txt`) covers only improvement slots
   (0 … split−1). Wonder slots are handled by `wondericon.csv` / `wonders.csv`.

---

## How extraction is wired

```
sprite_atlas_config.csv
  improvements  → Improvements.bmp  8 cols, 73×41 pitch  → ICON_IMPROVE_*.tga
  wonder_atlas  → Improvements.bmp  8 cols, 73×41 pitch  → ICON_WONDER_*.tga

civ2_sprite_extractor.py --sheet improvements
  reads: momjr_csv/improvements.csv  (cell_index col, rows 0–39)
  writes: ICON_IMPROVE_*.tga  →  scen0000/default/graphics/pictures/

civ2_sprite_extractor.py --sheet wonder_atlas
  reads: momjr_csv/wonders.csv  (cell_index col, rows 40–67)
  writes: ICON_WONDER_*.tga  →  scen0000/default/graphics/pictures/
```

After extraction, run `ctp2_generator.py` then `mom_audit.py` (expect 39 PASS,
0 FAIL) before committing.
