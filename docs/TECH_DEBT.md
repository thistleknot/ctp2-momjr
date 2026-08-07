# Tech Debt — MoM Mod

## High Priority

### Spellbook shows only 2 spells per page (middle pages)
- Close + Prev + 2 spells + Next = 5 arms (engine max)
- FIX PLANNED: single-char button labels ([1] [2] [3] [N] [X])
- Body text becomes the legend: "1) Bless (10)  2) Endurance (10)  3) Holy Weapon (10)"
- No Prev button — X returns to hub, forward-only paging
- 3 spells per page uniform, aim for equal distribution across max 3 pages per rarity
- With ~3-6 spells per rarity per sphere, most rarity groups fit on 1-2 pages

### Spells should be research-gated (total conversion gap)
- Original MoM: spells are RESEARCHED, not freely available
- CTP2 advances = MoM spell research (mapping already exists)
- Spellbook currently shows ALL spells regardless of research state
- FIX: each spell needs EnableAdvance mapping; spellbook checks
  PlayerHasAdvance before showing a button arm
- This makes the tech tree meaningful — you research to unlock spells
- Priority: after the UI fix (no point gating invisible spells)

### Control-plane reconciliation spec needed
- Two repos: harness (ctp2-modding) and mod payload (ctp2-momjr)
- Harness main can't run generator end-to-end (missing advance_mask.csv etc)
- examples/momjr/control-plane/ is incomplete vs what generator requires
- Need spec: what CSVs exist, what each drives, full generation flow

### Never use mom-base-clean branch again
- All harness work on modding/main
- All mod output committed to ctp2-momjr
- mom-base-clean is a stale snapshot, not the working mod

## Normal Priority

### Generator refactor (spec exists: docs/specs/generator-refactor.md)
- 6000 lines in one file, decompose to <1000/module
- Enables clean feature grafting without merge hell

### Flight test probes don't exercise features
- turnloop only hits End Turn — misses all UI paths
- Need probes for: spellbook full path, build queue, research
- probe_spellbook.py only opens menu, doesn't click through

### Spellbook routing had 3 entry points, only 1 was updated
- MagicMenu "Cast a Working" button (mom_msg.slc) — fixed
- BeginTurn MomSpellMenuTick (mom_spells.slc) — fixed
- Old MomMsgSpellbookChaos alertbox (mom_spells.slc) — removed
- Lesson: grep ALL .slc files for the old segment name before committing
