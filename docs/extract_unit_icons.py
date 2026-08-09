"""Extract per-unit icon PNGs from CTP2 TGA files for mkdocs embedding."""
import csv
import struct
from pathlib import Path
from PIL import Image

CSV_PATH = Path(__file__).parent.parent / "tools" / "momjr_csv" / "units.csv"
TGA_DIR = Path(__file__).parent.parent / "scen0000" / "default" / "graphics" / "pictures"
OUT_DIR = Path(__file__).parent / "img" / "units"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def read_tga_argb1555(path):
    """Read a 16-bit ARGB1555 TGA and return a PIL Image."""
    with open(path, "rb") as f:
        data = f.read()

    # TGA header (18 bytes)
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


def main():
    # Read units CSV to get art_cell_index -> unit name mapping
    units = {}
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            art_idx = int(r["art_cell_index"].strip())
            name = r["name"].strip().lower().replace(" ", "_").replace("'", "")
            units[art_idx] = name

    # The TGA naming pattern: CM2_UPAP{NNN}L.TGA where NNN is zero-padded art_cell_index
    converted = 0
    for art_idx, unit_name in sorted(units.items()):
        tga_name = f"CM2_UPAP{art_idx:03d}L.TGA"
        tga_path = TGA_DIR / tga_name
        if not tga_path.exists():
            # Try without L suffix
            tga_name2 = f"CM2_UPAP{art_idx:03d}.TGA"
            tga_path = TGA_DIR / tga_name2
            if not tga_path.exists():
                continue

        try:
            img = read_tga_argb1555(tga_path)
            if img:
                out_path = OUT_DIR / f"{unit_name}.png"
                # Resize to thumbnail for table embedding (48px height)
                ratio = 48 / img.height
                new_w = max(1, int(img.width * ratio))
                img_thumb = img.resize((new_w, 48), Image.NEAREST)
                img_thumb.save(out_path)
                converted += 1
        except Exception as e:
            print(f"  WARN: {tga_name} -> {e}")

    print(f"Extracted {converted} unit icons to {OUT_DIR}")


if __name__ == "__main__":
    main()
