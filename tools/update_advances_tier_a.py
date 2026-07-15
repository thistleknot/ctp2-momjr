"""
Update advances.csv: set cell_index = (Epoch × 5) + Category for each advance.
Backs up original, then rewrites with new cell_index values.
"""
import csv, re, shutil, os

CSV_PATH = r"H:\Program Files(x86)\Activision\Call To Power 2\Scenarios\mom\tools\momjr_csv\advances.csv"
BACKUP   = CSV_PATH + ".bak_tier_b"

shutil.copy2(CSV_PATH, BACKUP)
print(f"Backed up to {BACKUP}")

rows = []
with open(CSV_PATH, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    for row in reader:
        rows.append(row)

changed = 0
for row in rows:
    try:
        epoch = int(str(row["epoch"]).strip())
        cat_raw = str(row["category"]).strip()
        cat = int(cat_raw.split(";")[0].strip())
    except (ValueError, KeyError):
        print(f"  SKIP (parse error): {row.get('name','?')!r}  epoch={row.get('epoch')} cat={row.get('category')}")
        continue

    new_idx = epoch * 5 + cat
    old_idx = row["cell_index"]
    row["cell_index"] = new_idx
    if str(old_idx) != str(new_idx):
        print(f"  {row['name']:<32} {old_idx} -> {new_idx}  (E{epoch} C{cat})")
        changed += 1
    else:
        print(f"  {row['name']:<32} {old_idx} unchanged  (E{epoch} C{cat})")

with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

print(f"\nUpdated {changed}/{len(rows)} rows in {CSV_PATH}")
