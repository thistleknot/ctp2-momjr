#!/usr/bin/env python3
"""
Civ2 MoM JR BMP sprite extractor for CTP2.

Require:
  - Pillow installed
  - Source BMPs at H:/Games/civ2/MOMJR/MOMJR/
  - CSV files at Scenarios/mom/tools/momjr_csv/
  - Write access to CTP2 pictures directories

Guarantee:
  - Extracts individual sprites from Civ2 BMP sprite sheets
  - Converts transparency (magenta 255,0,255 and/or green 0,255,0) to alpha
  - Saves ICON_UNIT_XXX.tga, ICON_ADVANCE_XXX.tga, ICON_IMPROVE_XXX.tga etc.
    to CTP2 pictures dir
  - Clears stale generated unit icon outputs before regeneration
  - Sheet layout parameters are data-driven via sprite_atlas_config.csv

Maintain:
  - Never writes outside CTP2 pictures directories
  - Reports count of icons written vs skipped
  - sprite_atlas_config.csv is the single source of truth for BMP grid geometry

Usage:
  python civ2_sprite_extractor.py [--dry-run] [--sheet icons|units|improvements|advances|all]
"""

import argparse
import csv
import os
import sys
from pathlib import Path

try:
    import numpy as np
    from PIL import Image
except ImportError:
    sys.exit("Pillow and numpy are required: pip install Pillow numpy")

# Source BMP directory — per-mod: override with CIV2_MOD_BMP_DIR (defaults to
# the MoM source mod for backward compatibility).
BMP_DIR = Path(os.environ.get("CIV2_MOD_BMP_DIR", r"H:\Games\civ2\MOMJR\MOMJR"))

# CTP2 MoM scenario pictures target. Do not write generated MoM art into
# ctp2_data; base UI assets are a separate lookup layer.
CTP2_ROOT = Path(__file__).parent.parent.parent.parent  # H:\Program Files(x86)\Activision\Call To Power 2
PICTURES_DIRS = [
    CTP2_ROOT / r"Scenarios\mom\scen0000\default\graphics\pictures",
]

# CSV files: (csv_path, id_col, sheet_key)  — cell_index col used automatically if present
CSV_SOURCES = [
    (CTP2_ROOT / r"Scenarios\mom\tools\momjr_csv\units.csv", "icon", "icons"),
    (CTP2_ROOT / r"Scenarios\mom\tools\momjr_csv\units.csv", "sprite", "units"),
    # Use 'ident' (primary key) instead of 'icon' to avoid corrupted filename generation
    # when the Excel artifact has misaligned/NaN 'name' and garbage 'icon' values.
    (CTP2_ROOT / r"Scenarios\mom\tools\momjr_csv\improvements.csv", "ident", "improvements"),
    (CTP2_ROOT / r"Scenarios\mom\tools\momjr_csv\tileimp.csv", "ident", "improvements"),
    # advances.csv has no 'ident' column; its identifier is 'icon' (ICON_ADVANCE_*)
    (CTP2_ROOT / r"Scenarios\mom\tools\momjr_csv\advances.csv", "icon", "advances"),
]

# All known Civ2 background/transparency colors across MoMJR and HoMM2 mods
TRANS_COLORS = {
    (255, 0, 255),    # bright magenta — primary
    (135, 83, 135),   # dark magenta variant
    (128, 80, 128),   # MoMJR-specific dark magenta
    (0, 255, 0),      # green (some mods)
}

# Units.bmp map-sprite (SPRITE_*.tga) grid detection parameters.
#
# ROOT CAUSE (2026-07-04): MoMJR Units.bmp is NOT the clean 10-col x 64x48
# atlas the rigid layout assumed. Its real content is a 9-column x 7-row grid
# with ~64px pitch on BOTH axes, irregular gutters, and content that starts at
# y=15 / x=9 (not 0,0). The rigid grid mismapped every unit from flat index 9
# onward — clipping some (row offset y0 vs y15) and shifting others by whole
# cells (col 9 lands in the empty right gutter x576-640). Result: 19 truly
# empty extractions plus dozens of "colorful but wrong-unit" sprites.
#
# Fix: detect the real column/row bands from the foreground projection, split
# gutters at their midpoints, and map each unit's sequential index (RULES @UNITS
# / units.csv row order) directly into the detected row-major grid.
_UNITS_BAND_MIN_FG = 20       # min foreground px in a column/row to count as content
_UNITS_BAND_MIN_LEN = 10      # min contiguous px for a content band (drops header noise)
_UNITS_MIN_FIGURE_PX = 20     # cells with fewer figure px are empty placeholders (B3..B9)

# Sheet grid layouts are loaded from sprite_atlas_config.csv at import time.
# Fallback hardcoded layouts are kept here only for backward compatibility when
# the config file is absent.
_FALLBACK_LAYOUTS = {
    "units":        ("Units.bmp",        64, 48, 10),
    "improvements": ("Improvements.bmp", 64, 32, 9, 65, 33, 1, 1),
    "wonder_atlas": ("Improvements.bmp", 73, 41, 8),
}

