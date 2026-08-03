# Changelog

MoM (Masters of Magic) scenario for Call to Power 2. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Entries are grouped by
the dimension they touch, because the control plane is organised that way.

Only player-visible or tool-contract changes are listed. Byte-level regeneration
noise is not a change.

---

## [3.10.0] — 2026-08-03 — a summon costs what it is worth

**Minor.** Gameplay. Requires a NEW game: saves cache compiled SLIC.

### The defect

Every summon cost a flat **75 mana**, at every rung:

| rung | creature | shields | mana |
|---|---|---|---|
| 1 | Phantom Warriors | 150 | 75 |
| 1 | Warbears | 350 | 75 |
| 3 | Storm Giant | 1500 | 75 |
| 5 | Storm Drake | 4000 | 75 |

A **27x swing in value at one price**. Upkeep had scaled with rung since v3.5.0,
so acquisition was the missing half of that system — and the gap pushed play the
wrong way: summoning was poor value at rung 1 and absurd value at rung 5.

### Changed

- **Summon price is `45 + 30 * rung` → 75 / 105 / 135 / 165 / 195.**

  The ceiling is load-bearing, not taste: `MomMagicSchoolGrant` caps pools at
  Life 200 / Nature 220 / Sorcery 260 / Chaos 300, so a price above 200 would put
  rung 5 permanently beyond Life's reach.

  **The gate uses the ladder rung; the debit uses the rolled rung.** A roll can
  return any creature at or below the caster's rung, so requiring
  `45 + 30 * MomSphereRung` up front guarantees whatever comes back is
  affordable — a click can never be consumed by a summon that cannot be paid for
  — and you then pay for what you actually got.

  All four sites use one expression: human gate (button body), human debit
  (`MomSummonOrderTick`), AI gate and AI debit. The AI must not play a cheaper
  economy than the player; that exact divergence already bit this mod once on the
  upkeep rate.

- The summon arm no longer misquotes its own price. `"Summon Creature (75)"`
  became false the moment price scaled; the arm is now `"Summon Creature"` and
  the price appears on the panel's rung line and in the refusal message.

### Fixed

- `MOM_MSG_SUMMON_NOMANA` hardcoded "A creature costs 75". It now reads the live
  price.

### Added (gates)

- `gate_mana_upkeep.py` assertion 13: the price must derive from the rung at
  BOTH the gate and the debit of BOTH paths, and no bare `75` may survive on the
  summon path. Proven by reintroducing a flat 75 in the AI debit and watching it
  fail, then restoring.

### Known

- **Button labels do not interpolate.** `{Scalar}` substitution works in message
  bodies but a `MOM_MSG_BTN_*` label renders the literal braces — measured, both
  surfaces in one frame. Arms must be static strings.
- The curve is verified at **rung 1 only** (in-frame: "a creature of your rung
  costs 75, and you hold 50"). Rungs 2-5 are thousands of science away and were
  not reachable in a short run; the arithmetic is `45 + 30*r`, the behaviour at
  those rungs is unobserved.

---

## [3.9.0] — 2026-08-03 — a tribe begins knowing its own sphere

**Minor.** Gameplay + tooling. Requires a NEW game: saves cache compiled SLIC.

### The defect

A tribe's own magic sat 27 advances and ~19,300 science away, because
`ADVANCE_*_MAGIC` hangs off `ADVANCE_GRAND_MASTERY` and nothing anywhere granted
it. The player met this as "You have not yet learned the magic of your sphere" in
3675BC. Removing the v3.2.0 rung floor in 3.7.0 fixed a real tech-tree bypass and
exposed what the floor had been imitating: a starting-advance mechanism that was
never built.

### Changed

- **Tribes start holding their sphere root.** `MomSphereRootGrant`
  (`mom_magic.slc`) grants `ADVANCE_LIFE_MAGIC` / `NATURE_MAGIC` / `SORCERY` /
  `DEATH_MAGIC` / `CHAOS_MAGIC` to players 1..5. It is guarded on
  `MomSphereRung[p] < 1`, which `MomSphereRungTick` clears on the grant — the
  guard latches itself, so no separate latch array is needed and no new SLIC
  state was added.

  **Verified for Nature and Sorcery**, both of which hold summoned creatures by
  turn 20 — far too early to have researched a 1035-science root. **Death shows
  rung-0 behaviour for a full 200 turns and is unexplained**; see *Known* below.
  Ship this knowing the grant is not confirmed for every tribe.
- **The five rung-1 creatures are buildable at the sphere root**, not the lore
  advance. Previously a Warbears cost 1970 science to BUILD and nothing but mana
  to SUMMON; both now open together, so the choice is an honest trade of 75 mana
  plus preparation against 350 shields. Only these five `EnableAdvance` values
  move (`LIFE_LORE` → `LIFE_MAGIC`, and the four siblings). The creature is still
  production-gated by its shield cost.

  This also closes a gap measured across the AI build lists: before it, **no
  tribe had a single racial unit buildable under 455 science**, so every early
  army was neutral Spearmen and Swordsmen and the only sphere-flavoured units on
  the map were summoned ones.

### Fixed (harness)

- **The 200-turn probe could not boot.** `full_game_v3.json` prologue step 27 was
  a posted click at (600,6). The identical ping had been diagnosed as fatal and
  migrated to `hover` in the per-turn cycle only; the prologue's copy survived,
  in the same file, under a comment reading "This is the ONLY posted click in the
  file". Every run died `0xC0000005` right after the main-menu shot — at HEAD,
  with the mod reverted, in every scenario. Now `hover`, and two consecutive
  200-turn runs complete.
- `uiwalk.scenario_pack_index()` derives the scenario row instead of pinning it.
  The engine sorts the picker **case-insensitively**, so `mom` is row 3; a pinned
  row was correct but unverifiable, and "correcting" it to 5 loaded `smm`.
- `probe_long_game.py` gains `PROBE_OBSERVE=1`: no posted clicks at all, for
  displays where the engine letterboxes its 800x600 UI and any posted click
  faults.
- New `tools/uiwalk/probe_scenario_list.py` — captures the picker without
  selecting, since `inject_select`'s `SelectItem` has no bounds check.

### Added (gates)

- `validate_scenario.py` gate 29 `check_slic_arrays_declared`: an undeclared SLIC
  **array** is a hard "Symbol is undefined" error at load, unlike a scalar, which
  the engine silently auto-creates — one reached the operator as a load-time
  modal. Catchable statically, so it should never reach a playtest again.

  It also checks declaration **order** against the real `#include` sequence in
  `scenario.slc`: a use in a file that loads before the declaring file is the
  same hard error, and the first draft of `MomSphereRootGrant` had exactly that
  (`mom_turns.slc` include 49 reading `MomSphereRung[]` from `mom_summon.slc`
  include 54). Proven against a 4-case battery — clean tree passes, the ordering
  bug fails, an undeclared array fails, restored tree passes.

### Known, measured, NOT fixed

Two 200-turn runs (see `lessons_learned.md`):

- **AI armies are majority-summoned** — Nature 26/46 (57%), Sorcery 30/43 (70%),
  stable t80→t200. The AI summons on a 70% per-turn roll whenever solvent, with
  no bound relative to army size. A ratio cap is a design decision, not a bug fix.
- **Death never summons**, holding exactly its 240 mana cap from t20 to t200. The
  income-only-gate hypothesis was patched, tested, **falsified**, and reverted.
  Affordability and an empty pool are both eliminated; the surviving hypothesis is
  that `MomSphereRung[4]` is still 0, i.e. the sphere-root grant above does not
  reach Death. The next step is to READ that variable — the probe samples
  per-player mana but not rung — rather than infer it from behaviour again.
- **Chaos never plays** — 0 units and 0 mana in all ten samples, so player 5 never
  takes a turn. Starting placement in the map, not SLIC.

---

## [3.8.0] — 2026-08-02 — unit stats are rank-cast from the source, not multiplied

**Minor.** Data. Every combat unit's stats change; saves keep whatever the
database said when they were made.

### The defect

The port rescaled civ2 stats with flat multipliers:

```python
attack    = attack_raw * 5
defense   = max(5, def_raw * 5)
hp        = 10              # hp_raw parsed, then DISCARDED
```

Three consequences, all of them the balance complaint:

- **Linear multiply lets the top run away.** civ2's attack median is 5.5, so x5
  pinned most of the roster at 5–30 while a 15a Great Wyrm reached 75. The gap
  between a dragon and an army grew without bound instead of saturating.
- **The floor crushed the bottom.** civ2's defence median is 2–3, so
  `max(5, d*5)` put nearly every buildable unit at 5–15 and threw away the real
  spread the source has — War Troll 5d, Iron Golem 5d, Ariel 8d all collapsed
  together. This is why built units looked like they had no armour: they had it
  in the source, and the map destroyed it.
- **MaxHP shipped as a literal 10 on every unit.** civ2 carries a real durability
  axis, 1h Spearmen through 6h Great Wyrm, and the port parsed `hp` only to pick
  a sprite size before writing the constant. The engine *does* honour MaxHP
  (`UnitData.cpp:6256`); stock CTP2 simply never varies it. A dragon died as fast
  as a peasant.

### Changed

Stats are now **rank-cast**: each unit is placed by its rank position within the
civ2 distribution, then re-cast onto a CTP2 target range anchored so source
min/median/max land exactly on target min/median/max. The ordering is the
original designer's; only the range and the curve are ours.

The warp is `smoothstep`, `w = p²(3−2p)` — its gradient rises to a peak at the
midpoint and decays after, so power climbs steeply out of the trash tier then
saturates. Massed cheap units stay relevant against a top-tier creature.

```
              before            after
SPEARMEN       5/  5/10/1     10/ 10/10/1
CATAPULT      30/  5/10/1     45/ 10/10/1
WAR_TROLL     25/ 25/10/1     54/ 43/35/1     <- buildable, real armour
GUARDIAN_SPT   5/ 25/10/1     10/ 43/35/1
ARCHANGEL     60/ 60/10/2     92/100/20/5
GREAT_WYRM    75/ 45/10/2    100/ 87/60/5
INFERNAL_DEV 495/  5/10/1    100/ 10/10/1     <- outlier tamed
                                (attack/defense/HP/firepower)
```

Resulting spread: attack 10–100 (median 35), defence 10–100 (median 15), **HP
10–60 across 5 distinct values**, firepower 1–6.

Targets live in `mod_policy.json` under `unit_stat_scaling.stat_curve`.
Attack/defence/firepower use **stock CTP2's own min/median/max**, so nothing
lands outside a range the engine already ships. HP has no stock spread to match —
stock is flat 10 on all 74 units — so its target preserves the *source* ratios
instead: civ2's 1/2/6 becomes 10/20/60, floor left at today's universal value so
no unit loses HP.

Infernal Device's 99a (at cost 480, 6.6× the next attack for a seventh of the
price) is excluded when measuring the source distribution, so one broken row
cannot stretch the scale for everyone. It is still cast — it just no longer
defines the maximum.

