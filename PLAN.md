# CURRENT — Missing Gaia records crash native startup (2026-10-25)

- Hypothesis: MoM intentionally defines only ENDGAME_MOM_MASTERY, while native GaiaController::CanStartCountdown reads the missing ENDGAME_PROCESSING_TOWER record; the resulting null dereference causes fresh startup to fail before turn one.
- Evidence: runs/20261025-104013-turnloop reached 0/3 turns; crash-20261025-104109.txt names CanStartCountdown+0x26; disassembly at 0x0059c686 dereferences a null lookup result; the scenario's EndGameObjects.txt has one non-Gaia record.
- Change under test: native code treats omitted Gaia assets as unavailable, resets lookup caches on scenario initialization, and rejects countdown/tower building without the required assets; scenario data stays generator-owned.
- Prediction: absent/partial Gaia records no longer cause native initialization failures; complete stock records retain their normal thresholds; failure at the same instruction falsifies the guard.
- Confirmation bar: test absent, partial, and complete record sets, then a fresh MoM game with a city and three responsive turns; no SLIC errors or crash; test the separate save-load path on preserved extensionless saves.
- Status: the initial guard is incomplete for debug initialization and is being repaired; no successful gameplay validation claimed; #473 is draft.
- Correction: the earlier extension-filter search missed real extensionless AUTOSAVE/QUICKSAVE archives; inspect their metadata before attributing a saved game to MoM.
- City-validity status update: the H:/BuildTools toolchain is installed and can compile; the old missing-workload claim is superseded, while runtime acceptance remains OPEN.

# CURRENT — SLIC city callback invalid-handle guard (2026-10-24)

1. **Hypothesis** — `mod_CanCityBuildBuilding` receives a city handle that is invalid at the callback boundary; reading `theCity.owner` then fails and SLIC reports `noname: is not an integer` at line 188. Engine `CitySymbol_Valid::GetIntValue` returns a boolean safely, while owner lookup fails when `GetCity(city)` cannot resolve the handle.
2. **Test** — emit `if (theCity.valid == 0) { return 1; }` before any city member reads in all three build callbacks, regenerate through the harness, and audit the generated scenario.
3. **Prediction** — TRUE: generated callbacks guard invalid handles before `.owner`/`.location`, preventing this error path while allowing the engine's normal build decision. FALSE: the same dialog recurs despite the guard, so the callback binding or another `.owner` read is the next target.
4. **Latest result** — first in-game load falsified the assumption that `city.valid` was already exposed: the game reported `valid is not a member of theCity` in all three callbacks and reached 0/3 turns. Source inspection found `CitySymbol_Valid` implemented but not registered in `SlicStruct_City`; the registration and a contract spec are now present in the engine source tree. Build is blocked because Visual Studio lacks C++ tools and this account is not an administrator. The generator output currently requires that engine rebuild; no gameplay fix is confirmed.
# CURRENT — PR #455 exact-binary validation

**Disposition:** Layer 1 renderer-restoration gate. Navigation, exact-binary staging, the seven SLIC builtins, target callback, and ESC cancellation are proven. The rebuilt ADB7 binary adds right-click production cancellation. Two raw discriminators now prove the black captures are inside the SDL client render, not HWND selection, process replacement, `PrintWindow`, crop bounds, or DPI coordinate scaling. Freeze feature changes and full-battery retries until the committed software-renderer contract produces two consecutive nonzero client captures.

**Second discriminator result:** Removing only probe-local `SetProcessDPIAware()` changed the recorded client geometry from `1280x960` to `1024x768`, but `runs/20260815-095058-capture` retained cached=fresh HWND (`43127610`), owner PID `36152`, class `SDL_app`, `PrintWindow=1`, full nonzero count `118700`, valid crop bounds `(9,38)-(1033,806)`, and client nonzero count `0` on both captures. DPI awareness changed geometry as predicted but did not restore SDL pixels; it is falsified as the immediate cause.

**Archaeology result and confirmed restoration:** The committed `_child_env()` in both owning repositories sets `SDL_RENDER_DRIVER=software`, and its measured contract says the accelerated SDL backend is unreadable through GDI `PrintWindow`. The working tree replaced that key with `SDL_HINT_RENDER_DRIVER=software`; the latter is not the renderer-selection environment variable. Restoring only `SDL_RENDER_DRIVER=software` produced `runs/20260815-095545-capture`: cached=fresh HWND `6099758`, one owner PID, `PrintWindow=1`, valid `1024x768` crops, and exactly `1433030` nonzero client values on both consecutive captures. The rendered scenario-selection frame visibly matches `20260815-093446-builtins`. **Root cause confirmed:** the renderer environment substitution selected a GDI-unreadable SDL backend; offscreen stashing remains valid.

