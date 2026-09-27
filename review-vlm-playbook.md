# Playbook: review unit art with a contrastive vision judge

Source: operator, 2026-09-27 — "reduce from a full sprite-sheet to a few exemplars …
few-shot from the style we prefer, few-shot from the style we disprefer … contrastive
comparisons for the vlm to focus only on the problematic images … generate a single
klein and z-image and choose the best one, else vlm transcribe them and pick the best
elements to create a new one."

**Objective (operator's words):** find the units that are out of style and iterate on
those until they are in line with the rest — and make the judge focus only on the
problematic images.

## Why this shape

Measured 2026-09-27 on DWARF_WARRIOR (the full-sheet judge, 13 references, 3 runs):
the judge picked the current art 3/3 and called the whole reference set "pixel art" —
it was overloaded by 13 units at 96x72 and rewarded sprite crispness, not style.
Two things fix that:

1. **Contrastive few-shot, not a full sheet.** A handful of PREFERRED exemplars
   (operator-approved, never raised as a quality issue, plus logged inspirations) and
   a handful of DISPREFERRED exemplars (units the operator flagged, e.g. the pixel-look
   DWARF_CROSSBOW). The judge only has to say which side a unit falls on.
2. **Judge at master size.** Style is judged on 160x120 masters shown at 2x; the
   operator's final look stays at 96x72 shipping size.

## Tools

- `tools/style_audit.py` — judge (`ask_vlm`, Qwen3-VL-8B on the .17 ComfyUI server,
  ~3 s/question), sheets (`grid`, `comparison_sheet`, `side_by_side`), `contrast`,
  `judge` (3 shuffled runs, majority).
- `tools/momjr_csv/style_anchors.json` — becomes `{preferred: [...],
  dispreferred: [...], inspirations: [...]}`.
- `.tmp/gen_style_candidates.py` — one z-image + one klein (ReferenceLatent fed the
  preferred exemplars) per unit. klein ≈ 5.5 min/image on the P5200.
- `.tmp/rmbg.py` + `.tmp/union_alpha.py` — background as installed today.
- `tools/install_crafted_art.py --file` — install an accepted result.

## Rules that do not bend

- Every verdict is 3 runs with shuffled order; majority decides. One answer is noise.
- Candidates are rendered through the same pipeline as the exemplars (background
  removed, installed to a preview master) before they are judged.
- Nothing is installed without the operator seeing it on the review page.
- Units with `no_regenerate` in `unit_art_truth.json` are exemplars, never targets,
  unless the operator names them.
- Max 2 generate→judge→transcribe cycles per unit; then it goes to the operator.

## Layer 1 — parallel

- [OPEN] T1 Pick the exemplars
  Propose 4–5 PREFERRED (majority style on the set sheet, operator-approved, not
  flagged) and 4–5 DISPREFERRED (operator-flagged units). Inspirations join
  PREFERRED. Operator confirms the two lists — the one decision that is theirs.
  _Files:_ tools/momjr_csv/style_anchors.json, tools/style_audit.py
  _Verify:_ `python tools/style_audit.py exemplars` draws both sheets; operator OK

- [OPEN] T2 Contrastive judge prompt + calibration
  One image = PREFERRED block, DISPREFERRED block, then the unit (or candidates).
  Question: "Which block does X belong to? Answer PREFERRED or DISPREFERRED, then the
  visual elements that decided it." Calibrate before use: a PREFERRED exemplar held
  out must come back PREFERRED, and DWARF_CROSSBOW must come back DISPREFERRED, 3/3
  runs each. If either fails, the instrument is broken — fix it, do not use it.
  _Files:_ tools/style_audit.py, tools/test_style_audit.py
  _Verify:_ `python tools/style_audit.py calibrate` → 2/2 cases pass 3/3 runs

## Layer 2 — sequential

- [OPEN] T3 Find the problem units
  Run the contrastive question on every unit not in either exemplar list. A unit is
  a target when DISPREFERRED in ≥2 of 3 runs. Output: ranked list + the judge's
  deciding elements, as a review page. Operator can add or strike targets.
  _Files:_ tools/style_audit.py
  _Verify:_ `python tools/style_audit.py outliers` → list + page; rerun gives same set

- [OPEN] T4 One klein + one z-image per target, judge picks
  Per target: `contrast` (preferred exemplar vs the unit) writes the redraw prompt;
  generate ONE z-image and ONE klein (klein shown the preferred exemplars). Judge:
  CURRENT vs z-image vs klein, contrastive sheet, 3 runs. A candidate wins only if
  picked ≥2/3 AND the judge confirms the subject is still that unit.
  _Files:_ .tmp/gen_style_candidates.py, tools/style_audit.py
  _Verify:_ per target: `judge` output with votes + reasons logged

- [OPEN] T5 Else: transcribe and recombine
  If neither candidate wins: the judge transcribes both candidates and the nearest
  preferred exemplar — what each gets right (pose, palette, lighting, detail,
  subject) — and the iterating agent writes ONE new prompt combining the elements
  the judge credited. Generate again with the engine that scored closer. One retry;
  if it still loses, the unit goes to the operator with the transcripts.
  _Files:_ tools/style_audit.py, .tmp/gen_style_candidates.py
  _Verify:_ transcript + new prompt + second judge result logged per unit

- [OPEN] T6 Operator gate and install
  Review page: CURRENT beside the winner, with the judge's reasons. Accepted winners
  install via `install_crafted_art.py --file`, verdict recorded in the truth file.
  _Files:_ tools/momjr_csv/unit_art_truth.json, scen0000/**/SPRITE_*.tga, ICON_UNIT_*
  _Verify:_ `build_sprites.py` N/N, `mom_audit.py` FAIL 0, map-size sheet reviewed

- [OPEN] T7 Close the round
  Re-run T3 on the changed units only (stop when none is DISPREFERRED 2/3, or after 2
  rounds). Rebuild `mom.zip`, commit with the round's accepted units named.
  _Files:_ mom.zip, items-to-work.md
  _Verify:_ outlier count falls round over round; commit lists units

## Log

Each task appends a `_Lessons:` line here when it closes.
