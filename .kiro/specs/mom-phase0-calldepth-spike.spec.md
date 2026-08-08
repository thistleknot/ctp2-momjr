---
description: 'Phase 0: verify that a flat MomCastSpell dispatcher survives the SLIC call-depth limit in-game'
import:
  - mom-feature-roadmap
---

***definitions***

- :Flat-Dispatcher: is `MomCastSpell(int_t p, int_t spellId)` — one user-function call from a Button, all effect bodies inlined as an if-chain.
- :Nested-Shape: is the original structure (Button → dispatcher → per-spell helper = two levels). Expected to crash (control).
- :Call-Depth-Limit: is the engine constraint: one level of user-function call from a handler body. Second level = 0xC0000005.
- :A/B-Test: is in-game comparison: Flame Strike (flat, hypothesis: survives) vs Demon Strike (nested, control: expected crash).

***implementation reqs***

- Code: `scen0000/default/gamedata/mom_spells.slc`.
- `MomCastSpell(int_t p, int_t spellId)` — single flat entry, `spellId` as int PARAMETER.
- Five call sites: 2 in `MomMsgSpellbook`, 2 in `MomMsgSpellbookChaos`, 1 in `MomSpellAICast` BeginTurn.
- Per-spell dials selected by inlined if-chain. Nearest-enemy-city search inlined with `IsPlayerAlive` guard.
- `MomCastFlameStrike`/`MomCastDemonStrike` left as dead code until verified, then deleted.

***test reqs***

- Cast Flame Strike from both spellbook variants → no crash.
- AI Chaos wizard casts on BeginTurn → no crash.
- (Control) Demon Strike nested path → expected 0xC0000005.
- `validate_all_surfaces.py` surface 7 green before launch.
- If flat also crashes → spike FALSIFIED → fallback to one-function-per-spell.

***functional specs***

- The :Flat-Dispatcher: MUST survive without 0xC0000005.
  - Given flat dispatch deployed, When player casts Flame Strike, Then effect fires and mana deducted.
  - Given flat dispatch deployed, When AI casts on BeginTurn, Then completes without crash.
- The :Nested-Shape: SHOULD crash to confirm the hypothesis.
- If spike FALSIFIED, fallback: one generated function per spell, each its own Button, paged spellbook.

## Blocker

The `uiwalk` turnloop `date_rect` is miscalibrated at 1280×1024. Options:
1. Fix date_rect (needs pixel measurement from 1280×1024 frames)
2. Manual user test (30 seconds, bypasses harness)
3. Revert userprofile.txt to 1024×768
