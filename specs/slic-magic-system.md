---
description: 'MoM magic system: per-player magic-power pool, school multipliers, castable spells, mana nodes, and AI casting — all on base-verified SLIC. Successor to the sphere-magic economy layer (slic-sphere-layer.md).'
import:
  - slic-sphere-layer
---

***definitions***

- :MagicPool: is a player's magic-power state — current power, max capacity, and
  per-turn generation — held in file-scope `int_t Arr[31]` arrays indexed by player
  (survives turns and save/load; NOT a new engine object).
- :MagicSchool: is the sphere a player belongs to, identified by the SAME numeric player
  index as slic-sphere-layer's `:SphereModule:` factions (1 Life, 2 Nature, 3 Sorcery,
  4 Death, 5 Chaos). It sets the pool's per-turn multiplier and max capacity.
- :ManaNode: is a good-bearing tile in a player's city radius. MoM's goods ARE terrain
  gems/minerals (Rubies, Diamonds, ...), so every good is thematically a mana node; detect
  via the base-verified `HasGood(loc) >= 0` (returns the good index, negative if none).
  Good-specific `GoodDB(GOOD_X)`/`ResourceDB` comparison is NOT base-verified (no stock SLIC
  uses it, and MoM has no GOOD_GOLD/GEMS), so M4 counts ANY good, not a specific one.
- :Spell: is a power-costed effect a player casts: spend :MagicPool: power to summon a
  school unit or apply an effect to a target.
- :Cast: is the trigger→afford→spend→effect sequence. The trigger is a SELECTED army/city
  or a capital-summon — NEVER a keypress (the engine has no keyboard event).
- :ManaVerbs: is the base-verified builtin set this layer is restricted to —
  `CreateUnit(pIdx,UnitDB(),loc,dist)`, `MakeLocation`, `HasGood`/`ResourceDB`,
  `PlayerHasWonder`/`CityHasBuilding`, `GetCityByIndex`, `IsHumanPlayer`, `Message`+`{var}`
  string interpolation. The momjr forms (`KeyPress`/`NotifyPlayer`/`ShowMessageBox`/string
  `CreateUnit`/`.hasBuilding("…")`) are FORBIDDEN — they do not exist in the engine.
  MESSAGE INTERPOLATION is restricted to the base-verified `{scalar}` and `{obj[lit].member}`
  forms only (proven in AlexanderTheGreat: `{cityScore}`, `{barbNum}`, `{city[0].name}`).
  ARRAY-INDEXED-BY-GLOBAL interpolation `{Arr[Idx]}` (the momjr/Cradle `{CULTURE[REV_Gk]}`
  idiom) is FORBIDDEN — the renderer cannot resolve it and silently DROPS the whole message
  (M1 popup regression). To show a computed number, copy it into a plain `int_t` display
  scalar immediately before the `Message` and interpolate `{thatScalar}`.

***implementation reqs***

- Module `mom_magic.slc`, `#include`d after `mom_msg.slc` in the entry point; ASCII/LF only.
- Config: MAGIC_BASE_PER_TURN — base power gained per player per turn, tuning, varies by scenario.
- Config: MAGIC_POP_COEF — power per city population point, tuning, varies by scenario.
- Config: MANA_NODE_BONUS — per-turn power added per owned Gold/Gems node, tuning, varies by scenario.
- Constant: MAGIC_SLOTS — per-player array width (31, one slot per engine player index).
- Pool storage: `int_t MomMagicCur[31]`, `MomMagicMax[31]`, `MomMagicPerTurn[31]` at file scope.
- School storage: `int_t MomMagicSchoolPct[31]` at file scope — per-player per-turn multiplier
  as an integer PERCENT (SLIC is integer-only; scaling is `gen * pct / 100`). Default 0, read as
  100 (baseline, pre-magic) until the school grant sets it.
- Constant: per-school multiplier/max table (M2), set on the sphere's magic-advance GrantAdvance,
  themed to slic-sphere-layer (Life balanced baseline, Chaos highest/most volatile):

  | School (player idx) | MomMagicSchoolPct | MomMagicMax |
  |---|---|---|
  | Life 1    | 100 | 200 |
  | Nature 2  | 110 | 220 |
  | Death 4   | 115 | 240 |
  | Sorcery 3 | 125 | 260 |
  | Chaos 5   | 140 | 300 |

  Chaos "most variable" is deferred: M2 gives Chaos the highest flat multiplier; a `Rand`-based
  per-turn jitter is a later refinement, kept out now to stay on verified deterministic getters.
- All symbol references (`UNIT_`/`IMPROVE_`/`WONDER_`/`ADVANCE_`/`GOOD_`) resolve in the
  generated DBs — enforced by `validate_all_surfaces.py` surface 7 BEFORE launch.

***test reqs***

- `test_mom_slic.py` extended: `mom_magic.slc` present, ASCII/LF, braces balanced; the pool
  handler ticks in `BeginTurn`; the cast path uses `CreateUnit(p, UnitDB(...), ...)` (integer
  index) and `MakeLocation`, never a string unit or a keypress; every spell/mana `{var}`
  string key exists in `scen_str.txt`; no forbidden `:ManaVerbs:` (KeyPress/NotifyPlayer/etc.).
