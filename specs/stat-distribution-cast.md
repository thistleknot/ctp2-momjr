---
description: 'Cast numeric unit/entity stats between game mods by rank-transplanting the source distribution onto the destination''s own, stratified by tech age. Preserves rank order and the cross-axis copula by construction; reports four moments plus median/MAD as the acceptance contract. Generalises the civ2 -> CTP2 stat rescale beyond MoM.'
---

***definitions***

- :StatAxis: is one numeric column that both games express the same *concept* on
  but not necessarily the same *magnitude* — attack, defence, hitpoints,
  firepower, movement, cost. Each axis is cast SEPARATELY but not
  independently: because every entity keeps its own rank on every axis, the
  cross-axis :Copula: survives without being modelled.
- :SourceDistribution: is the multiset of values a :StatAxis: takes across the
  source mod's own entities, read from the control plane (`units.csv`), never
  hardcoded. Editing the control plane must reshape the scale, not silently
  disagree with it.
- :TargetDistribution: is the multiset the destination game's *stock* entities
  take on the corresponding axis. It is the evidence for what the destination
  engine has actually been exercised at.
- :ShapeSummary: is `(L-location, L-scale, L-skew, L-kurtosis)` — Hosking's
  L-moments, linear combinations of ORDER STATISTICS. It is **diagnostic
  reporting only**, never the contract. Conventional moments are not used: see
  the note under the mechanism requirement.
- :Copula: is the joint rank structure across axes — which entities are glass
  cannons, which are walls. Formally the dependence function once each margin is
  mapped to uniform by its own rank. It is what makes a unit *coherent*, and it
  is invisible to any per-axis check.
- :AgeStratum: is the tech age an entity's enabling advance belongs to. Stock
  CTP2 spans ten ages, so its global stat range is a TIME SERIES, not a power
  ladder — a warrior and a tank in one distribution. Targets are measured per
  stratum so like is compared with like.
- :RankPosition: is an entity's ordinal position within the
  :SourceDistribution:, ties shared. It encodes the original designer's intent
  about relative power and is the one thing a cast must never alter.
- :DegenerateAxis: is a :StatAxis: whose :SourceDistribution: has fewer than
  `min_distinct` distinct values. Moments are not meaningful on it.
- :SharedScaleAxis: is a :StatAxis: whose two games use the same semantic units,
  so a value means the same thing in both without rescaling.

***requirements***

**The cast SHALL preserve rank order.** For any two entities `a`, `b` on the same
axis, `source(a) < source(b)` implies `output(a) <= output(b)`. A cast that
reorders entities has overwritten the source designer's intent, which is the one
thing being transplanted.

**The cast SHALL preserve the :Copula:.** Spearman rank-correlation between
every pair of axes MUST agree between source and output within `copula_tolerance`.
This is the invariant that per-axis checks cannot see: margins can each be
perfect while the units they describe are incoherent.

> MEASURED on the 3.8.0 cast: max |difference| across all 16 axis pairs was
> **0.0140** (e.g. defence-hp 0.779 -> 0.788). Rank transplant preserves the
> copula BY CONSTRUCTION — each entity keeps its percentile on every axis, and
> the rank representation *is* the empirical copula. The residual is integer
> rounding and ties collapsing at the range bounds.

**The cast SHALL report its :ShapeSummary: per :AgeStratum:, as a DIAGNOSTIC.**
Compared like with like — a MoM unit gated on an age-3 advance against stock's
age-3 distribution, not against a global range spanning a warrior and a nuke. A
divergence is a prompt to look, not a failure.

