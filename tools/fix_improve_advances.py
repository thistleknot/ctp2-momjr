"""
fix_improve_advances.py - Fix placeholder/truncated ENABLING_ADVANCE values in improve.csv.

Maps Civ2 abbreviation codes to their full CTP2 advance IDs, derived from
the category comment in advances.csv (format: '<num>    ; <code>').

Special case: ADVANCE_no (Civ2 "no prerequisite") is mapped per-building
to the most contextually appropriate CTP2 advance.
"""
import csv
import io
import shutil
import sys
from pathlib import Path

TOOLS = Path(__file__).parent
IMPROVE_CSV = TOOLS / "data_csv" / "improve.csv"

# Direct code→CTP2-ID mapping derived from advances.csv icon column + manual resolution
CODE_MAP = {
    "ADVANCE_X3":  "ADVANCE_ARTIFICING",
    "ADVANCE_X4":  "ADVANCE_LESSER_FAUNA_LORE",
    "ADVANCE_U1":  "ADVANCE_FORCES_OF_NATURE",
    "ADVANCE_U3":  "ADVANCE_SEA_LORE",
    "ADVANCE_Fli": "ADVANCE_WIZARDRY",
    "ADVANCE_Rec": "ADVANCE_NATURE_WIZARD",
    "ADVANCE_PT":  "ADVANCE_NATURE_ADEPT",
    "ADVANCE_Plu": "ADVANCE_NATURE_LORE",
    "ADVANCE_Mys": "ADVANCE_MYSTICISM",
    "ADVANCE_Rob": "ADVANCE_DEATH_ADEPT",
    "ADVANCE_E1":  "ADVANCE_RUNE_LORE",
    "ADVANCE_CA":  "ADVANCE_HEALING",
    "ADVANCE_Cmp": "ADVANCE_METAMORPHOSIS",
    "ADVANCE_Ato": "ADVANCE_ELDRITCH_LORE",
    "ADVANCE_RR":  "ADVANCE_GREATER_ENCHANTMENTS",
    "ADVANCE_Cmb": "ADVANCE_LESSER_ENCHANMENTS",
    "ADVANCE_Min": "ADVANCE_CHAOS_WIZARD",
    "ADVANCE_NF":  "ADVANCE_GRAND_MASTERY",
    "ADVANCE_Phy": "ADVANCE_SORCERY_WIZARD",
    "ADVANCE_Too": "ADVANCE_LIFE_WIZARD",
}

# Per-building overrides for ADVANCE_no (Civ2 "no prerequisite")
NO_PREREQ_MAP = {
    "IMPROVE_SAM_MISSILE_BATTERY": "ADVANCE_BALLISTICS",
    "IMPROVE_COASTAL_FORTRESS":    "ADVANCE_MASONRY",
    "IMPROVE_TRANSPORTER":         "ADVANCE_FUTURE_TECHNOLOGY",
}


def fix_improve_csv(path: Path) -> int:
    """
    Rewrite improve.csv replacing placeholder/truncated ENABLING_ADVANCE values
    with their correct full CTP2 advance IDs.

    Requires: path exists and is a valid CSV with 'id' and 'ENABLING_ADVANCE' columns.
    Guarantees: file is rewritten in-place; original backed up as .bak.
    Returns: number of rows changed.
    """
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        text = f.read()

    reader = csv.DictReader(io.StringIO(text))
    fieldnames = reader.fieldnames
    rows = list(reader)

    changed = 0
    for row in rows:
        row_id = row.get("id", "").strip()
        val = row.get("ENABLING_ADVANCE", "").strip()

        new_val = None
        if val in CODE_MAP:
            new_val = CODE_MAP[val]
        elif val == "ADVANCE_no":
            if row_id in NO_PREREQ_MAP:
                new_val = NO_PREREQ_MAP[row_id]
            else:
                print(f"  WARNING: {row_id} has ADVANCE_no but no per-building mapping — leaving as-is")

        if new_val is not None and new_val != val:
            print(f"  {row_id}: {val} -> {new_val}")
            row["ENABLING_ADVANCE"] = new_val
            changed += 1

    if changed == 0:
        print("No changes needed.")
        return 0

    # Backup
    backup = path.with_suffix(".csv.bak_advance_fix")
    shutil.copy2(path, backup)
    print(f"\nBacked up to: {backup}")

    # Write fixed CSV preserving original encoding
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows ({changed} changed) to {path}")
    return changed


if __name__ == "__main__":
    print("Fixing ENABLING_ADVANCE placeholders in improve.csv...")
    print()
    n = fix_improve_csv(IMPROVE_CSV)
    sys.exit(0 if n >= 0 else 1)
