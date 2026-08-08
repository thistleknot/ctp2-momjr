# Magic Resistance & Immunity Spec

Status: ACTIVE
Created: 2026-08-07
Updated: 2026-08-07
Disposition: Graduated affinities model (v2)

## Summary

Units have RESISTANCE AFFINITIES to spells from opposing spheres. There are NO
total blocks. Every spell has a chance to land against any target — the question
is how likely, not whether it's possible.

## Core Principle: Gradations, Not Walls

**Total blocks = bad.** If a Paladin makes Death Wish impossible, there's no
tension in the matchup. The correct model is graduated resistance:

- High affinity (opposing sphere elite): 80% resist
- Medium affinity (opposing sphere common/aura): 50% resist
- Low affinity (chaos entropy / hero self-save): 20-30% resist
- Artifact bonus: +15% (additive, stacks)

A Death Knight attacking a Paladin-guarded city still has a 20% chance to land
its Death Wish. That 20% is what makes it worth TRYING — and what makes the
defender sweat despite having the "counter" in position.

## Resistance Tiers

| Tier | Resist % | When |
|---|---|---|
| Elite opposing | 80% | Target IS an elite opposing-sphere unit (e.g. Paladin vs death) |
| Aura (strong) | 60% | Co-located elite opposing protector (Paladin on same tile) |
| Aura (moderate) | 40% | Co-located common opposing unit (Guardian Spirit on tile) |
| Chaos entropy | 25% | Target is a chaos creature (blanket, all spells) |
| Hero self-save | 35% | Target is a named hero |
| Lamp artifact | +15% | Target's owner holds the Lamp (additive) |

These DO NOT stack multiplicatively — the system checks in priority order and
uses the HIGHEST applicable tier. The lamp bonus is the only additive element.

## Resolution Order (highest tier wins)

1. Check elite opposing affinity → 80% (+ lamp 15% = 95% max, never 100%)
2. Check aura (strong protector on tile) → 60% (+ lamp = 75%)
3. Check aura (moderate protector on tile) → 40% (+ lamp = 55%)
4. Check chaos entropy → 25% (+ lamp = 40%)
5. Check hero self-save → 35% (+ lamp = 50%)
6. Check lamp-only → 15%
7. No protection → 0% (spell always lands)

## The 5-Sphere Affinity Table

| Attacking Sphere | Elite Opposing (80%) | Strong Aura (60%) | Moderate Aura (40%) |
|---|---|---|---|
| Death | Undead + Paladins, Archangel, Arch Mage | Paladins, Archangel on tile | Guardian Spirit, Unicorn, Ariel, Serena on tile |
| Chaos | Storm Drake, Air Elemental, Warlock | Storm Drake, Warlock on tile | Mage, Jafar, Storm Giant on tile |
| Nature | Efreet, Hydra, Infernal Device | Efreet, Hydra on tile | Hell Hounds, Tauron, Warrax on tile |
| Sorcery | Behemoth, Great Wyrm, War Mammoth | Behemoth, Great Wyrm on tile | Warbears, Freya, Alorra on tile |
| Life | Lich, Death Knight, Dracolich | Lich, Dracolich on tile | Wraith, Rjak, Malleus on tile |

## Why No Total Blocks

1. **Tension over certainty.** An 80% resist is scary for the attacker but not
   hopeless. A 100% block removes all decision-making from both sides.
2. **Investment always matters.** The caster spent mana AND positioned their unit.
   A total block means that investment was literally wasted. 80% means it was a
   long shot that might still pay off.
3. **Counter-counter play.** If blocks are total, the metagame collapses to "bring
   the counter or don't bother." With gradations, you can gamble on overwhelming
   force — cast twice, cast at 80% because the 20% payoff is devastating.
4. **Narrative.** A Death Knight's spell punching through a Paladin's ward is a
   story moment. A spell that simply says "immune" is anti-climactic.

## Acceptance Criteria

1. NO spell has 0% chance to land (except against the caster's own units)
2. Maximum resistance is 95% (elite opposing + lamp), never 100%
3. Resolution uses single highest tier + lamp additive
4. All 5 spheres have their affinity table populated
5. Chaos entropy applies against ALL spell spheres (universal low-tier)
6. Generator emits Random(100) < threshold checks, never hard resisted=1 without roll
