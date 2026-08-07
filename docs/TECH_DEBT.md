# Tech Debt — MoM Mod

## High Priority

### Spellbook shows only 2 spells per page (middle pages)
- Close + Prev + 2 spells + Next = 5 arms (engine max)
- First/last pages can fit 3 spells (no Prev or no Next)
- Middle pages stuck at 2. Consider: fewer rarity groups, or accept it.
- Alternatively: remove Prev entirely, Close returns to hub, Next advances.
  That gives Close + 3 spells + Next = 5 on every page.

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
