---
description: 'Fix invisible makespr.py-built unit sprites: anim transparency must be 15 (opaque), not 0'
---

***definitions***

- :AnimTransparency: is the per-frame u16 in a SPR anim block that the engine
  feeds to the draw blitter as blend alpha (`alpha = value << 3`); 15 = fully
  opaque, 0 = fully invisible. It is unrelated to the pixel-level chromakey
  alpha inside frame data.
- :StaticUnitScript: is the GU##.TXT makespr script template for 1-frame
  MOVE-only MoM sprites, embedded in `rebuild_peasant_spr.py` (`_GU_SCRIPT`)
  and `build_sprites.py`.

***implementation reqs***

- Engine ground truth (H:\Games\civctp2\ctp2_code):
  `Actor.h:83 NO_TRANSPARENCY = 15`;
  `Action.cpp:143 GetTransparency()` returns the SPR anim's per-frame value
  whenever the file supplies an anim (every makespr output does);
  `UnitActor.cpp:470` copies it into the actor each tick;
  `pixelutils.h:49 Blend16` returns pure background when alpha is 0.
- Touched files: `Scenarios/mom/tools/rebuild_peasant_spr.py`,
  `Scenarios/mom/tools/build_sprites.py` (template text only);
  `makespr.py` gains a warning, never silent value rewrites (faithful port).
- Output artifacts: `ctp2_data/default/graphics/sprites/GU104.SPR` now;
  GU91–GU99 and GU100–GU148 on batch rebuild.

***test reqs***

- `decode_anim.py` (session scratchpad): decodes MOVE-anim transparencies
  from any GU*.SPR without launching the game.
- Positive control: stock `GU091.SPR` / `GU013.SPR` decode to `[15,…]` and
  provably render in this scenario.
- Negative control (pre-fix): `GU104.SPR` and `GU100.SPR` decode to `[0]`.

***functional specs***

- makespr.py `pack_anim` MUST pad omitted :AnimTransparency: entries with 15
  (opaque), never 0. (Refinement: `ANIM_TRANSPARENCIES <n>` in script syntax
  is a flag — `0` means "no explicit list", `1 { v… }` supplies one — so the
  script template was never the defect; the zero-pad in `pack_anim` was.)
  - Given the canonical :StaticUnitScript: (`ANIM_TRANSPARENCIES 0`), When
    makespr.py compiles it and decode_anim.py runs on the output, Then
    transparencies == [15].   [VERIFIED 2026-07-03]
- makespr.py SHOULD warn when a script supplies an explicit all-zero
  :AnimTransparency: list — an all-invisible unit is never intended.
  - Given a script with `ANIM_TRANSPARENCIES 1 { 0 }`, When makespr.py
    compiles it, Then a warning states the unit will be invisible and names
    15 as the opaque value.
- When GU104.SPR is rebuilt from ICON_UNIT_PEASANTS.tga with the fixed
  template, the peasant MUST be visible on the map after a full CTP2
  restart, at every zoom level.
  - Given the running game, When the Peasants unit is selected, Then body
    and banner both render (banner-only = regression).
    [CONFIRMED IN-GAME 2026-07-03 — peasant visible on map, correct art]
- Where the batch rebuild runs (`build_sprites.py --force`), all MoM
  sprites 91–148 MUST decode to transparencies [15] and become visible.
- If the peasant is still invisible after the rebuild: the transparency
  hypothesis is falsified; the next discriminators are the zoom test
  (visible only fully zoomed-in ⇒ mini-frame path) and a stock-sprite swap
  (`DefaultSprite SPRITE_WARRIOR` on UNIT_PEASANTS ⇒ wiring/state).
- makespr.py MUST stay byte-identical to makespr.exe on the golden fixture
  (Kull's Legion, `H:\Games\ctp2\16-makespr\16\`): stage inputs + GU16.TXT,
  run `makespr.py -u 16`, byte-compare against the exe-built GU16.SPR.
  - Given the fixture, When makespr.py compiles GU16, Then output ==
    exe GU16.SPR byte-for-byte.   [VERIFIED 2026-07-03 — 452,956/452,956]
