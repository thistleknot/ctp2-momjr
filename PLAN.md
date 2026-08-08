# PLAN — Faction gating + age re-layout

Source plan: `C:\Users\user\.claude\plans\synchronous-petting-naur.md`.
This file is the live tracker. Amendments below supersede the plan text.

## Amendments in force

1. Historical civs removed — `civilisation.txt` ships BARBARIAN + the 5 tribes only.
2. All ten ages retained; MoM tech spread across them.
3. Item 7 is an **agent/self-driven recursive review**, not a script. `close_gating.py` CANCELLED.
4. Tech cap: delete the modern advances **and** the `*_WAW` junk advances outright.
   Mundane tech ends at Renaissance (Age 4); Ages 5+ are purely magical.
5. Tileimps: re-anchor where balance survives; basic infrastructure (farms) stays.
6. Buildings get a sphere too.

---

## Item 0 — verify `mod_CanPlayerHaveAdvance` is a true chokepoint — **DONE**

Battery passed: research, goody hut, diplomatic trade all logged. `theCity.owner`
resolves in a build hook. Seeding order clean.

## Item 1 — `sphere` as a first-class control-plane column — **DONE**

`sphere` added to `units.csv` and `improvements.csv`; `unit_factions.csv` written
as the reviewable taxonomy. Precedence: units.csv `sphere` > prior
`unit_factions.csv` edit > keyword inference. Hero tribes adjudicated by review
agents (the one authorized subagent dispatch; complete).

**Rejected from the plan:** dropping the four `r.get("source")` reads — that would
destroy SMM's taxonomy. Registering the CSVs in `export_mod_workbook.py` is a
no-op; `collect_csv_files` auto-discovers via `rglob("*.csv")`.

## Item 2 — prereq rewrite pass — **DONE**

Sphere'd units/improvements moved onto their sphere ladder rung. **The authored
rung wins over `cost_to_tier`** (memory `mom-authored-rung-beats-derived-tier`) —
the derived tier demotes every master summon.

## Item 3 — age re-layout + tech cap — **DONE**

**Measured deletion set is 112, not the plan's 113**: 71 base advances in
AGE_FIVE..AGE_TEN + 30 `_WAW` + 11 AGE_THREE modern pollutants. Keep = 143.
Zero kept advances have a deleted prerequisite.

Age layout is **derived**, not hand-typed (`_relayout_advance_ages`):
topological order → seed `bound[rung]=rung_age` / `bound[other]=10` → propagate
**backward** along prerequisite edges (`bound[parent]=min(bound[parent],bound[child])`)
→ forward walk assigning ages. The rung age is authoritative and is never
`max()`'d against a prerequisite's age.

Base CTP2 advances lost their prerequisites on import, so 69 of 143 are
prereq-depth 0. Their age comes from their **authored CTP2 `Age` field**, clamped
to `_MUNDANE_MAX_AGE = 4`. Only MoM-authored advances get depth banding.

**Result — histogram** AGE_ONE 38 / TWO 34 / THREE 16 / FOUR 22 / FIVE 11 /
SIX 7 / SEVEN 5 / EIGHT 5 / NINE 5 / TEN 0. Zero monotonicity violations. All 30
sphere rungs exactly on ages 2–7. `AGE_OF_REASON`, `GUNPOWDER`, `CHEMISTRY`,
`PRINTING_PRESS`, `CANNON_MAKING` all at age 4.

Re-anchor / delete plane: `tools/momjr_csv/advance_reanchor.csv`, 51 rows —
7 government deletes, 13 tileimp re-anchors, 16 tileimp deletes, 13 terrain
re-anchors, `WONDER_GNOME_TREASURY → ADVANCE_BANKING`, `UNIT_SETTLER` field clear.

Great Library scrub: `_scrub_dead_advance_surfaces()` strips GL sections,
`<L:DATABASE_ADVANCES,…>` cross-links, `ICON_ADVANCE_*` uniticon blocks and
`gl_str.txt` keys for every advance absent from the live tree.

**Verified:** generator EXIT=0; byte-stable from run 3 onward; **zero dangling
`ADVANCE_*` scenario-wide** (excluding the seven measured-inert files:
`AdvanceLists.txt`, `strategies.txt`, `Const.txt`, `DiffDB.txt`,
`Units_historic.txt`, `Units_release.txt`, `tut2_main.slc`). Harness mirror
md5-identical.