> CONVENTIONAL MOMENTS ARE NOT A CONTRACT, and an earlier draft of this spec was
> wrong to make them one. `UNIT_NUKE` at attack 1000 is not measurement error —
> it is a real unit that is SUPPOSED to be off-scale. The question is not "remove
> the outlier" but "which statistic am I willing to let one unit control", and
> skew and kurtosis are exactly that statistic.
>
> MEASURED, n=46: excess kurtosis is **41.02** whether the outlier sits at 10x,
> 1000x, or 1,000,000x — identical to four significant figures. It saturates
> against an order-statistic ceiling of n-2 = 44. Stock CTP2's attack kurtosis of
> 38.16 is 87% of the maximum a sample that size can express, so it reports the
> SAMPLE SIZE, not the design. Matching it would be matching n.
>
> L-moments are used instead because they carry no fourth-power term for one
> entity to dominate: conventional skew swings 13.5x with and without the nuke,
> L-skew swings 4.5x and is bounded to [-1,1] by construction (Hosking 1990).

**The cast SHALL NOT exceed the target's observed range.** No output value may
fall outside `[min, max]` of the :TargetDistribution:. Beyond that range the
destination engine's combat maths and its AI's own unit evaluation are untested.

**The mechanism SHALL be quantile transplant, and that IS the contract.** Map
each entity's :RankPosition: to its percentile `p`, then take the
:TargetDistribution:'s value at percentile `p`, interpolated. Shape matches
exactly by construction, the map is monotone, and there is no estimator to break.
An off-scale entity simply lands in the top slot.

> This is the probability integral transform, and in one dimension "quantile
> mapping" and "copula mapping" are the SAME operation. Stating it directly is
> the point: "change the units, keep the design" is a rank statement, and
> approximating it through four summary numbers can only lose information.

**A :DegenerateAxis: SHALL NOT be moment-matched.** With fewer than
`min_distinct` source values there is no distribution to transplant; a percentile
map onto a wider target *invents* spread that the source never expressed. Two
cases:

- If the axis is a :SharedScaleAxis:, pass the value through **unchanged**. The
  source value already means the correct thing in the destination.
- Otherwise apply a plain affine map onto the target range and record the axis as
  degenerate in the run log, so the weakness is visible rather than implied.

**Outliers SHALL be detected robustly and DERIVED, never hardcoded.** The cutoff
is computed from the data by Tukey fence (`Q3 + 1.5*IQR`) cross-checked against
`median + 3 * 1.4826 * MAD`; the two SHOULD agree, and a divergence is itself a
signal that the distribution is odd. Outliers are excluded from the *measure* on
BOTH sides — source and target — and are still cast, landing at the top of the
range. Removing a row from the measure and removing it from the output are
different things.

> MEASURED on stock CTP2 attack: Tukey gives 129.4, MAD gives 129.0, and both
> flag exactly one unit — `UNIT_NUKE` at 1000. Excluding it moves the target from
> (mean 61.7, sdev 142.2, skew 6.22, kurt 38.16) to (40.9, 26.2, 0.46, -0.85).
> A hardcoded cutoff would have been a magic constant that silently rots as the
> control plane changes; these are two independent estimators agreeing.

***scenarios***

**Given** civ2 attack values `1..15` with median 5.5, **when** cast onto stock
CTP2 attack `10..100` with median 40, **then** a 1a entity outputs 10, a 15a
entity outputs 100, and the output median SHALL be within `moment_tolerance` of
40.

**Given** civ2 firepower `1..3` (3 distinct) and CTP2 firepower `1..6`, **when**
`min_distinct` is 5, **then** firepower is a :DegenerateAxis:; and **given**
firepower is declared a :SharedScaleAxis:, **then** values pass through unchanged
— `1f -> 1`, `2f -> 2`, `3f -> 3`.

> This scenario is why the rule exists. The 3.8.0 cast mapped `2f -> 5` on 16
> units, because a source median of 1 pushes anything above it past the median
> anchor. Firepower is damage-per-round in *both* games, so that was inventing
> 2.5x damage the source never specified.

**Given** an entity beyond the DERIVED outlier fence — `UNIT_NUKE` at attack
1000, or `Infernal Device` at 99a — **when** the axis is cast, **then** it SHALL
NOT contribute to the measured distribution on its side, and it SHALL still
receive an output at the top of the target range.

