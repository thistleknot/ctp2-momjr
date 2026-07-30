# Changelog

MoM (Masters of Magic) scenario for Call to Power 2. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Entries are grouped by
the dimension they touch, because the control plane is organised that way.

Only player-visible or tool-contract changes are listed. Byte-level regeneration
noise is not a change.

---

## [3.2.0] — 2026-07-29 — the ladder starts mattering, and the AI starts casting

**Minor.** Additive: 3.1.1 saves load unchanged and still make sense. Nothing is
renamed, repriced, or deleted — but the AI now spends a resource it previously
banked forever, so a save carried across this line will play differently from here.

### Fixed

- **Every sphere summoned exactly one creature, forever.** `MomSummonOrderTick`
  resolved the 75-mana summon through five CONSTANTS, one per player index.
  Nature was hardwired to `UNIT_WARBEARS` — **cost 4, the cheapest of its 13
  units** — so researching `NATURE_LORE → ADEPT → MAGE → WIZARD → MASTER` changed
  nothing about what mana bought, and 12 Nature creatures were unreachable by
  summoning. The six-rung ladder that 2.0 and 3.0 built was decorative *for the
  mod's headline feature*. Reported in play 2026-07-28.

  The summon now rolls, weighted, over every rung the caster has unlocked: the
  newest rung takes the widest band and older rungs keep a floor, with the bands
  cut from the *count* of unlocked rungs so adding a rung cannot leave a dead one.
  A fresh Nature tribe already rolls over Centaurs / Elven Archers / Warbears with
  no research at all. Heroes are excluded — unique tribe leaders, not summonable
  troops — via a new `unit_roles.heroes` roster in `mod_policy.json`.

- **The AI accrued mana every turn and could never spend a point of it.**
  `MomMagicPoolTick` accrues for all five sphere players, human or not, but
  `MomSummonChoice[p]` — the only thing that authorises a summon — was set in
  exactly ONE place: a **button body**, which only a human click reaches. So every
  AI tribe banked to the 100 cap and sat there for the whole game, and the ten
  `IsHumanPlayer` guards in the magic modules only ever *suppressed* output for
  the AI rather than substituting an action. The mod's headline system was a
  human-only privilege — and part of why two long headless runs ended when the
  script ran out rather than when the game did.

- **Summon result messages no longer name the creature.** Naming was safe while
  the summon was fixed; "Warbears lumber out" while a Great Wyrm stands in the
  capital is worse than saying nothing, and SLIC can only interpolate plain
  `{scalar}` — a unit index is not a name.

### Added

- **`mom_ai_magic.slc` — the AI's magic brain.** One `BeginTurn` handler, bound
  `p >= 1 && p <= 5` first and `!IsHumanPlayer` guarded, running a rule ladder over
  war state (`AtWarWith`) and pool level with `Random(100)` breaking ties so two AI
  tribes do not act identically. It pays the **same** 75/50 prices the human pays,
  and reuses `MomSpawnSphereUnit` so its summons get the same occlusion-safe
  placement instead of stacking on the capital tile. No `Message()` on this path —
  a messagebox aimed at an AI player is the message-queue overflow AV.

- **`mom_summon.slc` (generated) — rung tracking and the weighted roll.** The rung
  is read back off each unit's *existing* gate advance, so the summon table and
  `mom_gating.slc` cannot disagree about which rung owns a creature.

- **Gate 26 — `tools/gate_ai_magic.py`.** Asserts behaviour rather than reference
  integrity, because both defects above were invisible to every existing gate:
  nothing dangled. Checks that no sphere can roll another's creature or a hero,
  that every sphere offers more than one creature, that every ident is a live
  block, that the AI handler is bounded and AI-only, and that every roll band
  terminates at 100. **Each of those six assertion classes was proven to fire
  against a deliberately broken file before the fix was accepted.**

### Notes on what this cost to get right

- **`HasAdvance` was rejected despite 700+ uses across the other mods.** All of
  them pass a bare `ID_ADVANCE_*`, and the engine **silently auto-creates unknown
  symbols** — an unresolvable name returns a permanent *false* rather than erroring
  — while `validate_all_surfaces.py`'s surface-7 regex is anchored `\bADVANCE_` and
  cannot match inside `ID_ADVANCE_`. Nothing in the repo would have caught the
  typo. Rungs are tracked by comparing `value[0] == AdvanceDB(...)`, which is
  covered.
