"""
Scan Icons.bmp to locate the 5x4 Tier-A tech icon grid.
Generates full labeled contact sheet + finds the offset with max variance
(highest visual interest = most likely to be the actual icon block).
"""
import os
import numpy as np
from PIL import Image, ImageDraw

ICONS_BMP = r"H:\Games\civ2\MOMJR\MOMJR\Icons.bmp"
OUT_DIR = r"C:\Users\user\.copilot\session-state\9b090415-ba9e-48b0-90e9-e87483f5cada\files"

TILE_W, TILE_H = 34, 18
N_COLS, N_ROWS = 5, 4  # Tier A grid shape

icons = Image.open(ICONS_BMP).convert("RGB")
arr = np.array(icons)
IW, IH = icons.size

# --- Find candidate offsets: scan every (ox, oy) step 2px, score by total variance ---
best_score = 0
best_ox, best_oy = 0, 0
scores = []

for oy in range(0, min(IH - N_ROWS * TILE_H, 400), 2):
    for ox in range(0, min(IW - N_COLS * TILE_W, IW - N_COLS * TILE_W + 1), 2):
        block = arr[oy:oy + N_ROWS * TILE_H, ox:ox + N_COLS * TILE_W]
        score = float(block.var())
        scores.append((score, ox, oy))
        if score > best_score:
            best_score = score
            best_ox, best_oy = ox, oy

scores.sort(reverse=True)
print("Top 10 candidate offsets (by pixel variance = most visually complex):")
for score, ox, oy in scores[:10]:
    print(f"  offset=({ox},{oy})  variance={score:.1f}")

print(f"\nBest offset: ({best_ox},{best_oy})")

# --- Generate full contact sheet of Icons.bmp at 34x18 grid from (0,0) ---
# Show all complete tiles in the image with idx labels
scale = 3
pad_y = 14
n_full_cols = IW // TILE_W
n_full_rows = IH // TILE_H
cell_w = TILE_W * scale
cell_h = TILE_H * scale + pad_y

out_img = Image.new("RGB", (cell_w * n_full_cols, cell_h * n_full_rows), (30, 30, 30))
draw = ImageDraw.Draw(out_img)

for row in range(n_full_rows):
    for col in range(n_full_cols):
        x = col * TILE_W
        y = row * TILE_H
        cell = icons.crop((x, y, x + TILE_W, y + TILE_H))
        cell_big = cell.resize((TILE_W * scale, TILE_H * scale), Image.NEAREST)
        ox = col * cell_w
        oy = row * cell_h + pad_y
        out_img.paste(cell_big, (ox, oy))
        idx = row * n_full_cols + col
        tier_a_idx = row * 5 + col if (row < 4 and col < 5) else -1
        label = f"r{row}c{col}" + (f" T{tier_a_idx}" if tier_a_idx >= 0 else "")
        draw.text((ox + 1, row * cell_h + 1), label, fill=(255, 255, 0))

sheet_path = os.path.join(OUT_DIR, "icons_bmp_full_scan.png")
out_img.save(sheet_path)
print(f"Wrote full scan: {sheet_path} ({out_img.size})")

# --- Generate focused contact sheet at best offset ---
scale2 = 4
cell_w2 = TILE_W * scale2
cell_h2 = TILE_H * scale2 + 20
focus_img = Image.new("RGB", (cell_w2 * N_COLS, cell_h2 * N_ROWS), (30, 30, 30))
draw2 = ImageDraw.Draw(focus_img)

for row in range(N_ROWS):
    for col in range(N_COLS):
        x = best_ox + col * TILE_W
        y = best_oy + row * TILE_H
        cell = icons.crop((x, y, x + TILE_W, y + TILE_H))
        cell_big = cell.resize((TILE_W * scale2, TILE_H * scale2), Image.NEAREST)
        ox = col * cell_w2
        oy = row * cell_h2 + 20
        focus_img.paste(cell_big, (ox, oy))
        idx = row * 5 + col
        label = f"idx={idx} ({col},{row}) @({best_ox + col*TILE_W},{best_oy + row*TILE_H})"
        draw2.text((ox, row * cell_h2 + 2), label, fill=(255, 200, 0))

focus_path = os.path.join(OUT_DIR, "tier_a_best_offset.png")
focus_img.save(focus_path)
print(f"Wrote focus scan: {focus_path}")

# Also try the (0,0) offset explicitly
focus0 = Image.new("RGB", (cell_w2 * N_COLS, cell_h2 * N_ROWS), (30, 30, 30))
draw0 = ImageDraw.Draw(focus0)
for row in range(N_ROWS):
    for col in range(N_COLS):
        x = col * TILE_W
        y = row * TILE_H
        cell = icons.crop((x, y, x + TILE_W, y + TILE_H))
        cell_big = cell.resize((TILE_W * scale2, TILE_H * scale2), Image.NEAREST)
        ox = col * cell_w2
        oy = row * cell_h2 + 20
        focus0.paste(cell_big, (ox, oy))
        idx = row * 5 + col
        draw0.text((ox, row * cell_h2 + 2), f"idx={idx} px=({col*TILE_W},{row*TILE_H})", fill=(255, 200, 0))

focus0_path = os.path.join(OUT_DIR, "tier_a_offset0.png")
focus0.save(focus0_path)
print(f"Wrote offset(0,0) focus: {focus0_path}")