### Tooling

- `validate_scenario.py` gate 28: no combat stat may collapse to a single value
  across the roster, and none may exceed stock CTP2's own maximum. Proven to
  reject a re-flattened MaxHP before being trusted. A stat with one distinct
  value is a dropped column, not balance.

## [3.7.0] — 2026-08-02 — summoning costs what building costs

**Minor.** Behavioural. Old saves are unaffected because they cache compiled
SLIC; the change applies to new games.

### The imbalance

The same creature cost **1970 science to build and 0 science to summon**:

```
SPEARMEN       150 shields   ADVANCE_WARRIOR_CODE   (start advance)
CENTAURS       250 shields   ADVANCE_SHAMANISM      (455 science)
WARBEARS       350 shields   ADVANCE_NATURE_LORE    (1970 science)
```

`MomSummonRoll` floored the ladder rung at 1, so every tribe had rung-1
summoning from turn one and the summon path skipped the tech tree entirely. A
tribe's only sphere-flavoured units were therefore ones it *could never have
built* — which is why the Tribes of Nature arrived at your border as three
identical Warbears, over and over.

The floor was added in 3.2.0 against "a tribe that starts holding its sphere root
never fires the `GrantAdvance` that would raise it off 0". **That premise is
false here** — nothing in the scenario grants a `*_MAGIC` or `*_LORE` advance and
there is no starting-advance mechanism, so no tribe ever starts holding its root.
It guarded a case that does not exist, and cost a whole tech gate.

### Changed

- **A tribe cannot summon until it researches its sphere's magic.** Rung 0 now
  falls through every band, `MomSummonRoll` returns 0, and the pool is not
  debited. For Nature that is 1035 science — still earlier than the 1970 needed
  to *build* a Warbears, so magic still reaches the creature first. It is simply
  no longer free.
- **The panel reports rung 0 honestly** instead of claiming "rung 1 of 5" while
  every summon silently failed.
- **The arm explains itself.** Clicking Summon with no magic learned now says so,
  ahead of the no-mana and already-preparing branches.

### Fixed

- **The 3.6.1 leader names were applied to generated files and reverted by the
  next regeneration.** `civilisation.txt` and `civ_str.txt` are generator-owned.
  The generator already emitted `_LEADERF_NAME` whenever `players.csv` carried a
  `civ2_leader_female` value — the column was simply blank for four realms and a
  duplicate ("Freya") for Nature. Sophia / Raven / Zarah / Kali / Ignara now live
  in the control plane and survive regeneration.

### Verified in game

Headless, new game, 20 turns, no SLIC errors:

```
Mana 100/100  inc 29 - up 0 = 29  rung 0
units   3 4 5 0 0
summon  0 0 0 0 0
mana    100 60 52 100 0
```

Summon counts are zero for every tribe and mana **accumulates** instead of
draining from turn ~5, while AI unit counts still grow — the armies are now
city-built.

### Known open

- The rung-1 pool is still one creature per sphere, so variety returns as a
  question once the gate is judged in play.
- Summon price is still flat 75 mana for anything from 150 to 4000 shields of
  value. Pricing by rung is designed but not implemented.
- The creature power curve is linear (attack 5 → 75 in even steps) with **flat
  HP 10 on every unit**. A saturating curve with a counter class is the intended
  direction, not yet started.

## [3.6.1] — 2026-08-02 — every realm has a queen

**Patch.** Data only. No save impact; the name is read at display time.

### The change

Picking a female leader gave you the male leader's name. Four of the five realms
pointed `LeaderNameFemale` straight at the `_LEADERM_NAME` key, and the fifth
(Nature) pointed at a `_LEADERF_NAME` string whose value was just "Freya" again —
so the female slot was male-aliased everywhere, by wiring rather than by accident.

Each realm now has a distinct leader per gender:

| realm | male | female |
|---|---|---|
| Life | Ariel | **Sophia** |
| Nature | Freya | **Raven** |
| Sorcery | Jafar | **Zarah** |
| Death | Rjak | **Kali** |
| Chaos | Tauron | **Ignara** |

Raven and Kali are Master of Magic wizards, so they share the roster the five
existing names came from. Sophia, Zarah, and Ignara are new — the canon has no
unused female wizard for those spheres.

### Files

- `scen0000/english/gamedata/civ_str.txt` — added four `_LEADERF_NAME` strings,
  replaced Nature's duplicate value
- `scen0000/default/gamedata/civilisation.txt` — repointed `LeaderNameFemale`
  for Life, Sorcery, Death, and Chaos off the male key

### Known open

The new-game screen still defaults to **Alexander**. `civilisation.txt` defines
six civs while `civ_str.txt` retains the full stock CTP2 table, so the picker
falls back to stock Greek. Unrelated to these strings; not fixed here.

