import pandas as pd

v2_xlsx_path = r'H:\Program Files(x86)\Activision\Call To Power 2\Scenarios\AE_Mod\ae_mod_control_plane_v2.xlsx'
df_v2 = pd.read_excel(v2_xlsx_path, sheet_name='units')

print("Total v2 units:", len(df_v2))
print("\nFirst 20 v2 unit names:")
for name in df_v2['name'].head(20):
    print(f"  {name}")

print("\nSearching for 'PEASANT' in v2 names:")
matches = df_v2[df_v2['name'].str.contains('PEASANT', case=False, na=False)]
for name in matches['name']:
    print(f"  {name}")

print("\nSearching for 'ZOMBIE' in v2 names:")
matches = df_v2[df_v2['name'].str.contains('ZOMBIE', case=False, na=False)]
for name in matches['name']:
    print(f"  {name}")

print("\nAll v2 unit names containing 'B6' or 'B3' or 'B9':")
for name in df_v2['name']:
    if 'B6' in name or 'B3' in name or 'B9' in name:
        print(f"  {name}")
