# Enchant Stacking

## Cumulative Power

Global and city enchantments can be **stacked** — casting the same enchantment
multiple times amplifies its effect. This adds a mana investment dimension:
do you diversify across many enchantments, or concentrate power into a few
deeply-stacked ones?

## How Stacking Works

1. Cast an enchantment normally (first layer)
2. Cast the same enchantment again while the first is active
3. The effect multiplies by the stack count
4. Each recast costs more mana than the previous

### Cost Scaling

| Stack Level | Cost Multiplier |
|------------|----------------|
| 1st cast | 1x (base cost) |
| 2nd cast | 1.5x |
| 3rd cast | 2x |

### Stack Cap

Maximum 3 stacks per enchantment. Beyond that, you must diversify.

## Dispel Interaction

When an opponent casts Dispel/Disjunction against your stacked enchantment:

- A successful dispel removes **one stack**, not the entire enchantment
- To fully remove a 3-stack enchantment requires 3 successful dispels
- This makes deeply-invested enchantments more durable

## Strategic Implications

**Concentrating** (few enchantments, high stacks):
- Harder for enemies to fully dispel
- More powerful per-enchantment effect
- Expensive (escalating costs)
- Vulnerable if the one enchantment IS dispelled

**Diversifying** (many enchantments, 1 stack each):
- Broader coverage
- Each individual enchantment is easy to dispel
- Cheaper per cast
- Opponent must spend many dispels to clear everything

## Example: Just Cause (Life)

| Stack | Cost | Effect |
|-------|------|--------|
| 1 | 150 mana | -1 Unrest all cities, +10 Fame |
| 2 | 225 mana (total 375) | -2 Unrest all cities, +20 Fame |
| 3 | 300 mana (total 675) | -3 Unrest all cities, +30 Fame |

A 3-stack Just Cause transforms your empire's happiness, but costs 675 total mana
and requires 3 hand draws of the same spell.

## The MtG Parallel

This is equivalent to MtG's cumulative enchantments and devotion mechanics.
Investing deeper into one color (sphere) rewards you with compounding effects.
The difference: MtG enchantments are unique permanents. Here, the same spell
cast repeatedly builds power.

## Interaction with Spell Hand

Since you draw spells randomly, getting the same spell in hand multiple times
requires either:
- A small spellbook (fewer researched spells = higher repeat chance)
- Multiple turns of holding the spell without casting
- High draw rate (Arcana stat)

This creates a natural gating: deep stacks require patience and focus.
