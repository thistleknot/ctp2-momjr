# Unit art — items to work

Source: operator review of `tools/momjr_csv/unit_art_review_0926-1520.html`
and `.tmp/matrix/sheet_0926_labelled.png`, 2026-09-26.
On the review page **left = CURRENT** (installed), **right = PROPOSED** (generated).

**Status 2026-09-26 18:45: every item resolved.** All 82 units carry a final
verdict in `unit_art_truth.json` (61 correct, 21 crafted). Review page:
`tools/momjr_csv/unit_art_review_0926-1840b.html`. Ship-size sheet of every unit:
`.tmp/matrix/sheet_0926_final_ship.png`. Built + audited, NOT verified in game.

## Keep the current art — DONE

CRYSTAL_GOLEM, DJINN, DROW, TREANT, ARCH_MAGE ("former unit" = the left,
installed `arch_mage.png`), CENTAUR_BOWMAN. All `no_regenerate`; the review page
now shows "final — no candidate" for every decided unit.

## Accepted proposals ("these are all fantastic") — DONE

49 generated proposals installed. Two adjustments:
- ARIEL: a shield + health-bar HUD icon was baked into the source art; cropped out.
- TAURON: the proposal draws a gold portrait frame around the figure; kept as approved.

## New art — DONE

| Unit | Pick | Note |
|---|---|---|
| APPRENTICE | s202 | img2img variation of the PRIEST art, young hooded caster |
| CATAPULT | s2718 | real four-wheeled torsion catapult |
| CENTAURS | klein s2718 d0.45 | `centaur.png` was the old tile at native size, not new art; z-image cannot draw centaurs; 5 of 6 klein outputs were a man riding a horse |
| GRIFFIN | s31337 | first batch drew 4/4 winged lions; fixed by leading the prompt with "the HEAD of a golden eagle" |
| INFERNAL_DEVICE | s11 | infernal war engine, no longer a fish |
| MALLEUS | s31337 | hooded witch-hunter knight on a black horse; other seeds had unkeyable dark backgrounds |
| MINION | s11 | hooded servant of a death wizard |
| STEAM_CANNON | s31337 | barrel level, muzzle right |
| UNICORN | s11 | realistic; keyed at tol 24 with no pocket pass |
| WYVERN | s31337 | prompt was literally "small dragon" |
| TROLL | s2718 | gaunt grey-blue cave troll — distinct from the green OGRE/ORC |

## New unit MINOTAUR_BOWMAN — DONE

Generator-owned (`units.csv` row, clone of Minotaur stats), sprite GU181, art =
the archer proposal. CENTAUR_BOWMAN also got its `units.csv` row — it had been
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
