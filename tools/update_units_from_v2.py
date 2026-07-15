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

# Field mapping: MoM field -> v2 field
field_mapping = {
    'attack': 'attack',
    'defense': 'defense',
    'hp': 'hp',
    'firepower': 'firepower',
    'cost': 'shield_cost',
    'move': 'max_move_points'
}

# Update MoM rows with v2 numeric values
updated_count = 0
matched_names = []
for mom_row in mom_rows:
    mom_name = mom_row['name']
    # Convert MoM name to v2 key format: uppercase, spaces to underscores
    mom_key = mom_name.upper().replace(' ', '_')
    v2_row = v2_lookup.get(mom_key)
    if v2_row is None:
        print(f"Warning: No v2 match for MoM unit '{mom_name}' (looked for '{mom_key}')")
        continue

    # Update numeric fields
    for mom_field, v2_field in field_mapping.items():
        if v2_field in v2_row and pd.notna(v2_row[v2_field]):
            val = v2_row[v2_field]
            if isinstance(val, (int, float)):
                if float(val).is_integer():
                    mom_row[mom_field] = str(int(val))
                else:
                    mom_row[mom_field] = str(val)
            else:
                mom_row[mom_field] = str(val)
    updated_count += 1
    matched_names.append(mom_name)

print(f"Updated {updated_count} units out of {len(mom_rows)} total units.")
print(f"Matched units: {', '.join(sorted(matched_names))}")

# Write back MoM CSV
with open(mom_csv_path, 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=mom_fieldnames)
    writer.writeheader()
    writer.writerows(mom_rows)

print(f"MoM units.csv has been updated successfully.")
