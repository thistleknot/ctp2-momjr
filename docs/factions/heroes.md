# Heroes

Heroes are queen-pieces: powerful, unique-feeling, summon-only. They never appear
in city build queues. The only path to a hero is through the spellbook.

## Core Rules

1. **CantBuild.** All named heroes have the CantBuild flag. They never appear in
   any city's production queue.
2. **Summon-only.** Heroes come through spellbook summon spells (Summon Hero,
   Summon Champion, or sphere-specific summons).
3. **Ladder-gated.** Each hero is tied to a specific advance on the sphere ladder.
   Early heroes at rung 1-2, late heroes at rung 4-5.
4. **Not truly unique.** You CAN have two of the same hero if you summon twice.
   The cost (mana + draw luck) is the scarcity, not an engine-enforced cap.

## Hero Roster

| Hero | Sphere | Stats | Move | Prereq | Ladder Position |
|------|--------|-------|------|--------|----------------|
| Serena | Life | 3a/4d/2h/1f | 2 | Life Lore (Inv) | Early (rung 2) |
| Ariel | Life | 3a/8d/2h/2f | 2 | Life Wizard (Too) | Late (rung 5) |
| Freya | Nature | 4a/5d/2h/2f | 3 | Nature Lore (Plu) | Early (rung 2) |
| Alorra | Nature | 6a/2d/2h/1f | 2 | Nature Wizard (Rec) | Late (rung 5) |
| Jafar | Sorcery | 6a/4d/2h/2f | 4 | Sorcerous Lore (The) | Early (rung 2) |
| Rjak | Death | 6a/6d/2h/2f | 2 | Death Lore (Rfg) | Early (rung 2) |
| Malleus | Death | 8a/2d/2h/1f | 2 | Death Master (SE) | Late (rung 6) |
| Tauron | Chaos | 8a/3d/2h/3f | 2 | Chaos Lore (MP) | Early (rung 2) |
| Warrax | Chaos | 8a/3d/2h/2f | 2 | Chaos Wizard (Min) | Late (rung 5) |

## Early vs Late Heroes

**Early heroes** (rung 2) are available shortly after entering your sphere's
magic ladder. They're strong for their timing but not dominant:
- Serena (Life): defensive support, 4 defense
- Freya (Nature): mobile, 3 move speed
- Jafar (Sorcery): fastest hero in the game, 4 move
- Rjak (Death): balanced fighter, 6/6 attack/defense
- Tauron (Chaos): highest firepower (3), raw damage

**Late heroes** (rung 5-6) require deep sphere investment but are powerhouses:
- Ariel (Life): 8 defense, nearly unkillable tank
- Alorra (Nature): 6 attack glass cannon
- Malleus (Death): 8 attack assassin
- Warrax (Chaos): 8 attack bruiser

Sorcery only has one hero (Jafar) — they rely on summoned creatures and control
instead of hero power.

## Heroes as Aura Emitters

Heroes of a sphere serve as mobile resistance aura sources:
- Ariel (Life) protects nearby units against Death magic
- Freya (Nature) protects nearby units against Sorcery magic
- Tauron (Chaos) protects nearby units against Nature magic
- Rjak (Death) protects nearby units against Life magic
- Jafar (Sorcery) protects nearby units against Chaos magic (moderate)

Positioning a hero with your army provides the "strong aura" tier (60% resistance
against the opposing sphere) for all co-located units.

## Losing and Resuming Heroes

When a hero dies:
- They're gone from the map immediately
- They can be resummoned (same spell, same mana cost)
- No permanent death — just the cost of resummoning
- Think of it as: heroes are powerful spirits you channel, not mortal beings

## The Scarcity Design

Why heroes are summon-only instead of buildable:

- **Drama.** Each hero summon is a meaningful event, not routine production.
- **Investment.** You spend mana (which could fund other spells) to call a hero.
- **Positioning.** Heroes appear at your Summoning Circle, not at arbitrary cities.
- **Hand luck.** You need to draw the summon spell. This prevents guaranteed timing.
- **Counter-play.** Opponents can see your hero and prioritize killing it, knowing
  the resummon cost is real.
