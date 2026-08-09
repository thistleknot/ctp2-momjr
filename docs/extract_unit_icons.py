"""Crop individual unit icons from the observer contact sheet for mkdocs table embedding."""
import csv
from pathlib import Path
from PIL import Image

CSV_PATH = Path(__file__).parent.parent / "tools" / "momjr_csv" / "units.csv"
SHEET_PATH = Path(__file__).parent.parent / "tools" / "observer_sheets" / "units_contact_sheet.png"
OUT_DIR = Path(__file__).parent / "img" / "units"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Grid layout: 704x3200 sheet, 4 columns x 20 rows, units sorted alphabetically
COLS = 4
ROWS = 20
CELL_W = 176  # 704 / 4
CELL_H = 160  # 3200 / 20


def main():
    # Read all unit names from CSV
    units = []
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            units.append(r["name"].strip())

    # Sort alphabetically (matching observer sheet order)
    units_sorted = sorted(units, key=lambda x: x.upper())

    if len(units_sorted) != COLS * ROWS:
        print(f"WARNING: {len(units_sorted)} units but grid expects {COLS * ROWS}")

    # Open contact sheet
    sheet = Image.open(SHEET_PATH)

    # Crop each cell and save as unit slug
    count = 0
    for idx, name in enumerate(units_sorted):
        col = idx % COLS
        row = idx // COLS

        x0 = col * CELL_W
        y0 = row * CELL_H
        x1 = x0 + CELL_W
        y1 = y0 + CELL_H

        cell = sheet.crop((x0, y0, x1, y1))

        # Save with slug name
        slug = name.lower().replace(" ", "_").replace("'", "")
        out_path = OUT_DIR / f"{slug}.png"
        cell.save(out_path)
        count += 1

    print(f"Cropped {count} unit icons from observer sheet to {OUT_DIR}")


if __name__ == "__main__":
    main()
