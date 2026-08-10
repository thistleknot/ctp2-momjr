"""Classify unit icons from all 3 source mods using NVIDIA vision model.

Batch 4 images per request + 4 concurrent requests = 16x throughput.
Produces a master list: what each image depicts + proxy recommendations.
Sources: MoM (current), HoMM2, LotR.
"""
import asyncio
import base64
import csv
import json
import struct
from io import BytesIO
from pathlib import Path

import aiohttp
from PIL import Image

# ─── Config ───────────────────────────────────────────────────────────────────

API_KEY = "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"
MODEL = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"
INVOKE_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

BATCH_SIZE = 4       # images per request
CONCURRENCY = 4      # parallel requests

MOM_ICONS_DIR = Path(__file__).parent / "img" / "units"
HOMM2_SHEET = Path(__file__).parent / "img" / "HoMM2_Units_sheet.png"
LOTR_DIR = Path(r"H:\Games\ctp2\Lord of the Rings-20260424T030215Z-3-001"
                r"\Lord of the Rings\CTP2_LOTR_100\Call To Power 2")

CSV_PATH = Path(__file__).parent.parent / "tools" / "momjr_csv" / "units.csv"
OUT_PATH = Path(__file__).parent / "art_audit_results.json"

KNOWN_GOOD = {"paladins", "pegasus", "elven_archers", "catapult"}
HEADERS = {"Authorization": f"Bearer {API_KEY}", "Accept": "application/json"}


def img_to_b64(img: Image.Image) -> str:
    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def read_tga_to_pil(path: Path):
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


