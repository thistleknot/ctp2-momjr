"""Extract buildings from wiki corpus → buildings_wiki.csv.

This supplements (not replaces) the existing improvements.csv. It provides
terrain_prereq, race restrictions, and detailed effects from the wiki that
the Civ2 spine doesn't carry.

Run: python -m wiki_import.extract_buildings
From: Scenarios/mom/tools/
"""
import csv
import re
from collections import Counter

from .common import load_corpus, strip_furniture, sanitize_ident, extract_number, extract_field, OUTPUT_DIR

OUTPUT_CSV = OUTPUT_DIR / "buildings_wiki.csv"

# Known MoM building names (for matching)
_BUILDING_KEYWORDS = [
    "sawmill", "smithy", "stable", "stables", "shrine", "temple", "library",
    "university", "guild", "barracks", "armory", "fortress", "granary",
    "marketplace", "bank", "oracle", "cathedral", "builder's hall",
    "animists", "sage's tower", "war college", "ship yard", "shipwright",
    "parthenon", "alchemist", "wizard's guild", "miner's guild",
    "mechanicians", "farmer's market", "forester's guild", "maritime guild",
    "fantastic stable", "fighter's guild", "armorer's guild",
    "war college", "amplifying tower", "coal",
]


def _is_building_page(title: str, text: str) -> bool:
    """Heuristic: is this a building/city improvement page?"""
    tl = title.lower()
    xl = text[:500].lower() if text else ""

    if any(kw in tl for kw in _BUILDING_KEYWORDS):
        return True
    if "construction cost" in xl and ("upkeep" in xl or "maintenance" in xl):
        if "building" in xl or "town" in xl or "city" in xl:
            return True
    return False


def _extract_building(title: str, text: str) -> dict | None:
    """Extract building data from a wiki page."""
    text = strip_furniture(text)

    name = title.strip()
    cost = extract_number(text, r"(?:Construction|Build(?:ing)?) Cost")
    upkeep = extract_number(text, r"(?:Upkeep|Maintenance)")
    prerequisite = extract_field(text, r"Prerequisite") or ""
    replaces = extract_field(text, r"Replaces") or ""

    # Terrain requirement extraction
    terrain_prereq = ""
    tl = text.lower()
    if "requires" in tl and "forest" in tl:
        terrain_prereq = "TERRAIN_FOREST"
    elif "requires" in tl and ("hill" in tl or "mountain" in tl):
        terrain_prereq = "TERRAIN_HILL|TERRAIN_MOUNTAIN"
    elif "shore" in tl or "coast" in tl or "river mouth" in tl:
        if "requires" in tl or "must be" in tl or "only" in tl:
            terrain_prereq = "TERRAIN_WATER_SHALLOW"

    # Race restriction
    race_restrict = ""
    race_pat = re.search(r"(?:only|exclusive to|available to)\s+(.+?)(?:\.|,|\n)", text, re.I)
    if race_pat:
        race_restrict = race_pat.group(1).strip()

    # Description
    lines = [l.strip() for l in text.split("\n") if l.strip() and len(l.strip()) > 20]
    desc = lines[0] if lines else ""
    if len(desc) > 200:
        last_period = desc[:200].rfind(".")
        desc = desc[:last_period + 1] if last_period > 60 else desc[:200]

    return {
        "ident": f"IMPROVE_{sanitize_ident(name)}",
        "name": name,
        "cost": cost or 0,
        "upkeep": upkeep or 0,
        "prerequisite": prerequisite,
        "replaces": replaces,
        "terrain_prereq": terrain_prereq,
        "race_restriction": race_restrict,
        "description": desc,
    }


def main():
    corpus = load_corpus()
    buildings = []

    for page in corpus:
        title = page["t"]
        text = page.get("x", "")
        if _is_building_page(title, text):
            bld = _extract_building(title, text)
            if bld:
                buildings.append(bld)

    # Deduplicate
    seen = set()
    unique = []
    for b in buildings:
        if b["ident"] not in seen:
            seen.add(b["ident"])
            unique.append(b)
    buildings = unique

    print(f"  extracted: {len(buildings)} buildings")
    # Terrain gating found
    gated = [b for b in buildings if b["terrain_prereq"]]
    print(f"  terrain-gated: {len(gated)}")
    for b in gated:
        print(f"    {b['name']}: {b['terrain_prereq']}")

    # Write CSV
    fieldnames = ["ident", "name", "cost", "upkeep", "prerequisite", "replaces",
                  "terrain_prereq", "race_restriction", "description"]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(buildings)

    print(f"  wrote {OUTPUT_CSV} ({len(buildings)} rows)")


if __name__ == "__main__":
    main()
