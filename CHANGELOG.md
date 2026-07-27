# Changelog

MoM (Masters of Magic) scenario for Call to Power 2. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Entries are grouped by
the dimension they touch, because the control plane is organised that way.

Only player-visible or tool-contract changes are listed. Byte-level regeneration
noise is not a change.

---

## [Unreleased] — faction gating + age re-layout

The five tribes are now distinct in the data, not just in SLIC's player index,
and the tech tree ends at the Renaissance with the Masters of Magic ladder spread
across Ages 5–10. Planned in
`~/.claude/plans/synchronous-petting-naur.md`; postmortem in `PLAN.md`.

### Added

- **`mod_CanPlayerHaveAdvance` / `mod_CanCityBuild{Unit,Building,Wonder}`** —
  generated `scen0000/default/gamedata/mom_gating.slc`, `#include`d from
  `scenario.slc`. Because `mod_CanPlayerHaveAdvance` sits inside `GiveAdvance`,
  one function fences research, huts, conquest, spy steal, diplomacy and the
  Great Library. Generated, never hand-edited.
- **`sphere` as a first-class control-plane column** on `units.csv` and
  `improvements.csv` (`life|nature|sorcery|death|chaos|neutral`), plus
  `unit_factions.csv` as the reviewable curated taxonomy. In the data plane
  `sphere` means *who may build it*; in SLIC it means *who gets a bonus* — a
  neutral building with a per-sphere bonus is correct, not a contradiction.
- **`tools/gate_faction_gating.py`** — 9 assertions over the ladder, the sphere
  matrix and the generated SLIC. Assertion 5 (every ident in `mom_gating.slc`
  exists in the generated DB) is the one that matters: a typo there is a silent
  no-op, the worst failure mode available. Registered in `validate_scenario.py`
  as `check_faction_gating`.
- **Gate 11, `check_effective_tree_advance_refs`** — scans the tree the engine
  will *actually load* (scenario override else base) for dangling references
  across 13 record families. See the DB-Error section below.
- **Buildings and wonders now carry a sphere**, so tribe identity extends past
  units.

### Changed

- **Age layout.** Age 1 ancient mundane + the two magic roots; Ages 2–4
  classical/medieval/renaissance mundane paired with `*_MAGIC` / `*_LORE` /
  `*_ADEPT`; Ages 5–7 `*_MAGE` / `*_WIZARD` / `*_MASTER`; Ages 8–10 the MoM
  capstones. **Mundane tech ends at Age 4.** Age is derived from the ladder rung,
  so a rename cannot desync it.
- **Prereq rewrite.** A unit or improvement with a real sphere is re-anchored
  onto that sphere's rung, tier from existing cost banding; `neutral` rows keep
  their prereq. Without this the re-layout moves nothing — content follows its
  enabling advance, so 20 of the 33 Age-1 units were only ever going to leave Age
  1 by being re-anchored. The pass runs after the unit mask and cost retune and
  before `gl_descriptions.apply_descriptions`, which quotes the prereq in derived
  prose.
- **SLIC sphere matrix completed.** Chaos gained its four missing branches
  (grant-building, milestone building + unit, build-burst); Death gained
  `MomCountDeathFoci`. `mom_msg.slc` spawns now use the occlusion-safe placement
  from `MomSpawnSphereUnit` instead of the raw city tile.
- **`p <= 5` bound** added at the eight lower-only guard sites. It cannot fire
  today — `civilisation.txt` ships only BARBARIAN plus the five tribes — which is
  exactly why it is there for whoever adds a civ next.
- Four stale `slic_purpose.json` descriptions corrected; `slic_inventory.csv`
  gained a `sphere` column so these gaps are machine-visible next time.

### Removed

- **113 advances** (71 modern, ~30 `*_WAW` junk, 11 modern pollutants). Zero kept
  advances had a deleted prerequisite — the cut was clean at the tree level. All
  fallout below is downstream citation, not tree damage.
- **6 modern governments** (Communism, Corporate Republic, Democracy, Ecotopia,
  Fascism, Technocracy, Virtual Democracy). Anarchy, Monarchy, Republic and
  Theocracy survive, which is the correct set for a Renaissance cap.
- **17 industrial/modern tile improvements** (undersea everything, maglev, radar,
  air bases, hydroponic farms, listening posts, …). Basic infrastructure is
  untouched: Farms, Advanced Farms, Mines, Road, Railroad, Nets, Fisheries, Port,
  Fortifications, Trading Post and the five vegetation terraforms all remain.
- Authored HISTORICAL Great Library text for the deleted advances, pruned from
  `gl_descriptions.csv`.

### Fixed — the DB-Error modal class (all three, one root cause)

Every *"X not found in Y database"* modal traced to the same defect: **static
gates only inspected files the scenario overrides, but the engine loads the
base-tree copy of any gamedata file the scenario does not ship.** Deleting 113
advances and 17 tileimps turned every base-tree file citing a deleted ident into
a load-killing landmine that no gate could see.

