# ctp2-momjr — Master of Magic total conversion for Call to Power 2

CTP2 port of the Civ2 **MoM Junior** scenario (Master of Magic), built on the
Apolyton Edition.

![MoM running in CTP2: the MAGIC STATUS panel with a live mana pool and a
Summon Creature arm, beside a Life Tribe city](docs/img/mom_magic_status_ingame.png)

## What this mod adds

- **Interactive SLIC, per civ.** The magic system is a real modal the player
  acts on, not a notification stream: `MAGIC STATUS` shows the mana pool and
  income, and its `Summon Creature (75)` arm places an order that survives the
  turn boundary and resolves next `BeginTurn`. The creature is chosen from the
  **caster's own sphere** — a Life tribe summons a Guardian Spirit and *cannot*
  raise Death's zombies. Each of the five spheres (Life, Nature, Sorcery, Death,
  Chaos) has its own predicates, buildings, income, blessings, spellbook and
  result popups.
- **Mana is a real resource.** 100-point pool, income from cities and owned mana
  nodes, and a priced spellbook — summons and spells compete for the same pool
  instead of being free.
- **Centred unit art.** MoM's units are rebuilt into CTP2 sprites whose draw
  anchor matches the vanilla convention, so they stand on their tile instead of
  drifting off it. Extent and anchor are derived together from the measured
  envelope of all 95 shipped `GU0*.SPR` — see `lessons_learned.md`, which is the
  project wiki.
- **A control plane you can edit in Excel.** `mom_dimension_inventory.xlsx` is
  the artifact the mod is based on. **Each tab is one dimension** — units,
  advances, improvements, terrain, players, wonders, tileimp, sprite pick rules,
  cost bands, atlas geometry, and **slic** — so changing the mod means editing a
  spreadsheet, not hand-patching game text files.

## The control plane

`mom_dimension_inventory.xlsx` — 35 tabs, one per dimension. A **cell is a file,
and/or a set of constants, classes and/or functions** — the actual content, not
a description of it.

### Why SLIC flows the other way

Every other dimension is **forward-generated**: a Civ2 mod is encoded into the
workbook, and the generator turns that into scenario files.

SLIC is the exception, and has to be. Civ2 has no equivalent to it — there is
nothing upstream to encode *from*. SLIC is authored directly against CTP2, which
is precisely why it is **backcast** into the workbook by
`tools/backcast_slic.py`:

```
Civ2 RULES.TXT ---encode--> [ mom_dimension_inventory.xlsx ] ---generate--> scenario
                                          ^
scenario *.slc  ---backcast---------------+
```

The workbook stays the single place to see what the mod *is*; the `.slc` files
stay the source of truth for what it *does*. The backcast never writes SLIC — a
spreadsheet that could regenerate SLIC would be strictly worse than text files
that are diffable, commentable and compilable.

### The `slic` tab

One row per module, and the content columns carry real source:

| column | holds |
|---|---|
| `constants` | module-scope declarations (the per-player arrays) |
| `functions` | every `int_f` / `void_f`, whole, with its leading comment |
| `handlers` | every `HandleEvent` block, whole |
| `triggers` | every UI trigger block, whole |
| `segments` | every `alertbox` / `messagebox`, whole |
| `source` | the entire file, verbatim |

plus `phase` and `include_order` (read from `scenario.slc`'s `#include` list,
not hardcoded). `slic_index` is the flat companion — one row per declaration
with its signature — for scanning and filtering rather than reading.

Structure is re-derived on every run. The `purpose` and `status` prose is merged
forward by name and kept in `tools/momjr_csv/slic_purpose.json`, so a
declaration added in code shows up with an empty `purpose` — a visible TODO —
and human- or LLM-written intent text is never clobbered. That is the second
process: propose a feature in the sheet, implement it in SLIC, and let the
backcast reconcile the two.

```
python tools/export_mod_workbook.py   # rebuilds the forward-generated tabs
python tools/backcast_slic.py         # then adds slic + slic_index
python tools/backcast_slic.py --check # exits 1 if the tab drifted from the code
```

Run the backcast **after** the export — the export rebuilds the workbook from
the forward dimensions and does not know about SLIC.

## The two artifacts

The mod and the code, kept separate on purpose:

## 1. `mom.zip` — the mod

What a player installs. Unzip into `Scenarios\` and the scenario is there.

It carries **only** what the engine loads — `packicon.tga`, `packlist.txt` and
`scen0000/`, the same shape as the scenarios that ship with the game — under a
top-level `mom/` prefix. No tooling, no control plane, no docs: **the repo holds
the code, the zip holds the mod.** Rebuilt from the tree, never hand-maintained:

```
python tools\ctp2_generator.py    # control plane -> scenario
python tools\mom_audit.py         # validate
python tools\build_mod_zip.py     # package
```

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
