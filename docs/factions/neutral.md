# Neutral — Dwarves & Mercenaries

Neutral units belong to no sphere. They're available to any faction that
researches the correct mundane advances. They form the backbone infrastructure:
settlers, siege, naval, and the terrain-gated Dwarves.

## Identity

- **Theme**: Technology, craftsmanship, civilization
- **No sphere alignment**: Available to all factions equally
- **Gate**: Advance prerequisites (not sphere ladder)
- **Dwarves**: Additionally gated by mountain/hill terrain

## Unit Roster

### Common Units (any faction)

| Unit | Role | Atk | Def | HP | FP | Move | Domain | Prereq |
|------|------|-----|-----|----|----|------|--------|--------|
| Peasants | Scout | 0 | 1 | 2 | 1 | 1 | Land | — |
| Spearmen | Basic defense | 1 | 1 | 1 | 1 | 1 | Land | — |
| Swordsmen | Basic melee | 2 | 2 | 1 | 1 | 1 | Land | Bronze Working |
| Knights | Cavalry | 4 | 2 | 1 | 1 | 2 | Land | Chivalry |
| Catapult | Siege | 6 | 1 | 1 | 1 | 1 | Land | Mathematics |
| Steam Cannon | Heavy siege | 10 | 2 | 2 | 2 | 1 | Land | Artificing |
| Iron Golem | Construct tank | 8 | 5 | 4 | 1 | 1 | Land | Thaumaturgy |
| Settler | City founder | 0 | 2 | 2 | 1 | 1 | Land | — |
| Caravan | Trade | 0 | 1 | 1 | 1 | 1 | Land | Trade |

### Naval Units

| Unit | Role | Atk | Def | HP | FP | Move | Domain | Prereq |
|------|------|-----|-----|----|----|------|--------|--------|
| Galley | Transport | 1 | 1 | 1 | 1 | 3 | Sea | Map Making |
| Warship | Naval combat | 7 | 3 | 2 | 1 | 4 | Sea | Sea Mastery |

### Air Units

| Unit | Role | Atk | Def | HP | FP | Move | Domain | Prereq |
|------|------|-----|-----|----|----|------|--------|--------|
| Airship | Fast recon | 5 | 1 | 1 | 1 | 6 | Air | Artificing |

### Mage Units (Proximity Casting)

| Unit | Role | Atk | Def | HP | FP | Move | Range | Prereq |
|------|------|-----|-----|----|----|------|-------|--------|
| War Mage | Tactical caster | 4 | 2 | 1 | 1 | 1 | 1 tile | Rune Lore |
| Arch Mage | Strategic caster | 6 | 3 | 2 | 2 | 1 | 2 tiles | Wizardry |

### Dwarves (Mountain-Gated)

| Unit | Role | Atk | Def | HP | FP | Move | Prereq | Terrain |
|------|------|-----|-----|----|----|------|--------|---------|
| Dwarf Warrior | Melee tank | 4 | 5 | 3 | 1 | 1 | Iron Working | Hill/Mountain |
| Dwarf Crossbow | Ranged | 3 | 3 | 2 | 2 | 1 | Masonry | Hill/Mountain |
| Dwarf Runesmith | Magic-resist | 5 | 6 | 3 | 1 | 1 | Thaumaturgy | Hill/Mountain |

## Dwarves: The Mountain Question

Dwarves are NOT a sphere. They're a **resource** — like iron deposits or mana
nodes. They exist where mountains are. Any faction that holds mountain territory
and researches the right advance can recruit them.

This matches the original MoM design: dwarves are a neutral race recruitable by
any wizard who conquers their cities.

### Terrain Gate

A city must be on hill or mountain terrain to build Dwarf units. The
`mod_CanCityBuildUnit` check verifies terrain type before allowing production.

### Dwarf Runesmith

The Runesmith deserves special mention: 5 attack, 6 defense, and 50% base magic
resistance. She's the best anti-magic unit available to all factions — expensive
to reach (Thaumaturgy requires deep mundane research) but worth it against
spell-heavy opponents.

## The Lamp

| Unit | Role | Atk | Def | HP | FP | Move | Prereq |
|------|------|-----|-----|----|----|------|--------|
| Lamp | Artifact carrier | 0 | 1 | 1 | 1 | 0 | — |

The Lamp is a unique immobile artifact unit that grants +15% spell resistance to
its owner's armies. See [Artifacts](../systems/artifacts.md) for details.

## Strategic Role

Neutral units fill gaps that sphere rosters don't cover:
- **Settlers** — only way to found new cities
- **War Mage / Arch Mage** — required for proximity casting (all factions need these)
- **Knights** — solid cavalry before sphere-specific elite unlock
- **Steam Cannon** — late-game siege when creature attacks won't break walls
- **Dwarves** — the best conventional infantry available to anyone with mountains