def _load_atlas_config() -> dict:
    """
    Load sheet layout parameters from sprite_atlas_config.csv.

    Require: sprite_atlas_config.csv exists alongside this script or in the
             Scenarios/mom/tools/ directory.
    Guarantee: returns dict mapping sheet_key -> layout tuple compatible with
               load_sheet_cells(). Falls back to _FALLBACK_LAYOUTS if absent.
    Maintain: sprite_atlas_config.csv is the single source of truth for BMP
              grid geometry; this function must never be bypassed.
    """
    # Per-mod config (the mod's csv dir) wins over the shared tools copy.
    config_paths = []
    csv_dir = os.environ.get("CTP2_GENERATOR_CSV_DIR")
    if csv_dir:
        config_paths.append(Path(csv_dir) / "sprite_atlas_config.csv")
    config_paths += [
        CTP2_ROOT / r"Scenarios\mom\tools\sprite_atlas_config.csv",
        Path(__file__).parent / "sprite_atlas_config.csv",
    ]
    config_path = next((p for p in config_paths if p.exists()), None)
    if config_path is None:
        print("[WARN] sprite_atlas_config.csv not found — using fallback layouts")
        return dict(_FALLBACK_LAYOUTS)

    layouts = {}
    with open(config_path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            key = row["sheet_key"].strip()
            bmp = row["bmp_file"].strip()
            ox, oy   = int(row["offset_x"]), int(row["offset_y"])
            pw, ph   = int(row["pitch_w"]),  int(row["pitch_h"])
            cw, ch   = int(row["cell_w"]),   int(row["cell_h"])
            nc       = int(row["n_cols"])
            nr       = int(row.get("n_rows", "0"))
            # Store as extended tuple: (bmp, cell_w, cell_h, n_cols, pitch_w, pitch_h, offset_x, offset_y, n_rows)
            layouts[key] = (bmp, cw, ch, nc, pw, ph, ox, oy, nr)
    print(f"  Loaded {len(layouts)} sheet layout(s) from {config_path.name}")
    return layouts

SHEET_LAYOUTS = _load_atlas_config()

# Green-grid sheets use pure (0, 255, 0) cell borders. Static cell sizes are
# kept here as validated fallbacks when projection detection is confused by
# partial borders, diagonal intersections, or group separators.
GREEN_GRID_LAYOUTS = {
    "terrain2": ("Terrain2.bmp", 65, 33),
    "cities":   ("Cities.bmp",   65, 68),
}

GENERATED_OUTPUT_PATTERNS = {
    "icons": ("ICON_UNIT_*.tga", "ICON_UNIT_*.png"),  # clean both on regeneration
}


def _collapse_position_runs(positions: "np.ndarray", max_gap: int = 1) -> list:
    """
    Collapse sorted integer pixel positions to one midpoint per contiguous run.

    Require: positions is a sorted 1D numpy array.
    Guarantee: returns midpoint line positions; empty input returns [].
    """
    if len(positions) == 0:
        return []

    lines = []
    run_start = int(positions[0])
    previous = int(positions[0])

    for pos in positions[1:]:
        pos = int(pos)
        if pos > previous + max_gap:
            lines.append((run_start + previous) // 2)
            run_start = pos
        previous = pos

    lines.append((run_start + previous) // 2)
    return lines


def _regular_lines_from_cell_size(limit: int, cell_size: int, offset: int = 0) -> list:
    """
    Return regular grid border positions for a known cell size.

    Require: limit and cell_size are positive integers.
    Guarantee: includes every in-bounds border from offset to limit.
    """
    if limit <= 0 or cell_size <= 0:
        return []
    return list(range(offset, limit + 1, cell_size))


def detect_green_grid_lines(bmp_path: Path) -> tuple:
    """
    Detect pure-green cell-border lines in a Civ2 BMP sheet.

    Require: bmp_path exists and can be opened by Pillow.
    Guarantee: returns (x_lines, y_lines) collapsed from pure (0,255,0) pixels.
    Failure modes: sheets with dense diagonal/partial green marks can produce
    noisy projections; callers should compare against static layout fallbacks.
    """
    src = Image.open(bmp_path).convert("RGB")
    arr = np.array(src, dtype=np.uint8)
    green = (arr[:, :, 0] == 0) & (arr[:, :, 1] == 255) & (arr[:, :, 2] == 0)
    x_positions = np.where(green.sum(axis=0) > 0)[0]
    y_positions = np.where(green.sum(axis=1) > 0)[0]
    return _collapse_position_runs(x_positions), _collapse_position_runs(y_positions)


def load_green_grid_cells(sheet_key: str) -> list:
    """
    Load cells from a green-grid Civ2 sheet using validated static grid sizes.

    Require: sheet_key is in GREEN_GRID_LAYOUTS and source BMP exists.
    Guarantee: slices cell content inside border pixels and returns RGBA cells.
    Failure modes: missing BMP returns []; sheets with irregular groups are still
    sliced by the validated static stride rather than hallucinated canvas edges.
    """
    bmp_file, cell_w, cell_h = GREEN_GRID_LAYOUTS[sheet_key]
    bmp_path = BMP_DIR / bmp_file
    if not bmp_path.exists():
        print(f"  [WARN] BMP not found: {bmp_path}")
        return []

    src = Image.open(bmp_path).convert("RGBA")
    width, height = src.size

    # Detection is retained for parser transparency; static sizes are the
    # validated source of truth for these MoMJR sheets.
    detected_x, detected_y = detect_green_grid_lines(bmp_path)
    if detected_x and detected_y:
        print(f"  Green grid detected in {bmp_file}: x_lines={len(detected_x)} y_lines={len(detected_y)}")

    x_lines = _regular_lines_from_cell_size(width, cell_w)
    y_lines = _regular_lines_from_cell_size(height, cell_h)

    cells = []
    for row in range(len(y_lines) - 1):
        y0 = y_lines[row] + 1
        y1 = y_lines[row + 1]
        for col in range(len(x_lines) - 1):
            x0 = x_lines[col] + 1
            x1 = x_lines[col + 1]
            if x0 < x1 and y0 < y1:
                cells.append(src.crop((x0, y0, x1, y1)))

    return cells


def clean_generated_outputs(sheet_keys: list, dry_run: bool) -> int:
    """
    Delete generated image files before regeneration to prevent stale half-crops.

    Require: sheet_keys are requested extractor sheet names.
    Guarantee: only deletes patterns owned by this extractor, currently unit icon
    PNGs; never deletes unrelated base-game or scenario TGA files.
    """
    patterns = []
    for sheet_key in sheet_keys:
        patterns.extend(GENERATED_OUTPUT_PATTERNS.get(sheet_key, ()))

    if not patterns:
        return 0

    deleted = 0
    for picture_dir in PICTURES_DIRS:
        if not picture_dir.exists():
            continue
        for pattern in patterns:
            for path in picture_dir.glob(pattern):
                deleted += 1
                if dry_run:
                    print(f"  [DRY] would delete stale generated file {path}")
                else:
                    path.unlink()
    if deleted:
        action = "Would delete" if dry_run else "Deleted"
        print(f"{action} {deleted} stale generated file(s)")
    return deleted


def load_sheet_cells(sheet_key: str) -> list:
    """
    Load all sprite cells from a sheet BMP, converting transparency.
    Returns a flat list of RGBA PIL Images in row-major order.
    """
    if sheet_key in GREEN_GRID_LAYOUTS:
        return load_green_grid_cells(sheet_key)

    layout = SHEET_LAYOUTS[sheet_key]
    # Support 4-tuple, 8-tuple (legacy), and 9-tuple (config-loaded) formats
    if len(layout) == 4:
        bmp_file, cell_w, cell_h, n_cols = layout
        pitch_w, pitch_h, offset_x, offset_y, n_rows = cell_w, cell_h, 0, 0, 0
    elif len(layout) == 8:
        bmp_file, cell_w, cell_h, n_cols, pitch_w, pitch_h, offset_x, offset_y = layout
        n_rows = 0
    else:
        bmp_file, cell_w, cell_h, n_cols, pitch_w, pitch_h, offset_x, offset_y, n_rows = layout
    bmp_path = BMP_DIR / bmp_file
    if not bmp_path.exists():
        print(f"  [WARN] BMP not found: {bmp_path}")
        return []

    src = Image.open(bmp_path).convert("RGBA")
    arr = np.array(src, dtype=np.uint8)  # (H, W, 4)
    h, w = arr.shape[:2]

    # Vectorized: set alpha=0 for all transparency color pixels
    for (tr, tg, tb) in TRANS_COLORS:
        mask = (arr[:, :, 0] == tr) & (arr[:, :, 1] == tg) & (arr[:, :, 2] == tb)
        arr[mask, 3] = 0

    cells = []
    row_count = 0
    y = offset_y
    while y + cell_h <= h:
        if n_rows > 0 and row_count >= n_rows:
            break
        x = offset_x
        col = 0
        while x + cell_w <= w and col < n_cols:
            cell_arr = arr[y:y + cell_h, x:x + cell_w]
            cells.append(Image.fromarray(cell_arr, "RGBA"))
            x += pitch_w
            col += 1
        y += pitch_h
        row_count += 1

    return cells


def is_cell_empty(img: "Image.Image") -> bool:
    """
    Return True if every pixel in the cell is a background/transparency color.

    Require: img is RGBA.
    Guarantee: returns False as soon as any non-background pixel is found.
    """
    arr = np.array(img.convert("RGBA"), dtype=np.uint8)
    bg_mask = np.zeros(arr.shape[:2], dtype=bool)
    for (tr, tg, tb) in TRANS_COLORS:
        bg_mask |= (arr[:, :, 0] == tr) & (arr[:, :, 1] == tg) & (arr[:, :, 2] == tb)
    # Also treat fully-transparent and pure-black as background
    bg_mask |= (arr[:, :, 3] == 0)
    bg_mask |= ((arr[:, :, 0] == 0) & (arr[:, :, 1] == 0) & (arr[:, :, 2] == 0))
    return bool(np.all(bg_mask))


def read_csv_identifiers(csv_path: Path, id_col: str) -> list:
    """
    Return list of (cell_index, identifier, name) from CSV, in file order.

    The sheet position comes from 'art_cell_index' when that column is present
    and non-blank, else from 'cell_index', else the sequential row index.
    'art_cell_index' exists because 'cell_index' doubles as the generator's
    advance cost weight — sheet coordinates must not overwrite cost ordering.
    A sentinel value beyond the sheet (e.g. 999) skips extraction for that row,
    leaving the existing ICON_*.tga on disk untouched.
    """
    rows = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        has_cell_index = "cell_index" in (reader.fieldnames or [])
        has_art_cell = "art_cell_index" in (reader.fieldnames or [])
        for i, row in enumerate(reader):
            ident = row.get(id_col, "").strip()
            name = row.get("name", f"row{i}").strip()
            if ident:
                art_text = (row.get("art_cell_index") or "").strip() if has_art_cell else ""
                if art_text.lstrip("-").isdigit():
                    cell_idx = int(art_text)
                elif has_cell_index:
                    cell_idx = int(row["cell_index"])
                else:
                    cell_idx = i
                rows.append((cell_idx, ident, name))
    return rows


def save_tga(img: Image.Image, dest_path: Path, dry_run: bool) -> bool:
    """
    Save image as 24-bit RGB TGA with black (0,0,0) as the background color.
    Transparent pixels (alpha=0) are composited onto black to match the CTP2
    unit panel dark background and avoid visible color fringing.
    """
    if dry_run:
        print(f"  [DRY] would write {dest_path}")
        return True
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    bg = Image.new("RGB", img.size, (0, 0, 0))
    if img.mode == "RGBA":
        bg.paste(img.convert("RGB"), mask=img.split()[3])
    else:
        bg.paste(img.convert("RGB"))
    bg.save(str(dest_path), format="TGA")
    return True


def save_tga_rgb555(img: Image.Image, dest_path: Path, dry_run: bool) -> bool:
    """
    Save image as uncompressed 16-bit TGA (RGB555/X1R5G5B5) with black background.

    CTP2 is sensitive to unsupported TGA variants in uniticon.txt-loaded image
    paths. This writer emits the same format family already used successfully by
    build_mom_icons.py: TrueColor, 16-bit, no alpha channel, no compression.
    Transparent pixels are composited onto black (0,0,0) to match the canonical
    AE unit icon convention — the engine renders these in a dark-bordered panel
    and does not apply color-key transparency to unit icons.
    """
    if dry_run:
        print(f"  [DRY] would write {dest_path}")
        return True

    dest_path.parent.mkdir(parents=True, exist_ok=True)

    bg = Image.new("RGB", img.size, (0, 0, 0))
    if img.mode == "RGBA":
        bg.paste(img.convert("RGB"), mask=img.split()[3])
    else:
        bg.paste(img.convert("RGB"))

    arr = np.array(bg, dtype=np.uint8)
    h, w = arr.shape[:2]
    r = arr[:, :, 0].astype(np.uint16) >> 3
    g = arr[:, :, 1].astype(np.uint16) >> 3
    b = arr[:, :, 2].astype(np.uint16) >> 3
    packed = (r << 10) | (g << 5) | b
    flipped = np.flipud(packed)

    header = bytes([
        0,  # id_length
        0,  # color_map_type
        2,  # image_type: uncompressed true-color
        0, 0, 0, 0, 0,  # color map spec
        0, 0,  # x_origin
        0, 0,  # y_origin
        w & 0xFF, (w >> 8) & 0xFF,
        h & 0xFF, (h >> 8) & 0xFF,
        16,  # bits_per_pixel
        0x00,  # descriptor: bottom-left origin, 0 alpha bits
    ])
    with open(dest_path, "wb") as fh:
        fh.write(header)
        fh.write(flipped.tobytes())
    return True


def extract_sheet(sheet_key: str, identifiers: list, dry_run: bool, output_dir: Path) -> tuple:
    """
    Map identifiers to sprite cells and write TGAs.

    Each entry in identifiers is (cell_index, icon_id, name).
    cell_index is used directly as the flat row-major index into the BMP grid,
    allowing non-sequential or sparse mappings (e.g. advances where some slots
    are inherited base-game icons not used by MoMJR).

    Cells that are entirely background pixels are skipped — no TGA is written
    and the generator falls back to its default placeholder TGA.

    Returns (written, skipped).
    """
    cells = load_sheet_cells(sheet_key)
    if not cells:
        return 0, len(identifiers)

    written = 0
    skipped = 0

    for cell_index, ident, name in identifiers:
        if cell_index >= len(cells):
            print(f"  [SKIP] {ident} — cell_index {cell_index} beyond sheet ({len(cells)} cells)")
            skipped += 1
            continue

        cell = cells[cell_index]
        if is_cell_empty(cell):
            skipped += 1
            continue

        # Scale to the standard 160×120 canvas that CTP2 expects for GL icons.
        cell = _scale_rgba_to_canvas(cell, 160, 120)

        dest = output_dir / f"{ident}.tga"
        save_tga_rgb555(cell, dest, dry_run)
        if not dry_run:
            print(f"  Wrote {dest.name} ({name})")
        written += 1

    return written, skipped


def _remove_bg_colors(arr: "np.ndarray") -> "np.ndarray":
    """
    Set alpha=0 for all known background/transparency colors in an RGBA uint8 array.
    Also removes all three dark-magenta palette variants used across Civ2 mods.
    """
    for (tr, tg, tb) in TRANS_COLORS:
        mask = (arr[:, :, 0] == tr) & (arr[:, :, 1] == tg) & (arr[:, :, 2] == tb)
        arr[mask, 3] = 0
    return arr


def _remove_black_outline(arr: "np.ndarray") -> "np.ndarray":
    """
    Remove the 1-pixel black outline that Civ2 artists drew around every sprite.
    Method: flood-expand the transparent region to consume any fully-black pixel
    that is adjacent (4-connected) to a transparent pixel.

    Require: arr is RGBA uint8 with background already zeroed out.
    Guarantee: only edge-connected black pixels are removed; interior black
    (e.g., shadow areas surrounded by colour) is preserved.
    """
    from collections import deque

    h, w = arr.shape[:2]
    alpha = arr[:, :, 3]
    is_black = (arr[:, :, 0] == 0) & (arr[:, :, 1] == 0) & (arr[:, :, 2] == 0)

    # Seed: all transparent pixels
    visited = alpha == 0
    q: deque = deque()
    ys, xs = np.where(visited)
    for y, x in zip(ys.tolist(), xs.tolist()):
        q.append((int(y), int(x)))

    while q:
        y, x = q.popleft()
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and not visited[ny, nx] and is_black[ny, nx]:
                visited[ny, nx] = True
                arr[ny, nx, 3] = 0
                q.append((ny, nx))
    return arr


def _connected_alpha_components(arr: "np.ndarray") -> list:
    """
    Return alpha-connected components as dictionaries with size and bbox.

    Require: arr is an RGBA uint8 array.
    Guarantee: components are 4-connected over alpha>0 pixels and sorted largest first.
    """
    from collections import deque

    alpha = arr[:, :, 3] > 0
    h, w = alpha.shape
    seen = np.zeros((h, w), dtype=bool)
    components = []

    for sy, sx in zip(*np.where(alpha)):
        if seen[sy, sx]:
            continue

        q: deque = deque([(int(sy), int(sx))])
        seen[sy, sx] = True
        pixels = []

        while q:
            y, x = q.popleft()
            pixels.append((y, x))
            for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and alpha[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    q.append((ny, nx))

        ys = [p[0] for p in pixels]
        xs = [p[1] for p in pixels]
        components.append({
            "size": len(pixels),
            "left": min(xs),
            "top": min(ys),
            "right": max(xs) + 1,
            "bottom": max(ys) + 1,
            "pixels": pixels,
        })

    components.sort(key=lambda item: item["size"], reverse=True)
    return components


def _remove_boundary_artifacts(arr: "np.ndarray") -> "np.ndarray":
    """
    Remove tiny non-sprite fragments copied from neighboring cells.

    Require: arr is RGBA uint8 after transparency stripping.
    Guarantee: preserves meaningful sprite components, including shadows, but
    drops tiny isolated flecks and boundary fragments from adjacent cells.
    """
    components = _connected_alpha_components(arr)
    if not components:
        return arr

    h, w = arr.shape[:2]
    main_size = components[0]["size"]
    keep = np.zeros((h, w), dtype=bool)

    for component in components:
        touches_boundary = (
            component["left"] == 0
            or component["top"] == 0
            or component["right"] == w
            or component["bottom"] == h
        )
        small_relative_to_sprite = component["size"] < max(12, main_size * 0.05)
        tiny_isolated_fleck = component["size"] < 6

        if tiny_isolated_fleck or (touches_boundary and small_relative_to_sprite):
            continue

        for y, x in component["pixels"]:
            keep[y, x] = True

    cleaned = arr.copy()
    cleaned[~keep, 3] = 0
    return cleaned


def _alpha_bbox(arr: "np.ndarray", padding: int = 3) -> tuple | None:
    """
    Return a padded alpha bbox for a cleaned sprite array.

    Require: arr is RGBA uint8.
    Guarantee: bbox stays within image bounds; returns None for empty alpha.
    """
    ys, xs = np.where(arr[:, :, 3] > 0)
    if len(xs) == 0:
        return None

    h, w = arr.shape[:2]
    left = max(0, int(xs.min()) - padding)
    top = max(0, int(ys.min()) - padding)
    right = min(w, int(xs.max()) + 1 + padding)
    bottom = min(h, int(ys.max()) + 1 + padding)
    return left, top, right, bottom


def _scale_rgba_to_canvas(img_rgba: "Image.Image", target_w: int, target_h: int, margin: int = 2) -> "Image.Image":
    """
    Scale an RGBA sprite to a fixed canvas while preserving aspect ratio.

    Require: img_rgba contains the already-cropped sprite art.
    Guarantee: returns an RGBA image exactly target_w × target_h.
    """
    max_w = target_w - margin * 2
    max_h = target_h - margin * 2
    cw, ch = img_rgba.size
    if cw == 0 or ch == 0:
        return Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))

    scale = min(max_w / cw, max_h / ch)
    new_w = max(1, int(cw * scale))
    new_h = max(1, int(ch * scale))
    scaled = img_rgba.resize((new_w, new_h), Image.NEAREST)

    canvas = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    canvas.paste(scaled, ((target_w - new_w) // 2, (target_h - new_h) // 2), scaled)
    return canvas


def _cluster_positions(values: list[float], max_gap: int) -> list[float]:
    """
    Collapse sorted 1D positions to cluster medians separated by max_gap.

    Require: values is non-empty.
    Guarantee: returns one representative center per contiguous cluster.
    """
    ordered = sorted(values)
    clusters = [[ordered[0]]]
    for value in ordered[1:]:
        if value - clusters[-1][-1] <= max_gap:
            clusters[-1].append(value)
        else:
            clusters.append([value])
    return [sum(cluster) / len(cluster) for cluster in clusters]


def _detect_units_sheet_slots(sheet_arr: "np.ndarray", slot_count_hint: int) -> tuple[list[float], list[float], dict]:
    """
    Infer the Units.bmp portrait slot grid from the whole sheet.

    The sheet is not a clean 10×64×48 atlas. Instead, portrait bodies occupy
    stable row/column corridors separated by broad background bands. We detect
    connected components across the entire sheet, derive the dominant body-size
    median from the largest components, then cluster component centers into the
    row/column medians that define each portrait slot.

    Require: sheet_arr is RGBA uint8 with background colors already zeroed out.
    Guarantee: returns x/y slot centers plus a dict mapping (row, col) to the
    components that belong to that slot.
    Failure modes: raises RuntimeError if the inferred grid is too small for the
    number of identifiers requested.
    """
    components = [component for component in _connected_alpha_components(sheet_arr) if component["size"] >= 8]
    if not components:
        raise RuntimeError("Units.bmp slot detection found no visible components")

    largest_sizes = sorted((component["size"] for component in components), reverse=True)[:min(slot_count_hint, len(components))]
    median_primary_size = int(np.median(largest_sizes)) if largest_sizes else 0
    anchor_min_size = max(60, int(median_primary_size * 0.45))
    anchors = [component for component in components if component["size"] >= anchor_min_size]
    if not anchors:
        anchors = components

    median_w = int(np.median([component["right"] - component["left"] for component in anchors]))
    median_h = int(np.median([component["bottom"] - component["top"] for component in anchors]))
    cluster_gap = max(12, min(median_w, median_h) // 2)

    x_centers = _cluster_positions([component["left"] + (component["right"] - component["left"]) / 2 for component in anchors], cluster_gap)
    y_centers = _cluster_positions([component["top"] + (component["bottom"] - component["top"]) / 2 for component in anchors], cluster_gap)
    if len(x_centers) * len(y_centers) < slot_count_hint:
        raise RuntimeError(
            f"Units.bmp slot detection inferred only {len(x_centers)}x{len(y_centers)} slots for {slot_count_hint} identifiers"
        )

    slots = {(row, col): [] for row in range(len(y_centers)) for col in range(len(x_centers))}
    for component in components:
        col = min(range(len(x_centers)), key=lambda idx: abs((component["left"] + component["right"]) / 2 - x_centers[idx]))
        row = min(range(len(y_centers)), key=lambda idx: abs((component["top"] + component["bottom"]) / 2 - y_centers[idx]))
        slots[(row, col)].append(component)

    return x_centers, y_centers, slots


def _compose_units_slot_sprite(sheet_arr: "np.ndarray", slot_components: list[dict]) -> "Image.Image":
    """
    Build one RGBA sprite image from all components assigned to a detected slot.

    Require: sheet_arr is RGBA uint8 with transparent background.
    Guarantee: returns a tightly-cropped RGBA sprite preserving all parts that
    belong to the slot, including legitimately disconnected upper/lower halves.
    """
    if not slot_components:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))

    slot_arr = np.zeros_like(sheet_arr)
    for component in slot_components:
        for y, x in component["pixels"]:
            slot_arr[y, x] = sheet_arr[y, x]

    bbox = _alpha_bbox(slot_arr, padding=3)
    if bbox is None:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))

    left, top, right, bottom = bbox
    cropped_arr = slot_arr[top:bottom, left:right].copy()
    cropped_arr = _remove_black_outline(cropped_arr)
    cropped_arr = _remove_boundary_artifacts(cropped_arr)

    refined = _alpha_bbox(cropped_arr, padding=0)
    if refined is None:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))

    left, top, right, bottom = refined
    return Image.fromarray(cropped_arr[top:bottom, left:right], "RGBA")