## [3.6.0] — 2026-08-01 — summoning takes preparation

**Minor.** Additive. Old saves load; a save made before this has nothing
preparing, which is the same state as a fresh game.

### The change

A summon used to resolve on the next `BeginTurn` regardless of what was rolled,
so a Great Wyrm and a Warbears arrived on exactly the same schedule and there was
nothing to plan around. Committing a summon now debits the mana, rolls the
creature, and starts a **countdown equal to its sphere rung**:

| rung | creature tier | turns |
|---|---|---|
| 1 | Warbears, Guardian Spirit | **1** — unchanged from before |
| 3 | Behemoth, Demon | 3 |
| 5 | Great Wyrm, Archangel | **5** |

This is deliberately not a second helping of upkeep. **Upkeep bounds how many
creatures you can keep; preparation bounds how fast you can get them.**

- **One at a time.** An order placed while a countdown runs is refused, with a
  message saying how many turns remain. That is what makes it a plan rather than
  a queue.
- **No cancel.** The mana is committed when the clock starts. A commitment you
  can walk away from for free is not a commitment.
- **The AI plays the same rules** — it goes through the same state machine rather
  than spawning directly, so one writer owns placement, ledgering and timing for
  both sides and the two paths cannot drift apart.
- **The panel shows the countdown**, replacing the standing note about upkeep
  rates (the rate is still readable from the income arithmetic on the line above).
  The alertbox is fixed height and silently drops overflow, so lines are
  exchanged rather than added.

### Fixed

- **Headless runs froze at first AI contact.** The turn cycle swept three modals
  and had no `DipWizard` sweep at all, so a 700-turn run stalled dead at turn 55.
  Earlier 200-turn runs never reached contact, which is why it never showed —
  *a cycle validated at one horizon is not validated at a longer one.* Confirmed
  fixed: the re-run reached turn 85 and exited clean.

### Tooling

- `tools/gate_mana_upkeep.py` assertion 9: the countdown is seeded from the rung,
  pending is cleared on arrival (otherwise the creature respawns every turn
  forever), the arrival branch is mutually exclusive with commit (otherwise a
  rung-1 preparation is invisible), both the button and the AI refuse a second
  order while preparing, and the AI no longer spawns directly. Each proven to
  fire against its specific defect before being trusted.
- `tools/uiwalk/probe_summon_prep.py`: samples the panel **every turn** across a
  commit, because a rung-1 countdown is one turn long and any coarser cadence
  steps straight over the mechanic and sees nothing.
- `tools/uiwalk/probe_long_game.py` + `probe_slic/mom_probe.slc`: a read-only
  per-tribe sampler that surfaces AI mana, unit counts and creature counts onto
  the human panel, since the harness reads pixels and no AI's state is ever
  rendered. Install is idempotent at startup — a probe killed mid-run skips its
  `finally` and leaks its instrument into the scenario.

---

## [3.5.0] — 2026-08-01 — mana is an economy: creatures cost upkeep, not just a deposit

**Minor.** Additive. Old saves load and keep playing; creatures summoned before
the upgrade are simply untracked and are never charged, so nothing a save is
holding becomes invalid.

### The defect

Summoning cost **75 mana once and nothing afterwards**. That gave mana exactly
one sink, the sink was repeatable, and nothing bounded it — so a tribe with no
other use for the pool accumulated an unbounded pile of identical creatures. At
sphere rung 1 a Nature tribe's pool is `[Warbears]`, one creature, which is why
the report was *"I've still only seen one unit type from tribes of nature."*

The build lane was **not** the cause this time — v3.3.0 holds. Both gating walls
are exclusion-shaped, so Nature can research every mundane advance and build all
13 of its own units plus every neutral one. What flooded the map was the summon
lane, by accumulation.

### Added

- **Mana upkeep.** Summoned creatures cost mana every turn they live, scaled by
  the sphere rung they were rolled at (`rung x 2`), so a rung-5 Great Wyrm is a
  real commitment and a rung-1 Warbears is cheap. Income minus upkeep is the net.
- **Buildings generate mana.** Each sphere's own thematic buildings — Wizard's
  Fortress, Primal Source, Beacon of Wisdom, Mechanician's Guild, Merchant's
  Guild, plus a smaller second tier — add to the tally, so a tribe can *invest*
  in income instead of only waiting on population. Deliberately the same
  buildings the sphere already rewards on construction, not a second table.
- **Hard insolvency, weighted by upkeep.** When upkeep outruns income and the
  pool cannot pay, one creature is released — chosen by a random draw
  **weighted by its own upkeep**, so the hungrier the creature the likelier it
  is to evaporate. A rung-5 Great Wyrm is five times as likely to go as a rung-1
  Warbears; among nine cheap creatures and one dear one, the dear one carries
  **35.7%** of the risk. At most **one per turn**, so a deficit bleeds off
  gradually instead of wiping an army in a tick. Weighted rather than
  last-in-first-out because the creature most likely to go is then also the one
  that frees the most mana — the pool recovers fastest — and because a
  positional rule lets you shield an expensive creature by summoning a cheap one
  after it. **None of this happens unless you over-summon.**
- **The MAGIC STATUS panel shows the whole ledger** — income, upkeep and net on
  separate lines — so a pool that stops growing is legible rather than
  mysterious, and the arithmetic is checkable at a glance.
- **The AI now checks sustainability, not affordability.** It summons only while
  projected net income stays non-negative; when it cannot feed another creature
  it banks, and its production goes where it should — city units, the mainstay.

### Fixed

- **`CityHasBuilding` takes a QUOTED string**, unlike the `UnitDB(UNIT_X)` /
  `AdvanceDB(ADVANCE_X)` family. The bare form is a runtime *"Wrong type of
  argument"*, not a compile error, so the first cut of the building tally was
  byte-stable and passed **every** static gate, `mom_audit.py` (0 FAIL) and
  `backcast_slic.py --check` while being completely dead. Only the running game
  caught it.
- **`gate_ai_magic`'s pool parser** split the whole of `mom_summon.slc` and
  attributed every trailing `UnitDB(...)` to the last sphere block — so adding
  the upkeep rate table after the roll made it report Chaos rolling 16 other
  spheres' creatures. It now scopes to `MomSummonRoll`'s body.

### Tooling

- `tools/gate_mana_upkeep.py` (gate 27): ledger sizing, spawn-call arity,
  clear-on-invalid in the scan, bounded disband, call depth <= 1, no user call
  nested in another's argument list, quoted-ident builtins, and an
  upkeep-weighted disband draw. Proven to reject the pre-fix tree at **12
  violations** before being trusted; each later assertion proven to fire against
  the specific defect it describes.
- `tools/uiwalk/probe_mana_upkeep.py`: headless in-game probe of the panel
  arithmetic.
- `tools/test_disband_weighting.py`: the roulette draw ported verbatim from SLIC
  and measured over four varied ledgers, including the sparse and all-equal
  cases. Insolvency is genuinely hard to reach in play — a summon needs 75
  banked mana and each creature lowers net income, so a rung-1 tribe walks net
  down to exactly zero and can never bank 75 again — so the selection maths is
  tested directly rather than waited for.

---

## [3.4.0] — 2026-07-29 — the sentinel wonders are gone, and the panel says which rung

**Minor.** Additive plus a content removal that no save can be holding: the five
wonders culled were never buildable.

### Removed

