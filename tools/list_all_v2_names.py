import pandas as pd

v2_xlsx_path = r'H:\Program Files(x86)\Activision\Call To Power 2\Scenarios\AE_Mod\ae_mod_control_plane_v2.xlsx'
df_v2 = pd.read_excel(v2_xlsx_path, sheet_name='units')

print("All v2 unit names (total:", len(df_v2), "):")
for name in sorted(df_v2['name'].dropna().unique()):
    print(f"  {name}")