- Two self-inflicted defects were caught by instruments, not review: `;` is not a
  comment in a string table (`#` is) and killed the load until the native-dialog
  error channel named the exact line; and rung 0 owns no creature, so every tribe
  at game start would have summoned *nothing* while the arm still looked
  affordable — fixed at both the root mapping and with a floor in the roll.

### Known open — what is NOT proven in a running game

Both features below are verified **statically** (generated pools, seven gate
assertions each proven against a broken file) and the SLIC layer is verified to
load and run clean across 25 headless turns with **zero SLIC errors**. Neither
has been observed happening on screen.

- **Summon variety is unproven in-game.** Three probe attempts failed, all on one
  root cause, all recorded in `tools/uiwalk/probe_summon_variety.py`'s parked
  header: a hardcoded arm coordinate was swallowed by a `Message()` window
  stacked above the alertbox; dismissing that at the measured close point opened
  the OPTIONS menu instead, because the constant is only valid while a box is up;
  and the frame-measuring third attempt found `0 buttons` because the MAGIC
  STATUS box never opened at all in that driver. Its fall-through clicks panned
  the map once per attempt — the operator watched the view scroll in a loop. The
  blocker is upstream of the click (`j` not raising the menu from that driver,
  while the same keypress works from a steps JSON), so it is a harness defect,
  not a mod one.
- **AI mana spending is not observable at all** by this harness: the pool renders
  for the human alone, and the harness reads pixels only.

---

## [3.1.1] — 2026-07-29 — every wonder message printed its name twice

**Patch.** No rule, cost, age, or save-format change — 3.1.0 saves load
unchanged. A string the engine has always looked for was simply absent, so a
message that was already supposed to read correctly now does.

### Fixed

- **`Bardic CollegeBardic College`.** Every wonder message rendered the wonder's
  name twice, concatenated with nothing between — seen in the wild on the
  rival-wonder warning. `#ARTICLE` is not a computed article: it is an
  **ident-suffix lookup**, and the engine resolves
  `{wonder[0].name#ARTICLE}` by reading `<IDENT>_ARTICLE` out of `gl_str.txt`,
  falling back to the *name* when the key is missing. Eleven messages in
  `info_str.txt` are written as two adjacent interpolations —

  ```
  WONDER_STARTED "... has begun work on {wonder[0].name#ARTICLE}{wonder[0].name}."
  ```

  — so one missing key doubles the name in all of them: `WONDER_BUILT`,
  `WONDER_BUILT_QUEUE_EMPTY`, `WONDER_STARTED`, `WONDER_STOPPED`,
  `WONDER_ALMOST_FINISHED`, `WONDER_COMPLETE_OWNER`, `WONDER_COMPLETE_ALL`,
  `WONDER_DESTROYED`, `WONDER_OBSOLETE`, `NANITE_DEFUSER_ELIMINATES_NUKES`,
  `PROTECTED_FROM_CONVERSION_BY_WONDER`. The base tree ships 30 of these keys and
  wonders are the only database that uses the modifier; MoM's `gl_str.txt`
  overrides the base file and shipped **zero**.

  **Two independent lanes were broken, and fixing either alone leaves the bug.**
  `_prune_gl_strings` deleted every *inherited* key, because a trailing
  `_ARTICLE` never matched a keep-id — so `WONDER_PYRAMIDS_ARTICLE` read as an
  orphan, and anything written later would have been pruned straight back out.
  Meanwhile the wonder writer never emitted MoM's *own*. The pruner now
  normalises `_ARTICLE` to its owning ident, exactly as it already did for a
  leading `DESCRIPTION_`, and the writer derives the article from the display
  name: `""` when the name is already definite or possessive, `"the "`
  otherwise. That reproduces the base game's own convention
  (`WONDER_THE_APPIAN_WAY_ARTICLE ""`, `WONDER_ARISTOTLES_LYCEUM_ARTICLE ""`,
  `WONDER_PYRAMIDS_ARTICLE "the "`). Derived rather than authored in a csv
  column, so renaming a wonder cannot desync the two.

  Now reads *the Bardic College*, *the Guild of Legends*, *The Parthenon*,
  *Gaia's Shrine*.

### Added

- **Gate 25 — `check_wonder_articles`.** Asserts the *result* rather than either
  lane: every `WONDER_*` block has an article key, and no article key outlives
  its wonder. Proven against the unfixed tree **before** the fix was written —
  28 FAILs, one per wonder. A gate that has never rejected anything is not
  evidence.

### Known open

