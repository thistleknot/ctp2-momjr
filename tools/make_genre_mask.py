"""Build/refresh the genre-mask staging sheet for a merged control plane.

Purpose:
    Emit `<csvdir>/genre_mask.csv` — a reviewable inventory of every merged
    unit / advance / improvement, so out-of-genre content (modern military,
    sci-fi, industrial) can be commented and masked before generation. This is
    the staging control plane: the user edits the `mask` column (yes = drop),
    the `reason` column is free-text, and merge_control_planes --mask honors it.

    Rows carry a keyword pre-screen: obvious out-of-genre items default to
    mask=yes with a reason; everything else is blank for human review. An
    existing genre_mask.csv is MERGED (never clobbered) — user edits on ids
    already present are preserved; only genuinely new ids are appended.

Usage:
    make_genre_mask.py --csv <merged csv dir>

Motif kept: medieval / fantasy / bronze / hellenistic / iron age.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

# Case-insensitive substring keywords that mark a name as OUT of the
# bronze/iron/medieval/fantasy/hellenistic motif. Conservative — genuine
# ambiguities (Cannon, Artillery) are left for human review by NOT listing
# borderline terms that also fit fantasy (e.g. "cannon" ~ bombard).
OUT_OF_GENRE = {
    # modern naval / air / armor
    "aegis": "modern warship", "cruiser": "modern warship",
    "battleship": "modern warship", "destroyer": "modern warship",
    "submarine": "modern submarine", "carrier": "modern carrier",
    "aircraft": "aircraft", "fighter": "modern aircraft",
    "bomber": "modern aircraft", "helicopter": "helicopter",
    "gunship": "helicopter", "tank": "modern armor",
    "apc": "modern armor", "artillery": "modern artillery",
    # firearms / gunpowder / modern infantry (post-medieval; a bronze/iron/
    # hellenistic/medieval motif has no gunpowder — flag it, review in sheet)
    "machine gun": "firearms", "paratrooper": "modern infantry",
    "cavalry brigade": "modern cavalry", "mech. inf": "modern infantry",
    "mech inf": "modern infantry", "mechanized": "modern infantry",
    "marines": "modern infantry", "alpine": "modern infantry",
    "armor": "modern armor", "howitzer": "modern artillery",
    "cannon": "gunpowder artillery", "musket": "gunpowder",
    "rifle": "firearms", "cruise": "missile", "missile": "missile",
    "stealth": "modern aircraft", "stlth": "modern aircraft",
    "destroyer": "modern warship", "mobile saw": "modern",
    # sci-fi / future
    "nuclear": "nuclear", "plasma": "sci-fi", "laser": "sci-fi",
    "robot": "sci-fi", "cyborg": "sci-fi", "mech ": "sci-fi",
    "war walker": "sci-fi", "space": "sci-fi", "fusion": "sci-fi",
    "antimatter": "sci-fi", "nanite": "sci-fi", "cyber": "sci-fi",
    "star ": "sci-fi", "orbital": "sci-fi", "plasmatica": "sci-fi",
    # industrial / modern civic + techs
    "urban planner": "modern civic", "corporate": "modern economy",
    "television": "modern media", "subway": "modern infra",
    "mag-lev": "modern infra", "maglev": "modern infra",
    "railroad": "industrial (remapped)", "automobile": "industrial",
    "ecoterrorist": "modern", "eco ranger": "modern",
    "troop ship": "modern transport", "freight": "modern logistics",
    "conscription": "modern doctrine", "democracy": "modern govt",
    "computer": "sci-fi", "electronics": "industrial",
    "nuclear power": "modern power", "nuclear fission": "modern",
    "genetic": "modern science", "gene ": "modern science",
    # structural junk from civ2 scenario merges: HoMM2 town-buildings that
    # come in as cost-99 pseudo-units, and redundant faction hero-settlers
    # (7 near-identical "X Hero (Settler)" — the generic Peasants/Settlers
    # already cover city founding).
    "dragon city": "pseudo-building (town-as-unit)",
    "city of the dead": "pseudo-building (town-as-unit)",
    "xanadu": "pseudo-building (creature dwelling)",
    "hero (settler)": "redundant faction hero-settler",
}

DIMENSIONS = (("unit", "units.csv", "UNIT_"),
              ("advance", "advances.csv", "ADVANCE_"),
              ("improve", "improvements.csv", "IMPROVE_"))

AGE_ORDER = ["AGE_ONE", "AGE_TWO", "AGE_THREE", "AGE_FOUR", "AGE_FIVE",
             "AGE_SIX", "AGE_SEVEN", "AGE_EIGHT", "AGE_NINE", "AGE_TEN"]


def sanitize(name: str) -> str:
    s = name.upper().replace(" ", "_").replace("'", "").replace("-", "_")
    return re.sub(r"[^A-Z0-9_]", "", s)


def load_advance_ages(scenario: Path) -> dict[str, str]:
    """ADVANCE_X -> AGE_Y from the generated Advance.txt (default AGE_ONE)."""
    path = scenario / "default/gamedata/Advance.txt"
    ages: dict[str, str] = {}
    if not path.exists():
        return ages
    text = path.read_text(encoding="latin-1")
    for m in re.finditer(r"^(ADVANCE_\w+) \{(.*?)^\}", text, re.M | re.S):
        a = re.search(r"Age (AGE_\w+)", m.group(2))
        ages[m.group(1)] = a.group(1) if a else "AGE_ONE"
    return ages


def load_code_map(csv_dir: Path) -> dict[tuple[str, str], str]:
    """(lane, code) -> ADVANCE_X from advance_code_map.csv."""
    path = csv_dir / "advance_code_map.csv"
    out: dict[tuple[str, str], str] = {}
    if not path.exists():
        return out
    with path.open(newline="", encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            out[(r["lane"], r["code"])] = r["advance"]
    return out


def age_index(age: str) -> int:
    return AGE_ORDER.index(age) if age in AGE_ORDER else 0


def prescreen(name: str) -> str:
    low = name.lower()
    for kw, reason in OUT_OF_GENRE.items():
        if kw in low:
            return reason
    return ""


def load_existing(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return {r["id"]: r for r in csv.DictReader(fh)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, required=True, help="merged csv dir")
    parser.add_argument("--scenario", type=Path, default=None,
                        help="generated scenario dir (enables age-gate)")
    parser.add_argument("--max-age", default="AGE_FOUR",
                        help="highest kept advance Age; anything past it is masked "
                             "(default AGE_FOUR = bronze/hellenistic/iron/medieval)")
    args = parser.parse_args()
    csv_dir = args.csv
    out = csv_dir / "genre_mask.csv"
    existing = load_existing(out)

    # Age-gate inputs (principled era cut): advance -> age, unit/improve prereq
    # code -> advance -> age. Anything past --max-age is out of the motif.
    ages = load_advance_ages(args.scenario) if args.scenario else {}
    codemap = load_code_map(csv_dir)
    cutoff = age_index(args.max_age)

    def era_reason(dim: str, name: str, prereq: str) -> str:
        """Return an era reason if this entity is gated past the cutoff."""
        if dim == "advance":
            a = "ADVANCE_" + sanitize(name)
            if a in ages and age_index(ages[a]) > cutoff:
                return f"era: {ages[a]}"
        else:  # unit / improve — resolve prereq code -> advance -> age
            code = (prereq or "").strip()
            if code and code.lower() not in ("no", "nil", ""):
                a = codemap.get(("unit", code)) or codemap.get(("prereq", code))
                if a and a in ages and age_index(ages[a]) > cutoff:
                    return f"era: {ages[a]} (via {a[8:]})"
        return ""

    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    kept_existing = 0
    for dim, fname, prefix in DIMENSIONS:
        path = csv_dir / fname
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                name = (r.get("name") or "").strip()
                if not name:
                    continue
                ident = prefix + sanitize(name)
                if ident in seen:
                    continue
                seen.add(ident)
                if ident in existing:
                    rows.append(existing[ident])  # preserve user edits verbatim
                    kept_existing += 1
                    continue
                # NEVER auto-flag base (curated) content: it is the working,
                # era-appropriate foundation, and CTP2's advance-ages misclassify
                # some medieval/fantasy items (Merchant's Guild via ECONOMICS=
                # AGE_FIVE). Genre-masking targets MERGED-source content only.
                # (A user may still hand-set mask=yes on a base row.)
                source = r.get("source", "base")
                if source == "base":
                    reason = ""
                else:
                    # Age-gate first (principled), keyword screen as backstop.
                    reason = era_reason(dim, name, r.get("prereq", "")) or prescreen(name)
                rows.append({
                    "dimension": dim, "id": ident, "name": name,
                    "source": source,
                    "mask": "yes" if reason else "",
                    "reason": reason,
                })

    header = ["dimension", "id", "name", "source", "mask", "reason"]
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=header, lineterminator="\r\n",
                           extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    flagged = sum(1 for r in rows if (r.get("mask") or "").strip().lower() == "yes")
    print(f"wrote {out.name}: {len(rows)} rows, {flagged} pre-flagged mask=yes, "
          f"{kept_existing} existing edits preserved")
    print("Review the blank 'mask' cells; set 'yes' to drop, add a 'reason'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
