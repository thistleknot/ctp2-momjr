# Headless MoM playtest: menu input and turn-50 confirmation (2026-10-25)

The earlier two-city playtest froze at turn 38 with units logged at 1,717,986,938 HP. After moving MoM runtime modifier initialization ahead of derived-stat calculations and rebuilding Debug-SDL, run `tools/uiwalk/runs/20261025-190353-turnloop/` reached turn 50/50. It had one city, Eudoria, and a Spearman queue; it did not reproduce the two-city queues or summon Crusader. The fixed run logged nine combat HP values, maximum 20, zero SLIC errors, and a verified autosave copy after each turn. It passed the old failure point, but that specific two-city/Crusader setup remains untested.

## Build Manager controls

Coordinate clicks did not select list rows or add production in the Build Manager. The debug executable's UI injection hook worked with these paths from `editqueue.ldl`:

- Unit rows: `BuildEditorWindow.ItemsBox.UnitsList`.
- Building rows: `BuildEditorWindow.ItemsBox.BuildingList`.
- Tabs: `BuildEditorWindow.ItemsBox.UnitsButton` and `BuildEditorWindow.ItemsBox.BuildingsButton`.
- Add: `BuildEditorWindow.ItemsBox.AddButton`.
- Clear: `BuildEditorWindow.QueueGroup.ClearButton`.
- Close: `BuildEditorWindow.NormalModeButtons.CloseButton`.

Clear opens a confirmation dialog. The left button confirms; the right button cancels. Verify the queue is empty before rebuilding it. The visible confirmed queue in both cities was Spearman, Spearman, Barracks, Spearman, Peasants.

## Select and verify the debug executable

The integration Debug-SDL executable is `H:\Games\civctp2-gaia-integration\ctp2_code\ctp\ctp2-dbg.exe`, SHA-256 `3CF936863B5BE86F65DB06B292A5F12771469C450F25E49761C90C0F4E3CC4B3`. The crash-capture launcher now defaults to this source directory and checks the selected PE image's actual imported DLLs. This image imports `MSVCP140D.dll`, `VCRUNTIME140D.dll`, and `ucrtbased.dll`, not `MSVCRTD.dll`; requiring the latter caused a false Release fallback. `-NoRun` preflight now reports `ctp2-dbg.exe` in `debug-preferred` mode. Confirm the selected source path and staged SHA in output for every actual run. The 2026-10-25 Release fallback exited with access violation `0xc0000005` in `ntdll.dll`, but the captured crash stack was empty and does not identify the fault.

On 2026-10-26, the corrected crash-capture command selected and staged the integration `ctp2-dbg.exe`, reported x86, and left a Windows-responsive `Call To Power 2` process running with no new crash report. The process is still open, so the runtime overlay remains active until normal exit. This confirms the stale Release fallback is fixed; it does not diagnose the older Release executable's access violation.

The earlier debug rerun reached MoM at 4000 BC (turn 0), founded Eudoria with `b`, and verified its queue as Spearman, Spearman, Barracks, Spearman, Peasants. The first map image was black; a single inert-bar hover (`fx=0.586`, `y=6`) repainted the terrain. `right` and `left` showed no visible change in this client, so do not repeat them without evidence. A map click at `(579,411)` selected the remaining Peasant on the city tile; the status bar showed `(41,59)`. For queue input, explicitly select the unit/building row by LDL path and index, press Add, wait about one second, then inspect the queue. The first Add press looked unchanged until a later list event. Evidence: `tools/uiwalk/runs/20261025-180014/` and `tools/uiwalk/runs/20261025-181351/01_eudoria_queue_complete.png`.

## Turn checking

Capture the frame, issue one End Turn action, wait for the screen to settle, then require the date to change. If it does not, stop and inspect the process and logs; do not repeat the same action. The 50-turn run used one action per turn and recorded 50/50 date changes with zero SLIC errors.

## Autosave checkpoints and restore limits

`AutoSave=Yes` caused `save/games/Alexan/AUTOSAVE-Alexan` to change after each confirmed turn. The harness hashes save files before each turn, waits for a changed archive after the date advances, and copies it to `tools/uiwalk/runs/20261025-190353-turnloop/checkpoints/turn_NNN_AUTOSAVE-Alexan`. All 50 copies were verified against the source file when copied; the installed turn-50 file matches checkpoint hash `d670288b27f7edd39c1903b4c7f90b2670754bb75dd4a9ddaaeddd712af1e056`.