### Pass-ordering laws learned here (do not re-derive)

- `reg.save_all()` rewrites `Units.txt` / `Wonder.txt` from `reg._parsed`, so a
  late raw `_write_rel` to them is silently discarded — mutate `._text` instead.
- `tileimp.txt` is rebuilt every run and evicted from the registry cache; any
  re-anchor must run **after** that rebuild.
- The GL files are likewise rebuilt each run, so the scrub legitimately re-fires
  every run. Idempotence is measured in **output**, not in the fire count.
- An orphan advance is any ident **absent from the live tree** — a strict
  superset of the mask, because base files cite advances MoM never imported.

---

## Item 4 — close the SLIC sphere-matrix gaps — **DONE**

- [x] Chaos: `MomGrantChaosBuilding` in `mom_func.slc` — milestone = `IMPROVE_COLOSSEUM`,
      the only unclaimed chaos-reading improvement of the 21 in `buildings.txt`
- [x] Chaos: milestone building + `UNIT_HELL_HOUNDS` spawn in `mom_city_effects.slc`;
      the random windfall is KEPT (it is Chaos's B1 identity), the milestone is additive
- [x] Chaos: build-burst branch (COLOSSEUM, MERCHANTS_GUILD) + header table updated
- [x] Death: `MomCountDeathFoci` (BARRACKS 1 / MECHANICIANS_GUILD 2); Chaos also gained
      `MomCountChaosFoci` (COLOSSEUM 2 / MERCHANTS_GUILD 1). Both wired into `mom_turns.slc`
      as additive terms — neither sphere loses its identity income term.
- [x] `p <= 5` at 8 guard sites — measured 1 (`mom_magic`) + 2 (`mom_msg`) + 5 (`mom_spells`)
- [x] `mom_msg.slc` occlusion-safe spawn: all five summons now route through
      `MomSpawnSphereUnit`. ONE level from the handler body, so clear of the
      2-level 0xC0000005 chain.
- [x] `sphere` column in `slic_inventory.csv` — **derived, not hand-typed**
      (`sphere_of()` in `backcast_slic.py`; name wins, comment-stripped body is the
      fallback). Appended not inserted: `load_curation()` and the CURATION writeback
      address idx rows positionally.
- [x] 5 stale `slic_purpose.json` strings fixed (the plan named 4; `MomSpawnSphereUnit`
      still claimed "CreateUnit in first city" after the occlusion fix) + 8 new rows.

**Verified:** `backcast_slic.py --check` → `slic tab: current`, EXIT=0. Sphere
histogram is **square at the core** — 4 decls each for life/nature/sorcery/death
(`MomPlayerIsX`, `MomCountX`, `MomGrantXBuilding`, `MomBlessX`), chaos +4 extra
from the chaos-only spellbook. `backcast_slic.py` mirrored to the harness
(md5 `6ca660b72bce73221f46c86901858dd1`).

## Item 5 — generate `mom_gating.slc` — **DONE**

Four `mod_Can*` hooks, `#include`d from `scenario.slc:65`. Hard constraints
honoured: **`g.player`, never `thePlayer`** (probe B3 — `CallMod` builds the arg
as `SLIC_SYM_PLAYER` and `SetIntValue` only writes `SLIC_SYM_IVAR`, so the index
is never stored and the read always yields 0); **flat bodies** — a 2-level
user-function chain from an engine callback is an access violation; compare via
`AdvanceDB()`/`UnitDB()`/`BuildingDB()`/`WonderDB()` (`WonderDB` confirmed a real
conduit at `SlicEngine.cpp:2883`); player guard first, because
`ResetCanResearch` calls the advance hook once per advance per player.
`theCity.owner` carries identity on the three build hooks (probe B2).

Emitted by `_emit_mom_gating_slc()` in `ctp2_generator.py`, ordered **dead last**
in `main()` — every ident is filtered against the live `Advance.txt` /
`Units.txt` / `buildings.txt` / `Wonder.txt` block names, so the 14 phantom
`WONDER_`/`IMPROVE_` idents `sphere_gate_targets()` emits per improvements row
are dropped rather than becoming dangling refs.

**Verified:** generator EXIT=0, `+ mom_gating.slc: 86 ident(s) walled across 5
tribes` = 30 advances (6 rungs × 5) + 42 units + 3 buildings + 11 wonders.
200 lines, **byte-stable across two consecutive runs**
(md5 `08a3e7d584913debd4ea7dbce306721b`); `Advance.txt`
(`8707550b17bbb909e90935921fd1fe70`) and `Units.txt`
(`4aa60d329a97b8c8b4aad44f04be23ef`) unchanged, proving the new pass clobbers
nothing. Generator mirrored to the harness (`5635a3cd978fb6850d3cec88fecf68a1`).

## Item 6 — `tools/gate_faction_gating.py` — **DONE**

9 assertions; shared predicate `sphere_gate_targets()` imported from
`ctp2_generator.py` so writer and gate cannot disagree. Registered in
`validate_scenario.py` `main()` as `check_faction_gating(scen, fails)` — gate 10.

| # | asserts |
|---|---|
| A1 | a sphere'd block's `EnableAdvance` is on **its own** ladder |
| A2 | every rung reaches its sphere root transitively through prerequisites |
| A3 | all 6 rungs of all 5 ladders exist in `Advance.txt` |
| A4 | the wall names every rung — no straggler |
| A5 | every ident the wall cites exists in the generated DB (**the silent no-op**) |
| A6 | no ragged column in the 5×N SLIC matrix |
| A7 | no rung in `AGE_ONE` (start band → granted free at `Player.cpp:536`) |
| A8 | zero dangling `ADVANCE_*` refs in any live dimension file |
| A9 | rung ages match `_RUNG_AGE`; no sphere'd block enabled by a mundane advance |

**Verified — live tree: 70 targets, 0 violations, EXIT=0**; `validate_scenario.py
--scenario scen0000` → all gates pass.

**Negative control (the gate was measured against known-BAD artifacts, not just
a green tree).** Two scratch copies with injected defects; every class fired on
the right assertion:

- A1/A9 ← `UNIT_ZOMBIES.EnableAdvance` repointed to `ADVANCE_BRONZE_WORKING`
- A4/A5/A8 ← one typo'd ident (`ADVANCE_CHAOS_MASTUR`) in the wall
- A7/A9 ← `ADVANCE_LIFE_MAGE` moved to `AGE_ONE`
- A8 ← a dangling `ADVANCE_GHOST_TECH` in `buildings.txt`
- A2 ← `ADVANCE_NATURE_MAGE` reparented off its ladder (7 downstream rungs cut)
- A3 ← `ADVANCE_SORCEROUS_LORE` block deleted

8 of those propagate through `validate_scenario.py` as `FAIL A*` lines.

**Two instrument defects the negative-control discipline caught first**, both in
the gate and neither in the mod: `MomBless*` are messagebox **segments**, not
functions, so a call-shape regex reported all five spheres as ragged; and
`uniticon.txt`'s 568 `ADVANCE_*_GAMEPLAY/_HISTORICAL/_PREREQ/_STATISTICS` are
Great Library **string keys**, not advance references. Residual real dangling
refs after excluding those: **zero**.

Mirrored to the harness (`gate_faction_gating.py` `ec39347f4b0d55359c246fe4830ffb53`,
`validate_scenario.py` `32befdc2a21d3f26a29f7161ff72217e`).

## Item 7 — recursive taxonomy review — **DONE**

Agent-driven, not a script (`close_gating.py` cancelled per the user). Four
review rounds over the sphere partitioning; round 4 was the last that changed
anything and round 5 returned nothing new. Findings applied: the five tribe
leaders pinned from `players.csv`, the four unlorded heroes (Serena, Alorra,
Warrax, Malleus) adjudicated from art/stats/cost-band, and Entropy Engine moved
to `death` with prereq `Sth` (`ADVANCE_DEATH_WIZARD`) in `improvements.csv:44`.
`sphere` in the CSVs means *who may build it*; `sphere` in SLIC means *who gets a
bonus* — a neutral building with a per-sphere bonus is correct, not a conflict.

## Item 8 — prune GL descriptions for deleted advances — **DONE**

Authored HISTORICAL text for the deleted advances removed from
`gl_descriptions.csv`. `gate_gl_descriptions.py` → 784/784 PASS.

---

## Postmortem — the DB-Error modal class (three modals, one root cause)

**Root cause, common to all three:** every static gate in this project only
inspected files the scenario *overrides*. The engine loads the **base-tree** copy
of any gamedata file the scenario does not ship. The tech cap deleted 113
advances and 17 tile improvements, so every base-tree file citing a deleted
ident became a load-killing landmine that no gate could see.

Two things made this expensive to find:

- The engine prints the **display name**, not the ident
  (`AdvanceRecord.cpp:768` → `g_theStringDB->GetNameStr(id)`), which is why
  grepping for "Industrial Revolution" found nothing — the ident is
  `ADVANCE_INDUSTRIAL_REVOLUTION`.
- The engine **aborts on the first dangling ref only**, so launching the game
  discovers them strictly one at a time at ~5 min each. Using the game as the
  scanner was the method defect; a static all-family sweep enumerates the whole
  backlog in one read-only pass.

| # | Modal | Source | Fix |
|---|---|---|---|
| 1 | `ICON_ADVANCE_DEFAULT` | the advance-deletion prune's `_dead()` sweep ate the engine's fallback icon (referenced by the `ADVANCE_NA` sentinel, not by any advance) | exempt the sentinel |
| 2 | *Industrial Revolution not found in Advance database* | **base** `Pop.txt` — `POP_LABORER`→`ADVANCE_INDUSTRIAL_REVOLUTION`, `POP_MERCHANT`→`ADVANCE_ECONOMICS` | `_scrub_dead_advance_surfaces()` re-anchors to `ADVANCE_CONSTRUCTION` / `ADVANCE_TRADE` and pulls the file into the scenario; all five specialists stay playable and both anchors are pre-Renaissance |
| 3 | *Listening Post not found in terrainimprovement database* | **base** `aidata/ImprovementLists.txt` — `IMPROVEMENT_LIST_MISC`→`TILEIMP_LISTENING_POSTS` | new `_scrub_dead_tileimp_surfaces()` re-anchors to `TILEIMP_TRADING_POST` (an empty AI list is an untested engine path) |

**Gate 11 generalised to all families** (`validate_scenario.py`
`check_effective_tree_advance_refs`). It resolves each of 13 families against its
defining file, walks the engine's `civapp.cpp` parse list *plus* `aidata/`, and
for each file checks the copy the engine will actually load. Two axes of scoping
keep it at zero false positives: only genuinely-parsed files (base `Improve.txt`,
`endgame.txt`, `order.txt`, the `*icon.txt` exports and
`Units_{historic,release}.txt` all carry dead refs and are inert), and `//`
comments stripped before tokenising (`strategies.txt` lists seven deleted
governments, all commented out). **Negative control: on the unfixed tree it
reported exactly one failure — `TILEIMP_LISTENING_POSTS` — and nothing else.**

Also fixed: the gate had silently no-op'd because `base = scen.parents[3]`
assumed an absolute path, and `--scenario scen0000` is relative. It now walks
`scen.resolve().parents` upward for `ctp2_data/default/gamedata`.

## Verification tail — **DONE**

| Check | Result |
|---|---|
| `ctp2_generator.py` | exit 0 |
| Double-run md5 on `ImprovementLists.txt`, `Pop.txt`, `Advance.txt`, `Units.txt`, `buildings.txt`, `mom_gating.slc` | **BYTE-STABLE** |
| `validate_scenario.py --scenario scen0000` | all gates pass |
| `gate_faction_gating.py` | 71 targets / **0 violations** |
| `gate_gl_descriptions.py` | **784/784 PASS** |
| All-family dangling sweep over the effective tree | 1 true positive (fixed); every other hit triaged as a field name, enum, GL string key, AI list record name or comment |
| **Headless boot** (`uiwalk.py --run steps/newgame_mom_inject.json --save none`) | reaches **turn 1, 4000BC, no modal**; two frames at 909 / 3658 unique colours prove the message pump stayed live |
| Leaked processes after the run | none |
| Mirror `.py` to `H:/Games/ctp2/ctp2-modding/tools/` | done (`.py` only — CSVs are mod data) |

Still open, scope-limited and carried: the AI stall run to ~turn 40 (no SLIC hook
observes AI goal-picking, so this needs a live game), and uiwalk's abort teardown
which logs *"leaving it running"* rather than killing the process — it did not
fire this run, but the path is still there.

## Known risks

- A typo'd ident in `mom_gating.slc` silently disables that gate — gate
  assertion 5 is the only thing that catches it.
- AI research thrash when a denied advance is already committed; no SLIC hook
  observes AI goal-picking. Measure in the turn-40 run before accepting a trade.
