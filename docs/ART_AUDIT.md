# Art Audit — Units with Wrong Icons

Status: ACTIVE
Created: 2026-08-08

These units have incorrect art assigned in-game. The mkdocs player's guide
surfaces the problem; the fix is to reassign TGA files in the icon pipeline.

Use the expandable reference sheets (MoMJR, HoMM2, LotR) on the Units page
to pick replacements.

## Confirmed Wrong (from human review)

| Unit | Current Icon Shows | Should Show | Source Index |
|------|--------------------|-------------|--------------|
| UNIT_PRIEST | Dwarf fighter with axe | Priest/healer (robed, staff) | art 69 |
| UNIT_DRUID | Pikeman/spearman | Druid/nature caster (robed, green) | art 11 (Druid row) |
| UNIT_WAR_MAMMOTH | Green female spellcaster (WARLOCK art) | Large beast/mammoth | art 51 |
| UNIT_WAR_TROLL | Mounted magic marauder (WARRAX art) | Troll (large, brutish) | art 37 |
| UNIT_WARBEARS | Warship (three-mast ship) | Bear creature | art 6 |
| UNIT_AIR_ELEMENTAL | Hot air balloon (AIRSHIP art) | Elemental/spirit (wispy, translucent) | art 53 |
| UNIT_APPRENTICE | Wand/star effect only | Young mage figure | art 74 |
| UNIT_WAR_MAGE | Warbears (bear creature) | Mage/caster with staff | art 64 |
| UNIT_WARSHIP | War Troll (green orc) | Ship/naval vessel | art 33 |
| UNIT_GOBLIN | Transparency/chainmail on board | Goblin (small, green, menacing) | art 79 |

## Root Cause

The GL icon TGA files (`CM2_UPAP{NNN}L.TGA`) have the wrong art baked into
specific indices. The `art_cell_index` in `units.csv` points to the correct
position, but the TGA at that position contains art for a different unit.

This is likely a sprite extraction pipeline bug — the extractor mapped source
art cells to output indices incorrectly for these 10+ units.

## Fix Path

1. Identify correct source art from HoMM2/LotR/MoMJR reference sheets
2. Extract the correct cell from the source
3. Convert to ARGB1555 TGA at 160x120 (CTP2 GL icon format)
4. Write to `CM2_UPAP{correct_index}L.TGA`
5. Regenerate observer sheet and docs icons
6. Verify in-game via turnloop

## Pending Review

The 10 units above are confirmed wrong. The remaining 70 need visual review
against the reference sheets to confirm correctness. Use:
```
mkdocs serve
```
Then check each row's Icon column against expectations.