def clean_and_scale_cell(cell_rgba: "Image.Image", target_w: int, target_h: int) -> "Image.Image":
    """
    Full sprite-clean pipeline for one 64×48 Civ2 cell:
      1. Remove all bg/transparency colors → alpha=0
      2. Remove 1-px black outline (flood expand from transparent edges)
      3. Remove tiny boundary artifacts from neighboring cells
      4. Crop to the cleaned sprite's alpha bbox, preserving 3px source padding
      5. Scale to target_w × target_h preserving aspect ratio, 2px margin
      6. Return RGBA image — caller decides final format

    Require: cell_rgba is a 64×48 RGBA PIL image.
    Guarantee: returns RGBA PIL image of exactly (target_w × target_h).
    """
    arr = np.array(cell_rgba, dtype=np.uint8).copy()
    arr = _remove_bg_colors(arr)
    arr = _remove_black_outline(arr)
    arr = _remove_boundary_artifacts(arr)

    bbox = _alpha_bbox(arr, padding=3)
    if bbox is None:
        return Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))

    l, t, r, b = bbox
    cropped_arr = arr[t:b, l:r]
    cropped = Image.fromarray(cropped_arr, "RGBA")
    return _scale_rgba_to_canvas(cropped, target_w, target_h)


def extract_icon_units(identifiers: list, dry_run: bool, output_dir: Path) -> tuple:
    """
    Derive ICON_UNIT_*.tga from Units.bmp by detecting the real portrait slots
    from the full sheet, then scaling each detected slot to 160×120.

    This avoids the false fixed-grid assumption that clipped units such as
    Alorra and Archangel in half.
    Returns (written, skipped).
    """
    bmp_path = BMP_DIR / "Units.bmp"
    if not bmp_path.exists():
        print(f"  [WARN] BMP not found: {bmp_path}")
        return 0, len(identifiers)

    sheet_arr = np.array(Image.open(bmp_path).convert("RGBA"), dtype=np.uint8)
    sheet_arr = _remove_bg_colors(sheet_arr)
    x_centers, y_centers, slots = _detect_units_sheet_slots(sheet_arr, len(identifiers))
    print(f"  Units.bmp slot detection: {len(x_centers)} columns x {len(y_centers)} rows")

    written = 0
    skipped = 0
    for idx, (row_i, ident, name) in enumerate(identifiers):
        slot_row = row_i // len(x_centers)
        slot_col = row_i % len(x_centers)
        if slot_row >= len(y_centers):
            print(f"  [WARN] No detected slot for {ident} (idx={idx})")
            skipped += 1
            continue

        sprite = _compose_units_slot_sprite(sheet_arr, slots.get((slot_row, slot_col), []))
        icon = _scale_rgba_to_canvas(sprite, 160, 120)
        dest = output_dir / f"{ident}.tga"
        save_tga_rgb555(icon, dest, dry_run)
        if not dry_run:
            print(f"  Wrote {dest.name} ({name})")
        else:
            print(f"  [DRY] would write {dest}")
        written += 1

    return written, skipped


