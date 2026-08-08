# Unit-Spell Binding Spec

Status: ACTIVE
Created: 2026-08-07
Disposition: Design complete, implementing Phase 1

## Summary

Each spell is tied to a specific unit type as its "caster proxy." The unit must
exist in the player's army AND be within range of the target for the spell to
resolve its full effect. This turns army composition into a spell-selection
decision and makes each elite creature a high-value chess piece.

## Design Principles

1. **The unit IS the spell.** Owning a Death Knight means you CAN cast Death Wish.
   Losing it means you can't until you rebuild/resummon.
2. **Position is permission.** The bound unit must be within Distance() range of
   the target — same proximity system as War Mage/Arch Mage (already shipped).
3. **Fallback, not lockout.** If the required unit is absent, the spell still
   "fires" but does a reduced/generic effect (mana deducted, message shown, no
   real damage). The player isn't punished for clicking — they just don't get the
   signature effect.
4. **Strength-weighted targeting.** Offensive spells that kill a unit select
   intelligently: iterate enemy units at the target, weight by attack strength,
   sample the strongest (or weakest for plague/death effects).
5. **AI awareness.** The AI caster (MomSpellAICast) checks unit presence before
   choosing which spell to fire. No change to AI movement yet — that's Phase 2.

## Range Model (inherited from proximity-gated casting)

| Caster Unit Type | Range | Role |
|---|---|---|
| Any unit (generic) | 0 | Self-buffs only |
| UNIT_WAR_MAGE | 1 | Tactical (adjacent city) |
| UNIT_ARCH_MAGE | 2 | Strategic (2-tile artillery) |
| Bound signature unit | per binding | Spell-specific |

The targeting preamble already scans all player units. The extension: for each
signature spell, scan for the SPECIFIC bound unit and check its distance to the
target independently of the generic mage scan.

## Phase 1 Binding Table (10 signatures)

| SpellId | Spell Name | Sphere | Required Unit | Unit Range | Effect |
|---|---|---|---|---|---|
| 108 | Death Wish | death | UNIT_DEATH_KNIGHT | 1 | Kill strongest enemy unit at target city |
| 100 | Black Wind | death | UNIT_WRAITH | 1 | Kill weakest enemy unit at target city |
| 106 | Cruel Unminding | death | UNIT_LICH | 1 | Drain 30 mana from target player |
| 126 | Fire Storm | chaos | UNIT_EFREET | 2 | Spawn Hell Hounds at enemy city |
| 128 | Call the Void | chaos | UNIT_GREAT_WYRM | 2 | Kill 2 enemy units at target (apocalyptic) |
| 47 | Earthquake | nature | UNIT_BEHEMOTH | 1 | Spawn War Troll at enemy city (siege proxy) |
| 51 | Ice Storm | nature | UNIT_STORM_GIANT | 2 | Spawn Warbears at enemy city |
| 78 | Stasis | sorcery | UNIT_STORM_DRAKE | 2 | Spawn Phantom Warriors at target (freeze proxy) |
| 85 | Spell Binding | sorcery | UNIT_WARLOCK | 2 | Drain 50 mana from target player |
| 83 | Great Unsummoning | sorcery | UNIT_AIR_ELEMENTAL | 2 | Kill 1 enemy unit at target |

## Effect Implementation Details

### KillUnit targeting (strength-weighted)

```
// Iterate units at tgtLoc, find the one with highest .attack
// Then KillUnit(bestUnit)
bestAtk = 0;
for (k = 0; k < GetUnitsAtLocation(tgtLoc); k = k + 1) {
    GetUnitFromCell(tgtLoc, k, tmpKillUnit);
    if (tmpKillUnit.attack > bestAtk) {
        bestAtk = tmpKillUnit.attack;
        killTarget = tmpKillUnit;
    }
}
if (bestAtk > 0) {
    KillUnit(killTarget);
}
```

For "kill weakest" — invert: find LOWEST .attack > 0.
For "kill N" — loop N times, each time find strongest remaining.

### Mana drain

```
// Target is the player who owns the targeted city
// player[2] was set to the city owner during targeting
MomMagicCur[player[2]] = MomMagicCur[player[2]] - 30;
if (MomMagicCur[player[2]] < 0) {
    MomMagicCur[player[2]] = 0;
}
```

### Spawn at target (existing pattern)

```
CreateUnit(p, UnitDB(UNIT_HELL_HOUNDS), tgtLoc, 0);
```

## Generator Changes

In `_emit_spell_effects()`, add a lookup table `SPELL_BINDINGS`:

```python
SPELL_BINDINGS = {
    108: {"unit": "UNIT_DEATH_KNIGHT", "range": 1, "effect": "kill_strongest"},
    100: {"unit": "UNIT_WRAITH", "range": 1, "effect": "kill_weakest"},
    ...
}
```

For each bound spell, the generator emits:
1. A unit-specific scan (does player own UNIT_X within range of target?)
2. The signature effect body (KillUnit / CreateUnit / mana drain)
3. Fallback: if unit not present or not in range, show "requires X" message

## Strings Needed

- MOM_MSG_NO_REQUIRED_UNIT  "This spell requires a specific unit in range. Check the Great Library for details."
- Unit description updates in GL: "The Death Knight can channel the Death Wish spell when adjacent to an enemy city."

## SLIC Constraints

- KillUnit(unit_t) is base-verified (used in AlexanderTheGreat extensively)
- GetUnitFromCell(location, index, out_unit) is base-verified
- GetUnitsAtLocation(location) returns count — base-verified
- All targeting logic MUST remain inlined in MomCastSpell (call-depth budget)
- The unit scan adds ~15 lines per signature spell to the generated file

## Phase 2 (future)

- AI moves signature units toward enemy cities before casting
- Dynamic spellbook text showing which spells are "ready" (unit in position)
- More bindings (expand from 10 to 30+ as each gets gameplay-tested)
- Consumed-on-cast variants (scroll units)

## Acceptance Criteria

1. Generator emits 10 signature spell bodies with unit-type + range checks
2. Each signature spell has a real effect (KillUnit, CreateUnit, or mana drain)
3. Absence of required unit shows a clear feedback message
4. Audit passes (FAIL: 0)
5. Turnloop 5 turns clean (0 SLIC errors)
6. Unit GL descriptions updated to mention spell portfolio
