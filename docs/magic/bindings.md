# Unit-Spell Bindings

## The Unit IS the Spell

Each signature spell is bound to a specific unit type. That unit must exist in
your army AND be within range of the target for the spell to deliver its full
effect. This makes each elite creature a high-value chess piece — losing one
means losing access to a capability.

## Design Principles

1. **Ownership = access.** Having a Death Knight means you CAN cast Death Wish.
   Losing it means you can't (until you rebuild/resummon).
2. **Position = permission.** The bound unit must be within range, same as the
   proximity system for War Mage / Arch Mage.
3. **Fallback, not lockout.** Without the required unit, the spell still "fires"
   but does a reduced/generic effect. You're not punished for clicking — you just
   don't get the devastating signature effect.
4. **Strength-weighted targeting.** Offensive kill spells select intelligently:
   they target the strongest (or weakest) enemy unit at the location.

## Phase 1 Binding Table

| Spell | Sphere | Required Unit | Range | Effect |
|-------|--------|--------------|-------|--------|
| Death Wish | Death | Death Knight | 1 | Kill strongest enemy unit |
| Black Wind | Death | Wraith | 1 | Kill weakest enemy unit |
| Cruel Unminding | Death | Lich | 1 | Drain 30 mana from target |
| Fire Storm | Chaos | Efreet | 2 | Spawn Hell Hounds at target |
| Call the Void | Chaos | Great Wyrm | 2 | Kill 2 enemy units |
| Earthquake | Nature | Behemoth | 1 | Spawn War Troll at target |
| Ice Storm | Nature | Storm Giant | 2 | Spawn Warbears at target |
| Stasis | Sorcery | Storm Drake | 2 | Spawn Phantom Warriors |
| Spell Binding | Sorcery | Warlock | 2 | Drain 50 mana from target |
| Great Unsummoning | Sorcery | Air Elemental | 2 | Kill 1 enemy unit |

## How Kill Targeting Works

For "kill strongest" spells (Death Wish, Call the Void, Great Unsummoning):

1. Scan all enemy units at the target location
2. Find the unit with the highest attack value
3. Kill that unit

For "kill weakest" (Black Wind):

1. Scan all enemy units at the target location
2. Find the unit with the lowest attack value > 0
3. Kill that unit

For "kill N" (Call the Void kills 2):

1. Kill strongest
2. Remove it from the list
3. Kill next strongest

## Mana Drain

Cruel Unminding and Spell Binding directly reduce the target player's mana pool:

- Target is the player who owns the targeted city
- Their MomMagicCur drops by the drain amount
- Cannot go below 0

## Spawn Effects

Fire Storm, Earthquake, Ice Storm, and Stasis spawn friendly units at the enemy
location as a proxy for combat effects:

- Hell Hounds, War Trolls, Warbears, Phantom Warriors appear at the target
- They become your units, immediately in enemy territory
- Think of them as the spell's "damage" expressed as a siege force

## Without the Bound Unit

If you cast a signature spell without the required unit in range:

- Mana is deducted
- Message shown: "This spell requires [Unit Name] within range"
- No effect occurs
- The spell is consumed from your hand

Always check your army composition before casting signature spells.

## Great Library Integration

Each bound unit's Great Library entry describes its signature spell:

> "The Death Knight can channel the Death Wish spell when adjacent to an enemy city."

This makes the binding discoverable in-game without requiring external documentation.
