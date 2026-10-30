## Comparison Criteria Clarification Needed

**Hypothesis**: The comparison should be:
- Extract paths from CSV file A (say, a `source_path` column)
- Extract paths from CSV file B (say, a `target_path` column)
- Compare paths where the *same path* appears in both files
- Track differences: missing in one, duplicated, format mismatches

**Alternative Hypothesis 2**: Compare paths within the same file (e.g., `source_path` column across multiple rows), tracking: duplicates, missing paths, format inconsistencies.

**Confirmation needed**:
1. Which CSV files?
2. Which specific path columns?
3. Is the comparison cross-file (same path in both) or intra-file (column consistency)?
4. What counts as "missing"? Same path, different format, or missing column entirely?

**Evidence available**: The dimension_inventory.md and MOD_DIMENSIONS.md reference CSVs like `units.csv`, `scenarios.csv` for path extraction. Consult these for source column names.
## 2026-10-27 — Unit enchantments via engine user flags (unverified in-game)

**Hypothesis.** 18 of the 44 do-nothing spells are MoM unit enchantments. ReMoM stores each as one bit in a per-unit uint32 (`gd_unit_fields.h:28`) and turns the bits into stat changes at battle load (`COMBINIT.c:705-884`). CTP2 had a registered but always-0 `UnitHasUserFlag` (`slicfunc.cpp:5794`) and three unused combat hooks (`mod_UnitAttack/Defense/RangedAttack`, `UnitData.cpp:3299/3496/3715`). Backing the stub with a real field lets generated SLIC carry the 18.
**Test.** Engine: `m_userFlags` + `SetUnitUserFlag/ClearUnitUserFlag` (branch feat/unit-user-flags), move/attack/counter-defense modifiers kept across turn reset. Generator: `_UNIT_ENCHANTS` table -> cast branch sets the flag on the selected unit, hooks add the bonus.
**Prediction if TRUE.** Cast Holy Armor on a selected unit -> "The selected unit is enchanted"; a second cast -> "already has this enchantment", no mana spent; that unit's defense in a fight is +2. Endurance: unit has +1 move after end-turn. Regeneration: HP up at turn start. **If FALSE:** hook never binds -> no stat change; or a SLIC Error popup at game start (compile).
**Confirmation bar.** NEW game (saves cache SLIC). Three different spells, one fight each, compare combat odds with and without. Single run proves nothing for the hooks.
**Known gaps (stated, not hidden).** Flags are NOT saved: reload loses enchantments. Iron Skin and Stone Skin stack here (MoM: they do not). Hooks run SLIC on every attack/defense calculation: AI end-turn may slow (hypothesis, unmeasured). Release exe is `ctp2-dbg.exe` built with LinkIncremental=false because the incremental linker crashed (LNK1000 IncrCalcPtrs) - build-command change only, vcxproj untouched.

## 2026-10-27 — Right-click menu showed only "Map Info": stale objects after a class-layout change (RESOLVED)

**Hypothesis.** The enchantment work added `m_userFlags` to `UnitData` BETWEEN `m_flags` and `m_pos` (UnitData.h). The first build after that edit linked 367 object files that predate it, so some TUs read `m_pos` at the old offset.
**Evidence (headless, engine-written rcdiag.txt, build with stale objs):** `RCDIAG final state=1 vis=1 uown=1 ucity=0 pos=0,0 units=0 city=0` and `state=4 ... ucity=1 pos=0,0 ... city=0` - selected unit and founded city owned by the viewing player, position read as 0,0, so ControlPanelWindow::BuildList looked at an empty tile and added only Map Info.
**Falsifier run (after `/t:Rebuild`, same probe):** `RCDIAG final state=4 vis=1 uown=1 ucity=1 pos=22,82 units=2 u0own=1 city=1 cown=1`. Position real, city and owner detected. CONFIRMED.
**Law.** An incremental MSBuild after editing a member layout of a class used across many TUs is NOT trustworthy here: always `/t:Rebuild`, and put new members at the END of the class. Verify with an engine-side print of the values the failing code reads, not by reading the code.
**Tooling notes.** The game is a GUI-subsystem exe: `printf` never reaches `runs/engine_stdout.log`; write diagnostics with fopen to the working dir (`ctp2_program/ctp/`). `uiwalk.EXE_DIR` already is `ctp2_program/ctp`. Slow machine + AV scan needs `LAUNCH_TIMEOUT_S` x3. Diagnostics and both probes removed; engine files restored to HEAD.
