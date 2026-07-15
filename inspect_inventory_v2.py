import pandas as pd
import sys

# Set encoding to handle potential unicode characters in stdout
sys.stdout.reconfigure(encoding='utf-8')

file_path = r'H:\Program Files(x86)\Activision\Call To Power 2\Scenarios\mom\mom_dimension_inventory.xlsx'

try:
    xl = pd.ExcelFile(file_path)
    sheet_names = xl.sheet_names
    print(f"Sheets: {sheet_names}")

    for sheet in sheet_names:
        df = pd.read_excel(file_path, sheet_name=sheet)
        print(f"\n--- Sheet: {sheet} ---")
        print(f"Headers: {df.columns.tolist()}")
        print("Sample (first 3 rows):")
        # Use to_string to ensure we get a clean representation
        print(df.head(3).to_string())
except Exception as e:
    print(f"Error: {e}")