- **The five `x`-sentinel wonders.** `Xlighthouse`, `Xapollo Program`,
  `Xstatue Of Liberty`, `Xwomens Suffrage`, `Xcure For Cancer` came from MOMJR's
  `Rules.txt` as `xLighthouse, 20, 0, no,` — the `x` name prefix **and** the `no`
  never-buildable sentinel — and neither lane excluded them, so they shipped with
  the sentinel baked into the display name. Not cosmetic-internal as previously
  filed: the Great Library's Warrior Code page listed all five to the player as
  wonders it enables (measured in-game, `runs/20260729-174823`).

  `wonders.csv` turned out to have an `IncludeInMoM` column that the generator
  **never reads** and that is `True` on all 28 rows — the intended exclusion
  mechanism did not exist. Culled at the control plane instead. **28 → 23
  wonders**, which is the count gate 24's own docstring already claimed. Zero
  `WONDER_X` references remain anywhere in `scen0000`; GL sections, `gl_str` keys
  and icons went with them.

### Added

- **The MAGIC STATUS panel now shows your sphere rung.** *"Sphere rung: 1 of 5 -
  a summon rolls over every rung you have reached."* Since 3.2 the summon draws
  from every rung unlocked, and the player had no way to see which pool that was
  — at rung 1 a sphere offers exactly one creature, which looks identical to the
  bug 3.2 fixed. Verified on screen, `runs/20260729-181301-summonvar/menu_t144`.

- **Gate 25 rejects the civ2 `x` sentinel** in any wonder ident or display name.
  Proven against the pre-cull tree first: **10 FAILs**, 5 idents + 5 names.

### Verified through the headless harness

- **Summoning works end to end.** Turn 144: multiple **Guardian Spirit** stacks
  standing on tiles *around* Eudoria — the caster's own sphere creature, placed by
  the occlusion-safe neighbour search rather than stacked on the capital. The arm
  click, the order surviving the turn boundary, and the spawn are all confirmed.
- **Summon variety is still not observed, and now we know why:** the panel read
  `Sphere rung: 1 of 5` at turn 144. At rung 1 a sphere's pool is exactly one
  creature *by design* — the 5×4 grid widens with the ladder — and the seat never
  researched up it. What remains unproven is only the rung ≥ 2 behaviour, which
  the static gate covers.
- Byte-stable; all scenario gates, faction gating 71/0, ai/summon, GL 784/784,
  `mom_audit` 0 FAIL.

### Harness (no player-visible effect)

- **The map edge-scrolled for entire runs.** CTP2's aui polls the **real** cursor
  via `GetCursorPos`, never our posted `WM_MOUSEMOVE`; with the window stashed
  past the right edge of a three-monitor desktop, the operator's cursor mapped to
  client `x = -584` and the engine scrolled left every frame. It never stopped
  because edge-scroll runs only while the window holds `SDL_WINDOW_INPUT_FOCUS`,
  which `_spoof_focus()` set before every input and nothing ever cleared.
  `_drop_focus()` now releases it after each input. Measured: 10 consecutive
  turns at exactly (0.0, 0.0) map translation, and the clock still advances
  4000BC → 3725BC.

---

## [3.3.0] — 2026-07-29 — a tribe can finally build its own troops

**Minor.** Additive: 3.2.0 saves load unchanged. 23 units move from a magic
ladder rung back onto the mundane advance MOMJR always specified for them, so a
tribe gains access earlier — nothing is removed, renamed or repriced.

### Fixed

- **Every sphere unit was locked behind the magic ladder, so tribes had no
  troops.** All 13 Nature units required `NATURE_LORE` — 1865 science, itself
  behind `GRAND_MASTERY` and `ELDRITCH_LORE`. Photographed in the Build Manager
  at turn 1: Eudoria's Units tab offered exactly **two** items, `Spearmen` and
  `Peasants`. Seventy-eight turns later the same capital reported *"There are
  already twelve units in that city, which is the maximum allowable units per
  tile"* — twelve identical Spearmen, because Spearmen was effectively the only
  choice. Reported in play 2026-07-28 as "the tribes of nature would only ever
  spawn one unit"; the previous release wrongly attributed that to the summon.

  **Cause.** 3.0's prereq rewrite pushed *every* sphere'd row onto a ladder rung
  derived from its cost. That is right for a fantastic creature and wrong for a
  racial troop, and MoM's design turns on exactly that distinction: troops are
  **built** in cities and are the mainstay, creatures are **summoned**. MOMJR
  already encodes which is which, in `advance_code_map.csv`'s `unit` lane —
  Centaurs → `SHAMANISM`, Elven Archers → `PANTHEISM`, Minotaur →
  `WARRIOR_CODE`, War Troll → `LEADERSHIP`, against Warbears → `NATURE_LORE`,
  Cockatrice → `NATURE_ADEPT`, Great Wyrm → `NATURE_MASTER`. The cost-derived
  tier is now a last resort rather than the default.

  **23 normal / 20 fantastic.** Centaurs now cost 455 science (`SHAMANISM`,
  AGE_ONE, no prerequisites) instead of 1865-behind-two-roots, and **Minotaur is
  buildable on turn one** — `WARRIOR_CODE` is a start advance. Racial troops stay
  faction-walled, so only Nature fields Elven Archers.

- **The summon pool collapsed 34 → 20**, the clean 5 spheres × 4 rungs grid.
  Centaurs and Elven Archers are no longer summonable, which was the other half
  of the same report: summoning a racial troop never made sense.

### Fixed (regressions caught during this change)

- The wall infers a block's sphere by reverse-looking-up its gate advance in the
  ladders. Once racial troops gated on mundane advances that belong to no ladder,
  the lookup returned nothing and **23 units silently fell out of
  `mod_CanCityBuildUnit`** — the wall dropped from 87 idents to 59 and every
  tribe could build them. `gate_faction_gating`'s A9 caught it. The sphere is now
  recorded at classification time instead of inferred.
- **A9 itself was rewritten.** Its premise — "sphere'd but on a mundane advance
  ⇒ every tribe reaches it" — held only while every sphere'd block was forced
  onto a rung. There are two independent gates: the advance, and the SLIC wall.
  It now asserts *sphere'd ⇒ walled*, and was re-proven by deleting Centaurs from
  the wall and watching it fail.

### Verified through the headless harness

- **Build Manager, turn 1** (`runs/20260729-173656`): Units tab photographed.
- **Great Library, Warrior Code page** (`runs/20260729-174823`), reached by
  `press: BuildEditorWindow.LibraryButton` and following the `Requires:`
  hyperlink — the engine rendering the live DB back: *"Warrior Code needs no
  prior research and is available from the first turn... It enables the units
  **Minotaur**, Peasants and Spearmen."*
- Generator byte-stable; all scenario gates pass; `gate_faction_gating` 71
  targets / 0 violations; `gate_ai_magic` PASS; GL 784/784; `mom_audit` 0 FAIL.

### Known open

- The five `x`-sentinel wonders are **player-visible**, not just internal: the
  Warrior Code page lists "Xapollo Program, Xcure For Cancer, Xlighthouse,
  Xstatue Of Liberty and Xwomens Suffrage" among the wonders it enables.
- Summon variety is still not observed on screen. The 78-turn probe clicked the
  arm 13 times and captured the SLIC reply *"You lack the mana for a summoning.
  A creature costs 75, and you hold 58"* — so the arm body runs and the economy
  is live — but early turns lacked mana and by the time the pool filled, the
  capital had hit the twelve-unit tile cap so no summon could land. **The build
  bug was masking the summon test.** Worth re-running now that cities are not
  jammed with Spearmen.

---

## [3.2.0] — 2026-07-29 — the ladder starts mattering, and the AI starts casting

**Minor.** Additive: 3.1.1 saves load unchanged and still make sense. Nothing is
renamed, repriced, or deleted — but the AI now spends a resource it previously
banked forever, so a save carried across this line will play differently from here.

### Fixed