- Five wonders still display a literal `X` — `Xlighthouse`, `Xapollo Program`,
  `Xstatue Of Liberty`, `Xwomens Suffrage`, `Xcure For Cancer`. Traced to civ2
  source `Rules.txt:251,267,269,273,275`, where MoMJR marks them
  `xLighthouse, 20, 0, no,` — the `x` name prefix *and* the `no` never-buildable
  sentinel. They are correctly disabled in the scenario (`EnableAdvance ==
  ObsoleteAdvance`, no effects, absent from every AI build list, and gate 24
  already enforces that), so this is cosmetic residue on the Great Library page
  only.
- The fix is verified statically, not on screen. The message fires only when a
  rival starts a wonder, which cannot be triggered on demand, and the harness
  reads pixels only.

---

## [3.1.0] — 2026-07-27 — the victory nobody could reach

**Minor.** 3.0.x saves load unchanged and every rule, cost and age is untouched.
It is not a patch because it restores a whole system rather than repairing one
value: the AI can now build wonders at all, which means the scenario's win
condition exists for the first time.

### Fixed

- **No AI player could build any wonder, so the game had no winner.** All seven
  lists in `aidata/WonderBuildLists.txt` shipped empty. The reason was sound —
  an empty scenario override stops the engine falling back to stock aidata,
  whose wonder idents do not exist in the MoM WonderDB and would dangle — but
  the engine picks wonders for an AI goal *only* from these lists. Empty meant
  none of the 23 live MoM wonders was ever a candidate. And since
  `EndGameObjects.txt` makes the victory *hold `WONDER_RUNE_OF_RULERSHIP` for 10
  turns*, an AI-only game had **no reachable terminal state except the year
  2300**. The lists are now derived from the generated `Wonder.txt` — which
  keeps the original guarantee, because every ident is read out of the
  scenario's own database — and each wonder is filed by its own effect lines, so
  it re-files itself when its effects change instead of drifting from a
  hand-typed roster. 23 live wonders across 7 lists; the 5 self-obsoleting `X*`
  stubs are excluded.

- **A rival's diplomatic proposal froze the turn loop indefinitely.** A tribe
  demanding tribute opens a modal `DipWizard` window, and END TURN never fires
  again. The headless harness now rejects it every turn. Reject, never accept:
  an unattended playthrough must not hand over gold.

### Verified

- **The scenario now ends.** A headless playthrough on the fixed scenario
  reached a terminal state — `DEFEAT` at **turn 390 / 1505AD**, score 4380 — the
  first time any run has ended because the *game* ended rather than because the
  script ran out. Attribution is by controlled experiment, one variable: the same
  walk against a scenario whose wonder lists were emptied again played
  **420/420 turns with no endgame window and no stalls**. Populated lists end the
  game; empty lists do not. (One run per arm, different maps — the direction is
  the prediction, not a rate.)

- **Where the game actually ends on the clock**: `DiffDB.txt` TIME_SCALE runs
  20 yr/turn to turn 150, then 10, 5, 2, and 1 from turn 600, so
  `END_OF_GAME_YEAR 2300` falls at **turn 1000**. Turn 200 is 500BC and turn 600
  is 1900AD — no 200- or 600-turn script could ever have ended the game on time.

### Added

- **Gate 24, `check_wonder_build_lists`.** Asserts that every ident in the AI
  lists is a real `Wonder.txt` block, that no self-obsoleting stub is offered,
  that every live wonder appears in at least one list, and that the wonder named
  by `EndGameObjects.txt` is among them. Validated against the pre-fix scenario
  first, where it produced **24 failures** — a gate that has never rejected
  anything is not evidence.

- **`tools/balance_report.py`** — the first check in this repo that asks whether
  the mod is *fair* rather than whether it is *legal*. Cost-efficiency outliers
  on a median/MAD band over log(power/cost), sphere parity, and a stat-twin
  check for units with an identical combat line at very different prices.
  Reports; does not gate.

- **`tools/uiwalk/detect_endgame.py`** — tells an ENDING apart from a FREEZE.
  Both produce identical zero-delta frames, so `decode_run.py` reported the
  first real ending this project has ever reached as its worst failure class
  (`STALLED at 117 checkpoints`). This reads the `VictoryWindow` title strip
  instead. Validated both directions: it finds the ending at turn 390, and
  reports no ending for the run that genuinely froze.

- **`tools/uiwalk/make_full_game.py`** — the full-game walk is generated from a
  turn count instead of being a hand-maintained 1553-element JSON pinned at 200
  turns. Reproduces the verified 200-turn file body-identically.

### Known open

