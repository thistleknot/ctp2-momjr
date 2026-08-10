"""Fix the 4 remaining failed icons."""
import csv
import struct
from pathlib import Path
from PIL import Image

LOTR = Path(r"H:\Games\ctp2\Lord of the Rings-20260424T030215Z-3-001"
            r"\Lord of the Rings\CTP2_LOTR_100\Call To Power 2")
HOMM2_SHEET = Path(__file__).parent / "img" / "HoMM2_Units_sheet.png"
TGA_DIR = Path(__file__).parent.parent / "scen0000" / "default" / "graphics" / "pictures"
IMG_DIR = Path(__file__).parent / "img" / "units"
CSV_PATH = Path(__file__).parent.parent / "tools" / "momjr_csv" / "units.csv"


def find_lotr(fn):
    m = list(LOTR.rglob(fn))
    if not m:
        m = [p for p in LOTR.rglob("*") if p.name.lower() == fn.lower()]
    return m[0] if m else None


def read_tga_rgb(path):
    with open(path, "rb") as f:
        data = f.read()
    id_len = data[0]
    w = struct.unpack_from("<H", data, 12)[0]
    h = struct.unpack_from("<H", data, 14)[0]
    if data[16] != 16:
        return None
    ps = 18 + id_len
    img = Image.new("RGB", (w, h), (0, 0, 0))
    px = img.load()
    for y in range(h):
        for x in range(w):
            off = ps + ((h - 1 - y) * w + x) * 2
            if off + 2 > len(data):
                break
            val = struct.unpack_from("<H", data, off)[0]
            px[x, y] = (
                ((val >> 10) & 0x1F) * 255 // 31,
                ((val >> 5) & 0x1F) * 255 // 31,
                (val & 0x1F) * 255 // 31,
            )
    return img


def write_tga(img, path):
    w, h = img.size
    img = img.convert("RGB")
    px = img.load()
    header = bytearray(18)
    header[2] = 2
    struct.pack_into("<H", header, 12, w)
    struct.pack_into("<H", header, 14, h)
    header[16] = 16
    header[17] = 1
    pixels = bytearray(w * h * 2)
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, h - 1 - y]
            val = (1 << 15) | (((r * 31 + 127) // 255) << 10) | (((g * 31 + 127) // 255) << 5) | ((b * 31 + 127) // 255)
            struct.pack_into("<H", pixels, (y * w + x) * 2, val)
    with open(path, "wb") as f:
        f.write(header + pixels + b"\x00" * 8 + b"TRUEVISION-XFILE.\x00")


def get_homm2_cell(row, col):
    sheet = Image.open(HOMM2_SHEET)
    cw, ch = sheet.width // 8, sheet.height // 6
    return sheet.crop((col * cw, row * ch, (col + 1) * cw, (row + 1) * ch))


def get_art_idx(slug):
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            s = r["name"].strip().lower().replace(" ", "_").replace("'", "")
            if s == slug:
                return int(r["art_cell_index"].strip())
    return None


def fix(slug, source_type, source_ref):
    art_idx = get_art_idx(slug)
    if art_idx is None:
        print(f"  SKIP {slug}: not in CSV")
        return

    if source_type == "homm2":
        row, col = source_ref
        img = get_homm2_cell(row, col)
    elif source_type == "lotr":
        src = find_lotr(source_ref)
        if not src:
            print(f"  SKIP {slug}: {source_ref} not found")
            return
        img = read_tga_rgb(src)
        if not img:
            print(f"  SKIP {slug}: read failed")
            return

    img160 = img.resize((160, 120), Image.LANCZOS)
    write_tga(img160, TGA_DIR / f"CM2_UPAP{art_idx:03d}L.TGA")

    canvas = Image.new("RGB", (176, 160), (24, 24, 24))
    img160.thumbnail((150, 130), Image.NEAREST)
    x = (176 - img160.width) // 2
    y = (160 - 18 - img160.height) // 2
    canvas.paste(img160, (x, y))
    canvas.save(IMG_DIR / f"{slug}.png")
    print(f"  OK {slug} -> CM2_UPAP{art_idx:03d}L.TGA")


def main():
    # Great Wyrm -> HoMM2 r1_c2 (red and green dragons)
    fix("great_wyrm", "homm2", (1, 2))

    # Centaurs -> HoMM2 r3_c6 (centaur visible in the cell)
    fix("centaurs", "homm2", (3, 6))

    # Behemoth -> HoMM2 r1_c1 (grey winged creature crouching - closest to massive beast)
    fix("behemoth", "homm2", (1, 1))

    # Infernal Device -> LotR 144 (golden armored figure with wings - otherworldly construct)
    # Actually let's try something more chaotic/explosive
    # LotR doesn't have great options. Use HoMM2 r3_c2 (mummy, vampire, dragon, winged)
    fix("infernal_device", "homm2", (3, 2))


if __name__ == "__main__":
    main()