- **Every sphere summoned exactly one creature, forever.** `MomSummonOrderTick`
  resolved the 75-mana summon through five CONSTANTS, one per player index.
  Nature was hardwired to `UNIT_WARBEARS` — **cost 4, the cheapest of its 13
  units** — so researching `NATURE_LORE → ADEPT → MAGE → WIZARD → MASTER` changed
  nothing about what mana bought, and 12 Nature creatures were unreachable by
  summoning. The six-rung ladder that 2.0 and 3.0 built was decorative *for the
  mod's headline feature*. Reported in play 2026-07-28.

  The summon now rolls, weighted, over every rung the caster has unlocked: the
  newest rung takes the widest band and older rungs keep a floor, with the bands
  cut from the *count* of unlocked rungs so adding a rung cannot leave a dead one.
  A fresh Nature tribe already rolls over Centaurs / Elven Archers / Warbears with
  no research at all. Heroes are excluded — unique tribe leaders, not summonable
  troops — via a new `unit_roles.heroes` roster in `mod_policy.json`.

- **The AI accrued mana every turn and could never spend a point of it.**
  `MomMagicPoolTick` accrues for all five sphere players, human or not, but
  `MomSummonChoice[p]` — the only thing that authorises a summon — was set in
  exactly ONE place: a **button body**, which only a human click reaches. So every
  AI tribe banked to the 100 cap and sat there for the whole game, and the ten
  `IsHumanPlayer` guards in the magic modules only ever *suppressed* output for
  the AI rather than substituting an action. The mod's headline system was a
  human-only privilege — and part of why two long headless runs ended when the
  script ran out rather than when the game did.

- **Summon result messages no longer name the creature.** Naming was safe while
  the summon was fixed; "Warbears lumber out" while a Great Wyrm stands in the
  capital is worse than saying nothing, and SLIC can only interpolate plain
  `{scalar}` — a unit index is not a name.

### Added

- **`mom_ai_magic.slc` — the AI's magic brain.** One `BeginTurn` handler, bound
  `p >= 1 && p <= 5` first and `!IsHumanPlayer` guarded, running a rule ladder over
  war state (`AtWarWith`) and pool level with `Random(100)` breaking ties so two AI
  tribes do not act identically. It pays the **same** 75/50 prices the human pays,
  and reuses `MomSpawnSphereUnit` so its summons get the same occlusion-safe
  placement instead of stacking on the capital tile. No `Message()` on this path —
  a messagebox aimed at an AI player is the message-queue overflow AV.

- **`mom_summon.slc` (generated) — rung tracking and the weighted roll.** The rung
  is read back off each unit's *existing* gate advance, so the summon table and
  `mom_gating.slc` cannot disagree about which rung owns a creature.

- **Gate 26 — `tools/gate_ai_magic.py`.** Asserts behaviour rather than reference
  integrity, because both defects above were invisible to every existing gate:
  nothing dangled. Checks that no sphere can roll another's creature or a hero,
  that every sphere offers more than one creature, that every ident is a live
  block, that the AI handler is bounded and AI-only, and that every roll band
  terminates at 100. **Each of those six assertion classes was proven to fire
  against a deliberately broken file before the fix was accepted.**

### Notes on what this cost to get right

- **`HasAdvance` was rejected despite 700+ uses across the other mods.** All of
  them pass a bare `ID_ADVANCE_*`, and the engine **silently auto-creates unknown
  symbols** — an unresolvable name returns a permanent *false* rather than erroring
  — while `validate_all_surfaces.py`'s surface-7 regex is anchored `\bADVANCE_` and
  cannot match inside `ID_ADVANCE_`. Nothing in the repo would have caught the
  typo. Rungs are tracked by comparing `value[0] == AdvanceDB(...)`, which is
  covered.
- Two self-inflicted defects were caught by instruments, not review: `;` is not a
  comment in a string table (`#` is) and killed the load until the native-dialog
  error channel named the exact line; and rung 0 owns no creature, so every tribe
  at game start would have summoned *nothing* while the arm still looked
  affordable — fixed at both the root mapping and with a floor in the roll.

### Known open — what is NOT proven in a running game

Both features below are verified **statically** (generated pools, seven gate
assertions each proven against a broken file) and the SLIC layer is verified to
load and run clean across 25 headless turns with **zero SLIC errors**. Neither
has been observed happening on screen.

- **Summon variety is unproven in-game.** Three probe attempts failed, all on one
  root cause, all recorded in `tools/uiwalk/probe_summon_variety.py`'s parked
  header: a hardcoded arm coordinate was swallowed by a `Message()` window
  stacked above the alertbox; dismissing that at the measured close point opened
  the OPTIONS menu instead, because the constant is only valid while a box is up;
  and the frame-measuring third attempt found `0 buttons` because the MAGIC
  STATUS box never opened at all in that driver. Its fall-through clicks panned
  the map once per attempt — the operator watched the view scroll in a loop. The
  blocker is upstream of the click (`j` not raising the menu from that driver,
  while the same keypress works from a steps JSON), so it is a harness defect,
  not a mod one.
- **AI mana spending is not observable at all** by this harness: the pool renders
  for the human alone, and the harness reads pixels only.

---

## [3.1.1] — 2026-07-29 — every wonder message printed its name twice

**Patch.** No rule, cost, age, or save-format change — 3.1.0 saves load
unchanged. A string the engine has always looked for was simply absent, so a
message that was already supposed to read correctly now does.

### Fixed

- **`Bardic CollegeBardic College`.** Every wonder message rendered the wonder's
  name twice, concatenated with nothing between — seen in the wild on the
  rival-wonder warning. `#ARTICLE` is not a computed article: it is an
  **ident-suffix lookup**, and the engine resolves
  `{wonder[0].name#ARTICLE}` by reading `<IDENT>_ARTICLE` out of `gl_str.txt`,
  falling back to the *name* when the key is missing. Eleven messages in
  `info_str.txt` are written as two adjacent interpolations —

  ```
  WONDER_STARTED "... has begun work on {wonder[0].name#ARTICLE}{wonder[0].name}."
  ```

  — so one missing key doubles the name in all of them: `WONDER_BUILT`,
  `WONDER_BUILT_QUEUE_EMPTY`, `WONDER_STARTED`, `WONDER_STOPPED`,
  `WONDER_ALMOST_FINISHED`, `WONDER_COMPLETE_OWNER`, `WONDER_COMPLETE_ALL`,
  `WONDER_DESTROYED`, `WONDER_OBSOLETE`, `NANITE_DEFUSER_ELIMINATES_NUKES`,
  `PROTECTED_FROM_CONVERSION_BY_WONDER`. The base tree ships 30 of these keys and
  wonders are the only database that uses the modifier; MoM's `gl_str.txt`
  overrides the base file and shipped **zero**.

  **Two independent lanes were broken, and fixing either alone leaves the bug.**
  `_prune_gl_strings` deleted every *inherited* key, because a trailing
  `_ARTICLE` never matched a keep-id — so `WONDER_PYRAMIDS_ARTICLE` read as an
  orphan, and anything written later would have been pruned straight back out.
  Meanwhile the wonder writer never emitted MoM's *own*. The pruner now
  normalises `_ARTICLE` to its owning ident, exactly as it already did for a
  leading `DESCRIPTION_`, and the writer derives the article from the display
  name: `""` when the name is already definite or possessive, `"the "`
  otherwise. That reproduces the base game's own convention
  (`WONDER_THE_APPIAN_WAY_ARTICLE ""`, `WONDER_ARISTOTLES_LYCEUM_ARTICLE ""`,
  `WONDER_PYRAMIDS_ARTICLE "the "`). Derived rather than authored in a csv
  column, so renaming a wonder cannot desync the two.

  Now reads *the Bardic College*, *the Guild of Legends*, *The Parthenon*,
  *Gaia's Shrine*.

### Added

- **Gate 25 — `check_wonder_articles`.** Asserts the *result* rather than either
  lane: every `WONDER_*` block has an article key, and no article key outlives
  its wonder. Proven against the unfixed tree **before** the fix was written —
  28 FAILs, one per wonder. A gate that has never rejected anything is not
  evidence.

### Known open

