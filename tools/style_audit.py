"""style_audit.py -- find units whose art is out of style with the set, and judge
restyle candidates, using a local vision model on the ComfyUI server.

NO GOVERNING SPEC. Basis: operator 2026-09-27 -- "find those out of style and
iterate on those until they are in line with the rest"; "you should be able to use
.17 for vlm tasks". Plan: ~/.claude/plans/i-have-a-image-graceful-milner.md.

THE JUDGE is Qwen3-VL (AILab_QwenVL node) run through the ComfyUI API. One answer
from a vision model is noise, so every question is asked RUNS times with the
image order shuffled, and the majority decides.

Commands:
  probe UNIT            one question about one unit -- proves the judge answers
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageStat

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_sprites as B                          # noqa: E402
import zimage_graph as Z                           # noqa: E402
from export_transparent_png import DEFAULT_PICS    # noqa: E402

VLM_MODEL = "Qwen3-VL-8B-Instruct"
VLM_QUANT = "8-bit (Balanced)"
GROUND = (96, 104, 88)          # terrain-ish grey the units are judged on


def facing(unit: str, pics: Path = Path(DEFAULT_PICS)) -> Image.Image:
    """The unit exactly as build_sprites feeds the game: 96x72, keyed, on ground."""
    f = B._facing_images(pics / f"SPRITE_{unit}.tga", False)[0]
    plate = Image.new("RGB", f.size, GROUND)
    plate.paste(f, (0, 0), f)
    return plate


def features(img: Image.Image) -> dict[str, float]:
    """Style numbers for the figure only (ground pixels excluded)."""
    rgb = img.convert("RGB")
    mask = Image.eval(ImageChops.difference(rgb, Image.new("RGB", rgb.size, GROUND))
                      .convert("L"), lambda v: 255 if v else 0)
    hsv = rgb.convert("HSV")
    st = ImageStat.Stat(hsv, mask)
    edges = rgb.convert("L").filter(ImageFilter.FIND_EDGES)
    es = ImageStat.Stat(edges, mask)
    n = max(1, sum(1 for v in mask.getdata() if v))
    colours = len({p for p, m in zip(rgb.getdata(), mask.getdata()) if m})
    return {"saturation": st.mean[1], "value": st.mean[2], "contrast": st.stddev[2],
            "edges": es.mean[0], "colours_per_px": colours / n, "coverage": n / (rgb.width * rgb.height)}


def central(feats: dict[str, dict[str, float]], k: int = 13) -> list[str]:
    """The k units nearest the set median, each feature scaled by its spread (MAD)."""
    import statistics as st
    keys = next(iter(feats.values())).keys()
    med = {f: st.median(v[f] for v in feats.values()) for f in keys}
    mad = {f: (st.median(abs(v[f] - med[f]) for v in feats.values()) or 1.0) for f in keys}
    dist = {u: sum(((v[f] - med[f]) / mad[f]) ** 2 for f in keys) ** 0.5
            for u, v in feats.items()}
    return sorted(dist, key=dist.get)[:k]


def grid(cells: list[tuple[str, Image.Image]], cols: int, scale: int = 1) -> Image.Image:
    """Labelled grid of equally sized images."""
    w, h = cells[0][1].size
    w, h = w * scale, h * scale
    lb = 14
    rows = (len(cells) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (w + 4) + 4, rows * (h + lb + 4) + 4), (30, 30, 34))
    d = ImageDraw.Draw(sheet)
    for i, (label, im) in enumerate(cells):
        x, y = 4 + (i % cols) * (w + 4), 4 + (i // cols) * (h + lb + 4)
        d.text((x + 2, y), label, fill=(255, 226, 140))
        sheet.paste(im.resize((w, h), Image.NEAREST), (x, y + lb))
    return sheet


def comparison_sheet(refs: list[Image.Image], candidates: list[tuple[str, Image.Image]]
                     ) -> Image.Image:
    """Top: the reference set (unlabelled, 2x). Bottom: labelled candidates (2x)."""
    top = grid([("", r) for r in refs], cols=5, scale=2)
    bottom = grid(candidates, cols=max(1, len(candidates)), scale=2)
    sheet = Image.new("RGB", (max(top.width, bottom.width), top.height + bottom.height + 22),
                      (30, 30, 34))
    d = ImageDraw.Draw(sheet)
    d.text((6, 4), "REFERENCE SET", fill=(200, 200, 200))
    sheet.paste(top, (0, 16))
    d.text((6, top.height + 18), "CANDIDATES", fill=(200, 200, 200))
    sheet.paste(bottom, (0, top.height + 22))
    return sheet


def ask_vlm(image: Path, prompt: str, seed: int = 1, max_tokens: int = 256) -> str:
    """Ask the server's vision model one question about one image; return its text."""
    up = Z.upload(image.resolve())
    g = {"1": {"class_type": "LoadImage", "inputs": {"image": up}},
         "2": {"class_type": "AILab_QwenVL",
               "inputs": {"model_name": VLM_MODEL, "quantization": VLM_QUANT,
                          "attention_mode": "auto",
                          "preset_prompt": "🖼️ Detailed Description",
                          "custom_prompt": prompt, "max_tokens": max_tokens,
                          "keep_model_loaded": True, "seed": seed,
                          "image": ["1", 0]}},
         "3": {"class_type": "PreviewAny", "inputs": {"source": ["2", 0]}}}
    h = Z.run(g, timeout=1800)
    out = (h.get("outputs") or {}).get("3", {})
    text = out.get("text") or out.get("string")
    if isinstance(text, list):
        text = text[0] if text else ""
    # An empty answer must never read as a judgment: fail loudly instead.
    if not text or not str(text).strip():
        raise RuntimeError(f"vision model returned no text (history outputs: {h.get('outputs')!r:.200})")
    return str(text).strip()