def _project_bands(profile: "np.ndarray", threshold: int, min_len: int) -> list:
    """
    Collapse a 1D foreground projection into contiguous content bands.

    Require: profile is a 1D array of per-line foreground pixel counts.
    Guarantee: returns [(start, end)] inclusive spans where the profile stays at
    or above threshold for at least min_len pixels; gutters (below threshold)
    separate bands. Short spikes (< min_len) such as the sheet header strip are
    discarded so they do not create phantom rows/columns.
    """
    on = profile >= threshold
    segs = []
    start = None
    for i, active in enumerate(on):
        if active and start is None:
            start = i
        elif not active and start is not None:
            if i - start >= min_len:
                segs.append((start, i - 1))
            start = None
    if start is not None and len(on) - start >= min_len:
        segs.append((start, len(on) - 1))
    return segs


def _band_cuts(bands: list, limit: int) -> list:
    """
    Turn content bands into cell crop spans by splitting each gutter at its
    midpoint (outer edges extend to the sheet bound).

    Require: bands is the sorted output of _project_bands; limit is the axis size.
    Guarantee: returns [(lo, hi)] spans, one per band, that tile the axis without
    overlap. Over-extended outer margins are harmless because callers tight-crop
    to the alpha bbox afterwards.
    """
    cuts = []
    for k in range(len(bands)):
        lo = 0 if k == 0 else (bands[k - 1][1] + bands[k][0]) // 2
        hi = limit if k == len(bands) - 1 else (bands[k][1] + bands[k + 1][0]) // 2
        cuts.append((lo, hi))
    return cuts