**Callback oracle result at restored geometry:** `runs/20260815-095636-builtins` armed target mode and deactivated after dispatch, but the probe reported `gold_delta=0`. Persisted frames directly falsify callback failure: gold visibly changes `106 -> 1106`, with 136 changed pixels confined to x `753..778`, y `7..15`. At `1024x768`, the proportional x crop `0.56..0.64` moved to `573..654`; the HUD gold digits stayed at the same fixed x position observed in the `1280x960` proofs (`751..776`). `gold_rect()` now uses fixed HUD coordinates x `730..810`, y `0..40`. Offline replay passed callback runs `095636=136`, `093446=85`, `092941=85`, and zero-effect control `084905=0`; the live battery is unblocked.

**First discriminator result:** `runs/20260815-094845-capture` produced all-zero prefix frames 1–5 under the same ADB7 source/staged hash and a clean process exit, then the diagnostic aborted because it treated the expected black visual assertions as prerequisites. After removing only that early abort, `runs/20260815-094956-capture` closed the boundary: cached and freshly resolved HWND were identical (`101323068`), both belonged to PID `38356`, both raw `PrintWindow` calls returned 1, both full `1303x1019` bitmaps had `118700` nonzero values, and both valid in-bounds `1280x960` client crops had exactly zero nonzero values. Window identity, process ownership, API return, and crop arithmetic are therefore clean; only the SDL client render is black.

**Recovered last-good evidence:** Commit `acdfb2af2fb492a937746f4f278e4680866da03c` contains the proven picker implementation. Consecutive artifacts `runs/20260802-205652-longgame` and `runs/20260802-210818-longgame` each reached 200 turns. Their path is fixed: select `ScenarioWindow.AvailableListBox` index `3`, press `ScenarioWindow.LoadButton`, select the inner list index `0`, then press `SPNewGameWindow.StartButton`; `ui_map.json` records seven items, three visible rows, and no scroll requirement.

**Observed regression:** `inject_select()` now waits for `select:ok`, retries ten times, and raises when no response arrives. The native `select:` branch now uses `GetItemByIndex()` and writes `select:ok`/`select:refused`. Runs `20260815-085830-builtins` and `20260815-090004-builtins` both exhausted those retries before entering MoM. This acknowledgment protocol is the earliest divergence from the last-good path.

**Falsifiable restoration hypothesis:** restoring only Python's one-shot command post and native `NumItems()`/`SelectItem()` selection, while preserving the hash-verified runtime overlay and target instrumentation, will recover boot navigation. TRUE predicts the unchanged one-turn turnloop reaches `1/1` with zero SLIC errors; FALSE predicts a boot failure despite exact last-good selection semantics and sends diagnosis to the runtime overlay or current picker contents.

**Single-variable test:** rebuild Final-SDL after the native restoration, then run `turnloop.py --turns 1` from `tools/uiwalk`. Do not resume builtin testing until this matched control passes.

**Closed hypotheses:** The lost Windows SDL injection consumer was reconstructed and compiled. Directly executing `SOURCE_ROOT\ctp2.exe` is not valid even with `cwd=EXE_DIR`: CTP2 derives data roots from the module location, so it searched the source checkout rather than the installed `ctp2_data` tree.

**Current falsifiable hypothesis:** the existing PowerShell runtime-overlay mechanism is the correct boundary if it is invoked from the tracked source script with an explicit installed root, always stages the selected source runtime (not only on architecture mismatch), verifies source/staged SHA-256 equality, launches from the installed path, and restores in `finally`.

**Latest result:** the fixed-window correction is confirmed. `runs/20260815-070958-turnloop` reached all five turns with `VERDICT: OK`, `turns_reached=5/5`, and `slic_errors=0` against the hash-verified rebuilt executable.

**Current observed defect:** `ScriptTargetMode::Begin()` sets `CP_TARGETING_MODE_SCRIPT_PENDING`, but the next `ControlPanelWindow::Idle()` calls `TargetingMode()`. That switch handles order/tile-improvement/terraform only, so script pending reaches `default`, calls `ClearTargetingMode()`, and deactivates the callback before `target:0,0` arrives. Run `runs/20260815-083942-builtins` is the pinned failure: phase 1 advanced, gold delta stayed zero, and the callback was absent.

**Falsifiable hypothesis:** adding only a no-op `CP_TARGETING_MODE_SCRIPT_PENDING` branch to `ControlPanelWindow::TargetingMode()` will preserve the one-shot script target across idle ticks. If true, the unchanged target injection reaches `ScriptTargetClick()` and the gold callback fires. If false, target mode will still clear or callback resolution/injection is the next broken link.

