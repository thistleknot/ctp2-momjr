"""Validate unit icons via nemotron vision. Score each against its name."""
import asyncio
import base64
import csv
import json
import sys
from pathlib import Path

import aiohttp

API_KEY = "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"
MODEL = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"
URL = "https://integrate.api.nvidia.com/v1/chat/completions"
HEADERS = {"Authorization": f"Bearer {API_KEY}", "Accept": "application/json"}

IMG_DIR = Path(__file__).parent / "img" / "units"
CSV_PATH = Path(__file__).parent.parent / "tools" / "momjr_csv" / "units.csv"
OUT_PATH = Path(__file__).parent / "icon_validation.json"

CONCURRENCY = 4


async def validate_one(session, sem, slug, unit_name, sphere):
    img_path = IMG_DIR / f"{slug}.png"
    if not img_path.exists():
        return {"slug": slug, "name": unit_name, "score": 0, "reason": "NO_FILE"}

    b64 = base64.b64encode(img_path.read_bytes()).decode()
    prompt = (
        f"This image should depict a fantasy game unit called '{unit_name}' "
        f"(sphere: {sphere}). "
        f"Score 0-100 how well the image matches that identity. "
        f"0 = completely wrong (modern cars, graphs, chalkboards, sci-fi). "
        f"50 = vaguely related but wrong creature type. "
        f"100 = perfect match. "
        f"Reply ONLY with: SCORE: <number> REASON: <5 words what you see>"
    )

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
        ]}],
        "max_tokens": 50,
        "temperature": 0.1,
        "stream": False,
    }

    async with sem:
        for attempt in range(3):
            try:
                async with session.post(URL, json=payload, headers=HEADERS,
                                        timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    if resp.status == 429 or resp.status >= 500:
                        await asyncio.sleep(2 ** (attempt + 1))
                        continue
                    resp.raise_for_status()
                    data = await resp.json()
                    text = data["choices"][0]["message"]["content"].strip()
                    score = 0
                    reason = text
                    if "SCORE:" in text.upper():
                        parts = text.upper().split("SCORE:")[1].strip()
                        score_str = ""
                        for ch in parts:
                            if ch.isdigit():
                                score_str += ch
                            elif score_str:
                                break
                        score = int(score_str) if score_str else 0
                    if "REASON:" in text.upper():
                        reason = text.split("REASON:")[-1].strip()
                    return {"slug": slug, "name": unit_name, "score": score, "reason": reason}
            except Exception as e:
                if attempt == 2:
                    return {"slug": slug, "name": unit_name, "score": -1, "reason": f"ERROR: {e}"}
                await asyncio.sleep(2 ** (attempt + 1))
    return {"slug": slug, "name": unit_name, "score": -1, "reason": "MAX_RETRIES"}


async def main():
    # If args provided, only check those slugs. Otherwise check all.
    check_slugs = sys.argv[1:] if len(sys.argv) > 1 else None

    units = []
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            name = r["name"].strip()
            slug = name.lower().replace(" ", "_").replace("'", "")
            sphere = r["sphere"].strip()
            if check_slugs is None or slug in check_slugs:
                units.append({"name": name, "slug": slug, "sphere": sphere})

    print(f"Validating {len(units)} icons...")
    sem = asyncio.Semaphore(CONCURRENCY)

    async with aiohttp.ClientSession() as session:
        tasks = [validate_one(session, sem, u["slug"], u["name"], u["sphere"]) for u in units]
        results = await asyncio.gather(*tasks)

    # Save
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    passed = [r for r in results if r["score"] >= 50]
    failed = [r for r in results if 0 <= r["score"] < 50]
    errors = [r for r in results if r["score"] < 0]

    print(f"\nPASSED (>= 50): {len(passed)}")
    for r in sorted(passed, key=lambda x: -x["score"]):
        print(f"  {r['name']:20s} score={r['score']:3d}  {r['reason'][:50]}")

    if failed:
        print(f"\nFAILED (< 50): {len(failed)}")
        for r in sorted(failed, key=lambda x: x["score"]):
            print(f"  {r['name']:20s} score={r['score']:3d}  {r['reason'][:50]}")

    if errors:
        print(f"\nERRORS: {len(errors)}")
        for r in errors:
            print(f"  {r['name']:20s} {r['reason'][:60]}")


if __name__ == "__main__":
    asyncio.run(main())
