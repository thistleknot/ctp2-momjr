---
description: 'Rescale a source mod''s numeric entity stats onto a wider destination range. The mod is compared ONLY TO ITSELF — its own ordering and relative spacing are the design and are preserved; the destination game supplies range BOUNDS, never a shape to match. Generalises the civ2 MOMJR -> CTP2 stat rescale.'
---

***definitions***

- :StatAxis: is one numeric column both games express the same *concept* on but
  not the same *magnitude* — attack, defence, hitpoints, firepower, movement,
  cost. Each is cast separately but not independently: because every entity keeps
  its own rank on every axis, the cross-axis :Copula: survives without being
  modelled.
- :SourceDistribution: is the multiset of values a :StatAxis: takes across **the
  source mod's own entities**, read from the control plane (`units.csv`), never
  hardcoded. Editing the control plane must reshape the scale, not silently
  disagree with it.
- :RangeBound: is `[min, max]` for an axis in the destination game — the interval
  the destination engine has actually been exercised at. It is a **constraint**,
  not a distribution: only its endpoints are used, never its shape.
- :Copula: is the joint rank structure across axes — which entities are glass
  cannons, which are walls. It is what makes an entity *coherent*, and it is
  invisible to any per-axis check.
- :RankPosition: is an entity's ordinal position within the
  :SourceDistribution:, ties shared. It encodes the original designer's intent
  about relative power and is the one thing a cast must never alter.
- :DegenerateAxis: is a :StatAxis: whose :SourceDistribution: has fewer than
  `min_distinct` distinct values — too coarse for a percentile map to say
  anything a passthrough would not.
- :SharedScaleAxis: is a :StatAxis: whose two games use the same semantic units,
  so a value already means the correct thing in the destination.

***requirements***

**The mod SHALL be compared only to itself.** The cast rescales the
:SourceDistribution: onto a wider interval. The destination game's own entity
stats are NOT a target distribution and their shape is NOT matched — importing
them would overwrite the source designer's intent with the destination's, which
is the opposite of porting a mod.

> An earlier draft of this spec got this wrong: it transplanted MOMJR onto stock
> CTP2's distribution, which dragged in stock's age structure (ten tech eras in
> one distribution) and stock's outliers (`UNIT_NUKE` at attack 1000, pinning
> sample kurtosis at 87% of its order-statistic ceiling). None of that is MOMJR's
> design and none of it should reach the output.

**The cast SHALL preserve rank order.** For any two entities `a`, `b` on the same
axis, `source(a) < source(b)` implies `output(a) <= output(b)`. Reordering
entities overwrites the design being ported.

**The cast SHALL preserve the :Copula:.** Spearman rank-correlation between every
pair of axes MUST agree between source and output within `copula_tolerance`.
Margins can each be perfect while the entities they describe are incoherent, and
no per-axis check can see it.

> MEASURED on the 3.8.0 cast: max drift **0.0140** across all 16 axis pairs
> (defence-hp 0.779 -> 0.788). Preserved BY CONSTRUCTION — each entity keeps its
> percentile on every axis, and the rank representation *is* the empirical
> copula. Residual is integer rounding and ties at the bounds.

**Use Spearman or Kendall for that assertion, never Pearson.** Pearson is not
preserved under a rank transform; rank correlations are. Asserting on Pearson
measures a number that changes the moment the marginals are remapped.

**Output SHALL stay inside the :RangeBound:.** Beyond it the destination engine's
combat maths and its AI's unit evaluation are untested.

**Relative spacing SHALL be preserved, not just order.** The map is anchored on
the source's own min / median / max so an entity at the source median lands at
the target median. Rank alone would flatten a bottom-heavy distribution — civ2
attack has median 5.5 against a max of 15, and that skew is design, not noise.

**A :DegenerateAxis: SHALL NOT be rescaled.** With too few distinct source values
a percentile map *invents* spread the source never expressed. If the axis is also
a :SharedScaleAxis:, pass values through **unchanged**; otherwise apply a plain
affine map and record the axis as degenerate in the run log.

**Source outliers SHALL be excluded from the MEASURE and still cast.** The cutoff
is DERIVED from the source by Tukey fence (`Q3 + 1.5*IQR`) cross-checked against
`median + 3 * 1.4826 * MAD`, never a literal. One broken row must not stretch the
scale for every other entity — but removing it from the measure and removing it
from the output are different things; it still lands at the top.

