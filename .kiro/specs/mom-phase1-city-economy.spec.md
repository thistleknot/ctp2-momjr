---
description: 'Phase 1: terrain-gated buildings, mana constants to policy, food/growth rebalance'
import:
  - mom-feature-roadmap
---

***definitions***

- :Terrain-Gating: is the mechanic where a building requires specific terrain types in the city radius.
- :Terrain-Prereq: is a new column in `improvements.csv` specifying required terrain.
- :Mana-Economy-Block: is a `mod_policy.json` section holding all mana constants (replacing scattered literals).
- :Build-Chain: is a sequence where each building unlocks the next (Sawmill → Foresters' Guild).

***implementation reqs***

- Add `terrain_prereq` to `improvements.csv` (values: `TERRAIN_FOREST`, `TERRAIN_HILL|TERRAIN_MOUNTAIN`, etc.).
- Generator emits gating into `mod_CanCityBuildBuilding` (existing SLIC hook).
- Promote all mana constants from `mom_magic.slc` literals into `mod_policy.json`:
  `MAGIC_BASE_PER_TURN` (10), `MAGIC_POP_COEF` (2), `MANA_NODE_BONUS` (5),
  `MomMagicMax` (200), `MomUpkeepRate` (2), `MomMagicSchoolPct[]`, `MomSummonCivPct[]`.
- Rebalance food/growth chain (Granary, Farmer's Market, Sawmill, Foresters' Guild).
- Extend `gate_mana_upkeep.py` to assert policy-sourced dials preserve ANCHOR-200.

***test reqs***

- City with no forest → Sawmill unbuildable.
- City with forest → Sawmill available.
- Mana policy produces identical gameplay to current literals (regression).
- `gate_mana_upkeep.py` passes with policy values.

***functional specs***

- A building with :Terrain-Prereq: MUST be unbuildable when terrain is absent.
- :Build-Chain:s MUST propagate: blocked prereq → all downstream blocked.
- :Mana-Economy-Block: MUST be the single source of truth for all mana constants.
- Food/growth rebalance MUST make city specialization measurably pay.

## Source

- `C:\Users\user\Documents\wiki\games\ctp2\mom min maxing.txt`
- MoM wiki buildings pages (~35 articles)
