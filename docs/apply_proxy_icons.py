"""Apply proxy icon replacements from LotR/HoMM2 sources.

Reads source TGAs, converts to the correct format, writes to the MoM icon slots.
Then regenerates the observer sheet and docs icons.
"""
import csv
import struct
import shutil
from pathlib import Path
from PIL import Image
from io import BytesIO

LOTR_DIR = Path(r"H:\Games\ctp2\Lord of the Rings-20260424T030215Z-3-001"
                r"\Lord of the Rings\CTP2_LOTR_100\Call To Power 2")
HOMM2_SHEET = Path(__file__).parent / "img" / "HoMM2_Units_sheet.png"
MOM_PICTURES = Path(__file__).parent.parent / "scen0000" / "default" / "graphics" / "pictures"
CSV_PATH = Path(__file__).parent.parent / "tools" / "momjr_csv" / "units.csv"

# Replacement map: unit_slug -> (source, file_or_grid_pos)
REPLACEMENTS = {
    "priest":         ("lotr", "152CL.tga"),
    "apprentice":     ("lotr", "158L.tga"),
    "arch_mage":      ("lotr", "152L.tga"),
    "death_knight":   ("lotr", "117CL.tga"),
    "lich":           ("lotr", "152UL.tga"),
    "dracolich":      ("lotr", "150L.tga"),
    "djinn":          ("homm2", "r1_c5"),
    "dwarf_warrior":  ("lotr", "108_1CL.tga"),
    "dwarf_runesmith": ("homm2", "r4_c3"),
    "goblin":         ("homm2", "r3_c4"),
    "orc":            ("lotr", "106CL.tga"),
    "ogre":           ("lotr", "UPUP111L.tga"),
    "settler":        ("lotr", "147L.tga"),
    "caravan":        ("lotr", "UPUP002L.tga"),
    "bone_golem":     ("lotr", "144L.tga"),
    "crystal_golem":  ("lotr", "144UL.tga"),
}


def find_lotr_tga(filename):
    """Find a TGA in the LotR directory tree."""
    matches = list(LOTR_DIR.rglob(filename))
    if not matches:
        # Try case-insensitive
        matches = [p for p in LOTR_DIR.rglob("*") if p.name.lower() == filename.lower()]
    return matches[0] if matches else None


def get_homm2_cell(grid_pos):
    """Extract a cell from the HoMM2 sheet. grid_pos like 'r1_c5'."""
    sheet = Image.open(HOMM2_SHEET)
    parts = grid_pos.replace("r", "").replace("c", "").split("_")
    row, col = int(parts[0]), int(parts[1])
    COLS, ROWS = 8, 6
    CELL_W, CELL_H = sheet.width // COLS, sheet.height // ROWS
    x0, y0 = col * CELL_W, row * CELL_H
    return sheet.crop((x0, y0, x0 + CELL_W, y0 + CELL_H))


def read_tga_to_pil(path):
    """Read TGA to PIL."""
    with open(path, "rb") as f:
        data = f.read()
    id_len = data[0]
    width = struct.unpack_from("<H", data, 12)[0]
    height = struct.unpack_from("<H", data, 14)[0]
    bpp = data[16]
    if bpp != 16:
        return None
    pixel_start = 18 + id_len
    img = Image.new("RGBA", (width, height))
    pixels = img.load()
    for y in range(height):
        for x in range(width):
            offset = pixel_start + ((height - 1 - y) * width + x) * 2
            if offset + 2 > len(data):
                break
            val = struct.unpack_from("<H", data, offset)[0]
            r = ((val >> 10) & 0x1F) * 255 // 31
            g = ((val >> 5) & 0x1F) * 255 // 31
            b = (val & 0x1F) * 255 // 31
            a = 255 if (val >> 15) & 1 else 0
            pixels[x, y] = (r, g, b, a)
    return img


def write_tga_argb1555(img, path):
    """Write a PIL image as ARGB1555 TGA with descriptor byte 1."""
    width, height = img.size
    img = img.convert("RGBA")
    pixels = img.load()

    # TGA header (18 bytes)
    header = bytearray(18)
    header[2] = 2  # uncompressed true-color
    struct.pack_into("<H", header, 12, width)
    struct.pack_into("<H", header, 14, height)
    header[16] = 16  # 16 bpp
    header[17] = 1   # descriptor: 1 alpha bit (ARGB1555)

    pixel_data = bytearray(width * height * 2)
    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, height - 1 - y]  # bottom-up
            r5 = (r * 31 + 127) // 255
            g5 = (g * 31 + 127) // 255
            b5 = (b * 31 + 127) // 255
            a1 = 1 if a > 127 else 0
            val = (a1 << 15) | (r5 << 10) | (g5 << 5) | b5
            offset = (y * width + x) * 2
            struct.pack_into("<H", pixel_data, offset, val)

    # TGA 2.0 footer (26 bytes)
    footer = b'\x00' * 8 + b'TRUEVISION-XFILE.\x00'

    with open(path, "wb") as f:
        f.write(header)
        f.write(pixel_data)
        f.write(footer)


def get_art_cell_index(unit_slug):
    """Look up art_cell_index for a unit slug."""
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            slug = r["name"].strip().lower().replace(" ", "_").replace("'", "")
            if slug == unit_slug:
                return int(r["art_cell_index"].strip())
    return None


def main():
    replaced = 0
    failed = 0

    for unit_slug, (source, ref) in REPLACEMENTS.items():
        art_idx = get_art_cell_index(unit_slug)
        if art_idx is None:
            print(f"  SKIP {unit_slug}: not found in CSV")
            failed += 1
            continue

        target_tga = MOM_PICTURES / f"CM2_UPAP{art_idx:03d}L.TGA"

        # Get source image
        if source == "lotr":
            src_path = find_lotr_tga(ref)
            if not src_path:
                print(f"  SKIP {unit_slug}: LotR TGA '{ref}' not found")
                failed += 1
                continue
            src_img = read_tga_to_pil(src_path)
            if not src_img:
                print(f"  SKIP {unit_slug}: failed to read '{ref}'")
                failed += 1
                continue
        elif source == "homm2":
            src_img = get_homm2_cell(ref)
        else:
            print(f"  SKIP {unit_slug}: unknown source '{source}'")
            failed += 1
            continue

        # Resize to 160x120 (CTP2 GL icon standard size)
        src_img = src_img.resize((160, 120), Image.LANCZOS)

        # Backup original if it exists
        if target_tga.exists():
            backup = target_tga.with_suffix(".TGA.bak")
            if not backup.exists():
                shutil.copy2(target_tga, backup)

        # Write new TGA
        write_tga_argb1555(src_img, target_tga)
        print(f"  OK {unit_slug:20s} -> {target_tga.name} (from {source}/{ref})")
        replaced += 1

    print(f"\nDone: {replaced} replaced, {failed} failed")


if __name__ == "__main__":
    main()
