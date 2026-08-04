---
description: 'Powers a player EARNS rather than buys — capacity granted by artifacts, creatures unlocked by holding other creatures, and bounded wishes from a genie or a captured avatar. Every high-impact effect names a reachable counter, so it is a threat to prepare against rather than an event that simply happens to you.'
---

***definitions***

- :Anchor: is the fixed 200 mana pool defined by [[fixed-anchor-scaling]]. This
  spec extends it and does not repeal it.
- :EarnedCapacity: is a temporary increase to a player's pool above the
  :Anchor:, granted by a possession and lost with it. It is stated as a
  FRACTION of the :Anchor:, never as an absolute.
- :ConditionalUnlock: is a creature or effect that no rung of the summon ladder
  can reach, opened instead by holding a stated set of things — three dragons, a
  building, an artifact.
- :Wish: is one entry in a fixed, enumerated list of effects. There is no
  open-ended wish.
- :WishTier: is `minor` or `major`. A :Genie: grants only `minor`; only a
  captured :Avatar: grants `major`.
- :TargetedEffect: is a :Wish: or creature ability aimed at a specific city or
  unit belonging to another player.
- :Counter: is the stated, reachable condition under which a :TargetedEffect:
  fails or rebounds — mounted ballistae on a city wall, a veteran escort.
- :PersistentHazard: is a :TargetedEffect: that changes the RULES of a place
  rather than its state: it alters the ground, then recurs on a schedule the
  victim can see coming but not prevent.
- :PoisonedGift: is a :PersistentHazard: whose altered ground is also BETTER
  than what it replaced. The victim chooses between abandoning it and working it
  under threat, and that choice is the mechanic.
- :Attributable: describes a divergence between players that can be traced to a
  named in-game event, as opposed to a constant that differed from turn one.
- :Site: is a map location where a :Vessel: may be found — a cavern, a ruin, the
  remains of a lost city. It is defined by terrain and neighbourhood, never by a
  bare random roll.
- :Vessel: is a discovered object that carries a power rather than being one — a
  lamp holding a :Genie:. Found, not built; the power comes out of it later.
- :Precondition: is the terrain-and-neighbourhood test a tile must pass to be a
  :Site:. Because it depends only on the map, it can be evaluated ONCE at game
  start rather than per turn.

***requirements***

**The STARTING pool SHALL remain the :Anchor: for every player.**
:EarnedCapacity: is added on top and only ever by an in-game cause.

> This is the whole reconciliation with [[fixed-anchor-scaling]], and it is a
> real distinction rather than a loophole. That spec forbids a per-peer
> *baseline* because a constant that differs from turn one creates a degenerate
> direction in the parameter space — you cannot tell tuning from outcome.
> :EarnedCapacity: is :Attributable:: every player starts identical, and any
> later difference has a cause you can point at. Earned divergence is the
> mechanic; assumed divergence is the defect.

**:EarnedCapacity: SHALL be expressed as a fraction of the :Anchor:** (`+25%`,
not `+50`), so the anchor stays the unit of account and a later change to the
anchor rescales it automatically.

**:EarnedCapacity: SHALL be revocable.** Lose the artifact, lose the capacity;
if the pool then exceeds the new maximum it is clamped, not banked.

**A :ConditionalUnlock: SHALL state its condition in things the player can
SEE.** Counting creatures they own or buildings they built is legible; a hidden
counter is not.

**A :Wish: SHALL come from an enumerated list.** The list is the design.

> The tiers are the limit that makes the fantasy safe. A :Genie: is common
> enough to be a tactic, so it grants only `minor`. An :Avatar: must be
> CAPTURED — a tribe leader taken alive — which is rare, costly, and visible to
> the victim before it happens.

**A :TargetedEffect: SHALL leave the target something to DO, and SHALL NOT
target a capital.**

> This supersedes an earlier draft that said "SHALL NOT destroy a city outright"
> and justified it by magnitude. Magnitude was the wrong axis. A one-shot
> deletion is bad because it removes the victim's ability to respond; a hazard
> ten times larger is fine if it demands a response instead of ending the
> conversation. **Duration and answerability are the axes, not size.**

**Magic SHALL be calibrated to a FANTASY ERA'S imagination, not to a modern
weapon.**

> Vesuvius was the ancient world's apocalypse. The scale to reach for sits
> between the era's most powerful conventional weapon and the unthinkable — and
> the unthinkable in that frame is a mountain opening, a plague, a river of
> fire. Magic does not have to out-do a warhead to be terrifying; it has to
> out-do a catapult by enough that no catapult answers it.

**A :PersistentHazard: SHALL be preferred to an instant effect of the same
weight.** Six TRIZ inversions produce it from "destroy the city", and each one
is a design gain rather than a compromise:

| TRIZ move | applied |
|---|---|
| The other way round (13) | change the GROUND, not the city |
| Segmentation (1) | one apocalypse → many small eruptions |
| Periodic action (19) | intermittent, so there are planning windows |
| Local quality (3) | exposure varies with distance from the mountain |
| Prior counteraction (9) | defences buildable BEFORE the first blast |
| **Harm into benefit (22)** | **volcanic soil is the most fertile there is** |

> Move 22 is the one that changes the design. A cursed tile that is also the
> best tile turns grief into a :PoisonedGift: — and that IS the operator's
> "mixed wish", arrived at from the other direction. It also makes the effect
> usable on ONESELF: accepting recurring devastation for yield is a coherent
> Chaos strategy rather than an own-goal.

**A :PersistentHazard: SHALL be geographically conditioned.** A volcano needs a
mountain. Terrain that must already be there makes the wish a matter of where
the victim settled, which is a decision they made and can learn from.

**Every :TargetedEffect: SHALL declare a :Counter:, and that :Counter: SHALL be
reachable by the target before the effect is available to the attacker.**

> A counter unlocked later than the threat is not a counter, it is a delay. The
> tech that mounts ballistae on walls and on ships must sit at or below the
> advance that opens the dragon.

**A :Counter: SHALL be expressed in state SLIC can actually read.**

> MEASURED against the 230-file corpus: `IsVeteran` (4 sites) and
> `ToggleVeteran` (6) exist; **`IsEntrenched` does not exist at all**. So
> "fortified OR veteran" is not directly expressible. Either the rule leans on
> veteran alone, or fortification is latched by SLIC from the `EntrenchOrder` /
> `DetrenchOrder` events into state this mod maintains — which costs an array
> and a lifetime, and must be judged against that cost rather than assumed free.

**A :Vessel: SHALL be found at a :Site:, never scattered at random.**

> Reward density and danger density are the same map. A lamp in open grassland is
> a lottery ticket that pays whoever built the most explorers; a lamp in the
> caverns of a lost city, in bad terrain, with barbarians thick around it, is a
> CONTESTED OBJECTIVE — it asks whether you will commit force, which makes it a
> mid-game decision instead of an early-game scramble.

**A :Site:'s :Precondition: SHALL be evaluated at GAME START and stored, not
recomputed per turn.**

> The test is "treacherous terrain AND near a lost city", and both halves are
> map facts that do not change. Evaluating a neighbourhood predicate over every
> tile every turn would be the most expensive thing in the mod for an answer
> that is constant. Compute the set once, keep the sites, spend nothing after.
> This is the operator's own point: some huts carry PRE-CALCULATED
> preconditions, and the alternative is a per-turn distance scan.

**A :Site: SHALL raise the barbarian presence around it**, so the reward is
guarded by something the map itself explains.

**A :ConditionalUnlock: or :Wish: SHALL NOT be granted to a player who is not in
play.**

> Not hypothetical. Chaos has 0 units and 0 mana in all ten samples of a
> 200-turn run, and Death holds its cap for 200 turns without summoning. A power
> layered on top of a tribe that never enters play is invisible work.

***scenarios***

**Given** a player holding an artifact worth `+25%`, **when** the artifact is
lost, **then** the maximum SHALL return to the :Anchor: and any excess held mana
SHALL be clamped away rather than kept.

**Given** a player holding three dragons, **when** the :ConditionalUnlock:
condition is evaluated, **then** the unlocked creature SHALL become available,
and **when** one dragon dies, **then** it SHALL become unavailable again.

**Given** a dragon adjacent to a city WITHOUT mounted ballistae, **when** it
breathes fire, **then** the city SHALL lose population and the dragon SHALL take
no damage.

**Given** the same attack on a city WITH mounted ballistae, **when** it
resolves, **then** the dragon SHALL take damage.

**Given** a captured :Avatar: and a `major` :Wish: flipping a city, **when** the
target is a capital, **then** the wish SHALL be refused with a stated reason.

**Given** a `major` :Wish: aimed at a tile with no mountain in range, **when** it
is cast, **then** it SHALL be refused — the volcano has nowhere to come from.

**Given** a tile converted to `TERRAIN_VOLCANIC`, **when** it is worked, **then**
it SHALL yield MORE than the terrain it replaced, and **when** the eruption
timer fires, **then** the adjacent city SHALL lose population and tile
improvements.

**Given** a volcanic tile and a built ward, **when** the eruption fires, **then**
the loss SHALL be reduced rather than prevented — a hazard that can be fully
neutralised stops being a hazard and becomes free fertility.