- In-game gate (human = Life), per phase: pool popup shows the correct `{power}`; a cast
  deducts power and summons/affects the target; a Gold/Gems node raises per-turn power; the
  AI casts without a crash. Retry past the intermittent New-Game-setup crash.

***functional specs***

- When a turn begins for any player, the player's :MagicPool: current power gains
  `MomMagicPerTurn(p)`, capped at `MomMagicMax(p)`; a human player sees a one popup showing
  the new power. (Behavioral: pool tick.)
  - Initialize gain ← MAGIC_BASE_PER_TURN + population·MAGIC_POP_COEF + node bonus, scaled by
    the :MagicSchool: multiplier; then `MomMagicCur[p] ← min(MomMagicCur[p]+gain, MomMagicMax[p])`.
  - Given a Life player with power below max, When BeginTurn fires, Then power MUST rise by the
    computed per-turn amount and MUST NOT exceed `MomMagicMax[p]`.
- When a player is granted their sphere's magic advance (reuses slic-sphere-layer's GrantAdvance
  path), their :MagicSchool: multiplier and `MomMagicMax[p]` are set for that school. Each school
  differs per its slic-sphere-layer theme (Chaos highest/most variable, Life balanced).
- A player casts a :Spell: only While `MomMagicCur[p] >= spellCost`; casting MUST deduct
  `spellCost` and MUST fail closed (no effect, power refunded) if the target location is invalid.
  (Behavioral: cast sequence.)
  - Cast trigger is a selected army/city (`HandleEvent(ArmySelected|CitySelected)`, target =
    `army[0]`/`city[0]`) or a capital summon (reuse `MomSpawnSphereUnit`); the summon location
    is `city.location` or `MakeLocation(loc,x,y)` — distance 0 = the exact tile.
  - Given a player with power ≥ spellCost, When they cast a summon spell, Then a school unit
    MUST appear at the target and power MUST drop by exactly spellCost.
  - Given a player with power < spellCost, When they attempt a cast, Then nothing MUST happen
    and power MUST be unchanged.
- Where a player owns/works a :ManaNode: (a tile where `HasGood(loc) == ResourceDB(GOOD_GOLD)`
  or `GOOD_GEMS`), their `MomMagicPerTurn(p)` MUST include MANA_NODE_BONUS per node.
- While a player is an AI (`!IsHumanPlayer(p)`) with power ≥ its cast threshold, on BeginTurn the
  AI SHOULD pick an enemy target via `GetCityByIndex`/`tmpCity.location` and cast one spell; it
  MUST NOT act for a human player and MUST NOT crash when no valid target exists.
- Spell result messages use `Message(p,'KEY')` with `{scalar}` interpolation of plain `int_t`
  display globals set immediately before the Message (NOT `{Arr[Idx]}`, which the renderer drops);
  the layer MUST NOT use `NotifyPlayer`/`ShowMessageBox`/string concatenation (they do not exist).

***behavioral: MagicPoolTick (HandleEvent(BeginTurn) post)***

    Input: p — the turn player index, from player[0]
    Uses: MomRecalcMagicPerTurn(p) — recompute per-turn gen, ℤ≥0
    Uses: IsHumanPlayer(p) — human vs AI, {0,1}
    Uses: Message(p, key) — show a scen_str popup with {var} interpolation

    MomMagicPerTurn[p] ← MomRecalcMagicPerTurn(p)
    MomMagicCur[p] ← MomMagicCur[p] + MomMagicPerTurn[p]
    When MomMagicCur[p] > MomMagicMax[p]:
        MomMagicCur[p] ← MomMagicMax[p]            (Maintain: 0 ≤ MomMagicCur[p] ≤ MomMagicMax[p])
    // PERIODIC popup: every 10th round only (0,10,20,...) -- per-turn spam is unwanted
    // (user feedback). Latch still guards a same-round re-entrant fire (flood safety).
    When IsHumanPlayer(p) and (round mod 10 == 0):
        MomMagicCurDisp ← MomMagicCur[p]           // copy pool values into plain int_t display
        MomMagicMaxDisp ← MomMagicMax[p]           // scalars; the message interpolates {scalar},
        MomMagicGenDisp ← MomMagicPerTurn[p]       // NEVER {Arr[Idx]} (unsupported, drops msg)
        Message(p, 'MomMagicPower')                (Assert: fires at most once per player per round)
    // The RELIABLE magic popup is the GrantAdvance milestone (below): no BeginTurn Message is
    // proven to surface in this mod, so the periodic one is best-effort; the milestone rides
    // the proven GrantAdvance message path (sphere blessings display on the same event).

