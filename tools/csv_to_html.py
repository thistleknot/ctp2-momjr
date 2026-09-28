"""csv_to_html.py -- scrollable single-file HTML review of unit art vs its caption.

Spec: no governing spec found. Basis: operator instruction 2026-09-06 -- "create
      an html version i can scroll so I can id misattributions". Promote to a REQ
      before anything depends on the output.

STEP 2b, an alternative to csv_to_xlsx.py off the same base64 CSV. Excel is good
for editing fields; this is better for the specific job of SPOTTING
MISATTRIBUTION, because the art and the claim sit side by side at a readable
size and the page can be filtered down to just the suspicious rows.

THE BADGE IS THE OPERATOR'S VERDICT, NOT A GUESS
An earlier version flagged rows from the first captioning pass's model-judged
`matches` column. That was a guess and it was wrong twice -- WARBEARS is a bear
and AIR_ELEMENTAL an elemental spirit, both caught by hand. Worse, once the
operator had dictated the truth the page still showed the stale guess, so their
corrections were in the CSV but invisible here.

It now reads `unit_art_truth.json` and shows what the art ACTUALLY DEPICTS with
the verdict class beside it:

  * wrong    -- art does not depict the unit; a misassignment to correct
  * proxy    -- art does not depict the unit but was chosen deliberately as the
                closest available; not a defect
  * damaged  -- subject is right, the pixels are broken (fragments, holes, or a
                file shared between units)
  * correct  -- art and name agree

Units with no recorded verdict carry no badge, which reads as UNREVIEWED rather
than as confirmed-good.

SELF-CONTAINED BY CONSTRUCTION. Images are inlined from the CSV's base64, so the
file opens from anywhere with no server, no image directory, and no network.
"""
from __future__ import annotations

import argparse
import base64
import csv
import html
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_CSV = HERE / "momjr_csv" / "unit_art_prompts_units_with_art.csv"
DEFAULT_JUDGED = HERE / "momjr_csv" / "unit_art_truth.json"
DEFAULT_XREF = HERE / "momjr_csv" / "unit_art_crossref.csv"
DEFAULT_GEN = [Path(r"H:\Program Files(x86)\Activision\Call To Power 2\.tmp\matrix\intent"),
               Path(r"H:\Program Files(x86)\Activision\Call To Power 2\.tmp\matrix\intent\seeds"),
               Path(r"H:\Program Files(x86)\Activision\Call To Power 2\.tmp\matrix\intent\txt2img"),
               Path(r"H:\Program Files(x86)\Activision\Call To Power 2\.tmp\matrix\intent\style"),
               # the restyle pass over units whose art was already correct
               Path(r"H:\Program Files(x86)\Activision\Call To Power 2\.tmp\matrix\upgrade\normalized"),
               # APPRENTICE regenerated from scratch, masked, fresh seeds
               Path(r"H:\Program Files(x86)\Activision\Call To Power 2\.tmp\matrix\intent\apprentice2")]
DEFAULT_OUT = HERE / "momjr_csv" / "unit_art_review.html"

SHOW = ["subject", "race", "pose", "gear", "weapon", "mount", "colours",
        "materials"]


def name_art_flags(path: Path) -> dict[str, dict]:
    """ident -> the OPERATOR's verdict about what the art depicts.

    This replaced a model-judged `matches` column. That column was a guess and
    it was wrong twice (WARBEARS is a bear, AIR_ELEMENTAL an elemental). The
    operator has since dictated the truth per unit, so the page shows THAT and
    stops presenting a guess as a flag.
    """
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def game_binding(path: Path) -> dict[str, dict]:
    """ident -> what the GAME binds this art to, straight from Units.txt.

    The caption says what the pixels look like; this says which unit the engine
    actually instantiates with them. Different questions, and the review needs
    both -- a tile can depict a wolf (caption) while the game hands it to
    UNIT_ORC (binding), and that pairing IS the misattribution.

    Read from unit_art_crossref.csv, which parses Units.txt rather than
    inferring from filenames. Filenames caused the confusion in the first place:
    SPRITE_B4 looked like a unit and is not one.
    """
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as fh:
        return {r["ident"]: r for r in csv.DictReader(fh)}


