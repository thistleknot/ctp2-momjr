# Unit art — items to work

Source: operator review of `tools/momjr_csv/unit_art_review_0926-1520.html`
and `.tmp/matrix/sheet_0926_labelled.png`, 2026-09-26.
On the review page **left = CURRENT** (installed), **right = PROPOSED** (generated).

**Status 2026-09-26 18:45: every item resolved.** All 82 units carry a final
verdict in `unit_art_truth.json` (61 correct, 21 crafted). Review page:
`tools/momjr_csv/unit_art_review_0926-2039.html`. Ship-size sheet of every unit:
`.tmp/matrix/sheet_0926_final_ship.png`. Built + audited, NOT verified in game.

## Keep the current art — DONE

CRYSTAL_GOLEM, DJINN, DROW, TREANT, ARCH_MAGE ("former unit" = the left,
installed `arch_mage.png`), CENTAUR_BOWMAN. All `no_regenerate`; the review page
now shows "final — no candidate" for every decided unit.

## Dwarves — DONE

DWARF_WARRIOR and DWARF_CROSSBOW now use the right-hand (generated) images from
the 15:20 review page, as the operator intended, replacing the hand-made files.

## Accepted proposals ("these are all fantastic") — DONE

49 generated proposals installed. Two adjustments:
- ARIEL: a shield + health-bar HUD icon was baked into the source art; cropped out.
- TAURON: the proposal draws a gold portrait frame around the figure; kept as approved.

## New art — DONE

| Unit | What the new art shows | Why this one |
|---|---|---|
| APPRENTICE | a young hooded caster in a plain grey robe with a glowing staff | a variation grown from the installed Priest art, as asked; the Mage-based ones still looked cartoonish |
| CATAPULT | a four-wheeled wooden torsion catapult, arm raised | the old proposal was a cart with a spear |
| CENTAURS | a long-haired centaur rearing with a spear, human torso on a chestnut horse body | `centaur.png` was the old tile at native size, not new art; z-image cannot draw centaurs, and 5 of 6 FLUX.2 klein tries drew a man riding a horse |
| GRIFFIN | eagle head, wings and talons on a lion body, wings spread | the first batch drew winged lions every time; leading the prompt with "the head of a golden eagle" fixed it |
| INFERNAL_DEVICE | a black iron siege engine on spiked wheels with a hellfire furnace and horned face | no longer a fish |
| MALLEUS | a hooded witch-hunter knight on a black horse raising a flaming hammer | the only candidate on a clean background; the rest had dark gradients that do not key |
| MINION | a gaunt hooded servant in black and purple robes with a lantern and dagger | prompted as a death wizard's servant, never the bare word "minion" |
| STEAM_CANNON | a bronze cannon on a wheeled carriage with a boiler, barrel level, muzzle right | fixes "facing up and backwards" |
| UNICORN | a realistic white unicorn in mid-gallop with a gold horn | no longer cartoonish; keyed gently so the white body keeps no holes |
| WYVERN | a small green dragon with spread wings | prompt was literally "small dragon" |
| TROLL | a gaunt grey-blue cave troll dragging a tree-trunk club | now distinct from the green ogre and orc |

Source files for each pick are recorded in `tools/momjr_csv/unit_art_truth.json`.

## Minotaur Warrior and Minotaur Crossbow — DONE

Operator: "minotaur becomes minotaur_warrior" and "where is my minotaur_crossbow".
The old Minotaur is now MINOTAUR_WARRIOR (`minotaur_reimagined.png`); the new
unit is MINOTAUR_CROSSBOW, a clone of its stats with the archer proposal as art.
The art shows a BOW, not a crossbow. Both are generator-owned `units.csv` rows
and both count as Chaos units for spell resistance. CENTAUR_BOWMAN also got its `units.csv` row — it had been
hand-added to generated files and the next regen would have deleted it.

## Harness fixes found along the way — DONE

- `sprite_overrides` (mod_policy.json): SETTLER 178, CATAPULT 179, GALLEY 180
  now survive regen.
- `stat_curve.source_exclude`: new clone units no longer re-scale ~30 units.
- `sprite_key_pockets` + `build_sprites._key_pockets`: enclosed background
  (between legs, inside bows) is transparent for 16 reviewed units.
- Installer: `--file`, `--key-tol`, `--key-pockets`; half-alpha cut; writes
  `ICON_UNIT_*.tga` with the sprite. 21 crafted portraits caught up.
- SETTLER re-keyed (tol 48): its whole frame was shipping as a black box.
- PEASANTS / LICH captions authored from the name.
- Review page now built from the complete caption table (the old one lacked
  both bowmen).

## Still open (not art defects)

- OGRE and ORC are both the operator's crafted art. With TROLL redrawn they read
  apart at 96x72 (grey armoured axe brute vs green spear orc), but only the
  operator can say whether that is distinct enough.
- PHANTOM_WARRIORS, AIR_ELEMENTAL, MAGE, WAR_MAGE, MALLEUS: enclosed black left
  as-is (ambiguous or real black art). Add to `sprite_key_pockets` if wanted.
- In-game verification.
