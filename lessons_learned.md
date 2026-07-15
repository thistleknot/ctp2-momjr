
## [PIPELINE] Universal mod encoder: civ2 → xlsx/csv control plane → ctp2, proven on HoMM2 (2026-07-15)

Commits d213155 + a60a147. The MoM pipeline is now a reusable encoder: any civ2 mod →
per-dimension csv/xlsx control plane (image cell indices transcribed) → ctp2 scenario.

- **Engine/policy split**: 58-item inventory (`specs/universal-encoder-policy-inventory.md`)
  classifies everything in ctp2_generator.py. Round 1 moved all module-level policy into
  9 per-mod files in the csv dir (mod_policy.json + tileimp/order/concept masks,
  gl_text_rewrites, advance_code_map, stub_advances, governicon_fallback,
  advance_cost_bands). A mod = one csv dir. **Round 2 (commit 1c33df1) finished the
  split**: all embedded main() literals extracted — Enchanted Road remap family
  (db_text_swaps/tileimp_block_swaps/gl_section_overrides.csv with set/replace/pop
  rows), sprite/size pick heuristics (sprite_pick_rules.csv, ordered rule evaluator),
  unit stat scaling + roles + settler category + GL branding (mod_policy.json),
  UNIT_SETTLER/PEASANTS verbatim blocks (unit_block_overrides.csv). Both rounds
  byte-stability-gated; only truly ENGINE items remain in code (see inventory).
- **Entry points**: `encode_civ2_mod.py --mod-dir <civ2 mod> --out <csv dir>` (stage 1),
  then `CTP2_GENERATOR_CSV_DIR=<csv dir> CTP2_GENERATOR_SCENARIO_DIR=<scen dir>
  CIV2_MOD_BMP_DIR=<mod dir> ctp2_generator.py` (stage 3). xlsx round-trip:
  `export_mod_workbook.py` ⇄ `sync_excel_to_csv.py` (all sheets, header-drift refusal,
  --check mode, newline/encoding preserved).
- **THE gate: regen byte-stability.** Baseline the generator into a scratch scenario
  (env vars), hash all files, re-run after every change, diff. Caught and fixed a real
  nondeterminism: set-iteration in _ensure_runtime_unit_gl_surfaces made
  gl_str/Great_Library churn between identical runs (sort before writing).
- **Dry-run discipline finds the universality gaps**: running the generator on an
  encoded FOREIGN mod (HoMM2Mod1.1) surfaced every hidden MoM assumption as a clean
  failure: unmapped prereq codes (fix: derive advance_code_map from the mod's own
  @CIVILIZE trailing-comment codes), hard-required wonders.csv/tileimp.csv (fix:
  graceful skips), workbook writing to the MoM path (fix: follow the active csv dir),
  stray prose lines inside @UNITS (fix: arity-based row validation).
- **Encoder fidelity check**: encode MOMJR and diff against the CURATED momjr_csv —
  advances 87/87 exact; every unit/improvement mismatch mapped to a documented hand
  decision (hero Mys gating, X-sentinel icon renames, wonders promoted to buildings).
  The mismatch list IS the curation ledger for a new mod.
