# Mana Economy

## The Three Numbers

Every player's magic state is defined by three values:

| Value | Meaning |
|-------|---------|
| MomMagicCur | Current mana available to spend |
| MomMagicMax | Maximum pool capacity |
| MomMagicPerTurn | Mana gained each turn |

## Generation Formula

Each turn, your mana generation is recalculated:

```
Base = MAGIC_BASE_PER_TURN (fixed constant)
Pop  = sum(city_population) * MAGIC_POP_COEF
Nodes = count(mana_nodes) * MANA_NODE_BONUS
Raw  = Base + Pop + Nodes
Final = Raw * SchoolPct / 100
```

Then: `MomMagicCur = min(MomMagicCur + Final, MomMagicMax)`

## School Multipliers

Your sphere determines your multiplier and max capacity:

| School | Multiplier | Max Pool | Identity |
|--------|-----------|----------|----------|
| Life | 100% | 200 | Balanced baseline |
| Nature | 110% | 220 | Slightly above average |
| Death | 115% | 240 | Efficient dark power |
| Sorcery | 125% | 260 | Best efficiency |
| Chaos | 140% | 300 | Highest raw generation |

The multiplier is set when you research your sphere's entry advance (e.g.,
researching "Life Magic" sets your school to Life with 100%/200).

## Mana Sources

### Base Generation
A fixed per-turn income that everyone gets regardless of empire size.

### Population
More citizens across your cities = more magical power. Expanding your empire
directly increases mana income.

### Mana Nodes
Gold and Gems resource tiles within your city radius act as mana nodes. Each
node adds a flat bonus per turn. Controlling territory with resources is
strategically valuable beyond just gold income.

### Hero Power Stat
Each point of hero Power adds directly to MomMagicPerTurn. A hero with Power 3
is equivalent to owning 3 extra mana nodes.

## Spending Mana

Mana is spent on:
1. **Casting spells** — immediate deduction from MomMagicCur
2. **Creature upkeep** — ongoing drain per turn per summoned unit
3. **(Future) Enchantment upkeep** — ongoing drain per active enchantment

## The Budget Problem

When two spends share one pool, the cheaper one can starve the expensive one.
Example: if your war-chest gold-conversion costs 50 and your summon costs 75,
the war-chest fires first every time (pool crosses 50 before 75).

The solution: expensive operations (summoning) are guarded by sustainability
checks. The AI won't spend on cheap alternatives if it can afford something
better that advances its position.

## Mana Starvation

Signs you're mana-starved:
- Pool never reaches casting threshold
- Summoned creatures dying because you can't afford upkeep
- Turns passing without any magical action

Fixes:
- Expand cities (more population = more generation)
- Control mana node tiles
- Research deeper sphere rungs (higher multiplier)
- Dismiss expensive summoned creatures to free upkeep

## Strategic Advice

- **Don't hoard past max.** Generation above max is wasted.
- **Summon within budget.** Total upkeep should be < 80% of per-turn generation.
- **Nodes are objectives.** Fight for resource-rich territory.
- **Chaos burns hot.** 140% multiplier means Chaos can outspend everyone short-term
  but runs dry faster when overcommitted.
- **Sorcery sustains.** 125% with 260 max means Sorcery has the best long-game
  mana position.
