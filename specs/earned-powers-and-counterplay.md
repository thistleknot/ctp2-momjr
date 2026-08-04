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
- :Attributable: describes a divergence between players that can be traced to a
  named in-game event, as opposed to a constant that differed from turn one.

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

**A :TargetedEffect: SHALL NOT destroy a city outright, and SHALL NOT target a
capital.**

> Annihilation is the CTP2 nuke, and the nuke is special-cased throughout the
> engine for good reason. Two bounded effects carry the same fantasy without the
> same swing: reduce population (`KillPop`, 38 call sites in the corpus) or flip
> allegiance (`GiveCity`, 8 sites). The allegiance flip is the more interesting
> of the two — it is the "mixed wish", it leaves the city standing, and it can
> be answered by retaking it.

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
- **Outright city destruction.** The nuke already occupies that slot and is
  special-cased; population loss and allegiance flip carry the fantasy at a
  fraction of the swing.
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
- **Sequencing.** Death does not summon and Chaos does not play. Both are open
  defects, and every power in this spec lands on top of the summon system they
  are failing to reach.