**Interpolation within the range SHALL be justified, not merely computed.** The
endpoints and the curve between them are a design judgment informed by the
subject matter — what a dragon should be relative to a spearman, what the engine
can express, what the source's own ratios imply. Record the reasoning beside the
numbers. A number no one can defend is a magic constant regardless of how it was
produced.

***scenarios***

**Given** civ2 attack `1..15` and a CTP2 :RangeBound: of `10..100`, **when**
cast, **then** the lowest-ranked entity outputs 10, the highest outputs 100, and
an entity at the source median outputs the target median — because the percentile
map places it there, not because a tolerance was met.

**Given** civ2 firepower `1..3` (3 distinct) and CTP2 firepower `1..6`, **when**
`min_distinct` is 5, **then** firepower is a :DegenerateAxis:; and **given** it is
declared a :SharedScaleAxis:, **then** values pass through unchanged —
`1f -> 1`, `2f -> 2`, `3f -> 3`.

> This is why the rule exists. The 3.8.0 cast mapped `2f -> 5` on 16 units,
> because a source median of 1 pushes anything above it past the median anchor.
> Firepower is damage-per-round in *both* games, so that invented 2.5x damage
> MOMJR never specified.

**Given** `Infernal Device` at 99a where the next-highest source attack is 15a,
**when** the axis is cast, **then** it SHALL NOT contribute to the measured
:SourceDistribution:, and it SHALL still receive an output at the top of the
range.

**Given** two axes with a source Spearman correlation of 0.779 (defence-hp),
**when** both are cast, **then** the output correlation SHALL remain within
`copula_tolerance` — measured 0.788, drift 0.009.

**Given** any axis after casting, **when** the roster is inspected, **then** it
SHALL have at least two distinct values. One value means the column was dropped,
not balanced.

***policy***

Per-mod, in `mod_policy.json` under `unit_stat_scaling.stat_curve`:

| key | meaning |
|---|---|
| `outlier_method` | `tukey` or `mad`; the cutoff is DERIVED, never a literal |
| `min_distinct` | below this many distinct source values, the axis is degenerate |
| `copula_tolerance` | allowed Spearman drift per axis pair (0.02 measured) |
| `shared_scale_axes` | axes that pass through unchanged when degenerate |
| `<axis>` | `[min, median, max]` of the destination RANGE, with provenance |

***acceptance***

**Assertions** — these fail the build:

1. Rank order preserved on every axis, pairwise across all entities.
2. :Copula: drift <= `copula_tolerance`, measured with Spearman.
3. No output outside the :RangeBound:.
4. No axis collapses to a single distinct value (`validate_scenario.py` gate 28).
5. Generator byte-stable across two consecutive runs.

**Diagnostics** — reported, looked at, fail nothing:

6. Per-axis source-vs-output summary using **L-moments** (Hosking 1990), not
   conventional moments. L-moments are linear combinations of order statistics,
   so no fourth-power term lets one entity dominate: on this data conventional
   skew swings 13.5x with and without an outlier, L-skew 4.5x and is bounded to
   [-1,1]. Conventional skew and kurtosis saturate against an order-statistic
   ceiling at these sample sizes — measured excess kurtosis was 41.02 whether the
   outlier sat at 10x or 1,000,000x — so they report n, not shape.

***rejected***

- **Matching the destination's distribution.** Imports the destination's design
  over the source's. The mod is compared only to itself.
- **Matching conventional moments.** They saturate against an order-statistic
  bound at these sample sizes; they describe n, not the design.
- **Box-Cox / Yeo-Johnson.** Relevant only if moments are fitted parametrically.
  The cast is distribution-free, and moments matched in transformed space do not
  stay matched after inverting.
- **Cornish-Fisher.** Not monotone for large |z|, so it reorders exactly the top
  entities the cast exists to place — breaking rank order and the :Copula:.
- **ZCA / whitening.** Affine, so it touches variance and correlation only;
  standardised third and fourth moments pass through unchanged.
- **NORTA / Iman-Conover.** The tool for IMPOSING a target dependence structure.
  This cast preserves the source's, which per-axis rank transplant already
  delivers.

***open***

- **The HP range has no destination precedent.** CTP2 ships `MaxHP` flat at 10 on
  all 74 stock units, so there is no interval to read off. 3.8.0 chose `10/20/60`
  by preserving the source's own ratios (civ2 `1h/2h/6h`) with the floor at the
  destination's universal value. Defensible, and still the one number in the
  system with no empirical backing.
- Whether `cost` and `move` should be cast this way. Cost is a linear `x100`,
  arguably right for a currency; move is a small integer range where the axis
  would be degenerate anyway.