**Latest result:** `runs/20260815-084905-builtins` posted the target immediately after asserted boot and still produced zero gold; its before/after frames are pixel-identical at 4000 BC and 100 gold. Fixture inclusion and binary hashes are verified, but those facts cannot distinguish “never armed” from “armed then cleared elsewhere.”

**Current falsifiable hypothesis:** runtime target activity is the missing discriminating signal. A generic opt-in `query:target-active` command on the existing command-file protocol will report `ScriptTargetMode::IsActive()` without changing game state. If it reports 0 after the fixture phase, the broken link is activation/event timing; if it reports 1 but `target:0,0` still yields no callback, dispatch or callback resolution is broken.

**Single-variable test:** add the query command and poll its response in `uiwalk.py`; have the probe assert active before every target/cancellation input and inactive after every successful target/cancellation. Rebuild, then run the battery. No fallback behavior and no MoM-specific production symbol are introduced.

**Latest result:** acknowledged selection made boot deterministic, and `runs/20260815-085550-builtins` reached the game. The runtime query returned `active_before=False`, proving the temporary `BeginTurn` fixture did not arm; target dispatch was never exercised.

**Current falsifiable hypothesis:** execute each temporary SLIC test segment explicitly through a generic, environment-gated `execute:<segment>` command. This removes BeginTurn timing and phase attribution. If each segment returns `execute:ok` and target-active becomes 1, the builtin arm is proven; if a segment executes but activity stays 0, that builtin/fixture assertion failed.

**Single-variable test:** replace the phase handler with one temporary segment per builtin plus one cancellation arm; have the probe explicitly execute each segment, query active, dispatch/cancel, and query inactive. No turn scheduling is involved.

**Confirmation bar:** the launcher reports equal source/staged hashes; all seven builtin rows PASS; each arm is observed active before input; target execution produces the gold witness and deactivates; ESC and right-click deactivate without callback, unrelated UI, or process death; `zero_slic_errors` PASS. Then remove the temporary fixture/include and rerun exact `5/5`, `slic_errors=0` before final builds and push.

**Observed target result:** `runs/20260815-092941-builtins` armed `BeginTargetMode`, consumed `target:0,0`, deactivated, and changed the persisted HUD from 100 to 1100 gold. The callback therefore executed. The reported `gold_delta=0` was a false failure: offline replay reproduced zero because `gold_rect()` sampled x `870..1023`, while the only changed pixels were x `751..776`, y `0..5` on the `1280x960` frames. The matched no-callback control `runs/20260815-084905-builtins` remains pixel-identical.

**Falsifiable oracle correction:** keep the existing top-four-percent vertical bound, but move the horizontal bound to normalized x `0.56..0.64`, which contains the measured gold digits at x ratio `0.587..0.606`. TRUE predicts offline replay yields a positive delta for `092941` and zero for `084905`, then the unchanged live battery advances beyond `BeginTargetMode`; FALSE means the fraction does not generalize to the live capture geometry and the oracle must use a direct state witness instead. Change no native or SLIC behavior for this test.

**Observed battery progression:** `runs/20260815-093446-builtins` passed all seven builtins and ESC cancellation. Right-click then caused native `0xC0000005`; Python's later `PostMessage` saw the destroyed HWND. The WER dump was not retained, but this matches the archived posted-button AV class. Source archaeology found the functional gap: PR #455 intercepts ESC in `ui_HandleKeypress`, but `SelectedItem::NewRegisterClick()` does not intercept right-click for active script targeting and reaches map hit-testing. The harness also sends an unnatural priming `WM_RBUTTONUP` before the normal down/up pair.

**Observed right-click restoration result:** `runs/20260815-100118-builtins` passed all seven builtins, callback execution, ESC cancellation, target active/inactive transitions, process survival, and zero SLIC errors. Right-click itself also deactivated targeting and suppressed the callback, but the probe marked it FAIL because whole-frame `action_delta=51101` exceeded `2000`. Persisted frames show no context menu or unrelated window: the pre-frame is the recurring stale black-map `PrintWindow` surface and the post-frame is the same map normally rendered after `_spoof_focus()` plus `WM_MOUSEMOVE`. The global delta is a render-freshness oracle, not a cancellation oracle.

**Matched-control test:** after arming, first capture and call `PostInput.hover()` at the right-click coordinate; this uses the identical focus/mouse-move preamble but no button and must leave target mode active. Use its refreshed post-hover frame as the treatment baseline, then re-arm only if needed, send ordinary right-button down/up, and require inactive afterward, zero callback gold delta, process alive, and zero SLIC errors. Retain image deltas as diagnostics, not verdicts; visually reject any context menu/modal in the persisted treatment frame. TRUE predicts hover reproduces the refresh while retaining activity and right-click alone clears activity; FALSE moves the defect back to production input handling.

---

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
