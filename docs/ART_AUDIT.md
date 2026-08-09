# Art Audit — Units with Wrong Icons

Status: ACTIVE (vision model classified 2026-08-08)
Created: 2026-08-08

The vision model (nvidia/nemotron-3-nano-omni-30b) classified each icon. The
sort-order bug is fixed — 7 of the original 10 "wrong" were actually the
cropping mismatch. The remaining mismatches are REAL art problems in the TGA files.

## Confirmed WRONG (needs replacement)

| Unit | Vision Model Says | Should Be | Priority |
|------|-------------------|-----------|----------|
| UNIT_PRIEST | "Holding a large axe" | Robed healer with staff | HIGH |
| UNIT_ORC | "Grey wolf with red collar" | Orc warrior (humanoid, brutish, green) | HIGH |
| UNIT_OGRE | "Riding a white horse" | Large brutish humanoid (club, massive) | HIGH |
| UNIT_DJINN | "Person riding grey horse with bow" | Floating genie/spirit (ethereal) | HIGH |
| UNIT_SETTLER | "Bearded mage in red robes" | Civilian/pioneer (cart, tools) | HIGH |
| UNIT_CARAVAN | "Turkey carrying rider and cargo" | Trade wagon/pack animal | MED |
| UNIT_BONE_GOLEM | "Skeleton warrior with sword and shield" | Bone construct (golem shape, not humanoid fighter) | MED |

## Needs Verification (human eye)

| Unit | Vision Model Says | Concern |
|------|-------------------|---------|
| UNIT_EFREET | "Female mage with fire legs" | Supposed to be fire genie/djinn — close? |
| UNIT_SERENA | "Horse rider" | Life hero, should be healer/support not mounted |
| UNIT_DRUID | "Druid in armor holding a staff" | Human said pikeman, model said druid. Check in-game. |
| UNIT_GOBLIN | (API timeout) | Human said "transparency/chainmail on board" |

## Confirmed CORRECT by Vision Model (44 units)

Peasants, Zombies, Spearmen, Swordsmen, Phantom Warriors, Warbears, Warlock,
Jafar, Rjak, Freya, Centaurs, Mage, Wyvern, Knights, Unicorn, Iron Golem,
Wraith, Griffin, Galley, Warship, Hydra, Airship, Minotaur, War Troll,
Gargoyle, Guardian Spirit, Salamander, War Mammoth, Storm Giant, Air Elemental,
Storm Drake, Great Wyrm, Behemoth, Merfolk, Archangel, Lamp, War Mage,
Arch Mage, Dwarf Runesmith, Treant, Crystal Golem, Vampire, Troll, Drow

Plus 4 KNOWN_GOOD (human confirmed): Paladins, Pegasus, Elven Archers, Catapult

## Not Classified (API errors)

Hell Hounds, Steam Cannon, Cockatrice, Infernal Device, Undead Dragon,
Death Knight, Lich, Dwarf Crossbow, Goblin

## LotR Catalog (partial — 33 of 458 classified before timeout)

| Index | Description | Potential Proxy For |
|-------|-------------|---------------------|
| 100 | Man holding fishing rod | Peasants/Settler |
| 101 | Soldier holding yellow shield | Spearmen |
| 102-107 | Various armored soldiers/archers | Infantry pool |
| 108_1 | Skeleton knight in armor | Death Knight / Bone Golem |
| 109 | Skeleton holding spears | Skeletons |
| 110 | Knight with spear and shield | Crusader / Templar |
| 111-112 | Archers | Elven Archers / Dwarf Crossbow |
| 115-116 | Horse riders | Knights / Crusader |

## Root Cause

Most mismatches are units added in v5+ (Priest, Orc, Ogre, Djinn, Bone Golem,
Goblin) that were given `art_cell_index` values pointing to TGA slots containing
art for DIFFERENT units. The original units (pre-v5) are mostly correct.

## Fix Path

1. For each WRONG unit, expand the HoMM2/LotR/MoMJR sheets in the mkdocs guide
2. Human picks the best match from available source art
3. Extract that source cell, convert to ARGB1555 TGA at 160x120
4. Write to the correct `CM2_UPAP{art_idx}L.TGA`
5. Regenerate observer sheet + docs icons
6. Re-run vision audit to confirm

## Next Steps

- Complete LotR classification (458 total, 33 done)
- Classify HoMM2 sheet cells
- Build proxy recommendation matrix: for each WRONG unit, rank candidates by
  description similarity from all 3 source mods
