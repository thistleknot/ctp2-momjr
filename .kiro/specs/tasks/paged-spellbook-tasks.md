# Paged Spellbook Implementation Tasks

Spec: `Scenarios/mom/.kiro/specs/mom-wiki-import.spec.md` + `SPELLBOOK_ARCHITECTURE.md`
Phase 0 confirmed: 20-turn soak, 0 crashes, 0 SLIC errors (run 20260806-155447).

## Tasks

### 1. Add `_emit_spellbook_pages()` to ctp2_generator.py
- [ ] Read `spells.csv` and filter: `effect_kind != 'flavour'` AND `overland_cost > 0`
- [ ] Group by sphere, apply cost rescaling from `mod_policy.json:spellbook.cost_rescale`
- [ ] Sort each sphere's spells by `research_cost` (unlock order)
- [ ] Paginate into groups of 4 spells per page
- [ ] Emit SLIC alertbox segments per page with: Close arm + 4 spell arms (or 3 + Next Page)
- [ ] Each spell arm body: `MomCastSpell(player[0], <spellId>);` (flat, one call level)
- [ ] Add `scen_str.txt` entries for each spell name + cost display string
- [ ] Wire the call into the main generation flow (after `_emit_mom_gating_slc`)
Dependencies: spells.csv exists, mod_policy.json has spellbook config

### 2. Emit per-spell effect bodies in MomCastSpell if-chain
- [ ] For each implementable spell, add an `elseif (spellId == N)` branch in the if-chain
- [ ] `summon` spells: `CreateUnit(p, UnitDB(UNIT_X), city.location, 0)`
- [ ] `instant_damage` spells: find nearest enemy city, reduce gold/pop (use existing pattern)
- [ ] `unit_enchant`/`city_enchant`/`global_enchant`: stub with Message (implement later)
- [ ] `dispel`: stub with Message (implement later)
- [ ] All branches: deduct `shipped_cost` from `MomMagicCur[p]`
Dependencies: Task 1 complete

### 3. Wire hub menu to sphere-specific spellbook page 1
- [ ] In `mom_msg.slc`, update `MomMsgMagicHub` to open the player's sphere spellbook page 1
- [ ] Remove the old hand-wired Flame Strike / Demon Strike button arms
- [ ] Keep the existing summon/artifacts/wishes arms unchanged
Dependencies: Task 1 complete

### 4. Add spell strings to scen_str.txt
- [ ] Generate `ID_MOM_SPELL_<N>_NAME` and `ID_MOM_SPELL_<N>_DESC` for each spell
- [ ] Format: "Spell Name (Cost: N)" for the button label
- [ ] Use the description from spells.csv (wiki-enriched, first 80 chars)
Dependencies: Task 1 complete

### 5. Extend validate_scenario.py for spellbook integrity
- [ ] Check: every spellId referenced in the SLIC if-chain exists in spells.csv
- [ ] Check: every spell's sphere matches the page it appears on
- [ ] Check: no page exceeds 5 arms
- [ ] Check: Close is always arm 0 on every page
Dependencies: Task 1 complete

### 6. Run generator + audit + 20-turn soak test
- [ ] `python ctp2_generator.py` → clean exit
- [ ] `python mom_audit.py` → FAIL: 0
- [ ] `python validate_scenario.py --scenario scen0000` → PASS
- [ ] `python turnloop.py --turns 20` → OK, 0 SLIC errors
- [ ] Verify spellbook alertbox appears and is dismissable without crash
Dependencies: Tasks 1-5 complete
