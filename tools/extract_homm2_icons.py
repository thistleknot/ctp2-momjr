"""Extract HoMM2 unit art + custom art into MoM icon/sprite TGAs."""
from PIL import Image
from pathlib import Path
import numpy as np

art_dir = Path(r'C:\Users\user\Documents\wiki\games\ctp2\art')
pics_dir = Path(r'H:\Program Files(x86)\Activision\Call To Power 2\Scenarios\mom\scen0000\default\graphics\pictures')
homm2_path = Path(r'H:\Games\civ2\HoMM2Mod1.1\Units.gif')

# Load HoMM2 sheet and key out magenta
sheet = Image.open(homm2_path).convert('RGBA')
arr = np.array(sheet)
for (r, g, b) in [(255, 0, 255), (135, 83, 135), (128, 80, 128)]:
    m = (arr[:, :, 0] == r) & (arr[:, :, 1] == g) & (arr[:, :, 2] == b)
    arr[m, 3] = 0
# Also key pure green grid lines
green = (arr[:, :, 0] == 0) & (arr[:, :, 1] == 255) & (arr[:, :, 2] == 0)
arr[green, 3] = 0
sheet_keyed = Image.fromarray(arr, 'RGBA')

# Detect grid from green lines
h_green = green.sum(axis=1)
v_green = green.sum(axis=0)
h_lines = np.where(h_green > 100)[0]
v_lines = np.where(v_green > 50)[0]