Loading the turn-1 autosave crashed in `UnitRecord::HasNuclearAttack` while restoring AI state: `CTPDatabase::Access` requested index 81 from a 74-record database. The checkpoint files preserve turn state, but this restore path is not yet proven usable. In `ctp2_data/default/uidata/keymap.txt`, `^s` is `SAVE_WORLD`, while `S` is `SAVE_GAME`; injected Ctrl+S and Shift+S produced no visible save dialog. Native autosave is the only save path verified in this run.

## Summon chooser: Crusader selection still unverified

`j` opens Magic Status. In this run the recorded click `(290,385)` opened Life Summons, where Crusader is option 2. The `2` key and guessed clicks `(512,420)` / `(640,525)` did not select it; one click moved the map. Do not reuse guessed coordinates or count a summon until the chooser closes and the selected unit is visible. `summon_variety2.json` is an entry-path reference, not proof of coordinates for every window geometry.

## Runaway combat: stop instead of waiting on the menu

At in-game turn 38 in the earlier run, AI army `0xd000002c` attacked army `0xd0000021` at `(0,73)`. The initial log records both units at `1717986938 HP`; after combat round 745502, a unit still had `1716197930 HP`. The game stopped responding without a date change. `UnitData::Create` had calculated HP and movement before zeroing `m_hpMaxMod` and `m_moveMod`; the calculators add those fields to database stats. After moving all four MoM overlays before derived-stat calculations, the rebuilt Debug-SDL run reached turn 50. Its combat logs showed nine HP values, maximum 20, with no billion-HP values. This supports the fix for the tested one-city game. Direct movement values and the two-city/Crusader setup were not checked. Keep unit CSV/database data unchanged. `CTP2Combat.cpp` copies `u->GetHP()` into combat state and resolves rounds while both sides live. Captured baseline artifacts: `H:\Temp\mom_turn50_stall.dmp`, `H:\Temp\mom_turn50_civ3log006.txt`, and `H:\Temp\mom_turn50_civ3log229.txt`.

---

# Headless MoM playtest: input lessons (2026-10-25)

The earlier two-city playtest stopped at in-game turn 38/50 during the runaway combat recorded above. The evidence images and action captures are in `tools/uiwalk/runs/20261025-160839/`. A later one-city run passed turn 50; it did not summon Crusader.

## Drive the right surface

The Build Manager's list rows and buttons ignored posted coordinate clicks in this session. Use the debug build's UI injection hook with the LDL paths from `editqueue.ldl`:

- Unit rows: `BuildEditorWindow.ItemsBox.UnitsList`.
- Building rows: `BuildEditorWindow.ItemsBox.BuildingList`.
- Unit/building tabs: `BuildEditorWindow.ItemsBox.UnitsButton` and `BuildEditorWindow.ItemsBox.BuildingsButton`.
- Add: `BuildEditorWindow.ItemsBox.AddButton`.
- Clear: `BuildEditorWindow.QueueGroup.ClearButton`.
- Close: `BuildEditorWindow.NormalModeButtons.CloseButton`.

Clear opens a confirmation dialog. The left button confirms; `MessageBoxDialog.DialogBackground.RightButton` cancels. Verify the queue is empty before rebuilding it. Both city queues were then visibly confirmed as Spearman, Spearman, Barracks, Spearman, Peasants.

## Treat each turn as a checked action

Capture the current frame, send one End Turn action, wait for stability, and compare the date. If the date does not change, stop and inspect; do not repeat the same action. The later fixed-build run advanced through turn 50; the earlier build stopped at turn 38.

## Summon choice still needs a verified input

`j` opens Magic Status. In this run `(290,385)` opened the Life Summons page, which lists Crusader as choice 2. Sending the `2` key and guessed clicks `(512,420)` and `(640,525)` did not select it. One click moved the map, so those coordinates are wrong for this page. The Crusader summon is **not confirmed**; use a fresh screenshot and verify the alert box closes and the selected summon appears before counting it as done. The prior `summon_variety2.json` sequence is a reference for entering the chooser, not a verified coordinate map for this screen.

