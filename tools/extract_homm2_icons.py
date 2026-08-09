"""Extract HoMM2 unit art + custom art into MoM icon/sprite TGAs.
Uses the same component-based slot detection as the MoMJR extractor."""
from PIL import Image
from pathlib import Path
import numpy as np
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from civ2_sprite_extractor import (
    _remove_bg_colors, _detect_units_sheet_slots,
    _compose_units_slot_sprite, _scale_rgba_to_canvas,
    save_tga_rgb555, ICON_CONTENT_MAX_FRAC, ICON_FLOOR_MARGIN,
)

art_dir = Path(r'C:\Users\user\Documents\wiki\games\ctp2\art')
pics_dir = Path(r'H:\Program Files(x86)\Activision\Call To Power 2\Scenarios\mom\scen0000\default\graphics\pictures')
homm2_path = Path(r'H:\Games\civ2\HoMM2Mod1.1\Units.gif')

# Load HoMM2 sheet and key out backgrounds (same as MoMJR process)
sheet = Image.open(homm2_path).convert('RGBA')
arr = np.array(sheet, dtype=np.uint8)
arr = _remove_bg_colors(arr)

# Detect slots using the proven component-based algorithm
x_centers, y_centers, slots = _detect_units_sheet_slots(arr, 54)
print(f'Grid: {len(x_centers)} cols x {len(y_centers)} rows')


def extract_cell(row, col):
    """Extract a single cell using the component-based slot detection."""
    sprite = _compose_units_slot_sprite(arr, slots.get((row - 1, col - 1), []))
    if sprite.size[0] <= 1 or sprite.size[1] <= 1:
        return None
    return sprite


def scale_to_icon(cropped, target_w=160, target_h=120):
    return _scale_rgba_to_canvas(
        cropped, target_w, target_h,
        max_frac=ICON_CONTENT_MAX_FRAC, floor_margin=ICON_FLOOR_MARGIN,
    )

# HoMM2 cell -> MoM unit assignments (row, col are 1-indexed)
# Properly identified using component-based slot detection (same as MoMJR extractor)
assignments = {
    'SPRITE_DWARF_WARRIOR': (3, 2),    # Dwarf
    'SPRITE_DWARF_CROSSBOW': (4, 3),   # Crossbow figure
    'SPRITE_DWARF_RUNESMITH': (5, 3),  # Gold armored figure
    'SPRITE_PRIEST': (3, 1),           # Robed mage (blue)
    'SPRITE_CRUSADER': (2, 2),         # Red/gold knight on horse
    'SPRITE_TEMPLAR': (1, 1),          # Dark knight on horse
    'SPRITE_DRUID': (4, 5),            # Green robed figure
    'SPRITE_APPRENTICE': (5, 1),       # Small/weak figure
    'SPRITE_CRYSTAL_GOLEM': (5, 3),    # Gold armored figure
    'SPRITE_DJINN': (2, 6),            # Lightning creature
    'SPRITE_VAMPIRE': (6, 4),          # Red demon
    'SPRITE_BONE_GOLEM': (6, 1),       # Skeleton
    'SPRITE_GOBLIN': (4, 1),           # Imp/goblin
    'SPRITE_ORC': (4, 2),              # Axe warrior
    'SPRITE_OGRE': (2, 4),             # Heavy armored mounted
    'SPRITE_TROLL': (3, 3),            # Red dragon/griffin (big tough creature)
}

print("\n--- HoMM2 extractions ---")
for sprite_name, (row, col) in assignments.items():
    cropped = extract_cell(row, col)
    if cropped is None:
        print(f'  EMPTY: {sprite_name} at ({row},{col})')
        continue
    icon = scale_to_icon(cropped)
    # Save as both SPRITE_X.tga and ICON_UNIT_X.tga
    save_tga_rgb555(icon, pics_dir / f'{sprite_name}.tga', dry_run=False)
    icon_name = sprite_name.replace('SPRITE_', 'ICON_UNIT_')
    save_tga_rgb555(icon, pics_dir / f'{icon_name}.tga', dry_run=False)
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
    save_tga_rgb555(icon, pics_dir / f'SPRITE_{unit_name}.tga', dry_run=False)
    save_tga_rgb555(icon, pics_dir / f'ICON_UNIT_{unit_name}.tga', dry_run=False)
    print(f'  {name} (custom) -> OK')

print("\nDone. 18 units now have own art.")
