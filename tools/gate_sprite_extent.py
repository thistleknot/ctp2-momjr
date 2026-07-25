"""GATE: opaque-content bbox fraction of the 96x72 canvas, via the REAL path.

Calls build_sprites._facing_images (which now runs _fit_content) on every
SPRITE_*.tga source. Asserts every unit is inside CONTENT_MAX_*_FRAC.
"""
import sys, pathlib
sys.path.insert(0, r"H:\Program Files(x86)\Activision\Call To Power 2\Scenarios\mom\tools")
import build_sprites as bs

src = pathlib.Path(r"H:\Program Files(x86)\Activision\Call To Power 2\Scenarios\mom\scen0000\default\graphics\pictures")
rows, bad = [], []
for tga in sorted(src.glob("SPRITE_*.tga")):
    img = bs._facing_images(tga, False)[0]
    box = img.getbbox()
    if box is None:
        continue
    x0, y0, x1, y1 = box
    w, h = (x1 - x0) / 96.0, (y1 - y0) / 72.0
    name = tga.stem.replace("SPRITE_", "")
    rows.append((w, h, name))
    # tolerance is ONE PIXEL per axis: the bound is pixel-quantised
    # (0.80 * 96 = 76.8 -> 77px = 0.8021), so a float-exact test can never pass.
    if w > bs.CONTENT_MAX_W_FRAC + 1.0/96 or h > bs.CONTENT_MAX_H_FRAC + 1.0/72:
        bad.append((round(w, 3), round(h, 3), name))

rows.sort(reverse=True)
print("widest 8:")
for w, h, n in rows[:8]:
    print(f"  {w:.2f} w  {h:.2f} h  {n}")
for tgt in ("GUARDIAN_SPIRIT", "SPEARMEN"):
    for w, h, n in rows:
        if n == tgt:
            print(f"  -> {w:.2f} w  {h:.2f} h  {n}")
print(f"n={len(rows)}  bound=({bs.CONTENT_MAX_W_FRAC} w, {bs.CONTENT_MAX_H_FRAC} h)")
print("GATE: " + ("PASS - every unit inside bound" if not bad else f"FAIL - {bad}"))
