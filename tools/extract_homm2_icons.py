"""Extract unit icons from HoMM2 Civ2 mod Units.gif into CTP2 TGA format.

Reads the HoMM2 sprite sheet (640x480, 10x10 grid of 64x48 cells),
extracts specific cells by index, scales to 160x120, and saves as
ARGB1555 TGA files for CTP2 uniticon.txt.

Usage: python extract_homm2_icons.py
"""
from pathlib import Path
from PIL import Image
import struct
import numpy as np

HOMM2_UNITS_GIF = Path(r"H:\games\civ2\HoMM2Mod1.1\Units.gif")
OUTPUT_DIR = Path(r"H:\Program Files(x86)\Activision\Call To Power 2\Scenarios\mom\scen0000\default\graphics\pictures")

# Cell dimensions in the HoMM2 sprite sheet
CELL_W, CELL_H = 64, 48
COLS = 10

# CTP2 icon target size
TARGET_W, TARGET_H = 160, 120

# Mapping: HoMM2 sheet index -> our unit icon filename
EXTRACTIONS = {
    17: "ICON_UNIT_GOBLIN.TGA",
    18: "ICON_UNIT_DWARF_WARRIOR.TGA",
    25: "ICON_UNIT_ORC.TGA",
    42: "ICON_UNIT_OGRE.TGA",
    50: "ICON_UNIT_TROLL.TGA",
    48: "ICON_UNIT_VAMPIRE.TGA",
    49: "ICON_UNIT_DRUID.TGA",
    58: "ICON_UNIT_CRUSADER.TGA",
    51: "ICON_UNIT_APPRENTICE.TGA",
    29: "ICON_UNIT_GOLEM_PROXY.TGA",  # for Crystal Golem + Bone Golem
    31: "ICON_UNIT_TEMPLAR.TGA",
    4:  "ICON_UNIT_PRIEST.TGA",  # Peasant sprite (closest to priest robes)
    16: "ICON_UNIT_TREANT.TGA",  # Sprite (nature fairy) -> Treant proxy
    15: "ICON_UNIT_DROW.TGA",    # Medusa -> Drow proxy (dark creature)
    18: "ICON_UNIT_DWARF_CROSSBOW.TGA",  # Same dwarf cell
    18: "ICON_UNIT_DWARF_RUNESMITH.TGA", # Same dwarf cell
}


def save_tga_argb1555(img: Image.Image, dest: Path):
    """Save a PIL Image as ARGB1555 16-bit TGA (CTP2 format).
    
    CTP2 requires: type=2 (uncompressed true-color), bpp=16, descriptor=1
    (1 alpha bit). TGA 2.0 footer for full compatibility.
    """
    img = img.convert("RGBA")
    w, h = img.size
    arr = np.array(img)
    
    # Convert RGBA8888 to ARGB1555
    r = (arr[:, :, 0] >> 3).astype(np.uint16)
    g = (arr[:, :, 1] >> 3).astype(np.uint16)
    b = (arr[:, :, 2] >> 3).astype(np.uint16)
    a = (arr[:, :, 3] > 127).astype(np.uint16)
    
    pixels = (a << 15) | (r << 10) | (g << 5) | b
    # TGA stores bottom-to-top
    pixels = np.flipud(pixels)
    
    # TGA header (18 bytes) — desc=0 matches MoM baseline (no alpha bit flag)
    header = struct.pack('<BBBHHBHHHHBB',
        0,    # id_length
        0,    # color_map_type
        2,    # image_type (uncompressed true-color)
        0, 0, # color_map (offset, length)
        0,    # color_map entry size
        0, 0, # x_origin, y_origin
        w, h, # width, height
        16,   # bpp
        0,    # descriptor (0 = MoM baseline format)
    )
    
    # TGA 1.0 format (no footer — CTP2 AE baseline is 38418 bytes)
    with open(dest, 'wb') as f:
        f.write(header)
        f.write(pixels.tobytes())


def extract_cell(sheet: Image.Image, index: int) -> Image.Image:
    """Extract a 64x48 cell from the sprite sheet by sequential index."""
    col = index % COLS
    row = index // COLS
    x = col * CELL_W
    y = row * CELL_H
    return sheet.crop((x, y, x + CELL_W, y + CELL_H))


def main():
    if not HOMM2_UNITS_GIF.exists():
        print(f"ERROR: {HOMM2_UNITS_GIF} not found")
        return
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Load and convert to RGBA
    sheet = Image.open(HOMM2_UNITS_GIF).convert("RGBA")
    print(f"Loaded {HOMM2_UNITS_GIF} ({sheet.size[0]}x{sheet.size[1]})")
    
    # Remove background (typically the palette's first color or magenta)
    # Civ2 uses the top-left pixel as the transparent color
    arr = np.array(sheet)
    bg_color = arr[0, 0, :3]  # top-left pixel RGB
    mask = np.all(arr[:, :, :3] == bg_color, axis=2)
    arr[mask, 3] = 0  # set alpha to 0 for background pixels
    sheet = Image.fromarray(arr)
    
    extracted = 0
    # De-duplicate: same index might map to multiple output files
    seen_indices = {}
    for index, filename in EXTRACTIONS.items():
        if index not in seen_indices:
            cell = extract_cell(sheet, index)
            # Scale to CTP2 icon size (160x120) with nearest-neighbor for pixel art
            scaled = cell.resize((TARGET_W, TARGET_H), Image.NEAREST)
            seen_indices[index] = scaled
        else:
            scaled = seen_indices[index]
        
        dest = OUTPUT_DIR / filename
        save_tga_argb1555(scaled, dest)
        print(f"  + {filename} (cell {index})")
        extracted += 1
    
    print(f"\nDone: {extracted} icon TGA(s) written to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
