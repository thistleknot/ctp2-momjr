"""Faction/sphere-gate units — build the reviewable taxonomy and set prereqs.

Purpose:
    Replaces flat cost-tiering with FACTION identity. Each unit is assigned a
    magic sphere (life/nature/death/chaos/sorcery) or 'neutral', inferred from
    its creature type and overridden by explicit design assignments. It then
    gates on that sphere's advance ladder at a tier derived from cost:
    LORE (cheap) -> ADEPT -> MAGE -> WIZARD -> MASTER (elite). So a Nature tribe
    researching Nature magic unlocks its Fae units, Death unlocks undead, etc.

    Writes TWO things:
      1. unit_factions.csv  — the reviewable taxonomy control plane
         (unit_id, name, cost, sphere, tier, gate_code, gate_advance). Edit
         'sphere'/'tier' here to correct the seed; re-run preserves edits.
      2. units.csv prereq   — set to the sphere-ladder gate code.

    Runs post-mask, pre-generator. Units with a real non-sphere prereq
    (MoM heroes on Mys) and units on the STARTER_WHITELIST keep it.

    Sphere precedence, strongest first:
      1. an explicit `sphere` column in units.csv  — the curated control plane
      2. a curated prior edit in unit_factions.csv
      3. keyword inference from the unit name
    (1) exists because MoM's plane now carries a hand-adjudicated `sphere`
    column; keyword inference is a seed for planes that do not have one yet
    (SMM), not an authority that may override a human decision.

Usage:
    assign_unit_factions.py --csv <merged csv dir>
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

NO_PREREQ = {"no", "nil", ""}

# Sphere ladder -> gate code per tier (from advance_code_map, unit lane).
# All ladders are AGE_TWO; tier within the ladder sets how deep you research.
SPHERE_LADDER = {
    "life":    {"lore": "Inv", "adept": "Lab", "mage": "Las", "wizard": "Too", "master": "Mag"},
    "nature":  {"lore": "Plu", "adept": "PT",  "mage": "Rad", "wizard": "Rec", "master": "Ref"},
    "death":   {"lore": "Rfg", "adept": "Rob", "mage": "SFl", "wizard": "Sth", "master": "SE"},
    "chaos":   {"lore": "MP",  "adept": "Med", "mage": "Met", "wizard": "Min", "master": "Mob"},
    "sorcery": {"lore": "The", "adept": "X2",  "mage": "NP",  "wizard": "Phy", "master": "Pla"},
}
TIER_ORDER = ["lore", "adept", "mage", "wizard", "master"]

# Creature-type -> sphere inference (first match wins; order matters).
SPHERE_KEYWORDS = [
    ("death",   ["skeleton", "zombie", "wraith", "undead", "bone", "ghoul",
                 "vampire", "lich", "wight", "necro", "shade", "minion",
                 "death", "malleus", "rjak", "barrow", "mummy", "ghost",
                 "spectral", "phantom", "witch", "baba yaga"]),
    ("nature",  ["centaur", "elf", "elven", "halfling", "sprite", "faerie",
                 "unicorn", "pegasus", "griffin", "treant", "dryad", "faun",
                 "alorra", "warbear", "cockatrice", "wolf", "hawk", "bear", "boar",
                 "great wyrm", "behemoth", "mammoth", "gnome", "tree",
                 "eagle", "spider", "ranger", "dwarf", "dwarves", "otterine"]),
    ("chaos",   ["goblin", "efreet", "salamander", "hell", "chaos", "orc",
                 "troll", "hydra", "warrax", "tauron", "hound", "fire",
                 "demon", "infernal", "gargoyle", "minotaur", "fanatic",
                 "dragon", "cyclops", "ogre", "berserk", "infidel", "horror",
                 "kraken", "imp", "beholder", "harpy", "manticore",
                 "basilisk", "wyvern", "medusa"]),
    ("life",    ["angel", "archangel", "paladin", "priest", "cleric", "healer",
                 "guardian", "serena", "ariel", "monk", "crusader",
                 "templar", "knight hosp", "prophet", "zealot"]),
    ("sorcery", ["elemental", "phantom warrior", "storm", "djinn", "genie",
                 "jafar", "warlock", "sorcer", "air ", "water", "earth",
                 "wind", "merman", "mermen", "merfolk", "merguard",
                 "porpoise", "triton", "naga", "siren", "wizard", "mage",
                 "changeling", "golem"]),
]

# Explicit design overrides (user-directed). name-substring -> sphere.
EXPLICIT = {
    "centaur": "nature", "halfling": "nature", "elf warrior": "nature",
    "goblin": "chaos",       # barbarian-aligned -> chaos ladder for now
    "skeleton": "death",
    "mermen": "sorcery", "minotaur": "chaos", "infidel": "chaos",
    # "H." = Hobgoblin in the midgard source (user-confirmed) — a chaos
    # creature, never a human line unit.
    "h. warriors": "chaos",
    "housecarl": "gated_neutral",
}

# Turn-1 units: STRICT whitelist. Everything else gets a gate — sphere ladder
# for creatures, the generic military ladder for mundane humans. The old
# cost<=2 heuristic leaked Mermen/H. Warriors/Infidels into every civ's
# turn-1 build list (user-reported three times).
STARTER_WHITELIST = {
    "peasant", "peasants", "settler", "settlers", "migrant", "warrior",
    "spearman", "spearmen", "spearman militia", "hoplite militia",
    "club warrior", "slinger", "town watch", "tribal leader", "emissary",
    "envoy", "coracle", "reed boat", "boat",
}

# Generic military ladder for GATED mundane units (base MoM advance codes,
# unit lane): tiered like the sphere ladders but open to every civ.
NEUTRAL_LADDER = {"lore": "War", "adept": "Bro", "mage": "Iro",
                  "wizard": "Feu", "master": "Chi"}


def sanitize(name: str) -> str:
    s = name.upper().replace(" ", "_").replace("'", "").replace("-", "_")
    return re.sub(r"[^A-Z0-9_]", "", s)


def cost_num(v: str) -> int:
    return int(re.sub(r"[^0-9]", "", str(v)) or 0)


def infer_sphere(name: str) -> str:
    low = name.lower()
    for key, sphere in EXPLICIT.items():
        if key in low:
            return sphere
    for sphere, kws in SPHERE_KEYWORDS:
        if any(k in low for k in kws):
            return sphere
    return "neutral"


def cost_to_tier(cost: int) -> str:
    if cost <= 4:   return "lore"
    if cost <= 8:   return "adept"
    if cost <= 15:  return "mage"
    if cost <= 40:  return "wizard"
    return "master"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, required=True)
    args = parser.parse_args()
    csv_dir = args.csv

    # Preserve prior taxonomy edits.
    tax_path = csv_dir / "unit_factions.csv"
    prior: dict[str, dict[str, str]] = {}
    if tax_path.exists():
        with tax_path.open(newline="", encoding="utf-8-sig") as fh:
            prior = {r["unit_id"]: r for r in csv.DictReader(fh)}

    upath = csv_dir / "units.csv"
    with upath.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        header = reader.fieldnames
        rows = list(reader)

    tax_rows = []
    from collections import Counter
    counts = Counter()
    for r in rows:
        name = (r.get("name") or "").strip()
        if not name:
            continue
        uid = "UNIT_" + sanitize(name)
        cost = cost_num(r.get("cost", "0"))
        prereq = (r.get("prereq") or "").strip().lower()

        source = r.get("source", "")
        edit = prior.get(uid, {})
        # An explicit `sphere` column in units.csv outranks everything: it is a
        # hand-adjudicated control-plane decision, not a machine seed. Planes
        # without the column (SMM) fall through to the prior-edit/keyword path
        # exactly as before.
        column_sphere = (r.get("sphere") or "").strip()
        if column_sphere not in set(SPHERE_LADDER) | {"gated_neutral", "neutral"}:
            column_sphere = ""
        # A prior sphere counts as a curated EDIT only when it names a real
        # cluster; machine seeds (starter/neutral/base/gated) re-infer so
        # keyword/whitelist fixes actually take effect on re-run.
        prior_sphere = (edit.get("sphere") or "").strip()
        if prior_sphere not in set(SPHERE_LADDER) | {"gated_neutral"}:
            prior_sphere = ""
        inferred = column_sphere or prior_sphere or infer_sphere(name)

        if (name.lower() in STARTER_WHITELIST and not prior_sphere
                and column_sphere not in SPHERE_LADDER):
            # true turn-1 generics only — strict whitelist, never cost-derived
            sphere = "starter"
            tier = ""
            gate_code = r.get("prereq", "")
            counts[sphere] += 1
        elif source == "base" and inferred not in set(SPHERE_LADDER) | {"gated_neutral"}:
            # BASE (curated MoM) units keep their prereq verbatim unless a
            # cluster explicitly claims them (e.g. Minotaur 'War' -> chaos).
            sphere = "base"
            tier = ""
            gate_code = r.get("prereq", "")
            counts[sphere] += 1
        elif prereq not in NO_PREREQ and inferred == "neutral" and source != "base":
            # merged unit with a real source tech gate and no cluster claim
            sphere = "gated"
            tier = ""
            gate_code = r.get("prereq", "")
            counts[sphere] += 1
        else:
            sphere = inferred
            # dragons are elite/event units regardless of cost -> MASTER tier
            tier = edit.get("tier") or ("master" if "dragon" in name.lower()
                                        else cost_to_tier(cost))
            if sphere in SPHERE_LADDER:
                # Faction units ALWAYS gate on their sphere (LORE minimum),
                # even cheap ones — that IS the faction identity. A Death
                # tribe's basic skeleton requires Death Lore.
                gate_code = SPHERE_LADDER[sphere].get(tier, SPHERE_LADDER[sphere]["lore"])
                r["prereq"] = gate_code
            else:
                # mundane human unit -> generic military ladder (open to all
                # civs, but NEVER ungated). Catches gated_neutral overrides
                # and merged units that arrived with no tech gate.
                sphere = "gated_neutral"
                gate_code = NEUTRAL_LADDER.get(tier, NEUTRAL_LADDER["lore"])
                r["prereq"] = gate_code
            counts[sphere] += 1

        gate_adv = ""
        tax_rows.append({"unit_id": uid, "name": name, "cost": str(cost),
                         "sphere": sphere, "tier": tier, "gate_code": gate_code,
                         "gate_advance": gate_adv, "source": r.get("source", ""),
                         # `basis` is authored prose recording WHY a sphere was
                         # chosen. Carried through verbatim so a re-run never
                         # silently discards the adjudication record.
                         "basis": edit.get("basis", "")})

    with upath.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=header, lineterminator="\r\n", extrasaction="ignore")
        w.writeheader(); w.writerows(rows)

    tax_header = ["unit_id", "name", "cost", "sphere", "tier", "gate_code",
                  "gate_advance", "source", "basis"]
    with tax_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=tax_header, lineterminator="\r\n", extrasaction="ignore")
        w.writeheader(); w.writerows(tax_rows)

    print(f"unit_factions.csv: {len(tax_rows)} units")
    print("gated by sphere:", dict(counts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
