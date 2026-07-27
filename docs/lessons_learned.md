
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
