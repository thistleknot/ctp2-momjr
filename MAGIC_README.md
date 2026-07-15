# MoM Magic System — player & modder guide

The five tribes are the five **spheres of magic**, seated as players 1–5:

| Player | Sphere  | Summon creature (M3)   | School cap / rate (M2) |
|--------|---------|------------------------|------------------------|
| 1      | Life    | Guardian Spirit        | 200 / ×1.00 |
| 2      | Nature  | War Bears              | 220 / ×1.10 |
| 3      | Sorcery | Mage                   | 260 / ×1.25 |
| 4      | Death   | Zombies                | 240 / ×1.15 |
| 5      | Chaos   | Hell Hounds            | 300 / ×1.40 |

Implemented in SLIC (`scen0000/default/gamedata/mom_magic.slc`, base-verified builtins only).
There is **no on-screen popup** — the effects are gameplay, not UI. What to watch for:

## What the magic does

1. **Sphere gold** (`mom_turns.slc`) — each sphere earns bonus gold every turn. Visible in
   your treasury income.
2. **Magic pool (M1)** — every turn, a sphere player accrues magic power:
   `10 + 2·(city population) + 5·(mana nodes)`, scaled by the school multiplier (M2),
   capped at the school's max. Silent (a per-player accumulator).
3. **School (M2)** — when you research your sphere's magic advance (Life Magic, Nature Magic,
   Sorcery, Death Magic, Chaos Magic), your pool cap and generation multiplier are set from
   the table above. Chaos generates fastest and stores the most; Life is the steady baseline.
4. **Summon (M3)** — *the visible payoff.* When your pool reaches its cap, it **discharges
   fully** and a **free sphere creature manifests in your capital**. With a couple of cities
   this happens roughly every 10–20 turns; faster with more cities and mana nodes, and faster
   for Chaos. **Watch your capital for units appearing on their own.**
5. **Mana nodes (M4)** — any tile bearing a good (MoM's goods are gems/minerals — Rubies,
   Diamonds, …) inside a city's radius adds +5/turn to that player's magic generation, so
   resource-rich empires summon more often.

Magic applies to sphere players 1–5 only (the barbarian player 0 is skipped — running the
tick for player 0 was the turn-10 crash, now guarded with `if (p >= 1)`).

## How to verify in-game
- Play a sphere (e.g. Life). Note your capital's garrison.
- Advance ~10–20 turns without building units there. A **Guardian Spirit** should appear
  on its own — that's the pool discharging.
- Research **Life Magic** to raise your cap/rate; grab gem tiles near cities to speed it up.

## Roadmap (built vs future)
- **Done:** M1 pool, M2 school multipliers, M3 pool-overflow summon, M4 mana nodes, sphere gold.
- **M5 (AI casting):** already covered — the summon fires for AI players too, fail-closed.
- **Deferred:** interactive/targeted spellcasting (needs a base-verified cast trigger CTP2
  SLIC doesn't expose) and an in-game power readout (the `{scalar}` popup exists in
  `mom_magic.slc` but is off; re-enable via the `Message(g.player,'MomMagicPower')` calls if a
  UI cue is wanted).
