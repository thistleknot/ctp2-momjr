# Faction Roster Spec

Status: ACTIVE
Created: 2026-08-07
Disposition: Implementing

## Summary

Each sphere gets a full roster of thematic units that define its faction identity.
The roster is tiered by advance prerequisite (early → mid → late game).
Neutral units serve as shared infrastructure available to any tribe.

## Current State (before this change)

- Life: 7 units (mostly summon-tier angels/guardians, lacks buildable infantry)
- Nature: 13 units (strong, well-rounded)
- Sorcery: 7 units (lacks early/mid options)
- Death: 11 units (strong undead roster)
- Chaos: 9 units (missing conventional infantry)
- Neutral: 26 units (7 are B# placeholders to remove)

## Target Roster

### Life — Holy Order (target: 11 units)
| Unit | Role | Stats (a/d/h/f) | Move | Prereq | NEW? |
|------|------|-----------------|------|--------|------|
| Guardian Spirit | Light tank | 1a/5d/3h/1f | 2 | Inv | existing |
| Paladins | Elite melee | 6a/2d/2h/1f | 2 | Ldr | existing |
| Unicorn | Fast cavalry | 3a/6d/2h/1f | 3 | Lab | existing |
| Pegasus | Flyer | 5a/2d/2h/2f | 5 | Las | existing |
| Archangel | Ultimate | 12a/12d/2h/2f | 4 | Mag | existing |
| Priest | Healer/support | 2a/3d/2h/1f | 1 | Gen | NEW |
| Crusader | Heavy infantry | 4a/4d/2h/1f | 1 | Inv | NEW |
| Templar | Elite infantry | 6a/5d/3h/1f | 1 | Lab | NEW |
| (Ariel) | Hero late | — | — | Too | existing CantBuild |
| (Serena) | Hero early | — | — | Inv | existing CantBuild |

### Nature — Fey Court (target: 15 units)
| Unit | Role | Stats | Move | Prereq | NEW? |
|------|------|-------|------|--------|------|
| Warbears | Early melee | 3a/3d/2h/1f | 1 | Plu | existing |
| Centaurs | Fast cavalry | 2a/1d/1h/1f | 2 | Env | existing |
| Elven Archers | Ranged | 3a/1d/1h/1f | 1 | Cor | existing |
| Cockatrice | Flying pest | 6a/1d/1h/3f | 2 | PT | existing |
| Griffin | Fast flyer | 4a/4d/2h/1f | 4 | X4 | existing |
| War Troll | Heavy | 7a/5d/3h/1f | 1 | Tac | existing |
| War Mammoth | Siege | 10a/5d/3h/1f | 2 | Exp | existing |
| Behemoth | Ultimate | 5a/4d/4h/1f | 1 | Rad | existing |
| Great Wyrm | Ultimate | 15a/9d/6h/2f | 2 | Ref | existing |
| Merfolk | Naval | 4a/3d/2h/1f | 4 | U3 | existing |
| Wyvern | Flyer | 8a/4d/2h/2f | 3 | Che | existing |
| Treant | Slow defender | 3a/8d/4h/1f | 1 | Plu | NEW |
| Druid | Caster/support | 3a/3d/2h/1f | 1 | PT | NEW |
| (Freya) | Hero early | — | — | Plu | existing CantBuild |
| (Alorra) | Hero late | — | — | Rec | existing CantBuild |

### Sorcery — Arcane Enclave (target: 11 units)
| Unit | Role | Stats | Move | Prereq | NEW? |
|------|------|-------|------|--------|------|
| Phantom Warriors | Illusion infantry | 3a/1d/1h/2f | 2 | The | existing |
| Mage | Caster | 3a/1d/1h/1f | 1 | X6 | existing |
| Warlock | Elite caster | 12a/2d/2h/2f | 2 | AFl | existing |
| Storm Giant | Heavy | 8a/4d/2h/1f | 2 | NP | existing |
| Air Elemental | Fast flyer | 6a/3d/1h/1f | 8 | X2 | existing |
| Storm Drake | Ultimate flyer | 12a/6d/3h/2f | 5 | Pla | existing |
| Apprentice | Early caster | 2a/1d/1h/1f | 1 | Hor | NEW |
| Crystal Golem | Tank | 4a/6d/3h/1f | 1 | X2 | NEW |
| Djinn | Elite summon | 8a/5d/2h/2f | 3 | Phy | NEW |
| (Jafar) | Hero | — | — | The | existing CantBuild |

### Death — Necropolis (target: 13 units)
| Unit | Role | Stats | Move | Prereq | NEW? |
|------|------|-------|------|--------|------|
| Skeletons | Cheap fodder | 1a/2d/1h/1f | 1 | Rfg | existing |
| Zombies | Slow tank | 2a/2d/2h/1f | 1 | Rfg | existing |
| Wraith | Fast assassin | 4a/3d/2h/1f | 2 | Rob | existing |
| Minion | Weak summon | 0a/0d/1h/1f | 2 | Wri | existing |
| Demon | Flyer | 4a/5d/2h/1f | 2 | SFl | existing |
| Undead Dragon | Air power | 12a/6d/4h/2f | 3 | Sth | existing |
| Dracolich | Elite flyer | 14a/7d/4h/2f | 3 | Sth | existing |
| Death Knight | Elite cavalry | 8a/6d/3h/1f | 2 | Mys | existing |
| Lich | Caster supreme | 6a/8d/3h/2f | 1 | SE | existing |
| Vampire | Life drain | 5a/4d/2h/2f | 2 | Rob | NEW |
| Bone Golem | Construct tank | 4a/7d/4h/1f | 1 | SFl | NEW |
| (Rjak) | Hero early | — | — | Rfg | existing CantBuild |
| (Malleus) | Hero late | — | — | SE | existing CantBuild |

### Chaos — Underworld Horde (target: 13 units)
| Unit | Role | Stats | Move | Prereq | NEW? |
|------|------|-------|------|--------|------|
| Hell Hounds | Fast early | 4a/2d/1h/1f | 1 | MP | existing |
| Minotaur | Melee | 1a/2d/2h/1f | 1 | War | existing |
| Gargoyle | Flyer | 2a/4d/2h/1f | 2 | Med | existing |
| Salamander | Fire melee | 10a/3d/2h/1f | 2 | X5 | existing |
| Efreet | Elite fire | 7a/3d/2h/2f | 1 | Met | existing |
| Hydra | Ultimate | 12a/3d/3h/2f | 1 | Mob | existing |
| Infernal Device | Siege | 99a/0d/1h/1f | 10 | NF | existing |
| Goblin | Cheap swarm | 1a/1d/1h/1f | 2 | MP | NEW |
| Orc | Solid infantry | 3a/2d/2h/1f | 1 | MP | NEW |
| Ogre | Heavy hitter | 6a/3d/3h/2f | 1 | Med | NEW |
| Troll | Regenerating | 5a/4d/3h/1f | 1 | Met | NEW |
| Drow | Fast elite | 4a/3d/2h/2f | 2 | Min | NEW |
| (Tauron) | Hero early | — | — | MP | existing CantBuild |
| (Warrax) | Hero late | — | — | Min | existing CantBuild |

### Neutral — Shared (cleanup B# placeholders)
Remove: B3, B4, B5, B6, B7, B8, B9 (7 placeholder units with no prereq and identical stats)
Keep: Peasants, Spearmen, Swordsmen, Knights, Iron Golem, Catapult, Steam Cannon,
      Galley, Warship, Airship, Caravan, Settler, Lamp, War Mage, Arch Mage,
      Dwarf Warrior, Dwarf Crossbow, Dwarf Runesmith

## New Units Summary (15 total)

| Sphere | Units to Add |
|--------|-------------|
| Life | Priest, Crusader, Templar |
| Nature | Treant, Druid |
| Sorcery | Apprentice, Crystal Golem, Djinn |
| Death | Vampire, Bone Golem |
| Chaos | Goblin, Orc, Ogre, Troll, Drow |

## Proxy Sprites

All new units use existing sprites until proper art is extracted from
H:\games\civ2\HoMM2Mod1.1\Units.gif or commissioned:

| New Unit | Proxy Sprite |
|----------|-------------|
| Priest | SPRITE_GUARDIAN_SPIRIT |
| Crusader | SPRITE_KNIGHTS |
| Templar | SPRITE_PALADINS |
| Treant | SPRITE_WAR_MAMMOTH |
| Druid | SPRITE_MAGE |
| Apprentice | SPRITE_PHANTOM_WARRIORS |
| Crystal Golem | SPRITE_IRON_GOLEM |
| Djinn | SPRITE_AIR_ELEMENTAL |
| Vampire | SPRITE_WRAITH |
| Bone Golem | SPRITE_IRON_GOLEM |
| Goblin | SPRITE_MINION |
| Orc | SPRITE_MINOTAUR |
| Ogre | SPRITE_WAR_TROLL |
| Troll | SPRITE_WAR_TROLL |
| Drow | SPRITE_DEMON |

## B# Placeholder Cleanup

The 7 B# units (B3, B4, B5, B6, B7, B8, B9) have prereq "no" which means they're
already hidden from the build queue (the generator masks "no" prereq units). They
will be removed from units.csv entirely to declutter.

## Acceptance Criteria

1. 15 new units in units.csv with correct sphere/prereq/stats
2. 7 B# placeholders removed
3. Generator produces clean Units.txt with all new units
4. Audit PASS (FAIL: 0)
5. All new sphere units appear in correct tribe's build list
6. Terrain gating still works for dwarves
7. Flight test clean (0 SLIC errors)
