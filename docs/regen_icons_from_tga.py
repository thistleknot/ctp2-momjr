"""Regenerate per-unit icon PNGs directly from the game TGA files."""
import csv
import struct
from pathlib import Path
from PIL import Image

CSV_PATH = Path(__file__).parent.parent / "tools" / "momjr_csv" / "units.csv"
TGA_DIR = Path(__file__).parent.parent / "scen0000" / "default" / "graphics" / "pictures"
OUT_DIR = Path(__file__).parent / "img" / "units"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def read_tga(path):
    with open(path, "rb") as f:
        data = f.read()
    id_len = data[0]
    width = struct.unpack_from("<H", data, 12)[0]
    height = struct.unpack_from("<H", data, 14)[0]
    bpp = data[16]
    desc = data[17]
    if bpp != 16:
        return None
    pixel_start = 18 + id_len
    # desc & 0x0F = number of alpha bits. If 0, treat all pixels as opaque.
    alpha_bits = desc & 0x0F
    top_down = (desc >> 5) & 1
    img = Image.new("RGBA", (width, height))
    pixels = img.load()
    for y in range(height):
        src_y = y if top_down else (height - 1 - y)
        for x in range(width):
            offset = pixel_start + (src_y * width + x) * 2
            if offset + 2 > len(data):
                break
            val = struct.unpack_from("<H", data, offset)[0]
            r = ((val >> 10) & 0x1F) * 255 // 31
            g = ((val >> 5) & 0x1F) * 255 // 31
            b = (val & 0x1F) * 255 // 31
            if alpha_bits > 0:
                a = 255 if (val >> 15) & 1 else 0
            else:
                # No alpha channel declared — all pixels opaque
                a = 255
            pixels[x, y] = (r, g, b, a)
    return img


def main():
    updated = 0
    kept = 0

    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            name = r["name"].strip()
            slug = name.lower().replace(" ", "_").replace("'", "")
            art_idx = int(r["art_cell_index"].strip())
            tga_path = TGA_DIR / f"CM2_UPAP{art_idx:03d}L.TGA"
            out_path = OUT_DIR / f"{slug}.png"

            if tga_path.exists():
                img = read_tga(tga_path)
                if img:
                    # Render on dark background with space for label
                    canvas = Image.new("RGB", (176, 160), (24, 24, 24))
                    img.thumbnail((150, 130), Image.NEAREST)
                    x = (176 - img.width) // 2
                    y = (160 - 18 - img.height) // 2
                    canvas.paste(img, (x, y), img)
                    canvas.save(out_path)
                    updated += 1
                    continue

            # If no TGA, keep existing icon from observer sheet crop (if it exists)
            if out_path.exists():
                kept += 1
            else:
                # Write a placeholder
                canvas = Image.new("RGB", (176, 160), (40, 10, 10))
                canvas.save(out_path)
                kept += 1

    print(f"Updated {updated} icons from TGAs, kept {kept} existing")


if __name__ == "__main__":
    main()
