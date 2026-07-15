"""
Generate the Tier A epoch×category translation matrix for MOMJR advances.
Outputs:
  - tier_a_matrix.csv  : 20-row matrix (one per unique icon slot)
  - advance_icon_map.csv: one row per advance showing its icon slot
  - tier_a_contact.png : visual contact sheet of Icons.bmp 5x4 tech-icon grid
"""
import csv, re, os, sys
from PIL import Image, ImageDraw, ImageFont

RULES = r"H:\Games\civ2\MOMJR\MOMJR\Rules.txt"
ICONS_BMP = r"H:\Games\civ2\MOMJR\MOMJR\Icons.bmp"
OUT_DIR = r"H:\Program Files(x86)\Activision\Call To Power 2\Scenarios\mom\tools"

CAT_LABELS = ["Militaristic", "Economic", "Social", "Academic", "Expansionist"]
EPOCH_LABELS = ["Ancient(0)", "Renaissance(1)", "Industrial(2)", "Modern(3)"]

# --- Parse @CIVILIZE ---
rules = open(RULES, encoding="latin-1").read()
civ_block = rules.split("@CIVILIZE")[1].split("@")[0]

advances = []
for line in civ_block.split("\n"):
    line = line.strip()
    if not line or line.startswith(";"):
        continue
    parts = line.split(",")
    if len(parts) < 7:
        continue
    name = parts[0].strip()
    try:
        epoch = int(parts[5].strip())
        cat = int(parts[6].split(";")[0].strip())
    except ValueError:
        break  # hit @UNITS section
    icon_idx = epoch * 5 + cat
    advances.append({
        "line_pos": len(advances),
        "name": name,
        "epoch": epoch,
        "category": cat,
        "icon_idx": icon_idx,
        "grid_col": cat,
        "grid_row": epoch,
    })

print(f"Parsed {len(advances)} advances from @CIVILIZE")

# --- Print 4x5 epoch×category grid ---
print("\nTIER A GRID  (col=Category, row=Epoch, value=icon_idx)")
header = f"{'':14}" + "".join(f"Cat{c}={CAT_LABELS[c][:3]:<9}" for c in range(5))
print(header)
for e in range(4):
    row = f"Epoch {e} {EPOCH_LABELS[e][:10]:<10}"
    for c in range(5):
        row += f"  idx={e*5+c:<6}"
    print(row)

# --- Print per-advance mapping ---
print(f"\n{'#':<5} {'Advance':<32} {'E':<3} {'C':<3} {'idx':<6} {'grid(col,row)'}")
for a in advances:
    print(f"{a['line_pos']:<5} {a['name']:<32} {a['epoch']:<3} {a['category']:<3} {a['icon_idx']:<6} ({a['grid_col']},{a['grid_row']})")

# --- Write advance_icon_map.csv ---
map_path = os.path.join(OUT_DIR, "advance_icon_map.csv")
with open(map_path, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["line_pos","name","epoch","category","icon_idx","grid_col","grid_row"])
    w.writeheader()
    w.writerows(advances)
print(f"\nWrote {map_path}")

# --- Write tier_a_matrix.csv (20 unique slots) ---
matrix_path = os.path.join(OUT_DIR, "tier_a_matrix.csv")
with open(matrix_path, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["icon_idx","epoch","category","epoch_label","category_label","grid_col","grid_row"])
    for e in range(4):
        for c in range(5):
            idx = e * 5 + c
            w.writerow([idx, e, c, EPOCH_LABELS[e], CAT_LABELS[c], c, e])
print(f"Wrote {matrix_path}")

# --- Generate contact sheet showing the 20 tier-A cells from Icons.bmp ---
# The Tier A tech icons are 34x18 tiles in a 5-col x 4-row block.
# We need to find the correct offset in Icons.bmp.
# Standard CIV2 Icons.bmp: tech icons start near top-left.
# Try offset (0,0) first — we'll label each tile so user can identify the correct region.
icons = Image.open(ICONS_BMP)
IW, IH = icons.size
TILE_W, TILE_H = 34, 18
N_COLS, N_ROWS = 5, 4

# Generate a contact sheet for multiple candidate y-offsets to find the tech block
out_path = os.path.join(OUT_DIR, "tier_a_icons_scan.png")

# Show first 8 rows x 5 cols of Icons.bmp at 34x18 tile size starting at x=0
scan_rows = 8
scale = 4
pad = 2
cell_w = TILE_W * scale + pad
cell_h = TILE_H * scale + 16 + pad  # 16px for label
img_out = Image.new("RGB", (cell_w * 5, cell_h * scan_rows), (40, 40, 40))
draw = ImageDraw.Draw(img_out)

for row in range(scan_rows):
    for col in range(5):
        x = col * TILE_W
        y = row * TILE_H
        if x + TILE_W <= IW and y + TILE_H <= IH:
            cell = icons.crop((x, y, x + TILE_W, y + TILE_H))
            cell_big = cell.resize((TILE_W * scale, TILE_H * scale), Image.NEAREST)
        else:
            cell_big = Image.new("RGB", (TILE_W * scale, TILE_H * scale), (80, 0, 0))
        ox = col * cell_w + pad // 2
        oy = row * cell_h + pad // 2
        img_out.paste(cell_big, (ox, oy + 14))
        idx = row * 5 + col
        label = f"r{row}c{col} i{idx}"
        draw.text((ox, oy), label, fill=(255, 255, 0))

img_out.save(out_path)
print(f"Wrote scan: {out_path}")
print("Done.")