def extract_units_sprites(identifiers: list, dry_run: bool, output_dir: Path) -> tuple:
    """
    Extract map sprites (SPRITE_*.tga) from Units.bmp using the real, detected
    9-column x 7-row content grid rather than a rigid pitch.

    Each identifier is (cell_index, sprite_id, name); cell_index is the unit's
    sequential position in units.csv, which equals the RULES.TXT @UNITS order,
    which equals the sheet's row-major cell order. That index is mapped directly
    into the detected grid: (cell_index // n_cols, cell_index % n_cols).

    Require: Units.bmp exists; identifiers are in sheet order.
    Guarantee: writes one 160x120 RGB555 TGA per non-empty unit cell; empty
    placeholder cells (B3..B9) and the non-MoMJR Settler are skipped (their
    existing TGA is left untouched). Returns (written, skipped).
    Failure modes: raises RuntimeError if grid detection collapses to nothing.
    """
    bmp_path = BMP_DIR / "Units.bmp"
    if not bmp_path.exists():
        print(f"  [WARN] BMP not found: {bmp_path}")
        return 0, len(identifiers)

    sheet_arr = np.array(Image.open(bmp_path).convert("RGBA"), dtype=np.uint8)
    sheet_arr = _remove_bg_colors(sheet_arr)
    height, width = sheet_arr.shape[:2]
    foreground = sheet_arr[:, :, 3] > 0

    col_bands = _project_bands(foreground.sum(axis=0), _UNITS_BAND_MIN_FG, _UNITS_BAND_MIN_LEN)
    row_bands = _project_bands(foreground.sum(axis=1), _UNITS_BAND_MIN_FG, _UNITS_BAND_MIN_LEN)
    n_cols, n_rows = len(col_bands), len(row_bands)
    if n_cols == 0 or n_rows == 0:
        raise RuntimeError("Units.bmp grid detection found no content bands")
    print(f"  Units.bmp grid detection: {n_cols} columns x {n_rows} rows "
          f"({n_cols * n_rows} cells)")

    col_cuts = _band_cuts(col_bands, width)
    row_cuts = _band_cuts(row_bands, height)

    written = 0
    skipped = 0
    for cell_index, ident, name in identifiers:
        # Settler is a CTP2 base unit, not present on the MoMJR sheet — its cell
        # would over-run into bottom-right sheet junk. Leave its existing TGA.
        if ident.upper() == "SPRITE_SETTLER":
            skipped += 1
            continue

        row_i = cell_index // n_cols
        col_i = cell_index % n_cols
        if row_i >= n_rows:
            print(f"  [SKIP] {ident} — index {cell_index} beyond {n_cols}x{n_rows} grid")
            skipped += 1
            continue

        x0, x1 = col_cuts[col_i]
        y0, y1 = row_cuts[row_i]
        cell = sheet_arr[y0:y1, x0:x1].copy()

        figure = int((cell[:, :, 3] > 0).sum())
        if figure < _UNITS_MIN_FIGURE_PX:
            # Empty placeholder cell (e.g. B3..B9) — no art on the sheet.
            skipped += 1
            continue

        bbox = _alpha_bbox(cell, padding=2)
        if bbox is None:
            skipped += 1
            continue

        left, top, right, bottom = bbox
        sprite = Image.fromarray(cell[top:bottom, left:right], "RGBA")
        icon = _scale_rgba_to_canvas(sprite, 160, 120)
        dest = output_dir / f"{ident}.tga"
        save_tga_rgb555(icon, dest, dry_run)
        if not dry_run:
            print(f"  Wrote {dest.name} ({name}, figure={figure}px)")
        else:
            print(f"  [DRY] would write {dest} ({name}, figure={figure}px)")
        written += 1

    return written, skipped


