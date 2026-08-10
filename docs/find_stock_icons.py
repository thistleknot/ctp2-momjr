"""Find unit icons that still show stock CTP2 art (lavender background)."""
import csv
from pathlib import Path
import numpy as np
from PIL import Image

IMG_DIR = Path(__file__).parent / "img" / "units"
CSV_PATH = Path(__file__).parent.parent / "tools" / "momjr_csv" / "units.csv"

units = []
with open(CSV_PATH, newline="", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        slug = r["name"].strip().lower().replace(" ", "_").replace("'", "")
        units.append({"name": r["name"].strip(), "slug": slug,
                      "art_idx": r["art_cell_index"].strip()})

problems = []
good = []
for u in units:
    p = IMG_DIR / f"{u['slug']}.png"
    if not p.exists():
        problems.append((u["name"], u["art_idx"], "NO_FILE"))
        continue
    arr = np.array(Image.open(p))
    # Stock CTP2 icons have a lavender/purple background (R~180, G~180, B~200+)
    # MoM icons have dark background (24, 24, 24)
    # Check corner pixels (should be background)
    corners = [arr[2, 2], arr[2, -3], arr[-3, 2], arr[-3, -3]]
    avg = np.mean(corners, axis=0)[:3]
    if avg[0] > 80 or avg[1] > 80 or avg[2] > 80:
        problems.append((u["name"], u["art_idx"], f"STOCK bg=({avg[0]:.0f},{avg[1]:.0f},{avg[2]:.0f})"))
    else:
        good.append(u["name"])

print(f"GOOD (dark bg, MoM art): {len(good)}")
print(f"PROBLEMS (stock CTP2 bg): {len(problems)}")
print()
for name, art_idx, reason in problems:
    print(f"  {name:20s} art_idx={art_idx:3s}  {reason}")
