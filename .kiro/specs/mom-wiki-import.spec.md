---
description: 'Phase 2: import the MoM wiki corpus (spells, units, heroes, buildings, terrain, minerals) into the CTP2 control plane'
import:
  - mom-feature-roadmap
---

***definitions***

- :Wiki-Corpus: is the offline MoM wiki mirror at `F:\Documents\wiki\games\mom\site\` — 878 pages in `index.json` (JSON list of `{t: title, s: slug, x: flattened text}` records), 1834 images, and per-page HTML under `p/`.
- :Wiki-Bucket: is a thematic partition of wiki pages: spells, heroes, buildings, race-units, terrain, minerals, encounter-sites, retorts, mechanics-prose.
- :Extractor: is a per-bucket Python module under `tools/wiki_import/` that reads `index.json`, strips wiki furniture, and emits a CSV under `tools/momjr_csv/`.
- :Sidecar-Override: is a corrections file (same convention as `unit_block_overrides` / `advance_overrides`) that persists manual fixes across re-imports. A re-import never silently discards overrides.
- :Effect-Kind: is the classification of a spell's implementability in CTP2: `summon`, `unit_enchant`, `city_enchant`, `global_enchant`, `instant_damage`, `dispel`, or `flavour` (masked but imported).
- :Paged-Spellbook: is the UI replacement for the two hand-wired buttons — driven off `spells.csv`, paging 5 spells at a time through alertbox arms with navigation.

***implementation reqs***

- Wiki parse target: `index.json` field `x` (plain-text article). Fall back to `p/<slug>__<hash>.html` only when `x` loses table structure.
- Extractors MUST be idempotent and re-runnable: same snapshot → byte-identical CSV, or the diff is a bug.
- Corrections go in sidecar override files, never in the imported CSVs.
- Wiki furniture to strip deterministically: category labels, "Research Required" banners, contents lists, navigation chrome. Assert stripper output is stable.
- Licensing: wiki is third-party. Record provenance in `docs/`. Keep imported prose paraphrased or clearly attributed — do not bulk-copy article text into shipped strings.
- New gate: `gate_wiki_import.py` — every imported CSV re-derives cleanly from snapshot; overrides all still apply to live rows; no imported ident violates charset/reserved-token gates.
- New gate: `gate_spells.py` — every `UNIT_*`/`IMPROVE_*` referenced by a spell exists in generated DB; costs are within pool reach; sphere column agrees with gating matrix.
- Spell effects bucketed by :Effect-Kind:. Non-implementable kinds ship as data with mask — visible in the control plane but not generated into gamedata.
- The spine `mom spells.txt` (at `C:\Users\user\Documents\wiki\games\ctp2\mom spells.txt`) provides authoritative spell numbers: rarity, type, target, overland cost, combat cost, upkeep, research cost. Wiki adds prose + effect detail.
- Five alertbox arms is the hard ceiling — paging is mandatory for >5 spells per sphere.

***test reqs***

- `gate_wiki_import.py` green: every CSV re-derives from snapshot, overrides apply, no charset violation.
- `gate_spells.py` green: all spell references resolve, costs within pool reach, sphere gating correct.
- `validate_all_surfaces.py` exit 0 after generation with imported content.
- `validate_scenario.py --scenario scen0000` PASS with same or higher file count.
- Re-run extractor twice: output must be byte-identical both times.

***functional specs***

- The :Wiki-Corpus: `index.json` MUST be parsed by per-bucket :Extractor:s that emit CSVs.
  - Given the MoM wiki mirror at `F:\Documents\wiki\games\mom\site\index.json`, When the spells extractor runs, Then `spells.csv` is produced with columns for id, name, sphere, rarity, effect_kind, cost, upkeep, description.
- Each :Extractor: MUST be idempotent.
  - Given an unchanged wiki snapshot, When the extractor runs twice, Then the output CSVs are byte-identical.
- :Sidecar-Override: files MUST persist across re-imports.
  - Given a correction in `spells_overrides.csv`, When the extractor re-runs, Then the override value takes precedence over the wiki-derived value.
- Wiki numbers MUST NOT bypass balance gates.
  - Given a wiki spell costing 500 mana, When imported, Then `mod_policy.json` and the balance gates decide the shipped cost (not the wiki number directly).
- The :Paged-Spellbook: MUST replace the two hand-wired buttons.
  - Given spells.csv with 40 Life spells, When the player opens the Life spellbook, Then pages of 5 spells display with forward/back navigation.
  - Given page 2 selected, When the player picks a spell and has sufficient mana, Then the cast triggers and mana is deducted.
- Non-implementable :Effect-Kind:s MUST be imported but masked.
  - Given a spell with effect_kind=`flavour`, When generated, Then it exists in spells.csv but is NOT emitted into scenario gamedata.
- Import priority order MUST be respected: spells → units/heroes → buildings/terrain/minerals → prose → images.
  - Given all extractors available, When the full import runs, Then spells land first (unblocks spellbook), followed by roster, then economy, then flavour.

## Bucket Details

| Bucket | Est. Count | Target CSV | Feeds |
|---|---|---|---|
| Spells/enchantments/curses/summons | ~50+ | `spells.csv` | Spellbook UI, gate_spells |
| Heroes | ~45 | `heroes.csv` | Future named-unit system |
| Buildings | ~35 | Fold into `improvements.csv` | Phase 1 terrain_prereq |
| Race units | many | `units.csv` augmentation | Per-race roster fidelity |
| Terrain specials | ~21 | Terrain tables | Phase 1 gating |
| Minerals/goods | ~12 | Goods tables | `HasGood()` consumers |
| Encounter sites | ~9 | Ruins/goody-hut content | Exploration flavour |
| Retorts | ~2+ | Captured as data (no CTP2 home) | Future wizard traits |
| Mechanics prose | large | `docs/` reference | Descriptions, vocabulary |