def main():
    parser = argparse.ArgumentParser(description="Extract Civ2 MoM JR sprites to CTP2 TGA files")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done, no writes")
    parser.add_argument("--sheet", default="all",
                        choices=["all", "icons", "units", "improvements", "advances"],
                        help="Which sheet to process (default: all)")
    args = parser.parse_args()

    # Resolve output dir — use first existing pictures dir, or create it
    out_dir = None
    for d in PICTURES_DIRS:
        if d.exists():
            out_dir = d
            break
    if out_dir is None:
        out_dir = PICTURES_DIRS[0]
        if not args.dry_run:
            out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {out_dir}")

    total_written = 0
    total_skipped = 0

    # Gather identifiers per sheet from CSVs
    sheet_ids: dict = {"icons": [], "units": [], "improvements": [], "advances": []}
    for csv_path, id_col, sheet_key in CSV_SOURCES:
        if args.sheet != "all" and args.sheet != sheet_key:
            continue
        if not csv_path.exists():
            print(f"[WARN] CSV not found: {csv_path}")
            continue
        rows = read_csv_identifiers(csv_path, id_col)
        sheet_ids[sheet_key].extend(rows)

    # Deduplicate while preserving order
    for key in sheet_ids:
        seen = set()
        deduped = []
        for r in sheet_ids[key]:
            if r[1] not in seen:
                seen.add(r[1])
                deduped.append(r)
        sheet_ids[key] = deduped

    requested_sheet_keys = [
        sheet_key
        for sheet_key, identifiers in sheet_ids.items()
        if identifiers and (args.sheet == "all" or args.sheet == sheet_key)
    ]
    clean_generated_outputs(requested_sheet_keys, args.dry_run)

    # Extract each requested sheet
    for sheet_key, identifiers in sheet_ids.items():
        if args.sheet != "all" and args.sheet != sheet_key:
            continue
        if not identifiers:
            continue
        print(f"\n--- Sheet: {sheet_key} ({len(identifiers)} identifiers) ---")
        if sheet_key == "icons":
            w, s = extract_icon_units(identifiers, args.dry_run, out_dir)
        elif sheet_key == "units":
            w, s = extract_units_sprites(identifiers, args.dry_run, out_dir)
        else:
            w, s = extract_sheet(sheet_key, identifiers, args.dry_run, out_dir)
        print(f"  Written: {w}  Skipped: {s}")
        total_written += w
        total_skipped += s

    print(f"\nTotal written: {total_written}  Total skipped: {total_skipped}")

    # Verify 5 random ICON_UNIT outputs for observer
    import random
    written_files = list(out_dir.glob("ICON_UNIT_*.tga"))
    written_files = written_files[:50]
    if written_files:
        sample = random.sample(written_files, min(5, len(written_files)))
        print("\n--- Observer sample (5 random ICON_UNIT files) ---")
        for f in sample:
            try:
                img = Image.open(f)
                px = img.load()
                cx, cy = img.width // 2, img.height // 2
                center = px[cx, cy]
                is_placeholder = all(c == 128 for c in center[:3])
                print(f"  {f.name}: {img.size} mode={img.mode} center={center} placeholder={'YES' if is_placeholder else 'NO'}")
            except Exception as e:
                print(f"  {f.name}: ERROR {e}")


if __name__ == "__main__":
    main()
