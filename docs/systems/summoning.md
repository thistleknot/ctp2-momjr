# Summoning

## How Summoning Works

Summoning spells create units from mana rather than city production. The summoned
creature appears at your **Summoning Circle** — a unique city feature that defines
where magical beings materialize.

## The Summoning Circle

- Every wizard starts with a Summoning Circle in their capital
- It can be relocated with the Spell of Return (1000 mana)
- All summons appear at the circle's location
- It's neither a building nor an enchantment — it's a unique feature

## Summoning Costs

Summoning spells have two costs:
1. **Casting cost** — mana spent immediately
2. **Upkeep** — mana drained per turn while the unit lives

| Example | Cast Cost | Upkeep/turn | Sphere |
|---------|-----------|-------------|--------|
| Magic Spirit | 30 | 1 | Arcane |
| Hell Hounds | 40 | 1 | Chaos |
| War Bears | 70 | 2 | Nature |
| Wraiths | 500 | 5 | Death |
| Storm Drake | 1000 | 25 | Sorcery |
| Great Drake | 900 | 30 | Chaos |
| Arch Angel | 950 | 20 | Life |

## Summoning vs Building

| Aspect | Summoning | City Building |
|--------|-----------|---------------|
| Cost type | Mana | Production (shields) |
| Appears at | Summoning Circle only | The producing city |
| Speed | Instant (one cast) | Multiple turns |
| Upkeep | Mana per turn | Gold per turn |
| Availability | Need spell in hand + mana | Need advance + city |
| Heroes | Summon-only | Never buildable |

## AI Summoning

AI wizards follow the same rules:
1. Check if power >= summon cost + sustainability threshold
2. Pick the strongest affordable summon
3. Create the unit at a valid city location
4. Track upkeep against future income

The AI won't summon if it can't sustain the upkeep — it checks whether ongoing
costs will starve its pool.

## Summon Hero / Summon Champion

Two arcane summoning spells bring heroes:

| Spell | Cost | Research | Effect |
|-------|------|----------|--------|
| Summon Hero | 300 | 500 | Summons a non-Champion hero |
| Summon Champion | 750 | 1250 | Summons a Champion-tier hero |

These draw from your sphere's hero pool based on which advances you've researched.
If you haven't unlocked a hero's prerequisite advance yet, that hero won't appear.

## Summoning Strategy

- **Early game**: Magic Spirit for scouting (cheap, 1 upkeep)
- **Mid game**: Sphere-specific creatures (War Bears, Hell Hounds)
- **Late game**: Ultimate creatures (Storm Drake, Arch Angel, Demon Lord)
- **Heroes**: Summon early heroes as soon as you hit rung 2

Watch your upkeep budget. A 300-mana pool generating 15/turn can sustain ~15
points of creature upkeep before going negative. Oversummoning leads to mana
starvation.
