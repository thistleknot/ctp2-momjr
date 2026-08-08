"""Extract race-specific units from wiki corpus → race_units_wiki.csv.

These are the per-race military rosters (High Men Swordsmen, Klackon Stag Beetle, etc.)
that supplement the existing units.csv with race-specific detail.

Run: python -m wiki_import.extract_race_units
From: Scenarios/mom/tools/
"""
import csv
import re
from collections import Counter

from .common import load_corpus, strip_furniture, sanitize_ident, extract_number, extract_field, OUTPUT_DIR

OUTPUT_CSV = OUTPUT_DIR / "race_units_wiki.csv"

# MoM races
_RACES = [
    "barbarian", "beastmen", "dark elf", "dark elves", "draconian",
    "dwarf", "dwarves", "gnoll", "halfling", "high elf", "high elves",
    "high men", "klackon", "lizardmen", "lizardman", "nomad", "orc",
    "troll",
]


def _is_race_unit_page(title: str, text: str) -> bool:
    """Heuristic: is this a race-specific military unit page?"""
    tl = title.lower()
    xl = text[:600].lower() if text else ""

    # Must have combat stats
    if "melee attack" not in xl and "ranged attack" not in xl:
        return False
    if "hit points" not in xl:
        return False

    # Should NOT be a hero page
    if "hero" in xl[:100] or "champion" in tl:
        return False
    # Should NOT be a summoned creature (those are spells)
    if "summoning spell" in xl or "casting cost" in xl:
        return False

    # Race-specific indicators
    if any(race in tl for race in _RACES):
        return True
    # Generic military unit names
    if any(w in tl for w in ["swordsmen", "spearmen", "pikemen", "halberdier",
                              "cavalry", "bowmen", "settlers", "engineers",
                              "shaman", "magicians", "priests", "trireme",
                              "galley", "warship", "catapult"]):
        return True

    return False


def _extract_unit(title: str, text: str) -> dict | None:
    """Extract race unit data from a wiki page."""
    text = strip_furniture(text)

    name = title.strip()
    melee = extract_number(text, r"Melee Attack(?: Strength)?")
    ranged = extract_number(text, r"Ranged Attack(?: Strength)?")
    defense = extract_number(text, r"Defense")
    resistance = extract_number(text, r"Resistance")
    hp = extract_number(text, r"Hit Points")
    movement = extract_number(text, r"Movement(?: Allowance)?")
    cost = extract_number(text, r"(?:Construction|Build(?:ing)?) Cost")
    upkeep = extract_number(text, r"(?:Upkeep|Maintenance)")

    # Race detection from content
    race = ""
    for r in _RACES:
        if r in text[:300].lower():
            race = r.title()
            break

    # Building requirement
    requires_building = extract_field(text, r"Requires") or ""

    # Description
    lines = [l.strip() for l in text.split("\n") if l.strip() and len(l.strip()) > 20]
    desc = lines[0] if lines else ""
    if len(desc) > 200:
        last_period = desc[:200].rfind(".")
        desc = desc[:last_period + 1] if last_period > 60 else desc[:200]

    return {
        "ident": f"UNIT_{sanitize_ident(name)}",
        "name": name,
        "race": race,
        "melee_attack": melee or 0,
        "ranged_attack": ranged or 0,
        "defense": defense or 0,
        "resistance": resistance or 0,
        "hit_points": hp or 0,
        "movement": movement or 0,
        "build_cost": cost or 0,
        "upkeep": upkeep or 0,
        "requires_building": requires_building,
        "description": desc,
    }


def main():
    corpus = load_corpus()
    units = []

    for page in corpus:
        title = page["t"]
        text = page.get("x", "")
        if _is_race_unit_page(title, text):
            unit = _extract_unit(title, text)
            if unit:
                units.append(unit)

    # Deduplicate
    seen = set()
    unique = []
    for u in units:
        if u["ident"] not in seen:
            seen.add(u["ident"])
            unique.append(u)
    units = unique

    print(f"  extracted: {len(units)} race units")
    # Race breakdown
    races = Counter(u["race"] for u in units if u["race"])
    for r, c in races.most_common():
        print(f"    {r}: {c}")

    # Write CSV
    fieldnames = ["ident", "name", "race", "melee_attack", "ranged_attack",
                  "defense", "resistance", "hit_points", "movement",
                  "build_cost", "upkeep", "requires_building", "description"]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(units)

    print(f"  wrote {OUTPUT_CSV} ({len(units)} rows)")


if __name__ == "__main__":
    main()
