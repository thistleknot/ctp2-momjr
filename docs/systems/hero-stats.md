# Hero Stats (Power / Fortitude)

## The Four Hero Stats

Heroes gain four stats that modify gameplay systems around them. These stats
don't change the hero's combat values directly — they modify the *systems*
the hero interacts with.

| Stat | Analogue | Effect |
|------|----------|--------|
| Power (INT) | Intelligence | Increases mana generation per turn |
| Command (CHA) | Charisma | Increases experience gain for co-located units |
| Fortitude (CON) | Constitution | Increases magic resistance tier |
| Arcana (WIS) | Wisdom | Increases spell hand draw rate |

## How Stats Grow

Hero stats increase with sphere rung research. Each rung on your sphere's
advance ladder grants +1 to one stat. The distribution follows the sphere's
identity:

| Sphere | Primary Stat | Secondary Stat |
|--------|-------------|---------------|
| Life | Fortitude | Command |
| Nature | Power | Fortitude |
| Sorcery | Arcana | Power |
| Death | Power | Arcana |
| Chaos | Power | Power (double) |

## Stat Effects in Detail

### Power (Mana Generation)

Each point of Power adds directly to `MomMagicPerTurn`. A hero with Power 3
generates 3 extra mana per turn for their owner — equivalent to owning 3
additional mana nodes.

- Scales linearly
- Applies globally (hero doesn't need to be in a city)
- Stacks across multiple heroes

### Command (Experience Boost)

Units co-located with a hero gain experience faster. In CTP2 terms, Command
proxies as: each point of Command has a chance to spawn a veteran-level unit
alongside newly produced units in the hero's city.

- Requires hero to be garrisoned in a city
- Only affects units produced in that city
- Higher Command = more frequent veteran spawns

### Fortitude (Resistance)

Each point of Fortitude raises the hero's personal resistance tier. At base,
heroes have the "hero self-save" tier (35%). With Fortitude:

| Fortitude | Effective Resistance |
|-----------|---------------------|
| 0 | 35% (base hero tier) |
| 1-2 | 45% |
| 3-4 | 55% |
| 5+ | 65% |

This stacks with the Lamp artifact (+15%) for a maximum hero resistance of 80%.

### Arcana (Draw Rate)

Arcana increases the number of spells drawn into your hand each turn:

| Arcana | Bonus Draws |
|--------|------------|
| 0-2 | +0 |
| 3-4 | +1 |
| 5-6 | +2 |
| 7+ | +3 |

More draws = more options each turn = more consistent access to key spells.

## Why Indirect Effects?

CTP2's engine doesn't support runtime modification of unit stats (no SetAttack
builtin). The hero stat system works by modifying the *systems around* the hero:

- Power → modifies the mana pool (a global array)
- Command → spawns veteran units (CreateUnit)
- Fortitude → modifies resistance thresholds (checked during spell resolution)
- Arcana → modifies hand draw count (BeginTurn handler)

This is the TRIZ Parameter Change principle: stats don't modify the unit directly,
they modify the systems the unit participates in.