def generated_art(dirs: list[Path]) -> dict[str, tuple[str, str]]:
    """ident -> (base64 png, which pass produced it).

    Candidate replacements live in several directories because they came from
    different fixes -- a seed sweep, a txt2img pass, a style-clause pass. Later
    directories win, so the search order encodes "most recent attempt first"
    without needing a manifest.

    Inlined as base64 like the source art, so the page stays one file that opens
    anywhere. Nothing here installs anything: this is a candidate shown BESIDE
    the current art, and the operator decides.
    """
    out: dict[str, tuple[str, str]] = {}
    for d in dirs:
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.png")):
            if p.name.startswith("_"):          # contact sheets, not units
                continue
            # Candidates are written as ORC_s777.png / PRIEST_game_art.png --
            # strip the WHOLE experiment suffix, not one underscore-segment, or
            # PRIEST_game_art keys as "PRIEST_game" and never matches a unit.
            ident = re.sub(r"_(s\d+|none|game_art|digital_paint)$", "", p.stem)
            out[ident] = (base64.b64encode(p.read_bytes()).decode("ascii"), d.name)
    return out


def render(rows: list[dict], flags: dict[str, dict],
           bind: dict[str, dict] | None = None,
           gen: dict[str, tuple[str, str]] | None = None,
           sheets: list[tuple[str, str]] | None = None) -> str:
    """`sheets`: (caption, src) sprite sheets shown above the cards. Operator
    2026-09-28: "always provide the sprite sheet w the html each pass"."""
    bind = bind or {}
    gen = gen or {}
    sheet_html = "".join(
        f'<figure class="sheet"><figcaption>{html.escape(c)}</figcaption>'
        f'<div class="scroll"><img src="{html.escape(s)}" alt="{html.escape(c)}"></div></figure>'
        for c, s in (sheets or []))
    if sheet_html:
        sheet_html = f'<section id="sheets"><h2>Sprite sheets</h2>{sheet_html}</section>'
    cards = []
    for r in rows:
        ident = r.get("ident", "")
        fmt = r.get("art_format") or "png"
        b64 = (r.get("art_b64") or "").strip()
        img = (f'<img src="data:image/{fmt};base64,{b64}" alt="{html.escape(ident)}">'
               if b64 else '<div class="noart">no art</div>')
        t = flags.get(ident) or {}
        # A decided unit (crafted / keep / no_regenerate) offers no candidate:
        # showing one invites re-deciding a closed question every review pass.
        final = t.get("verdict") in ("crafted", "keep") or t.get("no_regenerate")
        g = None if final else gen.get(ident)
        if final:
            newart = ('<figure class="pane empty"><figcaption>PROPOSED</figcaption>'
                      '<div class="noart">final &mdash; no candidate</div></figure>')
        elif g:
            newart = (f'<figure class="pane"><figcaption>PROPOSED '
                      f'<span class="src">{html.escape(g[1])}</span></figcaption>'
                      f'<img class="gen" src="data:image/png;base64,{g[0]}" '
                      f'alt="{html.escape(ident)} proposed"></figure>')
        else:
            newart = ('<figure class="pane empty"><figcaption>PROPOSED</figcaption>'
                      '<div class="noart">not generated</div></figure>')
        verdict = t.get("verdict", "")
        depicts = t.get("depicts", "")
        badge = (f'<span class="badge {verdict}">{html.escape(verdict)}</span>'
                 if verdict else "")
        truth = (f'<p class="truth"><b>ART DEPICTS:</b> {html.escape(depicts)}'
                 + (f'<span class="note">{html.escape(t.get("note",""))}</span>'
                    if t.get("note") else "") + "</p>") if depicts else ""

        b = bind.get(ident)
        if b:
            ok = b.get("art_exists") == "1"
            game = (
                '<p class="game"><b>IN GAME:</b> '
                f'<code>{html.escape(b.get("unit", ""))}</code>'
                f' &rarr; <code>{html.escape(b.get("sprite", ""))}</code>'
                + (f' &middot; icon <code>{html.escape(b["icon"])}</code>'
                   if b.get("icon") else "")
                + ("" if ok else ' <span class="miss">sprite file MISSING</span>')
                + "</p>")
        else:
            # No Units.txt entry means the engine never instantiates this art.
            game = ('<p class="game orphan"><b>IN GAME:</b> '
                    "no unit references this art (orphan)</p>")
        pairs = "".join(
            f'<div class="k">{html.escape(k)}</div>'
            f'<div class="v">{html.escape(str(r.get(k, "")))}</div>'
            for k in SHOW if r.get(k))
        desc = html.escape(r.get("description", ""))
        hay = html.escape(" ".join(str(r.get(k, "")) for k in
                                   ["ident", "subject", "race", "description"]).lower())
        cards.append(f"""
<article class="row" data-flag="{int(bool(verdict))}" data-verdict="{verdict}" data-gen="{int(bool(g))}" data-hay="{hay}">
  <div class="art">
    <figure class="pane"><figcaption>CURRENT</figcaption>{img}</figure>
    {newart}
  </div>
  <div class="body">
    <h2>{html.escape(ident)} {badge}</h2>
    {game}
    {truth}
    <p class="desc">{desc}</p>
    <div class="grid">{pairs}</div>
  </div>
</article>""")

    n_flag = sum(1 for r in rows if flags.get(r.get("ident", "")))
    return f"""<!doctype html>
<meta charset="utf-8">
<title>MoM unit art review</title>
<style>
 :root {{ color-scheme: dark; --bg:#14161c; --card:#1d212b; --line:#2c313f;
          --fg:#e7e9ee; --dim:#9aa1b1; --warn:#f0a94a; }}
 * {{ box-sizing:border-box; }}
 body {{ margin:0; background:var(--bg); color:var(--fg);
         font:14px/1.45 system-ui,Segoe UI,sans-serif; }}
 header {{ position:sticky; top:0; z-index:5; background:var(--bg);
           border-bottom:1px solid var(--line); padding:12px 16px;
           display:flex; gap:12px; align-items:center; flex-wrap:wrap; }}
 h1 {{ font-size:15px; margin:0 12px 0 0; font-weight:600; }}
 input[type=search] {{ background:var(--card); border:1px solid var(--line);
        color:var(--fg); padding:7px 10px; border-radius:6px; min-width:240px; }}
 label {{ color:var(--dim); display:flex; gap:6px; align-items:center; }}
 .count {{ color:var(--dim); margin-left:auto; }}
 main {{ padding:16px; display:flex; flex-direction:column; gap:12px; }}
 .row {{ display:grid; grid-template-columns:380px 1fr; gap:16px;
         background:var(--card); border:1px solid var(--line);
         border-radius:10px; padding:12px; }}
 .art {{ display:flex; gap:10px; align-items:flex-start; }}
 .pane {{ margin:0; display:flex; flex-direction:column; gap:4px; }}
 .pane figcaption {{ font-size:10.5px; letter-spacing:.06em; color:var(--dim); }}
 .pane .src {{ color:#8fd0ff; }}
 .pane img {{ width:170px; height:128px; object-fit:contain;
              background:#6a6a72; border-radius:6px;
              image-rendering:pixelated; }}
 .pane img.gen {{ image-rendering:auto; }}
 .pane.empty .noart {{ width:170px; height:128px; border-radius:6px;
                       border:1px dashed var(--line); color:var(--dim);
                       display:flex; align-items:center; justify-content:center;
                       font-size:11px; }}
 .noart {{ color:#333; font-size:12px; }}
 h2 {{ margin:0 0 6px; font-size:15px; letter-spacing:.02em; }}
 .badge {{ font-size:11px; padding:2px 7px; border-radius:99px;
           vertical-align:middle; margin-left:8px; }}
 .wrong {{ background:rgba(240,90,90,.18); color:#ff8b8b;
           border:1px solid rgba(240,90,90,.45); }}
 .proxy {{ background:rgba(240,169,74,.16); color:var(--warn);
           border:1px solid rgba(240,169,74,.4); }}
 .damaged {{ background:rgba(190,120,240,.16); color:#cfa2f5;
             border:1px solid rgba(190,120,240,.4); }}
 .correct {{ background:rgba(90,200,120,.16); color:#7fd99b;
             border:1px solid rgba(90,200,120,.4); }}
 .game {{ margin:0 0 6px; font-size:12.5px; color:var(--dim); }}
 .game b {{ color:#8fd0ff; letter-spacing:.03em; }}
 .game code {{ background:rgba(255,255,255,.07); padding:1px 5px;
               border-radius:4px; color:var(--fg); font-size:12px; }}
 .miss {{ color:#ff8b8b; }}
 .orphan b {{ color:#ff8b8b; }}
 .truth {{ margin:0 0 6px; padding:6px 9px; border-radius:6px;
           background:rgba(255,255,255,.05); font-size:13px; }}
 .truth b {{ color:var(--warn); letter-spacing:.03em; }}
 .note {{ display:block; color:var(--dim); font-size:12px; margin-top:3px; }}
 .desc {{ margin:0 0 8px; color:var(--fg); }}
 .grid {{ display:grid; grid-template-columns:max-content 1fr;
          gap:2px 12px; font-size:13px; }}
 .k {{ color:var(--dim); }}
 #sheets {{ padding:16px 16px 0; display:flex; flex-direction:column; gap:14px; }}
 .sheet {{ margin:0; }}
 .sheet figcaption {{ color:var(--dim); font-size:12px; margin-bottom:6px; }}
 .sheet .scroll {{ overflow-x:auto; }}
 .sheet img {{ display:block; max-width:none; image-rendering:pixelated; }}
 @media (max-width:640px) {{ .row {{ grid-template-columns:1fr; }} }}
</style>
<header>
  <h1>MoM unit art review</h1>
  <input type="search" id="q" placeholder="filter by name, subject, description…">
  <label><input type="checkbox" id="only"> only corrected ({n_flag})</label>
  <label><input type="checkbox" id="gonly"> only with a proposal</label>
  <select id="vsel">
    <option value="">all verdicts</option>
    <option value="wrong">wrong</option>
    <option value="proxy">proxy</option>
    <option value="damaged">damaged</option>
    <option value="correct">correct</option>
  </select>
  <span class="count" id="count"></span>
</header>
{sheet_html}
<main id="list">{''.join(cards)}</main>
<script>
const rows=[...document.querySelectorAll('.row')],
      q=document.getElementById('q'), only=document.getElementById('only'),
      vsel=document.getElementById('vsel'), gonly=document.getElementById('gonly'),
      count=document.getElementById('count');
function apply(){{
  const t=q.value.trim().toLowerCase(), f=only.checked, v=vsel.value; let n=0;
  for(const r of rows){{
    const ok=(!t||r.dataset.hay.includes(t))
           &&(!f||r.dataset.flag==='1')
           &&(!v||r.dataset.verdict===v)
           &&(!gonly.checked||r.dataset.gen==='1');
    r.style.display=ok?'':'none'; if(ok)n++;
  }}
  count.textContent=n+' / '+rows.length+' units';
}}
q.addEventListener('input',apply); only.addEventListener('change',apply);
vsel.addEventListener('change',apply); gonly.addEventListener('change',apply); apply();
</script>"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    ap.add_argument("--judged", type=Path, default=DEFAULT_JUDGED)
    ap.add_argument("--xref", type=Path, default=DEFAULT_XREF)
    ap.add_argument("--gen", nargs="*", type=Path, default=DEFAULT_GEN,
                    help="dirs of proposed replacement art, later wins")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--sheet", action="append", default=[], metavar="CAPTION=SRC",
                    help="sprite sheet shown above the cards; SRC is relative to the page")
    args = ap.parse_args()
    sheets = [tuple(s.split("=", 1)) for s in args.sheet]

    rows = list(csv.DictReader(open(args.csv, encoding="utf-8")))
    if not rows:
        print("empty csv", file=sys.stderr)
        return 2
    if "art_b64" not in rows[0]:
        print("csv has no art_b64 column -- run embed_unit_art_b64.py first",
              file=sys.stderr)
        return 2
    flags = name_art_flags(args.judged)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    bind = game_binding(args.xref)
    unbound = [r["ident"] for r in rows if r["ident"] not in bind]
    gen = generated_art(list(args.gen))
    args.out.write_text(render(rows, flags, bind, gen, sheets), encoding="utf-8")
    n_art = sum(1 for r in rows if r.get("art_b64"))
    import collections
    verdicts = collections.Counter(
        (flags.get(r["ident"]) or {}).get("verdict", "") for r in rows)
    print(f"{len(rows)} units, {n_art} with art, {len(rows)-len(unbound)} bound to a unit in Units.txt")
    print(f"   proposed replacements shown: {sum(1 for r in rows if r['ident'] in gen)}")
    if unbound:
        print(f"   NOT bound to any unit: {sorted(unbound)}")
    for v, n in sorted(verdicts.items()):
        print(f"   {v or '(no verdict recorded)':24} {n}")
    print(f"-> {args.out}  ({args.out.stat().st_size/1e6:.1f} MB, self-contained)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
