"""Sample 20 random unit icons, validate via nemotron. All must score >= 50."""
import asyncio
import base64
import csv
import random
from pathlib import Path

import aiohttp

API_KEY = "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"
MODEL = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"
URL = "https://integrate.api.nvidia.com/v1/chat/completions"
HEADERS = {"Authorization": f"Bearer {API_KEY}", "Accept": "application/json"}
IMG_DIR = Path(__file__).parent / "img" / "units"
CSV_PATH = Path(__file__).parent.parent / "tools" / "momjr_csv" / "units.csv"


async def check(session, sem, slug, name, sphere):
    img_path = IMG_DIR / f"{slug}.png"
    if not img_path.exists():
        return name, 0, "NO_FILE"
    b64 = base64.b64encode(img_path.read_bytes()).decode()
    prompt = (
        f"This image should depict a fantasy unit called '{name}' (sphere: {sphere}). "
        f"Score 0-100 how well it matches. 0=completely wrong (modern/sci-fi). 100=perfect. "
        f"Reply ONLY: SCORE: <number> REASON: <5 words>"
    )
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
        ]}],
        "max_tokens": 50, "temperature": 0.1, "stream": False,
    }
    async with sem:
        for attempt in range(3):
            try:
                async with session.post(URL, json=payload, headers=HEADERS,
                                        timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    if resp.status >= 500 or resp.status == 429:
                        await asyncio.sleep(2 ** (attempt + 1))
                        continue
                    resp.raise_for_status()
                    data = await resp.json()
                    text = data["choices"][0]["message"]["content"].strip()
                    score = 0
                    if "SCORE:" in text.upper():
                        s = text.upper().split("SCORE:")[1].strip()
                        digits = ""
                        for ch in s:
                            if ch.isdigit():
                                digits += ch
                            elif digits:
                                break
                        score = int(digits) if digits else 0
                    reason = text.split("REASON:")[-1].strip() if "REASON:" in text.upper() else text
                    return name, score, reason
            except Exception as e:
                if attempt == 2:
                    return name, -1, str(e)
                await asyncio.sleep(2 ** (attempt + 1))
    return name, -1, "MAX_RETRIES"


async def main():
    units = []
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            name = r["name"].strip()
            slug = name.lower().replace(" ", "_").replace("'", "")
            sphere = r["sphere"].strip()
            units.append((slug, name, sphere))

    random.seed(42)
    random.shuffle(units)
    sample = units[:20]

    print(f"Sampling 20 of {len(units)} units...")
    sem = asyncio.Semaphore(4)
    async with aiohttp.ClientSession() as session:
        tasks = [check(session, sem, s, n, sp) for s, n, sp in sample]
        results = await asyncio.gather(*tasks)

    passed = 0
    failed = []
    for name, score, reason in sorted(results, key=lambda x: -x[1]):
        status = "PASS" if score >= 50 else "FAIL"
        if score >= 50:
            passed += 1
        else:
            failed.append((name, score, reason))
        print(f"  {status} {name:20s} score={score:3d}  {reason[:50]}")

    print(f"\nResult: {passed}/20 PASSED, {len(failed)} FAILED")
    if not failed:
        print("ALL 20 PASS. Confidence threshold met.")
    else:
        print("FAILURES present. Fixing required.")
        for name, score, reason in failed:
            print(f"  FIX NEEDED: {name} ({reason})")


if __name__ == "__main__":
    asyncio.run(main())
