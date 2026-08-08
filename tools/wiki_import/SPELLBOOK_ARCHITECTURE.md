# Paged Spellbook — Generator Architecture

## Status: BLOCKED on Phase 0 in-game verification

The flat `MomCastSpell` dispatcher is built but unverified. Once the user confirms
Flame Strike casts without 0xC0000005, this architecture becomes implementable.

## Design

The paged spellbook replaces the two hand-wired buttons (Flame Strike, Demon Strike)
with a data-driven UI that pages through `spells.csv` per sphere.

### Constraints (measured, non-negotiable)

- **5 alertbox arms maximum** — a sixth is silently dropped from the tail
- **Close is always arm 0** — enforced by build
- **One-call-depth limit** — all spell logic must be inlined flat
- **Arms are not addressable by LDL string** — only StandardMinimizeButton resolves

### Page Layout

Each page shows 4 spells + 1 navigation arm:
```
[Close]  [Spell A]  [Spell B]  [Spell C]  [Spell D]  ← 5 arms exactly
```

Navigation between pages: "Next Page" replaces the 4th spell slot when there are
more spells than fit on one page. "Prev Page" is arm 1 when not on page 1.

### Data Flow

```
spells.csv (214 rows)
    ↓ filter: sphere == player's sphere AND effect_kind != 'flavour'
    ↓ filter: overland_cost > 0 (combat-only spells not castable overland)
    ↓ rescale: shipped_cost = max(min_cost, wiki_cost * rescale_factor)
    ↓ sort: by research_cost (unlocked order)
    ↓ paginate: groups of 4
    ↓
generator emits per-page alertbox SLIC in mom_spells.slc
    ↓
each arm calls MomCastSpell(p, spellId) with the inlined if-chain
```

### Generator Changes Needed

1. `_emit_spellbook_pages()` — reads `spells.csv`, filters to implementable spells
   per sphere, paginates into groups of 4, emits:
   - One `alertbox` segment per page
   - Button arms with `MomCastSpell(p, <spellId>)` calls
   - Navigation arms for page forward/back
   - scen_str.txt entries for spell names + cost display

2. The hub menu (`MomMsgMagicHub`) gets a sphere-specific spellbook arm that opens
   page 1 of that sphere's book.

3. `validate_scenario.py` extended: every spell referenced in the SLIC exists in
   `spells.csv` and has a valid effect_kind.

### Cost Rescaling (Phase 4)

Wiki costs range 10–5000. The CTP2 pool is 200. `mod_policy.json:spellbook.cost_rescale`:
- `rescale_factor: 0.1` → wiki 100 = shipped 10, wiki 500 = shipped 50
- `min_cost: 10` → floor so no spell is free
- `max_cost: 180` → ceiling so a full pool always affords at least one cast

These are Phase 4 tuning knobs. The architecture just applies them.

### Per-Sphere Spell Counts (from spells.csv, implementable only)

| Sphere | Total | Implementable | Pages needed |
|--------|-------|--------------|-------------|
| Life | 40 | ~38 | 10 |
| Nature | 40 | ~38 | 10 |
| Sorcery | 40 | ~38 | 10 |
| Death | 40 | ~38 | 10 |
| Chaos | 40 | ~38 | 10 |
| Arcane | 14 | ~12 | 3 |

### Unblock Criteria

1. User confirms Phase 0: Flame Strike casts without crash from flat dispatcher
2. That confirmation means: flat `MomCastSpell` + inlined if-chain is the proven shape
3. Generator then emits the full paginated spellbook in that same proven shape
