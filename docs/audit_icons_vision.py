"""Classify unit icons from all 3 source mods using NVIDIA vision model.

Produces a master list: what each image depicts + proxy recommendations for MoM units.
Sources: MoM (current), HoMM2, LotR.
"""
import base64
import csv
import json
import time
import struct
from pathlib import Path
from io import BytesIO

import requests
from PIL import Image

# ─── Config ───────────────────────────────────────────────────────────────────

API_KEY = "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"
MODEL = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"
INVOKE_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

MOM_ICONS_DIR = Path(__file__).parent / "img" / "units"
HOMM2_SHEET = Path(__file__).parent / "img" / "HoMM2_Units_sheet.png"
LOTR_DIR = Path(r"H:\Games\ctp2\Lord of the Rings-20260424T030215Z-3-001\Lord of the Rings\CTP2_LOTR_100\Call To Power 2")
MOMJR_SHEET = Path(__file__).parent / "img" / "momjr_units_sheet.png"

CSV_PATH = Path(__file__).parent.parent / "tools" / "momjr_csv" / "units.csv"
OUT_PATH = Path(__file__).parent / "art_audit_results.json"

HEADERS = {"Authorization": f"Bearer {API_KEY}", "Accept": "application/json"}

# Known goods
KNOWN_GOOD = {"paladins", "pegasus", "elven_archers", "catapult"}


def img_to_b64(img: Image.Image) -> str:
    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def classify(img_b64: str, label: str) -> str:
    """Ask vision model what creature/character the image depicts."""
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": (
                f"This pixel art game icon is labeled '{label}'. "
                "In 5-10 words, describe what creature or character you SEE. "
                "Be literal: horse rider, skeleton, ship, bear, dragon, mage, etc."
            )},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
        ]}],
        "max_tokens": 60,
        "temperature": 0.2,
        "stream": False,
    }
    try:
        resp = requests.post(INVOKE_URL, headers=HEADERS, json=payload, timeout=45)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"ERROR: {e}"


def read_tga_to_pil(path: Path) -> Image.Image | None:
    """Read ARGB1555 TGA to PIL Image."""
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


# ─── Phase 1: Classify MoM current icons ─────────────────────────────────────

def audit_mom():
    print("=== Phase 1: MoM Current Icons ===")
    units = []
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            units.append({
                "name": r["name"].strip(),
                "sphere": r["sphere"].strip(),
                "slug": r["name"].strip().lower().replace(" ", "_").replace("'", ""),
            })

    results = []
    for i, u in enumerate(units):
        slug = u["slug"]
        if slug in KNOWN_GOOD:
            results.append({**u, "source": "mom", "description": "KNOWN_GOOD", "match": True})
            continue

        img_path = MOM_ICONS_DIR / f"{slug}.png"
        if not img_path.exists():
            results.append({**u, "source": "mom", "description": "NO_FILE", "match": None})
            continue

        b64 = base64.b64encode(img_path.read_bytes()).decode()
        print(f"  [{i+1}/{len(units)}] {u['name']}...", end=" ", flush=True)
        desc = classify(b64, f"UNIT_{slug.upper()}")
        print(desc[:60])
        results.append({**u, "source": "mom", "description": desc, "match": None})
        time.sleep(0.8)

    return results


# ─── Phase 2: Classify LotR icons ────────────────────────────────────────────

def audit_lotr():
    print("\n=== Phase 2: LotR Icons ===")
    # Find all *L.tga in pictures dirs
    tgas = sorted(LOTR_DIR.rglob("*L.tga"))
    tgas = [t for t in tgas if "pictures" in str(t).lower()]
    print(f"  Found {len(tgas)} LotR icon TGAs")

    results = []
    for i, tga in enumerate(tgas[:80]):  # Cap at 80 to stay within budget
        label = tga.stem.replace("L", "")
        img = read_tga_to_pil(tga)
        if not img:
            continue
        b64 = img_to_b64(img)
        print(f"  [{i+1}] {label}...", end=" ", flush=True)
        desc = classify(b64, label)
        print(desc[:60])
        results.append({"name": label, "source": "lotr", "file": str(tga.name), "description": desc})
        time.sleep(0.8)

    return results


# ─── Phase 3: Classify HoMM2 sheet cells ─────────────────────────────────────

def audit_homm2():
    print("\n=== Phase 3: HoMM2 Sheet ===")
    if not HOMM2_SHEET.exists():
        print("  HoMM2 sheet not found, skipping")
        return []

    sheet = Image.open(HOMM2_SHEET)
    # HoMM2 sheet is 640x480. Estimate grid: looks like ~8 cols of 80px
    # Let's just send the whole sheet and ask for a list
    # Actually better: slice into a grid and classify individually
    # 640/80 = 8 cols, 480/80 = 6 rows = 48 cells
    COLS, ROWS = 8, 6
    CELL_W, CELL_H = sheet.width // COLS, sheet.height // ROWS

    results = []
    for row in range(ROWS):
        for col in range(COLS):
            idx = row * COLS + col
            x0 = col * CELL_W
            y0 = row * CELL_H
            cell = sheet.crop((x0, y0, x0 + CELL_W, y0 + CELL_H))
            b64 = img_to_b64(cell)
            label = f"HoMM2_r{row}_c{col}"
            print(f"  [{idx+1}/48] {label}...", end=" ", flush=True)
            desc = classify(b64, label)
            print(desc[:60])
            results.append({"name": label, "source": "homm2", "grid": f"r{row}c{col}", "description": desc})
            time.sleep(0.8)

    return results


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    all_results = {}

    mom_results = audit_mom()
    all_results["mom"] = mom_results

    lotr_results = audit_lotr()
    all_results["lotr"] = lotr_results

    homm2_results = audit_homm2()
    all_results["homm2"] = homm2_results

    # Save full results
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nSaved results to {OUT_PATH}")

    # Print MoM mismatches
    print("\n" + "=" * 60)
    print("MoM UNIT CLASSIFICATIONS:")
    for r in mom_results:
        if r["description"] not in ("KNOWN_GOOD", "NO_FILE"):
            print(f"  {r['name']:20s} ({r['sphere']:8s}): {r['description'][:70]}")

    # Print proxy recommendations
    print("\n" + "=" * 60)
    print("PROXY CANDIDATES (LotR + HoMM2 that might fit MoM units):")
    # This will be filled after results are analyzed


if __name__ == "__main__":
    main()