**Given** a plague :Wish:, **when** it resolves, **then** it SHALL spread and
decay on its own schedule rather than resolving in one turn.

**Given** the map at game start, **when** :Site: :Precondition:s are evaluated,
**then** the set of sites SHALL be fixed for the game and SHALL NOT be
recomputed on any later turn.

**Given** a tile in open grassland far from any ruin, **when** sites are chosen,
**then** it SHALL NOT be one — a :Vessel: is earned by reaching somewhere hard.

**Given** any two players at turn 1, **when** their pools are compared, **then**
they SHALL be equal — every later difference :Attributable: to a named event.

***policy***

Per-mod, in `mod_policy.json` under `earned_powers`:

| key | meaning |
|---|---|
| `capacity_grants` | possession -> fraction of :Anchor: it adds |
| `conditional_unlocks` | visible condition -> what it opens |
| `wishes` | tier -> the enumerated effect list |
| `counters` | effect -> its :Counter: and the advance that reaches it |
| `hazards` | terrain it creates, its recurrence odds, and its yield change |

Feasibility is settled, not assumed. Corpus call sites: `Terraform` 6,
`TerrainType` 472, `TerrainDB` 491, `Plague` 16, `PlagueDamage` 24,
`GetCityByLocation` 195, `CutImprovements` 46, `HappinessHit` 156. MoM owns
`terrain.txt` with 26 entries, so `TERRAIN_VOLCANIC` is an addition rather than
an engine change.

***acceptance***

**Assertions** — these fail the build:

1. Every player's STARTING pool equals the :Anchor: (extends
   `gate_mana_upkeep.py` assertion 14, which must learn to read a declared
   baseline rather than the live maximum).
2. Every `capacity_grants` value is a fraction, not an absolute.
3. Every :Wish: appears in the enumerated list; no effect reachable outside it.
4. Every :TargetedEffect: has a `counters` entry.
5. Every :Counter:'s advance is at or below the advance that opens its threat.
6. No :TargetedEffect: names a capital as a legal target.

**Diagnostics** — reported, fail nothing:

7. Maximum total :EarnedCapacity: reachable by one player, as a multiple of the
   :Anchor: — the honest measure of how far this spec bends its own constant.

***rejected***

- **Varying the starting pool per tribe.** The defect
  [[fixed-anchor-scaling]] exists to prevent; unchanged by anything here.
- **Open-ended wishes.** Unspecifiable, ungateable, and unbalanceable.
- **Outright city destruction** — but for AGENCY, not magnitude. It ends the
  conversation instead of starting one. The nuke also already occupies that slot
  and is special-cased through the engine.
- **A hazard that a defence fully neutralises.** Then the wish is a gift of
  fertile land with a tax the victim pays once, and the threat evaporates.
- **Benchmarking magic against modern weapons.** The reference frame is the
  era's own imagination; a mountain opening is apocalyptic enough.
- **A :Counter: gated behind a later advance than its threat.** That is a delay
  dressed as counterplay.

***open***

- **Fortification is not readable.** `IsEntrenched` has zero corpus call sites.
  Whether to latch it from the entrench events or drop it from the catapult rule
  is undecided, and it is the only mechanic here whose state SLIC cannot
  currently see.
- **What a captured :Avatar: costs to hold.** Capture implies it can be lost
  again; nothing yet says whether it is a unit, a flag, or a building.
- **Whether :EarnedCapacity: should raise the pool at all**, versus raising
  income or lowering price by the same fraction. All three are expressible
  against the :Anchor:; only the first changes the constant the player has
  learned to trust.
- **Who owns the eruption timer.** A per-tile schedule needs state per volcanic
  tile. SLIC arrays are flat and fixed-size, so either the count of volcanic
  tiles is capped or the timer is derived from the turn number and tile
  coordinates — deriving it costs nothing and cannot leak, and is probably
  right, but it makes the hazard predictable to a player who works out the rule.
- **Whether a :PoisonedGift: can be cast on oneself.** It is coherent Chaos
  play and it is also an exploit surface if the yield outruns the risk.
- **Where the lost cities come from.** `TileHasDeadCity` (10 corpus sites) and
  `StoreDeadCityLocation` (4) exist, but a dead city is normally the ruin of a
  city destroyed IN PLAY, so at turn 1 there may be none. Two readings, and they
  are different games: designate sites from terrain alone at game start (available
  immediately, arbitrary), or let the ruins of cities that actually fell in THIS
  game become the sites (emergent, narratively excellent, unavailable early).
- **Sequencing.** Death does not summon and Chaos does not play. Both are open
  defects, and every power in this spec lands on top of the summon system they
  are failing to reach.