| Modal | Base-tree file | Fix |
|---|---|---|
| icon lookup | `ADVANCE_NA` sentinel's fallback icon | restore `ICON_ADVANCE_DEFAULT` — the prune ate it because `ADVANCE_DEFAULT` is not a live advance |
| "Industrial Revolution not found in Advance database" | `Pop.txt` | re-anchor `POP_LABORER` → `ADVANCE_CONSTRUCTION`, `POP_MERCHANT` → `ADVANCE_TRADE` |
| "Listening Post not found in terrainimprovement database" | `aidata/ImprovementLists.txt` | re-anchor `IMPROVEMENT_LIST_MISC` → `TILEIMP_TRADING_POST` |

Re-anchor rather than delete — an empty AI list is an untested engine path.
Both fixes are generator passes (`_scrub_dead_advance_surfaces`,
`_scrub_dead_tileimp_surfaces`) that pull the base file into the scenario and
rewrite it, so they cannot rot.

Two traps that cost hours and are now documented:

- The engine prints the **display name**, not the ident, so grepping "Industrial
  Revolution" finds nothing.
- The engine **aborts on the first dangling reference only**, so launching the
  game discovers them one at a time at ~5 minutes each. Using the game as the
  scanner was the method defect; gate 11 replaces it with one read-only sweep.

Gate 11 needs two scopings to reach zero false positives: restrict to files the
engine genuinely parses (base `Improve.txt`, `endgame.txt`, `order.txt`, the
`*icon.txt` exports and `Units_{historic,release}.txt` all carry dead refs and
are inert — `uniticon.txt` is the sole runtime icon DB), and **strip `//`
comments before tokenising**, since `aidata/strategies.txt` lists seven deleted
governments entirely inside comments.

### Fixed — other

- `WONDER_GNOME_TREASURY` re-anchored to `ADVANCE_BANKING`; `NATURE_PRESERVE` to
  `ADVANCE_NATURE_MAGIC`; `ADVANCED_MINES` to `ADVANCE_ALCHEMY`; the seven
  terraform improvements onto the Nature ladder, which turns an orphan cleanup
  into a faction-identity win.
- `UNIT_SETTLER.ObsoleteAdvance` cleared.
- `assign_unit_factions.py` no longer reads a `source` column that
  `units.csv` never had — its `base`/`gated` split was degenerate. Dead
  `STARTER_COST` removed.
- `check_effective_tree_advance_refs` walked `scen.parents` upward instead of
  indexing a fixed depth. The fixed index assumed an absolute path, and
  `--scenario scen0000` is relative, so the guard returned early and **silently
  disabled the entire gate**. A gate that cannot fail is worse than no gate —
  always run the negative control.

### Verification

Generator exit 0 and byte-stable on rerun across `Advance.txt`, `Units.txt`,
`buildings.txt`, `ImprovementLists.txt`, `Pop.txt`, `mom_gating.slc`.
`gate_faction_gating` 71 targets / 0 violations; `gate_gl_descriptions` 784/784;
`validate_scenario --scenario scen0000` all gates. Negative control on the
unfixed tree returned exactly one failure — the reported bug — and zero false
positives. Headless boot reaches turn 1, 4000BC, no modal, no leaked processes.

### Known open

- **AI research thrash** unmeasured past turn 1. Denying an advance the AI has
  committed to may loop its selection rather than redirect it, and no SLIC hook
  observes AI goal-picking, so this needs a live game to ~turn 40.
- **`uiwalk.py` abort teardown** logs *"leaving it running"* instead of killing
  the process. It did not fire on the last run, but the path that leaked
  `ctp2.exe` processes is unchanged.

---

## Earlier work

Condensed from commit history; grouped by what broke rather than by date.

### Art and sprites

- **Unit sprite extent and anchor are one coupled bug** — anchoring on the pixel-
  mass centroid with extent at p85 makes units draw centre-mass. Changing extent
  without the anchor moves the unit off its tile. (`b6542ed`, `5f17ef4`)
- **Spearman missing from the map** — the engine reads *both* `GU%.2d.SPR` and
  `GU%.3d.SPR`; the builder wrote only one name. (`b212730`)
- **Icon over-zoom** — the extractor was a third, unaccounted producer of icon
  art. Uniform median==max across 55 files was the tell that a normalisation
  step, not source variance, was responsible. (`ca7ee5f`)
- `units.csv` gained an explicit `art_cell_index`; the old `cell_index` was live
  and wrong. (`f676469`)

### Pipeline and build

- **Buildings were all 1-turn builds** — the age-band cost rescale ran ~1300
  lines *before* the ingest that overwrites `buildings.txt`. Pass ordering, not
  arithmetic. (`b94b679`)
- **SLIC became a control-plane dimension**, flowing backward into the xlsx
  (one tab per dimension, cells holding real source). (`58d497f`, `4ff7b7d`)
- `mom.zip` is the **mod**, not the repo — the repo holds the code.
  (`770dbd8`)

### Magic and gameplay

- **Life could raise zombies** — summons are now gated to the caster's own
  sphere. (`b64eda1`)
- **Summoning priced at 75 mana**, with the pool accumulating instead of
  self-discharging. The old pool-overflow auto-summon had made the spellbook
  unaffordable by construction. (`8a9b1a3`, `f552582`)

### Harness

- **Alertbox arms are clickable** at the frame-measured centre — this retracts
  the earlier "posted buttons are lethal" claim. Dismissal aims at the
  last-declared arm. (`8b3c81d`, `783386f`, `d6baefb`)
- Headless steps that **observe** building turn counts in the Build Manager,
  rather than asserting against goldens. (`41b04d3`)
