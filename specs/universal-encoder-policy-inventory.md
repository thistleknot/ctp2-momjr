# Universal Mod Encoder — Policy-vs-Engine Inventory of ctp2_generator.py

Generated 2026-07-15 (line refs against the 4735-line generator at commit bb4b6e8).
Drives the engine/policy split: POLICY items move to per-mod control-plane files;
ENGINE items stay in code. MIXED = mechanism stays, values move.

Target control-plane files (all live in the mod's csv dir, e.g. `momjr_csv/`):
- `mod_policy.json` — scalar/structured knobs (start advances, scaling, remaps, fallbacks)
- `tileimp_mask.csv` (`id,reason,note`) — absorbs #1, #2, #8
- `gl_text_rewrites.csv` (`scope,section,find,replace`) — absorbs #5, #46, #48, #49, #50
- `order_mask.csv`, `concept_mask.csv` — #6, #7
- `advance_code_map.csv` (`code,advance,lane`) — #9, #10
- `stub_advances.csv` — #17
- `sprite_pick_rules.csv` (`match,sprite/size`) — #14, #15
- `unit_role_overrides.csv` — #29, #38
- `unit_overrides.csv` / template blocks — #39, #40, #42
- `governicon_fallback.csv` — #19
- `entity_renames.csv` — #46 (Railroad → Enchanted Road)
- `order_strings.csv` — #52
- `advance_cost_bands.csv` — #24

## Policy / mechanics table

| # | Name/description | Line range | Kind | Class | Proposed home | Notes/risk |
|---|---|---|---|---|---|---|
| 1 | `HIDDEN_SURROGATE_TILEIMPS` — 13 stock tile-imps hidden as compat surrogates | 34-48 | module-const | POLICY | `tileimp_mask.csv` (`reason=surrogate`) | Drives GL scrub + SURROGATES register |
| 2 | `HIDDEN_OUT_OF_GENRE_TILEIMPS` — malls/hydroponics/sci-fi | 50-58 | module-const | POLICY | `tileimp_mask.csv` (`reason=out_of_genre`) | |
| 3 | `START_GOVERNMENT_ADVANCE = "ADVANCE_MONARCHY"` | 60 | module-const | POLICY | `mod_policy.json:start_government_advance` | |
| 4 | `START_GUARANTEED_ADVANCES` (Monarchy + Warrior Code) | 61-66 | module-const | POLICY | `mod_policy.json:start_guaranteed_advances[]` | Empty-build-list risk if wrong |
| 5 | `HIDDEN_TILEIMP_GREAT_LIBRARY_TEXT` — 13 GL prose replace pairs | 68-84 | const | POLICY | `gl_text_rewrites.csv` | Tied to hidden tileimps |
| 6 | `HIDDEN_OUT_OF_GENRE_ORDERS` | 86-103 | module-const | POLICY | `order_mask.csv` | |
| 7 | `HIDDEN_OUT_OF_GENRE_CONCEPTS` | 105-109 | module-const | POLICY | `concept_mask.csv` | |
| 8 | `SURROGATE_TILEIMP_NOTES` | 111-125 | module-const | POLICY | `tileimp_mask.csv:note` | Feeds SURROGATES.txt |
| 9 | `advance_id()` prereq code→ADVANCE map (civ2 + MoM codes) | 140-188 | const-in-fn | MIXED | `advance_code_map.csv` | civ2 half generic, fantasy half policy; ValueError on unmapped |
| 10 | `MOM_UNIT_ADVANCE` (~90 rows) | 191-276 | module-const | POLICY | `advance_code_map.csv` (unit lane) | Eng→SEA_MASTERY, Gun→CHAOS_MAGIC thematic |
| 11 | `_NO_ADVANCE` = {nil,no,''} | 279 | module-const | ENGINE | keep | |
| 12 | `_ENGINE_REQUIRED_UNITS` = {UNIT_CITY} | 282-284 | module-const | ENGINE | keep | |
| 13 | `_HARDCODED_DB_UNITS` = {UNIT_CLERIC} | 291-293 | module-const | ENGINE | keep | unitutil.cpp lookup |
| 14 | `_pick_sprite()` MoM-name heuristics | 326-358 | branches | POLICY | `sprite_pick_rules.csv` | |
| 15 | `_pick_size()` giant/wyrm/dragon→Large | 361-367 | branches | POLICY | `sprite_pick_rules.csv` | |
| 16 | `_AGE_MAP` epoch→AGE_* | 371 | module-const | MIXED | `mod_policy.json:epoch_age_map` | |
| 17 | `_BASE_UNIT_STUB_ADVANCES` (~45 stub advances) | 375-420 | module-const | POLICY | `stub_advances.csv` | |
| 18 | `GL_VISIBLE_RAW_BLOCK_RELS` | 576-580 | module-const | ENGINE | keep | Wonder.txt flag limitation |
| 19 | `GOVERNICON_FALLBACK_IDS` | 785-791 | module-const | POLICY | `governicon_fallback.csv` | |
| 20 | `_ensure_diffdb_start_government()` | 463-500 | function | POLICY | driven by #4 | |
| 21 | `_retire_x_sentinels()` X-prefix placeholders | 503-538 | fn+literal | POLICY | `mod_policy.json:retire_sentinel_prefix` | Apolyton-pack specific |
| 22 | `_merge_mom_improvements_into_buildings()` remap dict + defaults | 661-766 | literals | MIXED | `mod_policy.json` remap/defaults | |
| 23 | `_write_surrogate_register()` | 872-894 | fn+literal | POLICY | keep (generated artifact) | |
| 24 | `_load_ae_advance_cost_bands()` AGE_ONE(120,600)… | 1417-1440 | const | POLICY | `advance_cost_bands.csv` | |
| 25 | `_scaled_mom_advance_cost()` clamp 2..62, factor 0.15, round-5 | 1789-1798 | literal | POLICY | `mod_policy.json:advance_cost_scaling` | |
| 26 | `branch_fallback_weights` {0:2,1:10,2:7,3:44,4:56} | 1808-1814 | literal | POLICY | `mod_policy.json:branch_fallback_weights` | |
| 27 | unit/wonder/improve cost-band retune + round_to=10, PP=cost//2 | 1443-1786 | fns+literals | MIXED | `mod_policy.json` cost-retune block | |
| 28 | `_write_empty_wonder_build_lists()` | 1278-1319 | fn+literal | MIXED | keep | |
| 29 | `_write_mom_unit_build_lists()` ranged/freight/settler/sea/air unit ids | 2049-2060 | literal | POLICY | `unit_role_overrides.csv` | |
| 30 | `_sanitize_omitted_building_refs()` fallback=IMPROVE_GRANARY | 2139-2210 | fn+literal | MIXED | `mod_policy.json:building_ref_fallback` | |
| 31 | wonders.csv consumption, ADVANCE_WARRIOR_CODE default | 2213-2286 | fn | MIXED | `wonders.csv` | |
| 32 | wonder icon atlas extraction (160x120) | 2350-2421 | fn+literal | MIXED | keep; atlas key policy | |
| 33 | `Scenario_files_to_nuke` | 2765-2776 | literal | MIXED | keep | |
| 34 | `csv_imports` manifest (sheet→txt+apply_kind) | 2786-2805 | literal | MIXED | `mod_policy.json` import manifest | terrain.csv excluded = policy |
| 35 | improvements emission skips (x/Nothing/SS/HIDE), cost*100 | 2923-2959 | branches | POLICY | csv conventions + policy | |
| 36 | fantasy research-tree isolation | 3062-3115 | branches | MIXED | driven by advances.csv | |
| 37 | unit stat scaling (atk×5, shield×100, hp=10, sounds) | 3144-3183 | literal | POLICY | `mod_policy.json:unit_stat_scaling` | |
| 38 | Peasants→SETTLER category special case | 3164-3168 | branch | POLICY | `unit_role_overrides.csv` | |
| 39 | `UNIT_SETTLER` retired verbatim block | 3207-3258 | literal | MIXED | `unit_overrides.csv`/template | |
| 40 | `UNIT_PEASANTS` verbatim block | 3279-3341 | literal | POLICY | `unit_overrides.csv` | do-not-revert |
| 41 | `UNIT_CITY` verbatim block + uniticon | 3354-3430 | literal | ENGINE | keep | |
| 42 | UNIT_SETTLER uniticon TGA force | 3262-3270 | branch | MIXED | `unit_overrides.csv` | |
| 43 | uniticon reconcile bad_icon_tokens→UPLG001 | 3609-3654 | literal | MIXED | `mod_policy.json` icon fallbacks | |
| 44 | improve/unit icon MoMJR art swap | 3656-3719 | branch | MIXED | keep | |
| 45 | goods dedup by numeric id | 3744-3757 | branch | ENGINE | keep | |
| 46 | RAILROAD→Enchanted Road remap (multi-site) | 3877-3881, 4092-4107, 4150-4210, 4358-4361 | literals | POLICY | `entity_renames.csv` + `gl_text_rewrites.csv` | signature policy example |
| 47 | out-of-genre/surrogate tileimp GLHidden | 3882-3901 | branch | POLICY | driven by #1/#2 | |
| 48 | Swamp GL Roads/Maglev prose rewrite | 4165-4173, 4211-4219 | literal | POLICY | `gl_text_rewrites.csv` | |
| 49 | ADVANCE_OIL_REFINING_PREREQ rewrite | 4160-4164 | literal | POLICY | `gl_text_rewrites.csv` | |
| 50 | HT_SUPERCONDUCTOR maglev prose strips | 4181-4198 | literal | POLICY | `gl_text_rewrites.csv` | |
| 51 | TILEIMP_MAGLEV_* section pops | 4174-4180, 4220-4226 | branch | POLICY | driven by tileimp mask | |
| 52 | `_manual_order_strings` | 2281-2285 | literal | MIXED | `order_strings.csv` | |
| 53 | `masked_building_icons` = [ICON_IMPROVE_XWOMENS_SUFFRAGE] | 4140 | literal | POLICY | improvements mask lane | |
| 54 | order visibility reconcile | 4271-4355 | branch | MIXED | driven by #6 | |
| 55 | DATABASE_IMPROVEMENTS→DATABASE_BUILDINGS GL link fix | 4118-4136 | branch | ENGINE | keep | |
| 56 | `_generate_civilisation_tribes()` | 4578-4661 | fn | POLICY | players.csv + tribe_cities.csv (already csv) | |
| 57 | `_generate_civstr_tribes()` singularization | 4664-4731 | fn+literal | POLICY | players.csv lane | |
| 58 | GL stub advances (cost 999999, ICON_ADVANCE_DEFAULT) | 2905-2921 | branch | MIXED | keep | |

## main() stage order (line refs)

1. Nuke + empty-init scenario files, clear registry cache — 2765-2783
2. Import csv sheets (buildings, improveicon, wonders, wondericon, wondermovie, goods, goodsid, goodsicon, terrainicon, governments, governicon, orders, concepts) + building_uniticon overlay — 2785-2821
3. Seed stub advances; emit advances from advances.csv; retune costs; advance-age map — 2831-2864
4. Backfill advance names, restore base GL prose, hidden stub advances — 2866-2921
5. Emit improvements; dedupe vs buildings; building uniticon — 2923-3015
6. Wonders migration + icon art + cost retune — 3017-3060
7. Fantasy research-tree isolation — 3062-3116
8. Emit units (stat scaling, sprite/size pick); unit cost retune — 3117-3191
9. UNIT_SETTLER/PEASANTS/CITY force blocks; unit gl_str — 3193-3466
10. Auto-hide non-MoM units; unit_mask; build lists — 3468-3529
11. Tile improvements; icon reconciles — 3531-3719
12. GL restores; goods dedup; wonder surface prune; building-ref sanitize; Goals — 3721-3806
13. Strict GL prune; Enchanted Road remap; tileimp hides — 3808-3901
14. Governments reconcile; concepts; RAILROAD swaps; GL prose rewrites; orders — 3903-4355
15. Merge improvements→buildings.txt; save_all; final scrubs; DiffDB start-gov; X-sentinels; tribes; workbook export; newsprite merge — 4357-4491

## Path/env risks (fix in task 2)

- Hardcoded default SCENARIO/CTP2_DATA paths (lines 22, 28) — env-overridable, OK as defaults.
- **BUG**: absolute base tileimp.txt path in main() (line ~3872) bypasses CTP2_DATA env.
- **BUG**: absolute base_newsprite/scenario_newsprite/scenario_units paths (4430-4432) bypass env.
- `_available_custom_sprites()` assumes scen0000 is sibling of tools dir (line 318) — independent of SCENARIO env.
- `extractor.load_sheet_cells("wonder_atlas")` assumes atlas key registered.

## Sheets consumed by the generator (per-mod contract)

buildings, improveicon, wonders, wondericon, wondermovie, goods, goodsid, goodsicon,
terrainicon, governments, governicon, orders, concepts, building_uniticon, advances,
improvements, units, unit_mask, tileimp, players, tribe_cities.
(terrain.csv deliberately NOT consumed — KEEP dimension. canonical_schema/improvements.csv optional.)