---

## The turn-loop ping had to lose its button (2026-07-27)

**Symptom.** Three consecutive runs died `0xC0000005` at scenario start,
including the previously-proven 40-turn baseline. Traceback always at
`inp.click`, ending `PostMessage: Invalid window handle`.

**Not the mod.** `git checkout 9318619~1 -- scen0000` and re-run: identical
failure. Restored immediately. This was never a v3.0.0 regression.

**The discriminating probe.** `steps/boot_only.json` — the proven boot sequence
with *zero* clicks after `StartButton`, then six timed shots. EXIT=0, healthy
1024x768 client at 4000BC. Boot is fine; **the posted click was the killer.**

**Why it started killing.** `ctp2-endturn-needs-mouse-input` says an injected
`enter` only counts if some mouse message reached the engine that turn, and the
loop satisfied that with a real click on "inert" top-bar chrome at a *pinned*
(600,6). A third display had become primary at a DPI-scaled 1536x864; the pixel
that is inert at a 1024-wide client is not inert at another width, and a miss AVs.

**The fix is smaller than the bug.** The engine needs *a mouse message*, not a
click. New `hover` verb posts `WM_MOUSEMOVE` alone — never hit-tested into a
control, so it cannot land on a widget and cannot AV. Aim is `fx`, a **fraction
of the live client width**, so it tracks whatever window the engine actually made.

**Law: aim derived from the live frame is safe; aim pinned to a pixel is not.**
And: when an input both *satisfies a requirement* and *carries a risk*, check
whether the requirement needs the risky half at all. It usually doesn't.

**Measured** run `20260727-181047`: 20/20 turns, zero AVs, Rush Buy counter
1200 -> 743 -> 12 (monotonic), so the clock genuinely advanced.

**Two things this run also fixed:**
- `decode_run.py`'s `STALL_MAX` was 2000px, calibrated on *five*-turn intervals.
  Per-turn it cried STALL six times on a run that was demonstrably progressing —
  a parked camera legitimately redraws only the build counter (~300-1200px). The
  real stall signature was always **byte-identical**; threshold is now 100. *A
  threshold carries the sampling density it was measured at.*
- `Game.kill()` derived the game PID from `self.hwnd` — the handle that is
  already dead on the abort path, so an aborted run terminated **nothing** and
  left a window on the user's screen. The PID is now remembered at acquisition.
  **HEADLESS has to hold on the failure path, or it does not hold.**


## Base-tree fallback is the DB-Error blind spot (2026-07-26)

**Symptom.** Three sequential native modals at scenario load, each killing the
boot: `ICON_ADVANCE_DEFAULT`, *"Industrial Revolution not found in Advance
database"*, *"Listening Post not found in terrainimprovement database"*.

**Root cause (one, for all three).** Every static gate only inspected files the
scenario *overrides*. The engine loads the **base-tree** copy of any gamedata
file the scenario does not ship. The tech cap deleted 113 advances and 17 tile
improvements, so base `Pop.txt` (`POP_LABORER` → `ADVANCE_INDUSTRIAL_REVOLUTION`)
and base `aidata/ImprovementLists.txt` (`IMPROVEMENT_LIST_MISC` →
`TILEIMP_LISTENING_POSTS`) became landmines no gate could see.

**Two traps.**
1. The engine prints the **display name**, not the ident —
   `AdvanceRecord.cpp:768` calls `g_theStringDB->GetNameStr(id)`. Grepping for
   "Industrial Revolution" finds nothing; the ident is
   `ADVANCE_INDUSTRIAL_REVOLUTION`.
2. The engine **aborts on the first dangling reference only**. Launching the
   game therefore discovers these strictly one at a time at ~5 min each.

**The method defect.** Using the game as the scanner. A static all-family sweep
over the *effective* tree enumerates the whole backlog in one read-only pass; on
the unfixed tree it returned exactly one true positive and nothing else.

**Fix.** `_scrub_dead_advance_surfaces()` and the new
`_scrub_dead_tileimp_surfaces()` pull the offending base file into the scenario
and re-anchor (`ADVANCE_CONSTRUCTION` / `ADVANCE_TRADE` /
`TILEIMP_TRADING_POST`). Re-anchor, never drop: an empty AI list is an untested
engine path, and all five Pop specialists stay playable.