- Five wonders still display a literal `X` — `Xlighthouse`, `Xapollo Program`,
  `Xstatue Of Liberty`, `Xwomens Suffrage`, `Xcure For Cancer`. Traced to civ2
  source `Rules.txt:251,267,269,273,275`, where MoMJR marks them
  `xLighthouse, 20, 0, no,` — the `x` name prefix *and* the `no` never-buildable
  sentinel. They are correctly disabled in the scenario (`EnableAdvance ==
  ObsoleteAdvance`, no effects, absent from every AI build list, and gate 24
  already enforces that), so this is cosmetic residue on the Great Library page
  only.
- The fix is verified statically, not on screen. The message fires only when a
  rival starts a wonder, which cannot be triggered on demand, and the harness
  reads pixels only.

---

## [3.1.0] — 2026-07-27 — the victory nobody could reach

**Minor.** 3.0.x saves load unchanged and every rule, cost and age is untouched.
It is not a patch because it restores a whole system rather than repairing one
value: the AI can now build wonders at all, which means the scenario's win
condition exists for the first time.

### Fixed

- **No AI player could build any wonder, so the game had no winner.** All seven
  lists in `aidata/WonderBuildLists.txt` shipped empty. The reason was sound —
  an empty scenario override stops the engine falling back to stock aidata,
  whose wonder idents do not exist in the MoM WonderDB and would dangle — but
  the engine picks wonders for an AI goal *only* from these lists. Empty meant
  none of the 23 live MoM wonders was ever a candidate. And since
  `EndGameObjects.txt` makes the victory *hold `WONDER_RUNE_OF_RULERSHIP` for 10
  turns*, an AI-only game had **no reachable terminal state except the year
  2300**. The lists are now derived from the generated `Wonder.txt` — which
  keeps the original guarantee, because every ident is read out of the
  scenario's own database — and each wonder is filed by its own effect lines, so
  it re-files itself when its effects change instead of drifting from a
  hand-typed roster. 23 live wonders across 7 lists; the 5 self-obsoleting `X*`
  stubs are excluded.

- **A rival's diplomatic proposal froze the turn loop indefinitely.** A tribe
  demanding tribute opens a modal `DipWizard` window, and END TURN never fires
  again. The headless harness now rejects it every turn. Reject, never accept:
  an unattended playthrough must not hand over gold.

### Verified

- **The scenario now ends.** A headless playthrough on the fixed scenario
  reached a terminal state — `DEFEAT` at **turn 390 / 1505AD**, score 4380 — the
  first time any run has ended because the *game* ended rather than because the
  script ran out. Attribution is by controlled experiment, one variable: the same
  walk against a scenario whose wonder lists were emptied again played
  **420/420 turns with no endgame window and no stalls**. Populated lists end the
  game; empty lists do not. (One run per arm, different maps — the direction is
  the prediction, not a rate.)

- **Where the game actually ends on the clock**: `DiffDB.txt` TIME_SCALE runs
  20 yr/turn to turn 150, then 10, 5, 2, and 1 from turn 600, so
  `END_OF_GAME_YEAR 2300` falls at **turn 1000**. Turn 200 is 500BC and turn 600
  is 1900AD — no 200- or 600-turn script could ever have ended the game on time.

### Added

- **Gate 24, `check_wonder_build_lists`.** Asserts that every ident in the AI
  lists is a real `Wonder.txt` block, that no self-obsoleting stub is offered,
  that every live wonder appears in at least one list, and that the wonder named
  by `EndGameObjects.txt` is among them. Validated against the pre-fix scenario
  first, where it produced **24 failures** — a gate that has never rejected
  anything is not evidence.

- **`tools/balance_report.py`** — the first check in this repo that asks whether
  the mod is *fair* rather than whether it is *legal*. Cost-efficiency outliers
  on a median/MAD band over log(power/cost), sphere parity, and a stat-twin
  check for units with an identical combat line at very different prices.
  Reports; does not gate.

- **`tools/uiwalk/detect_endgame.py`** — tells an ENDING apart from a FREEZE.
  Both produce identical zero-delta frames, so `decode_run.py` reported the
  first real ending this project has ever reached as its worst failure class
  (`STALLED at 117 checkpoints`). This reads the `VictoryWindow` title strip
  instead. Validated both directions: it finds the ending at turn 390, and
  reports no ending for the run that genuinely froze.

- **`tools/uiwalk/make_full_game.py`** — the full-game walk is generated from a
  turn count instead of being a hand-maintained 1553-element JSON pinned at 200
  turns. Reproduces the verified 200-turn file body-identically.

### Known open

- **All 55 units have `MaxHP 10`.** The civ2 source spreads hp across `1h..6h`;
  the port flattens it, so durability differentiates nothing. This is the
  largest dimension lost in the conversion and is **not** fixed here.
- `UNDEAD_DRAGON` costs 1200 against `STORM_DRAKE`'s 4000 for an identical
  60/30/10/2 line. Faithful to the civ2 source, which prices it 3 where Storm
  Drake is 14 — an upstream MoMJR authoring bug, carried correctly.
- `INFERNAL_DEVICE` delivers ~15x the median combat value per shield.
- Sphere totals span 2.56x (chaos 1165, death 455); rosters span 1.86x.
- `ADVANCE_RUNE_LORE` unlocks the victory wonder at **AGE_TWO of seven** and is
  ungated, so the win is available before most of the magic ladder exists.
- `BattleViewWindow.ExitButton` still does not close the battle view.

## [3.0.1] — 2026-07-27 — the diplomacy screen every tribe could not open

**Patch.** No rule, cost, age, or save-format change — 3.0.0 saves load
unchanged. One shipped art reference was wrong for all five tribes, and the
harness that proves a playthrough could not survive its own success.

### Fixed

- **Every tribe's diplomacy parchment pointed at art that does not exist.**
  `civilisation.txt` shipped `Parchment` 42–46 for the five tribes.
  `dipwizard.cpp:2673` builds the diplomacy background filename at *runtime* as
  `UPDG%02d.tga` from that field, so there is no database reference to dangle
  and no existing gate could see it. A regex scan of every
  `ctp2_data/**/*.zfs` returns exactly `updg01`–`updg41` plus `updg99` — so all
  five tribes resolved to a missing Targa, i.e. a native load-error modal that
  stops the engine's message pump. Fixed in the control plane
  (`tools/momjr_csv/players.csv` → 3 / 7 / 19 / 31 / 39).

  This is the failure mode worth remembering: the symptom is a frozen frame
  with nothing in the console, because the modal *is* the freeze. It survived
  three releases for exactly that reason.

### Added

- **Gate 23, `check_parchment_range`** — every `Parchment` must be in 1–41 or
  99. Written, then run against the known-bad `civilisation.txt` **before** the
  fix was generated; the first version used a `^(\w+)\s*\{` block regex and
  *passed* the bad file, because block headers here carry a trailing `#N` and
  open the brace on the next line. Rewritten line-wise and re-proven at 5
  FAILs. A gate that has never rejected anything is not evidence.

### Harness

Ships in `tools/uiwalk/`; no scenario data touched.

- **The per-turn ping lost its button.** An injected `enter` only advances the
  turn if a mouse message reached the engine — but it does not need a *button*.
  The old ping was a real click on "inert" top-bar chrome at a pinned
  `(600, 6)`; once a DPI-scaled display became primary, that pixel was no
  longer inert and three consecutive runs died `0xC0000005` on the first click.
  Replaced with a button-free `WM_MOUSEMOVE` (`hover` verb) aimed by `fx`, a
  fraction of the live client width. **Aim derived from the live frame is safe;
  aim pinned to a pixel is not.** Result: **200 turns, 4000BC → 150AD**, five
  times the previous 40-turn ceiling, zero stalls across 100 checkpoints.