def cluster(positions, gap=5):
    if len(positions) == 0:
        return []
    clusters = []
    start = positions[0]
    for i in range(1, len(positions)):
        if positions[i] - positions[i - 1] > gap:
            clusters.append((start + positions[i - 1]) // 2)
            start = positions[i]
    clusters.append((start + positions[-1]) // 2)
    return clusters


h_seps = cluster(h_lines)
v_seps = cluster(v_lines)

# Filter out separators at the very edge (position 0 or 1)
h_seps = [s for s in h_seps if s > 2][:5]  # expect 5 internal h-seps for 6 rows
v_seps = [s for s in v_seps if s > 2][:7]  # expect 7 internal v-seps for 8 cols
# But we need 9 cols: the sheet may have 8 internal separators
# Actually: 9 cols needs 8 v-seps. Let's just take all valid ones.
v_seps_all = [s for s in cluster(v_lines) if s > 2]
h_seps_all = [s for s in cluster(h_lines) if s > 2]
# Use first 8 v-seps and first 5 h-seps (giving 9 cols, 6 rows)
v_seps = v_seps_all[:8]
h_seps = h_seps_all[:5]
print(f'Grid: {len(v_seps)+1} cols x {len(h_seps)+1} rows')
print(f'H seps: {h_seps}')
print(f'V seps: {v_seps}')


def cells_from_seps(seps, total):
    bounds = [0] + seps + [total]
    return [(bounds[i] + 1, bounds[i + 1] - 1) for i in range(len(bounds) - 1)]


row_bounds = cells_from_seps(h_seps, arr.shape[0])
col_bounds = cells_from_seps(v_seps, arr.shape[1])


def extract_cell(row, col):
    y0, y1 = row_bounds[row - 1]
    x0, x1 = col_bounds[col - 1]
    if x1 <= x0 or y1 <= y0:
        print(f'    [WARN] bad bounds at ({row},{col}): x={x0}..{x1} y={y0}..{y1}')
        return None
    cell = sheet_keyed.crop((x0, y0, x1, y1))
    ca = np.array(cell)
    alpha = ca[:, :, 3]
    if alpha.max() == 0:
        return None
    rows_with = np.any(alpha > 0, axis=1)
    cols_with = np.any(alpha > 0, axis=0)
    rmin, rmax = np.where(rows_with)[0][[0, -1]]
    cmin, cmax = np.where(cols_with)[0][[0, -1]]
    return cell.crop((cmin, rmin, cmax + 1, rmax + 1))


def scale_to_icon(cropped, target_w=160, target_h=120):
    max_frac = 0.80
    floor_margin = 6
    uw = int(target_w * max_frac)
    uh = int(target_h * max_frac) - floor_margin
    cw, ch = cropped.size
    scale = min(uw / cw, uh / ch)
    nw = max(1, int(cw * scale))
    nh = max(1, int(ch * scale))
    resized = cropped.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new('RGBA', (target_w, target_h), (0, 0, 0, 0))
    x_off = (target_w - nw) // 2
    y_off = target_h - floor_margin - nh
    canvas.paste(resized, (x_off, y_off), resized)
    return canvas


def save_rgb555(img, dest):
    bg = Image.new('RGB', img.size, (0, 0, 0))
    if img.mode == 'RGBA':
        bg.paste(img.convert('RGB'), mask=img.split()[3])
    else:
        bg.paste(img.convert('RGB'))
    a = np.array(bg, dtype=np.uint8)
    h, w = a.shape[:2]
    r = a[:, :, 0].astype(np.uint16) >> 3
    g = a[:, :, 1].astype(np.uint16) >> 3
    b = a[:, :, 2].astype(np.uint16) >> 3
    packed = (r << 10) | (g << 5) | b
    flipped = np.flipud(packed)
    header = bytes([0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                    w & 0xFF, (w >> 8) & 0xFF,
                    h & 0xFF, (h >> 8) & 0xFF, 16, 0x00])
    with open(dest, 'wb') as fh:
        fh.write(header)
        fh.write(flipped.tobytes())


# HoMM2 cell -> MoM unit assignments (row, col are 1-indexed)
assignments = {
    'SPRITE_DWARF_WARRIOR': (3, 2),    # Dwarf
    'SPRITE_DWARF_CROSSBOW': (3, 3),   # Elf with bow (ranged dwarf proxy)
    'SPRITE_DWARF_RUNESMITH': (5, 5),  # Magi (robed caster)
    'SPRITE_PRIEST': (5, 5),           # Magi (robed holy figure)
    'SPRITE_CRUSADER': (1, 6),         # Paladin
    'SPRITE_TEMPLAR': (1, 7),          # Champion
    'SPRITE_DRUID': (3, 4),            # Druid
    'SPRITE_APPRENTICE': (5, 1),       # Halfling (small, weak)
    'SPRITE_CRYSTAL_GOLEM': (5, 3),    # Iron Golem
    'SPRITE_DJINN': (3, 6),            # Phoenix (magical flying)
    'SPRITE_VAMPIRE': (6, 4),          # Vampire
    'SPRITE_BONE_GOLEM': (6, 3),       # Mummy
    'SPRITE_GOBLIN': (2, 1),           # Goblin
    'SPRITE_ORC': (2, 2),              # Orc
    'SPRITE_OGRE': (2, 4),             # Ogre
    'SPRITE_TROLL': (2, 5),            # Troll
}

print("\n--- HoMM2 extractions ---")
for sprite_name, (row, col) in assignments.items():
    cropped = extract_cell(row, col)
    if cropped is None:
        print(f'  EMPTY: {sprite_name} at ({row},{col})')
        continue
    icon = scale_to_icon(cropped)
    # Save as both SPRITE_X.tga and ICON_UNIT_X.tga
    save_rgb555(icon, pics_dir / f'{sprite_name}.tga')
    icon_name = sprite_name.replace('SPRITE_', 'ICON_UNIT_')
    save_rgb555(icon, pics_dir / f'{icon_name}.tga')
    print(f'  {sprite_name} ({row},{col}) -> OK')

print("\n--- Custom art (Treant, Drow) ---")
for name in ['Treant', 'drow']:
    src = art_dir / f'{name}.tga'
    img = Image.open(src).convert('RGBA')
    a = np.array(img)
    alpha = a[:, :, 3]
    rows_with = np.any(alpha > 0, axis=1)
    cols_with = np.any(alpha > 0, axis=0)
    if not rows_with.any():
        print(f'  EMPTY: {name}')
        continue
    rmin, rmax = np.where(rows_with)[0][[0, -1]]
    cmin, cmax = np.where(cols_with)[0][[0, -1]]
    cropped = img.crop((cmin, rmin, cmax + 1, rmax + 1))
    icon = scale_to_icon(cropped)

    unit_name = name.upper()
    save_rgb555(icon, pics_dir / f'SPRITE_{unit_name}.tga')
    save_rgb555(icon, pics_dir / f'ICON_UNIT_{unit_name}.tga')
    print(f'  {name} (custom) -> OK')

print("\nDone. 18 units now have own art.")