**Given** two axes with a source Spearman correlation of 0.779 (defence-hp),
**when** both are cast, **then** the output correlation SHALL remain within
`copula_tolerance` — measured 0.788, drift 0.009.

**Given** any axis after casting, **when** the roster is inspected, **then** the
axis SHALL have at least two distinct values. A single value means the column was
dropped, not balanced.

***policy***

Per-mod, in `mod_policy.json` under `unit_stat_scaling.stat_curve`:

| key | meaning |
|---|---|
| `outlier_method` | `tukey` or `mad`; the cutoff is DERIVED, never a literal |
| `min_distinct` | below this many distinct source values, the axis is degenerate |
| `moment_tolerance` | allowed relative deviation per reported moment |
| `copula_tolerance` | allowed Spearman drift per axis pair (0.02 measured) |
| `stratify_by` | the field defining an :AgeStratum:, or null for a global cast |
| `shared_scale_axes` | axes that pass through unchanged when degenerate |
| `<axis>` | target distribution, per stratum, as the destination game's own values |

***acceptance***

**Assertions** — these fail the build:

1. Rank order is preserved on every axis — assert pairwise for all entities.
2. :Copula: drift <= `copula_tolerance` across every axis pair, measured with
   **Spearman**, never Pearson.
3. No output exceeds the target's observed `[min, max]`.
4. No axis collapses to a single distinct value (`validate_scenario.py` gate 28).
5. The generator remains byte-stable across two consecutive runs.

**Diagnostics** — these are reported and looked at, and fail nothing:

6. :ShapeSummary: per axis per :AgeStratum:, source beside output beside target.
   A divergence is a prompt to investigate, not a build failure — the cast's
   correctness is defined by 1–3, which quantile transplant satisfies by
   construction. Reporting shape is how a BAD TARGET gets noticed (a stratum with
   two entities, an axis that is degenerate in one game and rich in the other),
   not how the cast is judged.

***rejected***

- **Matching conventional moments.** Skew and kurtosis saturate against an
  order-statistic bound at these sample sizes; see the measurement above. They
  describe n, not the design.
- **Box-Cox / Yeo-Johnson before matching.** Only relevant if moments are fitted
  parametrically. Rank transplant is distribution-free. The deeper catch: moments
  matched in transformed space do NOT stay matched after inverting.
- **Cornish-Fisher moment correction.** Not monotone for large |z|, so it can
  reorder exactly the top entities the transplant exists to place — breaking both
  rank order and the :Copula:.
- **ZCA / whitening.** Affine (`W = V L^-1/2 V^T`), so it touches variance and
  correlation ONLY; standardised third and fourth moments pass through unchanged
  and the off-scale entity is still far out the other side. Different problem.
- **NORTA / Iman-Conover.** The right tool for IMPOSING a target dependence
  structure. This cast wants the opposite — to PRESERVE the source's, which is
  what "keep the design" means, and which per-axis rank transplant already
  delivers (measured drift 0.014). Adopt NORTA only if the goal ever inverts to
  giving ported entities the destination game's correlation structure.

***cautions***

- **Assert the :Copula: on Spearman or Kendall, never Pearson.** Pearson is NOT
  preserved under a rank transform; rank correlations are. Asserting on Pearson
  would measure a number that changes the moment the marginals are remapped.

***open***

- **The target for an axis the destination never varies.** CTP2 ships `MaxHP` as
  a flat 10 on all 74 stock units, so there is no :TargetDistribution: to
  transplant onto. 3.8.0 chose `10/20/60` by preserving the *source's* ratios
  (civ2 `1h/2h/6h`) with the floor at the destination's universal value. That is
  a defensible convention, not a measurement, and it is the one number in the
  system with no empirical backing.
- Whether `cost` and `move` should be cast this way too. Cost is currently a
  linear `x100`, which is arguably correct for a currency; move is a small
  integer range where quantile transplant would be degenerate anyway.