- **`decode_run.py` cried STALL on a healthy run.** Its 2000px threshold was
  fitted on five-turn checkpoints; applied per-turn, a camera parked over
  unexplored ocean legitimately redraws only the build counter (~300–1200 px).
  The bug the decoder exists to catch produced *byte-identical* frames, so the
  bar is now 100. A threshold carries the sampling density it was measured at.
- **Shots are sorted numerically.** `100_turn190.png` sorts before
  `66_turn122.png` as a string, so the first run past 99 checkpoints silently
  reported its last turn as 188 and compared its tail out of order.
- **Teardown kills the game on the abort path.** `kill()` derived the PID from
  a window handle that is already dead when a run aborts, so it terminated
  nothing and left a window on screen. The PID is now captured at window
  acquisition.

### Known open

Both harness-side, neither blocks a full playthrough:

- `BattleViewWindow.ExitButton` does not close the battle view, though the path
  matches `battleview.ldl:149`. Turns still advance; the frame stays occluded.
- The SLIC alertbox is never dismissed — one message persisted from turn 124
  through turn 200.

---

## [3.0.0] — 2026-07-27 — the Renaissance cap actually applies

**Major.** 2.0 announced "mundane tech ends at the Renaissance." It did not. The
cap was written, shipped, and enforced nothing — so 3.0 is the release where the
2.0 headline becomes true. Ages 5–7 are now magic-only, verified in-game.

The version bump is not ceremonial. Five advances change age, and one changes
cost by 60% (Ecognomics 3900 → 2425), so a 2.x research plan no longer costs what
it did and a 2.x save references the old bands.

### Fixed

- **The Renaissance cap was dead code.** `_relayout_advance_ages` decided
  "is this advance mundane?" with `ident in momjr` — i.e. "did MoM author it?"
  MoM authored essentially the entire tree, so that test was true for nearly
  every ident and the mundane branch never ran. **Ecognomics, Sanitation, Sea
  Lore, Greater Fauna Lore** (AGE_FIVE) and **Sea Mastery** (AGE_SIX) had drifted
  above the cap on depth banding alone. The discriminator is now a derived
  *magical closure* — is this a sphere-ladder rung, or does it transitively
  require one — which is also self-consistent with the no-advance-below-its-
  parent guarantee, since a mundane advance's prerequisites are mundane by
  construction. Post-fix distribution: AGE_ONE 35, TWO 43, THREE 19, FOUR 28,
  FIVE 5, SIX 7, SEVEN 7. Every one of the 19 advances above AGE_FOUR is
  magical.
- **`mom_sphere_home.slc` was written when its policy was off.** The emit block
  sat nested under the age-re-layout branch, so any run that re-aged anything
  wrote a SLIC file citing five `ADVANCE_HOME_*` that only exist when
  `sphere_home_exclusivity` is enabled — five dangling advance refs, the
  mom-db-error crash class. The sever pass ran *earlier* in the same run, so the
  mod only looked self-healing because a second generator run cleaned up after
  the first. Now guarded on the policy flag; one run is clean.
- **`mom_audit.py` reported a phantom missing building.** `IMPROVE_X` was
  harvested out of a documentation comment in `mom_func.slc`. SLIC text is now
  comment-stripped before idents are harvested. Audit: 65 PASS / **0 FAIL**.

### Added

- **Gate 22 — `check_renaissance_age_cap`** in `validate_scenario.py`. Reads the
  *shipped* `Advance.txt` and re-derives the magical closure independently of the
  writer, so the gate and the generator cannot agree on the same mistake. Control
  run against the pre-fix artifact: 5 FAILs, matching the 5 known strays.
- `ADVANCE_ECOGNOMICS_HISTORICAL` prose in `gl_descriptions.csv` (it was a stub).
- `tools/uiwalk/steps/newgame_gl_age_cap.json` — headless confirmation walk.

### Decided (previously open, now closed)

- **Ecognomics is native MoM, not a CTP2 import.**
  `H:\games\civ2\MOMJR\MOMJR\Rules.txt:107` — `Ecognomics, 4, 1, Uni, Ban`,
  i.e. University + Banking, exactly what the Great Library now shows. It stays.
- **`FUTURE_TECHNOLOGY` at AGE_SEVEN is correct.** Also MoM-native
  (`Rules.txt:174`), and its prerequisites are `DEATH_WIZARD` + `CHAOS_LORE`, so
  it is magical by closure, not a stray modern leftover.
- **`PrerequisiteBuilding` chains stay at 0.** Stock CTP2 ships 49; MoM ships
  none. This is faithfulness, not a gap: civ2's `@IMPROVE` record has four fields
  — name, cost, upkeep, *advance* prereq — and no building-prerequisite concept
  exists in the source at all. Not a todo.

### Verified

Headless, in-game, Great Library STATISTICS pane (run `20260727-082211`):
Ecognomics **Cost 2425 / Age 4**, Sanitation 1825/4, Sea Lore 2735/4,
Sea Mastery 3095/4, Greater Fauna Lore 2735/4. Plus byte-stable double
generator run, `validate_scenario` all gates, `gate_faction_gating` 0/71
violations, `gate_gl_descriptions` 784/784, `backcast_slic --check` current.

---

## [2.0.0] — 2026-07-26 — faction gating + age re-layout

**Major.** The five tribes are now distinct in the data, not just in SLIC's
player index, and the tech tree ends at the Renaissance with the Masters of Magic
ladder spread across Ages 5–10.

The version bump is not ceremonial — 2.0 breaks compatibility three ways. Saves
from 1.x reference 113 advances, 6 governments and 17 tile improvements that no
longer exist. Any downstream edit to `units.csv` or `improvements.csv` needs the
new `sphere` column. And content that was buildable by everyone in 1.x is now
gated per tribe, so a 1.x build order may no longer be legal.

Planned in
`~/.claude/plans/synchronous-petting-naur.md`; postmortem in `PLAN.md`.

### Added

- **`mod_CanPlayerHaveAdvance` / `mod_CanCityBuild{Unit,Building,Wonder}`** —
  generated `scen0000/default/gamedata/mom_gating.slc`, `#include`d from
  `scenario.slc`. Because `mod_CanPlayerHaveAdvance` sits inside `GiveAdvance`,
  one function fences research, huts, conquest, spy steal, diplomacy and the
  Great Library. Generated, never hand-edited.
- **`sphere` as a first-class control-plane column** on `units.csv` and
  `improvements.csv` (`life|nature|sorcery|death|chaos|neutral`), plus
  `unit_factions.csv` as the reviewable curated taxonomy. In the data plane
  `sphere` means *who may build it*; in SLIC it means *who gets a bonus* — a
  neutral building with a per-sphere bonus is correct, not a contradiction.
- **`tools/gate_faction_gating.py`** — 9 assertions over the ladder, the sphere
  matrix and the generated SLIC. Assertion 5 (every ident in `mom_gating.slc`
  exists in the generated DB) is the one that matters: a typo there is a silent
  no-op, the worst failure mode available. Registered in `validate_scenario.py`
  as `check_faction_gating`.
- **Gate 11, `check_effective_tree_advance_refs`** — scans the tree the engine
  will *actually load* (scenario override else base) for dangling references
  across 13 record families. See the DB-Error section below.
- **Buildings and wonders now carry a sphere**, so tribe identity extends past
  units.

### Changed

- **Age layout.** Age 1 ancient mundane + the two magic roots; Ages 2–4
  classical/medieval/renaissance mundane paired with `*_MAGIC` / `*_LORE` /
  `*_ADEPT`; Ages 5–7 `*_MAGE` / `*_WIZARD` / `*_MASTER`; Ages 8–10 the MoM
  capstones. **Mundane tech ends at Age 4.** Age is derived from the ladder rung,
  so a rename cannot desync it.
