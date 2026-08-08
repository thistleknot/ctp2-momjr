# Proximity & Targeting

## The Core Rule

Magic is spatial. A spell's full effect requires a **caster proxy unit** to be
physically positioned within range of the target. This transforms army
positioning from a combat concern into a casting concern.

## Range Model

| Caster Unit | Range | Role |
|-------------|-------|------|
| Any unit (generic) | 0 | Self-buffs only |
| War Mage | 1 tile | Tactical (adjacent city/army) |
| Arch Mage | 2 tiles | Strategic (artillery range) |
| Signature bound unit | Per binding | Spell-specific |

Range is measured in map tiles (Distance() builtin). A range of 1 means the
caster must be on an adjacent tile to the target. Range 2 means within two tiles.

## Targeting Flow

```
1. Player casts offensive spell at target location
2. System scans all player units on the map
3. For each unit: check if it's a valid caster proxy
4. For each valid proxy: check Distance(proxy, target) <= range
5. If ANY proxy in range → full effect
6. If NO proxy in range → fallback (reduced effect or fail message)
```

## What Counts as a Target

| Spell Type | Target | Example |
|-----------|--------|---------|
| Instant Spell (offensive) | Enemy city or army stack | Earthquake, Fire Storm |
| Town Enchantment | Friendly/enemy city | Heavenly Light, Cursed Lands |
| Unit Enchantment | Specific unit | Bless, Weakness |
| Global Enchantment | No target (global) | Crusade, Armageddon |
| Summoning Spell | Summoning Circle city | All summons |

Global enchantments and summons don't require proximity — they work from anywhere.
Only **targeted offensive spells** need mage positioning.

## The Chess Analogy

Think of your mages as artillery pieces:

- **War Mage** = rook. Medium range, can threaten adjacent territories.
- **Arch Mage** = bishop. Longer range, threatens two tiles out.
- **Signature units** = queen. Specific spells, specific ranges, devastating effect.

Positioning a Death Knight adjacent to an unprotected city is like moving your
queen into striking distance. Add a Paladin to the garrison and the Death Knight's
signature spell (Death Wish) drops from 100% to 20% effectiveness against that
defender.

## Summoning Circle

All summoned units appear at the city containing your **Summoning Circle**. This
is a unique town feature (not a building, not an enchantment). You can relocate
it with the Spell of Return.

Summons don't require proximity — the summoning circle IS the target.

## Fallback Behavior

When a spell fires without a valid caster proxy in range:

- Mana is still deducted (you committed the power)
- A message displays: "This spell requires a specific unit in range"
- No damage/effect occurs
- The spell is consumed from your hand

This is intentional. Casting without positioning is punished. Plan your moves.
