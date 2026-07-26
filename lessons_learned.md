## 2026-07-26 — SLIC is a control-plane dimension, and it flows BACKWARD

The control plane is `mom_dimension_inventory.xlsx`: one tab per dimension, and
a cell is a file and/or a set of constants/classes/functions — the content
itself, not a manifest describing it. I first built the SLIC dimension as a flat
CSV of signatures and was corrected; a manifest of names is a table of contents,
not a control plane, because nothing downstream can be rebuilt from it.

Every other dimension is forward-generated (Civ2 RULES.TXT -> xlsx -> scenario).
SLIC is the exception and has to be: Civ2 has no equivalent, so there is nothing
upstream to encode from. `tools/backcast_slic.py` runs the other way,
scenario `*.slc` -> xlsx, and never writes SLIC. A spreadsheet that could
regenerate SLIC would be strictly worse than text that is diffable and
compilable.

The tab that existed before was hand-maintained and had rotted exactly the way
hand-maintained inventories do: 17 declarations, `mom_magic.slc` marked PLANNED
although it ships and was verified in-game, `mom_spells.slc` missing entirely,
and no tool in `tools/` read it. Derived instead: 8 modules, 48 declarations,
57,196 bytes. Include order is parsed from `scenario.slc`'s `#include` list
rather than hardcoded, so adding a module cannot silently mis-order the tab.

**The split that makes it survivable.** Structure is re-derived every run;
prose (`purpose`, `status`) merges forward by name via
`tools/momjr_csv/slic_purpose.json`. A declaration added in code appears with an
empty `purpose` — a visible TODO — and curated intent is never clobbered. One
carve-out: a stale `PLANNED` never survives over code that demonstrably exists,
which is the specific failure the old tab shipped with.

**Harness lesson: openpyxl round-trips an empty string as `None`.** `--check`
reported STALE immediately after a successful write because
`existing != [HEADER] + rows` compared `None` against `""`. Any table drift gate
must normalise BOTH sides. Verified in both directions afterwards: clean -> exit
0; inject a `MomDriftProbe` handler -> STALE at 49 declarations, exit 1; revert
-> exit 0. A gate only tested on the passing case is not a gate.

## 2026-07-26 (second pass) — matching the WRONG STATISTIC looks like confirmation

The entry below closed the horizontal complaint on the evidence
`hot_x - bbox_cx ~= 0` for stock AND ours. That comparison was true, and
irrelevant. The user came back the same day: *"made the units a little too
small, and they are all still offset to the right a little bit"* — two real
defects the first pass created or missed.

**The horizontal one: bbox centre is not mass centre.** They coincide only for
art symmetric inside its box. MoM units carry a spear one way and a banner the
other, so the box grows on BOTH sides while the visual mass stays off to one.
Re-measured against the pixel-mass centroid instead:

| | stock (n=95) | ours, first pass |
|---|---|---|
| `hot_x - mass centroid` | **+0.5** med (−7.7..+15.3) | **−4.6** med |

Mass ~5px right of the anchor is exactly what renders as "offset to the right".
`_content_anchor` now computes `hot_x` from the **alpha-weighted centroid**
(alpha-weighted, not a binary opaque test, so a feathered edge does not count as
much as solid body). Post-fix across all 59: med **+0.2**, range −0.9..+4.1 —
tighter than stock's own spread.

**The size one: I treated a median as a law.** `STOCK_CONTENT_H` was pinned to
the stock *median* 55, but stock's shipped spread is 23..70 (p75 59, mean 52.9),
and we had been at 68-70 with nobody complaining about size. 55 is the centre of
a wide distribution, not a constraint. Raised to **62** (~p85): visibly larger,
still inside the shipped envelope, still under where no complaint existed.

**THE LESSON.** A statistic that matches is not evidence unless it is the
statistic that governs the symptom. `hot_x - bbox_cx` agreeing with stock felt
like confirmation and *foreclosed the correct line of attack* for a full round
trip. Before trusting an agreement, ask what the number would have to be for the
user's complaint to be true — if the complaint could be true with the number
unchanged, the number is not the instrument.

**Verified.** Windowed on the engine's own selection ring in
`runs/20260726-084023/03_peasant_on_open_map.png`: ring bbox `x[503,550]
y[372,419]` — 47x47, one tile, so the filter isolated the ring and not the
grid — unit mass centre `(525.9, 399.7)` vs ring centre `(526.5, 395.5)`:
**dx = −0.6px**. Closed.

**Harness note, same failure mode as before.** The FIRST attempt at that
measurement ran the green-density filter over the whole map and returned a
"ring" bbox of 313x368 px with `dx=+4.6`. Both numbers were artifacts: the
filter kept dotted-grid clusters, and the terrain-distance mask sampled green
grass while the unit stands on yellow-brown desert, so nearly every pixel read
as "far". Constraining the window to the unit's neighbourhood fixed it. Colour
segmentation at frame level is ALSO not usable for measuring unit SIZE — the
largest-blob heuristic grabbed a mountain above the ring. Size verdicts come
from decoding the SPR, which is objective; the frame instrument is for tile
anchoring only.

---

## 2026-07-26 — units drew off-centre: extent and anchor are ONE coupled bug

**Symptom.** User, twice: first "too far lower left", then after a fix "a little
too far to the right, and a little to the top". Two complaints that read like two
bugs. They are one: we were normalizing the art without normalizing the anchor
the engine draws it around.

**Measured, not assumed.** Decoded the MOVE frame of all 95 shipped `GU0*.SPR`
(shadow runs excluded from the bbox — the shadow is the ground blob and drags the
measured bottom down). Vanilla's envelope:

| | stock (n=95) | ours BEFORE | ours AFTER |
|---|---|---|---|
| content width | 31-32 | 56 / 70 | 44 / 55 |
| content height | 55 | 68 / 70 | **55** |
| content top | 9-10 | 1 | **10** |
| content bottom | 64 | 68 / 70 | **64** |
| **bottom - hot_y** | **12** | **0** | **12** |
| hot_x - content_cx | ~0 | ~0 | ~0 |

**Root cause.** `resize((96,72))` stretched each source TGA edge-to-edge, so MoM
units came out 1.75-2.2x wider and ~1.25x taller than the art the engine was
directed around — that overhanging mass is the "too far right". And
`_content_anchor` anchored at the literal content bottom (`bottom - hot_y == 0`)
where vanilla sits at 12, so `draw_pos = tile_anchor - hotpoint` put every unit
~12px too high — the "a little to the top".

**The law.** *Extent and anchor are coupled.* The 2026-07-25 attempt bound
`_fit_content` to 0.80/0.97 without touching the anchor; shrinking the art walked
the unit off its draw anchor and the change was reverted the same day. Fixing
either alone reintroduces the other's symptom. `_normalize_to_stock_extent()` and
`_content_anchor()` must be changed together.

**Width is deliberately NOT forced to stock.** Scaling is height-governed with a
width guard; MoM's source drawings genuinely are wider, and squashing them to 32
would distort every unit to fix a statistic nobody sees.

**Verified in-game, headless** (`steps/verify_unit_centering.json`, run
`20260726-081900`): founded Eudoria with the starting peasant, queued Spearmen
from `UnitsList` index 0, nine pinged end-turns to 3775BC, Spearmen built and on
the map. Read the verdict off the engine-drawn selection ring — the only
ground truth for the tile anchor there is — bbox `x[598,647] y[418,468]`, centre
`(622.5, 443.0)`: sprite mass on the centre, head below the ring top, feet above
the ring bottom, no overhang past any arrow.

**Two harness bugs fixed to get that frame at all.**
1. `uiwalk.py`'s `VK` table had no arrow keys (`KeyError: 'right'`). CTP2 repaints
   damaged regions only, so a freshly loaded map is BLACK under intact chrome
   until something forces a redraw; arrow-scroll is the cheapest trigger. Without
   arrows a map frame is literally uncapturable.
2. Four post-`enter` frames came back byte-identical — the turn never advanced.
   That is `ctp2-endturn-needs-mouse-input` again: post a click at inert chrome
   (600,6) BEFORE the key. Order matters; the key advances, the ping makes it count.

