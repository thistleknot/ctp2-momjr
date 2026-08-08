"""Extract spells from mom spells.txt spine + wiki corpus detail → spells.csv.

The spine (mom spells.txt) provides authoritative numbers: name, sphere, rarity,
type, target, overland_cost, combat_cost, upkeep, research_cost.
The wiki corpus adds: description, effect detail, effect_kind classification.

Run: python -m wiki_import.extract_spells
From: Scenarios/mom/tools/
"""
import csv
import re
from pathlib import Path

from .common import load_corpus, strip_furniture, sanitize_ident, OUTPUT_DIR

SPINE_PATH = Path(r"C:\Users\user\Documents\wiki\games\ctp2\mom spells.txt")
OUTPUT_CSV = OUTPUT_DIR / "spells.csv"

# Effect kind classification based on spell type
_EFFECT_KIND_MAP = {
    "summoning spell": "summon",
    "unit enchantment": "unit_enchant",
    "town enchantment": "city_enchant",
    "global enchantment": "global_enchant",
    "instant spell": "instant_damage",
    "combat instant": "instant_damage",
    "combat enchantment": "unit_enchant",
    "city curse": "city_enchant",
    "unit curse": "unit_enchant",
}


def _parse_cost(s: str) -> int:
    """Parse a cost field: may be '--', 'Special', '10+', or a number with junk chars."""
    s = s.strip().replace("\xad", "").replace(",", "")  # soft hyphens, commas
    if not s or s == "--" or s.lower() == "special" or s == "n/a*":
        return 0
    # Strip trailing + (e.g. "200+")
    s = s.rstrip("+")
    try:
        return int(s)
    except ValueError:
        # Try extracting just digits
        digits = re.sub(r"[^\d]", "", s)
        return int(digits) if digits else 0


def _parse_spine() -> list[dict]:
    """Parse mom spells.txt into structured spell records."""
    lines = SPINE_PATH.read_text(encoding="utf-8").splitlines()
    spells = []
    current_sphere = "arcane"

    for line in lines:
        # Detect sphere headers
        if line.startswith("List of ") and "Spells" in line:
            sphere_match = re.match(r"List of (\w+) Spells", line)
            if sphere_match:
                current_sphere = sphere_match.group(1).lower()
            continue

        # Skip non-data lines
        if not line.strip() or line.startswith("Sign In") or line.startswith("Edit"):
            continue
        if line.startswith("The following") or line.startswith("Name\t"):
            continue
        if line.strip().isdigit():  # section numbers
            continue
        if line.startswith("Source:"):
            continue

        # Parse tab-delimited spell data
        parts = line.split("\t")
        # Arcane has 7 fields (no Rarity), Life+ has 8 fields (with Rarity)
        if len(parts) < 6:
            continue

        # Clean soft hyphens from all fields
        parts = [p.replace("\xad", "").strip() for p in parts]

        if current_sphere == "arcane":
            # Arcane: Name, Type, Target, OverlandCost, CombatCost, Upkeep, Research
            if len(parts) < 7:
                continue
            name = parts[0].strip()
            rarity = "common"  # Arcane spells have no rarity
            spell_type = parts[1].strip()
            target = parts[2].strip()
            overland = _parse_cost(parts[3])
            combat = _parse_cost(parts[4])
            upkeep = _parse_cost(parts[5])
            research = _parse_cost(parts[6])
        else:
            # Life/Nature/Sorcery/Death/Chaos: Name, Rarity, Type, Target, Overland, Combat, Upkeep, Research
            if len(parts) < 8:
                continue
            name = parts[0].strip()
            rarity = parts[1].strip().lower()
            spell_type = parts[2].strip()
            target = parts[3].strip()
            overland = _parse_cost(parts[4])
            combat = _parse_cost(parts[5])
            upkeep = _parse_cost(parts[6])
            research = _parse_cost(parts[7])

        if not name or name.lower() == "name":
            continue

        # Classify effect kind
        effect_kind = _EFFECT_KIND_MAP.get(spell_type.lower(), "flavour")
        # Dispel-type spells
        if "dispel" in name.lower() or "disjunction" in name.lower():
            effect_kind = "dispel"

        spells.append({
            "name": name,
            "ident": f"SPELL_{sanitize_ident(name)}",
            "sphere": current_sphere,
            "rarity": rarity,
            "type": spell_type,
            "target": target,
            "overland_cost": overland,
            "combat_cost": combat,
            "upkeep": upkeep,
            "research_cost": research,
            "effect_kind": effect_kind,
            "description": "",
        })

    return spells


def _enrich_from_wiki(spells: list[dict]):
    """Match spells to wiki articles and extract descriptions."""
    corpus = load_corpus()
    # Build title -> article map
    wiki_by_title = {page["t"].lower(): page for page in corpus}

    matched = 0
    for spell in spells:
        # Try exact match first, then fuzzy
        key = spell["name"].lower()
        page = wiki_by_title.get(key)
        if page is None:
            # Try without "the" prefix or trailing "s"
            for variant in [key.rstrip("s"), "the " + key, key.replace("'s", "s")]:
                page = wiki_by_title.get(variant)
                if page:
                    break

        if page and page.get("x"):
            text = strip_furniture(page["x"])
            # Take first 200 chars as description (enough for game text)
            desc = text[:200].replace("\n", " ").strip()
            # Clean trailing partial sentence
            last_period = desc.rfind(".")
            if last_period > 80:
                desc = desc[:last_period + 1]
            spell["description"] = desc
            matched += 1

    print(f"  wiki enrichment: {matched}/{len(spells)} spells matched to articles")


def main():
    spells = _parse_spine()
    print(f"  spine parsed: {len(spells)} spells across {len(set(s['sphere'] for s in spells))} spheres")

    # Sphere breakdown
    from collections import Counter
    sphere_counts = Counter(s["sphere"] for s in spells)
    for sphere, count in sorted(sphere_counts.items()):
        print(f"    {sphere}: {count}")

    # Effect kind breakdown
    kind_counts = Counter(s["effect_kind"] for s in spells)
    print(f"  effect kinds: {dict(kind_counts)}")

    _enrich_from_wiki(spells)

    # Write CSV
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["ident", "name", "sphere", "rarity", "type", "target",
                  "overland_cost", "combat_cost", "upkeep", "research_cost",
                  "effect_kind", "description"]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(spells)

    print(f"  wrote {OUTPUT_CSV} ({len(spells)} rows)")


if __name__ == "__main__":
    main()