ANCHORS = HERE / "momjr_csv" / "style_anchors.json"
SCRATCH = HERE.parent.parent.parent / ".tmp" / "style"


def roster() -> list[str]:
    """Every real unit (placeholder B3..B9 tiles excluded)."""
    import csv
    rows = csv.DictReader(open(HERE / "momjr_csv" / "unit_art_prompts_units.csv",
                               encoding="utf-8"))
    return [r["ident"] for r in rows
            if not (len(r["ident"]) == 2 and r["ident"][0] == "B")]


def cmd_anchors(k: int) -> None:
    """Propose the k most central units, save them, and draw both sheets."""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    imgs = {u: facing(u) for u in roster()}
    feats = {u: features(im) for u, im in imgs.items()}
    pick = central(feats, k)
    ANCHORS.write_text(json.dumps({"status": "PROPOSED -- operator to confirm",
                                   "anchors": pick}, indent=1), encoding="utf-8")
    grid(sorted(imgs.items()), cols=10).save(SCRATCH / "set_sheet.png")
    grid([(u, imgs[u]) for u in pick], cols=5, scale=2).save(SCRATCH / "anchor_sheet.png")
    print(f"proposed {k} anchors -> {ANCHORS}")
    print("  " + " ".join(pick))
    print(f"sheets -> {SCRATCH / 'set_sheet.png'} , {SCRATCH / 'anchor_sheet.png'}")


CONTRAST_PROMPT = (
    "Two pieces of unit art for a fantasy strategy game. LEFT (labelled A) is the "
    "art direction the designer wants. RIGHT (labelled B) is a {name} that does not "
    "fit. 1) List the 5 visual elements that make A work (rendering style, lighting, "
    "palette, level of detail, proportions, outline, pose). 2) Say what B does "
    "differently for each. 3) Write ONE image-generation prompt, under 60 words, for "
    "a new {name} drawn the way A is drawn, whole body visible. Label the parts "
    "WORKS:, DIFFERS:, PROMPT:")


def side_by_side(a: Image.Image, b: Image.Image, h: int = 288) -> Image.Image:
    """A and B scaled to the same height, labelled, on the dark sheet colour."""
    def fit(im):
        im = im.convert("RGB")
        return im.resize((max(1, round(im.width * h / im.height)), h), Image.LANCZOS)
    a, b = fit(a), fit(b)
    sheet = Image.new("RGB", (a.width + b.width + 30, h + 24), (30, 30, 34))
    d = ImageDraw.Draw(sheet)
    d.text((8, 4), "A", fill=(255, 226, 140))
    d.text((a.width + 22, 4), "B", fill=(255, 226, 140))
    sheet.paste(a, (10, 22))
    sheet.paste(b, (a.width + 20, 22))
    return sheet


