import csv
import pandas as pd

# Paths
mom_csv_path = r'H:\Program Files(x86)\Activision\Call To Power 2\Scenarios\mom\tools\momjr_csv\units.csv'
v2_xlsx_path = r'H:\Program Files(x86)\Activision\Call To Power 2\Scenarios\AE_Mod\ae_mod_control_plane_v2.xlsx'

# Read MoM CSV
with open(mom_csv_path, 'r', newline='', encoding='utf-8') as f:
    mom_reader = csv.DictReader(f)
    mom_rows = list(mom_reader)
    mom_fieldnames = mom_reader.fieldnames

# Read v2 xlsx units sheet
df_v2 = pd.read_excel(v2_xlsx_path, sheet_name='units')

# Build v2 lookup: strip 'UNIT_' prefix, uppercase, map to row dict
v2_lookup = {}
for _, row in df_v2.iterrows():
    v2_name = row['name']
    if isinstance(v2_name, str) and v2_name.startswith('UNIT_'):
        key = v2_name[5:]  # strip 'UNIT_'
        v2_lookup[key] = row

# Show v2 data for Caravan and Catapult
for unit_key in ['CARAVAN', 'CATAPULT']:
    if unit_key in v2_lookup:
        row = v2_lookup[unit_key]
        print(f"\nv2 {unit_key}:")
        for field in ['attack', 'defense', 'hp', 'firepower', 'shield_cost', 'max_move_points']:
            if field in row:
                print(f"  {field}: {row[field]}")

# Show updated MoM rows for Caravan and Catapult
print("\n\nMoM units after update:")
for mom_row in mom_rows:
    if mom_row['name'] in ['Caravan', 'Catapult']:
        print(f"\n{mom_row['name']}:")
        for field in ['attack', 'defense', 'hp', 'firepower', 'cost', 'move']:
            print(f"  {field}: {mom_row[field]}")