**Falsified along the way, kept on purpose.** Thesis "the unit is offset
horizontally by a wrong `hot_x`" — dead. `hot_x - cx ~= 0` for stock AND ours
(exactly frame-centre for `GU92`). The horizontal complaint was width, not anchor.
Also: colour segmentation of a lone unit on grass FAILED (masks ate the mountain
and the unit's own orange body, returning the whole crop as the bbox). The
engine's own selection ring is the instrument; invented colour thresholds are not.

**Same root-cause family as the 54-icon over-zoom** (fit-to-fill normalization).
`_normalize_to_stock_extent` is the template for that fix — measure the stock
envelope, scale to it, correct the anchor in the same change.

## 2026-07-26 — every building was a 1-turn build: the rescale ran 1300 lines before the ingest

**Symptom.** Build Manager showed Barracks / Merchant's Guild / Coastal Fortress
all at `1` turn. Shipped `buildings.txt` carried `ProductionCost 4..24` — raw
Civ2 numbers — against a CTP2 first-age band of 270..875.

**It was NOT a missing control plane.** The age-scaling layer already existed
and its docstring names this exact symptom: "Raw Civ2 costs (4..60) render as
1-turn builds in CTP2". `_retune_mom_improvement_costs()` was being called. It
just ran at `main():2863` while `_merge_mom_improvements_into_buildings()` —
which writes raw CSV costs straight into the file — runs at `main():4156`. The
rescale was clobbered by the ingest every single run. Wonders and units were
never affected: their retunes run *after* their own ingestion.

**Discriminating evidence.** A full regen reproduced the raw costs exactly, and
a standalone call to the retune against the same on-disk file rescaled all 21
blocks correctly. Same function, same input, opposite outcome — that gap is only
explainable by ordering, and it pointed straight at the call site.

**Second bug, same class, found while verifying the first.** The ingest resolves
each building's gating advance against a set read from DISK
(`_read_rel("default/gamedata/Advance.txt")`), but the live tree is still in the
registry and is not flushed until `save_all()` — after the ingest. So the guard
`if adv not in advances` was testing against the *previous run's* advance file.
Fixed by reading `reg.load(...)` instead.

**Third, in the same code path: the two lanes of `advance_code_map.csv` are not
interchangeable.** Buildings were resolved through `MOM_UNIT_ADVANCE`, which is
filtered to `lane == "unit"`, so prereq-only codes fell to the fallback advance
— Merchant's Guild's `Eco` among them. But merging the prereq lane *over* the
unit lane is also wrong: 5 prereq-lane targets are dangling
(`ADVANCE_COMMUNE_WITH_GODS` was never generated), and a blind override demoted
Cathedral from the live `ADVANCE_THEOLOGY` to the fallback. Correct shape is a
resolution CHAIN — prereq lane, then unit lane, then fallback — where a
candidate is usable only if it exists AND is not disabled by self-prerequisite
(CTP2's sanctioned "unresearchable" form, applied to 169 base advances here).

**The law.** A silent fallback is how all three of these survived. The fallback
itself was correct behaviour; the silence was the defect. The generator now
prints `! prereq code 'X' for 'Y' is dangling or disabled` for every one, and
there is currently exactly one (`Eco`, because `ADVANCE_ECONOMICS` is a disabled
stub in MoM's replaced tech tree).

**Generalisation worth carrying.** When a transform's output looks untransformed,
check WHERE it runs before checking WHETHER it runs. Both bugs here were a
correct function reading correct data at the wrong point in the pipeline, and
neither would ever surface as an error.

## 2026-07-26 -- spearman-on-map closed: TWO shipped filename conventions, and my search could never have seen the second

**Root cause.** `ctp2.exe` carries BOTH format strings `GU%.2d.SPR` and
`GU%.3d.SPR`, and stock CTP2 ships sprites under both conventions (124
zero-padded, 83 unpadded, all mtime 2000-11-01). `build_sprites.py` wrote only
the unpadded name. Where a base zero-padded twin existed, the engine resolved
that first and served **stock art for a MoM unit**. `SPRITE_SPEARMEN 92`: MoM
wrote `GU92.SPR` (19,190 B) while base `GU092.SPR` (562,756 B) sat next to it
and won. Same for `SPRITE_ZOMBIES 91` and `SPRITE_SWORDSMEN 93`.

**Fix.** `_dest_names(num)` returns `{GU{n:02d}.SPR, GU{n:03d}.SPR}` and the
builder writes both. Verified deterministically: all 59 MoM-owned sprite ids
(91-149) are now byte-identical twins, so there is no filename the engine can
resolve that holds base art. Ids 2-90 remain divergent -- that is stock CTP2's
own shipped state, untouched by MoM.

**Method lesson (the expensive part).** I "verified the sprite chain clean"
three times and closed it as DO-NOT-RE-INVESTIGATE. The verification was
`find -iname 'GU92.SPR'`. That search **structurally cannot see `GU092.SPR`**.
The bug lived in the exact blind spot of the instrument I used to declare the
absence of a bug. A negative result is only as strong as the search's ability
to have returned a positive -- before concluding "not present", state what the
query would have missed. Note also that the padding is `%.2d`, i.e. a MINIMUM
of two digits: for n<10 the pair is `GU03`/`GU003`, never `GU3`. My first audit
script used `GU%d` and reported 58 phantom divergences.

## 2026-07-26 -- identical frames across a whole run: a modal dialog, and my own default argument

**Symptom.** Every one of 14 captures in a run was byte-identical, all showing
the startup "Loading..." frame. Read as "the game hung" or "our capture is
stale".

**Root cause.** A native `'Load save game Error'` dialog (window class `#32770`)
raised ~3s after launch blocked the engine's message pump, so it stopped
presenting and PrintWindow kept returning the last painted bitmap. It appeared
because `uiwalk.py --save` **defaults to `uiwalk_start`** -- a save the engine
cannot load -- and a menu-entry walk must be run with `--save none`. Our own
headless stash also parked the dialog off-screen, so it was invisible to anyone
watching. Line 710 of uiwalk.py already documented this exact trap from a
previous incident.

**Found by** enumerating every top-level window owned by the game PID and
printing on change -- not by reasoning about coordinates. Two coordinate-level
theories were proposed and falsified first (the `-32000,-32000` minimize
sentinel; `__COMPAT_LAYER=HighDpiAware`).

**Fix.** `Game._assert_no_blocking_modal()` runs on every `get_hwnd()` and
raises naming the dialog, so a blocked pump can never again masquerade as a
hung game or a stale capture.

## 2026-07-26 -- the "1.25 ratio" was never engine behaviour: it was OUR DPI awareness

**Root cause.** `uiwalk.py` called `ctypes.windll.user32.SetProcessDPIAware()`
while `ctp2.exe` ships no DPI manifest. On a 125%-scaled primary that puts the
harness and the game in **different coordinate spaces**: `GetClientRect`
returned PHYSICAL pixels (1280x960) for a client the game believed was logical
(1024x768). Ratio: exactly 1.25.

Everything built on top of that was an artifact. The "empirical per-surface
send scales" (message x0.80 = 1/1.25, alertbox x1.25) were the same mismatch
observed from two directions and mistaken for engine behaviour. **With uiwalk
DPI-unaware, send == capture, 1:1, on every surface.**

**Fix.** Deleted the awareness call. Captures returned to 1024x768 and all four
goldens went from 0/4 (0.144 / 0.075 / 0.193 / 0.454) to **4/4 at 1.000**.

**Method lesson.** I had claimed the goldens were "stale, captured at 1024x1280
under a portrait primary". They were always correct; the instrument was broken.
A perfect 1.000 is the proof. This is the third time in this project I blamed
the environment (display, monitor rotation, how something was authored) before
checking the instrument I control -- see `feedback-instrument-before-environment`.
Order of suspicion: my own argv, then the comparator, then the artifact, and
the environment LAST.

**Separate finding, still open by design:** a posted `click` in-game is
process-lethal (0xC0000005), reproducibly, ~5 runs. Falsified as causes: the
rebuilt sprites (control run with base art restored still AV'd) and the
coordinate (corrected under the new 1:1 rule, still AV'd). The click itself is
the trigger. It is also unnecessary -- `verify_centering.json` now waits instead
and completes all 14 shots at 4/4. Use the `press:`/`select:` injection hook,
which posts no mouse input, if a control ever genuinely needs pressing.

## 2026-07-26 -- icon over-zoom closed: the extractor was the THIRD producer of the same TGA

**Root cause.** `ICON_UNIT_*.tga` is written by three tools:
`civ2_sprite_extractor.py` (extraction), `build_unit_icon_art.py` (icon
builder), and `reframe_unit_icons.py` (one-shot repair). Two of them capped
content at `ICON_CONTENT_MAX_FRAC = 0.80`. The extractor did not -- its
`_scale_rgba_to_canvas` was unconditional fit-to-fill, so **every regen
silently un-repaired the shipped icons**, re-inflating figures until they
overran the 96x72 unit-preview box and protruding weapons were severed by the
frame. That is why the 2026-07-25 repair kept "coming back."

**Fix.** `_scale_rgba_to_canvas` now takes `max_frac` / `floor_margin`. The
sprite call sites keep the fit-to-fill default (their consumer
`build_sprites.py` does its own 96x72 fit and wants the largest clean source);
the icon call site passes the 0.80 cap and a 6px floor margin. The constants
live at module scope with a comment naming the other two producers.

**Two things the measurement caught that reading would not have:**

1. **`int()` -> `round()` is not a cosmetic cleanup.** I "tidied" the shared
   scale math while rewriting, and 33 `SPRITE_*.tga` moved by a pixel. The
   byte-identical sprite gate caught it immediately. Reverted to `int()`;
   sprites back to **0 changed**.
2. **Never-upscale is correct for the repair tool and WRONG for the
   extractor.** `reframe_unit_icons` clamps scale at 1.0 because it reframes an
   already-160x120 icon. The extractor's input is a native atlas cell ~40px
   tall, so the same clamp left every figure at **0.28** of the frame --
   measured, not reasoned. Dropped the clamp on the extractor path only, and
   documented the divergence in the docstring so it does not get "fixed" back.

**Gate (post-fix, 62 icons):** height extent median 0.77 / max **0.78**, width
median 0.55, over-cap **0**, edge-clipped **0**, and all 62 `SPRITE_*.tga`
byte-identical. Rendered repaired-vs-regenerated side by side at preview size:
same subject in every column, nothing touching the frame. The pipeline is now
idempotent -- `reframe_unit_icons` run against the new output is a no-op,
because content already sits at or under the cap.

**Method lesson.** When a repair keeps regressing, stop repairing and count the
**producers** of the artifact. Two agreeing tools and one disagreeing tool
looks exactly like a flaky fix. See [[ctp2-icon-overzoom-uniformity-tell]].

---

## 2026-07-26 -- the sprite cell_index disagreement was NOT latent; I had misread the extractor

**What I told the user:** the `units.csv` duplicate `cell_index` 1 was harmless
"because the extractor ignores that column and uses row position." **That was
false**, and the user's reply -- *"fix whatever produces this then"* -- is what
made me go read the producer instead of trusting my own summary.

`read_csv_identifiers()` resolves the sheet position as
`art_cell_index` -> else `cell_index` -> else the sequential row index.
`units.csv` had **no `art_cell_index` column**, so `cell_index` was live. That
column is the generator's cost/order weight: non-monotonic, skips values, and
carries a duplicate (Zombies and Spearmen both 1). On the detected 9x7 grid it
sends Spearmen to cell (0,1) -- the Zombies figure -- and Swordsmen to (0,2) --
the gold spearman. The next `civ2_sprite_extractor.py` run would have shifted
every sprite after Zombies by one, and would have manufactured the exact
"wrong unit on the map" defect the user had already reported twice.

**Measured before editing.** Rendered `Units.bmp` row-0 cells 0..3 against the
on-disk `SPRITE_ZOMBIES/SPEARMEN/SWORDSMEN.tga`: the TGAs match cells 1, 2, 3 --
**row order**, not `cell_index`. So the shipped art predates this CSV state and
was always correct; the "samurai IS the spearman" verdict stands. The defect was
armed, not yet fired.

**Fix:** added an explicit `art_cell_index` column (0..62) to `units.csv`,
which is exactly what that column exists for, and rewrote the
`extract_units_sprites()` docstring -- it had asserted `cell_index` "equals the
sheet's row-major cell order", which is the false claim that let this sit --
to forbid the `cell_index` fallback by name.

**Gate:** full regen after the fix is **byte-identical across all 62
`SPRITE_*.tga`**. 54 `ICON_UNIT_*.tga` bytes did move, and the control says that
is not mine: Zombies resolves to index 1 under *both* columns and its icon
changed anyway, so those diffs are the known pre-existing fit-to-fill over-zoom
drift. Reverted them; the commit is two source files.

**Method:** a byte-identical regen is the right gate for a "did I change the
mapping or just the bookkeeping" question -- it answers both halves at once. And
when a summary of mine gets quoted back, re-derive it from the code rather than
from the summary; this one had survived a whole eight-hypothesis investigation
unchecked.

## 2026-07-26 -- 75-mana summon VERIFIED both ways; and the "blocked on your display" claim was mine to fix

**Both arms of the pricing gate are now measured, headless, on live frames:**

| Premise | Verdict | Discriminating evidence |
|---|---|---|
| An affordable summon (pool at cap) spends and still spawns | **YES** | 16/16 turns, 0 SLIC errors, click at turn 12 -> readout turn 14 reads *"Your working completes. A Guardian Spirit manifests in your capital."* |
| An unaffordable summon is refused with a real reason | **YES** | 6/6 turns, 0 SLIC errors, click at turn 2 -> *"You lack the mana for a summoning. A creature costs 75, and you hold 44."* -- the **44 is live interpolation of `MomMagicCurDisp`**, so the gate is reading the actual pool, not a constant. |
| A refused summon silently places the order anyway | **NO** | `msg_box=None` at the +2 readout on the unaffordable run vs. a populated box on the affordable one. No spawn, no order left latched. |
| The pool still self-discharges at cap | **NO** | mana reached 75+ by turn 12 and was spendable -- under the old M3 auto-summon it would have zeroed itself at 100 every time. |

**The method failure worth keeping.** I closed the previous segment saying the
verification was *"blocked on a landscape primary display -- I won't change your
display."* That was wrong, and it is the exact shape
[[feedback-instrument-before-environment]] describes: an environment story about
the USER'S hardware standing in for a one-line check of MY OWN instrument. The
preflight aborted because `userprofile.txt` said `1024x768`, and my own memory
already recorded that **`1024x1280` is the geometry proven to boot and advance
turns on this portrait primary**. The fix was editing one line of a config file I
control, running the test, and putting the line back. Nothing about the user's
desktop was ever involved.

**Escalating a blocker onto the user is itself the tell.** Second time in two
days (the first was *"the only untried lever needs an exe rebuild, which is
yours to run"* -- `--summon-arm` was already in my own argparse). Before saying
"blocked on you", the question is: **is there a file I own that would unblock
this?** Ask it every single time.

Harness note: runs on a portrait primary need `ScreenResHeight=1280` in
`ctp2_program/ctp/userprofile.txt`, restored to `768` afterwards. That flip is
part of the run, not a change to the user's setup.

---
## 2026-07-26 -- "Samurai on the map, Spearmen in the UI": nothing was broken, the art is authentic

**User report (twice):** *"still seeing samurai on the map when spearman is in the
ui"*. Earlier phrasings: *"the carpet (spearman) doesn't match the drapes (on map
icon)"*, *"peasant is still showing up as a samurai"*.

**Verdict: the samurai IS the spearman.** Every link in the chain measured clean.
MoM's own Spearmen art is a gold lamellar warrior in a crested/horned helm holding
a long spear -- it reads as a samurai because that is how the source game drew it.
The UI portrait and the map sprite are the SAME picture, so there is no UI/map
mismatch to fix; what the user is reacting to is the art's style, not a defect.

I walked this backward link by link instead of guessing, and every hypothesis I
formed died to a measurement. That is the value of the entry -- the negative
results are the content.

| Premise | Verdict | Discriminating evidence |
|---|---|---|
| `GU92.SPR` is stale, or is stock CTP2 art adopted by the base/MoM id collision | **NO** | temp rebuild from `SPRITE_SPEARMEN.tga` is **byte-identical** to the file on disk: 19190 B, md5 `9d5bb9d3fbac7f346d252ba93d1ae33b`, both sides. |
| A `.zfs` archive or a second `GU92.SPR` shadows the loose file | **NO** | no sprite `.zfs` exists anywhere under `ctp2_data/**/graphics/`; `find -name GU92.SPR` returns exactly one path. |
| `SPRITE_SPEARMEN.tga` is a placeholder duplicated from another unit | **NO** | all **62** `SPRITE_*.tga` md5s are distinct. `SPRITE_SWORDSMEN.tga` shares byte size and mtime but hashes differently. |
| The UI icon and the map sprite come from different art | **NO** | rendered side by side: same gold lamellar figure, spear and round shield. The icon is a reframe of the same subject. |
| The spear is lost at 96x72 map scale, so the figure reads samurai | **NO** | rendered the keyed frame at 96x72 -- the spear is clearly visible. Killed my own hypothesis before it became a story. |
| `newsprite.txt` has a numbering defect that misresolves the sprite | **NO** | the two "duplicates" are benign: **90** is the shared city sprite (`SPRITE_CITY` / `OCEAN_CITY` / `SPACE_CITY`, base convention), and `SPRITE_SWORDSMAN` at 6 and 84 is a base-vs-MoM name collision on a unit that is not involved. `SPRITE_SPEARMEN 92` is unique; base has no entry at 92. |
| The sprite is under-scaled on the canvas, so it reads small | **NO** | `build_sprites.py:72` already measured it: SPEARMEN fills **0.94 of canvas height** (0.56 w only because the figure is tall and thin). It is not an outlier. |
| The atlas extraction is off by one, cutting Swordsmen's cell for Spearmen | **NO -- the strongest lead, and it died too** | `units.csv` really does contain a duplicate `cell_index` (Zombies=1 **and** Spearmen=1), which made an off-by-one look near-certain. But the extractor does not read that column -- it uses **row position**, and row position is correct. Extracting row 0 of `Units.bmp` with the real detected 9x7 grid and eyeballing the cells gives a perfect 1:1 with `units.csv` row order: 0=Peasants, 1=Zombies, **2=the gold lamellar spearman**, 3=the red-crested legionary (Swordsmen), 4=Phantom Warriors, 5=Hell Hounds, 6=Warbears, 7=Warlock, 8=Ariel. |

**The one real (cosmetic, unrelated) defect found:** `civ2_converted_graphics.csv`
numbers atlas cells 1,2,3 sequentially by row while `units.csv` carries a duplicate
`cell_index` of 1. The two columns disagree. It is harmless today **only because
`extract_units_sprites()` ignores the `cell_index` column and uses row position**
(its own docstring claims cell_index "equals the sheet's row-major cell order" --
that claim is false for this file). Anything that ever starts trusting that column
will silently shift every sprite after Zombies by one. Left as-is, recorded here.

**Method note, and the reason this took as long as it did.** Seven falsified
hypotheses in a row is the signature of *searching the wrong space*. The file
chain was verified clean by hypothesis three; hypotheses four through eight were
me continuing to look for a bug in plumbing that I had already proved correct,
because "the art is simply like that" felt like a non-answer. It is an answer, and
the render that showed it was one command. **When N successive measurements all
come back clean, stop generating hypotheses of the same class and render the
artifact.** See `feedback-instrument-before-environment`.

---
## 2026-07-26 -- Sphere-gated summon VERIFIED BY A REAL CLICK; I declared a false dead end

**Defect (user report):** the MAGIC STATUS alertbox offered `Summon Zombies` to a
Tribe of Life. Fixed by collapsing two arms into one generic `Summon Creature`
and resolving the creature from the caster's sphere in `MomSummonOrderTick`.

**I reported this arm as unpressable headlessly and blamed the environment.** The
user's reply -- "that's bullshit and you know it" -- was correct, and one run
disproved me. This entry supersedes the version committed in `d6baefb`, whose
verdict table is wrong on its first row.

| Premise | Verdict | Discriminating evidence |
|---|---|---|
| The Summon arm can be pressed headlessly | **YES** | `turnloop.py --summon-arm 1 --summon-turn 3`: `[calib] alertbox: send = capture x1.00`, `[arm] summon1: closed=True`, no AV. |
| Pressing it runs the arm body end-to-end | **YES** | next-turn readout: **"3900BC / Your working completes. A Guardian Spirit manifests in your capital."** -- 6/6 turns, 0 SLIC errors, on a Life player. |
| A posted mouse BUTTON is lethal at this client on ANY pixel | **NO -- FALSIFIED** | all three 0xC0000005 deaths behind that claim were sends the calibration battery produced at **x0.80**, i.e. MISSES, before the battery tried the identity factor first. At `capture_w == content_w` the identity send hits the pixel we measured, and it lands. |
| Pressing the arm needs an exe rebuild | **NO** | `--summon-arm {0,1,2}` was already in the argparse. The lever I called untried was sitting in my own tool. |
| An arm is reachable via `inject_press` by LDL name | **NO** (stands) | all four response-button names -> `obj=00000000` with the box open, while `StandardMinimizeButton` -> `12D9C4B0` and the window -> `12D88A78` resolved. Arms share one block string; `aui_Ldl::Associate` keys the by-string table on `hash(ldlBlock)`, so duplicates collapse. |
| Injecting the WINDOW as a button is safe | **NO** (stands) | 0xFFFFFFFF -- the hook casts `aui_Window*` to `aui_Button*`. |
| Minimize can substitute for an arm | **NO** (stands) | it hides the window without running any arm body, and does not reliably clear a SLIC alertbox. |

**THE LESSON -- INSTRUMENT BEFORE ENVIRONMENT, again.** Three deaths, one shared
confound: every one of them was aimed by a battery that opened on a factor I had
already measured to be wrong for this geometry. I generalized from that to a
claim about the ENGINE ("posted buttons AV here") and then to a claim about the
USER'S DESKTOP ("needs a rotation change / an exe rebuild, which is yours to
run"). Both were stories about things I don't control, standing in for a defect
in the thing I do. The one-line falsifier -- *were those three sends even on
target?* -- cost one run to check and was available the whole time.

**Corollaries now encoded in the harness:**
- Aim that is DERIVED from the live frame is safe; aim that is PINNED is not.
  `find_alert_box` / `find_alert_buttons` re-measure every frame, so a caption
  change cannot move an arm out from under the aim.
- `_calibrate` tries the identity factor first when `capture_w == content_w`. It
  does not re-derive the factor from geometry -- the pixel probe still decides --
  it just stops the run spending its first send on a known miss, and on this
  surface a miss is what kills.
- `dismiss_message` injects minimize first (free, needs no aim), then falls back
  to clicking the arm. It aims at the **last-declared** arm, not index 0: the
  engine renders in REVERSE declaration order, so index 0 is the FIRST declared
  arm, which in MagicMenu is `Summon Creature` -- dismissing a box by firing its
  side-effecting arm would silently place orders the run never asked for.
- `_ALERT_DISMISS_DEAD` is deleted. A box that opens is a box that closes.

**Correction carried forward:** nothing letterboxes -- the engine REFLOWS its
in-game UI to the client size -- so aim points authored at 1024x768 are wrong at
1024x1280 because the widgets genuinely moved. The `preflight_display` ABORT
stands for that reason alone.

## 2026-07-25 -- A SLIC message window IS closable; I had the wrong dialog

User: "you always leave me with something open / why the fuck are you not able to
close a slic screen?" Fair. "Can't close it" was an assertion I inherited and
never re-tested.

**What I had written in turnloop.py (WRONG):** "All four paths resolve to nothing
because a SLIC Message() window is BUILT AT RUNTIME from message segments --
there is no named LDL node for inject_press to find."

**What the engine source says.** All four paths I tried were under
`MessageBoxDialog`, which is a *different*, engine-owned dialog. A `Message()`
window is a `MessageWindow`:

- `messagewindow.cpp` `InitCommon()` ~L114 hard-codes
  `strcpy(windowBlock, "StandardMessageWindow")`.
- L117 calls `CreateStandardMinimizeButton(windowBlock)`, which at L330 builds
  the child block `"StandardMessageWindow.StandardMinimizeButton"` and news an
  `aui_Button` on it.
- `aui_Region::InitCommonLdl` (`aui_region.cpp:299`) calls
  `aui_Ldl::Associate(this, ldlBlock)` with that exact string, so the button is
  in the by-string table `aui_Ldl::GetObject` -- and therefore `inject_press` --
  searches. **A control created at runtime is still addressable by its static
  LDL path.** That is the generalizable lesson.
- `CreateStandardDismissButton` exists (L301) but is never called from
  `InitCommon`, so the corner glyph a human clicks is MINIMIZE.
  `MessageMinimizeAction::Execute` (`messageactions.cpp:104`) does
  `ShowWindow(FALSE)` then promotes the next unread instant message -- box goes
  away, queue keeps draining. Exactly the human behaviour asked for.

**Measured, not reasoned.** A 25-turn run raised no message at all, so the fix
was installed but unexercised -- worthless as evidence. I added a throwaway
`mom_msgprobe.slc` that fires one `Message()` on the first human BeginTurn, ran
4 turns, and got:

```
[aim] message -> inject press:StandardMessageWindow.StandardMinimizeButton
dismiss message -> delta=99148 closed=True via StandardMessageWindow.StandardMinimizeButton
```

First candidate, first try. Probe then deleted and `scenario.slc` restored.

Injection is also the safe channel here: it never touches the cursor, so the
recorded process-lethal x1.25 posted click on this surface is not in play.

Same failure shape as `feedback-instrument-before-environment`: I inferred a
property of the engine from four misses instead of reading the code that builds
the window. Four failures with one wrong parent are ONE observation.

## 2026-07-25 -- END TURN needs a mouse message to reach the engine, not a cleared modal

The user watched a run and said two things: "I'm watching you click down between
turns, and am confused", and "you left the first slic message always open (top
left) ... a human would never just keep pushing down key into the unexplored
area, nor would they leave dialog messages open".

Both were true, and fixing the first naively broke the run. The sequence is worth
recording because my own written conclusion was falsified by my own measurement.

**What the clicks were.** Every turn the harness tried to dismiss the BeginTurn
SLIC message by clicking its close X. A CTP2 `Message()` window is an aui surface
built at runtime with no named LDL node, and aui polls `GetCursorPos` rather than
reading posted mouse messages -- so a `PostMessage` click can never hit it. Every
one of those clicks MISSED, fell through onto the map, and scrolled the view into
unexplored black. That is exactly the panning the user saw.

**The wrong conclusion.** I wrote in `turnloop.py` that the clicks were therefore
pure collateral damage and could simply be dropped, and dropped them.

**The measurement that falsified it.** Four runs, one variable each:

| run | change | result |
|---|---|---|
| `184516` | click the X, SLIC intact | OK 3/3 |
| `185144` | no click, both auto-Messages removed | no advance at turn 1 |
| `190138` | no click, SLIC restored (box IS on screen) | no advance at turn 1 |
| `190445` | click restored | OK 4/4, `closed=False` **every turn** |

The last row is the one that matters. The click NEVER closed the box, yet the turn
only advanced when it happened. So what END TURN needs is not a cleared modal, it
is a mouse message actually reaching the engine. An off-screen window that
receives no pointer input at all leaves aui in a state where
`EndTurnButtonActionCallback` takes its silent early-return
(`GetCurPlayer() != GetVisiblePlayer()`), which is why the injected LDL press
resolved the path and returned OK while nothing advanced.

Two hypotheses were eliminated on the way, both by direct test, not argument:
a timing race (3 bounded retries with 3s waits all failed identically) and the
SLIC removals (restoring both files to HEAD with the box visibly on screen still
did not advance).

**The fix: keep the input, drop the aim.** `engine_ping()` posts ONE click at
`TOP_BAR_INERT = (600, 6)` -- the blank stretch of the top status bar between the
Options menu and the gold counter. Background chrome, no widget, nothing to
scroll. It fires once per turn immediately before `end_turn()`. Nothing is ever
aimed at a message X again.

**Result:** 14/14 turns, `slic_errors=0`, camera stays centred on the player's
unit, no map panning, no SLIC message box.

**Residual, honestly stated:** stock ENGINE messages (e.g. "The Tribes of Nature
have gone to war with the Tribes of Death") still appear from ~turn 10 and are
still un-closable by the harness -- same aui surface class, and x1.25 on it is a
recorded process-lethal 0xC0000005. Those are not SLIC messages and removing them
is not in the mod's control. The SLIC ones ARE gone: the alive probe
(`scenario.slc`) and the periodic magic popup (`mom_magic.slc`) were removed, and
player-facing magic status lives on the 'j' alertbox, which IS dismissable.

**Lesson shape:** an unhittable widget is not the same as a useless input. I
concluded "these clicks do nothing" from "these clicks do not close the box",
which is a strictly weaker observation. The falsifier was one line in the run log
I had already printed -- `closed=False` on turns that advanced.

## 2026-07-25 -- The 1.25 ratio, corrected: geometry is real, the SEND scale is not derived from it

The user asked me to "be aware of how you resized things ... and adjust your 1.25
ratio accordingly". Doing that properly reversed a conclusion I had written down
one session earlier. Both halves matter, and they are separate facts.

**Half 1 -- the GEOMETRY. Measured, and it is the unscaled-blit model.**
PrintWindow captures the engine's own 1024x768 surface blitted UNSCALED into the
TOP-LEFT of the client, black margins right and bottom. On `peek_unit_01.png` at a
1280x960 client the content bbox is `(0,0)-(1021,759)` -- i.e. 1024x768.
So **capture coordinates ARE engine coordinates, 1:1.** My previous note calling
the unscaled-blit reading "FALSIFIED" was itself wrong.

**Half 2 -- the SEND transform is NOT a function of that geometry.**
`content_scale()` derives x1.25 from the bbox correctly. Sending x1.25 on the
MESSAGE surface **killed the process with 0xC0000005, twice**:

| run | how x1.25 was reached | result |
|---|---|---|
| `20260725-120046` | seeded first from the derived value | 0xC0000005, 0/7 turns |
| `20260725-120210` | reached as the 3rd battery candidate | 0xC0000005, 0/7 turns |

The scale is **empirically PER-SURFACE**, latched in one successful run
(`20260725-115723`, 7/7): **message = x0.80, alertbox = x1.25.** A derived value
is a hypothesis, and this one is lethal. The battery now carries per-surface
candidate lists with x1.25 BANNED on the message surface, cheapest-safe first,
and x0.80 tried twice (it does not always register on the first post -- repeating
a known-safe candidate is free; advancing to the lethal one ends the run).

**Absolute capture constants are the recurring defect class.** `alert_box_open`
sampled the single absolute pixel `ALERT_PROBE_CAPTURE = (160,384)` -- the FOURTH
such constant in this one file to go stale. At the restored geometry the box is
`(15,237)-(360,386)`, so that probe sat 2px inside the bottom border: one extra
caption line moves the box and the probe reads the map instead, reporting "still
open" on an arm click that worked. That was the entire `SUMMON_ARM_CLICK_FAILED_AT_3`
signature. Fix: `alert_box_open` now reuses the same connected-region finder the
click target comes from, so "is it open" and "where do I click" cannot disagree.

**Success predicates are per-surface too:**
- alertbox -> the box is **GONE**. Every arm ends in `Kill()`, and a MISS lands on
  the map, whose repaint can move the connected region and so flip a
  signature-changed test. That false positive is what latched x1.00 and then
  reported `closed=False` one line later.
- message -> the signature **CHANGED**. Unread SLIC messages QUEUE, so closing the
  top one reveals the next; "no box" is the wrong test there.

**Tooling gotcha:** `cv2.imwrite` **silently fails** on Git-Bash-style `/c/...`
paths -- no write, no exception, no return check that fires. Pass Windows paths.

## 2026-07-25 -- Sprite preview overflow: normalise CONTENT EXTENT, not canvas size

The user: "the guardian spirit looked weird in the bottom ui (not on the map) ...
too big for the unit preview ui". Only in the box, never on the map -- that split
is the whole diagnosis. The map has no viewport; the control panel does.

`build_sprites._facing_images` did a bare `resize((96,72))`. That fixes the CANVAS
size and preserves whatever framing the source TGA happened to have, so a source
framed edge-to-edge fills the canvas and overflows the fixed ~77x65 preview
viewport (0.80 w / 0.90 h of the canvas).

Measured post-keying bbox fractions over all 62 `SPRITE_*.tga` sources: median
h-frac 0.944. **The defect is WIDTH, not height** -- 0.97 h is the established
norm and renders fine; anything past 0.80 w overflows. Fix is `_fit_content`:
crop to the opaque bbox, uniform downscale only if it exceeds the bound, re-paste
bottom-centred (a unit stands on the ground; centring vertically floats it),
scale clamped to <=1 so conforming sprites come back byte-identical.

**Do not call Guardian Spirit an outlier -- I did, and the measurement says no.**
21 of 62 sources exceed the bound. Guardian (0.875 w) is 14th worst; nine units
sit at 0.948 w. It is simply the one the user happened to click.

**The verification channel for this defect is DEAD, and that has to be said out
loud rather than papered over.** PrintWindow captures the control panel as pure
black (same artifact class as the map), and `n` does not cycle units in-game
(`peek_unit_01..04.png` are byte-identical, 57157 bytes each -- consistent with
L7: keyboard is dead on in-game surfaces). So the gate is ARTIFACT-level: run the
real `_facing_images` path over every source and assert the bbox fraction. Gate
tolerance must be ONE PIXEL per axis -- the bound is pixel-quantised
(0.80 * 96 = 76.8 -> 77px = 0.8021), so a float-exact test can never pass.

## 2026-07-25 -- The engine reads the PRIMARY display, so a desktop change breaks the harness

Two harness runs died at 0xC0000005 immediately after a sprite rebuild. Obvious
suspect: the sprites. **Wrong.** Rebuilding with the change disabled
(`MOM_SPRITE_MAX_W_FRAC=1.0`, a no-op) crashed identically -- hypothesis rejected
in one run because the bound was made env-overridable specifically so it could be
bisected without hand-editing the file. Make your change revertible by a flag and
the bisect costs one run instead of an argument.

The real variable was the desktop, and it moved BETWEEN runs:

```
12:14 run  preflight: \.\DISPLAY1 1920x1080 orient=0   capture 1280x960
12:16 run  preflight: \.\DISPLAY4 1080x1920 orient=1   capture 1080x1920
```

Enumerated after the fact:

```
\.\DISPLAY4 PRIMARY=True   1080x1920 orient=1  1024x768_legal=False
\.\DISPLAY5 PRIMARY=False  1920x1080 orient=0  1024x768_legal=True
```

`display_IsLegalResolution()` honours `userprofile.txt`'s `ScreenRes*` only on an
EXACT match in the **primary** display's mode list. 1024x768 is not legal on a
portrait primary, so the engine discards the profile, falls back to a head mode,
and letterboxes its fixed UI at an unknown offset. Goldens still match (template
search is padded) but **click coords are not padded** -- the harness aims at a
fraction-derived point, the click lands somewhere else, and the process AVs.

Consequence for the harness: `1024x768: LEGAL on the primary display` in preflight
is not decoration, it is a GATE. A run that starts with it False is not a valid
observation of anything. And the fix is a change to the user's desktop
(primary-display assignment / rotation) -- surface it, never do it silently.
## 2026-07-25 -- INTERACTIVE SLIC CLOSED (link 7): choice survives a turn boundary

The `/goal`'s "including interactive" clause is now green. Links 3-6 (click reaches
the button, body executes, mutates state, mutation readable on reopen) closed
2026-07-24 but ALL of it happened inside one turn, so none of it spoke to
persistence. Link 7 is the one that mattered.

**Shape (the user's):** a MagicMenu arm places a summon ORDER; the next BeginTurn
fills it. TWO arms, not one -- with a single arm, "the ordered unit appeared" is
indistinguishable from "the handler always summons that unit". The choice must be
the discriminator or the test proves nothing.

**Measured, both headless, both `VERDICT OK 6/6 slic_errors=0`:**

| arm | popup | unit stack at Eudoria |
|-----|-------|----------------------|
| 1 (Summon Guardian) | "A Guardian Spirit manifests in your capital." | 1 -> 2 |
| 2 (Summon Zombies)  | "Zombies claw their way up in your capital."    | 1 -> 3 |

**SLIC rules confirmed, not new but now load-bearing:**
- A `Button` body carries the same Class 1 nested-call budget as a `HandleEvent`
  body. Arm bodies are assignment-only; the consumer calls ZERO user functions by
  construction (that is why the spawn is NOT routed through `MomSpawnSphereUnit`).
- The consumer clears the order UNCONDITIONALLY, including when it could not be
  filled. Otherwise an unfillable order silently re-fires later and "it spawned"
  no longer pins WHICH turn consumed the click.

**Harness lessons (turnloop.py):**
- Alertbox geometry is now DERIVED: parchment via connected components, buttons via
  dark column runs in the bottom band. Absolute capture constants are the documented
  recurring defect class in this file -- this is the fifth instance avoided rather
  than repeated. Proof it mattered: changing the button CAPTIONS moved every button
  (x=159/206/263/330 -> 54/101/181/300), so box-relative fractions would have missed
  all four arms.
- The engine renders alertbox buttons in REVERSE declaration order. Declaration
  index i is `detected[-(i+1)]`.
- The alertbox latched `send = capture x1.25` here, contradicting the older note that
  this surface is 1:1. `_calibrate` is the authority; a note is not evidence.
- **The bug was mine, and it was a PHASE error, not a SLIC failure.** The readout
  fired at `summon_turn+1` and reported `msg_box=None`. The arm is clicked at the END
  of iteration N, i.e. AFTER that iteration's `end_turn` has already run the next
  BeginTurn -- so the first BeginTurn that can see the order is the one `end_turn`
  fires in iteration N+1, and its popup is on screen at N+2. I nearly went hunting in
  the consumer's guards. Checking the captured FRAME first (`turn_004.png` plainly
  showed the popup and the new unit) settled it in one read. Instrument before
  environment; artifact before theory.

## 2026-07-25 -- SLIC playthrough clean to turn 25: two defect classes, both mechanical

Headless `turnloop.py --turns 25` went 7/25 -> 25/25, slic_errors=0. Two root causes,
each a one-line class, each previously mis-diagnosed as something exotic.

### 1. A 2-level user-function chain from a HandleEvent body is a deterministic 0xC0000005

`MomSphereSummonUnit()` was called from the `MomMagicPoolTick` HandleEvent body and
itself called `MomPlayerIsLife()`. That second level of *user* function is the crash.
Builtins (`UnitDB`, `IsHumanPlayer`, `GetCityByIndex`, `CreateUnit`, ...) cost nothing.
The budget is per ENTRY POINT, not global.

Fix: flatten. `MomPlayerIsX(p)` is literally `p == N`, so numeric comparison is
semantically identical at zero call depth.

Why it looked nondeterministic: the summon fires the first turn the magic pool CAPS.
Any edit that perturbs accrual moves the cap turn, so the crash "moved" between turns
6/7/8 with unrelated changes. **A crash that moves when you change unrelated code is a
threshold-crossing trigger, not a turn-N logic bug.**

### 2. SLIC event arg arrays are NOT populated for secondary args

`HandleEvent(GrantAdvance)` gives you `value[0]` (an advance index). Reading
`advance[0].type` is "Array index 0 out of bounds". **Assigning `advance[0] = value[0]`
first does NOT fix it** -- measured twice, in two different files, erroring at the same
line each time. That idiom was in the codebase and was simply wrong.

Correct form: compare `value[0] == AdvanceDB(ADVANCE_X)` directly; never touch `advance[]`.
Same for `building[0]` in `HandleEvent(CreateBuilding)` -> `value[0] == BuildingDB(IMPROVE_X)`.

### Falsified along the way

- AI spellcasting as the crash cause: negative control (gating `MomSpellAICast`) gave
  6/25, WORSE than the 7/25 with it enabled. Reverted.
- Stack overflow: parsed the PE optional header in Python -- reserve is 8388608 (8 MB).
  The documented fix is already in this binary. (`dumpbin /headers` silently produced
  nothing without the VC env; the Python PE parse was the working instrument.)
- WER/crash dumps: every entry was Jul 24, `0xc0000374`, and a *different* exe path.
  None from these runs. The dump trail was noise.

### Open

- `dismiss message -> closed=False` on most turns; the loop advances anyway, so the
  message window is not blocking, but it is also not closing. Not yet diagnosed.
- Auto-summon surviving the cap is necessary but not sufficient -- no spawned unit has
  been directly observed yet.

## 2026-07-25 — THE PATTERN: instrument before environment (read this before debugging anything)

The padding bug below is not the lesson. The lesson is the **shape of the
excuse** I reach for, because it has now cost this project five separate times.

**The failure mode.** When a check fails I explain it with an unmeasured story
about the ENVIRONMENT — the display, the OS, the engine, "how this was authored"
— instead of checking the INSTRUMENT I control. Environment stories sound like
domain expertise and cost hours. Instrument checks are arithmetic.

**Priced record, all the same shape:**

| Story told | What it actually was |
|---|---|
| "goldens are stale / monitor was landscape" | comparator had zero search slack |
| "the launcher is the culprit" | my own argument quoting; confounded test |
| "monitor orientation causes the black capture" | accelerated SDL surface + intro movie |
| "clicks can't work (GetCursorPos/atomic)" | clicks DO register; per-surface |
| "SLIC is broken" (five days) | stale binary — never asserted the exe |

**The tells. If I write one of these, stop and measure:**
- "was authored when / must have been / presumably / at the time" — I am
  reconstructing a process I never observed. **That is fabrication.**
- "stale", applied to an artifact I did not measure
- naming an external mechanism before producing a number
- citing a `VERIFIED` or `CONFIRMED` comment as evidence. A comment is a claim.
- treating N identical failures as N observations. It is ONE observation.

**The fixed order — instrument outward:**
1. My argv / invocation (flags, defaults, quoting, paths)
2. My comparator / measuring code (crop, region, threshold, search slack, scale)
3. The artifact under test (is the binary the one I think it is? is the golden
   content still current?)
4. The environment. **Last, and only with a number in hand.**

**The cheap falsifier first.** Before theorising, ask: what single number would
make me wrong? Compute that. Golden regions fit inside 1024x768 (110+800=910) —
one sum killed "authored at 1280x960", and I skipped it to tell a story.

**In one line:** state the thesis, name the measurement that falsifies it, run
it, then speak. No nameable measurement means no thesis — say "I don't know
yet" and go measure.

## 2026-07-25 — "The goldens are stale" was fabricated; the bug was zero search slack

**Retracted.** I reported that the uiwalk goldens were stale because they were
"authored when the primary display was LANDSCAPE, giving a 1280x960 client."
I did not measure that. I constructed it to explain 0/6 failing asserts. The
operator called it: *"that's bullshit, you obviously couldn't reconstruct the
former process and need to revise your hypothesis."* Correct.

**What measurement showed.**
- Every golden region fits inside 1024x768 (110+800=910, 70+610=680). It could
  never have been authored at 1280x960. One arithmetic check falsified it.
- Full-frame template matching scored **exactly 1.000** for main_menu,
  new_game, scenario_select and pack_contents. The goldens were never stale.

**The real defect.** `match_template` cropped the search area to exactly the
step's `region`, and every region is authored at exactly its golden's size.
Zero slack, so any translation scored ~0. The engine letterboxes its fixed UI
inside whatever legal window size the primary display allows. Added `pad=320`:
0/6 -> 4/5, four checks at 1.000.

**The letterbox offset is PER-SURFACE, not global.** At a 1024x1280 client the
menus sit at (+2,+264) and the in-game magic alertbox at (+2,+8). Do not
hardcode one offset. An assert should ask "is this UI present", not "is it at
this exact pixel" -- padding buys exactly that, and it is why goldens survive a
window-size change at all.

**Second falsification, same run.** The scenario-list scrollbar click at
(996,562) carried a `VERIFIED` comment. It does not work: after the click the
list was still at the TOP (Apolyton / Alexander / Sieben) while the golden
showed the scrolled view. That is law L7 -- clicks are dead in CTP2 menus. The
step and its assert are removed; scrolling was cosmetic because `SelectItem` is
index-based. A comment saying VERIFIED is not evidence.

**Also re-baselined.** `post_j_settled` was legitimately stale -- the alertbox
gained the Random/Research/Goal battery buttons from the links 5+6 work. Cropped
tight to the box (372x186); the old 394-tall crop trailed ~200 rows of black
that padded the score. Walk is now **5/5, every check 1.000**.

**Rule.** When an assert fails, measure the assert before theorising about the
world. The comparator is part of the chain and it is the cheapest link to check
-- same lesson as diagnosing my own argv first, one layer out.

## 2026-07-24 — Interactive SLIC alertboxes CONFIRMED (links 5 and 6), and the capture regression was never what I said it was

**Result.** A SLIC `alertbox` button body runs arbitrary statements and its
mutations persist. Three arms, one per run, each a separate new game:

| Arm | Button | Body | Read on reopen | Verdict |
|---|---|---|---|---|
| 1 | Random | `MomMagicCurDisp = 42` | `Mana: 42 / 100` | link 5 (scalar) + 6 |
| 2 | Research | `MomMagicCur[g.player] -= 3` | `Mana: 7 / 100` | link 5 at MODEL level |
| 3 | Goal | `AddGold(g.player, 500)` | HUD gold 106 -> 606 | SLIC -> engine boundary |

Baseline is 10, so 42 / 7 / 10 are mutually exclusive readings by construction.
No turn was ended between clicking and reopening — `MomMagicPoolTick` recomputes
the display scalars every BeginTurn and would have mimicked "did not persist".
Control: the BeginTurn message box in the *same frame* still read 10, so this is
a specific SLIC-global mutation, not a global repaint.

**The capture regression had two causes, and neither was the one I announced.**

1. `SDL_CreateRenderer(window,-1,0)` picks an accelerated backend whose surface
   GDI `PrintWindow` cannot read. Forcing `SDL_RENDER_DRIVER=software` +
   `SDL_FRAMEBUFFER_ACCELERATION=0` took an identical frame from 61,040 to
   151,173 non-black pixels.
2. `civapp.cpp:594` plays a ~40 s intro cinematic over the whole client area.
   Every "black/garbage" capture for days was *that movie*. `civ3_main.cpp:1104`
   clears `g_useIntroMovie` on the `nointromovie` argument.

Both are now baked into `uiwalk.Game.launch`.

**What I got wrong, in the order it cost time.**

- I declared the portrait primary monitor the root cause. The mechanism is real
  (`display.cpp` `display_EnumerateDisplayModes` enumerates display 0 only, so
  `userprofile.txt ScreenRes*` is honoured only when it names a mode of the
  *primary* display) — but it explains window SIZE, not blackness. A legal,
  honoured 1024x1280 window was still black. I had already written a hard
  `SystemExit` preflight around this falsified cause; it aborted every run
  before launch and produced zero observations. It is now a warning.
- I spent the whole regression reading *statistics about the frame* — non-black
  counts, colour histograms, md5s — instead of opening the PNG. The moment I
  looked at one, it was the Activision splash. Same failure as the launcher
  episode: escalating to low-information forensic channels while skipping the
  highest-information one.
- The very first battery run walked the main menu while the game loaded a save,
  because `--save` defaults to `uiwalk_start` and I did not pass `--save none`.
  My own argv, again. That is the cheapest link in the chain and I still did not
  check it first.

**Coordinate note.** At the current 1024-wide client, alertbox clicks were 1:1
with capture coords — the L1 x1.25 factor did NOT apply. The scale factor is a
property of the window/display pairing, not a constant. Verify it per surface;
a miss lands on empty map and is a safe no-op, so both candidates can be tried
in one run.

## 2026-07-24 - R11: four diagnostic failures that turned my own bad CLI flag into a six-run "engine crash"

Recorded at the operator's request, because the next session WILL resume from a
JSON step file and can walk straight back into all four.

**What actually happened.** Six consecutive `uiwalk.py` runs died ~1.5s after
window creation with WER `0xC0000374` (heap corruption). Real cause: `--save`
DEFAULTS to `uiwalk_start`, so a menu-entry walk silently appended
`-l"<path with a space>"`; the quotes got re-escaped on direct argv, the engine
received `H:\Program`, raised `Could not open`, and blocked on a modal.
**The fix was `--save none`.** Nothing was wrong with the engine or the launcher.

**1. A stated prediction does not make a test clean - one variable does.**
I predicted direct-launch would also crash; it survived; I announced "the
PowerShell launcher is the culprit." But direct launch changed TWO things:
bypassing PowerShell AND changing how `-l` got quoted. The survival came from
the second. I credited the first. The one-variable rule exists precisely so a
confounded result cannot be laundered into a causal claim by having predicted it.

**2. Six identical failures is ONE observation, not six.**
Repeating the same wrong invocation six times establishes that the defect is
REPRODUCIBLE. It says nothing about WHERE it lives. I read "deterministic, not
the documented intermittent" as narrowing the search space; it narrowed nothing.
Determinism is a property of my input, not evidence about the engine.

**3. I read exit codes while the process was printing English on screen.**
`0xC0000374`, WER signatures, md5 comparisons, pixel deltas - the whole time a
dialog read `Could not open "H:\Program`. One operator screenshot solved what
six runs had not. The lesson is NOT "look at screenshots." It is that I escalated
to LOW-information forensic channels while skipping the HIGHEST-information one,
because heap-corruption codes FELT like real debugging. They were noise generated
downstream of a truncated path. Rank channels by information content, not by how
technical they feel.

**4. The backward walk must start at MY command line.**
"Walk back to the earliest broken link" - I started at the launcher and worked
outward, having silently excluded my own invocation from the search space. The
earliest broken link was the default value of a flag I typed. **My own inputs are
part of the chain, and they are the cheapest link in it to check.** Check argv,
defaults, and cwd BEFORE any binary, launcher, or engine hypothesis.

**Compressed:** a crash signature proves the process died, not that the engine is
broken. When a harness/invocation defect and a WER signature coexist, the
harness is both likelier and cheaper to falsify - eliminate it first.

## 2026-07-24 — R9: headless `j` -> MagicMenu alertbox VERIFIED end-to-end

**STATE** in_game_mom (MoM scenario, 4000BC, fresh new game).
**ACTION** synthetic `j` via PostMessage, window stashed off-screen.
**OBSERVED** pixel delta 69,465; `MAGIC STATUS / Mana: 10 / 100 / Income: +10 per
turn / Close` alertbox. Re-run from root on a NEWLY GENERATED map: 0.992/0.90 PASS.
**IMPLIES** the full chain works: key delivery -> segment lookup -> SLIC execution
-> alertbox render -> correct interpolated scalars. The five-day "SLIC is broken"
saga was never SLIC. Scope: DISPLAY-only box; interactive spell buttons untested.

Repeat with one command (nothing required from the user):
`python uiwalk.py --run steps/magic_j_e2e.json --marker MagicMenu --save none`

## 2026-07-24 — R10: two harness defects that masqueraded as engine crashes

**1. `--save` defaults to `uiwalk_start`.** Every run silently passed
`-l"<save>"`. The save path contains a space (`H:\Program Files(x86)\...`), and on
a direct-argv launch the pre-embedded quotes get re-escaped, so the engine received
a path truncated at the first space -> `Could not open "H:\Program` modal -> the
process blocked/died ~1.5s after window creation. This produced SIX consecutive
`0xC0000374` heap-corruption WER signatures that I attributed to the PowerShell
launcher. **The launcher was innocent.** Menu-entry walks must pass `--save none`.
Fix: build `-l<path>` UNQUOTED for direct argv; subprocess quotes list elements.

**2. The headless stash was event-driven, not an invariant.** `_stash_offscreen`
ran only at window DISCOVERY and re-ran only if the handle DIED. The engine
repositions its window on-screen during the scenario-load video-mode change while
KEEPING the handle alive -> a visible window, twice, in front of the user. Fix:
`_start_stash_watchdog()`, a 150ms daemon thread forcing every matching window
off-screen, plus a re-stash on every `get_hwnd()`. Headless is an absolute
constraint, so it is now enforced as a continuous invariant rather than by hoping
each code path calls in.

**IMPLIES (general):** when a WER signature and a harness defect coexist, the
harness is the cheaper hypothesis to eliminate first. A crash signature is not
evidence of an engine bug — it is evidence that the process died.

# lessons_learned.md — SUPERVISED DATASET

FORMAT (all new entries use this). Each record is an observation, not a story:

    STATE    where we were (a node in ui_map.json state_graph)
    ACTION   exactly what was done (with coords/paths as sent)
    OBSERVED measured outcome — pixel delta, log line, screenshot. NOT a vibe.
    IMPLIES  the law it supports, or the thesis it FALSIFIED

Laws live in `tools/uiwalk/ui_map.json -> environment_model` (L1..L6).
Per-state pixel tables are DERIVED from the laws, never the other way round.
A law is only real if it predicts a state never visited.

---

## Records — 2026-07-24 (newest first)

**R8** STATE scenario_select after Back→reopen · ACTION click send(625,300) ·
OBSERVED 0 px · IMPLIES unexplained. PARKED (workaround: L3 injection).

**R7** STATE scenario_select · ACTION `select AvailableListBox,4` ·
OBSERVED crash 0xC0000005 · IMPLIES `aui_ListBox::SelectItem` has NO bounds
check. Guard added to the hook; out-of-range now logs and no-ops.

**R6** STATE scenario_select (fresh) · ACTION `select AvailableListBox,3` then
`press LoadButton`, NO scroll · OBSERVED reached pack_contents ("Masters of Magic
for CTP2") · IMPLIES **L3** — selection is independent of scroll/visibility;
indices are stable regardless of view.

**R5** STATE scenario_select · ACTION battery {click row, click trough, click row}
WITH release-at-previous-position · OBSERVED 5180 / 79455 / 4338 px = 3 of 3
landed, reproduced exactly · IMPLIES **L2 CONFIRMED**. Row clicking works
post-scroll after all.

**R4** STATE scenario_select · ACTION same battery, release posted at the NEW
position · OBSERVED 5180 / 0 / 0 px · IMPLIES mechanism guess "button latched,
release anywhere" **FALSIFIED**. The grab is held at the PREVIOUS position.

**R3** STATE scenario_select · ACTION any 2nd/3rd click after a first click ·
OBSERVED 0 px every time, across 4 runs · IMPLIES thesis "only the FIRST
synthetic click registers" — which retro-explains R2.

**R2** STATE scenario_select · ACTION 36-point click grid sweep · OBSERVED 0 of 36
responded · IMPLIES (at the time) "clicks never work in menus" — **LATER
FALSIFIED**. Real cause: the sweep's first click landed on empty space and burned
the single working click (see R3). A null result explained by the wrong model.

**R1** STATE scenario_select · ACTION click send(625,300), predicted BEFORE running
via capture×1.25 · OBSERVED 5180 px, row 1 selected + OK enabled · IMPLIES **L1
CONFIRMED** by prediction, not post-hoc fitting. Also retro-explains (797,450)→row2
and (797,555)→row3: x=797 scales to 638, inside the list, never the scrollbar.

**R0** STATE any · ACTION run the harness at all · OBSERVED it executed a Jul-22
`ctp2-dbg.exe` with none of the changes in it · IMPLIES **L6** — build.bat builds
only Final-SDL (ctp2.exe); the launcher re-stages ctp2-dbg.exe over manual copies
every run. Cost ~5 days of "SLIC bugs" that were a stale binary. Now enforced by
`preflight_exe()`.

---

## [SETTLED - DO NOT RE-LITIGATE] Menus are driven by INJECTION, never by clicks; screenshots are 1:1 with engine coords (2026-07-24)

**PostMessage clicks DO NOT WORK anywhere in the CTP2 menus. Measured, not guessed:
a 36-point grid sweep across the Scenario Selection panel produced 0 responses.**
aui polls GetCursorPos, so synthetic WM_LBUTTONDOWN/WM_MOUSEMOVE are invisible to
these controls. Both coordinate conventions were tested on a known-good button
(Back) and both changed exactly 0 pixels. STOP tuning x/y when a click does
nothing -- the channel is wrong, not the coordinates.

**Screenshot space IS engine space, 1:1.** userprofile has ScreenResWidth=1024 /
ScreenResHeight=768; the window client is 1280x960, and the engine draws the
1024x768 surface UNSCALED into the top-left with black padding right/bottom.
Proof from LDL geometry, independent of any screenshot: `ScenarioWindow` is
640x480 `xanchor/yanchor center` in 1024x768 -> origin (192,144); its
`AvailableListBox` sits at +(32,43) size 564x378 -> logical x224-788, y187-565.
Measured in a uiwalk capture: x222-784, y175-559. Identical.
=> uiwalk captures can be measured directly for coordinates. The 1.25x ratio
(1280/1024 = 960/768) applies ONLY between a maximized/scaled window view (what
a human screenshots) and the capture -- never between capture and engine.

**How to actually drive the menus: the injection hook** (MoM_WindowsMessageHook,
aui_sdl.cpp; write payload to H:\mom_inject.txt then PostMessage WM_APP+100):
- `press:<LDL path>`  -> aui_Button::InjectPress()      (menu buttons)
- `select:<LDL path>,<index>` -> aui_ListBox::SelectItem()  (ADDED 2026-07-24)
- bare name           -> g_slicEngine->RunUITriggers()  (in-game SLIC uitriggers)

`CTP2_LISTBOX` is declared `atomic true`, so list ROWS and its SCROLLBAR have no
addressable LDL path -- `press:` cannot reach them and clicks cannot either.
Index selection is the ONLY way to pick a list row, and it needs no scrolling.

**Verified headless walk to the MoM scenario** (uiwalk, window off-screen):
```
esc,esc                                   -> main menu
press InitPlayWindow.NewGameButton        -> New Game
press SPNewGameWindow.ScenarioButton      -> Scenario Selection
select ScenarioWindow.AvailableListBox,3  -> The Masters of Magic Mod
press ScenarioWindow.LoadButton           -> MoM pack contents
```
Top-level pack order: 0 Apolyton, 1 Alexander the Great, 2 Sieben Samurai,
3 **Masters of Magic**.

**HAZARD: aui_ListBox::SelectItem has NO bounds check.** `select:...,4` crashed
the game outright (0xC0000005). Guard the index before injecting.

**Attribution discipline:** diff consecutive screenshots to infer what a step did,
and treat ONE observed change as a hypothesis, not proof. A row-highlight was
attributed to a click here; a controlled rerun (base state byte-identical to
unselected, 4 further clicks inert) disproved it. Byte-identical successive
screenshots = the input never landed, or a modal ate it.

## [PROCESS - CONFIRMED WORKING] Headless verification: preflight the binary, then build golden checkpoints (2026-07-24)

**The bug that burned five days was never SLIC — it was a stale binary.**
`build.bat` builds ONLY `Configuration=Final-SDL`, which produces `ctp2.exe`.
`ctp2-dbg.exe` is the `Debug-SDL` artifact and `build.bat` NEVER refreshes it.
Meanwhile `uiwalk.py`'s `EXE_CANDIDATES` is dead code: launching delegates to
`run-ctp2-dbg-crashcapture.ps1`, whose default order prefers `ctp2-dbg.exe`, and
which re-stages that exe from `H:\Games\civctp2\ctp2_code\ctp` on EVERY launch
and restores backups on exit — silently clobbering any manual `cp`. So every
headless run executed a Jul-22 binary with none of the changes under test, and
the "crashes" observed were the old bugs in the old build.

FIX (landed): `uiwalk.py` gained `preflight_exe()` — it resolves the exe that will
ACTUALLY launch and aborts unless a marker string is present in it
(`--marker MagicMenu`, `none` to skip), and threads `-PreferRelease` into the
launcher so `ctp2.exe` (the one build.bat refreshes) wins. `--use-debug-exe` opts
back into Debug-SDL. Sample preflight line:
`[preflight] launch candidate: ...ctp2.exe (16,468,480 bytes) / marker 'MagicMenu': FOUND`

**RULE: never trust "I rebuilt it" — assert a marker string in the launched exe.**

**METHOD (adopt for all in-game verification): incremental golden checkpoints, not
one big end-to-end walk.** Get ONE small state verified headless, freeze it as a
steps JSON + golden, then extend from there. First checkpoint landed and green:
`steps/checkpoint_main_menu.json` (wait -> esc -> wait -> esc -> wait_stable ->
shot -> assert vs `goldens/main_menu.png`) => `main_menu_check 1.000 0.90 PASS`,
exit 0, run headless with the window off-screen.
Command: `python uiwalk.py --run steps/checkpoint_main_menu.json --save none`

**Harness gotchas that each cost real time:**
- `esc` while in-game opens the **modal Options window**, which swallows every
  later key (console, `/reloadslic`, hotkeys). Diagnostic signature: all
  subsequent screenshots are BYTE-IDENTICAL. That means "a modal ate the input",
  NOT "nothing happened". Do not send a speculative `esc` to "clear popups".
- `assert`'s `golden` field must NOT include `.png` — uiwalk appends it
  (`GOLDENS / f"{step['golden']}.png"`), else you get `main_menu.png.png`.
- `VK` map lacked the console key; added `apostrophe` (VK_OEM_7) + tilde/minus/equals.
- Window is stashed off-screen at -32000,-32000 (`_stash_offscreen`;
  `UIWALK_VISIBLE=1` overrides). `PrintWindow(PW_RENDERFULLCONTENT)` captures fine
  off-screen, but the `mss` desktop-grab fallback and `--global-input` do NOT —
  they need the window on-screen, and off-screen they yield black/garbage that
  looks exactly like "the UI never appeared".
- `wait_stable` is pixel-EXACT identity and silently degrades to a plain wait on
  timeout (no error).
- `save/games/uiwalk_start` is a **MoM** save ("Tribes of Life"), not vanilla —
  boot with `--save uiwalk_start` to skip the crash-prone New Game menu walk.
  Saves cache compiled SLIC, so edited .slc needs `/reloadslic` (apostrophe
  console) — or start a NEW game, which compiles fresh.

**STANDING OPERATING RULE: Claude launches the game and drives the test; the user
verifies nothing by hand, and should not have to see the window.**


## [CONFIRMED WORKING] SLIC messages display in-game — the missing half was segments (2026-07-17)

USER-CONFIRMED: the turn-1 "sphere-magic SLIC layer online" popup renders in a new
MoM game. The display path (Message -> messagebox segment -> scen_str string) is now
proven end-to-end; blessings + magic-power popups ride the same plumbing.

Three defects stood between "SLIC verified clean" and a visible message — all the
same root lesson: **SLIC has ONE flat global namespace** (handler names, messagebox
names, and ID_-stripped string keys all resolve through the same symbol table).

1. **No messagebox segments existed.** Message(player,'Key') requires 'Key' to be a
   DEFINED SEGMENT (slicfunc.cpp Slic_Message: SFN_ERROR_NOT_SEGMENT otherwise —
   silently, no dialog). scen_str keys alone display nothing. Fix: 7 messagebox
   blocks in mom_msg.slc (base form: Show(); Text(ID_KEY); MessageType optional).
2. **String key == segment name -> "X is not a string variable" SLIC Error at load.**
   slicif_find_string strips ID_ and GetOrMakeSymbol()s the rest; if that symbol is
   already a segment, compile errors. Fix: string keys live in their own namespace
   (MOM_MSG_*).
3. **Messagebox name == handler name -> load-time CRASH (0xC0000005/0xC000041D in
   setup, mimics the intermittent!).** scenario.slc's BeginTurn handler 'MomSlicAlive'
   + messagebox 'MomSlicAlive' = duplicate segment definition. Fix: messagebox renamed
   'MomMsgSlicAlive'. RULE: before adding any named segment, grep all slc for the name
   (uniq -d over handler+messagebox names).
- Diagnosis rule sharpened: TWO consecutive "intermittent-looking" setup crashes right
  after a SLIC edit = the edit, not the intermittent.
- uiwalk hardening landed en route: crashcapture-wrapper launch, SDL focus spoofing,
  window re-resolve, GlobalInput foreground workaround (ALT tap), retry-once-on-
  intermittent. Menu automation needs --global-input (real cursor: aui polls
  GetCursorPos; PostMessage clicks are invisible to menus) — get user OK first.

## [CIV EXCLUSIVITY] Sphere-home gating: tribes now own their rosters (2026-07-17)

The repeated user requirement ("separate your civilizations") is now mechanical, not
curatorial. Architecture = the LotR source idiom, done deliberately:

- **mod_policy `sphere_home_exclusivity`** (SMM on, MoM off): generator creates 5
  unresearchable ADVANCE_HOME_<SPHERE> (self-prereq + GLHidden + GoodyHutExcluded)
  and wires `Prerequisites ADVANCE_HOME_<X>` onto all 25 sphere-ladder advances.
  Ladders become walkable ONLY by the tribe holding the home.
- **SLIC grant** (generator-emitted `mom_sphere_home.slc`, included from
  scenario.slc): BeginTurn + per-player latch grants each tribe its home by NUMERIC
  player index (1 Life .. 5 Chaos — the established scenario contract). GrantAdvance
  (player, AdvanceDB(...)) is engine-verified (slicfunc.cpp) and BYPASSES prereqs —
  self-prereq blocks research, not grants. Non-tribe civs get no home → pure
  human/neutral roster.
- **Whitelist rule**: SLIC-granted advances (ADVANCE_HOME_*) must be exempt from BOTH
  the sever pass (else the wiring is severed on regen 2) and the closed-set
  propagation (else all 5 ladders + rosters go hidden). "Unresearchable" ≠ "closed"
  when SLIC grants it.
- **Merge clobber trap**: base donates mod_policy.json on EVERY re-merge — flags set
  in the merged dir silently vanish. merge_control_planes gained `--policy-set
  KEY=JSON` (use it in the documented re-merge command).
- Also this wave: H. Warriors = HOBGOBLINS (user-confirmed) → chaos; theme-aware
  proxy buckets (donor icon classified by its own name's sphere — no more dragon
  Engineers); UNIT_*_SUMMARY backfill (529 SMM / 55 MoM, raw-ID box fix); art-matcher
  pedia token bug ('06warriorlarge' glued suffix); 3 era-leak units genre-masked
  (Biplane, Flying Fortress, Eisenhower); MoM resynced + validated.
- **Playtest contract**: exclusivity is SLIC → NEW GAME only (save-cache), and the
  human player's sphere = their PLAYER SLOT (1-5), not the civ name they picked.

## [GL HYGIENE] Closed-gate content must be GLHidden — dormant ≠ invisible (2026-07-16)

GL screenshot showed Angmar H1..H4 + faction variants as browsable dead records with
wrong art and empty prose. Unbuildable (gate closed) does NOT remove a unit from the
Great Library index — that's a separate flag.

- **New generator pass** (after the base auto-hide): compute the transitively CLOSED
  advance set — self-prereq roots, propagated over AND-semantics Prerequisites (any
  closed prereq closes the advance) — then GLHidden+GoodyHutExcluded the closed
  advances and NoIndex+GLHidden every unit whose EnableAdvance is closed. SMM: 266
  advances + 291 units hidden; MoM byte-gate strict no-op. Works IN-PLACE (fixpoint
  reads current self-prereqs; no full rebuild needed).
- Discriminator that matters: a unit the sphere pass re-gated (e.g. Archer Orcs →
  Chaos ladder) is OPEN and stays visible — the junk test is "gate unreachable",
  not "name looks like junk".
- Parser gained `UnitsFile.block_text(ident)` (brace-walk accessor).
- **Art batch 2**: the remaining fugly surface = VISIBLE units wearing proxies (114
  found). ~74 curated aliases added (shared art across siblings per the MoM
  shared-icon precedent): orc line → HoMM orc art, medieval infantry → knight art,
  ships → carrack/galleon, Cleric → Monk, Necromancer → LichePriest. 159/477 mapped
  total. Spot-check before ship caught nothing this round (3/3 good).
- STILL OPEN: aom era-leaks visible in roster (Biplane, Flying Fortress, 'Dwight
  Eisenhower') — epoch→age squash (epoch_age_map caps AGE_THREE) let them past the
  era gate; they're genre_mask candidates for the next re-merge. Collapse decision
  (52+21 candidate groups) still pending user review.

## [ART PASS v1] Real unit icons from CoMM3: 85 HoMM portraits replace proxies (2026-07-16)

User verdict on proxy art: garbage. First real-art slice shipped same session.

- **Pipeline**: `build_unit_icon_art.py --csv <csv> --archive CoMM3.7z --out art/pictures`
  → matches units.csv names to CoMM3 art (token matcher + curated alias table, e.g.
  Phoenix→PheonixRecolor [sic], Treefolk→Treeman, Lich→UndeadLiche, Elf→Elven_Bowman),
  renders CTP2 ICON TGAs, writes the reviewable `csv/unit_art_map.csv` staging sheet
  (existing rows never overwritten). `assign_proxy_art.py --art-dir` installs real art
  BEFORE the proxy pass. Durable home: `Scenarios/smm/art/pictures/` (git-tracked).
- **ICON format ground truth** (from shipped files, NOT the 0x21 helper): 160x120,
  TGA type 2, 16-bit RGB555 ((r>>3)<<10|(g>>3)<<5|(b>>3), little-endian), BOTTOM-origin
  desc 0x00, no footer, exactly 38418 bytes. desc is per texture family — read the
  real files first.
- **Two source kinds**: Civilopedia `*Large.pcx` portraits (cover-crop) and unit-dir
  FLC first frames via ffmpeg (chroma-scrub magenta/green → bbox-crop → fit-pad;
  WITHOUT the bbox crop an FLC icon is a dot in a black field — observer spot-check
  caught it). Always decode-and-LOOK at N samples before shipping art.
- v1 coverage: 85/477 (57 pedia + 28 flc), fantasy core (homm2/midgard) first;
  unmapped units keep proxies. Extend by editing unit_art_map.csv + `--force`.

## [FIXED — new defect class] Severed unreachable-gates rootify: "H units buildable" + two-pass convergence (2026-07-16)

User playtest: starting civ could build "H <faction>" units (56 LotR hero slots, wearing
hobgoblin proxy sprites). Root-cause walk surfaced a defect CLASS plus a pipeline rule.

- **Source idiom**: mods gate scenario-granted content behind an UNREACHABLE prereq
  (LotR racial advances + Hextapul + AoM governments all prereq
  ADVANCE_GAIA_CONTROLLER; the source's SLIC grants them per civ). 25 merged advances
  carried such gates.
- **Defect**: the generator's fantasy-tree isolation pass severs prereq edges pointing
  at foreign (non-control-plane) advances. When ALL of an advance's prereqs were
  foreign, severing promoted it to a FREE RESEARCHABLE ROOT (Hextapul: AGE_ONE, 600)
  — silently un-gating its whole downstream family (56 heroes, faction trees).
- **Fix (ctp2_generator.py sever loop)**: if severing removed every prereq the advance
  had, re-gate it with the engine-sanctioned self-prerequisite (Advances.cpp:498
  CanResearch=FALSE; block stays in DB, refs resolve). SMM full rebuild: 74 edges
  severed, **38 advances kept closed** (25 gaia-gated + 13 more). MoM byte-gate: change
  is a NO-OP on MoM (verified via stash A/B regen).
- **The state trap**: the sever fires ONCE (first generation from a fresh base); later
  in-place regens see already-severed blocks. Data fixes at this layer need the FULL
  rebuild (rm scen0000 → copy base → proxy art → generator), not an in-place regen.
- **Two-pass convergence rule (pre-existing, now documented)**: after a FULL rebuild the
  first generator pass is NOT the fixed point — advance costs are scaled from pre-sever
  prereq counts, AdvanceLists/gl ordering settles on pass 2. **Run the generator TWICE
  after any full rebuild** (pass 3 = pass 2, verified byte-identical). In-place regens
  on a converged tree are stable in one pass.
- Both trees resynced + validated: live MoM scen0000 had ALSO drifted (missing the
  committed coastal-settle MovementType fix!) — regenerated to fixed point; SMM fully
  rebuilt + converged; validate_scenario passes on both.

## [VERIFIED + 2 AUDIT SURFACES] SMM 7-source merge: collapse layer confirmed, ledgers added (2026-07-16)

Full verification pass on the in-flight 7-source merge (base/homm2/midgard/crusades +
new cradle/aom/lotr via the ctp2-native importer): 591 advances / 539 units.

- **What "collapsing" actually is (precision matters):** the union layer
  (`merge_control_planes.py`) is a DETERMINISTIC first-wins union on sanitized name +
  `tag:code` namespacing — no LLM in the mechanical pipeline. The REDUCE is the curated
  staging sheets (genre_mask, unit_factions) edited between merge passes. The skill's
  "not naive first-wins" describes the whole workflow, not the union primitive.
- **Verdict: the mechanical layer works.** Gates run and PASSED: (1) validate_scenario
  on live scen0000, exit 0; (2) merge determinism — scratch re-merge byte-identical to
  live csv for advances/improvements/advance_code_map, and byte-identical for
  units.csv + unit_factions.csv after replaying assign_unit_factions over the curated
  sheet; (3) generator determinism — two independent scratch regens byte-identical.
  Referential integrity: 0 dangling prereq/unit/gate/improve refs, 0 dup idents,
  0 masked base rows (f978fd5 protection holds).
- **STALE-TREE TRAP (new gate habit):** live scen0000 had drifted from the csv in 5
  files — incl. aidata/AdvanceLists.txt missing ALL 473 merged advances (AI would
  never research them) and Advance.txt costs. A tracked gamedata file being "recently
  modified" is NOT proof the tree matches the current csv+generator — the regen
  byte-diff is. Fixed by regenerating live scen0000 (now matches verified scratch,
  validate passes).
- **New audit surface 1 — `csv/collision_ledger.csv`:** merge_control_planes.py now
  persists every first-wins-dropped row (dimension, name, kept/dropped source, code).
  SMM: 788 drops (416 advances / 266 units / 106 improvements, 0 code-map conflicts).
  Deterministic across runs.
- **New audit surface 2 — `csv/collapse_candidates.csv`:** new tool
  `audit_collapse_candidates.py --csv <dir>` derives faction-suffix tokens FROM the
  data (trailing word whose removal lands on another entry's name, ≥2 hits), stems,
  groups. SMM: 52 advance groups (Archery ×5, Architecture ×4 …, mostly lotr
  per-faction variants vs cradle/base) + 21 unit groups (Hoplite/Legion/Spearman ×4
  cross-source). AWAITING USER DECISION: collapse vs keep — nothing collapsed yet.
  Known limit: plural stems not unified (KNIGHT vs KNIGHTS are separate groups).
- Deferred (user-decided): epoch_age_map still caps at AGE_THREE (Hellas design pass).

## [GATE + 2 FIXES] SMM first-playtest failures: generator exit-0 is NOT a gate (2026-07-15)

Two in-game failures right out of the gate on the merged Super Magic scenario, both
foreseeable data-defect classes discovered via live dialogs — the exact anti-pattern the
quality-gates rule forbids. Both root-fixed + a mandatory gate added (commits 7e62afb,
531376e).

1. **Engine reserved-token collision**: a unit literally named "Sprite" → id
   `UNIT_SPRITE` — a tokenizer KEYWORD (Token.cpp g_allTokens, sprite-file format
   tokens). StringDB lexes ids through the tokenizer → "Missing string id" →
   scenario-load exit. Fix: renamed source unit (Faerie Sprite); merge tool refuses
   any UNIT_/ADVANCE_/IMPROVE_ ident in `engine_reserved_tokens.txt` (all 76 keywords
   extracted from engine source).
2. **Unsanitized sprite names**: `_pick_sprite`'s fallback used a bare space-replace,
   so "Water/Air Elementals" leaked `SPRITE_WATER/AIR_ELEMENTALS` into Units.txt +
   newsprite.txt → "newsprite.txt:140: Expected integer" dialog. FOUR such names
   (the dialog only shows the first). Fix: fallback uses sanitize(); MoM regen
   byte-gate re-verified.
- **THE RULE**: every generated scenario runs `validate_scenario.py --scenario <dir>`
  BEFORE playtest — newsprite grammar, ident charset, reserved-token scan, gl_str
  grammar. Battery-proven: catches all 4 defects on the broken tree, passes working
  MoM, passes the fixed SMM. Generator exit-0 only means the PYTHON ran; the engine's
  parsers are the real contract.

## [PIPELINE] Universal mod encoder: civ2 → xlsx/csv control plane → ctp2, proven on HoMM2 (2026-07-15)

Commits d213155 + a60a147. The MoM pipeline is now a reusable encoder: any civ2 mod →
per-dimension csv/xlsx control plane (image cell indices transcribed) → ctp2 scenario.

- **Engine/policy split**: 58-item inventory (`specs/universal-encoder-policy-inventory.md`)
  classifies everything in ctp2_generator.py. Round 1 moved all module-level policy into
  9 per-mod files in the csv dir (mod_policy.json + tileimp/order/concept masks,
  gl_text_rewrites, advance_code_map, stub_advances, governicon_fallback,
  advance_cost_bands). A mod = one csv dir. **Round 2 (commit 1c33df1) finished the
  split**: all embedded main() literals extracted — Enchanted Road remap family
  (db_text_swaps/tileimp_block_swaps/gl_section_overrides.csv with set/replace/pop
  rows), sprite/size pick heuristics (sprite_pick_rules.csv, ordered rule evaluator),
  unit stat scaling + roles + settler category + GL branding (mod_policy.json),
  UNIT_SETTLER/PEASANTS verbatim blocks (unit_block_overrides.csv). Both rounds
  byte-stability-gated; only truly ENGINE items remain in code (see inventory).
- **Entry points**: `encode_civ2_mod.py --mod-dir <civ2 mod> --out <csv dir>` (stage 1),
  then `CTP2_GENERATOR_CSV_DIR=<csv dir> CTP2_GENERATOR_SCENARIO_DIR=<scen dir>
  CIV2_MOD_BMP_DIR=<mod dir> ctp2_generator.py` (stage 3). xlsx round-trip:
  `export_mod_workbook.py` ⇄ `sync_excel_to_csv.py` (all sheets, header-drift refusal,
  --check mode, newline/encoding preserved).
- **THE gate: regen byte-stability.** Baseline the generator into a scratch scenario
  (env vars), hash all files, re-run after every change, diff. Caught and fixed a real
  nondeterminism: set-iteration in _ensure_runtime_unit_gl_surfaces made
  gl_str/Great_Library churn between identical runs (sort before writing).
- **Dry-run discipline finds the universality gaps**: running the generator on an
  encoded FOREIGN mod (HoMM2Mod1.1) surfaced every hidden MoM assumption as a clean
  failure: unmapped prereq codes (fix: derive advance_code_map from the mod's own
  @CIVILIZE trailing-comment codes), hard-required wonders.csv/tileimp.csv (fix:
  graceful skips), workbook writing to the MoM path (fix: follow the active csv dir),
  stray prose lines inside @UNITS (fix: arity-based row validation).
- **Encoder fidelity check**: encode MOMJR and diff against the CURATED momjr_csv —
  advances 87/87 exact; every unit/improvement mismatch mapped to a documented hand
  decision (hero Mys gating, X-sentinel icon renames, wonders promoted to buildings).
  The mismatch list IS the curation ledger for a new mod.
- **Known limits (v1)**: wonders.csv block_text and players ctp2_* columns are hand-
  authored; terrain/goods/orders/concepts are KEEP dimensions; atlas geometry rows per
  mod (scaffolded from MOMJR's, extractor prefers the csv-dir copy).

## [FIXED — 5th fugly cause] Dropdown chrome AV: zfs-RIM surfaces fail every blit; loose-TGA override is the fix (2026-07-15)

The City-tab "muted tan strips with a beaded rope" fugly (city-name pulldown + MAYOR
pulldown) — the "next up" known issue recorded in 656ecab — is FIXED, user-confirmed.

- **Symptom**: both City-tab dropdowns showed flat tan with a knotted-cord line instead
  of the beige/gold dropdown chrome. NOT random rainbow static: the pixels were a stale
  slice of the tan parchment setup screen (upsg005/006 style, beaded border = the "rope").
- **Root cause**: dropdown chrome = 13 `uppd02*` images that exist ONLY inside
  pic555/565.zfs as RIM records (no loose TGAs anywhere, incl. Apolyton reference).
  `TargaImageFormat::LoadRIM` wraps the RIM bytes directly as the image surface
  (`LoadFileMapped`); **blitting those RIM-backed surfaces access-violates on every
  draw** (`DrawImages: blit FAILED (err=4) for image 'uppd02aX.tga' (surface 14x29)
  bltType=0 bltFlag=1`). The per-image SEH guard (f9a529266) contains the AV → the blit
  is skipped → chrome never painted → stale surface memory shows. Exactly the
  2026-07-10 rule firing: "skipping a paint = a fugly by another name."
- **Why it looked like data and wasn't**: all 3 documented data causes verified clean
  by bytes (DB double-load, TGA desc, CRLF), zfs archives structurally intact, RIM art
  decoded clean, zero load errors. 16af7c743's guess (missing upfg50-53) was a red
  herring — those were restored in f3ecf9e and are fine (they're the UNIT tab).
- **FIX (data-only, no rebuild)**: extract the 13 `uppd02*.rim` from **pic555.zfs**
  (555 = ARGB1555 = 16-bit TGA payload, no conversion loss), row-flip (RIM is
  top-down), write loose TGAs to `ctp2_data/default/graphics/pictures/` matching the
  proven upfg01 conventions: type 2, 16bpp, **desc=0x01, bottom-up rows, 8-zero-byte +
  `TRUEVISION-XFILE.\0` footer**. Loose TGA beats zfs RIM (`_access` check in
  `TargaImageFormat::Load`), and the normal TGA load path allocates a regular surface
  that blits fine. Chromakey magenta (31,0,31) survives 555→565 exactly.
- **Evidence recovery trick that cracked it**: the July-14 session's engine logs were
  rotated away, but the *conversation transcript jsonl* still contained the pasted log
  excerpt with the exact failing line. When a commit message cites "session logs",
  grep the transcript before re-instrumenting anything.
- **Rules**:
  1. **Any texture that lives only as a zfs RIM is one loose-TGA extraction away from
     a fix** — "caps come from zfs; not a data fix" (2026-07-11) was wrong: desc bytes
     can't be fixed in-archive, but a loose OVERRIDE bypasses the archive entirely.
  2. The uiwalk/user screenshot distinction that matters: coherent-but-wrong texture
     (stale screen slice) = paint never happened; rainbow noise = unpainted heap.
     Both are "surface never painted", different underlying memory.
  3. ZFS3 format (for future extractions): header `ZFS3 u32(ver) u32(fnlen=16)
     u32(entries/table=100) u32(total)`, tables at 0x1c chained by leading u32 next-ptr,
     entry = name[16] + u32 offset + u32 idx + u32 size + u32 time + u32 pad (36 B).
     RIM record: `RIMF u32(ver=1) u16 w,h,pitch,fmt(0=555,1=565)` + raw rows.

## [STATE + SCAN LESSON] Advance icons: canonical 11-cell design is CURRENT; a mid-session 71-repoint dedup was superseded (2026-07-15)

Ground truth measured 2026-07-15 (pixel md5 over decoded FirstFrame art of all 85
visible advances): **11 distinct images, 10 shared groups** — i.e. the canonical
advances.csv 11-category-cell contract from 656ecab, which the user accepted as
"working". Each magic school line (Chaos/Death/Life/Nature/Sorcery, 6 advances each)
shares its school image BY DESIGN; ditto the economy/military/civic/build groups.

- **History note**: mid-window on 07-14, a 71-repoint uniticon dedup (unique art per
  visible advance from the free pool) was built and verified — then superseded by the
  canonical-contract restore in 656ecab (generator rewires uniticon; contract = shared
  category art). If per-advance unique art is ever wanted again, do it durably: write
  art INTO the `ICON_ADVANCE_<X>.tga` files (generator forces uniticon Icon refs to
  those filenames — uniticon hand-repoints are regen-reverted, lessons 2026-07-14).
- **Durable scan lesson (keep)**: duplicate detection must key by **content hash
  ONLY** — keying by (md5, basename) hides same-content files under different names,
  which is exactly how generator-written school lines share bytes across
  ICON_ADVANCE_*.tga files. Decoded-PIXEL md5 beats file md5 (desc-byte/footer
  variance hides pixel identity).
- **Free-pool rule (keep, for any future repoints)**: candidate art = md5-group
  referenced by NO uniticon entry of any type — prevents advance-vs-building repeats
  inside the Great Library.

## [REGRESSION+FIX] generator regen reverted committed hand-fixes: sprite renumbering broke unit art; hero gating lost (2026-07-14)

The first generator regen in a while surfaced a whole CLASS of defect: **hand-fixes
committed directly to generated outputs get silently reverted on regen.** Two hits:

1. **Peasant (all custom units ≥95) showed wrong art.** The newsprite merge appended
   custom sprites in Units.txt encounter order with fresh sequential ids — but
   **sprite numbers are pinned to disk**: each id is baked into the GU<id>.SPR
   filename built by build_sprites.py (SPRITE_PEASANTS 104 ↔ GU104.SPR). The regen
   renumbered (Peasants 104→142) and every custom unit rendered another unit's
   sprite. FIX: merge now preserves the scenario file's existing custom name→id
   assignments verbatim and only appends genuinely new names (ctp2_generator.py
   newsprite block). Verified: regen name→id pairs == committed, zero drift.
2. **Hero flood at start returned.** Commit 73e7a6f gated the 9 champions
   (Ariel/Jafar/Rjak/Tauron/Serena/Freya/Alorra/Warrax/Malleus) behind
   ADVANCE_MYSTICISM by editing Units.txt directly; units.csv still said prereq
   'no' → regen flipped them back to WARRIOR_CODE (start-guaranteed = buildable
   turn 0). FIX: backported to the control plane — units.csv prereq 'Mys'
   (MOM_UNIT_ADVANCE already maps Mys→ADVANCE_MYSTICISM). Regen now reproduces
   the gating. (Spearmen gaining EnableAdvance WARRIOR_CODE is behaviorally
   neutral: WARRIOR_CODE is in START_GUARANTEED_ADVANCES.)

**Rule reinforced:** any fix applied to a generated .txt MUST be backported to the
CSV/control plane in the same session, or the next regen erases it. Audit idea:
before committing generator output, regen twice and require byte-stability.

## [PIPELINE-FIXES] advances extraction wired end-to-end; 3 defects fixed en route (2026-07-14)

First full `extractor → generator → audit` run for advance art (65 PASS / 0 FAIL):

1. **`civ2_sprite_extractor.py` CSV_SOURCES bug**: advances.csv was registered with
   `id_col="ident"` but that csv has no `ident` column (its identifier is `icon`)
   → every row silently skipped, "Total written: 0". A silent-skip on a missing id
   column is worth an explicit warning if it recurs elsewhere.
2. **Self-prereqs inflated advance costs**: `_retune_mom_advance_costs` counted
   `Prerequisites ADVANCE_X` lines including SELF-prereqs (the engine-sanctioned
   disable pattern) → disabled advances got prereq_factor 1.3 and blew the
   AGE_ONE ≤640 audit band (635→720 on first regen after the self-prereq commit).
   Fixed: prereq_count excludes self-references. Note: committed Advance.txt costs
   can be STALE relative to the generator (regen after any prereq/formula change).
3. **Audit lacked a retired-blocks whitelist**: the generator deliberately retires
   `IMPROVE_HIDE_SUPERMARKET` (removes the DB block, keeps uniticon/GL surfaces)
   — three audit checks (csv-coverage, dangling-icon, art-resolution) flagged it.
   Added `RETIRED_BUILDING_IDS` whitelist in mom_audit.py.

Post-state verified: 85 visible advances → exactly 11 pixel-distinct images,
each group homogeneous in cell_index (Chaos ×6 → cell 62 Forge of Chaos).

## [TOOLING] uiwalk — scripted in-game UI verification harness (2026-07-14)

`Scenarios/mom/tools/uiwalk/uiwalk.py`: launches the game deterministically, drives
it with scripted keys/clicks, screenshots checkpoints, template-matches regions
against goldens. Enables Claude-run verification instead of manual in-game checks.

- **Deterministic boot**: engine arg `-l"<save>"` loads a save AND auto-sets
  `nointromovie noshell` (civ3_main.cpp ParseCommandLine) — boots straight into the
  game. One-time setup: save the static turn-0 start as `uiwalk_start`.
  Other useful switches: `runinbackground` (render unfocused; profile has
  RunInBackground=No), `noshell`, `-s<scenario>`. Debug console commands exist but
  are `#ifdef _PLAYTEST` only — do not rely on them.
- **Keyboard nav beats pixel-hunting**: `keymap.txt` — `Ctrl+5` = Great Library,
  `A` = end turn, `Ctrl+x` = new game. The GL Search box gives deterministic
  navigation to any advance by typed name.
- **Goldens derive from the control plane** (`make_goldens.py`): advances.csv
  cell_index → Improvements.bmp cell → 160×120 canvas via the extractor's own
  helpers. Contract → expected pixels → in-game pixels, no blessed screenshots.
- **Input isolation (user requirement — never touch their mouse/keyboard)**:
  default backend PostMessages WM_KEY*/WM_CHAR/WM_*BUTTON* straight to the game
  HWND and captures via PrintWindow(PW_RENDERFULLCONTENT) — the game runs
  unfocused in the background, physical input untouched. SDL2 tracks modifiers
  from the posted VK_CONTROL events so Ctrl+5 chords work. `--global-input` is
  the explicit real-cursor fallback (pyautogui, FAILSAFE on) if PostMessage is
  ever ignored. `--record` only OBSERVES the user's clicks (GetAsyncKeyState
  polling), never generates input.
- Modes: `--run steps/gl_advances.json` (assert), `--baseline`, `--dry`,
  `--record` (logs user clicks as client coords until F12 — for path calibration),
  `--attach` (drive an already-running window), `--keep`.
- Teardown kills by recorded PID only. py310 already has pyautogui/mss/opencv/
  pygetwindow/pywin32. SLIC `LibraryAdvance()` etc. (slicfunc.cpp:2354+) remains
  the fallback for programmatic GL opening if synthetic input flakes.
- First walkthrough: `steps/gl_advances.json` — 8 anchor advances asserted against
  their category cells (Chaos Adept↔cell_62 Forge of Chaos, Death Adept↔46,
  Alchemy/Astrology↔44, Banking↔10, Nature Magic↔40, Future Technology↔66).
  Search-box coord (246,94) is provisional — calibrate with `--record` if needed.

## [ADVANCE-ICONS — CANONICAL CONTRACT] 11 category cells; the "11 distinct md5s" was the DESIGN (2026-07-14, corrects the entry below)

The canonical advance-art mapping is the **Excel control-plane contract**
(`mom_dimension_inventory*.xlsx` → `advances` sheet = live `advances.csv`
`cell_index`): **87 advances → 11 thematic category cells** of MOMJR
`Improvements.bmp` — 2 Barracks (military ×9), 7 Courthouse (governance ×7),
10 Bank (economy ×8), 30 Harbor (construction ×5), 40 Gaia's Shrine (Nature ×6),
44 Great Library (knowledge ×27), 45 Oracle (Life ×6), 46 Wall of Bone (Death ×6),
56 Eldritch College (Sorcery ×6), 62 Forge of Chaos (Chaos ×6),
66 Celestial Beacon (Future Tech ×1). Full table in
`tools/improvements_bmp_layout.md`.

- **"388 TGAs, 11 distinct images" was the DESIGN, not corruption.** Intra-category
  shared art is canonical — do not de-duplicate. The 2026-07-13 "surgical 27" fix
  and the 2026-07-14 momjr-port UPAP repoints both "fixed" the wrong thing; the
  extractor+generator run over the contract supersedes all of them.
- **User anchor decode**: "Chaos Adept = position 63 (row 8, column 7)" is
  1-BASED counting → 0-based flat cell 62 = Forge of Chaos (fiery swirl). Off-by-one
  between 1-based human positions and 0-based `cell_index` cost a full derivation
  detour (@CIVILIZE order, enables-chain, content-scored remap — all dead ends;
  `advances_cell_remap.csv` is superseded, kept for history).
- **`cell_index` dual-use is intentional**: the category value serves as both the
  art cell AND the generator cost-weight bucket. The `art_cell_index` extractor
  override (added today) stays as an unused, documented escape hatch.
- Points 2 (generator owns uniticon advance blocks), 4 (GLHidden), 5 (pre-extracted
  goldmines) of the entry below remain valid.

## [ADVANCE-ICONS] Improvements.bmp IS the tech sheet; cell_index is DUAL-USE; uniticon advance blocks are generator-owned (2026-07-14)

Supersedes the "Civ2 MOMJR has no per-advance portraits" claim in the 2026-07-13
entry below — user-corrected: **`H:\Games\civ2\MOMJR\MOMJR\Improvements.bmp` is
the advance art source.** Advances lift the cell of a related building/wonder
via `tools/momjr_csv/advances_cell_remap.csv` (`new_cell_index`; `civ_idx` =
`@CIVILIZE` order). Full geometry in `tools/improvements_bmp_layout.md`.

1. **`advances.csv` `cell_index` is dual-use** — `ctp2_generator.py` reads it as
   the advance **cost weight** (`csv_weights` → `_scaled_mom_advance_cost`).
   `update_advances_tier_a.py` set `cell_index = epoch*5 + category` for cost
   tiers, which collapsed art coords to 11 buckets — THE root cause of "388
   advance TGAs, 11 distinct images". Sheet coordinates now live in a separate
   **`art_cell_index`** column; `civ2_sprite_extractor.py` prefers it.
   `art_cell_index = 999` = deliberate skip sentinel (extractor's beyond-sheet
   path) — never put grid coords back into `cell_index`.
2. **uniticon `ICON_ADVANCE_*` blocks are generator-owned and ephemeral**
   (`ctp2_generator.py` ~3609): every `Advance.txt` Icon ref is forced to
   `ICON_ADVANCE_<X>.tga` if that file exists on disk, else `UPLG001.TGA`
   (the base DEFAULT placeholder). Hand-edits to advance uniticon lines are
   stomped on the next generator run. **Durable art = the CONTENT of
   `ICON_ADVANCE_<X>.tga`.** To pin art for an advance, write the art into that
   file, don't repoint uniticon.
3. **Remap quality**: 68/87 `new_cell_index` values are genuine; 19 are scorer
   misfires landing on empty grey cells (0, 35, 68–71) with degenerate scores
   ~24–26. Those 19 got `art_cell_index=999` and their desired art pre-seeded
   into `ICON_ADVANCE_*.tga` (Alchemy ← `CM2_UPAP010L`, University ←
   `CM2_UPIP053L`, Death/Sorcery tier ← unit stills, Chaos Magic ← its unique
   generated icon). The extractor scales cells to the 160×120 GL canvas itself.
4. **GL visibility = `GLHidden` flag in Advance.txt**: 255 DB advances = 85
   visible (complete momjr design set) + 170 hidden (base leftovers, WAW stubs,
   USER_DEF_TECH_A). The GL list starting at "Alchemy" (not "Agriculture") is
   how you know hiding works.
5. **Pre-extracted art goldmines** (user rule: pre-extracted only, no zip
   diving): `H:\Games\civctp2\Advance-Graph\pic555\` = 106 base+Cradle advance
   pictures as PNGs; `H:\Games\civctp2\ctp2_data\default\graphics\pictures\` =
   loose Apolyton-source TGAs (incl. CM2_UPIP/UPVP families). Normalize desc
   byte 17 → 0x00 on anything copied in (GL crash guard, entry below).
6. **The momjr port itself uses surrogates**: its uniticon borrows base art for
   fantasy techs (Chaos Magic ← Nuclear Power's `CM2_UPAP077L`; Astrology ←
   `UPAP104L`, which is Unified Physics' "theory box" — its text fields even
   alias `ADVANCE_THEORY_OF_GRAVITY_*`), and deliberately shares art across 7
   visible pairs (Alphabet+Writing, Bridge Building+Pottery, Ceremonial
   Burial+Pantheism, Currency+Trade, Map Making+Seafaring, Masonry+Sanitation,
   Mathematics+Mysticism). Don't "fix" those pairs as dupes.

Pipeline to apply sheet art: fix `advances.csv` → `civ2_sprite_extractor.py
--sheet advances` → `ctp2_generator.py` → `mom_audit.py` (39 PASS expected).

## [SLIC] Faction / scoping syntax — SUPERSEDED, see the B1a API Contract below
> Two earlier [SLIC] sections lived here (pre-2026-07-05). They asserted `p == TRIBES_X`,
> `player[p].civ`, and "never use `player[0]`" — **all three disproven in-game** — and are
> removed so this file no longer holds both the wrong and the right guidance. The canonical,
> load-time-proven contract is "[SLIC] B1a API Contract" near the bottom of this file:
> - `playerTurn` is undefined; the BeginTurn/event-local player IS `player[0]` (CORRECT, not
>   forbidden). Helpers take `int_t p`; callers pass `player[0]` in.
> - `TRIBES_LIFE..TRIBES_CHAOS` are civ-DB record names, NOT SLIC symbols. Faction check uses
>   the NUMERIC player index: `p == 1` Life, `2` Nature, `3` Sorcery, `4` Death, `5` Chaos
>   (player N = civ N). `player[p].civ` / `civ[p].ident` / `civilization[p]` do not exist.
> - Membership uses `CityHasBuilding(city, BuildingDB(IMPROVE_X))`; `AddGold`/`CreateUnit`
>   take the integer player index.
> - **Control-plane sync**: reflect any SLIC signature/handler change in
>   `tools/momjr_csv/slic_inventory.csv`, then regenerate `mom_dimension_inventory.xlsx` via
>   `tools/export_mod_workbook.py` (the CSV is the editable surface; the xlsx tab is derived).

## [FIXED] Great Library SourceList Crash (TGA Descriptor Byte Mismatch)
- **Symptom**: Intermittent crash when opening the Great Library (`SourceList::Initialize` / `SourceListItem`).
- **Root Cause**: The scenario directory contained a loose TGA file (`CM2_Upap001l.tga`) shadowing a base advance icon. This file had a TGA image-descriptor byte of `0x01`, while the base file (and the correct standard for loose scenario icons) requires `0x00`. The wrong descriptor byte causes the CTP2 engine to misread pixel data, leading to render corruption and a crash in the GL SourceList.
- **Resolution**: Removed/renamed the improperly formatted shadow TGA (`CM2_Upap001l.tga.BAD_FORMAT_BACKUP`). The engine now correctly falls back to the base `ctp2_data` version, which has the correct `0x00` descriptor byte.
- **Rule**: Never shadow base UI/advance icons with scenario TGAs unless absolutely necessary, and *always* verify the TGA descriptor byte (offset 17) is `0x00` for standard icons, or `0x01` specifically for GL background TGAs (`upfg500/501/502`, `uptg04e`).

# MoM (Civ2 → CTP2) — Lessons Learned

Running log of hard-won lessons. Newest sections at top. Companion to
`MOD_DIMENSIONS.md` (dimension map) and `tools/INTERCONNECTION_TRACKING.md`
(which file references which dimension).

---

## gamefile.txt is the authoritative load manifest — improvements = buildings.txt, NOT Improve.txt

`ctp2_data/default/gamedata/gamefile.txt` lists every record file the engine loads.
**Line 26 is `buildings.txt`; `Improve.txt` is NOT in the manifest — the engine never
loads it.** This is the root of the project-long "buildings.txt vs Improve.txt"
confusion:
- `ctp2_generator.py` authored MoM improvements into `Improve.txt` (a dead file), so MoM
  buildings never loaded and every SLIC/GL ref to them was undefined
  (`Symbol IMPROVE_BARRACKS is undefined`). mom's `buildings.txt` stayed pure AE base.
- Proof: **AE_Mod ships only `buildings.txt`, no `Improve.txt`, and works.**
- The two files use **different schemas**: `buildings.txt` (AE) = `EnableAdvance`,
  `ProductionCost`, `DefaultIcon`, `Description` (CamelCase, multi-line). `Improve.txt`
  (old CTP2) = `ENABLING_ADVANCE`, `IMPROVEMENT_PRODUCTION_COST`, `IMPROVE_DEFAULT_ICON`
  (UPPER_SNAKE, single-line). You cannot raw-append one into the other — convert fields.
- Fix: MoM improvements must be authored into `buildings.txt`. `validate_all_surfaces.py`
  now checks `IMPROVE_` against `buildings.txt` only, and its base-fallback surface is
  **scoped to gamefile.txt** (so it won't false-flag never-loaded files like Improve.txt).
- **Rule:** `gamefile.txt` is the source of truth for which files load. Any generator
  target NOT in gamefile.txt is dead. Cross-check generator outputs against it.

## AllinoneWindow (New Game setup) crashes can be intermittent

An access violation (`0xC0000005`) in `AllinoneWindow::Idle`/`SpitOutGameSetup` (the New
Game setup screen) recurred at session start (image load) and again later. Release-build
symbols in the crash dump are APPROXIMATE (nearest export, not the real function) — don't
over-read "WonderRecord/ConstRecord". When all reference surfaces validate clean, a
single **retry of the launch often succeeds** (it did here). Don't chase a clean build as
if it were a data bug.

## The 7 reference surfaces — validate ALL before launch (don't relaunch per error)

CTP2 validates entity references from MANY surfaces, not one. Discovering them one
launch at a time is the trap. `tools/validate_all_surfaces.py` checks every surface
against the live DBs and is wired into `ctpedit patch` (generator → `fix_gl_links`
→ `validate_all_surfaces` → audit). The surfaces:

1. **Data-file gating fields** — `EnableAdvance`/`ObsoleteAdvance`/`Prerequisites`/
   `AddAdvance`/`RemoveAdvance` → Advance DB; `UpgradeTo` → Unit DB. (e.g. "Cyber
   Ninja not found": `UNIT_SPY` upgraded to a base unit the build half-kept.)
2. **Great Library `<L:DATABASE_<TYPE>,<TOKEN>>` links** (all 10 dims). (e.g.
   "Desert Mountain" = `TERRAIN_BROWN_MOUNTAIN` link with an empty terrain.txt.)
3. **Great Library advance sections** `[ADVANCE_X_GAMEPLAY|HISTORICAL|PREREQ|
   STATISTICS]`. (e.g. "Drama not found": orphan advance GL section.)
4. **AI build lists / strategies** (`default/aidata/*.txt`).
5. **EndGameObjects.txt** (victory wonders/buildings/tileimps). (e.g. "The Solaris
   Project not found": missing file → fell back to stock requiring base wonders.)
6. **Base-fallback gamedata files** — any `ctp2_data/default/gamedata/*.txt` the
   scenario does NOT override is loaded from base and may reference replaced entities.
7. **SLIC entity symbols** — `UNIT_/IMPROVE_/ADVANCE_/WONDER_` in `*.slc` (runtime).
   (e.g. "Symbol UNIT_SHAMAN is undefined": Nature blessing spawned a missing unit.)

Rule of thumb: KEEP dimensions (terrain, governments, orders, concepts, goods, tile
improvements) use BASE content — never regenerate them from a structured CSV via a
"raw" importer (that wiped terrain.txt to 1 line). MoM dimensions (advances, units,
improvements, wonders) are CSV-authored; everything that references them (GL,
EndGameObjects, SLIC, build lists) must be authored/repaired to match.

### 🚨 TDD & Smoke Test Mandate
**Any error encountered during generation or runtime MUST be replicated as a failing condition in `validate_all_surfaces.py` (our smoke/unit tests).**
- When a change is made to fix an issue, the smoke test is the absolute authority on whether the fix worked.
- If the smoke test still triggers the same issue after the change, **the hypothesis for the fix was wrong**. Do not make excuses, do not blame cached files, do not stop until the smoke test passes.
- **Zero tolerance for shadow injections**: If the engine requires an entity to prevent a crash, it MUST be added to the Excel control plane. The generator must never silently inject base-game data post-CSV parsing. The control plane is the singular, undisputed source of truth.

---

## The two toolchains — know which one you're running

There are **two** generation front-ends and they are NOT interchangeable:

| Tool | Location | What it does | File layout |
|---|---|---|---|
| `mom_translator.py` | `modder_files/` | One-shot **wholesale replace** of 4 dimensions from Civ2 import | writes `buildings.txt`, reduced record sets |
| `ctp2_generator.py` (via `ctpedit.py patch`) | `Scenarios/mom/tools/` | **Control-plane driven** merge; idempotent; prunes/hides/syncs GL+uniticon | writes `Improve.txt`, full record sets |

**The control plane (`mom_dimension_inventory.xlsx` + `tools/momjr_csv/*.csv`) is the
source of truth.** `ctpedit.py patch all` is the canonical build. `mom_translator.py`
is a Civ2-import front-end whose output must still be reconciled by the control plane.

**Design rule (from the user):** MoM = *base records that don't conflict with the
fantasy genre* (qualitative pass over the control-plane records) **∪ Civ2 MoMJR imports**.
It is a **curated superset**, not a wholesale replacement.

### The whack-a-mole root cause
`mom_translator.py` *replaces* `Advance.txt` with only the ~95 Civ2 advances. But the
rest of the AE base (Great Library, uniticon, terrain, tileimp, AI data) still references
the full base set. CTP2 validates **every** cross-reference at load and hard-errors on the
first miss ("X not found in Y database"). Replacing a dimension wholesale orphans hundreds
of references. The old backup that actually launched had **278 advances** precisely because
it kept the base superset.

**Fix:** build with `ctpedit.py patch all` (the generator keeps/hides base records and
keeps the GL consistent), not by replacing dimensions wholesale.

---

## "X not found in Advance database" — it's the Great Library SECTIONS

Use the tools, don't grep blindly:
```
python tools/scan_interconnections.py advances ADVANCE_DRAMA
```
For an advance, the validated interconnection is the **Great Library entry-sections**
`[ADVANCE_X_GAMEPLAY|HISTORICAL|PREREQ|STATISTICS]` — NOT `uniticon.txt` (advances have
no icon-DB validation), and NOT only the `<L:DATABASE_ADVANCES,...>` prose links.

### Why pruning the GL sections does NOT work
`ctp2_generator._restore_missing_uniticon_gl_sections()` **re-adds** GL sections for every
`uniticon.txt` entry on every run. So deleting orphan advance GL sections is futile — they
come back. The generator's design is **keep base records, hide them** (mirrors how base
units get `GLHidden`+`NoIndex`), not delete them.

### The fix that stuck (now in `ctp2_generator.py`, after the advance restore pass)
Create **hidden stub advances** for every advance referenced by the GL (both section
headers and `<L:DATABASE_ADVANCES,...>` links, across `Great_Library.txt` AND
`WAW_Great_Library.txt`) that isn't already in `Advance.txt`. The existing `GLHidden` pass
then keeps them out of the player-facing tech tree. Result: `Advance.txt` 95 → 243, with
0 orphan advance sections/links. `ADVANCE_DRAMA` etc. now exist as hidden stubs.

`ModAdvance` only writes the `Advance.txt` block + `gl_str` display name — it does NOT
write GL sections, so stubbing advances does not duplicate GL prose.

---

## Units/Improvements GL sections are NOT load-validated like advances

AE base `Units.txt` has ~72 units but its Great Library references ~172 — and **AE_Mod
launches fine**. Therefore CTP2 does **not** hard-error on orphan unit/improvement GL
sections at scenario load the way it does for advances. Do **not** preemptively generate
stub units to "fix" 100+ orphan unit GL sections:
- `ModUnit` registers a GL section too, so stubbing would **duplicate** existing GL prose.
- The error class is unconfirmed for units; only advances were reproduced.

If a unit/improvement DB error ever IS reproduced at launch, diagnose with
`scan_interconnections.py` first to find the exact validated surface.

---

## Government / Anarchy science (original "tech never advances")

`GOVERNMENT_ANARCHY` in stock `govern.txt` has `MaxScienceRate 0` and `KnowledgeCoef 0.1`
→ you start in Anarchy and can NEVER research out of it. Set to `0.3 / 0.3`.
`govern.txt` is currently copied raw (no `governments.csv` row), so this edit lives in the
scenario `govern.txt` and survives generator runs. If `governments.csv` becomes the source,
encode it there instead.

---

## Tooling gotchas

- **Console encoding:** the `tools/*.py` print `⚠`/`→` (U+2026 etc.) and crash under
  Windows cp1252. Always run them with `PYTHONIOENCODING=utf-8`.
- **`crossref_audit.py`** expects the canonical file layout (`Improve.txt`, `feat.txt`, …).
  It fails on `mom_translator` output (`buildings.txt`, missing files). Run it only after
  `ctpedit.py patch all`.
- **`reg.load()` caches** (`schema_registry`/`ctp2_parser`): repeated `reg.load(rel)` returns
  the same object; `reg.save_all()` persists every cached object via `obj.render()`.
  `LibraryFile.render()` builds from `.sections`. WAW library is loaded separately via
  `_load_library_file` and must be saved explicitly with `_save_library_file`.
- **`apply_masks.py` does NOT clean `Great_Library.txt`** — it removes blocks from
  `Advance.txt`/`Units.txt`/`Improve.txt`/`Wonder.txt`/`tileimp.txt` + string tables only.
  It also only acts on records that EXIST in the data files; an orphan that lives ONLY in
  the GL is invisible to it.

---

## Scenario picker / launch hygiene

- **Custom picker art:** `packicon.tga` (pack root) and `scen0000/scenicon.tga` are the
  scenario-selection thumbnails. `mom_translator`'s copytree overwrites them with AE
  placeholders — it now preserves/restores them. The MoM custom art differs from AE's.
- **`scenario.txt`** is a plain 2–3 line text file (title / description), NOT KV. Overwrite
  it wholesale to re-identify the scenario; a regex replace silently no-ops on AE's format.
- **`packlist.txt`** is exactly 3 lines: name / description / scenario-count. Duplicate
  names across `mom/` and `mom_*/` make the picker show duplicate entries.
- **Don't keep two scenario dirs with the same packlist name** (`mom` vs `mom_`); rename
  stale ones.

---

## Feat.txt Integration (Lessons Learned)

**Purpose**: eat.txt defines mini-script effects triggered by the CTP2 engine or SLIC (e.g., EffectIncreaseProduction 5, SlicMessage "FeatGotConcrete"). These are typically tied to specific advances or building milestones.

**The Control Plane Mandate**: The control plane (CSVs) is the single gateway for scenario generation. Blindly passing through the base game's eat.txt violates this mandate, as it contains faction-specific feats (e.g., Egypt, Zoroastrianism) and advance/building dependencies that do not exist in the MoM mod, leading to broken or dead code.

**The Solution**: A generic translator (_translate_base_feats()) was implemented in ctp2_generator.py. It reads the base game's eat.txt and filters it against the MoM control plane:
- **Advance Check**: Feats named FEAT_ADVANCE_* are kept only if the corresponding ADVANCE_* exists in dvances.csv.
- **Building Check**: Feats containing Building IMPROVE_* are kept only if the corresponding IMPROVE_* exists in improvements.csv.
- Feats with no recognizable dependencies, or whose dependencies are fully satisfied, are kept. Others are dropped.

**Interconnections**: 
- eat.txt is tightly coupled to Advance.txt and uildings.txt (via Improve.txt).
- It also references gl_str.txt for display strings (e.g., Description str_ldl_0), though many base feats use a generic placeholder.

**Open Questions for Future Integration**:
1. Should we remap base-game feats to MoM-specific advances (e.g., mapping a generic "production boost" feat to an MoM custom advance) instead of strict keep/drop?
2. Should MoM define its own custom feats in a new eats.csv control plane file, rather than relying on filtered base-game feats?
3. How do we handle feats that depend on SLIC messages or events that are unique to base-game civilizations but have no MoM equivalent?

**Current State**: The generator now produces a valid, filtered eat.txt (9 feats kept) that strictly adheres to MoM's control plane dependencies, with no manual downstream patching.

---

## Unintegrated Changes Protocol (The \_unintegrated\ Directory)

**Problem**: The generator's "RECONSTRUCT FROM NOTHING" nuke phase (shutil.rmtree on \gamedata\ directories) aggressively wipes out any experimental, partially completed, or archived files (e.g., \_archived_slic/\). This causes valuable work-in-progress or deferred features to be lost in ancient git commits, making iterative re-approach difficult.

**Solution**: A dedicated \Scenarios/mom/tools/_unintegrated/\ directory has been established as the canonical holding area for:
- Archived SLIC modules (e.g., \mom_func.slc\, \mom_turns.slc\, \mom_city_effects.slc\)
- Partial CSV drafts or experimental dimension mappings
- Harness patches that require further debugging before control-plane integration

**Rules**:
1. **Generator Safety**: This directory is outside the nuke paths (\default/gamedata\, \english/gamedata\, \default/aidata\) and will **never** be automatically deleted by the generator.
2. **No Silent Deletion**: Files here must not be deleted without being moved to the active control plane (\momjr_csv/\) or explicitly documented as permanently abandoned.
3. **Promotion Path**: When a feature is ready, move its artifacts to the active harness, update \dimension_inventory.md\, and remove the file from \_unintegrated/\.

This ensures we can pivot architecturally without losing the breadcrumbs of what we were aiming to accomplish.

---

## [SPRITES] Invisible Unit Root Cause: Anim Transparency 0 (SOLVED 2026-07-03)
- **Symptom**: Unit banner renders on the map, body is invisible at EVERY zoom. Portrait fine. SPR structure valid, pixels decode fine.
- **Root Cause**: Each SPR anim block carries per-frame u16 transparencies used as blend alpha at draw time (`alpha = value << 3`). Per Activision's own script docs (Gu01.txt): *"0 is invisible, 15 is opaque"*. `Actor.h: NO_TRANSPARENCY = 15`; `pixelutils_Blend16` returns pure background at alpha 0. makespr.py's `pack_anim` zero-padded omitted transparency entries → every makespr.py-built unit drew at 0% opacity.
- **Trap within the trap**: `ANIM_TRANSPARENCIES 0` in GU scripts is a **flag** ("no explicit list"), not a value. Explicit lists are `ANIM_TRANSPARENCIES 1 { 15 15 ... }`. The fix belongs in the pad default (`pack_anim` pads with 15 now), not the templates.
- **Diagnosis without launching the game**: decode the MOVE-anim transparencies from any GU*.SPR — stock sprites all carry 15s.
- Spec: `Scenarios/mom/specs/spr-anim-transparency.md`.

## [SPRITES] makespr.py Achieved BYTE-FOR-BYTE Parity With makespr.exe (2026-07-03)
- **Golden fixture**: Kull's Cradle 5 Legion (`H:\Games\ctp2\16-makespr\16\` — inputs + Gu16.txt + makespr.exe-built GU16.SPR, 452,956 bytes). Full MakeSprite kit (MAKESPR.EXE, Cow example, GU00.txt template, docs): `H:\Games\ctp2\MakeSprite\` (source: http://www.ctp2.info/download/MakeSprite.zip).
- **Golden test**: stage inputs + GU16.TXT in a work dir, `python makespr.py -u 16`, byte-compare against Kull's GU16.SPR. Result after fixes: **IDENTICAL**.
- **Bugs found & fixed in makespr.py via the golden diff** (each was invisible to structural inspection):
  1. **Shadow stamp was GREEN not magenta** (`merge_shadow` white-bg branch): shadows encoded as opaque COPY runs instead of SHADOW runs → green/dark halo in-game. Magenta (255,0,255) packs to the shadow magic pixel in both 565 (0xF81F) and 555 (0x7C1F).
  2. **Alpha premultiply missing**: the original tool premultiplies EVERY pixel at load: `c = ceil(c*a/255)` (same ceil idiom as `spriteutils_AveragePixel32`). Full-frame feathered pixels carry premultiplied color; minis average premultiplied values. One premultiply at load reproduces both. (The Apolyton engine source's `RGB32Info` does NOT premultiply — the 1999 tool differs from the surviving source; the golden file is ground truth.)
  3. **Mini pipeline order**: exe quarters the PRISTINE image (ceil-average all 4 RGBA components INCLUDING alpha and transparent pixels' RGB), nearest-samples the shadow separately (aa=FALSE), then merges shadow into the mini and encodes. Partial averaged alpha ⇒ feathered runs in minis.
  4. **Single-facing actions (IDLE/VICTORY) read facing-4 files** (`GU16IA4.*`, `GU16VA4.*`), not facing-1. makespr.py now maps 1-facing actions to file digit 4.
  5. **`UNIT_SPRITE_ATTACK_IS_DIRECTIONAL`** tag (before the attack block) was unparsed → ParseError. Now parsed and written to the trailing `hasDirectional` u16 (`hasDeath` likewise now honors `UNIT_SPRITE_IS_DEATH`).
  6. **Shield points were hardcoded (24,24)**: parsed `UNIT_SPRITE_SHIELDPOINTS` values are now serialized (5 actions × 5 facings POINTs, enum order move/attack/idle/victory/work).
- **Input trap**: 24-bit RGB TIFFs (no alpha channel — e.g. the kit's own Cow sample) make every pixel opaque → no keying, ~14KB frames instead of ~2.4KB. makespr.py now warns. Proper inputs are 32-bit ARGB TIFF (tutorial: GIMP Select-by-Color → Cut on the GUblank template).
- **Art source lead for MoM units**: Civ3 "Conquests of Might and Magic III (CoMM3)" total conversion by tom2050 — https://forums.civfanatics.com/threads/conquests-of-might-and-magic-iii-comm3-epic.619720/ — has full HoMM3 creature unit graphics (candidate source for ZOMBIES/SPEARMEN/SWORDSMEN placeholder fixes).

**CANONICAL CONFIRMATION (2026-07-03)**: After the golden-parity fixes, the Peasants unit renders
correctly on the CTP2 map (body + banner, correct art, matching portrait) — verified in-game by
screenshot. The anim-transparency root cause and the makespr.py parity work above are the canonical
explanation and fix for the "invisible unit / empty sprite" class of bugs.

## [UNITS] Settler Retired; Peasants Are MoM's City Builders (2026-07-03)
- **Engine fact (gameinit.cpp:404, `gameinit_PlaceInitalUnits`)**: a new game spawns, as each
  player's starting units, the FIRST unit in the Units DB with `SettleLand`. There is no hardcoded
  "UNIT_SETTLER" — DB order + `Settle:` lines decide.
- **Design**: MoM has NO settler unit. UNIT_PEASANTS carries the full settle kit lifted from the AE
  base settler: `SettleCityType UNIT_CITY`, `SettleSize 1`, `Settle: Land/Mountain`, `Civilian`,
  plus a COMPLETE `UNIT_CITY` target block (the engine's settle order spawns UNIT_CITY; a truncated
  block missing terrain classes/flags can fail city creation silently, esp. with scenario SLIC off).
- **UNIT_SETTLER stays in the DB but retired**: `CantBuild`, no `Settle:` lines. Kept only to avoid
  dangling references (Great_Library/gl_str/tut2_main.slc) and DB index shifts — see the
  orphan-GL-section error class. Do not re-add its Settle lines or it becomes the starting unit again.
- **Settle runtime gates that fail SILENTLY with SLIC disabled**: (1) unit already moved this turn
  (needs unspent move points or first-move flag; MaxMovePoints 100 = any move exhausts it),
  (2) tile owned by another city's radius ("too close").

## [TECH] Empty Build List After First City = Starting Advances Don't Enable MoM Content (2026-07-03)
- **Symptom**: found first city → no units, no buildings available to build; fear of anarchy/zero-science start.
- **Mechanics (engine, AE build)**: starting techs come from `DiffDB.txt` `ADVANCE_CHANCES` blocks
  (one per difficulty; rows = `ADVANCE_X humanChance aiChance`; `Player.cpp` grants 100%-chance rows
  always). Starting government = first govern.txt entry whose EnableAdvance is HELD at start, else
  index 0 = ANARCHY (no science). MoM DiffDB already guaranteed ADVANCE_MONARCHY (anarchy escape ok).
- **Root cause**: the granted advances were all BASE techs (Toolmaking, Agriculture...) which enable
  ~nothing in MoM. MoM tier-0 hangs off **ADVANCE_WARRIOR_CODE** (12 units + 8 buildings incl.
  peasants). Not granted → empty build lists.
- **Fix**: guarantee `ADVANCE_WARRIOR_CODE 100 100` in every ADVANCE_CHANCES block; generator now
  injects all of `START_GUARANTEED_ADVANCES` (government + tier-0 enabler) via
  `_ensure_diffdb_start_government`. Keep the list in sync with the enabler histogram:
  `grep EnableAdvance Units.txt | sort | uniq -c`.
- **Note**: `EXTRA_SETTLER_CHANCE 1000000` in DiffDB gives the extra starting settle-unit; the engine
  spawns the first SettleLand DB unit, so post-settler-retirement these are Peasants.

## [BUILD-LIST] AE 'X' Sentinel Items Leaked Into Turn-1 Build Lists (2026-07-03)
- **Symptom**: build manager shows "Xpower Plant", "Xhydro Plant", "Xwomens Suffrage" etc. at start.
- **What X-items are**: the Apolyton pack's convention for REMOVED base-game improvements/wonders —
  kept in the DB under an X-prefixed name for index/reference safety. MoM's ingestion mistook them
  for MoM content (gl_str even says "is a Master of Magic city improvement") and gated them with
  the tier-0 advance (ADVANCE_WARRIOR_CODE), so guaranteeing that start tech surfaced them.
- **Fix (safe mask)**: stamp `ObsoleteAdvance ADVANCE_WARRIOR_CODE` on every `IMPROVE_X*`/`WONDER_X*`
  block — obsolete from turn 1 for all players, records stay in DB (no index shifts / dangling GL
  refs). Generator post-pass `_retire_x_sentinels()` keeps regens clean. 8 entries: 3 buildings
  (XPOWER_PLANT, XHYDRO_PLANT, XWOMENS_SUFFRAGE) + 5 wonders (XLIGHTHOUSE, XSTATUE_OF_LIBERTY,
  XWOMENS_SUFFRAGE, XAPOLLO_PROGRAM, XCURE_FOR_CANCER). Note buildings DO support ObsoleteAdvance
  in the AE engine (building.cdb:48) even though base buildings.txt never uses it.
- **Deeper cleanup (later)**: exclude X-prefixed idents at ingestion and register them in
  mask_state.json so apply_masks.py can remove them wholesale with GL scrubbing.

## [CONTROL-PLANE] 'HIDE X' CSV Rows Are Mask Directives, Not Content (2026-07-03)
- **Symptom**: a buildable improvement literally named "Hide Supermarket" in the build manager.
- **Root cause**: `momjr_csv/improvements.csv` row `999,HIDE Supermarket,...` means "hide the
  base-game Supermarket"; the generator ingested it as a MoM building named "Hide Supermarket"
  (cost 0, icon NOTHING) and even wrote GL text claiming it's a MoM improvement.
- **Fix**: generator skips rows whose name starts with `HIDE ` (or cell_index 999) as mask
  directives; existing phantom retired via ObsoleteAdvance (same safe-mask pattern as X-sentinels).

## [ART] Civ2 Sheet Extraction Rules That Survived Contact With Reality (2026-07-03)
- MoMJR Units.bmp: 64x48 cells, 10 cols; row0 = peasant(0), zombie(1), spearman(2), swordsman(3),
  phantom warriors(4)... backdrop = magenta + dusky purple (135,83,135) diamonds + green grid.
- **Backdrop classification**: a colour is backdrop only if it appears on the cell BORDER (>=4 px)
  AND covers >=3% of the cell. Naive exact-colour keying ate the spearman's spear (its highlight
  gray also touched the border via the shield). Component-size heuristics also failed (shaft grain
  merged with backdrop components).
- **Output TGA convention**: BLACK background (not magenta) — build_unit_sprite corner-keys it,
  which also removes the Civ2 1px black outline (as the manifest requires); magenta backgrounds
  leave a pink LANCZOS fringe on the compiled sprite.
- **Scale convention**: bbox-crop the figure and scale to ~116px tall on the 160x120 canvas,
  bottom-anchored at y=118 — matches the peasant's on-map mass (it fills ~97% of frame height).
- Cell indices + rules now recorded in momjr_csv/civ2_converted_graphics.csv (CONVERTED rows).

## [COSTS] MoM Improvement Costs Rescaled to AE Age Bands (2026-07-03)
- **Symptom**: buildings complete in 1 turn (raw Civ2 costs 4-60 in a CTP2 economy).
- **Fix**: `_retune_mom_improvement_costs()` in ctp2_generator — the missing sibling of the existing
  unit/wonder/advance retunes. Bands base buildings.txt ProductionCost by EnableAdvance age and maps
  MOMJR improvements.csv costs into them via `_scale_cost_into_band`. ALL csv rows feed the
  improvement specs (wonder rows >= 40 also emit IMPROVE_ blocks that show in the Buildings tab).
  Retired blocks (ObsoleteAdvance) skipped. Result: 270 (Barracks/Temple = base first-age floor)
  up to 3500; base first-age improvement band is ~[270..875], NOT starting at 525 (alphabetical
  sampling deceived; assert against the real band min).
- **Sprite extraction addendum (v6 rules)**: near-black figure pixels (r+g+b<=24) -> (16,16,16) so
  the baked Civ2 feet-shadow survives corner keying (tolerance 12); horizontal anchor = center of
  BODY columns (density >= 35% of peak) at canvas x=80 — full-pixel centroid or bbox lets thin
  protrusions (spear) drag the body off the selection axis ("body sits lower-right" symptom).

## [SLIC] Crash Signature: SLIC Debugger SourceList + Non-ASCII Bytes (2026-07-03)
- **Symptom**: silent crash at the game-setup screen. crash.txt stack: `AllinoneWindow::Idle` ->
  `SpitOutGameSetup` -> `SourceListItem(..., SlicSegment*, ...)` / `SourceList::Initialize` + `yy_nxt`
  (the SLIC lexer).
- **Chain**: `DebugSlic=Yes` in ctp2_program/ctp/userprofile.txt opens the built-in SLIC debugger
  (ui/slic_debug/sourcelist.cpp) whose ancient list UI access-violates while rendering sources when
  the lexer hits trouble. Trigger candidates that session: (1) scenario.slc contained UTF-8
  em-dashes in comments - the SLIC lexer is ASCII-only; (2) an EMPTY scenario-level tutorial.slc
  override (removing stock tut2 segments the engine may look up by name).
- **Rules**: .slc files must be PURE ASCII with CRLF, comments included (spec already said so; the
  violation was in a comment header). Retiring stock tutorial SLIC via an empty override is
  UNVERIFIED and parked (`tools/_unintegrated/tutorial.slc.phaseA-parked`) pending a clean bisect.
- **Diagnostics**: crash.txt + usercritmsgs.txt + logs/slicdbg.txt (per-segment parse dump when
  DebugSlic=Yes) are the SLIC triage trio.

## [SPRITES] Hot Points (47,72) Crash Scenario Load; (39,80) Loads Fine (2026-07-03, bisect-proven)
- **Symptom**: 0xC0000005 during scenario select, right after the unit-DB dump, no crash.txt.
  Reproduced 3x; bisect ladder (all SLIC parked = still crashed; GU92 hot points reverted = loads)
  proves the trigger was GU92.SPR built with hot points (47,72) — hot_y equal to the 72px frame
  height is the suspected edge (mechanism in the blitter unidentified; 80 > 72 is FINE).
- **Rules**: avoid hot_y == frame height; when nudging a unit down, prefer shifting the image
  within the 160x120 canvas over lowering hot_y toward 72. SLIC files were fully exonerated —
  the parked Phase A files can return unchanged.
- **Bisect discipline that solved it**: one variable per launch; evidence = civ3log tail +
  slicdbg.txt mtime + WER/event logs; timeline via file mtimes vs. session times.

## [AI-CRASH] HYPOTHESIS UNDER TEST — Guaranteed Start Tech Exposes Turn-0 AI Scheduler Crash (2026-07-03)
Following AGENTS.md "Hypothesis Discipline".
- **Hypothesis**: guaranteeing `ADVANCE_WARRIOR_CODE` at game start (DiffDB
  ADVANCE_CHANCES, commit bfdd322) is the FIRST time the AI has a full MoM buildable
  roster at turn 0, exposing a latent crash in CTP2's goal Scheduler while it
  evaluates MoM units. Evidence: crash log (civ3log000, 17:58 run) ends at line 641
  immediately after `ASSIGN POPULATIONS ... elapsed 0 ms` (last step of AI begin-turn
  management) with the fault in the next phase (Scheduler/Goal frames in the stack);
  the Governor was scoring `List 5 Best unit: Peasants`, `List 13/14 Best unit: Warrax`,
  and `Best settler unit: Peasants needed: -2` (malformed negative count). Before today
  the turn-0 AI had ~nothing buildable and never crashed — matches "which was new."
- **SLIC EXONERATED for this crash**: all four .slc files were PARKED
  (tools/_unintegrated/parked/) when this crash occurred; gamedata held only
  tut2_main.slc. SLIC removal did NOT stop the crash.
- **Test**: remove ONLY `ADVANCE_WARRIOR_CODE` from all 6 DiffDB ADVANCE_CHANCES blocks
  (keep ADVANCE_MONARCHY — it enables no units/buildings, just anarchy escape).
- **Prediction**: TRUE -> turn-0 AI crash stops (AI has empty roster again, as before).
  FALSE -> crash persists -> next rollback = buildings.txt cost rescale, then X-sentinel
  retirement.
- **Confirmation bar (INTERMITTENT bug)**: one clean launch proves NOTHING — the prior
  identical-file run played 10 turns before this run crashed at turn 0. Require **3-4
  consecutive games reaching turn ~15 with no AI crash** to accept.
- **If confirmed**: real fix is HARDENING MoM AI unit data (the `needed: -2` settler
  path / Warrax role attributes in UnitBuildLists.txt + unit AI flags), NOT permanently
  removing the start tech (which reintroduces the empty-build-list bug).
- **Result**: PENDING user playtest.

## [SPRITES] Uniform Hot-Point Rule — Auto-Anchor From Figure Geometry (2026-07-04)
- **Problem**: peasant (GU104) centered on its tile but spearman (GU92) sat upper-right, and manual
  per-unit hot-point tweaking (39,80)->(50,68)->(63,62) never converged (non-uniform, non-reproducible).
- **Root cause (data-proven)**: a unit centers when its hot point equals (figure_centre_x, feet_y-16).
  The peasant satisfied this by luck (template default 49,54 ~= its figure); the spearman's figure
  centre was 41 with feet at 70, so the correct anchor was (41,54) — nowhere near the hand-tuned values.
  CTP2 anchors a unit at its lower shin (feet-16), not its feet, so it straddles the iso tile diamond.
- **Uniform fix**: `build_unit_sprite.py` now DERIVES the hot point from each figure's bbox
  (`hotpoint_from_bbox`: hot_x = centre-x, hot_y = feet_y - FEET_TO_HOTPOINT=16). --hot-x/--hot-y are
  now OVERRIDES (default AUTO). Verified: peasant/zombie/spearman/swordsman all land at dx~0, dy=-16.
- **Rule for all future MoM unit sprites**: never hand-tune hot points; the figure's on-frame geometry
  determines the anchor. If a unit looks off, the figure is mis-placed in the frame (fix extraction),
  not the hot point.

## [FIXED] Fuglies: Improvement/Wonder Double-Load (2026-07-04) — THE root cause
- **Symptom**: rainbow-static ("fuglies") where the city-name renders — Build Manager city
  selector AND the control-panel unit/city name banner. Game otherwise fully playable.
- **Root Cause**: **24 concepts existed as BOTH an `IMPROVE_<X>` block in buildings.txt AND a
  `WONDER_<X>` block in Wonder.txt** (GREAT_LIBRARY, ORACLE, THE_PARTHENON, GNOME_TREASURY,
  GAIAS_SHRINE, …). The engine loads the same concept into two databases -> conflicting DB
  indices -> Build Manager render corruption that bleeds onto the shared name-banner surface.
  This is the SAME class as commit 7afc935 (the Improve.txt + buildings.txt double-load), in a
  new form: the generator emitted an `IMPROVE_` block for wonder rows (improvements.csv
  `cell_index >= 40`) on top of the `WONDER_` block. buildings.txt had 46 IMPROVE_ blocks;
  24 of them were wonder twins.
- **How it was found**: `git log --grep=fugl` — the commit history names the exact mechanism
  ("duplicate/conflicting building indices that corrupted the Build Manager render"). ALWAYS
  read the fugly commit messages first.
- **Resolution**: (1) removed the 24 duplicate `IMPROVE_<wonder>` blocks from buildings.txt
  (concept survives as its WONDER_ block); 46 -> 22 real improvements; `IMPROVE_ ∩ WONDER_ = ∅`.
  (2) fixed the generator (`ctp2_generator.py`, improvements.csv ingestion) to SKIP wonder rows
  (`cell_index >= 40`) when emitting IMPROVE_ blocks. (3) reconciled dangling refs to the removed
  GAIAS_SHRINE (BuildingBuildLists.txt happiness/small-city lists -> IMPROVE_TEMPLE; tut2_main.slc
  'TBuiltTemple' handler -> IMPROVE_TEMPLE, its intended target). (4) added surface-8 guard to
  validate_all_surfaces.py: no ident may be both IMPROVE_ and WONDER_.
- **Rule/Prevention**: a concept is EITHER an improvement OR a wonder, never both. The
  improve/wonder-overlap guard is now launch-blocking. See [[mom-gamefile-manifest]].

### The fuglies are COMPOUND — three co-occurring causes, all in `git log --grep=fugl`
Resolving the banner took fixing ALL THREE; any one left in place kept the static. Do not
stop at the first cause found:
1. **DB double-load** (this entry / 7afc935): a concept present as both IMPROVE_ and WONDER_
   (or Improve.txt + buildings.txt) -> conflicting build-manager indices -> render corruption.
2. **Image/TGA format** (032f463): CTP2 renders 16-bit TGAs as ARGB1555 with descriptor byte
   (offset 17) = 1 and a TGA-2.0 footer (AE: desc=1, 160x120 -> 38444B). MoM's desc=0 / no
   footer -> engine treats the alpha bit as 0 -> the fill blits transparent -> the surface is
   never painted -> heap garbage = the rainbow static. Fix the extractor/writer to emit ARGB1555
   (desc=1) + footer; do NOT blanket-force desc=0 (that was a wrong turn this session). Caveat:
   descriptor requirement varies by texture family (advance-icons upap* are desc=0; the CM2
   fugly proved a desc=1 override there breaks the GL) — match AE per family, verified by bytes.
3. **Line endings** (7b7ecf2): CRLF `\r` contamination in engine-parsed files breaks lookups.
   String files (gl_str/tips_str/civ_str/civilisation) MUST be LF (.gitattributes eol=lf).
- **A PARTIAL fix still shows full static — don't read "still broken" as "wrong hypothesis."**
  After the DB double-load fix alone, a clean full restart STILL rendered static (all tests here
  were full restarts — it is NOT a texture-cache/stale-render effect; that was a wrong inference).
  The banner only cleared once ALL THREE causes were addressed. With a compound bug, each correct
  fix looks like a failure until the last one lands, so verify all three surfaces before judging.
- **First move for ANY render corruption: `git log --grep=fugl` and read every message.** The
  history named all three mechanisms; chasing textures blind cost a whole session.

## [SLIC] B1a API Contract — sphere per-turn gold (2026-07-05, in-game proven)
Base-verified against ctp2_program/ctp/ctp2.map builtins + reference scenarios. Each was
a real load-time SLIC error dialog before the fix. Guarded by tools/test_mom_slic.py.
- **`playerTurn` is NOT a base SLIC symbol** ("Symbol playerTurn is undefined"). The
  BeginTurn event-local player is `player[0]`; used in an integer context it yields the
  turn player's index (reference scenarios do `if(player[0] == 1)`). The parked git-history
  modules used `playerTurn` throughout but were never actually run.
- **`TRIBES_LIFE`..`TRIBES_CHAOS` are civilisation-DB record names (#1..#5), NOT SLIC
  symbols** — SLIC cannot resolve them ("Symbol TRIBES_LIFE is undefined"). Faction identity
  uses the NUMERIC player index: player N = civ N (Life 1, Nature 2, Sorcery 3, Death 4,
  Chaos 5). The spec's `p == TRIBES_X` form was aspirational and never validated.
- **`AddGold(playerIndex, amount)`** — integer index, NOT `AddGold(player[p], ...)`. Real
  builtin (Slic_AddGold); AlexanderTheGreat uses `AddGold(1, 5000)`.
- **`CityHasBuilding(city, BuildingDB(IMPROVE_X))`** — a DB reference, NOT a quoted
  `"IMPROVE_X"` string.
- **One-shot handlers need a file-scope `int_t` latch**; DisableTrigger alone did NOT stop
  re-fire, and an unlatched `Message` in BeginTurn floods the queue -> 0xC0000005. Per-turn
  side effects that SHOULD fire every turn (AddGold income) need no latch.
- **Method that worked**: prove ONE element (Life) end-to-end in-game, then fan out to the
  dimension (B1b: the other 4 spheres). Life = `6 + cities*3 + lifeBlessings*4` gold/turn.

## [SPRITES] Units.bmp grid is 9x7 @ y=15, NOT 10-col @ (0,0) (2026-07-05)
MoMJR `H:\Games\civ2\MOMJR\MOMJR\Units.bmp` (640x586) is a 9-column x 7-row grid, ~64px
pitch both axes, content starting at y=15 (not 0,0). The extractor assumed 10 cols at (0,0),
mismapping every unit from flat cell 9 on: 19 sliced empty cells (invisible sprites) and ~30
rendered the WRONG neighbouring unit (Hydra showed a minotaur, etc.). Fixed via gutter-
detected grid in civ2_sprite_extractor.extract_units_sprites(). Cell N = the Nth unit in
RULES.TXT @UNITS order. B3-B9 are genuinely EMPTY placeholder cells (no source art).

## [UI] uptg06* dividers are STOCK art, not corruption; uptg06f-2 is loose-only (2026-07-05)
The dashed/hatched gold border dividers (uptg06b/h) are BYTE-IDENTICAL to the stock art in
pic555.zfs (verify with patch_ctp2_images.extract_rim_entry_tga_bytes) — authentic CTP2 UI,
not corruption. `patch_ctp2_images.py --base-only` regenerates exactly these. **NEVER remove
loose `uptg06f-2.tga`**: it is a copy NOT present in the zfs (LDL ctp_template.ldl references
it by name) — removing it = "Unable to find uptg06f-2.tga" launch error. GAP: validate_all_
surfaces.py has NO surface for LDL/UI-texture references; that class of missing-file is
currently unvalidated.

## [AI-CRASH — CONFIRMED + FIXED] Turn-0 goal-scheduler crash = negative settler need (2026-07-05)
The intermittent turn-0 `0xC0000005` (fault in `Scheduler::Scheduler` / `Goal*` / Governor,
NO SLIC frames -> SLIC/sprite changes exonerated) is CONFIRMED via a captured stack trace.
- **Trigger** (civ3log, Governor.cpp@3174): `Best settler unit: Peasants needed: -2, max: 0,
  current: 2`. The AI holds its 2 starting peasants; a strategy with `SettlerUnitsCount 0`
  yields `needed = 0 - 2 = -2`, and CTP2's goal scheduler underflows on the NEGATIVE need.
- **MoM-specific because**: peasants are `UNIT_CATEGORY_SETTLER` (Units.txt) AND the universal
  starting unit (UNIT_BUILD_LIST_LAND_SETTLER = { UNIT_PEASANTS }). So every AI starts with
  "settlers"; any strategy wanting fewer than the starting peasant count underflows. Base AE
  doesn't hit this (its settler is a separate, non-starting unit). Intermittent = only some
  map seeds/strategy assignments put an underflowing strategy in play at turn 0.
- **Fix**: raised every `SettlerUnitsCount < 2` to 2 in strategies.txt (lines 675, 1963, 3818).
  With the AI already holding 2 peasants, `needed = 0` (not negative) -> no underflow; and with
  `MaxSettlerBuildTurns 0` on those strategies, no actual expansion-behaviour change.
- **Verify**: intermittent, so test SEVERAL fresh new games. Workaround if a seed still slips:
  load a save (bypasses turn-0 AI init). The old "guaranteed WARRIOR_CODE" hypothesis is
  superseded — the AI does not even get WARRIOR_CODE (DiffDB 100/0) yet still crashed; the
  settler-need underflow is the real cause.

## [CRASH-DIAGNOSIS — TOOLING] In-game crash traces were symbolized against a STALE map (2026-07-09)
Every in-game "Exception Stack Trace" resolves addresses via `<exedir>\ctp2-dbg.map`
(DebugCallStack_Open). `run-ctp2-dbg-crashcapture.ps1` staged exe+pdb+dlls but NOT the
map, so the deployed map (5/26) lagged the exe (5/28) and **every symbol name in every
crash trace since was fiction** — the addresses were real (verified: WER `Exception
Offset 00152ca8` + base 0x00400000 == trace frame[0] 0x00552ca8; no ASLR rebase).
- **Consequence**: the b8161ec "turn-0 AI goal-scheduler crash (negative settler need)"
  diagnosis was built on bogus symbol names and is UNVERIFIED; the crash recurred 7/09.
  Only civ3log DPRINTF lines (file@line) were trustworthy in those captures.
- **Fix**: script now stages `ctp2-dbg.map` in lockstep with the exe (Get-OverlaySources).
- **Technique**: to re-symbolize any old trace, parse "Publics by Value" from the
  build-matched map and take the greatest symbol address <= each frame address.

## [CRASH - SITE CONFIRMED, CAUSE OPEN + GUARDS] Turn-0 0xC0000005 is a UI blit, not AI (2026-07-09)
Re-symbolized, the 7/09 crash is `aui_Blitter::Blt16To16+0x438` under
`ProgressWindow::StartCountingTo -> aui_UI::Draw -> ... -> aui_ImageList::DrawImages`
(the InitProgressWindow redraw during load; the AI log lines were merely last-logged).
- **FALSIFIED detour (do not repeat)**: the loose 120x120 desc=0x21 TGAs
  (`uptg20e.tga`/`uptg20e2.tga`/uptg06a-i, commit be124b9) looked like generated
  placeholder "impostors" shadowing zfs art - they are NOT. They are byte-identical
  (sha1-verified) extractions of the archive's .rim entries, produced by
  `patch_ctp2_images.py --base-only`; `uptg20e` really is a 120x120 tiling pattern and
  desc=0x21 (top-origin) is that pipeline's intended TGA form. They are REQUIRED loose
  because the archive stores `.rim`, not `.tga` - the launch script preflight enforces
  their presence and blocks launch without them. A deletion sweep was reverted in full.
- **Actual cause: still open** (intermittent; valid data was present on both crashing
  and working runs - suspect state-dependent, e.g. the aui_SDLSurface logical-size vs
  physical-buffer mismatch when a surface wraps the screen SDL_Surface with
  takeOwnership=FALSE, aui_sdlsurface.cpp:26-60).
- **Instruments installed** (H:\Games\civctp2): `DrawImages` skips + DPRINTFs
  NULL/degenerate image surfaces; `Blt16To16` refuses blits whose rects exceed the
  surface's PHYSICAL allocation (rows*Pitch vs Size) and DPRINTFs full geometry. With
  the map now staged fresh, the next occurrence self-identifies in civ3log instead of
  crashing.
- **Validator**: surface 9a = NEW dangling ldl-texture refs vs `ldl_texture_baseline.txt`
  (stock ships ~256 dangling refs that never load - absolute checks drown in noise);
  surface 9b = truncated/short-payload loose TGAs (desc byte is NOT a corruption signal).

## [CRASH-vs-FUGLY TRADE] aui_Window::Resize Draw-suppression reintroduces fuglies (2026-07-10)
The dead-buffer UI-blit crash (Blt16To16/TileBlt16To16 AV during CityControlPanel
construction, via ctp2_DropDown::AddItem -> SetWindowSize -> aui_Window::Resize) was first
"root-fixed" by gating the Draw() at the end of aui_Window::Resize behind
`if (g_ui->GetWindow(Id()))` — i.e. skip painting windows not yet attached to g_ui.
- **That REINTRODUCED fuglies**: CityControlPanel and its sub-surfaces are sized during
  construction BEFORE the parent window is registered in g_ui, so the guard suppressed their
  construction-time paint -> surface never painted -> rainbow static on the city-name/MAYOR
  banner. Same MECHANISM as the documented compound fugly ("surface never painted -> heap
  garbage"), but a NEW code trigger not in the data.
- **Diagnosis discipline that worked (after 3 false leads)**: verify the 3 documented DATA
  causes (DB double-load both forms, CRLF, TGA desc) are clean by BYTES (not `grep -c $'\r'`,
  which false-positived), AND confirm every engine guard logged 0 activations. When all data
  is clean and no guard fired, the culprit is the one change that alters rendering WITHOUT a
  log line — here, the Resize Draw-suppression.
- **Correct fix**: revert to unconditional Draw() in aui_Window::Resize; contain the actual
  dead-buffer crash with the SEH handlers inside Blt16To16/TileBlt16To16/DrawImages, which
  fail only the faulting blit rather than suppressing a whole paint. SEH had 0 hits the run
  the fugly appeared — proof the suppression was unnecessary for that run yet still corrupted.
- **Rule**: never fix a paint-time crash by SKIPPING the paint at a construction/resize choke
  point; contain it at the faulting blit. Skipping a paint = a fugly by another name.

## [FUGLY — 4th cause] Sizable-static name banner: transparent-cap surround unpainted (2026-07-11)
After the compound DB/TGA/CRLF fugly (all clean) AND after reverting the aui_Window::Resize
Draw-suppression (which fixed the LARGE-area banner static), a RESIDUAL rainbow static
remained on the control-panel unit/city NAME banner ENDS (the scroll end-caps).
- **Not a regression**: proven by 0 blitter-guard hits every run + the fact that engine
  changes only affect FAULTING/SKIPPED blits, so successful blits render byte-identically
  with or without them. Pre-existing; the crash fixes merely let the game run to show it.
- **Root cause**: the name banner is a `CTP2_STATIC_IMAGE_SIZABLE` (ctp2.ldl/controlpanel.ldl:
  left cap `uppd02ax` + stretched center `uppd02bx` + right cap `uppd02dx`, numberoflayers 2,
  NO pattern). The cap images are chromakey-transparent; the transparent surround around the
  cap art is never painted, so it shows uninitialized surface memory as static. This is the
  SAME documented mechanism ("fill blits transparent -> surface never painted -> heap garbage")
  as TGA cause #2, but a NEW trigger in the engine render path, not the data. Cap textures are
  zfs-stock (no loose desc fix possible).
- **Fix** (ctp2_Static::DrawThis): for a `m_multiImageStatic` with no pattern, draw the CENTER
  (parchment) segment across the FULL control rect BEFORE the caps/layers draw
  (`DrawThisStateImage(STATIC_IMAGE_CENTER, surface, &rect)`). The caps' transparent surround
  then shows the scroll texture instead of heap garbage. In-game proven clean.
- **Rule**: "fuglies are compound / a partial fix still shows static" (2026-07-04 lesson)
  extends to ENGINE causes too, not just the 3 data causes — verify the render path when all
  data surfaces are clean and no guard fired.

## [FIXED] Advance icons: 388 TGAs, only 11 distinct images (2026-07-13)
- **Symptom**: Alchemy/Alphabet/Animism (and whole groups) show the SAME image in the GL;
  the image itself is a Civ2 *building* picture, not an advance portrait.
- **Root cause (two layers)**:
  1. `momjr_csv/advances.csv` `cell_index` held 11 category-bucket values, not per-advance
     slots — every advance in a bucket sliced the same cell.
  2. Deeper: the atlas config's `advances -> Improvements.bmp` premise is WRONG. Visual
     inspection of `H:\Games\civ2\MOMJR\MOMJR\Improvements.bmp` proves it is building/wonder
     art; `Icons.bmp` is UI chrome. **Civ2 MOMJR has NO per-advance portraits at all** — the
     extractor pipeline for advances slices art that was never advance art.
- **The real design intent** lives in the momjr CTP2 port's own gamedata
  (`H:\Games\ctp2\mom\mom\Scen0000\default\gamedata\uniticon.txt` + `mom_uniticon.txt`):
  advances map to CTP2 GL pictures (CM2_UPAP*/UPAP*/UPSS*... mod-pack art). Only 129 of
  those 482 files exist locally (+63 recovered from the extracted Cradle/AoM dirs).
- **Fix applied** (data-only, uniticon.txt image fields only; Gameplay/Historical refs
  untouched): tiered assignment — (1) momjr mapping where the art file exists (67),
  (2) base `advanceicon.txt` art by exact name, loads from zfs (49), (3) remaining 109
  round-robined over a 98-image distinct pool (unused base CA*F + loose CM2/UP*L) so no
  two alphabetically-adjacent advances share an image (1 residual pair: NANO_MACHINES/
  NANO_WARFARE). Backup: scratchpad/uniticon.txt.bak.
- **Crash guard**: all 63 recovered loose TGAs arrived desc=0x01 — the documented GL
  SourceList crash trigger (see 2026-07-08 entry) — normalized to desc=0x00 before launch.
- **Rule**: for MoM advances there is no slicing source; per-advance art comes from the
  momjr uniticon mapping + base advanceicon fallback. Do NOT regenerate ICON_ADVANCE_*.tga
  from Improvements.bmp.

### CORRECTION to the entry above (same day) — fix was re-scoped after user regression report
The tiered rewrite of ALL 225 uniticon entries was **over-broad**: the generated MoM
category art was correct/liked for most advances (user: "I had most of the correct ones
before, now I'm missing most and only have old ones!" — e.g. Chaos Magic regressed to a
CTP2 power-plant picture). Final state: `uniticon.txt` restored from backup, then ONLY the
27 advances sharing Alchemy's md5-identical image were repointed — momjr loose art where
available (Alchemy→CM2_UPAP010L), base advanceicon exact-name (Writing→CA011F), remainder
round-robined over the other 10 MoM-generated looks (MoM aesthetic preserved, adjacency
dupes broken). **Rule: fix the complained-about set, nothing more — "correct" is what the
user sees, not what a tier ladder scores.** The desc=0x00 normalization of the 63 recovered
loose TGAs stands (GL-crash guard).
