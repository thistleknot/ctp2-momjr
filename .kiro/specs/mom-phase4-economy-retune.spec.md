---
description: 'Phase 4: retune mana economy with the full spell list in play'
import:
  - mom-feature-roadmap
  - mom-phase1-city-economy
  - mom-wiki-import
---

***definitions***

- :Combined-Demand: is the total mana draw from summons + spell casts + upkeep, which exceeds what the fixed-200 pool and flat upkeep rate 2 were designed for.
- :Economy-Retune: is the rebalancing of `MomMagicSchoolPct`, `MomSummonCivPct`, `MomUpkeepRate`, and potentially `MomMagicMax` against :Combined-Demand:.
- :Sustainability-Projection: is the AI's calculation of whether it can afford to summon/cast without going insolvent — must match the actual rates charged.

***implementation reqs***

- Rebalance all dials in `mod_policy.json` `mana_economy` block (Phase 1 prereq).
- `MomMagicSchoolPct[]` and `MomSummonCivPct[]` may need new values once 50+ spells compete for the pool.
- `MomUpkeepRate` may need to scale with creature count or tier rather than being flat.
- `MomMagicMax` (200) is the ANCHOR — changing it changes every cost's legibility. Last resort.
- AI sustainability projection MUST match actual rates (single-source via `MomUpkeepRate` global).
- Extend `gate_mana_upkeep.py` for the new economy shape.

***test reqs***

- A player with 5+ spells available can cast at least one per 3–5 turns at mid-game income.
- AI tribes summon AND cast (neither branch starves the other — the 3.11.0 starvation fix must hold).
- Insolvency fires correctly when income drops below upkeep (probe_insolvency.py with tuned rate).
- Pool-200 invariant: if MomMagicMax stays at 200, all costs remain legible fractions of 200.

***functional specs***

- :Combined-Demand: MUST be sustainable for a mid-game tribe with 3–5 cities.
  - Given a Life player with 4 cities, 2 mana nodes, 1 summon, and access to 10 spells, When playing normally, Then they can afford to cast at least one spell every 3–5 turns.
- The starvation guard MUST still hold: cheap branch (gold conversion) fires ONLY when the tribe cannot afford the expensive option.
- AI :Sustainability-Projection: MUST use the same rate constants as the actual upkeep scan.
- If 200 pool proves insufficient, the change MUST be explicit and all costs re-expressed.
- This phase MUST NOT ship until Phase 2 provides a real spell list to tune against.