**Gate.** `validate_scenario.py::check_effective_tree_advance_refs`, generalised
to 13 families over `civapp.cpp`'s parse list plus `aidata/`. Zero false
positives needs two scopings: only genuinely-parsed files (base `Improve.txt`,
`endgame.txt`, `order.txt`, the `*icon.txt` exports and
`Units_{historic,release}.txt` all carry dead refs and are inert), and **strip
`//` comments before tokenising** — `strategies.txt` lists seven deleted
governments, all commented out.

**Also.** The gate had silently no-op'd: `base = scen.parents[3]` assumes an
absolute path, and `--scenario scen0000` is relative, so the guard returned
early and disabled the whole check. Walk `scen.resolve().parents` upward
instead. A gate that cannot fail is worse than no gate — always run the
negative control.

---

## The Great Library printed stale numbers, and a stale instrument hid it

**Symptom.** `ADVANCE_WRITING_STATISTICS` advertised `Cost: 1000` for an advance
the DB priced at `1025`.

**Scope was wrong by 170x.** I carried "one cost drift". Running the new gate
against the live tree before fixing anything produced **170 FAILs** across all
three fields — `ADVANCE_CHAOS_MASTER` said `Cost: 1000` against a DB `8280`, and
`Age: Medieval` against `AGE_SEVEN`. Measure the class; never extrapolate from
the one instance you happened to notice.

**Root cause: pass ordering, again.** `ctp2_parser.Advance.register` stamps
Cost/Age/Branch at registration; `_retune_mom_advance_costs` rewrites Cost about
1300 lines later. `ctp2_generator` already encodes the countermeasure for GL prose
("Runs LAST, deliberately") — `_STATISTICS` simply predated that invariant. Fix
is the same idiom: derive from the final artifact at the end, never carry a value
forward.

**I nearly shipped an invented fact.** My first draft lifted `ctp2_parser`'s five
era words (Ancient/Medieval/Renaissance/Industrial/Modern) into a constant.
Measuring first killed them: `age.txt` carries **no display name at all** — the
`AGE_*` record is purely ordinal — and MoM ships **seven** ages, so AGE_SIX and
AGE_SEVEN printed as raw idents. The engine's `AGE_NAME_*` strings are a
different, five-valued concept that does not line up. `gl_age_display()` now
derives the ordinal, which is the only claim the data supports and stays correct
when the ladder is re-laid out.

**The second defect the first one exposed.** 39 labels shipped as
`Bronze_Working`, `Chaos_Magic` — three sites used `ident.split('_',1)[1].title()`,
which strips the prefix and leaves every interior underscore. It survived for
one reason: **an underscore is invisible inside an underlined link.** It only
became visible in the no-prereq sentence, which prints the bare name. Worse,
`gl_descriptions._harvest_labels` reads the *previous* generation's
`Great_Library.txt`, so one bad label re-seeded itself every run — a
self-sustaining feedback loop in a file the generator both reads and writes.

**The instrument was testing the wrong game.** Two headless probes were void: the
steps file inherited `select index 8` twice on `ScenarioWindow.AvailableListBox`
from a stale sibling, and index 8 boots **stock CTP2**. The verified MoM boot is
the two-level dialog **index 3 → LoadButton → index 0 → LoadButton**. The tell
was decisive once measured — searching "Chaos Magic" returned an *empty list* and
the article shown was stock "Religion". I had already started building a theory
("the pane must be engine-generated, not file-sourced") on top of that void
evidence. Three sibling steps files carried the same stale indices and were
silently testing stock CTP2 too; all three are fixed.

**The laws.**
1. A value stamped at registration is stale the moment any later pass rewrites
   its source. Derive at the end or gate it.
2. A gate must read the **shipped** artifact on both sides, not the writer's own
   output, so a future writer reintroducing the bug still fails.
3. When a generator reads a file it also writes, a single bad value is permanent
   unless something normalises at the read boundary.
4. Before trusting a headless result, prove the *right build and the right
   scenario* actually booted. A stale index is a stale binary by another name.

## The turn loop stalled on a modal that keys cannot reach

