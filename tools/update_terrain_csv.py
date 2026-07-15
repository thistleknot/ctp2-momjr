"""Convert terrain data from AE_Mod v2 xlsx to MoM terrain.csv."""
import sys
import pandas as pd
from pathlib import Path

# Paths
v2_xlsx = Path(r"H:\Program Files(x86)\Activision\Call To Power 2\Scenarios\AE_Mod\ae_mod_control_plane_v2.xlsx")
target_csv = Path(r"H:\Program Files(x86)\Activision\Call To Power 2\Scenarios\mom\tools\momjr_csv\terrain.csv")

# Ensure target directory exists
target_csv.parent.mkdir(parents=True, exist_ok=True)

# Read the 'terrain' sheet from the xlsx
print(f"Reading terrain sheet from {v2_xlsx}...")
try:
    df = pd.read_excel(v2_xlsx, sheet_name='terrain', engine='openpyxl')
except Exception as e:
    print(f"Error reading xlsx: {e}")
    sys.exit(1)

# Expected columns from spec (only these 10, ignore any extra)
expected_cols = ['terrain_id', 'tileset_index', 'hut_tileset_index_a', 'hut_tileset_index_b',
                 'icon', 'internal_type', 'movement_type', 'add_advance', 'remove_advance', 'resources']

# Verify required columns exist
missing = [c for c in expected_cols if c not in df.columns]
if missing:
    print(f"Missing required columns in terrain sheet: {missing}")
    print(f"Available columns: {list(df.columns)}")
    sys.exit(1)

# Keep only expected columns (in order), drop any extras like 'C'
df = df[expected_cols]

# Write to CSV
print(f"Writing {len(df)} rows to {target_csv}...")
df.to_csv(target_csv, index=False, encoding='utf-8')

print("Done.")