***behavioral: MagicSchoolGrant (HandleEvent(GrantAdvance) post)***

    Input: p — the granted player index, from player[0]
    Input: adv — the granted advance type, from advance[0].type
    Uses: MomPlayerIsLife(p)..MomPlayerIsChaos(p) — numeric-index sphere predicates, {0,1}
    Uses: AdvanceDB(ADVANCE_X) — resolve a magic-advance record; X in {LIFE_MAGIC, NATURE_MAGIC,
          SORCERY, DEATH_MAGIC, CHAOS_MAGIC}

    // One branch per school; a player takes only its own sphere's branch. Fires once per player
    // per advance (GrantAdvance semantics), so no latch. Separate named handler from the
    // blessing/message GrantAdvance handlers — all three coexist under the same event.
    When MomPlayerIsLife(p)   and adv == AdvanceDB(ADVANCE_LIFE_MAGIC):
        MomMagicSchoolPct[p] ← 100 ; MomMagicMax[p] ← 200
    Otherwise When MomPlayerIsNature(p)  and adv == AdvanceDB(ADVANCE_NATURE_MAGIC):
        MomMagicSchoolPct[p] ← 110 ; MomMagicMax[p] ← 220
    Otherwise When MomPlayerIsSorcery(p) and adv == AdvanceDB(ADVANCE_SORCERY):
        MomMagicSchoolPct[p] ← 125 ; MomMagicMax[p] ← 260
    Otherwise When MomPlayerIsDeath(p)   and adv == AdvanceDB(ADVANCE_DEATH_MAGIC):
        MomMagicSchoolPct[p] ← 115 ; MomMagicMax[p] ← 240
    Otherwise When MomPlayerIsChaos(p)   and adv == AdvanceDB(ADVANCE_CHAOS_MAGIC):
        MomMagicSchoolPct[p] ← 140 ; MomMagicMax[p] ← 300
        (Guarantee: MomMagicMax[p] set for the school; MomMagicCur[p] unchanged — the pool
         only refills on the BeginTurn tick, so raising Max never grants power instantly)
    // MILESTONE popup (proven GrantAdvance path). `granted` = a school branch fired this call.
    When granted and IsHumanPlayer(p):
        MomMagicPerTurn[p] ← MomRecalcMagicPerTurn(p)   // recompute so the popup shows the scaled rate
        MomMagicCurDisp ← MomMagicCur[p]                // READ only; does not modify the pool
        MomMagicMaxDisp ← MomMagicMax[p]
        MomMagicGenDisp ← MomMagicPerTurn[p]
        Message(p, 'MomMagicPower')                     (Assert: fires once, on the school advance)

***behavioral: MomRecalcMagicPerTurn(p) scaling (M2 layered on M1)***

    Initialize gen ← MAGIC_BASE_PER_TURN                          // 10
    Initialize nodes ← 0
    Uses: HasGood(loc) — good index at a tile, ≥0 if present (base-verified, tut2_func.slc)
    Uses: GetNeighbor(loc, i, out) — i-th adjacent tile, i ∈ 0..7 (MAX_DIR = 8)
    Loop over p's valid cities:
        gen ← gen + city.population · MAGIC_POP_COEF              // coef 2
        // M4 mana nodes: the city tile + its 8 neighbors, each good-bearing tile is a node
        When HasGood(city.location) ≥ 0: nodes ← nodes + 1
        Loop i ∈ 0..7: GetNeighbor(city.location,i,nloc); When HasGood(nloc) ≥ 0: nodes ← nodes+1
    gen ← gen + nodes · MANA_NODE_BONUS                           // bonus 5, before school scaling
    Initialize pct ← MomMagicSchoolPct[p]
    When pct == 0: pct ← 100                                      // pre-magic baseline
    gen ← gen · pct / 100                                         (Guarantee: integer-scaled, ℤ≥0)
    return gen

***behavioral: SpellCast (M3 — pool-overflow auto-summon)***

    CTP2 SLIC has NO interactive cast trigger (no keypress, and ArmySelected/CitySelected
    fire on every click → would spam). The base-verified spend is POOL OVERFLOW: when a
    player's magic pool caps, the accumulated power discharges into a summoned school
    creature at the capital. Deterministic, needs no UI, and applies to human AND AI (so it
    also seeds M5). Runs at the end of the BeginTurn pool tick, after accrual+cap.

    Uses: MomSphereSummonUnit(p) — the player's sphere creature UnitDB, 0 if no sphere
    Uses: MomSpawnSphereUnit(p, unitType) — spawn in player's first city (guards on cities)

    When MomMagicMax[p] > 0 and MomMagicCur[p] >= MomMagicMax[p]:
        summon ← MomSphereSummonUnit(p)
        When summon != 0 and player[p].cities > 0:
            MomMagicCur[p] ← 0                       (Guarantee: full pool spent on the summon)
            MomSpawnSphereUnit(p, summon)            (Guarantee: creature manifests at the capital)
        Otherwise: retain power                      (fail-closed: no sphere or no city → no summon)

    Per-sphere creature (reuses the blessing units): Life=UNIT_GUARDIAN_SPIRIT,
    Nature=UNIT_WARBEARS, Sorcery=UNIT_MAGE, Death=UNIT_ZOMBIES, Chaos=UNIT_HELL_HOUNDS.
    The summoned unit appearing IS the player feedback (no BeginTurn Message — unproven to
    surface). A future richer cast (choose spell/target) is deferred until a base-verified
    interactive trigger exists.