- **All 55 units have `MaxHP 10`.** The civ2 source spreads hp across `1h..6h`;
  the port flattens it, so durability differentiates nothing. This is the
  largest dimension lost in the conversion and is **not** fixed here.
- `UNDEAD_DRAGON` costs 1200 against `STORM_DRAKE`'s 4000 for an identical
  60/30/10/2 line. Faithful to the civ2 source, which prices it 3 where Storm
  Drake is 14 — an upstream MoMJR authoring bug, carried correctly.
- `INFERNAL_DEVICE` delivers ~15x the median combat value per shield.
- Sphere totals span 2.56x (chaos 1165, death 455); rosters span 1.86x.
- `ADVANCE_RUNE_LORE` unlocks the victory wonder at **AGE_TWO of seven** and is
  ungated, so the win is available before most of the magic ladder exists.
- `BattleViewWindow.ExitButton` still does not close the battle view.

## [3.0.1] — 2026-07-27 — the diplomacy screen every tribe could not open

**Patch.** No rule, cost, age, or save-format change — 3.0.0 saves load
unchanged. One shipped art reference was wrong for all five tribes, and the
harness that proves a playthrough could not survive its own success.

### Fixed

- **Every tribe's diplomacy parchment pointed at art that does not exist.**
  `civilisation.txt` shipped `Parchment` 42–46 for the five tribes.
  `dipwizard.cpp:2673` builds the diplomacy background filename at *runtime* as
  `UPDG%02d.tga` from that field, so there is no database reference to dangle
  and no existing gate could see it. A regex scan of every
  `ctp2_data/**/*.zfs` returns exactly `updg01`–`updg41` plus `updg99` — so all
  five tribes resolved to a missing Targa, i.e. a native load-error modal that
  stops the engine's message pump. Fixed in the control plane
  (`tools/momjr_csv/players.csv` → 3 / 7 / 19 / 31 / 39).

  This is the failure mode worth remembering: the symptom is a frozen frame
  with nothing in the console, because the modal *is* the freeze. It survived
  three releases for exactly that reason.

### Added

- **Gate 23, `check_parchment_range`** — every `Parchment` must be in 1–41 or
  99. Written, then run against the known-bad `civilisation.txt` **before** the
  fix was generated; the first version used a `^(\w+)\s*\{` block regex and
  *passed* the bad file, because block headers here carry a trailing `#N` and
  open the brace on the next line. Rewritten line-wise and re-proven at 5
  FAILs. A gate that has never rejected anything is not evidence.

### Harness

Ships in `tools/uiwalk/`; no scenario data touched.

- **The per-turn ping lost its button.** An injected `enter` only advances the
  turn if a mouse message reached the engine — but it does not need a *button*.
  The old ping was a real click on "inert" top-bar chrome at a pinned
  `(600, 6)`; once a DPI-scaled display became primary, that pixel was no
  longer inert and three consecutive runs died `0xC0000005` on the first click.
  Replaced with a button-free `WM_MOUSEMOVE` (`hover` verb) aimed by `fx`, a
  fraction of the live client width. **Aim derived from the live frame is safe;
  aim pinned to a pixel is not.** Result: **200 turns, 4000BC → 150AD**, five
  times the previous 40-turn ceiling, zero stalls across 100 checkpoints.
- **`decode_run.py` cried STALL on a healthy run.** Its 2000px threshold was
  fitted on five-turn checkpoints; applied per-turn, a camera parked over
  unexplored ocean legitimately redraws only the build counter (~300–1200 px).
  The bug the decoder exists to catch produced *byte-identical* frames, so the
  bar is now 100. A threshold carries the sampling density it was measured at.
- **Shots are sorted numerically.** `100_turn190.png` sorts before
  `66_turn122.png` as a string, so the first run past 99 checkpoints silently
  reported its last turn as 188 and compared its tail out of order.
- **Teardown kills the game on the abort path.** `kill()` derived the PID from
  a window handle that is already dead when a run aborts, so it terminated
  nothing and left a window on screen. The PID is now captured at window
  acquisition.

### Known open

Both harness-side, neither blocks a full playthrough:

- `BattleViewWindow.ExitButton` does not close the battle view, though the path
  matches `battleview.ldl:149`. Turns still advance; the frame stays occluded.
- The SLIC alertbox is never dismissed — one message persisted from turn 124
  through turn 200.

---

## [3.0.0] — 2026-07-27 — the Renaissance cap actually applies

**Major.** 2.0 announced "mundane tech ends at the Renaissance." It did not. The
cap was written, shipped, and enforced nothing — so 3.0 is the release where the
2.0 headline becomes true. Ages 5–7 are now magic-only, verified in-game.

