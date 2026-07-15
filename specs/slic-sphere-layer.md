---
description: 'Re-enable MoM scenario SLIC in three gated phases: baseline entry point, sphere-magic mechanics, player messages'
---

***definitions***

- :SlicEntryPoint: is the scenario-level `default/gamedata/scenario.slc` that
  base `script.slc` #includes (shadowing the intentionally-empty base stub);
  the only sanctioned activation point for MoM SLIC.
- :SphereModule: is one of `mom_func.slc` (helpers only, no handlers),
  `mom_turns.slc` (BeginTurn sphere income), `mom_city_effects.slc`
  (GrantAdvance/CreateBuilding milestone rewards), `mom_msg.slc` (GrantAdvance
  blessing popups, #included last) — the sphere-magic economy + messages.
- :SlicSymbolSurface: is the set of `UNIT_/IMPROVE_/ADVANCE_/WONDER_` tokens in
  scenario `.slc` files, validated by `tools/validate_all_surfaces.py` surface 7
  against the generated DBs.
- :PhaseGate: is a user-run in-game verification (optionally `ctp2-dbg.exe`)
  that MUST pass before the phase is committed with "working".

***implementation reqs***

- Engine contract: SLIC parse errors are NON-FATAL dialogs (load continues);
  unknown symbols are SILENTLY auto-created and no-op — offline symbol audit is
  therefore mandatory before every launch.
- Files MUST be ASCII/latin-1 (the `_unintegrated/` masters are UTF-16LE+BOM —
  convert on copy; masters stay untouched).
- Canonical syntax (in-game proven, B1a contract): faction check by NUMERIC player
  index — `p == 1` Life, `2` Nature, `3` Sorcery, `4` Death, `5` Chaos (player N = civ N).
  `TRIBES_X` are civ-DB record names, NOT SLIC symbols (undefined); `player[p].civ` /
  `civ[p].ident` do not exist. Helpers take `int_t p`; the BeginTurn/event-local player
  is `player[0]` (correct, not forbidden), passed into helpers as `p`.
- Generator: `.slc` is never nuked; new files MUST stay off
  `_sanitize_omitted_building_refs`'s edit list in `ctp2_generator.py`.
- Include order in :SlicEntryPoint:: func → turns → city_effects → msg (last).

***test reqs***

- `tools/validate_all_surfaces.py` (surface 7) green before each launch.
- Symbol checklist for Phase B (DB-verified, as deployed): 5 ADVANCE_ (LIFE_MAGIC,
  NATURE_MAGIC, SORCERY, DEATH_MAGIC, CHAOS_MAGIC); 4 UNIT_ (GUARDIAN_SPIRIT, WARBEARS,
  MAGE, ZOMBIES — one per sphere except Chaos, which grants gold, not a unit); 9 IMPROVE_
  (TEMPLE, CITY_WALLS, WIZARDS_FORTRESS, GRANARY, PRIMAL_SOURCE, FANTASTIC_STABLE,
  BEACON_OF_WISDOM, BARRACKS, MECHANICIANS_GUILD). The offline symbol audit
  (validate_all_surfaces.py surface 7) is what pruned CLERIC/SOLAR_HARNESS/ACADEMY from
  the original checklist — SOLAR_HARNESS/ACADEMY have no buildable record; the Life unit
  is GUARDIAN_SPIRIT, not CLERIC.

***functional specs***

- Phase A: the :SlicEntryPoint: MUST parse clean and prove handler execution;
  stock tutorial SLIC MUST be retired via a scenario-level `tutorial.slc`
  override (tut2_main.slc left on disk, no longer loaded).
  - Given the new scenario.slc + tutorial.slc, When CTP2 loads the MoM
    scenario, Then no SLIC error dialog appears, a new game plays several
    turns normally, and no tutorial trigger fires.
- Phase B: the three :SphereModule:s MUST load via the entry point and the
  sphere economy MUST function.
  - Given a faction (e.g. player index 1 = Life), When a turn begins, Then sphere
    gold is added per mom_turns.slc's formula.
  - When the faction's sphere advance is researched, Then the blessing
    building/unit/gold reward is granted once.
  - When a themed building completes, Then the one-time burst gold is granted.
  - While any referenced symbol is missing from the DBs: the fix happens
    BEFORE launch (module or control plane), never by trusting the engine.
- Phase C: sphere events SHOULD surface as messagebox popups via `mom_msg.slc`
  (strings keyed like NuclearDetente's), included last.
  - Given a granted blessing, When the handler fires, Then a popup with the
    correct scenario string appears.
- Each phase MUST be committed separately, message containing "working", only
  after its :PhaseGate: passes.
- Cross-cutting: `lessons_learned.md` [SLIC] sections MUST be corrected to the
  canonical faction syntax; the SLIC module/function inventory MUST be recorded
  (slic_inventory surface) per control-plane sync rule.
