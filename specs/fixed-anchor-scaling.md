---
description: 'Hold exactly ONE value constant in a closed numeric subsystem and express every other number relative to it. The anchor is not a balance decision — it is the unit of account that makes the remaining numbers identifiable, comparable, and legible to the player. Generalises the fixed 200 mana pool.'
---

***definitions***

- :Subsystem: is a set of numbers that only trade against each other — a pool,
  what fills it, what drains it, and what it may be spent on. Mana is one.
  Gold and science are separate ones. Two numbers belong to the same
  :Subsystem: only if changing one can be compensated by changing the other.
- :Anchor: is the single value inside a :Subsystem: held constant across every
  actor and every configuration. It is the denominator the rest are read
  against, not a tuned quantity.
- :DerivedValue: is any other number in the :Subsystem:, expressed as a ratio
  of the :Anchor: rather than as a free absolute.
- :Peer: is one actor drawing on the same :Subsystem: under the same rules —
  the five tribes here.
- :Dial: is a per-:Peer: deviation that expresses identity: a price percentage,
  a generation multiplier, an upkeep rate.
- :Headroom: is the fraction of the :Anchor: the dearest :DerivedValue: is
  permitted to reach, leaving the rest as working capital.
- :Denomination: is a deliberate change to the :Anchor: itself, which rescales
  every :DerivedValue: by the same factor and changes nothing about play.

***requirements***

**A :Subsystem: SHALL have EXACTLY ONE :Anchor:.** Not zero, not two.

> Zero is the defect this spec exists to prevent. If the pool may vary AND the
> prices may vary, then `(pool x k, prices x k)` is *the same game* — the
> parameter space has a degenerate direction along which nothing observable
> changes. That is a free parameter that cannot be measured, cannot be tuned,
> and silently makes two runs incomparable. It is the dummy-variable trap: with
> an intercept and every level present, the design matrix is rank-deficient and
> you must drop one level as the reference. **The :Anchor: is that reference
> level.** The operator's framing — fix the intercept, solve for the
> coefficients; fix `mmr_k` before permutation-testing the rest — is the same
> move, and it is about identifiability before it is about balance.

> Two is over-constraint. Fixing the pool *and* the dearest price determines the
> whole curve between them, leaving no room for the :Dial:s that carry identity.

**The :Anchor: SHALL be identical across every :Peer:.** A per-:Peer: anchor
reintroduces the degeneracy once per peer, and worse, makes the SMALLEST anchor
dictate the ceiling for everyone.

**The :Anchor: SHALL be a CAPACITY in arbitrary units, not a rate or a price.**
A capacity is read constantly, bounds everything else, and has no external
referent to contradict. A rate compounds with time and a price is already a
ratio.

**A quantity coupled to machinery outside the :Subsystem: SHALL NOT be the
:Anchor:.** Its units are not free.

> This is why hitpoints are cast and not pinned. HP feeds the engine's combat
> maths alongside attack, defence and firepower, so its scale is answerable to
> something outside itself. It gets the rank cast of
> [[stat-distribution-cast]]. Mana answers to nothing but mana.

**Every :DerivedValue: SHALL be stated as a ratio of the :Anchor:.** A cost
written as an absolute is a claim no one can check; the same cost written as a
percentage is immediately auditable against the one fixed number.

**Every :Peer: SHALL be able to afford its own most expensive :DerivedValue:
within the :Anchor:.** A price a peer can never reach is a feature deleted for
that peer, silently.

**A :Dial: SHALL NOT co-vary with another :Dial: in the same direction.**
Independent dials are additive; correlated ones are multiplicative and compound
into a dominant peer.

> MEASURED: pool capacity varied 200/220/260/240/300 while the generation
> multiplier varied 100/110/125/115/140 — the same ordering. Chaos held 50% more
> mana AND earned 40% faster. Neither number looked wrong alone.

**When a :DerivedValue: will not fit under the :Anchor:, the MAP is wrong — not
the :Anchor:.** Widen the map's compression, never the anchor.

> MEASURED: creature shield costs span 150..4000 (26.7x). A usable price band
> under a 200 pool spans ~20..180 (9x). No linear divisor exists — `/9` puts the
> dearest creature at 222% of the pool, `/22` drops the cheapest to 6. The
> resolution is a compressive cast, exactly as for stats.

**:Denomination: SHALL be recognised as a no-op.** Doubling the :Anchor: and
every :DerivedValue: changes no decision. Treat a proposal to move the anchor
"for balance" as a category error and look for the real :Dial:.

***scenarios***

**Given** a fixed :Anchor: of 200 and a dearest cost of 179, **when** a player
reads the panel, **then** they SHALL be able to price any decision against a
number they already know, without arithmetic.

**Given** two :Peer:s whose only difference is a price :Dial: of 54% and 92%,
**when** both are measured over a run, **then** any divergence in outcome SHALL
be attributable to that one dial.

**Given** a proposal to raise one :Peer:'s pool to 260, **when** it is
evaluated, **then** it SHALL be rejected as re-denominating that peer's whole
subsystem, and re-expressed as a change to a :Dial:.

**Given** a new :DerivedValue: costing more than :Headroom: of the :Anchor:,
**when** it is added, **then** the cast SHALL be recompressed rather than the
:Anchor: raised.

***policy***

Per-subsystem, in `mod_policy.json`:

| key | meaning |
|---|---|
| `anchor` | the one fixed capacity, with the reason it was chosen |
| `headroom` | fraction of `anchor` the dearest derived value may reach |
| `dials` | the per-peer deviations, each with its derivation |

Current mana subsystem: `anchor` 200, `headroom` 0.90, dials = price percentage
(derived from roster cost at equal rung) and generation multiplier.

***acceptance***

**Assertions** — these fail the build:

1. Exactly one :Anchor: per :Subsystem:, and its value is identical for every
   :Peer:.
2. No :DerivedValue: exceeds `anchor * headroom`.
3. Every :Peer: can afford its own maximum :DerivedValue:.
4. No two :Dial:s rank the :Peer:s in the same order (the co-variance test).
5. Every :DerivedValue: derives from the :Anchor: at EVERY site that computes
   it — a partial edit that leaves one site absolute is the defect this catches
   (`gate_mana_upkeep.py` assertion 13).

**Diagnostics** — reported, fail nothing:

6. Each :DerivedValue: as a percentage of the :Anchor:, min and max, so the
   band is visible at a glance.

***rejected***

- **Per-peer anchors.** Reintroduce the unidentifiable direction per peer, and
  hand the ceiling to the weakest.
- **Pinning two values.** Over-constrains; the curve between them is then forced
  and the dials have nowhere to act.
- **Pinning a rate.** Rates compound with time, so a fixed rate does not bound
  anything and cannot serve as a denominator.
- **Raising the :Anchor: to fit an expensive item.** :Denomination:, not
  balance — it changes every number and no decision.

***open***

- **Upkeep is still an absolute** (`rung * MomUpkeepRate`), not a fraction of
  the :Anchor:. It is the one :DerivedValue: not yet expressed in the anchor's
  terms, and it should be — a creature's keep is more legible as "1% of pool per
  turn" than as "2".
- **`headroom` 0.90 is a judgment, not a derivation.** It is defensible (the
  dearest purchase should be a real commitment without being the whole bank) but
  no measurement produced it.
- **Whether gold and science are one :Subsystem: or two.** They trade against
  each other through the tax rate, which by this spec's own test would make them
  one — with one anchor between them, not two.
