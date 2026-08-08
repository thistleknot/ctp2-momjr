"""Survey the MoM wiki corpus and report bucket distribution.

Run: python -m wiki_import.survey
From: Scenarios/mom/tools/
"""
import json
import re
from pathlib import Path
from collections import Counter

WIKI_PATH = Path(r"F:\Documents\wiki\games\mom\site\index.json")


def load_corpus():
    """Load the wiki corpus. Returns list of {t, s, x} dicts."""
    return json.loads(WIKI_PATH.read_text(encoding="utf-8"))


def classify_page(title: str, text: str) -> str:
    """Heuristic bucket classification from title + text content."""
    tl = title.lower()
    xl = text[:500].lower() if text else ""

    # Spells
    if any(w in tl for w in ["spell", "enchant", "curse", "summon"]):
        return "spell"
    if "casting cost" in xl and "research" in xl:
        return "spell"

    # Heroes
    if "hero" in tl or "champion" in tl:
        return "hero"
    if "hero ability" in xl or "random abilities" in xl:
        return "hero"

    # Buildings
    if any(w in tl for w in ["sawmill", "smithy", "stable", "shrine", "temple",
                              "library", "university", "guild", "barracks",
                              "armory", "fortress", "granary", "marketplace",
                              "bank", "oracle", "cathedral", "builder's hall",
                              "animists", "sage's tower", "war college",
                              "ship yard", "parthenon", "alchemist"]):
        return "building"
    if "construction cost" in xl and "upkeep" in xl and "building" in xl:
        return "building"

    # Race units
    if any(w in tl for w in ["swordsmen", "spearmen", "pikemen", "halberdier",
                              "cavalry", "bowmen", "shaman", "magician",
                              "priests", "settlers", "engineers"]):
        return "race_unit"
    if "melee attack" in xl and "movement" in xl and "hit points" in xl:
        if "hero" not in tl and "champion" not in tl:
            return "race_unit"

    # Terrain / minerals
    if any(w in tl for w in ["terrain", "adamantium", "mithril", "gems",
                              "coal", "iron", "silver", "gold deposit",
                              "crysx", "quork", "nightshade", "wild game"]):
        return "terrain"

    # Encounter sites
    if any(w in tl for w in ["node", "lair", "keep", "dungeon", "cave",
                              "ruins", "tower", "temple (encounter)"]):
        return "encounter"

    # Retorts
    if "retort" in tl:
        return "retort"

    # Races (civilization descriptions)
    if any(w in tl for w in ["high men", "high elves", "dark elves", "halflings",
                              "gnolls", "klackons", "lizardmen", "draconians",
                              "dwarves", "trolls", "nomads", "barbarians",
                              "beastmen", "orcs"]):
        return "race"

    # Wizard / AI
    if "wizard" in tl or "ai " in tl:
        return "wizard"

    # Mechanics
    if any(w in tl for w in ["combat", "damage", "resistance", "movement",
                              "experience", "diplomacy", "trade", "economy"]):
        return "mechanics"

    return "other"


def main():
    corpus = load_corpus()
    print(f"Total pages: {len(corpus)}")
    print(f"Fields per entry: {list(corpus[0].keys())}")
    print()

    buckets = Counter()
    by_bucket: dict[str, list[str]] = {}
    for page in corpus:
        bucket = classify_page(page["t"], page.get("x", ""))
        buckets[bucket] += 1
        by_bucket.setdefault(bucket, []).append(page["t"])

    print("Bucket distribution:")
    for bucket, count in buckets.most_common():
        print(f"  {bucket:15s} {count:4d}")

    print()
    print("Sample titles per bucket:")
    for bucket in ["spell", "hero", "building", "race_unit", "terrain", "encounter", "retort"]:
        titles = by_bucket.get(bucket, [])
        print(f"\n  [{bucket}] ({len(titles)} pages)")
        for t in titles[:8]:
            print(f"    - {t}")
        if len(titles) > 8:
            print(f"    ... +{len(titles) - 8} more")


if __name__ == "__main__":
    main()
