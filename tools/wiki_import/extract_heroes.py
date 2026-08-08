"""Extract heroes from wiki corpus → heroes.csv.

Heroes are named unique units with stats, hire conditions, and random abilities.
Run: python -m wiki_import.extract_heroes
From: Scenarios/mom/tools/
"""
import csv
import re
from collections import Counter

from .common import load_corpus, strip_furniture, sanitize_ident, extract_number, extract_field, OUTPUT_DIR

OUTPUT_CSV = OUTPUT_DIR / "heroes.csv"

# Known hero names from the wiki (the ones with "the <Title>" format)
_HERO_TITLE_PAT = re.compile(
    r"^(.+?)\s+the\s+(.+)$", re.I
)


def _is_hero_page(title: str, text: str) -> bool:
    """Heuristic: is this page about a named hero?"""
    tl = title.lower()
    xl = text[:600].lower() if text else ""
    # Direct hero indicators
    if "hero" in tl and "hero ability" not in tl:
        return True
    if _HERO_TITLE_PAT.match(title):
        return True
    # Content indicators
    if "random abilities" in xl and ("hire" in xl or "cost" in xl):
        return True
    if "melee attack" in xl and "hit points" in xl and "hero" in xl:
        return True
    return False


def _extract_hero(title: str, text: str) -> dict | None:
    """Extract hero data from a wiki page."""
    text = strip_furniture(text)

    name = title.strip()
    melee = extract_number(text, r"Melee Attack(?: Strength)?")
    ranged = extract_number(text, r"Ranged Attack(?: Strength)?")
    defense = extract_number(text, r"Defense")
    resistance = extract_number(text, r"Resistance")
    hp = extract_number(text, r"Hit Points")
    movement = extract_number(text, r"Movement(?: Allowance)?")
    cost = extract_number(text, r"(?:Hiring|Hire) Cost")

    # Extract type/class
    hero_type = extract_field(text, r"Type") or ""
    if not hero_type:
        # Try to infer from title pattern
        m = _HERO_TITLE_PAT.match(title)
        if m:
            hero_type = m.group(2)

    # Description: first meaningful paragraph
    lines = [l.strip() for l in text.split("\n") if l.strip() and len(l.strip()) > 20]
    desc = lines[0] if lines else ""
    if len(desc) > 200:
        last_period = desc[:200].rfind(".")
        if last_period > 60:
            desc = desc[:last_period + 1]
        else:
            desc = desc[:200]

    return {
        "ident": f"HERO_{sanitize_ident(name)}",
        "name": name,
        "type": hero_type,
        "melee_attack": melee or 0,
        "ranged_attack": ranged or 0,
        "defense": defense or 0,
        "resistance": resistance or 0,
        "hit_points": hp or 0,
        "movement": movement or 0,
        "hire_cost": cost or 0,
        "description": desc,
    }


def main():
    corpus = load_corpus()
    heroes = []

    for page in corpus:
        title = page["t"]
        text = page.get("x", "")
        if _is_hero_page(title, text):
            hero = _extract_hero(title, text)
            if hero:
                heroes.append(hero)

    # Deduplicate by ident
    seen = set()
    unique = []
    for h in heroes:
        if h["ident"] not in seen:
            seen.add(h["ident"])
            unique.append(h)
    heroes = unique

    print(f"  extracted: {len(heroes)} heroes")
    # Type breakdown
    types = Counter(h["type"] for h in heroes if h["type"])
    for t, c in types.most_common(10):
        print(f"    {t}: {c}")

    # Write CSV
    fieldnames = ["ident", "name", "type", "melee_attack", "ranged_attack",
                  "defense", "resistance", "hit_points", "movement",
                  "hire_cost", "description"]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(heroes)

    print(f"  wrote {OUTPUT_CSV} ({len(heroes)} rows)")


if __name__ == "__main__":
    main()