- **Prereq rewrite.** A unit or improvement with a real sphere is re-anchored
  onto that sphere's rung, tier from existing cost banding; `neutral` rows keep
  their prereq. Without this the re-layout moves nothing — content follows its
  enabling advance, so 20 of the 33 Age-1 units were only ever going to leave Age
  1 by being re-anchored. The pass runs after the unit mask and cost retune and
  before `gl_descriptions.apply_descriptions`, which quotes the prereq in derived
  prose.
- **SLIC sphere matrix completed.** Chaos gained its four missing branches
  (grant-building, milestone building + unit, build-burst); Death gained
  `MomCountDeathFoci`. `mom_msg.slc` spawns now use the occlusion-safe placement
  from `MomSpawnSphereUnit` instead of the raw city tile.
- **`p <= 5` bound** added at the eight lower-only guard sites. It cannot fire
  today — `civilisation.txt` ships only BARBARIAN plus the five tribes — which is
  exactly why it is there for whoever adds a civ next.
- Four stale `slic_purpose.json` descriptions corrected; `slic_inventory.csv`
  gained a `sphere` column so these gaps are machine-visible next time.

### Removed

- **113 advances** (71 modern, ~30 `*_WAW` junk, 11 modern pollutants). Zero kept
  advances had a deleted prerequisite — the cut was clean at the tree level. All
  fallout below is downstream citation, not tree damage.
- **6 modern governments** (Communism, Corporate Republic, Democracy, Ecotopia,
  Fascism, Technocracy, Virtual Democracy). Anarchy, Monarchy, Republic and
  Theocracy survive, which is the correct set for a Renaissance cap.
- **17 industrial/modern tile improvements** (undersea everything, maglev, radar,
  air bases, hydroponic farms, listening posts, …). Basic infrastructure is
  untouched: Farms, Advanced Farms, Mines, Road, Railroad, Nets, Fisheries, Port,
  Fortifications, Trading Post and the five vegetation terraforms all remain.
- Authored HISTORICAL Great Library text for the deleted advances, pruned from
  `gl_descriptions.csv`.

### Fixed — the DB-Error modal class (all three, one root cause)

Every *"X not found in Y database"* modal traced to the same defect: **static
gates only inspected files the scenario overrides, but the engine loads the
base-tree copy of any gamedata file the scenario does not ship.** Deleting 113
advances and 17 tileimps turned every base-tree file citing a deleted ident into
a load-killing landmine that no gate could see.

| Modal | Base-tree file | Fix |
|---|---|---|
| icon lookup | `ADVANCE_NA` sentinel's fallback icon | restore `ICON_ADVANCE_DEFAULT` — the prune ate it because `ADVANCE_DEFAULT` is not a live advance |
| "Industrial Revolution not found in Advance database" | `Pop.txt` | re-anchor `POP_LABORER` → `ADVANCE_CONSTRUCTION`, `POP_MERCHANT` → `ADVANCE_TRADE` |
| "Listening Post not found in terrainimprovement database" | `aidata/ImprovementLists.txt` | re-anchor `IMPROVEMENT_LIST_MISC` → `TILEIMP_TRADING_POST` |

Re-anchor rather than delete — an empty AI list is an untested engine path.
Both fixes are generator passes (`_scrub_dead_advance_surfaces`,
`_scrub_dead_tileimp_surfaces`) that pull the base file into the scenario and
rewrite it, so they cannot rot.

Two traps that cost hours and are now documented:

- The engine prints the **display name**, not the ident, so grepping "Industrial
  Revolution" finds nothing.
- The engine **aborts on the first dangling reference only**, so launching the
  game discovers them one at a time at ~5 minutes each. Using the game as the
  scanner was the method defect; gate 11 replaces it with one read-only sweep.

Gate 11 needs two scopings to reach zero false positives: restrict to files the
engine genuinely parses (base `Improve.txt`, `endgame.txt`, `order.txt`, the
`*icon.txt` exports and `Units_{historic,release}.txt` all carry dead refs and
are inert — `uniticon.txt` is the sole runtime icon DB), and **strip `//`
comments before tokenising**, since `aidata/strategies.txt` lists seven deleted
governments entirely inside comments.

### Fixed — other

- `WONDER_GNOME_TREASURY` re-anchored to `ADVANCE_BANKING`; `NATURE_PRESERVE` to
  `ADVANCE_NATURE_MAGIC`; `ADVANCED_MINES` to `ADVANCE_ALCHEMY`; the seven
  terraform improvements onto the Nature ladder, which turns an orphan cleanup
  into a faction-identity win.
- `UNIT_SETTLER.ObsoleteAdvance` cleared.
- `assign_unit_factions.py` no longer reads a `source` column that
  `units.csv` never had — its `base`/`gated` split was degenerate. Dead
  `STARTER_COST` removed.
- `check_effective_tree_advance_refs` walked `scen.parents` upward instead of
  indexing a fixed depth. The fixed index assumed an absolute path, and
  `--scenario scen0000` is relative, so the guard returned early and **silently
  disabled the entire gate**. A gate that cannot fail is worse than no gate —
  always run the negative control.

### Verification

Generator exit 0 and byte-stable on rerun across `Advance.txt`, `Units.txt`,
`buildings.txt`, `ImprovementLists.txt`, `Pop.txt`, `mom_gating.slc`.
`gate_faction_gating` 71 targets / 0 violations; `gate_gl_descriptions` 784/784;
`validate_scenario --scenario scen0000` all gates. Negative control on the
unfixed tree returned exactly one failure — the reported bug — and zero false
positives. Headless boot reaches turn 1, 4000BC, no modal, no leaked processes.

### Known open

- **AI research thrash** unmeasured past turn 1. Denying an advance the AI has
  committed to may loop its selection rather than redirect it, and no SLIC hook
  observes AI goal-picking, so this needs a live game to ~turn 40.
- **`uiwalk.py` abort teardown** logs *"leaving it running"* instead of killing
  the process. It did not fire on the last run, but the path that leaked
  `ctp2.exe` processes is unchanged.

---

## Earlier work

Condensed from commit history; grouped by what broke rather than by date.

### Art and sprites

- **Unit sprite extent and anchor are one coupled bug** — anchoring on the pixel-
  mass centroid with extent at p85 makes units draw centre-mass. Changing extent
  without the anchor moves the unit off its tile. (`b6542ed`, `5f17ef4`)
- **Spearman missing from the map** — the engine reads *both* `GU%.2d.SPR` and
  `GU%.3d.SPR`; the builder wrote only one name. (`b212730`)
- **Icon over-zoom** — the extractor was a third, unaccounted producer of icon
  art. Uniform median==max across 55 files was the tell that a normalisation
  step, not source variance, was responsible. (`ca7ee5f`)
- `units.csv` gained an explicit `art_cell_index`; the old `cell_index` was live
  and wrong. (`f676469`)

### Pipeline and build

- **Buildings were all 1-turn builds** — the age-band cost rescale ran ~1300
  lines *before* the ingest that overwrites `buildings.txt`. Pass ordering, not
  arithmetic. (`b94b679`)
- **SLIC became a control-plane dimension**, flowing backward into the xlsx
  (one tab per dimension, cells holding real source). (`58d497f`, `4ff7b7d`)
- `mom.zip` is the **mod**, not the repo — the repo holds the code.
  (`770dbd8`)

### Magic and gameplay

- **Life could raise zombies** — summons are now gated to the caster's own
  sphere. (`b64eda1`)
- **Summoning priced at 75 mana**, with the pool accumulating instead of
  self-discharging. The old pool-overflow auto-summon had made the spellbook
  unaffordable by construction. (`8a9b1a3`, `f552582`)

### Harness

- **Alertbox arms are clickable** at the frame-measured centre — this retracts
  the earlier "posted buttons are lethal" claim. Dismissal aims at the
  last-declared arm. (`8b3c81d`, `783386f`, `d6baefb`)
- Headless steps that **observe** building turn counts in the Build Manager,
  rather than asserting against goldens. (`41b04d3`)
