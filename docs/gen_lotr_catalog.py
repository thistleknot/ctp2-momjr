"""Generate a browsable LotR art catalog page with individual icons and tags."""
import csv
import json
import struct
from pathlib import Path
from PIL import Image
import numpy as np

LOTR = Path(r"H:\Games\ctp2\Lord of the Rings-20260424T030215Z-3-001"
            r"\Lord of the Rings\CTP2_LOTR_100\Call To Power 2")
AUDIT_PATH = Path(__file__).parent / "art_audit_results.json"
OUT_DIR = Path(__file__).parent / "img" / "lotr"
OUT_MD = Path(__file__).parent / "reference" / "lotr-catalog.md"

OUT_DIR.mkdir(parents=True, exist_ok=True)


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
            px[x, y] = (((val >> 10) & 0x1F) * 255 // 31,
                        ((val >> 5) & 0x1F) * 255 // 31,
                        (val & 0x1F) * 255 // 31)
    return img


def main():
    # Load audit descriptions
    descriptions = {}
    if AUDIT_PATH.exists():
        with open(AUDIT_PATH) as f:
            data = json.load(f)
        for item in data.get("lotr", []):
            descriptions[item["name"]] = item.get("description", "")

    # Find all L.tga files in pictures dirs
    tgas = sorted(LOTR.rglob("*L.tga"), key=lambda p: p.stem.upper())
    tgas = [t for t in tgas if "pictures" in str(t).lower()]
    print(f"Found {len(tgas)} LotR TGAs")

    # Extract each as a PNG
    extracted = []
    for tga in tgas:
        label = tga.stem.replace("L", "").replace("l", "")
        out_path = OUT_DIR / f"{label}.png"

        if not out_path.exists():  # Skip if already extracted
            img = read_tga_rgb(tga)
            if img:
                img.save(out_path)
            else:
                continue

        desc = descriptions.get(label, descriptions.get(label.upper(), ""))
        extracted.append((label, desc, tga.name))

    print(f"Extracted {len(extracted)} icons")

    # Generate markdown catalog
    lines = ["# LotR Art Catalog\n"]
    lines.append(f"{len(extracted)} unit icons from the CTP2 Lord of the Rings mod.\n")
    lines.append("Use this to pick replacements for MoM units that need better art.\n")
    lines.append("Tell me: \"Use LotR **XXX** for **UNIT_NAME**\"\n")
    lines.append("| Icon | ID | Description |")
    lines.append("|------|----|-------------|")

    for label, desc, filename in extracted:
        img_ref = f"![{label}](../img/lotr/{label}.png)"
        desc_clean = desc.replace("|", "/")[:80] if desc else "—"
        lines.append(f"| {img_ref} | {label} | {desc_clean} |")

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT_MD}")


if __name__ == "__main__":
    main()
