---
description: 'Phase 3: 2022-review QoL pass — spellbook usability, sphere identity, research pacing'
import:
  - mom-feature-roadmap
  - mom-wiki-import
---

***definitions***

- :QoL-Pass: is a usability and polish layer applied after Phase 2 data import exists — cheap with the pipeline, prohibitive without it.
- :Sphere-Identity: is the visual/mechanical distinctiveness of each magic school — distinct enough that a player immediately knows which sphere they (and opponents) belong to.
- :Research-Pacing: is the rate at which advances unlock, tuned so the magic/spell content is reachable in a normal-length game without being trivially fast.

***implementation reqs***

- Depends on Phase 2 data pipeline existing (spells.csv, wiki-imported content).
- Spellbook usability: page indicators, spell descriptions in the alertbox, cost visible before casting.
- Sphere identity: distinct per-sphere colour/icon in messages, sphere-specific greeting/taunt text.
- Research pacing: tuned via `advance_cost_bands.csv` and `calendar_periods.csv` (already generator-owned since v4.1.0).
- Source: `C:\Users\user\Documents\wiki\games\ctp2\mom 2022 review.txt` and `Review.txt`.

***test reqs***

- Spellbook: player can identify spell cost, sphere, and effect before casting.
- Sphere identity: visual distinction measurable (different message strings, icon colour).
- Pacing: a typical game reaches mid-tier spells by turn ~50–80 (not turn 200+).
- No regression: all Phase 0–2 gates still pass.

***functional specs***

- The spellbook MUST show cost and sphere for each spell before the player commits.
- Each sphere MUST have visually distinct identity markers in all player-facing messages.
- Research pacing MUST be tuned so mid-tier magic content is reachable in a standard game length.
- This phase MUST NOT ship without Phase 2 data pipeline in place.
