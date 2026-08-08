# Resistance & Affinities

## Core Principle: Gradations, Not Walls

There are **no total blocks** in the resistance system. Every spell has a chance
to land against any target. The question is how likely, not whether it's possible.

Why no total blocks?

1. **Tension over certainty.** An 80% resist is scary but not hopeless. A 100%
   block removes all decision-making.
2. **Investment always matters.** The caster spent mana and positioned units. Total
   blocks waste that investment entirely.
3. **Counter-counter play.** With gradations, you can gamble on overwhelming force.
   Cast twice at 80% because the 20% payoff is devastating.
4. **Narrative.** A Death Knight's spell punching through a Paladin's ward is a
   story moment. "Immune" is anti-climactic.

## Resistance Tiers

The system checks in priority order and uses the **highest applicable tier**:

| Tier | Resist % | When |
|------|----------|------|
| Elite opposing | 80% | Target IS an elite opposing-sphere unit |
| Aura (strong) | 60% | Co-located elite opposing protector |
| Aura (moderate) | 40% | Co-located common opposing unit |
| Hero self-save | 35% | Target is a named hero |
| Chaos entropy | 25% | Target is a chaos creature (blanket) |
| Lamp artifact | +15% | Additive bonus (stacks with above) |
| No protection | 0% | Spell always lands |

**Maximum possible resistance: 95%** (elite opposing 80% + Lamp 15%). Never 100%.

## Resolution Order

```
1. Is target an elite opposing unit? → 80% (+ lamp = 95%)
2. Is there an elite opposing protector on the same tile? → 60% (+ lamp = 75%)
3. Is there a common opposing unit on the same tile? → 40% (+ lamp = 55%)
4. Is target a hero? → 35% (+ lamp = 50%)
5. Is target a chaos creature? → 25% (+ lamp = 40%)
6. Does target's owner hold the Lamp only? → 15%
7. No protection → 0%
```

Tiers do NOT stack multiplicatively. The system finds the highest applicable
tier, adds the Lamp bonus if present, and rolls once.

## The Five-Sphere Affinity Table

| Attacking Sphere | Elite Opposing (80%) | Strong Aura (60%) | Moderate Aura (40%) |
|-----------------|---------------------|-------------------|---------------------|
| Death | Paladins, Archangel, Arch Mage | Paladins, Archangel on tile | Guardian Spirit, Unicorn on tile |
| Chaos | Storm Drake, Air Elemental, Warlock | Storm Drake, Warlock on tile | Mage, Storm Giant on tile |
| Nature | Efreet, Hydra, Infernal Device | Efreet, Hydra on tile | Hell Hounds on tile |
| Sorcery | Behemoth, Great Wyrm, War Mammoth | Behemoth, Great Wyrm on tile | Warbears on tile |
| Life | Lich, Death Knight, Dracolich | Lich, Dracolich on tile | Wraith on tile |

## Practical Examples

**Scenario: Death Wish targeting a city garrisoned by Paladins**

- Death Wish is a Death sphere spell
- Paladins are elite Life units (opposing Death)
- Resistance: 80%
- With Lamp: 95%
- The Death Knight still has a 5-20% chance to land the kill

**Scenario: Fire Storm targeting an unprotected city**

- Fire Storm is a Chaos sphere spell
- No opposing units present
- Resistance: 0%
- Spell lands guaranteed (then damage is calculated separately)

**Scenario: Stasis targeting a city with Warbears**

- Stasis is a Sorcery spell
- Warbears are common Nature units (opposing Sorcery)
- Resistance: 40% (moderate aura)
- 60% chance the spell lands fully

## Army Composition as Defense

Your resistance posture is determined by what units you garrison:

- **Pure defense**: Stack elite opposing units in key cities
- **Balanced**: Mix unit types for moderate coverage against all spheres
- **Aggressive**: Accept vulnerability, invest in offense instead

The aura system means a single Paladin protects its entire city garrison against
Death magic. Positioning one protector strategically can cover multiple fronts.
