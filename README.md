# ctp2-momjr — Master of Magic total conversion for Call to Power 2

CTP2 port of the Civ2 **MoM Junior** scenario (Master of Magic), built on the
Apolyton Edition. This repo carries TWO artifacts side by side, on purpose:

## 1. `mom.zip` — the frozen, hand-patched working version

Snapshot of the scenario as manually/AI-patched to a confirmed-working state
**before** the control-plane refactor. This is the regression reference: if the
control-plane pipeline ever produces something that misbehaves in-game, diff
against the contents of this zip to find what drifted.

## 2. The repo tree — the control-plane version

The same scenario, restructured so everything regenerates from data:

- `scen0000/` — the generated CTP2 scenario (gamedata, graphics, aidata)
- `tools/` — the universal mod encoder pipeline:
  - `encode_civ2_mod.py` — Civ2 `RULES.TXT` → per-dimension CSVs (+ xlsx workbook)
  - `tools/momjr_csv/` — **the control plane**: dimension CSVs + per-mod policy
    (`mod_policy.json`, masks, GL rewrites, sprite pick rules, unit block overrides,
    advance code map, cost bands, atlas geometry)
  - `ctp2_generator.py` — control plane → scenario files (engine only; all MoM
    decisions live in the policy files)
  - `export_mod_workbook.py` / `sync_excel_to_csv.py` — xlsx ⇄ csv round-trip
  - `mom_audit.py` — post-generation validation
- `specs/` — design specs, including the engine/policy inventory that drove the split
- `lessons_learned.md` — the project wiki (newest entries first)

### Regeneration

```
set CTP2_GENERATOR_SCENARIO_DIR=<scenario dir>   # optional; defaults to Scenarios\mom\scen0000
python tools\ctp2_generator.py
python tools\mom_audit.py
```

The generator is deterministic: two runs from the same control plane produce
byte-identical output (this is the pipeline's regression gate).

### Converting a different Civ2 mod

```
python tools\encode_civ2_mod.py --mod-dir <civ2 mod dir> --out <new csv dir>
# hand-curate the csv dir (wonders block_text, players ctp2 columns, policy, atlas)
set CTP2_GENERATOR_CSV_DIR=<new csv dir>
python tools\ctp2_generator.py
```

Source game content © Activision / Firaxis / the original MoMJR scenario
authors; this repo contains only mod data and tooling.