async def classify_batch(session, batch):
    """Send up to 4 images in one request. Returns list of descriptions."""
    prompt_parts = []
    for i, item in enumerate(batch):
        prompt_parts.append(f"Image {i+1} is labeled '{item['label']}'.")

    prompt = (
        " ".join(prompt_parts)
        + f" For EACH image (1-{len(batch)}), describe in 5-10 words what creature "
        "or character you see. Be literal: horse rider, skeleton, ship, bear, "
        "dragon, mage, etc. Format: one line per image as '1: description'."
    )

    content = [{"type": "text", "text": prompt}]
    for item in batch:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{item['b64']}"}
        })

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 150,
        "temperature": 0.2,
        "stream": False,
    }

    for attempt in range(3):
        try:
            async with session.post(
                INVOKE_URL, json=payload, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                if resp.status == 429 or resp.status >= 500:
                    await asyncio.sleep(2 ** (attempt + 1))
                    continue
                resp.raise_for_status()
                data = await resp.json()
                text = data["choices"][0]["message"]["content"].strip()
                # Parse "1: desc\n2: desc" format
                descriptions = {}
                for line in text.split("\n"):
                    line = line.strip()
                    if line and line[0].isdigit() and ":" in line:
                        idx_str, desc = line.split(":", 1)
                        try:
                            idx = int(idx_str.strip()) - 1
                            descriptions[idx] = desc.strip()
                        except ValueError:
                            pass
                results = []
                for i in range(len(batch)):
                    results.append(descriptions.get(i, text if len(batch) == 1 else "PARSE_FAIL"))
                return results
        except Exception as e:
            if attempt == 2:
                return [f"ERROR: {e}"] * len(batch)
            await asyncio.sleep(2 ** (attempt + 1))

    return ["ERROR: max retries"] * len(batch)


async def process_queue(items, source_name):
    """Process items with batch=4, concurrency=4."""
    results = [None] * len(items)
    semaphore = asyncio.Semaphore(CONCURRENCY)

    batches = []
    for i in range(0, len(items), BATCH_SIZE):
        batches.append((i, items[i:i + BATCH_SIZE]))

    done = [0]
    total = len(batches)

    async with aiohttp.ClientSession() as session:
        async def run_batch(start_idx, batch):
            async with semaphore:
                descs = await classify_batch(session, batch)
                for j, desc in enumerate(descs):
                    results[start_idx + j] = desc
                done[0] += 1
                if done[0] % 5 == 0 or done[0] == total:
                    print(f"  [{source_name}] {done[0]}/{total} batches done", flush=True)
                await asyncio.sleep(0.3)

        tasks = [run_batch(si, b) for si, b in batches]
        await asyncio.gather(*tasks)

    return results


# ─── Prepare phases ───────────────────────────────────────────────────────────

def prepare_mom():
    units = []
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            units.append({
                "name": r["name"].strip(),
                "sphere": r["sphere"].strip(),
                "slug": r["name"].strip().lower().replace(" ", "_").replace("'", ""),
            })

    items = []
    skip_results = []
    for u in units:
        if u["slug"] in KNOWN_GOOD:
            skip_results.append({**u, "source": "mom", "description": "KNOWN_GOOD"})
            continue
        img_path = MOM_ICONS_DIR / f"{u['slug']}.png"
        if not img_path.exists():
            skip_results.append({**u, "source": "mom", "description": "NO_FILE"})
            continue
        b64 = base64.b64encode(img_path.read_bytes()).decode()
        items.append({"label": f"UNIT_{u['slug'].upper()}", "b64": b64, "meta": u})

    return items, skip_results


def prepare_lotr():
    tgas = sorted(LOTR_DIR.rglob("*L.tga"))
    tgas = [t for t in tgas if "pictures" in str(t).lower()]
    print(f"  LotR: {len(tgas)} TGAs")

    items = []
    for tga in tgas:
        img = read_tga_to_pil(tga)
        if not img:
            continue
        b64 = img_to_b64(img)
        label = tga.stem.replace("L", "")
        items.append({"label": label, "b64": b64, "file": tga.name})

    return items


def prepare_homm2():
    if not HOMM2_SHEET.exists():
        return []
    sheet = Image.open(HOMM2_SHEET)
    COLS, ROWS = 8, 6
    CELL_W, CELL_H = sheet.width // COLS, sheet.height // ROWS
    items = []
    for row in range(ROWS):
        for col in range(COLS):
            x0, y0 = col * CELL_W, row * CELL_H
            cell = sheet.crop((x0, y0, x0 + CELL_W, y0 + CELL_H))
            b64 = img_to_b64(cell)
            items.append({"label": f"HoMM2_r{row}_c{col}", "b64": b64})
    return items


# ─── Main ─────────────────────────────────────────────────────────────────────

async def main():
    all_results = {}

    # Phase 1: MoM
    print("=== Phase 1: MoM (76 icons, ~19 batches) ===")
    mom_items, mom_skipped = prepare_mom()
    mom_descs = await process_queue(mom_items, "MoM")
    mom_results = list(mom_skipped)
    for i, desc in enumerate(mom_descs):
        mom_results.append({**mom_items[i]["meta"], "source": "mom", "description": desc})
    all_results["mom"] = mom_results

    # Phase 2: LotR
    print("\n=== Phase 2: LotR (~458 icons, ~115 batches) ===")
    lotr_items = prepare_lotr()
    lotr_descs = await process_queue(lotr_items, "LotR")
    lotr_results = []
    for i, desc in enumerate(lotr_descs):
        lotr_results.append({
            "name": lotr_items[i]["label"],
            "source": "lotr",
            "file": lotr_items[i].get("file", ""),
            "description": desc,
        })
    all_results["lotr"] = lotr_results

    # Phase 3: HoMM2
    print("\n=== Phase 3: HoMM2 (48 cells, ~12 batches) ===")
    homm2_items = prepare_homm2()
    if homm2_items:
        homm2_descs = await process_queue(homm2_items, "HoMM2")
        homm2_results = []
        for i, desc in enumerate(homm2_descs):
            homm2_results.append({
                "name": homm2_items[i]["label"],
                "source": "homm2",
                "description": desc,
            })
        all_results["homm2"] = homm2_results

    # Save
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)

    # Summary
    print(f"\n{'='*60}")
    print(f"MoM: {len(mom_results)} | LotR: {len(lotr_results)} | HoMM2: {len(all_results.get('homm2', []))}")
    print(f"Saved to {OUT_PATH}")
    print(f"\nMoM classifications:")
    for r in mom_results:
        if r["description"] not in ("KNOWN_GOOD", "NO_FILE"):
            print(f"  {r['name']:20s} ({r['sphere']:8s}): {r['description'][:70]}")


if __name__ == "__main__":
    asyncio.run(main())