def cmd_contrast(unit: str, inspiration: Path) -> str:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    img = SCRATCH / f"contrast_{unit}.png"
    side_by_side(Image.open(inspiration), facing(unit)).save(img)
    name = unit.replace("_", " ").lower()
    answer = ask_vlm(img, CONTRAST_PROMPT.format(name=name), max_tokens=700)
    (SCRATCH / f"contrast_{unit}.txt").write_text(answer, encoding="utf-8")
    return answer


JUDGE_PROMPT = (
    "The top block is the REFERENCE SET of unit art for one fantasy strategy game. "
    "Below it are candidates labelled {letters}, each meant to be a {name}. Which ONE "
    "candidate best matches the reference set's art style AND clearly shows a {name}? "
    "Answer with the letter first, like 'C', then one sentence why.")


def thumb(im: Image.Image, box=(96, 72)) -> Image.Image:
    """Fit any image into a ship-size cell on the ground colour."""
    im = im.convert("RGBA")
    im.thumbnail(box, Image.LANCZOS)
    plate = Image.new("RGB", box, GROUND)
    plate.paste(im, ((box[0] - im.width) // 2, (box[1] - im.height) // 2), im)
    return plate


def parse_letter(answer: str, letters: str) -> str | None:
    """First standalone candidate letter in the answer, or None."""
    import re
    m = re.search(rf"\b([{letters}])\b", answer.upper())
    return m.group(1) if m else None


def cmd_judge(unit: str, candidates: dict[str, Image.Image], runs: int = 3) -> dict:
    """Ask RUNS times with shuffled letters; return votes per candidate name."""
    import random
    anchors = json.loads(ANCHORS.read_text(encoding="utf-8"))["anchors"]
    refs = [facing(u) for u in anchors if u != unit]
    names = list(candidates)
    votes = {n: 0 for n in names}
    reasons = []
    SCRATCH.mkdir(parents=True, exist_ok=True)
    for r in range(runs):
        order = names[:]
        random.Random(r + 1).shuffle(order)
        letters = "ABCDEFGH"[:len(order)]
        cells = [(letters[i], thumb(candidates[n])) for i, n in enumerate(order)]
        img = SCRATCH / f"judge_{unit}_r{r}.png"
        comparison_sheet(refs, cells).save(img)
        ans = ask_vlm(img, JUDGE_PROMPT.format(letters=", ".join(letters),
                                               name=unit.replace("_", " ").lower()),
                      seed=r + 1)
        pick = parse_letter(ans, letters)
        if pick:
            votes[order[letters.index(pick)]] += 1
        reasons.append((r, pick and order[letters.index(pick)], ans[:200]))
    return {"votes": votes, "reasons": reasons}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("probe")
    p.add_argument("unit")
    p.add_argument("--out", type=Path, default=HERE.parent.parent.parent / ".tmp")
    an = sub.add_parser("anchors")
    an.add_argument("--k", type=int, default=13)
    c = sub.add_parser("contrast", help="what makes an inspiration work vs a unit")
    c.add_argument("unit")
    c.add_argument("inspiration", type=Path)
    j = sub.add_parser("judge", help="pick the candidate that best fits the set")
    j.add_argument("unit")
    j.add_argument("files", nargs="+", type=Path, help="NAME=PATH candidates")
    j.add_argument("--runs", type=int, default=3)
    a = ap.parse_args()
    if a.cmd == "judge":
        cands = {}
        for spec in map(str, a.files):
            name, _, path = spec.partition("=")
            if path == "CURRENT":
                cands[name] = facing(a.unit)
            elif path.lower().endswith(".tga"):
                # a master: render it through the same sprite pipeline as the set
                cands[name] = facing(Path(path).stem[len("SPRITE_"):], Path(path).parent)
            else:
                cands[name] = Image.open(path)
        res = cmd_judge(a.unit, cands, a.runs)
        for r, pick, why in res["reasons"]:
            print(f"  run {r}: {pick}  | {why}")
        print("votes:", res["votes"])
        return 0
    if a.cmd == "contrast":
        print(cmd_contrast(a.unit, a.inspiration))
        return 0
    if a.cmd == "anchors":
        cmd_anchors(a.k)
        return 0
    if a.cmd == "probe":
        img = a.out / f"probe_{a.unit}.png"
        facing(a.unit).resize((192, 144), Image.NEAREST).save(img)
        print(ask_vlm(img, f"This is unit art for a fantasy strategy game. What unit "
                           f"is shown, and describe its art style in one sentence "
                           f"(painted, pixel art, cartoon, realistic, lighting, palette)."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