**Symptom.** A 40-turn headless AI stall run completed without crashing, but
frames at turns 20/25/30/35 were byte-identical (`changed_px = 0`). Per the
pixel-delta decoder a zero is ambiguous — input never landed, landed and did
nothing, or something swallowed it — so it was not read as "the AI stalled".

**Observed.** `09_turn20.png` shows the `SciAdvanceScreen` RESEARCH modal:
"scientists have discovered Bronze Working. Select a new Advance", with
Ceremonial Burial / Pottery / Shamanism / Currency and Goal / OK. The clock was
frozen at 3625BC. The injected `enter` was being absorbed by the modal, which is
the already-recorded law `ctp2-input-reach-by-surface`: in-game modals take
clicks, not keys.

**Fix.** A posted in-game click is process-lethal, so the modal is cleared by
*injection* on its OK button — `science.ldl:430` declares it as
`SciAdvanceScreen.Background.BackButton` (text `str_ldl_CAPS_OK`, the label is
"OK" but the ident says "Back"). Injection is fire-and-forget: when the modal is
absent the hook finds no control and does nothing, so the press is safe to issue
unconditionally on every turn. `steps/ai_stall_40turns.json` now runs
`press SciAdvanceScreen.Background.BackButton` → `wait 400` → `click(600,6)` →
`enter` → `wait_stable`.

**Result.** Run `20260727-075633`: 40 turns, every delta 61k–159k, no zero
frame, clock 3625BC → **3000BC**, two cities founded, AI diplomacy greetings
arriving. **No AI research thrash** — the risk the plan named as its weakest
point does not reproduce.

**Laws.**
1. `uiwalk.py` has no conditionals, but injection is idempotent-by-absence — an
   unconditional `press` on a modal that may not be up is the conditional.
2. An LDL ident is not its label. The OK button is named `BackButton`; grep the
   `text` string, not the name you see on screen.
3. A run that "completes" is not a run that progressed. Assert the game clock
   moved, not just that no step threw.

## The discriminator that was true for everything

**Symptom.** `ADVANCE_ECOGNOMICS` sat at AGE_FIVE — inside the band the design
reserves for magic — even though `_relayout_advance_ages` documents a guarantee
that mundane tech stops at AGE_FOUR. The cap was written, shipped, and enforcing
nothing.

**Root cause.** The cap keyed on `ident in momjr`, meaning "did MoM author this
advance?" MoM authored essentially the entire tree, so the predicate was true for
nearly every ident and the `else` branch that applied the cap was dead code. I
did not assume this — I ran a probe printing `momjr=` per ident and every one
came back `True`.

**Three laws.**

1. **A boolean that is nearly always true is not a discriminator, it is a
   constant.** Before trusting a branch, measure how often each side is taken. A
   branch that never executes reads exactly like a branch that always passes.
2. **Write the gate first and it tells you the blast radius.** I framed this as
   one bad advance. The Gate-22 control run against the *pre-fix* artifact
   returned **five** FAILs: Ecognomics, Greater Fauna Lore, Sanitation, Sea Lore
   (AGE_FIVE) and Sea Mastery (AGE_SIX). Fixing what I had noticed would have
   left four.
3. **Derive the discriminator from structure, not from provenance.** "Who wrote
   it" is metadata that drifts; "is it a sphere rung, or does it transitively
   require one" is a closure over the actual prerequisite graph and cannot go
   stale. It also preserves the sibling guarantee for free: a mundane advance's
   prerequisites are mundane by construction, so clamping can never place an
   advance below its parent.

**The bug the fix uncovered.** The `mom_sphere_home.slc` emitter was nested under
the age-re-layout branch, unrelated to its own policy flag — so any run that
re-aged anything wrote SLIC citing five `ADVANCE_HOME_*` that only exist when
`sphere_home_exclusivity` is on. The policy-off sever pass runs *earlier* in the
same function, so it could not undo it; the system only looked self-healing
because a second generator run cleaned up after the first. **A defect that a
re-run hides is still a defect** — the shipping artifact is whatever one run
produces.

**Verified headlessly**, run `20260727-082211`: all five advances read `Age: 4`
in the Great Library, Ecognomics at the predicted `Cost: 2425`.