The version bump is not ceremonial. Five advances change age, and one changes
cost by 60% (Ecognomics 3900 → 2425), so a 2.x research plan no longer costs what
it did and a 2.x save references the old bands.

### Fixed

- **The Renaissance cap was dead code.** `_relayout_advance_ages` decided
  "is this advance mundane?" with `ident in momjr` — i.e. "did MoM author it?"
  MoM authored essentially the entire tree, so that test was true for nearly
  every ident and the mundane branch never ran. **Ecognomics, Sanitation, Sea
  Lore, Greater Fauna Lore** (AGE_FIVE) and **Sea Mastery** (AGE_SIX) had drifted
  above the cap on depth banding alone. The discriminator is now a derived
  *magical closure* — is this a sphere-ladder rung, or does it transitively
  require one — which is also self-consistent with the no-advance-below-its-
  parent guarantee, since a mundane advance's prerequisites are mundane by
  construction. Post-fix distribution: AGE_ONE 35, TWO 43, THREE 19, FOUR 28,
  FIVE 5, SIX 7, SEVEN 7. Every one of the 19 advances above AGE_FOUR is
  magical.
- **`mom_sphere_home.slc` was written when its policy was off.** The emit block
  sat nested under the age-re-layout branch, so any run that re-aged anything
  wrote a SLIC file citing five `ADVANCE_HOME_*` that only exist when
  `sphere_home_exclusivity` is enabled — five dangling advance refs, the
  mom-db-error crash class. The sever pass ran *earlier* in the same run, so the
  mod only looked self-healing because a second generator run cleaned up after
  the first. Now guarded on the policy flag; one run is clean.
- **`mom_audit.py` reported a phantom missing building.** `IMPROVE_X` was
  harvested out of a documentation comment in `mom_func.slc`. SLIC text is now
  comment-stripped before idents are harvested. Audit: 65 PASS / **0 FAIL**.

### Added

- **Gate 22 — `check_renaissance_age_cap`** in `validate_scenario.py`. Reads the
  *shipped* `Advance.txt` and re-derives the magical closure independently of the
  writer, so the gate and the generator cannot agree on the same mistake. Control
  run against the pre-fix artifact: 5 FAILs, matching the 5 known strays.
- `ADVANCE_ECOGNOMICS_HISTORICAL` prose in `gl_descriptions.csv` (it was a stub).
- `tools/uiwalk/steps/newgame_gl_age_cap.json` — headless confirmation walk.

### Decided (previously open, now closed)

- **Ecognomics is native MoM, not a CTP2 import.**
  `H:\games\civ2\MOMJR\MOMJR\Rules.txt:107` — `Ecognomics, 4, 1, Uni, Ban`,
  i.e. University + Banking, exactly what the Great Library now shows. It stays.
- **`FUTURE_TECHNOLOGY` at AGE_SEVEN is correct.** Also MoM-native
  (`Rules.txt:174`), and its prerequisites are `DEATH_WIZARD` + `CHAOS_LORE`, so
  it is magical by closure, not a stray modern leftover.
- **`PrerequisiteBuilding` chains stay at 0.** Stock CTP2 ships 49; MoM ships
  none. This is faithfulness, not a gap: civ2's `@IMPROVE` record has four fields
  — name, cost, upkeep, *advance* prereq — and no building-prerequisite concept
  exists in the source at all. Not a todo.

### Verified

Headless, in-game, Great Library STATISTICS pane (run `20260727-082211`):
Ecognomics **Cost 2425 / Age 4**, Sanitation 1825/4, Sea Lore 2735/4,
Sea Mastery 3095/4, Greater Fauna Lore 2735/4. Plus byte-stable double
generator run, `validate_scenario` all gates, `gate_faction_gating` 0/71
violations, `gate_gl_descriptions` 784/784, `backcast_slic --check` current.

---

## [2.0.0] — 2026-07-26 — faction gating + age re-layout

**Major.** The five tribes are now distinct in the data, not just in SLIC's
player index, and the tech tree ends at the Renaissance with the Masters of Magic
ladder spread across Ages 5–10.

The version bump is not ceremonial — 2.0 breaks compatibility three ways. Saves
from 1.x reference 113 advances, 6 governments and 17 tile improvements that no
longer exist. Any downstream edit to `units.csv` or `improvements.csv` needs the
new `sphere` column. And content that was buildable by everyone in 1.x is now
gated per tribe, so a 1.x build order may no longer be legal.

Planned in
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
