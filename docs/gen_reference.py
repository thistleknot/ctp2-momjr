"""Generate reference markdown pages from momjr_csv source data."""
import csv
import os
from pathlib import Path

CSV_DIR = Path(__file__).parent.parent / "tools" / "momjr_csv"
OUT_DIR = Path(__file__).parent / "reference"
OUT_DIR.mkdir(exist_ok=True)

# ─── UNITS ────────────────────────────────────────────────────────────────────

def gen_units():
    rows = []
    with open(CSV_DIR / "units.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            name = r["name"].strip()
            sphere = r["sphere"].strip()
            move = r["move"].strip()
            # parse stats like "3a" -> 3
            atk = r["attack"].replace("a", "").strip()
            dfn = r["defense"].replace("d", "").strip()
            hp = r["hp"].replace("h", "").strip()
            fp = r["firepower"].replace("f", "").strip()
            cost = r["cost"].strip()
            prereq = r["prereq"].strip()
            domain_code = r["domain"].strip()
            domain = {0: "Land", 1: "Air", 2: "Sea"}.get(int(domain_code), "Land") if domain_code.isdigit() else "Land"
            rows.append((sphere, name, atk, dfn, hp, fp, move, domain, cost, prereq))

    # Sort by sphere then name
    sphere_order = {"life": 0, "nature": 1, "sorcery": 2, "death": 3, "chaos": 4, "neutral": 5}
    rows.sort(key=lambda x: (sphere_order.get(x[0], 9), x[1]))

    lines = ["# Unit Stats\n"]
    lines.append("Complete unit roster generated from `units.csv`. Sorted by sphere.\n")
    lines.append("| Sphere | Unit | Atk | Def | HP | FP | Move | Domain | Cost | Prereq |")
    lines.append("|--------|------|-----|-----|----|----|------|--------|------|--------|")
    for sphere, name, atk, dfn, hp, fp, move, domain, cost, prereq in rows:
        lines.append(f"| {sphere.capitalize()} | {name} | {atk} | {dfn} | {hp} | {fp} | {move} | {domain} | {cost} | {prereq} |")

    lines.append(f"\n**Total: {len(rows)} units**\n")
    (OUT_DIR / "units.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"  units.md: {len(rows)} rows")


# ─── SPELLS ───────────────────────────────────────────────────────────────────

def gen_spells():
    rows = []
    with open(CSV_DIR / "spells.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            name = r["name"].strip()
            sphere = r["sphere"].strip()
            rarity = r["rarity"].strip()
            stype = r["type"].strip()
            overland = r["overland_cost"].strip()
            combat = r["combat_cost"].strip()
            upkeep = r["upkeep"].strip()
            research = r["research_cost"].strip()
            rows.append((sphere, rarity, name, stype, overland, combat, upkeep, research))

    sphere_order = {"arcane": 0, "life": 1, "nature": 2, "sorcery": 3, "death": 4, "chaos": 5}
    rarity_order = {"common": 0, "uncommon": 1, "rare": 2, "very rare": 3}
    rows.sort(key=lambda x: (sphere_order.get(x[0], 9), rarity_order.get(x[1], 9), x[2]))

    lines = ["# Spell List\n"]
    lines.append("Complete spell database generated from `spells.csv`. Sorted by sphere and rarity.\n")

    current_sphere = None
    for sphere, rarity, name, stype, overland, combat, upkeep, research in rows:
        if sphere != current_sphere:
            current_sphere = sphere
            lines.append(f"\n## {sphere.capitalize()} Spells\n")
            lines.append("| Spell | Rarity | Type | Overland | Combat | Upkeep | Research |")
            lines.append("|-------|--------|------|----------|--------|--------|----------|")
        lines.append(f"| {name} | {rarity.capitalize()} | {stype} | {overland} | {combat} | {upkeep} | {research} |")

    lines.append(f"\n**Total: {len(rows)} spells**\n")
    (OUT_DIR / "spells.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"  spells.md: {len(rows)} rows")


# ─── ADVANCES ─────────────────────────────────────────────────────────────────

def gen_advances():
    rows = []
    with open(CSV_DIR / "advances.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            name = r["name"].strip()
            prereq1 = r["prereq1"].strip()
            prereq2 = r["prereq2"].strip()
            epoch = r["epoch"].strip()
            cat_raw = r["category"].strip()
            # category has comments like "0    ; Chi" - extract the code
            cat_parts = cat_raw.split(";")
            cat_id = cat_parts[0].strip()
            abbrev = cat_parts[1].strip() if len(cat_parts) > 1 else ""
            rows.append((cat_id, name, abbrev, prereq1, prereq2, epoch))

    # Category names
    cat_names = {
        "0": "Military", "1": "Economic", "2": "Religious",
        "3": "Academic", "4": "Engineering"
    }

    lines = ["# Advance Tree\n"]
    lines.append("Complete advance/research tree generated from `advances.csv`.\n")
    lines.append("## All Advances\n")
    lines.append("| Advance | Code | Prereq 1 | Prereq 2 | Category | Epoch |")
    lines.append("|---------|------|----------|----------|----------|-------|")
    for cat_id, name, abbrev, prereq1, prereq2, epoch in rows:
        cat_name = cat_names.get(cat_id, cat_id)
        p1 = prereq1 if prereq1 not in ("no", "nil") else "—"
        p2 = prereq2 if prereq2 not in ("no", "nil") else "—"
        lines.append(f"| {name} | {abbrev} | {p1} | {p2} | {cat_name} | {epoch} |")

    # Sphere ladders section
    lines.append("\n## Sphere Magic Ladders\n")
    lines.append("Each sphere has a 6-rung research chain:\n")
    ladders = {
        "Life": ["Life Magic (Gen)", "Life Lore (Inv)", "Life Adept (Lab)", "Life Mage (Las)", "Life Wizard (Too)", "Life Master (Mag)"],
        "Nature": ["Nature Magic (X1)", "Nature Lore (Plu)", "Nature Adept (PT)", "Nature Mage (Rad)", "Nature Wizard (Rec)", "Nature Master (Ref)"],
        "Sorcery": ["Sorcery (Hor)", "Sorcerous Lore (The)", "Sorcery Adept (X2)", "Sorcery Mage (NP)", "Sorcery Wizard (Phy)", "Sorcery Master (Pla)"],
        "Death": ["Death Magic (U2)", "Death Lore (Rfg)", "Death Adept (Rob)", "Death Mage (SFl)", "Death Wizard (Sth)", "Death Master (SE)"],
        "Chaos": ["Chaos Magic (Gun)", "Chaos Lore (MP)", "Chaos Adept (Med)", "Chaos Mage (Met)", "Chaos Wizard (Min)", "Chaos Master (Mob)"],
    }
    for sphere, rungs in ladders.items():
        lines.append(f"### {sphere}\n")
        lines.append("```")
        lines.append(" → ".join(rungs))
        lines.append("```\n")

    lines.append(f"\n**Total: {len(rows)} advances**\n")
    (OUT_DIR / "advances.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"  advances.md: {len(rows)} rows")


# ─── BUILDINGS ────────────────────────────────────────────────────────────────

def gen_buildings():
    rows = []
    with open(CSV_DIR / "improvements.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            name = r["name"].strip()
            cost = r["cost"].strip()
            upkeep = r["upkeep"].strip()
            prereq = r["prereq"].strip()
            sphere = r["sphere"].strip()
            effects = r.get("effects", "").strip()
            # Skip hidden/placeholder entries
            if name.startswith("x") or name.startswith("HIDE"):
                continue
            rows.append((sphere, name, cost, upkeep, prereq, effects))

    sphere_order = {"neutral": 0, "life": 1, "nature": 2, "sorcery": 3, "death": 4, "chaos": 5}
    rows.sort(key=lambda x: (sphere_order.get(x[0], 9), x[1]))

    lines = ["# Building List\n"]
    lines.append("City improvements and wonders generated from `improvements.csv`.\n")
    lines.append("| Building | Sphere | Cost | Upkeep | Prereq | Effects |")
    lines.append("|----------|--------|------|--------|--------|---------|")
    for sphere, name, cost, upkeep, prereq, effects in rows:
        p = prereq if prereq not in ("no", "nil") else "—"
        eff = effects[:60] + "..." if len(effects) > 60 else effects
        lines.append(f"| {name} | {sphere.capitalize()} | {cost} | {upkeep} | {p} | {eff} |")

    lines.append(f"\n**Total: {len(rows)} buildings**\n")
    (OUT_DIR / "buildings.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"  buildings.md: {len(rows)} rows")


# ─── TERRAIN ──────────────────────────────────────────────────────────────────

def gen_terrain():
    rows = []
    with open(CSV_DIR / "terrain.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            tid = r["terrain_id"].strip()
            internal = r["internal_type"].strip()
            movement = r["movement_type"].strip()
            resources = r.get("resources", "").strip()
            rows.append((tid, internal, movement, resources))

    lines = ["# Terrain Effects\n"]
    lines.append("All terrain types and their properties, generated from `terrain.csv`.\n")
    lines.append("## Terrain Types\n")
    lines.append("| ID | Type | Movement | Resources |")
    lines.append("|----|------|----------|-----------|")
    for tid, internal, movement, resources in rows:
        # Simplify resource display
        res_short = ", ".join(r.split("_")[-1] for r in resources.split(";")[:2]).strip(", ") if resources else "—"
        lines.append(f"| {tid} | {internal} | {movement} | {res_short} |")

    lines.append("\n## Cataclysm Terrain Mapping\n")
    lines.append("When a sphere's Master advance is researched, surrounding tiles transform:\n")
    lines.append("| Sphere | Target Terrain | Index | Theme |")
    lines.append("|--------|---------------|-------|-------|")
    lines.append("| Death | TERRAIN_DEAD | 17 | Dark wasteland |")
    lines.append("| Life | TERRAIN_SPECIAL1 | 25 | Radiant fields |")
    lines.append("| Chaos | TERRAIN_DESERT | 5 | Volcanic wastes |")
    lines.append("| Nature | TERRAIN_JUNGLE | 7 | Primal overgrowth |")
    lines.append("| Sorcery | TERRAIN_GLACIER | 3 | Crystal frozen |")

    lines.append(f"\n**Total: {len(rows)} terrain types**\n")
    (OUT_DIR / "terrain.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"  terrain.md: {len(rows)} rows")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Generating reference pages...")
    gen_units()
    gen_spells()
    gen_advances()
    gen_buildings()
    gen_terrain()
    print("Done.")