- **Known limits (v1)**: wonders.csv block_text and players ctp2_* columns are hand-
  authored; terrain/goods/orders/concepts are KEEP dimensions; atlas geometry rows per
  mod (scaffolded from MOMJR's, extractor prefers the csv-dir copy).

## [FIXED — 5th fugly cause] Dropdown chrome AV: zfs-RIM surfaces fail every blit; loose-TGA override is the fix (2026-07-15)

The City-tab "muted tan strips with a beaded rope" fugly (city-name pulldown + MAYOR
pulldown) — the "next up" known issue recorded in 656ecab — is FIXED, user-confirmed.

- **Symptom**: both City-tab dropdowns showed flat tan with a knotted-cord line instead
  of the beige/gold dropdown chrome. NOT random rainbow static: the pixels were a stale
  slice of the tan parchment setup screen (upsg005/006 style, beaded border = the "rope").
- **Root cause**: dropdown chrome = 13 `uppd02*` images that exist ONLY inside
  pic555/565.zfs as RIM records (no loose TGAs anywhere, incl. Apolyton reference).
  `TargaImageFormat::LoadRIM` wraps the RIM bytes directly as the image surface
  (`LoadFileMapped`); **blitting those RIM-backed surfaces access-violates on every
  draw** (`DrawImages: blit FAILED (err=4) for image 'uppd02aX.tga' (surface 14x29)
  bltType=0 bltFlag=1`). The per-image SEH guard (f9a529266) contains the AV → the blit
  is skipped → chrome never painted → stale surface memory shows. Exactly the
  2026-07-10 rule firing: "skipping a paint = a fugly by another name."
- **Why it looked like data and wasn't**: all 3 documented data causes verified clean
  by bytes (DB double-load, TGA desc, CRLF), zfs archives structurally intact, RIM art
  decoded clean, zero load errors. 16af7c743's guess (missing upfg50-53) was a red
  herring — those were restored in f3ecf9e and are fine (they're the UNIT tab).
- **FIX (data-only, no rebuild)**: extract the 13 `uppd02*.rim` from **pic555.zfs**
  (555 = ARGB1555 = 16-bit TGA payload, no conversion loss), row-flip (RIM is
  top-down), write loose TGAs to `ctp2_data/default/graphics/pictures/` matching the
  proven upfg01 conventions: type 2, 16bpp, **desc=0x01, bottom-up rows, 8-zero-byte +
  `TRUEVISION-XFILE.\0` footer**. Loose TGA beats zfs RIM (`_access` check in
  `TargaImageFormat::Load`), and the normal TGA load path allocates a regular surface
  that blits fine. Chromakey magenta (31,0,31) survives 555→565 exactly.
- **Evidence recovery trick that cracked it**: the July-14 session's engine logs were
  rotated away, but the *conversation transcript jsonl* still contained the pasted log
  excerpt with the exact failing line. When a commit message cites "session logs",
  grep the transcript before re-instrumenting anything.
- **Rules**:
  1. **Any texture that lives only as a zfs RIM is one loose-TGA extraction away from
     a fix** — "caps come from zfs; not a data fix" (2026-07-11) was wrong: desc bytes
     can't be fixed in-archive, but a loose OVERRIDE bypasses the archive entirely.
  2. The uiwalk/user screenshot distinction that matters: coherent-but-wrong texture
     (stale screen slice) = paint never happened; rainbow noise = unpainted heap.
     Both are "surface never painted", different underlying memory.
  3. ZFS3 format (for future extractions): header `ZFS3 u32(ver) u32(fnlen=16)
     u32(entries/table=100) u32(total)`, tables at 0x1c chained by leading u32 next-ptr,
     entry = name[16] + u32 offset + u32 idx + u32 size + u32 time + u32 pad (36 B).
     RIM record: `RIMF u32(ver=1) u16 w,h,pitch,fmt(0=555,1=565)` + raw rows.

## [STATE + SCAN LESSON] Advance icons: canonical 11-cell design is CURRENT; a mid-session 71-repoint dedup was superseded (2026-07-15)

Ground truth measured 2026-07-15 (pixel md5 over decoded FirstFrame art of all 85
visible advances): **11 distinct images, 10 shared groups** — i.e. the canonical
advances.csv 11-category-cell contract from 656ecab, which the user accepted as
"working". Each magic school line (Chaos/Death/Life/Nature/Sorcery, 6 advances each)
shares its school image BY DESIGN; ditto the economy/military/civic/build groups.

- **History note**: mid-window on 07-14, a 71-repoint uniticon dedup (unique art per
  visible advance from the free pool) was built and verified — then superseded by the
  canonical-contract restore in 656ecab (generator rewires uniticon; contract = shared
  category art). If per-advance unique art is ever wanted again, do it durably: write
  art INTO the `ICON_ADVANCE_<X>.tga` files (generator forces uniticon Icon refs to
  those filenames — uniticon hand-repoints are regen-reverted, lessons 2026-07-14).
- **Durable scan lesson (keep)**: duplicate detection must key by **content hash
  ONLY** — keying by (md5, basename) hides same-content files under different names,
  which is exactly how generator-written school lines share bytes across
  ICON_ADVANCE_*.tga files. Decoded-PIXEL md5 beats file md5 (desc-byte/footer
  variance hides pixel identity).
- **Free-pool rule (keep, for any future repoints)**: candidate art = md5-group
  referenced by NO uniticon entry of any type — prevents advance-vs-building repeats
  inside the Great Library.

## [REGRESSION+FIX] generator regen reverted committed hand-fixes: sprite renumbering broke unit art; hero gating lost (2026-07-14)

The first generator regen in a while surfaced a whole CLASS of defect: **hand-fixes
committed directly to generated outputs get silently reverted on regen.** Two hits:

1. **Peasant (all custom units ≥95) showed wrong art.** The newsprite merge appended
   custom sprites in Units.txt encounter order with fresh sequential ids — but
   **sprite numbers are pinned to disk**: each id is baked into the GU<id>.SPR
   filename built by build_sprites.py (SPRITE_PEASANTS 104 ↔ GU104.SPR). The regen
   renumbered (Peasants 104→142) and every custom unit rendered another unit's
   sprite. FIX: merge now preserves the scenario file's existing custom name→id
   assignments verbatim and only appends genuinely new names (ctp2_generator.py
   newsprite block). Verified: regen name→id pairs == committed, zero drift.
2. **Hero flood at start returned.** Commit 73e7a6f gated the 9 champions
   (Ariel/Jafar/Rjak/Tauron/Serena/Freya/Alorra/Warrax/Malleus) behind
   ADVANCE_MYSTICISM by editing Units.txt directly; units.csv still said prereq
   'no' → regen flipped them back to WARRIOR_CODE (start-guaranteed = buildable
   turn 0). FIX: backported to the control plane — units.csv prereq 'Mys'
   (MOM_UNIT_ADVANCE already maps Mys→ADVANCE_MYSTICISM). Regen now reproduces
   the gating. (Spearmen gaining EnableAdvance WARRIOR_CODE is behaviorally
   neutral: WARRIOR_CODE is in START_GUARANTEED_ADVANCES.)

**Rule reinforced:** any fix applied to a generated .txt MUST be backported to the
CSV/control plane in the same session, or the next regen erases it. Audit idea:
before committing generator output, regen twice and require byte-stability.

## [PIPELINE-FIXES] advances extraction wired end-to-end; 3 defects fixed en route (2026-07-14)

First full `extractor → generator → audit` run for advance art (65 PASS / 0 FAIL):

1. **`civ2_sprite_extractor.py` CSV_SOURCES bug**: advances.csv was registered with
   `id_col="ident"` but that csv has no `ident` column (its identifier is `icon`)
   → every row silently skipped, "Total written: 0". A silent-skip on a missing id
   column is worth an explicit warning if it recurs elsewhere.
2. **Self-prereqs inflated advance costs**: `_retune_mom_advance_costs` counted
   `Prerequisites ADVANCE_X` lines including SELF-prereqs (the engine-sanctioned
   disable pattern) → disabled advances got prereq_factor 1.3 and blew the
   AGE_ONE ≤640 audit band (635→720 on first regen after the self-prereq commit).
   Fixed: prereq_count excludes self-references. Note: committed Advance.txt costs
   can be STALE relative to the generator (regen after any prereq/formula change).
3. **Audit lacked a retired-blocks whitelist**: the generator deliberately retires
   `IMPROVE_HIDE_SUPERMARKET` (removes the DB block, keeps uniticon/GL surfaces)
   — three audit checks (csv-coverage, dangling-icon, art-resolution) flagged it.
   Added `RETIRED_BUILDING_IDS` whitelist in mom_audit.py.

Post-state verified: 85 visible advances → exactly 11 pixel-distinct images,
each group homogeneous in cell_index (Chaos ×6 → cell 62 Forge of Chaos).

## [TOOLING] uiwalk — scripted in-game UI verification harness (2026-07-14)

`Scenarios/mom/tools/uiwalk/uiwalk.py`: launches the game deterministically, drives
it with scripted keys/clicks, screenshots checkpoints, template-matches regions
against goldens. Enables Claude-run verification instead of manual in-game checks.

- **Deterministic boot**: engine arg `-l"<save>"` loads a save AND auto-sets
  `nointromovie noshell` (civ3_main.cpp ParseCommandLine) — boots straight into the
  game. One-time setup: save the static turn-0 start as `uiwalk_start`.
  Other useful switches: `runinbackground` (render unfocused; profile has
  RunInBackground=No), `noshell`, `-s<scenario>`. Debug console commands exist but
  are `#ifdef _PLAYTEST` only — do not rely on them.
- **Keyboard nav beats pixel-hunting**: `keymap.txt` — `Ctrl+5` = Great Library,
  `A` = end turn, `Ctrl+x` = new game. The GL Search box gives deterministic
  navigation to any advance by typed name.
- **Goldens derive from the control plane** (`make_goldens.py`): advances.csv
  cell_index → Improvements.bmp cell → 160×120 canvas via the extractor's own
  helpers. Contract → expected pixels → in-game pixels, no blessed screenshots.
- **Input isolation (user requirement — never touch their mouse/keyboard)**:
  default backend PostMessages WM_KEY*/WM_CHAR/WM_*BUTTON* straight to the game
  HWND and captures via PrintWindow(PW_RENDERFULLCONTENT) — the game runs
  unfocused in the background, physical input untouched. SDL2 tracks modifiers
  from the posted VK_CONTROL events so Ctrl+5 chords work. `--global-input` is
  the explicit real-cursor fallback (pyautogui, FAILSAFE on) if PostMessage is
  ever ignored. `--record` only OBSERVES the user's clicks (GetAsyncKeyState
  polling), never generates input.
- Modes: `--run steps/gl_advances.json` (assert), `--baseline`, `--dry`,
  `--record` (logs user clicks as client coords until F12 — for path calibration),
  `--attach` (drive an already-running window), `--keep`.
- Teardown kills by recorded PID only. py310 already has pyautogui/mss/opencv/
  pygetwindow/pywin32. SLIC `LibraryAdvance()` etc. (slicfunc.cpp:2354+) remains
  the fallback for programmatic GL opening if synthetic input flakes.
- First walkthrough: `steps/gl_advances.json` — 8 anchor advances asserted against
  their category cells (Chaos Adept↔cell_62 Forge of Chaos, Death Adept↔46,
  Alchemy/Astrology↔44, Banking↔10, Nature Magic↔40, Future Technology↔66).
  Search-box coord (246,94) is provisional — calibrate with `--record` if needed.

## [ADVANCE-ICONS — CANONICAL CONTRACT] 11 category cells; the "11 distinct md5s" was the DESIGN (2026-07-14, corrects the entry below)

The canonical advance-art mapping is the **Excel control-plane contract**
(`mom_dimension_inventory*.xlsx` → `advances` sheet = live `advances.csv`
`cell_index`): **87 advances → 11 thematic category cells** of MOMJR
`Improvements.bmp` — 2 Barracks (military ×9), 7 Courthouse (governance ×7),
10 Bank (economy ×8), 30 Harbor (construction ×5), 40 Gaia's Shrine (Nature ×6),
44 Great Library (knowledge ×27), 45 Oracle (Life ×6), 46 Wall of Bone (Death ×6),
56 Eldritch College (Sorcery ×6), 62 Forge of Chaos (Chaos ×6),
66 Celestial Beacon (Future Tech ×1). Full table in
`tools/improvements_bmp_layout.md`.

- **"388 TGAs, 11 distinct images" was the DESIGN, not corruption.** Intra-category
  shared art is canonical — do not de-duplicate. The 2026-07-13 "surgical 27" fix
  and the 2026-07-14 momjr-port UPAP repoints both "fixed" the wrong thing; the
  extractor+generator run over the contract supersedes all of them.
- **User anchor decode**: "Chaos Adept = position 63 (row 8, column 7)" is
  1-BASED counting → 0-based flat cell 62 = Forge of Chaos (fiery swirl). Off-by-one
  between 1-based human positions and 0-based `cell_index` cost a full derivation
  detour (@CIVILIZE order, enables-chain, content-scored remap — all dead ends;
  `advances_cell_remap.csv` is superseded, kept for history).
- **`cell_index` dual-use is intentional**: the category value serves as both the
  art cell AND the generator cost-weight bucket. The `art_cell_index` extractor
  override (added today) stays as an unused, documented escape hatch.
- Points 2 (generator owns uniticon advance blocks), 4 (GLHidden), 5 (pre-extracted
  goldmines) of the entry below remain valid.

## [ADVANCE-ICONS] Improvements.bmp IS the tech sheet; cell_index is DUAL-USE; uniticon advance blocks are generator-owned (2026-07-14)

Supersedes the "Civ2 MOMJR has no per-advance portraits" claim in the 2026-07-13
entry below — user-corrected: **`H:\Games\civ2\MOMJR\MOMJR\Improvements.bmp` is
the advance art source.** Advances lift the cell of a related building/wonder
via `tools/momjr_csv/advances_cell_remap.csv` (`new_cell_index`; `civ_idx` =
`@CIVILIZE` order). Full geometry in `tools/improvements_bmp_layout.md`.

1. **`advances.csv` `cell_index` is dual-use** — `ctp2_generator.py` reads it as
   the advance **cost weight** (`csv_weights` → `_scaled_mom_advance_cost`).
   `update_advances_tier_a.py` set `cell_index = epoch*5 + category` for cost
   tiers, which collapsed art coords to 11 buckets — THE root cause of "388
   advance TGAs, 11 distinct images". Sheet coordinates now live in a separate
   **`art_cell_index`** column; `civ2_sprite_extractor.py` prefers it.
   `art_cell_index = 999` = deliberate skip sentinel (extractor's beyond-sheet
   path) — never put grid coords back into `cell_index`.
2. **uniticon `ICON_ADVANCE_*` blocks are generator-owned and ephemeral**
   (`ctp2_generator.py` ~3609): every `Advance.txt` Icon ref is forced to
   `ICON_ADVANCE_<X>.tga` if that file exists on disk, else `UPLG001.TGA`
   (the base DEFAULT placeholder). Hand-edits to advance uniticon lines are
   stomped on the next generator run. **Durable art = the CONTENT of
   `ICON_ADVANCE_<X>.tga`.** To pin art for an advance, write the art into that
   file, don't repoint uniticon.
3. **Remap quality**: 68/87 `new_cell_index` values are genuine; 19 are scorer
   misfires landing on empty grey cells (0, 35, 68–71) with degenerate scores
   ~24–26. Those 19 got `art_cell_index=999` and their desired art pre-seeded
   into `ICON_ADVANCE_*.tga` (Alchemy ← `CM2_UPAP010L`, University ←
   `CM2_UPIP053L`, Death/Sorcery tier ← unit stills, Chaos Magic ← its unique
   generated icon). The extractor scales cells to the 160×120 GL canvas itself.
4. **GL visibility = `GLHidden` flag in Advance.txt**: 255 DB advances = 85
   visible (complete momjr design set) + 170 hidden (base leftovers, WAW stubs,
   USER_DEF_TECH_A). The GL list starting at "Alchemy" (not "Agriculture") is
   how you know hiding works.
5. **Pre-extracted art goldmines** (user rule: pre-extracted only, no zip
   diving): `H:\Games\civctp2\Advance-Graph\pic555\` = 106 base+Cradle advance
   pictures as PNGs; `H:\Games\civctp2\ctp2_data\default\graphics\pictures\` =
   loose Apolyton-source TGAs (incl. CM2_UPIP/UPVP families). Normalize desc
   byte 17 → 0x00 on anything copied in (GL crash guard, entry below).
6. **The momjr port itself uses surrogates**: its uniticon borrows base art for
   fantasy techs (Chaos Magic ← Nuclear Power's `CM2_UPAP077L`; Astrology ←
   `UPAP104L`, which is Unified Physics' "theory box" — its text fields even
   alias `ADVANCE_THEORY_OF_GRAVITY_*`), and deliberately shares art across 7
   visible pairs (Alphabet+Writing, Bridge Building+Pottery, Ceremonial
   Burial+Pantheism, Currency+Trade, Map Making+Seafaring, Masonry+Sanitation,
   Mathematics+Mysticism). Don't "fix" those pairs as dupes.

Pipeline to apply sheet art: fix `advances.csv` → `civ2_sprite_extractor.py
--sheet advances` → `ctp2_generator.py` → `mom_audit.py` (39 PASS expected).

## [SLIC] Faction / scoping syntax — SUPERSEDED, see the B1a API Contract below
> Two earlier [SLIC] sections lived here (pre-2026-07-05). They asserted `p == TRIBES_X`,
> `player[p].civ`, and "never use `player[0]`" — **all three disproven in-game** — and are
> removed so this file no longer holds both the wrong and the right guidance. The canonical,
> load-time-proven contract is "[SLIC] B1a API Contract" near the bottom of this file:
> - `playerTurn` is undefined; the BeginTurn/event-local player IS `player[0]` (CORRECT, not
>   forbidden). Helpers take `int_t p`; callers pass `player[0]` in.
> - `TRIBES_LIFE..TRIBES_CHAOS` are civ-DB record names, NOT SLIC symbols. Faction check uses
>   the NUMERIC player index: `p == 1` Life, `2` Nature, `3` Sorcery, `4` Death, `5` Chaos
>   (player N = civ N). `player[p].civ` / `civ[p].ident` / `civilization[p]` do not exist.
> - Membership uses `CityHasBuilding(city, BuildingDB(IMPROVE_X))`; `AddGold`/`CreateUnit`
>   take the integer player index.
> - **Control-plane sync**: reflect any SLIC signature/handler change in
>   `tools/momjr_csv/slic_inventory.csv`, then regenerate `mom_dimension_inventory.xlsx` via
>   `tools/export_mod_workbook.py` (the CSV is the editable surface; the xlsx tab is derived).

## [FIXED] Great Library SourceList Crash (TGA Descriptor Byte Mismatch)
- **Symptom**: Intermittent crash when opening the Great Library (`SourceList::Initialize` / `SourceListItem`).
- **Root Cause**: The scenario directory contained a loose TGA file (`CM2_Upap001l.tga`) shadowing a base advance icon. This file had a TGA image-descriptor byte of `0x01`, while the base file (and the correct standard for loose scenario icons) requires `0x00`. The wrong descriptor byte causes the CTP2 engine to misread pixel data, leading to render corruption and a crash in the GL SourceList.
- **Resolution**: Removed/renamed the improperly formatted shadow TGA (`CM2_Upap001l.tga.BAD_FORMAT_BACKUP`). The engine now correctly falls back to the base `ctp2_data` version, which has the correct `0x00` descriptor byte.
- **Rule**: Never shadow base UI/advance icons with scenario TGAs unless absolutely necessary, and *always* verify the TGA descriptor byte (offset 17) is `0x00` for standard icons, or `0x01` specifically for GL background TGAs (`upfg500/501/502`, `uptg04e`).

# MoM (Civ2 → CTP2) — Lessons Learned

Running log of hard-won lessons. Newest sections at top. Companion to
`MOD_DIMENSIONS.md` (dimension map) and `tools/INTERCONNECTION_TRACKING.md`
(which file references which dimension).

---

## gamefile.txt is the authoritative load manifest — improvements = buildings.txt, NOT Improve.txt

`ctp2_data/default/gamedata/gamefile.txt` lists every record file the engine loads.
**Line 26 is `buildings.txt`; `Improve.txt` is NOT in the manifest — the engine never
loads it.** This is the root of the project-long "buildings.txt vs Improve.txt"
confusion:
- `ctp2_generator.py` authored MoM improvements into `Improve.txt` (a dead file), so MoM
  buildings never loaded and every SLIC/GL ref to them was undefined
  (`Symbol IMPROVE_BARRACKS is undefined`). mom's `buildings.txt` stayed pure AE base.
- Proof: **AE_Mod ships only `buildings.txt`, no `Improve.txt`, and works.**
- The two files use **different schemas**: `buildings.txt` (AE) = `EnableAdvance`,
  `ProductionCost`, `DefaultIcon`, `Description` (CamelCase, multi-line). `Improve.txt`
  (old CTP2) = `ENABLING_ADVANCE`, `IMPROVEMENT_PRODUCTION_COST`, `IMPROVE_DEFAULT_ICON`
  (UPPER_SNAKE, single-line). You cannot raw-append one into the other — convert fields.
- Fix: MoM improvements must be authored into `buildings.txt`. `validate_all_surfaces.py`
  now checks `IMPROVE_` against `buildings.txt` only, and its base-fallback surface is
  **scoped to gamefile.txt** (so it won't false-flag never-loaded files like Improve.txt).
- **Rule:** `gamefile.txt` is the source of truth for which files load. Any generator
  target NOT in gamefile.txt is dead. Cross-check generator outputs against it.

## AllinoneWindow (New Game setup) crashes can be intermittent

An access violation (`0xC0000005`) in `AllinoneWindow::Idle`/`SpitOutGameSetup` (the New
Game setup screen) recurred at session start (image load) and again later. Release-build
symbols in the crash dump are APPROXIMATE (nearest export, not the real function) — don't
over-read "WonderRecord/ConstRecord". When all reference surfaces validate clean, a
single **retry of the launch often succeeds** (it did here). Don't chase a clean build as
if it were a data bug.

## The 7 reference surfaces — validate ALL before launch (don't relaunch per error)

CTP2 validates entity references from MANY surfaces, not one. Discovering them one
launch at a time is the trap. `tools/validate_all_surfaces.py` checks every surface
against the live DBs and is wired into `ctpedit patch` (generator → `fix_gl_links`
→ `validate_all_surfaces` → audit). The surfaces:

1. **Data-file gating fields** — `EnableAdvance`/`ObsoleteAdvance`/`Prerequisites`/
   `AddAdvance`/`RemoveAdvance` → Advance DB; `UpgradeTo` → Unit DB. (e.g. "Cyber
   Ninja not found": `UNIT_SPY` upgraded to a base unit the build half-kept.)
2. **Great Library `<L:DATABASE_<TYPE>,<TOKEN>>` links** (all 10 dims). (e.g.
   "Desert Mountain" = `TERRAIN_BROWN_MOUNTAIN` link with an empty terrain.txt.)
3. **Great Library advance sections** `[ADVANCE_X_GAMEPLAY|HISTORICAL|PREREQ|
   STATISTICS]`. (e.g. "Drama not found": orphan advance GL section.)
4. **AI build lists / strategies** (`default/aidata/*.txt`).
5. **EndGameObjects.txt** (victory wonders/buildings/tileimps). (e.g. "The Solaris
   Project not found": missing file → fell back to stock requiring base wonders.)
6. **Base-fallback gamedata files** — any `ctp2_data/default/gamedata/*.txt` the
   scenario does NOT override is loaded from base and may reference replaced entities.
7. **SLIC entity symbols** — `UNIT_/IMPROVE_/ADVANCE_/WONDER_` in `*.slc` (runtime).
   (e.g. "Symbol UNIT_SHAMAN is undefined": Nature blessing spawned a missing unit.)

Rule of thumb: KEEP dimensions (terrain, governments, orders, concepts, goods, tile
improvements) use BASE content — never regenerate them from a structured CSV via a
"raw" importer (that wiped terrain.txt to 1 line). MoM dimensions (advances, units,
improvements, wonders) are CSV-authored; everything that references them (GL,
EndGameObjects, SLIC, build lists) must be authored/repaired to match.

### 🚨 TDD & Smoke Test Mandate
**Any error encountered during generation or runtime MUST be replicated as a failing condition in `validate_all_surfaces.py` (our smoke/unit tests).**
- When a change is made to fix an issue, the smoke test is the absolute authority on whether the fix worked.
- If the smoke test still triggers the same issue after the change, **the hypothesis for the fix was wrong**. Do not make excuses, do not blame cached files, do not stop until the smoke test passes.
- **Zero tolerance for shadow injections**: If the engine requires an entity to prevent a crash, it MUST be added to the Excel control plane. The generator must never silently inject base-game data post-CSV parsing. The control plane is the singular, undisputed source of truth.

---

## The two toolchains — know which one you're running

There are **two** generation front-ends and they are NOT interchangeable:

| Tool | Location | What it does | File layout |
|---|---|---|---|
| `mom_translator.py` | `modder_files/` | One-shot **wholesale replace** of 4 dimensions from Civ2 import | writes `buildings.txt`, reduced record sets |
| `ctp2_generator.py` (via `ctpedit.py patch`) | `Scenarios/mom/tools/` | **Control-plane driven** merge; idempotent; prunes/hides/syncs GL+uniticon | writes `Improve.txt`, full record sets |

**The control plane (`mom_dimension_inventory.xlsx` + `tools/momjr_csv/*.csv`) is the
source of truth.** `ctpedit.py patch all` is the canonical build. `mom_translator.py`
is a Civ2-import front-end whose output must still be reconciled by the control plane.

**Design rule (from the user):** MoM = *base records that don't conflict with the
fantasy genre* (qualitative pass over the control-plane records) **∪ Civ2 MoMJR imports**.
It is a **curated superset**, not a wholesale replacement.

### The whack-a-mole root cause
`mom_translator.py` *replaces* `Advance.txt` with only the ~95 Civ2 advances. But the
rest of the AE base (Great Library, uniticon, terrain, tileimp, AI data) still references
the full base set. CTP2 validates **every** cross-reference at load and hard-errors on the
first miss ("X not found in Y database"). Replacing a dimension wholesale orphans hundreds
of references. The old backup that actually launched had **278 advances** precisely because
it kept the base superset.

**Fix:** build with `ctpedit.py patch all` (the generator keeps/hides base records and
keeps the GL consistent), not by replacing dimensions wholesale.

---

## "X not found in Advance database" — it's the Great Library SECTIONS

Use the tools, don't grep blindly:
```
python tools/scan_interconnections.py advances ADVANCE_DRAMA
```
For an advance, the validated interconnection is the **Great Library entry-sections**
`[ADVANCE_X_GAMEPLAY|HISTORICAL|PREREQ|STATISTICS]` — NOT `uniticon.txt` (advances have
no icon-DB validation), and NOT only the `<L:DATABASE_ADVANCES,...>` prose links.

### Why pruning the GL sections does NOT work
`ctp2_generator._restore_missing_uniticon_gl_sections()` **re-adds** GL sections for every
`uniticon.txt` entry on every run. So deleting orphan advance GL sections is futile — they
come back. The generator's design is **keep base records, hide them** (mirrors how base
units get `GLHidden`+`NoIndex`), not delete them.

### The fix that stuck (now in `ctp2_generator.py`, after the advance restore pass)
Create **hidden stub advances** for every advance referenced by the GL (both section
headers and `<L:DATABASE_ADVANCES,...>` links, across `Great_Library.txt` AND
`WAW_Great_Library.txt`) that isn't already in `Advance.txt`. The existing `GLHidden` pass
then keeps them out of the player-facing tech tree. Result: `Advance.txt` 95 → 243, with
0 orphan advance sections/links. `ADVANCE_DRAMA` etc. now exist as hidden stubs.

`ModAdvance` only writes the `Advance.txt` block + `gl_str` display name — it does NOT
write GL sections, so stubbing advances does not duplicate GL prose.

---

## Units/Improvements GL sections are NOT load-validated like advances

AE base `Units.txt` has ~72 units but its Great Library references ~172 — and **AE_Mod
launches fine**. Therefore CTP2 does **not** hard-error on orphan unit/improvement GL
sections at scenario load the way it does for advances. Do **not** preemptively generate
stub units to "fix" 100+ orphan unit GL sections:
- `ModUnit` registers a GL section too, so stubbing would **duplicate** existing GL prose.
- The error class is unconfirmed for units; only advances were reproduced.

If a unit/improvement DB error ever IS reproduced at launch, diagnose with
`scan_interconnections.py` first to find the exact validated surface.

---

## Government / Anarchy science (original "tech never advances")

`GOVERNMENT_ANARCHY` in stock `govern.txt` has `MaxScienceRate 0` and `KnowledgeCoef 0.1`
→ you start in Anarchy and can NEVER research out of it. Set to `0.3 / 0.3`.
`govern.txt` is currently copied raw (no `governments.csv` row), so this edit lives in the
scenario `govern.txt` and survives generator runs. If `governments.csv` becomes the source,
encode it there instead.

---

## Tooling gotchas

- **Console encoding:** the `tools/*.py` print `⚠`/`→` (U+2026 etc.) and crash under
  Windows cp1252. Always run them with `PYTHONIOENCODING=utf-8`.
- **`crossref_audit.py`** expects the canonical file layout (`Improve.txt`, `feat.txt`, …).
  It fails on `mom_translator` output (`buildings.txt`, missing files). Run it only after
  `ctpedit.py patch all`.
- **`reg.load()` caches** (`schema_registry`/`ctp2_parser`): repeated `reg.load(rel)` returns
  the same object; `reg.save_all()` persists every cached object via `obj.render()`.
  `LibraryFile.render()` builds from `.sections`. WAW library is loaded separately via
  `_load_library_file` and must be saved explicitly with `_save_library_file`.
- **`apply_masks.py` does NOT clean `Great_Library.txt`** — it removes blocks from
  `Advance.txt`/`Units.txt`/`Improve.txt`/`Wonder.txt`/`tileimp.txt` + string tables only.
  It also only acts on records that EXIST in the data files; an orphan that lives ONLY in
  the GL is invisible to it.

---

## Scenario picker / launch hygiene

- **Custom picker art:** `packicon.tga` (pack root) and `scen0000/scenicon.tga` are the
  scenario-selection thumbnails. `mom_translator`'s copytree overwrites them with AE
  placeholders — it now preserves/restores them. The MoM custom art differs from AE's.
- **`scenario.txt`** is a plain 2–3 line text file (title / description), NOT KV. Overwrite
  it wholesale to re-identify the scenario; a regex replace silently no-ops on AE's format.
- **`packlist.txt`** is exactly 3 lines: name / description / scenario-count. Duplicate
  names across `mom/` and `mom_*/` make the picker show duplicate entries.
- **Don't keep two scenario dirs with the same packlist name** (`mom` vs `mom_`); rename
  stale ones.

---

## Feat.txt Integration (Lessons Learned)

**Purpose**: eat.txt defines mini-script effects triggered by the CTP2 engine or SLIC (e.g., EffectIncreaseProduction 5, SlicMessage "FeatGotConcrete"). These are typically tied to specific advances or building milestones.

**The Control Plane Mandate**: The control plane (CSVs) is the single gateway for scenario generation. Blindly passing through the base game's eat.txt violates this mandate, as it contains faction-specific feats (e.g., Egypt, Zoroastrianism) and advance/building dependencies that do not exist in the MoM mod, leading to broken or dead code.

**The Solution**: A generic translator (_translate_base_feats()) was implemented in ctp2_generator.py. It reads the base game's eat.txt and filters it against the MoM control plane:
- **Advance Check**: Feats named FEAT_ADVANCE_* are kept only if the corresponding ADVANCE_* exists in dvances.csv.
- **Building Check**: Feats containing Building IMPROVE_* are kept only if the corresponding IMPROVE_* exists in improvements.csv.
- Feats with no recognizable dependencies, or whose dependencies are fully satisfied, are kept. Others are dropped.

**Interconnections**: 
- eat.txt is tightly coupled to Advance.txt and uildings.txt (via Improve.txt).
- It also references gl_str.txt for display strings (e.g., Description str_ldl_0), though many base feats use a generic placeholder.

**Open Questions for Future Integration**:
1. Should we remap base-game feats to MoM-specific advances (e.g., mapping a generic "production boost" feat to an MoM custom advance) instead of strict keep/drop?
2. Should MoM define its own custom feats in a new eats.csv control plane file, rather than relying on filtered base-game feats?
3. How do we handle feats that depend on SLIC messages or events that are unique to base-game civilizations but have no MoM equivalent?

**Current State**: The generator now produces a valid, filtered eat.txt (9 feats kept) that strictly adheres to MoM's control plane dependencies, with no manual downstream patching.

---

## Unintegrated Changes Protocol (The \_unintegrated\ Directory)

**Problem**: The generator's "RECONSTRUCT FROM NOTHING" nuke phase (shutil.rmtree on \gamedata\ directories) aggressively wipes out any experimental, partially completed, or archived files (e.g., \_archived_slic/\). This causes valuable work-in-progress or deferred features to be lost in ancient git commits, making iterative re-approach difficult.

**Solution**: A dedicated \Scenarios/mom/tools/_unintegrated/\ directory has been established as the canonical holding area for:
- Archived SLIC modules (e.g., \mom_func.slc\, \mom_turns.slc\, \mom_city_effects.slc\)
- Partial CSV drafts or experimental dimension mappings
- Harness patches that require further debugging before control-plane integration

**Rules**:
1. **Generator Safety**: This directory is outside the nuke paths (\default/gamedata\, \english/gamedata\, \default/aidata\) and will **never** be automatically deleted by the generator.
2. **No Silent Deletion**: Files here must not be deleted without being moved to the active control plane (\momjr_csv/\) or explicitly documented as permanently abandoned.
3. **Promotion Path**: When a feature is ready, move its artifacts to the active harness, update \dimension_inventory.md\, and remove the file from \_unintegrated/\.

This ensures we can pivot architecturally without losing the breadcrumbs of what we were aiming to accomplish.

---

## [SPRITES] Invisible Unit Root Cause: Anim Transparency 0 (SOLVED 2026-07-03)
- **Symptom**: Unit banner renders on the map, body is invisible at EVERY zoom. Portrait fine. SPR structure valid, pixels decode fine.
- **Root Cause**: Each SPR anim block carries per-frame u16 transparencies used as blend alpha at draw time (`alpha = value << 3`). Per Activision's own script docs (Gu01.txt): *"0 is invisible, 15 is opaque"*. `Actor.h: NO_TRANSPARENCY = 15`; `pixelutils_Blend16` returns pure background at alpha 0. makespr.py's `pack_anim` zero-padded omitted transparency entries → every makespr.py-built unit drew at 0% opacity.
- **Trap within the trap**: `ANIM_TRANSPARENCIES 0` in GU scripts is a **flag** ("no explicit list"), not a value. Explicit lists are `ANIM_TRANSPARENCIES 1 { 15 15 ... }`. The fix belongs in the pad default (`pack_anim` pads with 15 now), not the templates.
- **Diagnosis without launching the game**: decode the MOVE-anim transparencies from any GU*.SPR — stock sprites all carry 15s.
- Spec: `Scenarios/mom/specs/spr-anim-transparency.md`.

## [SPRITES] makespr.py Achieved BYTE-FOR-BYTE Parity With makespr.exe (2026-07-03)
- **Golden fixture**: Kull's Cradle 5 Legion (`H:\Games\ctp2\16-makespr\16\` — inputs + Gu16.txt + makespr.exe-built GU16.SPR, 452,956 bytes). Full MakeSprite kit (MAKESPR.EXE, Cow example, GU00.txt template, docs): `H:\Games\ctp2\MakeSprite\` (source: http://www.ctp2.info/download/MakeSprite.zip).
- **Golden test**: stage inputs + GU16.TXT in a work dir, `python makespr.py -u 16`, byte-compare against Kull's GU16.SPR. Result after fixes: **IDENTICAL**.
- **Bugs found & fixed in makespr.py via the golden diff** (each was invisible to structural inspection):
  1. **Shadow stamp was GREEN not magenta** (`merge_shadow` white-bg branch): shadows encoded as opaque COPY runs instead of SHADOW runs → green/dark halo in-game. Magenta (255,0,255) packs to the shadow magic pixel in both 565 (0xF81F) and 555 (0x7C1F).
  2. **Alpha premultiply missing**: the original tool premultiplies EVERY pixel at load: `c = ceil(c*a/255)` (same ceil idiom as `spriteutils_AveragePixel32`). Full-frame feathered pixels carry premultiplied color; minis average premultiplied values. One premultiply at load reproduces both. (The Apolyton engine source's `RGB32Info` does NOT premultiply — the 1999 tool differs from the surviving source; the golden file is ground truth.)
  3. **Mini pipeline order**: exe quarters the PRISTINE image (ceil-average all 4 RGBA components INCLUDING alpha and transparent pixels' RGB), nearest-samples the shadow separately (aa=FALSE), then merges shadow into the mini and encodes. Partial averaged alpha ⇒ feathered runs in minis.
  4. **Single-facing actions (IDLE/VICTORY) read facing-4 files** (`GU16IA4.*`, `GU16VA4.*`), not facing-1. makespr.py now maps 1-facing actions to file digit 4.
  5. **`UNIT_SPRITE_ATTACK_IS_DIRECTIONAL`** tag (before the attack block) was unparsed → ParseError. Now parsed and written to the trailing `hasDirectional` u16 (`hasDeath` likewise now honors `UNIT_SPRITE_IS_DEATH`).
  6. **Shield points were hardcoded (24,24)**: parsed `UNIT_SPRITE_SHIELDPOINTS` values are now serialized (5 actions × 5 facings POINTs, enum order move/attack/idle/victory/work).
- **Input trap**: 24-bit RGB TIFFs (no alpha channel — e.g. the kit's own Cow sample) make every pixel opaque → no keying, ~14KB frames instead of ~2.4KB. makespr.py now warns. Proper inputs are 32-bit ARGB TIFF (tutorial: GIMP Select-by-Color → Cut on the GUblank template).
- **Art source lead for MoM units**: Civ3 "Conquests of Might and Magic III (CoMM3)" total conversion by tom2050 — https://forums.civfanatics.com/threads/conquests-of-might-and-magic-iii-comm3-epic.619720/ — has full HoMM3 creature unit graphics (candidate source for ZOMBIES/SPEARMEN/SWORDSMEN placeholder fixes).

**CANONICAL CONFIRMATION (2026-07-03)**: After the golden-parity fixes, the Peasants unit renders
correctly on the CTP2 map (body + banner, correct art, matching portrait) — verified in-game by
screenshot. The anim-transparency root cause and the makespr.py parity work above are the canonical
explanation and fix for the "invisible unit / empty sprite" class of bugs.

## [UNITS] Settler Retired; Peasants Are MoM's City Builders (2026-07-03)
- **Engine fact (gameinit.cpp:404, `gameinit_PlaceInitalUnits`)**: a new game spawns, as each
  player's starting units, the FIRST unit in the Units DB with `SettleLand`. There is no hardcoded
  "UNIT_SETTLER" — DB order + `Settle:` lines decide.
- **Design**: MoM has NO settler unit. UNIT_PEASANTS carries the full settle kit lifted from the AE
  base settler: `SettleCityType UNIT_CITY`, `SettleSize 1`, `Settle: Land/Mountain`, `Civilian`,
  plus a COMPLETE `UNIT_CITY` target block (the engine's settle order spawns UNIT_CITY; a truncated
  block missing terrain classes/flags can fail city creation silently, esp. with scenario SLIC off).
- **UNIT_SETTLER stays in the DB but retired**: `CantBuild`, no `Settle:` lines. Kept only to avoid
  dangling references (Great_Library/gl_str/tut2_main.slc) and DB index shifts — see the
  orphan-GL-section error class. Do not re-add its Settle lines or it becomes the starting unit again.
- **Settle runtime gates that fail SILENTLY with SLIC disabled**: (1) unit already moved this turn
  (needs unspent move points or first-move flag; MaxMovePoints 100 = any move exhausts it),
  (2) tile owned by another city's radius ("too close").

## [TECH] Empty Build List After First City = Starting Advances Don't Enable MoM Content (2026-07-03)
- **Symptom**: found first city → no units, no buildings available to build; fear of anarchy/zero-science start.
- **Mechanics (engine, AE build)**: starting techs come from `DiffDB.txt` `ADVANCE_CHANCES` blocks
  (one per difficulty; rows = `ADVANCE_X humanChance aiChance`; `Player.cpp` grants 100%-chance rows
  always). Starting government = first govern.txt entry whose EnableAdvance is HELD at start, else
  index 0 = ANARCHY (no science). MoM DiffDB already guaranteed ADVANCE_MONARCHY (anarchy escape ok).
- **Root cause**: the granted advances were all BASE techs (Toolmaking, Agriculture...) which enable
  ~nothing in MoM. MoM tier-0 hangs off **ADVANCE_WARRIOR_CODE** (12 units + 8 buildings incl.
  peasants). Not granted → empty build lists.
- **Fix**: guarantee `ADVANCE_WARRIOR_CODE 100 100` in every ADVANCE_CHANCES block; generator now
  injects all of `START_GUARANTEED_ADVANCES` (government + tier-0 enabler) via
  `_ensure_diffdb_start_government`. Keep the list in sync with the enabler histogram:
  `grep EnableAdvance Units.txt | sort | uniq -c`.
- **Note**: `EXTRA_SETTLER_CHANCE 1000000` in DiffDB gives the extra starting settle-unit; the engine
  spawns the first SettleLand DB unit, so post-settler-retirement these are Peasants.

## [BUILD-LIST] AE 'X' Sentinel Items Leaked Into Turn-1 Build Lists (2026-07-03)
- **Symptom**: build manager shows "Xpower Plant", "Xhydro Plant", "Xwomens Suffrage" etc. at start.
- **What X-items are**: the Apolyton pack's convention for REMOVED base-game improvements/wonders —
  kept in the DB under an X-prefixed name for index/reference safety. MoM's ingestion mistook them
  for MoM content (gl_str even says "is a Master of Magic city improvement") and gated them with
  the tier-0 advance (ADVANCE_WARRIOR_CODE), so guaranteeing that start tech surfaced them.
- **Fix (safe mask)**: stamp `ObsoleteAdvance ADVANCE_WARRIOR_CODE` on every `IMPROVE_X*`/`WONDER_X*`
  block — obsolete from turn 1 for all players, records stay in DB (no index shifts / dangling GL
  refs). Generator post-pass `_retire_x_sentinels()` keeps regens clean. 8 entries: 3 buildings
  (XPOWER_PLANT, XHYDRO_PLANT, XWOMENS_SUFFRAGE) + 5 wonders (XLIGHTHOUSE, XSTATUE_OF_LIBERTY,
  XWOMENS_SUFFRAGE, XAPOLLO_PROGRAM, XCURE_FOR_CANCER). Note buildings DO support ObsoleteAdvance
  in the AE engine (building.cdb:48) even though base buildings.txt never uses it.
- **Deeper cleanup (later)**: exclude X-prefixed idents at ingestion and register them in
  mask_state.json so apply_masks.py can remove them wholesale with GL scrubbing.

## [CONTROL-PLANE] 'HIDE X' CSV Rows Are Mask Directives, Not Content (2026-07-03)
- **Symptom**: a buildable improvement literally named "Hide Supermarket" in the build manager.
- **Root cause**: `momjr_csv/improvements.csv` row `999,HIDE Supermarket,...` means "hide the
  base-game Supermarket"; the generator ingested it as a MoM building named "Hide Supermarket"
  (cost 0, icon NOTHING) and even wrote GL text claiming it's a MoM improvement.
- **Fix**: generator skips rows whose name starts with `HIDE ` (or cell_index 999) as mask
  directives; existing phantom retired via ObsoleteAdvance (same safe-mask pattern as X-sentinels).

## [ART] Civ2 Sheet Extraction Rules That Survived Contact With Reality (2026-07-03)
- MoMJR Units.bmp: 64x48 cells, 10 cols; row0 = peasant(0), zombie(1), spearman(2), swordsman(3),
  phantom warriors(4)... backdrop = magenta + dusky purple (135,83,135) diamonds + green grid.
- **Backdrop classification**: a colour is backdrop only if it appears on the cell BORDER (>=4 px)
  AND covers >=3% of the cell. Naive exact-colour keying ate the spearman's spear (its highlight
  gray also touched the border via the shield). Component-size heuristics also failed (shaft grain
  merged with backdrop components).
- **Output TGA convention**: BLACK background (not magenta) — build_unit_sprite corner-keys it,
  which also removes the Civ2 1px black outline (as the manifest requires); magenta backgrounds
  leave a pink LANCZOS fringe on the compiled sprite.
- **Scale convention**: bbox-crop the figure and scale to ~116px tall on the 160x120 canvas,
  bottom-anchored at y=118 — matches the peasant's on-map mass (it fills ~97% of frame height).
- Cell indices + rules now recorded in momjr_csv/civ2_converted_graphics.csv (CONVERTED rows).

## [COSTS] MoM Improvement Costs Rescaled to AE Age Bands (2026-07-03)
- **Symptom**: buildings complete in 1 turn (raw Civ2 costs 4-60 in a CTP2 economy).
- **Fix**: `_retune_mom_improvement_costs()` in ctp2_generator — the missing sibling of the existing
  unit/wonder/advance retunes. Bands base buildings.txt ProductionCost by EnableAdvance age and maps
  MOMJR improvements.csv costs into them via `_scale_cost_into_band`. ALL csv rows feed the
  improvement specs (wonder rows >= 40 also emit IMPROVE_ blocks that show in the Buildings tab).
  Retired blocks (ObsoleteAdvance) skipped. Result: 270 (Barracks/Temple = base first-age floor)
  up to 3500; base first-age improvement band is ~[270..875], NOT starting at 525 (alphabetical
  sampling deceived; assert against the real band min).
- **Sprite extraction addendum (v6 rules)**: near-black figure pixels (r+g+b<=24) -> (16,16,16) so
  the baked Civ2 feet-shadow survives corner keying (tolerance 12); horizontal anchor = center of
  BODY columns (density >= 35% of peak) at canvas x=80 — full-pixel centroid or bbox lets thin
  protrusions (spear) drag the body off the selection axis ("body sits lower-right" symptom).

## [SLIC] Crash Signature: SLIC Debugger SourceList + Non-ASCII Bytes (2026-07-03)
- **Symptom**: silent crash at the game-setup screen. crash.txt stack: `AllinoneWindow::Idle` ->
  `SpitOutGameSetup` -> `SourceListItem(..., SlicSegment*, ...)` / `SourceList::Initialize` + `yy_nxt`
  (the SLIC lexer).
- **Chain**: `DebugSlic=Yes` in ctp2_program/ctp/userprofile.txt opens the built-in SLIC debugger
  (ui/slic_debug/sourcelist.cpp) whose ancient list UI access-violates while rendering sources when
  the lexer hits trouble. Trigger candidates that session: (1) scenario.slc contained UTF-8
  em-dashes in comments - the SLIC lexer is ASCII-only; (2) an EMPTY scenario-level tutorial.slc
  override (removing stock tut2 segments the engine may look up by name).
- **Rules**: .slc files must be PURE ASCII with CRLF, comments included (spec already said so; the
  violation was in a comment header). Retiring stock tutorial SLIC via an empty override is
  UNVERIFIED and parked (`tools/_unintegrated/tutorial.slc.phaseA-parked`) pending a clean bisect.
- **Diagnostics**: crash.txt + usercritmsgs.txt + logs/slicdbg.txt (per-segment parse dump when
  DebugSlic=Yes) are the SLIC triage trio.

## [SPRITES] Hot Points (47,72) Crash Scenario Load; (39,80) Loads Fine (2026-07-03, bisect-proven)
- **Symptom**: 0xC0000005 during scenario select, right after the unit-DB dump, no crash.txt.
  Reproduced 3x; bisect ladder (all SLIC parked = still crashed; GU92 hot points reverted = loads)
  proves the trigger was GU92.SPR built with hot points (47,72) — hot_y equal to the 72px frame
  height is the suspected edge (mechanism in the blitter unidentified; 80 > 72 is FINE).
- **Rules**: avoid hot_y == frame height; when nudging a unit down, prefer shifting the image
  within the 160x120 canvas over lowering hot_y toward 72. SLIC files were fully exonerated —
  the parked Phase A files can return unchanged.
- **Bisect discipline that solved it**: one variable per launch; evidence = civ3log tail +
  slicdbg.txt mtime + WER/event logs; timeline via file mtimes vs. session times.

## [AI-CRASH] HYPOTHESIS UNDER TEST — Guaranteed Start Tech Exposes Turn-0 AI Scheduler Crash (2026-07-03)
Following AGENTS.md "Hypothesis Discipline".
- **Hypothesis**: guaranteeing `ADVANCE_WARRIOR_CODE` at game start (DiffDB
  ADVANCE_CHANCES, commit bfdd322) is the FIRST time the AI has a full MoM buildable
  roster at turn 0, exposing a latent crash in CTP2's goal Scheduler while it
  evaluates MoM units. Evidence: crash log (civ3log000, 17:58 run) ends at line 641
  immediately after `ASSIGN POPULATIONS ... elapsed 0 ms` (last step of AI begin-turn
  management) with the fault in the next phase (Scheduler/Goal frames in the stack);
  the Governor was scoring `List 5 Best unit: Peasants`, `List 13/14 Best unit: Warrax`,
  and `Best settler unit: Peasants needed: -2` (malformed negative count). Before today
  the turn-0 AI had ~nothing buildable and never crashed — matches "which was new."
- **SLIC EXONERATED for this crash**: all four .slc files were PARKED
  (tools/_unintegrated/parked/) when this crash occurred; gamedata held only
  tut2_main.slc. SLIC removal did NOT stop the crash.
- **Test**: remove ONLY `ADVANCE_WARRIOR_CODE` from all 6 DiffDB ADVANCE_CHANCES blocks
  (keep ADVANCE_MONARCHY — it enables no units/buildings, just anarchy escape).
- **Prediction**: TRUE -> turn-0 AI crash stops (AI has empty roster again, as before).
  FALSE -> crash persists -> next rollback = buildings.txt cost rescale, then X-sentinel
  retirement.
- **Confirmation bar (INTERMITTENT bug)**: one clean launch proves NOTHING — the prior
  identical-file run played 10 turns before this run crashed at turn 0. Require **3-4
  consecutive games reaching turn ~15 with no AI crash** to accept.
- **If confirmed**: real fix is HARDENING MoM AI unit data (the `needed: -2` settler
  path / Warrax role attributes in UnitBuildLists.txt + unit AI flags), NOT permanently
  removing the start tech (which reintroduces the empty-build-list bug).
- **Result**: PENDING user playtest.

## [SPRITES] Uniform Hot-Point Rule — Auto-Anchor From Figure Geometry (2026-07-04)
- **Problem**: peasant (GU104) centered on its tile but spearman (GU92) sat upper-right, and manual
  per-unit hot-point tweaking (39,80)->(50,68)->(63,62) never converged (non-uniform, non-reproducible).
- **Root cause (data-proven)**: a unit centers when its hot point equals (figure_centre_x, feet_y-16).
  The peasant satisfied this by luck (template default 49,54 ~= its figure); the spearman's figure
  centre was 41 with feet at 70, so the correct anchor was (41,54) — nowhere near the hand-tuned values.
  CTP2 anchors a unit at its lower shin (feet-16), not its feet, so it straddles the iso tile diamond.
- **Uniform fix**: `build_unit_sprite.py` now DERIVES the hot point from each figure's bbox
  (`hotpoint_from_bbox`: hot_x = centre-x, hot_y = feet_y - FEET_TO_HOTPOINT=16). --hot-x/--hot-y are
  now OVERRIDES (default AUTO). Verified: peasant/zombie/spearman/swordsman all land at dx~0, dy=-16.
- **Rule for all future MoM unit sprites**: never hand-tune hot points; the figure's on-frame geometry
  determines the anchor. If a unit looks off, the figure is mis-placed in the frame (fix extraction),
  not the hot point.

## [FIXED] Fuglies: Improvement/Wonder Double-Load (2026-07-04) — THE root cause
- **Symptom**: rainbow-static ("fuglies") where the city-name renders — Build Manager city
  selector AND the control-panel unit/city name banner. Game otherwise fully playable.
- **Root Cause**: **24 concepts existed as BOTH an `IMPROVE_<X>` block in buildings.txt AND a
  `WONDER_<X>` block in Wonder.txt** (GREAT_LIBRARY, ORACLE, THE_PARTHENON, GNOME_TREASURY,
  GAIAS_SHRINE, …). The engine loads the same concept into two databases -> conflicting DB
  indices -> Build Manager render corruption that bleeds onto the shared name-banner surface.
  This is the SAME class as commit 7afc935 (the Improve.txt + buildings.txt double-load), in a
  new form: the generator emitted an `IMPROVE_` block for wonder rows (improvements.csv
  `cell_index >= 40`) on top of the `WONDER_` block. buildings.txt had 46 IMPROVE_ blocks;
  24 of them were wonder twins.
- **How it was found**: `git log --grep=fugl` — the commit history names the exact mechanism
  ("duplicate/conflicting building indices that corrupted the Build Manager render"). ALWAYS
  read the fugly commit messages first.
- **Resolution**: (1) removed the 24 duplicate `IMPROVE_<wonder>` blocks from buildings.txt
  (concept survives as its WONDER_ block); 46 -> 22 real improvements; `IMPROVE_ ∩ WONDER_ = ∅`.
  (2) fixed the generator (`ctp2_generator.py`, improvements.csv ingestion) to SKIP wonder rows
  (`cell_index >= 40`) when emitting IMPROVE_ blocks. (3) reconciled dangling refs to the removed
  GAIAS_SHRINE (BuildingBuildLists.txt happiness/small-city lists -> IMPROVE_TEMPLE; tut2_main.slc
  'TBuiltTemple' handler -> IMPROVE_TEMPLE, its intended target). (4) added surface-8 guard to
  validate_all_surfaces.py: no ident may be both IMPROVE_ and WONDER_.
- **Rule/Prevention**: a concept is EITHER an improvement OR a wonder, never both. The
  improve/wonder-overlap guard is now launch-blocking. See [[mom-gamefile-manifest]].

### The fuglies are COMPOUND — three co-occurring causes, all in `git log --grep=fugl`
Resolving the banner took fixing ALL THREE; any one left in place kept the static. Do not
stop at the first cause found:
1. **DB double-load** (this entry / 7afc935): a concept present as both IMPROVE_ and WONDER_
   (or Improve.txt + buildings.txt) -> conflicting build-manager indices -> render corruption.
2. **Image/TGA format** (032f463): CTP2 renders 16-bit TGAs as ARGB1555 with descriptor byte
   (offset 17) = 1 and a TGA-2.0 footer (AE: desc=1, 160x120 -> 38444B). MoM's desc=0 / no
   footer -> engine treats the alpha bit as 0 -> the fill blits transparent -> the surface is
   never painted -> heap garbage = the rainbow static. Fix the extractor/writer to emit ARGB1555
   (desc=1) + footer; do NOT blanket-force desc=0 (that was a wrong turn this session). Caveat:
   descriptor requirement varies by texture family (advance-icons upap* are desc=0; the CM2
   fugly proved a desc=1 override there breaks the GL) — match AE per family, verified by bytes.
3. **Line endings** (7b7ecf2): CRLF `\r` contamination in engine-parsed files breaks lookups.
   String files (gl_str/tips_str/civ_str/civilisation) MUST be LF (.gitattributes eol=lf).
- **A PARTIAL fix still shows full static — don't read "still broken" as "wrong hypothesis."**
  After the DB double-load fix alone, a clean full restart STILL rendered static (all tests here
  were full restarts — it is NOT a texture-cache/stale-render effect; that was a wrong inference).
  The banner only cleared once ALL THREE causes were addressed. With a compound bug, each correct
  fix looks like a failure until the last one lands, so verify all three surfaces before judging.
- **First move for ANY render corruption: `git log --grep=fugl` and read every message.** The
  history named all three mechanisms; chasing textures blind cost a whole session.

## [SLIC] B1a API Contract — sphere per-turn gold (2026-07-05, in-game proven)
Base-verified against ctp2_program/ctp/ctp2.map builtins + reference scenarios. Each was
a real load-time SLIC error dialog before the fix. Guarded by tools/test_mom_slic.py.
- **`playerTurn` is NOT a base SLIC symbol** ("Symbol playerTurn is undefined"). The
  BeginTurn event-local player is `player[0]`; used in an integer context it yields the
  turn player's index (reference scenarios do `if(player[0] == 1)`). The parked git-history
  modules used `playerTurn` throughout but were never actually run.
- **`TRIBES_LIFE`..`TRIBES_CHAOS` are civilisation-DB record names (#1..#5), NOT SLIC
  symbols** — SLIC cannot resolve them ("Symbol TRIBES_LIFE is undefined"). Faction identity
  uses the NUMERIC player index: player N = civ N (Life 1, Nature 2, Sorcery 3, Death 4,
  Chaos 5). The spec's `p == TRIBES_X` form was aspirational and never validated.
- **`AddGold(playerIndex, amount)`** — integer index, NOT `AddGold(player[p], ...)`. Real
  builtin (Slic_AddGold); AlexanderTheGreat uses `AddGold(1, 5000)`.
- **`CityHasBuilding(city, BuildingDB(IMPROVE_X))`** — a DB reference, NOT a quoted
  `"IMPROVE_X"` string.
- **One-shot handlers need a file-scope `int_t` latch**; DisableTrigger alone did NOT stop
  re-fire, and an unlatched `Message` in BeginTurn floods the queue -> 0xC0000005. Per-turn
  side effects that SHOULD fire every turn (AddGold income) need no latch.
- **Method that worked**: prove ONE element (Life) end-to-end in-game, then fan out to the
  dimension (B1b: the other 4 spheres). Life = `6 + cities*3 + lifeBlessings*4` gold/turn.

## [SPRITES] Units.bmp grid is 9x7 @ y=15, NOT 10-col @ (0,0) (2026-07-05)
MoMJR `H:\Games\civ2\MOMJR\MOMJR\Units.bmp` (640x586) is a 9-column x 7-row grid, ~64px
pitch both axes, content starting at y=15 (not 0,0). The extractor assumed 10 cols at (0,0),
mismapping every unit from flat cell 9 on: 19 sliced empty cells (invisible sprites) and ~30
rendered the WRONG neighbouring unit (Hydra showed a minotaur, etc.). Fixed via gutter-
detected grid in civ2_sprite_extractor.extract_units_sprites(). Cell N = the Nth unit in
RULES.TXT @UNITS order. B3-B9 are genuinely EMPTY placeholder cells (no source art).

## [UI] uptg06* dividers are STOCK art, not corruption; uptg06f-2 is loose-only (2026-07-05)
The dashed/hatched gold border dividers (uptg06b/h) are BYTE-IDENTICAL to the stock art in
pic555.zfs (verify with patch_ctp2_images.extract_rim_entry_tga_bytes) — authentic CTP2 UI,
not corruption. `patch_ctp2_images.py --base-only` regenerates exactly these. **NEVER remove
loose `uptg06f-2.tga`**: it is a copy NOT present in the zfs (LDL ctp_template.ldl references
it by name) — removing it = "Unable to find uptg06f-2.tga" launch error. GAP: validate_all_
surfaces.py has NO surface for LDL/UI-texture references; that class of missing-file is
currently unvalidated.

## [AI-CRASH — CONFIRMED + FIXED] Turn-0 goal-scheduler crash = negative settler need (2026-07-05)
The intermittent turn-0 `0xC0000005` (fault in `Scheduler::Scheduler` / `Goal*` / Governor,
NO SLIC frames -> SLIC/sprite changes exonerated) is CONFIRMED via a captured stack trace.
- **Trigger** (civ3log, Governor.cpp@3174): `Best settler unit: Peasants needed: -2, max: 0,
  current: 2`. The AI holds its 2 starting peasants; a strategy with `SettlerUnitsCount 0`
  yields `needed = 0 - 2 = -2`, and CTP2's goal scheduler underflows on the NEGATIVE need.
- **MoM-specific because**: peasants are `UNIT_CATEGORY_SETTLER` (Units.txt) AND the universal
  starting unit (UNIT_BUILD_LIST_LAND_SETTLER = { UNIT_PEASANTS }). So every AI starts with
  "settlers"; any strategy wanting fewer than the starting peasant count underflows. Base AE
  doesn't hit this (its settler is a separate, non-starting unit). Intermittent = only some
  map seeds/strategy assignments put an underflowing strategy in play at turn 0.
- **Fix**: raised every `SettlerUnitsCount < 2` to 2 in strategies.txt (lines 675, 1963, 3818).
  With the AI already holding 2 peasants, `needed = 0` (not negative) -> no underflow; and with
  `MaxSettlerBuildTurns 0` on those strategies, no actual expansion-behaviour change.
- **Verify**: intermittent, so test SEVERAL fresh new games. Workaround if a seed still slips:
  load a save (bypasses turn-0 AI init). The old "guaranteed WARRIOR_CODE" hypothesis is
  superseded — the AI does not even get WARRIOR_CODE (DiffDB 100/0) yet still crashed; the
  settler-need underflow is the real cause.

## [CRASH-DIAGNOSIS — TOOLING] In-game crash traces were symbolized against a STALE map (2026-07-09)
Every in-game "Exception Stack Trace" resolves addresses via `<exedir>\ctp2-dbg.map`
(DebugCallStack_Open). `run-ctp2-dbg-crashcapture.ps1` staged exe+pdb+dlls but NOT the
map, so the deployed map (5/26) lagged the exe (5/28) and **every symbol name in every
crash trace since was fiction** — the addresses were real (verified: WER `Exception
Offset 00152ca8` + base 0x00400000 == trace frame[0] 0x00552ca8; no ASLR rebase).
- **Consequence**: the b8161ec "turn-0 AI goal-scheduler crash (negative settler need)"
  diagnosis was built on bogus symbol names and is UNVERIFIED; the crash recurred 7/09.
  Only civ3log DPRINTF lines (file@line) were trustworthy in those captures.
- **Fix**: script now stages `ctp2-dbg.map` in lockstep with the exe (Get-OverlaySources).
- **Technique**: to re-symbolize any old trace, parse "Publics by Value" from the
  build-matched map and take the greatest symbol address <= each frame address.

## [CRASH - SITE CONFIRMED, CAUSE OPEN + GUARDS] Turn-0 0xC0000005 is a UI blit, not AI (2026-07-09)
Re-symbolized, the 7/09 crash is `aui_Blitter::Blt16To16+0x438` under
`ProgressWindow::StartCountingTo -> aui_UI::Draw -> ... -> aui_ImageList::DrawImages`
(the InitProgressWindow redraw during load; the AI log lines were merely last-logged).
- **FALSIFIED detour (do not repeat)**: the loose 120x120 desc=0x21 TGAs
  (`uptg20e.tga`/`uptg20e2.tga`/uptg06a-i, commit be124b9) looked like generated
  placeholder "impostors" shadowing zfs art - they are NOT. They are byte-identical
  (sha1-verified) extractions of the archive's .rim entries, produced by
  `patch_ctp2_images.py --base-only`; `uptg20e` really is a 120x120 tiling pattern and
  desc=0x21 (top-origin) is that pipeline's intended TGA form. They are REQUIRED loose
  because the archive stores `.rim`, not `.tga` - the launch script preflight enforces
  their presence and blocks launch without them. A deletion sweep was reverted in full.
- **Actual cause: still open** (intermittent; valid data was present on both crashing
  and working runs - suspect state-dependent, e.g. the aui_SDLSurface logical-size vs
  physical-buffer mismatch when a surface wraps the screen SDL_Surface with
  takeOwnership=FALSE, aui_sdlsurface.cpp:26-60).
- **Instruments installed** (H:\Games\civctp2): `DrawImages` skips + DPRINTFs
  NULL/degenerate image surfaces; `Blt16To16` refuses blits whose rects exceed the
  surface's PHYSICAL allocation (rows*Pitch vs Size) and DPRINTFs full geometry. With
  the map now staged fresh, the next occurrence self-identifies in civ3log instead of
  crashing.
- **Validator**: surface 9a = NEW dangling ldl-texture refs vs `ldl_texture_baseline.txt`
  (stock ships ~256 dangling refs that never load - absolute checks drown in noise);
  surface 9b = truncated/short-payload loose TGAs (desc byte is NOT a corruption signal).

## [CRASH-vs-FUGLY TRADE] aui_Window::Resize Draw-suppression reintroduces fuglies (2026-07-10)
The dead-buffer UI-blit crash (Blt16To16/TileBlt16To16 AV during CityControlPanel
construction, via ctp2_DropDown::AddItem -> SetWindowSize -> aui_Window::Resize) was first
"root-fixed" by gating the Draw() at the end of aui_Window::Resize behind
`if (g_ui->GetWindow(Id()))` — i.e. skip painting windows not yet attached to g_ui.
- **That REINTRODUCED fuglies**: CityControlPanel and its sub-surfaces are sized during
  construction BEFORE the parent window is registered in g_ui, so the guard suppressed their
  construction-time paint -> surface never painted -> rainbow static on the city-name/MAYOR
  banner. Same MECHANISM as the documented compound fugly ("surface never painted -> heap
  garbage"), but a NEW code trigger not in the data.
- **Diagnosis discipline that worked (after 3 false leads)**: verify the 3 documented DATA
  causes (DB double-load both forms, CRLF, TGA desc) are clean by BYTES (not `grep -c $'\r'`,
  which false-positived), AND confirm every engine guard logged 0 activations. When all data
  is clean and no guard fired, the culprit is the one change that alters rendering WITHOUT a
  log line — here, the Resize Draw-suppression.
- **Correct fix**: revert to unconditional Draw() in aui_Window::Resize; contain the actual
  dead-buffer crash with the SEH handlers inside Blt16To16/TileBlt16To16/DrawImages, which
  fail only the faulting blit rather than suppressing a whole paint. SEH had 0 hits the run
  the fugly appeared — proof the suppression was unnecessary for that run yet still corrupted.
- **Rule**: never fix a paint-time crash by SKIPPING the paint at a construction/resize choke
  point; contain it at the faulting blit. Skipping a paint = a fugly by another name.

## [FUGLY — 4th cause] Sizable-static name banner: transparent-cap surround unpainted (2026-07-11)
After the compound DB/TGA/CRLF fugly (all clean) AND after reverting the aui_Window::Resize
Draw-suppression (which fixed the LARGE-area banner static), a RESIDUAL rainbow static
remained on the control-panel unit/city NAME banner ENDS (the scroll end-caps).
- **Not a regression**: proven by 0 blitter-guard hits every run + the fact that engine
  changes only affect FAULTING/SKIPPED blits, so successful blits render byte-identically
  with or without them. Pre-existing; the crash fixes merely let the game run to show it.
- **Root cause**: the name banner is a `CTP2_STATIC_IMAGE_SIZABLE` (ctp2.ldl/controlpanel.ldl:
  left cap `uppd02ax` + stretched center `uppd02bx` + right cap `uppd02dx`, numberoflayers 2,
  NO pattern). The cap images are chromakey-transparent; the transparent surround around the
  cap art is never painted, so it shows uninitialized surface memory as static. This is the
  SAME documented mechanism ("fill blits transparent -> surface never painted -> heap garbage")
  as TGA cause #2, but a NEW trigger in the engine render path, not the data. Cap textures are
  zfs-stock (no loose desc fix possible).
- **Fix** (ctp2_Static::DrawThis): for a `m_multiImageStatic` with no pattern, draw the CENTER
  (parchment) segment across the FULL control rect BEFORE the caps/layers draw
  (`DrawThisStateImage(STATIC_IMAGE_CENTER, surface, &rect)`). The caps' transparent surround
  then shows the scroll texture instead of heap garbage. In-game proven clean.
- **Rule**: "fuglies are compound / a partial fix still shows static" (2026-07-04 lesson)
  extends to ENGINE causes too, not just the 3 data causes — verify the render path when all
  data surfaces are clean and no guard fired.

## [FIXED] Advance icons: 388 TGAs, only 11 distinct images (2026-07-13)
- **Symptom**: Alchemy/Alphabet/Animism (and whole groups) show the SAME image in the GL;
  the image itself is a Civ2 *building* picture, not an advance portrait.
- **Root cause (two layers)**:
  1. `momjr_csv/advances.csv` `cell_index` held 11 category-bucket values, not per-advance
     slots — every advance in a bucket sliced the same cell.
  2. Deeper: the atlas config's `advances -> Improvements.bmp` premise is WRONG. Visual
     inspection of `H:\Games\civ2\MOMJR\MOMJR\Improvements.bmp` proves it is building/wonder
     art; `Icons.bmp` is UI chrome. **Civ2 MOMJR has NO per-advance portraits at all** — the
     extractor pipeline for advances slices art that was never advance art.
- **The real design intent** lives in the momjr CTP2 port's own gamedata
  (`H:\Games\ctp2\mom\mom\Scen0000\default\gamedata\uniticon.txt` + `mom_uniticon.txt`):
  advances map to CTP2 GL pictures (CM2_UPAP*/UPAP*/UPSS*... mod-pack art). Only 129 of
  those 482 files exist locally (+63 recovered from the extracted Cradle/AoM dirs).
- **Fix applied** (data-only, uniticon.txt image fields only; Gameplay/Historical refs
  untouched): tiered assignment — (1) momjr mapping where the art file exists (67),
  (2) base `advanceicon.txt` art by exact name, loads from zfs (49), (3) remaining 109
  round-robined over a 98-image distinct pool (unused base CA*F + loose CM2/UP*L) so no
  two alphabetically-adjacent advances share an image (1 residual pair: NANO_MACHINES/
  NANO_WARFARE). Backup: scratchpad/uniticon.txt.bak.
- **Crash guard**: all 63 recovered loose TGAs arrived desc=0x01 — the documented GL
  SourceList crash trigger (see 2026-07-08 entry) — normalized to desc=0x00 before launch.
- **Rule**: for MoM advances there is no slicing source; per-advance art comes from the
  momjr uniticon mapping + base advanceicon fallback. Do NOT regenerate ICON_ADVANCE_*.tga
  from Improvements.bmp.

### CORRECTION to the entry above (same day) — fix was re-scoped after user regression report
The tiered rewrite of ALL 225 uniticon entries was **over-broad**: the generated MoM
category art was correct/liked for most advances (user: "I had most of the correct ones
before, now I'm missing most and only have old ones!" — e.g. Chaos Magic regressed to a
CTP2 power-plant picture). Final state: `uniticon.txt` restored from backup, then ONLY the
27 advances sharing Alchemy's md5-identical image were repointed — momjr loose art where
available (Alchemy→CM2_UPAP010L), base advanceicon exact-name (Writing→CA011F), remainder
round-robined over the other 10 MoM-generated looks (MoM aesthetic preserved, adjacency
dupes broken). **Rule: fix the complained-about set, nothing more — "correct" is what the
user sees, not what a tier ladder scores.** The desc=0x00 normalization of the 63 recovered
loose TGAs stands (GL-crash guard).
