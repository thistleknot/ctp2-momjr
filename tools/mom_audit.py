"""
MoM scenario post-generation audit checklist.

Dimensions checked:
  1. File population   — expected gamedata files exist and have MoM content
  2. CSV coverage      — every CSV row maps to a block in the generated file
  3. Icon / image      — every block's Icon ref resolves in uniticon.txt; no bad TGAs
  4. Age distribution  — advances distributed across valid ages; no raw AGE_0/1/2 in GL
  5. GL completeness   — every advance/unit/building has all 4 GL sections
  6. Cross-ref sanity  — EnableAdvance / Prerequisites / EnableBuilding all resolve
  7. GL text quality   — no semicolon bleed in Branch, no raw AGE_0 in Age line

Run after every ctp2_generator.py invocation:
    python Scenarios/mom/tools/mom_audit.py

Premises:
  [observed] Generated files live in scen0000/default/gamedata and english/gamedata.
  [observed] CSVs in momjr_csv/ are the source-of-truth for MoM content.
  [observed] MoM buildings can live in Improve.txt or buildings.txt.
  [observed] Governments whose `EnableAdvance` still exists in the surviving MoM
             `Advance.txt` must remain present in scenario `govern.txt`; otherwise
             the scenario can strand players in `GOVERNMENT_ANARCHY` where
             `MaxScienceRate 0` blocks research.
  [observed] Player startup tech grants come from `DiffDB.txt` `ADVANCE_CHANCES`;
             if MoM inherits stock startup techs but none of the scenario's live
             governments are start-enabled, players can remain in
             `GOVERNMENT_ANARCHY` and later science recalculations collapse to `0`.
  [observed] `CityHasBuilding(...)` consumes quoted building names like
             `"IMPROVE_TEMPLE"`, while `CreateBuilding(...)` and event building
             comparisons consume `BuildingDB(IMPROVE_*)` integer DB handles.
  [observed] Any building referenced from MoM SLIC via `"IMPROVE_*"` names or
             `BuildingDB(IMPROVE_*)` must exist in buildings.txt, because that is
             the scenario SLIC symbol surface for city-building helpers and
             building-event comparisons.
  [inferred] A block exists iff its IDENT appears before a '{' in the file.
  [inferred] Valid ages are AGE_ONE..AGE_TEN as defined in age.txt.
  [inferred] GL sections are only expected for MoM-added blocks (from CSV), not for
             base CTP2 units / buildings which use their own description system.
"""

import csv
import re
import sys
import struct
from collections import Counter, defaultdict
from pathlib import Path
from PIL import Image, ImageDraw, ImageOps

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).parent.parent  # …/Scenarios/mom
TOOLS = Path(__file__).parent
MOMJR = TOOLS / "momjr_csv"
REPO_ROOT = ROOT.parent.parent
BASE_GAMEDATA = REPO_ROOT / "ctp2_data" / "default" / "gamedata"
SCENARIO  = ROOT / "scen0000"
GAMEDATA  = SCENARIO / "default" / "gamedata"
AIDATA    = SCENARIO / "default" / "aidata"
ENGDATA   = SCENARIO / "english" / "gamedata"
SPRITES_DIR = REPO_ROOT / "ctp2_data" / "default" / "graphics" / "sprites"
MOM_SPRITE_MIN = 91
SPR_MAGIC = b"FRPS\x03\x00\x01\x00"
OBSERVER_DIR = TOOLS / "observer_sheets"
PACKED_PICTURE_ARCHIVES = [
    REPO_ROOT / "ctp2_data" / "default" / "graphics" / "pictures" / "pic555.zfs",
    REPO_ROOT / "ctp2_data" / "default" / "graphics" / "pictures" / "pic565.zfs",
    REPO_ROOT / "ctp2_data" / "english" / "graphics" / "pictures" / "pic555.zfs",
    REPO_ROOT / "ctp2_data" / "english" / "graphics" / "pictures" / "pic565.zfs",
]

# ---------------------------------------------------------------------------
# Sanitize — must match ctp2_generator.py exactly
# ---------------------------------------------------------------------------
def sanitize(name: str) -> str:
    s = name.upper().replace(" ", "_").replace("'", "").replace("-", "_")
    s = re.sub(r'[^A-Z0-9_]', '', s)
    return re.sub(r'_+', '_', s).strip('_')

# ---------------------------------------------------------------------------
# File parsers
# ---------------------------------------------------------------------------
def block_ids(path: Path) -> set:
    """Return the set of block IDENTs declared in a CTP2 text file (any format)."""
    ids = set()
    if not path.exists():
        return ids
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        m = re.match(r'^([A-Z][A-Z0-9_]+)\s*\{', line.strip())
        if m:
            ids.add(m.group(1))
    return ids


def block_id_counts(path: Path) -> Counter:
    """Return IDENT occurrence counts from a CTP2 block file."""
    counts = Counter()
    if not path.exists():
        return counts
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        m = re.match(r'^([A-Z][A-Z0-9_]+)\s*\{', line.strip())
        if m:
            counts[m.group(1)] += 1
    return counts

def kv_map(path: Path, key: str) -> list:
    """Return all values for a given key anywhere in a CTP2 file.

    Handles both multi-line CTP2 format (key at line start) and the
    single-line block format produced by CTP2BlockFile.render() where
    keys appear inline within a brace block.
    """
    if not path.exists():
        return []
    text = path.read_text(encoding='utf-8', errors='replace')
    text = re.sub(r'(?m)^\s*#.*$', '', text)
    return re.findall(rf'\b{re.escape(key)}\s+(\S+)', text)


def diffdb_advance_chances(path: Path) -> list[list[tuple[str, int, int]]]:
    """Return ADVANCE_CHANCES blocks as [(advance_id, human_chance, ai_chance), ...]."""
    if not path.exists():
        return []
    text = path.read_text(encoding='utf-8', errors='replace')
    block_re = re.compile(r'(?ms)^\s*ADVANCE_CHANCES\s*\{\s*\n(.*?)^\s*\}', re.MULTILINE)
    entry_re = re.compile(r'^\s*(ADVANCE_[A-Z0-9_]+)\s+(\d+)\s+(\d+)\s*$', re.MULTILINE)
    blocks = []
    for body in block_re.findall(text):
        entries = [(advance_id, int(human), int(ai)) for advance_id, human, ai in entry_re.findall(body)]
        blocks.append(entries)
    return blocks


def block_texts(path: Path, prefix: str) -> dict:
    """Return nested-brace-safe block text keyed by IDENT for a prefix."""
    if not path.exists():
        return {}
    text = path.read_text(encoding='utf-8', errors='replace')
    blocks = {}
    lines = text.splitlines(keepends=True)
    i = 0
    while i < len(lines):
        match = re.match(rf'^({re.escape(prefix)}[A-Z0-9_]+)\s*\{{', lines[i])
        if not match:
            i += 1
            continue
        ident = match.group(1)
        depth = 0
        block_lines = []
        while i < len(lines):
            block_lines.append(lines[i])
            depth += lines[i].count('{') - lines[i].count('}')
            i += 1
            if len(block_lines) > 1 and depth <= 0:
                break
        blocks[ident] = ''.join(block_lines)
    return blocks


def top_level_record_order(path: Path) -> list[str]:
    """Return top-level record order for multi-line CTP2 databases like civilisation.txt."""
    if not path.exists():
        return []
    lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
    order = []
    for i, raw in enumerate(lines):
        match = re.match(r'^([A-Z][A-Z0-9_]+)(?:\s+#\d+)?\s*$', raw.strip())
        if not match:
            continue
        probe = i + 1
        while probe < len(lines) and lines[probe].strip() == '':
            probe += 1
        if probe < len(lines) and lines[probe].strip() == '{':
            order.append(match.group(1))
    return order

def gl_sections(path: Path) -> set:
    """Return set of section names from a Great_Library.txt file."""
    secs = set()
    if not path.exists():
        return secs
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        m = re.match(r'^\[([A-Z_0-9]+)\]$', line.strip())
        if m:
            secs.add(m.group(1))
    return secs

def age_refs_in_file(path: Path) -> list:
    """Return all 'Age AGE_X' values from Advance.txt."""
    return kv_map(path, 'Age')

def gl_stats_lines(gl_path: Path) -> list:
    """Return (section, line_content) pairs inside every _STATISTICS section."""
    results = []
    if not gl_path.exists():
        return results
    current = None
    for line in gl_path.read_text(encoding='utf-8', errors='replace').splitlines():
        s = line.strip()
        m = re.match(r'^\[([A-Z_0-9]+_STATISTICS)\]$', s)
        if m:
            current = m.group(1)
            continue
        if s == '[END]':
            current = None
            continue
        if current:
            results.append((current, s))
    return results

def tga_refs_in_file(path: Path) -> set:
    """Return all TGA filenames referenced in a file (uppercased)."""
    tgas = set()
    if not path.exists():
        return tgas
    for val in re.findall(r'"([^"]+\.(?:TGA|tga))"',
                          path.read_text(encoding='utf-8', errors='replace')):
        tgas.add(val.upper())
    return tgas


def uniticon_line_map(path: Path) -> dict:
    """Return raw single-line uniticon/wondericon-style entries by icon ID."""
    entries = {}
    if not path.exists():
        return entries
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        m = re.match(r'^([A-Z][A-Z0-9_]+)\s*\{.*\}$', line.strip())
        if m:
            entries[m.group(1)] = line.strip()
    return entries


def uniticon_text_refs(line: str) -> list[tuple[str, str]]:
    """Return symbolic text refs from a rendered uniticon entry."""
    refs = []
    for field in ("Gameplay", "Historical", "Prereq", "Vari", "StatText"):
        match = re.search(rf'\b{field}\s+"([^"]+)"', line)
        if not match:
            continue
        value = match.group(1).strip()
        if not value or value.upper() == "NULL" or value.lower().endswith(".txt"):
            continue
        refs.append((field, value))
    return refs


def block_has_hidden_flag(block_text: str) -> bool:
    """Return whether a raw block is intentionally hidden from normal UI surfaces."""
    return bool(re.search(r'^\s*(?:NoIndex|GLHidden)\s*$', block_text, re.MULTILINE))


def block_field_value(block_text: str, field: str) -> str:
    """Extract a simple single-token field from a raw block."""
    match = re.search(rf'\b{re.escape(field)}\s+(\S+)', block_text)
    return match.group(1).strip() if match else ""


def tga_header(path: Path) -> dict | None:
    """Return a minimal parsed TGA header or None if the file is unreadable."""
    if not path.exists() or path.stat().st_size < 18:
        return None
    raw = path.read_bytes()[:18]
    return {
        "image_type": raw[2],
        "width": struct.unpack_from("<H", raw, 12)[0],
        "height": struct.unpack_from("<H", raw, 14)[0],
        "bpp": raw[16],
        "descriptor": raw[17],
    }


def string_ids(path: Path) -> set:
    """Return string IDs present in gl_str.txt."""
    ids = set()
    if not path.exists():
        return ids
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        m = re.match(r'^([A-Z][A-Z0-9_]+)\s+', line)
        if m:
            ids.add(m.group(1))
    return ids


def first_tga_ref(line: str) -> str | None:
    """
    Return the first TGA filename referenced in a rendered uniticon entry line.

    Prefer FirstFrame because it is the large portrait surface the Great Library
    actually shows for improvements / tile improvements.
    """
    if not line:
        return None

    first_frame = re.search(r'FirstFrame\s+"([^"]+\.(?:TGA|tga))"', line)
    if first_frame:
        return first_frame.group(1)

    icon = re.search(r'Icon\s+"([^"]+\.(?:TGA|tga))"', line)
    if icon:
        return icon.group(1)
    return None


def resolve_picture_asset(filename: str, picture_dirs: list[Path]) -> Path | None:
    """Resolve a referenced TGA filename across scenario/base picture search paths."""
    target = filename.upper()
    for picture_dir in picture_dirs:
        if not picture_dir.exists():
            continue
        direct = picture_dir / filename
        if direct.exists():
            return direct
        for candidate in picture_dir.glob("*"):
            if candidate.name.upper() == target:
                return candidate
    return None


def image_stats(path: Path) -> dict:
    """
    Return basic image stats used for blank-image detection.

    Guarantee: returns width/height plus non_black and unique-color counts.
    Failure modes: Pillow will raise if the file is unreadable.
    """
    img = Image.open(path).convert("RGB")
    px = img.load()
    non_black = 0
    colors = set()
    for y in range(img.height):
        for x in range(img.width):
            rgb = px[x, y]
            colors.add(rgb)
            if rgb != (0, 0, 0):
                non_black += 1
    return {
        "width": img.width,
        "height": img.height,
        "non_black": non_black,
        "unique_colors": len(colors),
    }


def render_contact_sheet(entries: list[tuple[str, Image.Image]], out_path: Path, thumb_size=(160, 120), columns: int = 4) -> Path | None:
    """
    Render a labeled contact sheet PNG for observer spot-checking.

    Require: entries contain (label, PIL image) tuples.
    Guarantee: writes a PNG contact sheet and returns its path, or returns None
    when there are no entries.
    """
    if not entries:
        return None

    label_h = 24
    margin = 8
    tile_w = thumb_size[0] + margin * 2
    tile_h = thumb_size[1] + label_h + margin * 2
    rows = (len(entries) + columns - 1) // columns
    canvas = Image.new("RGB", (columns * tile_w, rows * tile_h), (24, 24, 24))
    draw = ImageDraw.Draw(canvas)

    for idx, (label, image) in enumerate(entries):
        col = idx % columns
        row = idx // columns
        x0 = col * tile_w
        y0 = row * tile_h
        box = (x0 + margin, y0 + margin, x0 + margin + thumb_size[0], y0 + margin + thumb_size[1])
        thumb = ImageOps.contain(image.convert("RGB"), thumb_size, Image.NEAREST)
        paste_x = box[0] + (thumb_size[0] - thumb.width) // 2
        paste_y = box[1] + (thumb_size[1] - thumb.height) // 2
        canvas.paste(thumb, (paste_x, paste_y))
        draw.rectangle([box[0] - 1, box[1] - 1, box[2], box[3]], outline=(96, 96, 96), width=1)
        draw.text((x0 + margin, y0 + margin + thumb_size[1] + 4), label[:24], fill=(220, 220, 220))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, format="PNG")
    return out_path


def build_resolved_icon_entries(icon_ids: set[str], line_map: dict, picture_dirs: list[Path]) -> tuple[list[tuple[str, Path]], list[str]]:
    """
    Resolve icon IDs from uniticon.txt to concrete image files.

    Returns:
      - resolved entries as (icon_id, asset_path)
      - issues for missing line or missing referenced file
    """
    resolved = []
    issues = []
    for icon_id in sorted(icon_ids):
        line = line_map.get(icon_id, "")
        tga_name = first_tga_ref(line)
        if not tga_name:
            issues.append(f"{icon_id} -> no TGA ref in uniticon.txt")
            continue
        asset_path = resolve_picture_asset(tga_name, picture_dirs)
        if asset_path is None:
            issues.append(f"{icon_id} -> missing {tga_name}")
            continue
        resolved.append((icon_id, asset_path))
    return resolved, issues


def build_green_grid_sheet(sheet_key: str) -> list[tuple[str, Image.Image]]:
    """
    Build contact-sheet entries for green-grid source sheets.

    These are source-art observer surfaces, not uniticon-resolved assets.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parents[2].parent))
    import civ2_sprite_extractor as extractor

    cells = extractor.load_green_grid_cells(sheet_key)
    return [(f"{sheet_key}_{idx:03d}", cell) for idx, cell in enumerate(cells)]


_PACKED_PICTURE_BYTES: list[bytes] | None = None


def packed_picture_has_asset(filename: str) -> bool:
    """
    Return True when a picture stem is embedded in one of the stock ZFS archives.

    ZFS entries do not expose plain `.tga` names as easy text strings, but the
    uppercase stem bytes do occur in the archive and are sufficient for the
    checklist's "graphics present" test.
    """
    global _PACKED_PICTURE_BYTES
    if _PACKED_PICTURE_BYTES is None:
        _PACKED_PICTURE_BYTES = [path.read_bytes().upper() for path in PACKED_PICTURE_ARCHIVES if path.exists()]

    stem = Path(filename).stem.upper().encode("ascii", errors="ignore")
    return any(stem and stem in blob for blob in _PACKED_PICTURE_BYTES)


def build_sheet_contact_entries(sheet_key: str, identifiers: list[tuple[int, str, str]], start_index: int = 0) -> list[tuple[str, Image.Image]]:
    """
    Build contact-sheet entries from a source BMP sheet by CSV order.

    This is the observer surface for dimensions whose in-game art remains packed
    inside stock ZFS archives.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parents[2].parent))
    import civ2_sprite_extractor as extractor

    cells = extractor.load_sheet_cells(sheet_key)
    entries = []
    for local_idx, (_, _, name) in enumerate(identifiers):
        cell_idx = start_index + local_idx
        if cell_idx >= len(cells):
            break
        entries.append((name, cells[cell_idx]))
    return entries

# ---------------------------------------------------------------------------
# CSV loaders — filtering must mirror ctp2_generator.py exactly
# ---------------------------------------------------------------------------
def _is_stub_unit(name: str) -> bool:
    """Match the generator's skip logic for placeholder unit rows."""
    if not name or name.lower() == 'blah':
        return True
    if len(name) == 2 and name[0].upper() == 'B' and name[1].isdigit():
        return True
    return False

def load_advance_names(csv_path: Path) -> list:
    names = []
    if not csv_path.exists():
        return names
    with open(csv_path, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            n = row['name'].split(';')[0].strip()
            if not n or n.lower() == 'blah' or n.startswith('x') or 'Extra Advance' in n:
                continue
            names.append(n)
    return names

def load_unit_names(csv_path: Path) -> list:
    names = []
    if not csv_path.exists():
        return names
    with open(csv_path, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            n = row['name'].strip()
            if _is_stub_unit(n):
                continue
            names.append(n)
    return names

def load_building_names(csv_path: Path) -> list:
    names = []
    if not csv_path.exists():
        return names
    with open(csv_path, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            n = row['name'].strip()
            if not n or n.startswith('x') or n == 'Nothing' or 'SS ' in n:
                continue
            names.append(n)
    return names

def load_tileimp_names(csv_path: Path) -> list:
    names = []
    if not csv_path.exists():
        return names
    with open(csv_path, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            n = row['name'].strip()
            if not n or n.startswith('x') or n == 'Nothing':
                continue
            names.append(n)
    return names


def load_new_civ_ids(csv_path: Path) -> list[str]:
    ids = []
    if not csv_path.exists():
        return ids
    with open(csv_path, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            if row.get('ctp2_is_new', '').strip().lower() != 'yes':
                continue
            civ_id = row.get('ctp2_civ_id', '').strip()
            if civ_id:
                ids.append(civ_id)
    return ids

# ---------------------------------------------------------------------------
# Checklist runner
# ---------------------------------------------------------------------------
PASS  = 'PASS '
FAIL  = 'FAIL '
WARN  = 'WARN '
DEFER = 'DEFER '
INFO  = 'INFO '

results = []

def check(status, dimension, name, detail=''):
    results.append((status, dimension, name, detail))
    icon = {'PASS ': '+', 'FAIL ': '!', 'WARN ': '?', 'INFO ': 'i', 'DEFER ': '~'}[status]
    print(f"  {icon} [{status.strip()}] {name}")
    if detail:
        for line in detail.splitlines():
            print(f"         {line}")

# ===========================================================================
# Load everything up front
# ===========================================================================
print("\n=== Loading game files ===")

advance_ids   = block_ids(GAMEDATA / "Advance.txt")
unit_ids      = block_ids(GAMEDATA / "Units.txt")
unit_blocks   = block_texts(GAMEDATA / "Units.txt", "UNIT_")
improve_ids   = block_ids(GAMEDATA / "Improve.txt")   # MoM buildings live here or in buildings.txt
improve_blocks = block_texts(GAMEDATA / "Improve.txt", "IMPROVE_")
govern_blocks = block_texts(GAMEDATA / "govern.txt", "GOVERNMENT_")
base_govern_blocks = block_texts(BASE_GAMEDATA / "govern.txt", "GOVERNMENT_")
buildings_txt_ids = block_ids(GAMEDATA / "buildings.txt") if (GAMEDATA / "buildings.txt").exists() else set()
buildings_txt_blocks = block_texts(GAMEDATA / "buildings.txt", "IMPROVE_") if (GAMEDATA / "buildings.txt").exists() else {}
wonder_ids    = block_ids(GAMEDATA / "Wonder.txt")
wonder_blocks = block_texts(GAMEDATA / "Wonder.txt", "WONDER_")
tileimp_ids   = block_ids(GAMEDATA / "tileimp.txt")
tileimp_blocks = block_texts(GAMEDATA / "tileimp.txt", "TILEIMP_")
icon_ids      = block_ids(GAMEDATA / "uniticon.txt")
valid_ages    = block_ids(GAMEDATA / "age.txt")
advance_counts = block_id_counts(GAMEDATA / "Advance.txt")
unit_counts    = block_id_counts(GAMEDATA / "Units.txt")
improve_counts = block_id_counts(GAMEDATA / "Improve.txt")
wonder_counts  = block_id_counts(GAMEDATA / "Wonder.txt")
tileimp_counts = block_id_counts(GAMEDATA / "tileimp.txt")
gl_str_ids     = string_ids(ENGDATA / "gl_str.txt")

gl_main   = gl_sections(ENGDATA / "Great_Library.txt")
gl_waw    = gl_sections(ENGDATA / "WAW_Great_Library.txt") if (ENGDATA / "WAW_Great_Library.txt").exists() else set()
gl_all    = gl_main | gl_waw
scenario_slc_path = GAMEDATA / "scenario.slc"
scenario_slc_text = scenario_slc_path.read_text(encoding='utf-8', errors='replace') if scenario_slc_path.exists() else ""
mom_slic_building_refs = set()
for slic_name in ("mom_func.slc", "mom_turns.slc", "mom_city_effects.slc"):
    slic_path = GAMEDATA / slic_name
    if slic_path.exists():
        slic_text = slic_path.read_text(encoding='utf-8', errors='replace')
        mom_slic_building_refs.update(re.findall(r'BuildingDB\((IMPROVE_[A-Z0-9_]+)\)', slic_text))
        mom_slic_building_refs.update(re.findall(r'CityHasBuilding\([^,\n]+,\s*"(IMPROVE_[A-Z0-9_]+)"\)', slic_text))

csv_advances  = load_advance_names(MOMJR / "advances.csv")
csv_units     = load_unit_names(MOMJR / "units.csv")
csv_buildings = load_building_names(MOMJR / "improvements.csv")
csv_tileimps  = load_tileimp_names(MOMJR / "tileimp.csv")
csv_new_civs  = load_new_civ_ids(MOMJR / "players.csv")
civ_order     = top_level_record_order(GAMEDATA / "civilisation.txt")

# Derive expected IDs from CSVs
exp_advance_ids  = {f"ADVANCE_{sanitize(n)}" for n in csv_advances}
exp_unit_ids     = {f"UNIT_{sanitize(n)}"    for n in csv_units}
exp_building_ids = {f"IMPROVE_{sanitize(n)}" for n in csv_buildings}
exp_tileimp_ids  = {f"TILEIMP_{sanitize(n)}" for n in csv_tileimps}

# Blocks the generator deliberately retires (never buildable, removed from the
# DB; their uniticon/GL surfaces are intentionally kept). Excluded from
# coverage and dangling-icon checks — see _retune docstring in ctp2_generator.py.
RETIRED_BUILDING_IDS = {"IMPROVE_HIDE_SUPERMARKET"}
exp_building_ids -= RETIRED_BUILDING_IDS

print(f"  Advance.txt:  {len(advance_ids)} blocks")
print(f"  Units.txt:    {len(unit_ids)} blocks")
print(f"  Improve.txt:  {len(improve_ids)} blocks (includes base CTP2 + MoM)")
print(f"  Wonder.txt:   {len(wonder_ids)} blocks")
print(f"  tileimp.txt:  {len(tileimp_ids)} blocks")
print(f"  uniticon.txt: {len(icon_ids)} entries")
print(f"  GL sections:  {len(gl_all)} total")
print(f"  Valid ages:   {sorted(valid_ages)[:5]}...")
print(f"  CSV advances: {len(csv_advances)} -> {len(exp_advance_ids)} expected IDs")
print(f"  CSV units:    {len(csv_units)} -> {len(exp_unit_ids)} expected IDs")
print(f"  CSV buildings:{len(csv_buildings)} -> {len(exp_building_ids)} expected IDs")
print(f"  CSV tileimps: {len(csv_tileimps)} -> {len(exp_tileimp_ids)} expected IDs")

# ===========================================================================
# DIMENSION 1 — File population
# ===========================================================================
print("\n=== Dimension 1: File Population ===")
for label, path, min_count, count_fn in [
    ("Advance.txt",       GAMEDATA/"Advance.txt",       50,  lambda: len(advance_ids)),
    ("Units.txt",         GAMEDATA/"Units.txt",         10,  lambda: len(unit_ids)),
    # Improvements load from buildings.txt per gamefile.txt; Improve.txt is NOT loaded
    # by the engine and is intentionally removed by the generator.
    ("buildings.txt",     GAMEDATA/"buildings.txt",     40,  lambda: len(buildings_txt_ids)),
    ("Wonder.txt",        GAMEDATA/"Wonder.txt",         1,  lambda: len(wonder_ids)),
    ("tileimp.txt",       GAMEDATA/"tileimp.txt",       40,  lambda: len(tileimp_ids)),
    ("uniticon.txt",      GAMEDATA/"uniticon.txt",      100, lambda: len(icon_ids)),
    ("Great_Library.txt", ENGDATA/"Great_Library.txt",  100, lambda: len(gl_main)),
    ("gl_str.txt",        ENGDATA/"gl_str.txt",          10,
     lambda: sum(1 for _ in (ENGDATA/"gl_str.txt").read_text(encoding='utf-8', errors='replace').splitlines() if _.strip() and not _.strip().startswith('//'))),
]:
    if not path.exists():
        check(FAIL, "file-population", f"{label} exists", f"File not found: {path}")
    else:
        count = count_fn()
        if count >= min_count:
            check(PASS, "file-population", f"{label} populated ({count} entries)")
        else:
            check(WARN, "file-population", f"{label} sparse ({count} < {min_count} expected)")

for slic_name in ("mom_func.slc", "mom_turns.slc", "mom_city_effects.slc"):
    slic_path = GAMEDATA / slic_name
    unintegrated_path = TOOLS / "_unintegrated" / slic_name
    if slic_path.exists():
        check(PASS, "file-population", f"{slic_name} exists")
    elif unintegrated_path.exists():
        check(DEFER, "file-population", f"{slic_name} exists", f"Deferred to _unintegrated/")
    else:
        check(FAIL, "file-population", f"{slic_name} exists", f"File not found: {slic_path}")

missing_slic_includes = [
    slic_name for slic_name in ("mom_func.slc", "mom_turns.slc", "mom_city_effects.slc")
    if not (TOOLS / "_unintegrated" / slic_name).exists() and f'#include "{slic_name}"' not in scenario_slc_text
]
if missing_slic_includes:
    check(FAIL, "file-population", "scenario.slc includes MoM SLIC modules",
          "\n".join(missing_slic_includes))
else:
    check(PASS, "file-population", "scenario.slc includes MoM SLIC modules")

if not civ_order:
    check(FAIL, "file-population", "civilisation.txt: parsed record order", "No civilisation records parsed")
elif not csv_new_civs:
    check(WARN, "file-population", "civilisation.txt: MoM tribe order skipped", "players.csv has no ctp2_is_new civ rows")
else:
    expected_order = ["BARBARIAN"] + csv_new_civs
    if civ_order == expected_order:
        check(PASS, "file-population",
              f"civilisation.txt: scenario civ list is BARBARIAN + MoM tribes only ({', '.join(csv_new_civs)})")
    else:
        check(FAIL, "file-population",
              "civilisation.txt: scenario civ list is MoM-only",
              f"Expected order: {', '.join(expected_order)}\nActual order: {', '.join(civ_order)}")

# ===========================================================================
# DIMENSION 2 — CSV coverage
# ===========================================================================
print("\n=== Dimension 2: CSV -> Game File Coverage ===")

def audit_csv_coverage(label, expected, game_ids, file_label):
    missing = expected - game_ids
    if not missing:
        check(PASS, "csv-coverage", f"{label}: all {len(expected)} CSV entries in {file_label}")
    else:
        sample = sorted(missing)[:5]
        more = f"\n  ...and {len(missing)-5} more" if len(missing) > 5 else ""
        check(FAIL, "csv-coverage", f"{label}: {len(missing)}/{len(expected)} missing from {file_label}",
              "\n".join(sample) + more)

audit_csv_coverage("Advances",  exp_advance_ids,  advance_ids,  "Advance.txt")
audit_csv_coverage("Units",     exp_unit_ids,     unit_ids,     "Units.txt")

# Buildings can live in Improve.txt, buildings.txt, OR have been migrated to Wonder.txt.
# Accept any location as valid.
effective_building_ids = improve_ids | buildings_txt_ids | {wid.replace("WONDER_", "IMPROVE_", 1) for wid in wonder_ids}
audit_csv_coverage("Buildings", exp_building_ids, effective_building_ids, "Improve.txt or buildings.txt or Wonder.txt")

def audit_duplicate_ids(label, counts):
    dupes = {ident: n for ident, n in counts.items() if n > 1}
    if not dupes:
        check(PASS, "csv-coverage", f"{label}: no duplicate block IDs")
    else:
        sample = [f"{ident} ({n}x)" for ident, n in sorted(dupes.items())[:10]]
        more = f"\n  ...and {len(dupes)-10} more" if len(dupes) > 10 else ""
        check(FAIL, "csv-coverage", f"{label}: {len(dupes)} duplicate block IDs",
              "\n".join(sample) + more)

audit_duplicate_ids("Advance.txt", advance_counts)
audit_duplicate_ids("Units.txt", unit_counts)
audit_duplicate_ids("Improve.txt", improve_counts)
audit_duplicate_ids("Wonder.txt", wonder_counts)
audit_duplicate_ids("tileimp.txt", tileimp_counts)

# ===========================================================================
# DIMENSION 3 — Icon / image coverage
# ===========================================================================
print("\n=== Dimension 3: Icon / Image Coverage ===")

# Advances: Icon key
adv_icon_refs  = set(kv_map(GAMEDATA / "Advance.txt",  "Icon"))
# Units: DefaultIcon key
unit_icon_refs = set(kv_map(GAMEDATA / "Units.txt",    "DefaultIcon"))
# Buildings (Improve.txt + buildings.txt): IMPROVE_DEFAULT_ICON / DefaultIcon keys
bld_icon_refs  = set(kv_map(GAMEDATA / "Improve.txt",  "IMPROVE_DEFAULT_ICON"))
bld_icon_refs |= set(kv_map(GAMEDATA / "buildings.txt", "DefaultIcon")) if (GAMEDATA / "buildings.txt").exists() else set()
# Wonders: DefaultIcon key
won_icon_refs  = set(kv_map(GAMEDATA / "Wonder.txt",   "DefaultIcon"))
# TileImps: Icon key
tileimp_icon_refs = set(kv_map(GAMEDATA / "tileimp.txt", "Icon"))

def audit_icons(label, refs, registry, reg_label, skip_prefix=None):
    check_refs = {r for r in refs if skip_prefix is None or r.startswith(skip_prefix)}
    missing = check_refs - registry
    if not missing:
        check(PASS, "icon-coverage", f"{label}: all {len(check_refs)} Icon refs resolve in {reg_label}")
    else:
        sample = sorted(missing)[:5]
        more = f"\n  ...and {len(missing)-5} more" if len(missing) > 5 else ""
        check(FAIL, "icon-coverage", f"{label}: {len(missing)} Icon refs missing from {reg_label}",
              "\n".join(sample) + more)

audit_icons("Advance icons",  adv_icon_refs,  icon_ids,         "uniticon.txt", skip_prefix="ICON_ADVANCE_")
audit_icons("Unit icons",     unit_icon_refs, icon_ids,         "uniticon.txt", skip_prefix="ICON_UNIT_")
audit_icons("Building icons", bld_icon_refs,  icon_ids,         "uniticon.txt")
audit_icons("Wonder icons",   won_icon_refs,  icon_ids,         "uniticon.txt")
audit_icons("TileImp icons",  tileimp_icon_refs, icon_ids, "uniticon.txt", skip_prefix="ICON_TILEIMP_")

# Bad TGA check — CM2_Upap001l.tga is the crosshatch diagram (visually broken)
# Note: this TGA also appears in baseline uniticon.txt entries we don't own — WARN not FAIL
# Check for dangling building icon references in uniticon.txt
# Every ICON_IMPROVE_* in uniticon.txt must have a corresponding IMPROVE_* in buildings.txt or Improve.txt
# Otherwise, the CTP2 engine throws "X not found in Building database" on startup.
uniticon_bld_icons = {icon_id for icon_id in icon_ids if icon_id.startswith("ICON_IMPROVE_")}
dangling_bld_icons = []
for icon_id in sorted(uniticon_bld_icons):
    bld_id = "IMPROVE_" + icon_id[len("ICON_IMPROVE_"):]
    if bld_id not in effective_building_ids and bld_id not in RETIRED_BUILDING_IDS:
        dangling_bld_icons.append(f"{icon_id} -> {bld_id}")

if dangling_bld_icons:
    sample = dangling_bld_icons[:10]
    more = f"\n  ...and {len(dangling_bld_icons)-10} more" if len(dangling_bld_icons) > 10 else ""
    check(FAIL, "cross-refs", f"uniticon.txt: {len(dangling_bld_icons)} building icon(s) with no matching building in DB",
          "\n".join(sample) + more)
else:
    check(PASS, "cross-refs", "uniticon.txt: all building icons have matching DB entries")

BAD_TGA = "CM2_UPAP001L.TGA"
tgas = tga_refs_in_file(GAMEDATA / "uniticon.txt")
if BAD_TGA in tgas:
    check(WARN, "icon-coverage", f"Bad TGA found in uniticon.txt: {BAD_TGA}",
          "Pre-existing baseline entries; our generated entries use UPLG001.TGA.\n"
          "Run a full reconciliation pass to clean up baseline entries if needed.")
else:
    check(PASS, "icon-coverage", f"No bad TGA ({BAD_TGA}) in uniticon.txt")

# CSV-owned unit icon asset format check — generated loose TGAs must match the
# validated CTP2-safe contract for this scenario: 160x120, uncompressed
# true-color, 16-bit RGB555, descriptor 0x00.
PICTURE_DIRS = [
    ROOT / "scen0000" / "default" / "graphics" / "pictures",
    REPO_ROOT / "ctp2_data" / "default" / "graphics" / "pictures",
    REPO_ROOT / "ctp2_data" / "english" / "graphics" / "pictures",
]
csv_unit_icon_ids = {f"ICON_UNIT_{sanitize(name)}" for name in csv_units}
UNITICON_LINES = uniticon_line_map(GAMEDATA / "uniticon.txt")
applied_csv_unit_icon_ids = {
    icon_id
    for icon_id in csv_unit_icon_ids
    if f'"{icon_id}.TGA"' in UNITICON_LINES.get(icon_id, "").upper()
}
bad_csv_unit_icon_files = []
for icon_id in sorted(applied_csv_unit_icon_ids):
    filename = f"{icon_id}.tga"
    asset_path = None
    for picture_dir in PICTURE_DIRS:
        candidate = picture_dir / filename
        if candidate.exists():
            asset_path = candidate
            break
    if asset_path is None:
        bad_csv_unit_icon_files.append(f"{icon_id} -> missing {filename}")
        continue

    header = tga_header(asset_path)
    if header is None:
        bad_csv_unit_icon_files.append(f"{icon_id} -> unreadable header")
        continue

    if (
        header["image_type"] != 2
        or header["width"] != 160
        or header["height"] != 120
        or header["bpp"] != 16
        or header["descriptor"] != 0x00
    ):
        bad_csv_unit_icon_files.append(
            f"{icon_id} -> {asset_path.name} "
            f"type={header['image_type']} {header['width']}x{header['height']} "
            f"bpp={header['bpp']} desc=0x{header['descriptor']:02X}"
        )

if not applied_csv_unit_icon_ids:
    check(INFO, "icon-coverage", "CSV-owned unit icon TGAs are not currently applied; proxy baseline is active")
elif bad_csv_unit_icon_files:
    sample = bad_csv_unit_icon_files[:10]
    more = f"\n  ...and {len(bad_csv_unit_icon_files)-10} more" if len(bad_csv_unit_icon_files) > 10 else ""
    check(FAIL, "icon-coverage", f"{len(bad_csv_unit_icon_files)} CSV-owned unit icon files fail TGA format checks",
          "\n".join(sample) + more)
else:
    check(PASS, "icon-coverage", f"All {len(applied_csv_unit_icon_ids)} applied CSV-owned unit icon files match 160x120 RGB555 TGA format")

# Resolve actual large-art assets for the unit family and generate observer
# contact sheets. Units are scenario-owned loose assets, so we can verify the
# concrete TGA files directly.
# Migrated wonders use ICON_WONDER_* in uniticon.txt; regular improvements use ICON_IMPROVE_*.
_migrated_wonder_improve_ids = {wid.replace("WONDER_", "IMPROVE_", 1) for wid in wonder_ids}
csv_building_icon_ids = {
    (f"ICON_WONDER_{sanitize(name)}" if f"IMPROVE_{sanitize(name)}" in _migrated_wonder_improve_ids
     else f"ICON_IMPROVE_{sanitize(name)}")
    for name in csv_buildings
}
csv_tileimp_icon_ids = {f"ICON_TILEIMP_{sanitize(name)}" for name in csv_tileimps}

resolved_unit_entries, unit_resolve_issues = build_resolved_icon_entries(applied_csv_unit_icon_ids, UNITICON_LINES, PICTURE_DIRS)
if unit_resolve_issues:
    sample = unit_resolve_issues[:10]
    more = f"\n  ...and {len(unit_resolve_issues)-10} more" if len(unit_resolve_issues) > 10 else ""
    check(FAIL, "icon-coverage", f"units: {len(unit_resolve_issues)} referenced art file(s) unresolved",
          "\n".join(sample) + more)
else:
    check(PASS, "icon-coverage", f"units: all {len(resolved_unit_entries)} referenced art files resolve on disk")

blank_unit_assets = []
unit_contact_entries = []
for icon_id, asset_path in resolved_unit_entries:
    stats = image_stats(asset_path)
    if stats["non_black"] == 0 or stats["unique_colors"] <= 1:
        blank_unit_assets.append(f"{icon_id} -> {asset_path.name} ({stats['width']}x{stats['height']}, non_black={stats['non_black']})")
    unit_contact_entries.append((icon_id.replace("ICON_", ""), Image.open(asset_path)))

if blank_unit_assets:
    sample = blank_unit_assets[:10]
    more = f"\n  ...and {len(blank_unit_assets)-10} more" if len(blank_unit_assets) > 10 else ""
    check(FAIL, "icon-coverage", f"units: {len(blank_unit_assets)} referenced art file(s) appear blank",
          "\n".join(sample) + more)
else:
    check(PASS, "icon-coverage", "units: no referenced art files are fully blank")

sheet_path = render_contact_sheet(unit_contact_entries, OBSERVER_DIR / "units_contact_sheet.png")
if sheet_path is not None:
    check(INFO, "icon-coverage", "units: observer contact sheet written", str(sheet_path))

# Improvements and tile improvements mostly resolve to stock packed picture
# archives. Treat packed-archive hits as present, then render observer sheets
# from the source Improvements.bmp layout because the packed ZFS assets are not
# loose files we can open directly.
RETIRED_ICON_IDS = {f"ICON_{b}" for b in RETIRED_BUILDING_IDS}
for family_name, family_icon_ids in (("improvements", csv_building_icon_ids - RETIRED_ICON_IDS), ("tileimps", tileimp_icon_refs)):
    unresolved = []
    for icon_id in sorted(family_icon_ids):
        line = UNITICON_LINES.get(icon_id, "")
        tga_name = first_tga_ref(line)
        if not tga_name:
            unresolved.append(f"{icon_id} -> no TGA ref in uniticon.txt")
            continue
        asset_path = resolve_picture_asset(tga_name, PICTURE_DIRS)
        if asset_path is None and not packed_picture_has_asset(tga_name):
            unresolved.append(f"{icon_id} -> missing {tga_name} (loose + packed)")

    if unresolved:
        sample = unresolved[:10]
        more = f"\n  ...and {len(unresolved)-10} more" if len(unresolved) > 10 else ""
        check(FAIL, "icon-coverage", f"{family_name}: {len(unresolved)} referenced art file(s) unresolved",
              "\n".join(sample) + more)
    else:
        check(PASS, "icon-coverage", f"{family_name}: all {len(family_icon_ids)} referenced art files resolve loose or packed")

improvement_sheet_entries = build_sheet_contact_entries(
    "improvements",
    [(idx, "", name) for idx, name in enumerate(csv_buildings)],
    start_index=0,
)
sheet_path = render_contact_sheet(improvement_sheet_entries, OBSERVER_DIR / "improvements_source_contact_sheet.png")
if sheet_path is not None:
    check(INFO, "icon-coverage", "improvements: source contact sheet written", str(sheet_path))

tileimp_sheet_entries = build_sheet_contact_entries(
    "improvements",
    [(idx, "", name) for idx, name in enumerate(csv_tileimps)],
    start_index=len(csv_buildings),
)
sheet_path = render_contact_sheet(tileimp_sheet_entries, OBSERVER_DIR / "tileimps_source_contact_sheet.png")
if sheet_path is not None:
    check(INFO, "icon-coverage", "tileimps: source contact sheet written", str(sheet_path))

for green_sheet in ("terrain2", "cities"):
    green_entries = build_green_grid_sheet(green_sheet)
    sheet_path = render_contact_sheet(green_entries, OBSERVER_DIR / f"{green_sheet}_source_contact_sheet.png")
    if sheet_path is not None:
        check(INFO, "icon-coverage", f"{green_sheet}: source contact sheet written",
              str(sheet_path))

# ===========================================================================
# DIMENSION 4 — Age distribution
# ===========================================================================
print("\n=== Dimension 4: Age Distribution ===")

age_vals = age_refs_in_file(GAMEDATA / "Advance.txt")
age_counts = defaultdict(int)
bad_ages = []
for a in age_vals:
    if a in valid_ages:
        age_counts[a] += 1
    else:
        bad_ages.append(a)

if bad_ages:
    uniq = sorted(set(bad_ages))
    check(FAIL, "age-distribution", f"{len(bad_ages)} invalid age refs in Advance.txt",
          f"Unknown ages: {uniq}")
else:
    check(PASS, "age-distribution", "All Age refs in Advance.txt use valid age IDs")

for age in sorted(age_counts):
    check(INFO, "age-distribution", f"  {age}: {age_counts[age]} advances")

must_have = {'AGE_ONE', 'AGE_TWO', 'AGE_THREE'}
empty = [a for a in must_have if age_counts.get(a, 0) == 0]
if empty:
    check(WARN, "age-distribution", f"Expected ages with zero advances: {empty}")
else:
    check(PASS, "age-distribution", "AGE_ONE/TWO/THREE all have advances")

# ---------------------------------------------------------------------------
# Cost-band sanity — guards the research-cost pathology (raw base/WAW tail up to
# 234743 + Cost==1 outlier made mid/late tech take thousands of turns; AGE_ONE must
# stay <640 so first advances complete in <40 turns at ~16 science). See
# ctp2_generator._load_ae_advance_cost_bands.
# ---------------------------------------------------------------------------
import re as _re_cost
_AGE_RANK = {'AGE_ONE':1,'AGE_TWO':2,'AGE_THREE':3,'AGE_FOUR':4,'AGE_FIVE':5,
             'AGE_SIX':6,'AGE_SEVEN':7,'AGE_EIGHT':8,'AGE_NINE':9,'AGE_TEN':10}
_adv_text = (GAMEDATA / "Advance.txt").read_text(encoding="latin-1")
_age_cost = defaultdict(list)
for _blk in _re_cost.split(r'(?=^ADVANCE_[A-Z0-9_]+\s*\{)', _adv_text, flags=_re_cost.M):
    _a = _re_cost.search(r'^\s*Age\s+(AGE_[A-Z_]+)', _blk, _re_cost.M)
    _c = _re_cost.search(r'^\s*Cost\s+(\d+)', _blk, _re_cost.M)
    if _a and _c:
        _age_cost[_a.group(1)].append(int(_c.group(1)))
_all_costs = [c for v in _age_cost.values() for c in v]
if _all_costs:
    _mx = max(_all_costs)
    check(PASS if _mx < 20000 else FAIL, "cost-band",
          f"max advance cost {_mx} {'<' if _mx < 20000 else '>='} 20000 (no 6-figure pathology)")
    _tiny = [c for c in _all_costs if c < 50]
    check(PASS if not _tiny else FAIL, "cost-band",
          "no advance Cost < 50" if not _tiny else f"{len(_tiny)} advance(s) with Cost < 50 (e.g. {_tiny[:3]})")
    _one_hi = max(_age_cost.get('AGE_ONE', [0]))
    check(PASS if _one_hi <= 640 else FAIL, "cost-band",
          f"AGE_ONE max cost {_one_hi} {'<=' if _one_hi <= 640 else '>'} 640 (first advances <40 turns @16 science)")
    # per-age median must not decrease as age rises
    _meds = []
    for _a in sorted(_age_cost, key=lambda a: _AGE_RANK.get(a, 0)):
        _v = sorted(_age_cost[_a]); _meds.append((_a, _v[len(_v)//2]))
    _mono = all(_meds[i][1] <= _meds[i+1][1] for i in range(len(_meds)-1))
    check(PASS if _mono else WARN, "cost-band",
          "per-age median cost is monotonic (early cheaper than late)"
          if _mono else f"per-age median not monotonic: {_meds}")

# ===========================================================================
# DIMENSION 5 — GL completeness (MoM-added blocks only)
# ===========================================================================
print("\n=== Dimension 5: GL Completeness (MoM CSV blocks only) ===")

GL_SUFFIXES = ("_STATISTICS", "_GAMEPLAY", "_HISTORICAL", "_PREREQ")

def audit_gl(label, ids, suffixes=GL_SUFFIXES, gl_set=gl_all):
    missing_by_suffix = defaultdict(list)
    for ident in sorted(ids):
        for suf in suffixes:
            if f"{ident}{suf}" not in gl_set:
                missing_by_suffix[suf].append(ident)
    if not any(missing_by_suffix.values()):
        check(PASS, "gl-completeness", f"{label}: all {len(ids)} blocks have all GL sections")
    else:
        for suf, bad in sorted(missing_by_suffix.items()):
            sample = sorted(bad)[:5]
            more = f"\n  ...and {len(bad)-5} more" if len(bad) > 5 else ""
            check(FAIL, "gl-completeness", f"{label}{suf}: {len(bad)} missing",
                  "\n".join(sample) + more)

# Only MoM-added IDs that actually exist in the game files
mom_advs  = exp_advance_ids & advance_ids
mom_units = exp_unit_ids    & unit_ids
mom_blds  = exp_building_ids & (improve_ids | buildings_txt_ids)
mom_wons  = {w for w in wonder_ids if w.startswith("WONDER_")}

audit_gl("Advances",  mom_advs)
audit_gl("Units",     mom_units)
audit_gl("Buildings", mom_blds)
audit_gl("Wonders",   mom_wons)

# ===========================================================================
# DIMENSION 6 — Cross-reference sanity
# ===========================================================================
print("\n=== Dimension 6: Cross-Reference Sanity ===")

def crossref_check(label, ref_key, source_path, valid_ids):
    refs = kv_map(source_path, ref_key)
    bad  = [r for r in refs if r not in valid_ids]
    if not bad:
        check(PASS, "cross-refs", f"{label}: all {len(refs)} {ref_key} refs resolve")
    else:
        uniq = sorted(set(bad))[:5]
        more = f"\n  ...and {len(set(bad))-5} more unique" if len(set(bad)) > 5 else ""
        check(FAIL, "cross-refs", f"{label}: {len(bad)} unresolved {ref_key} refs",
              "\n".join(uniq) + more)

crossref_check("Advance prerequisites", "Prerequisites",  GAMEDATA/"Advance.txt",   advance_ids)
crossref_check("Unit EnableAdvance",    "EnableAdvance",  GAMEDATA/"Units.txt",      advance_ids)
crossref_check("Unit ObsoleteAdvance",  "ObsoleteAdvance",GAMEDATA/"Units.txt",      advance_ids)
crossref_check("Building EnabledBy",    "ENABLING_ADVANCE",GAMEDATA/"Improve.txt",  advance_ids)
if (GAMEDATA / "buildings.txt").exists():
    crossref_check("Buildings.txt EnableAdvance", "EnableAdvance", GAMEDATA/"buildings.txt", advance_ids)

missing_slic_buildings = sorted(set(mom_slic_building_refs) - buildings_txt_ids)
if missing_slic_buildings:
    sample = missing_slic_buildings[:10]
    more = f"\n  ...and {len(missing_slic_buildings)-10} more" if len(missing_slic_buildings) > 10 else ""
    check(FAIL, "cross-refs",
          f"MoM SLIC building refs: {len(missing_slic_buildings)} missing from buildings.txt",
          "\n".join(sample) + more)
else:
    check(PASS, "cross-refs",
          f"MoM SLIC building refs: all {len(mom_slic_building_refs)} symbols resolve in buildings.txt")

required_governments = []
for ident, block_text in base_govern_blocks.items():
    if ident == "GOVERNMENT_ANARCHY":
        required_governments.append(ident)
        continue
    enable_advance = block_field_value(block_text, "EnableAdvance")
    if enable_advance and enable_advance in advance_ids:
        required_governments.append(ident)

missing_required_governments = [
    ident for ident in required_governments
    if ident not in govern_blocks
]
if missing_required_governments:
    sample = missing_required_governments[:10]
    more = f"\n  ...and {len(missing_required_governments)-10} more" if len(missing_required_governments) > 10 else ""
    check(FAIL, "cross-refs",
          f"govern.txt: {len(missing_required_governments)} government block(s) missing despite live enabling advances",
          "\n".join(sample) + more)
else:
    check(PASS, "cross-refs",
          f"govern.txt: all {len(required_governments)} governments enabled by live advances are present")

governicon_ids = block_ids(GAMEDATA / "governicon.txt")
required_govern_icons = {
    block_field_value(govern_blocks[ident], "Icon")
    for ident in required_governments
    if ident in govern_blocks and block_field_value(govern_blocks[ident], "Icon")
}
missing_govern_icons = sorted(icon_id for icon_id in required_govern_icons if icon_id not in governicon_ids)
if missing_govern_icons:
    sample = missing_govern_icons[:10]
    more = f"\n  ...and {len(missing_govern_icons)-10} more" if len(missing_govern_icons) > 10 else ""
    check(FAIL, "cross-refs",
          f"governicon.txt: {len(missing_govern_icons)} live government icon entry(ies) missing",
          "\n".join(sample) + more)
else:
    check(PASS, "cross-refs",
          f"governicon.txt: all {len(required_govern_icons)} live government icon entries are present")

missing_government_uniticons = sorted(
    icon_id for icon_id in required_govern_icons
    if icon_id != "ICON_GOV_DEFAULT" and icon_id not in icon_ids
)
if missing_government_uniticons:
    sample = missing_government_uniticons[:10]
    more = f"\n  ...and {len(missing_government_uniticons)-10} more" if len(missing_government_uniticons) > 10 else ""
    check(FAIL, "cross-refs",
          f"uniticon.txt: {len(missing_government_uniticons)} live government uniticon block(s) missing",
          "\n".join(sample) + more)
else:
    check(PASS, "cross-refs",
          f"uniticon.txt: all {len(required_govern_icons) - (1 if 'ICON_GOV_DEFAULT' in required_govern_icons else 0)} live government uniticon blocks are present")

research_governments = [
    ident for ident in required_governments
    if ident != "GOVERNMENT_ANARCHY"
    and float(block_field_value(govern_blocks.get(ident, ""), "MaxScienceRate") or 0) > 0
]
if research_governments:
    check(PASS, "cross-refs",
          f"govern.txt: {len(research_governments)} non-Anarchy governments retain positive MaxScienceRate")
else:
    check(FAIL, "cross-refs",
          "govern.txt: at least one non-Anarchy government retains positive MaxScienceRate",
          "The scenario would be stuck in zero-science government space.")

diffdb_path = GAMEDATA / "DiffDB.txt"
if not diffdb_path.exists():
    check(FAIL, "cross-refs", "DiffDB.txt: scenario override exists", f"File not found: {diffdb_path}")
else:
    diffdb_blocks = diffdb_advance_chances(diffdb_path)
    if not diffdb_blocks:
        check(FAIL, "cross-refs", "DiffDB.txt: ADVANCE_CHANCES blocks parsed", "No ADVANCE_CHANCES blocks found")
    else:
        government_start_advances = {
            block_field_value(block_text, "EnableAdvance")
            for ident, block_text in govern_blocks.items()
            if ident != "GOVERNMENT_ANARCHY" and block_field_value(block_text, "EnableAdvance")
        }
        missing_start_governments = []
        for index, entries in enumerate(diffdb_blocks, start=1):
            guaranteed_human = {
                advance_id for advance_id, human_chance, _ai_chance in entries
                if human_chance >= 100
            }
            guaranteed_ai = {
                advance_id for advance_id, _human_chance, ai_chance in entries
                if ai_chance >= 100
            }
            if not (guaranteed_human & government_start_advances):
                missing_start_governments.append(f"difficulty #{index}: no guaranteed human government-start advance")
            if not (guaranteed_ai & government_start_advances):
                missing_start_governments.append(f"difficulty #{index}: no guaranteed AI government-start advance")
        if missing_start_governments:
            check(FAIL, "cross-refs",
                  "DiffDB.txt: each difficulty guarantees a live government-start advance",
                  "\n".join(missing_start_governments))
        else:
            check(PASS, "cross-refs",
                  f"DiffDB.txt: all {len(diffdb_blocks)} difficulty blocks guarantee a live government-start advance for human and AI")

visible_uniticon_ids = set()
for ident, block_text in unit_blocks.items():
    if block_has_hidden_flag(block_text):
        continue
    icon_id = block_field_value(block_text, "DefaultIcon")
    if icon_id:
        visible_uniticon_ids.add(icon_id)
for ident, block_text in improve_blocks.items():
    if block_has_hidden_flag(block_text):
        continue
    icon_id = block_field_value(block_text, "IMPROVE_DEFAULT_ICON")
    if icon_id:
        visible_uniticon_ids.add(icon_id)
for ident, block_text in buildings_txt_blocks.items():
    if block_has_hidden_flag(block_text):
        continue
    icon_id = block_field_value(block_text, "DefaultIcon")
    if icon_id:
        visible_uniticon_ids.add(icon_id)
for ident, block_text in wonder_blocks.items():
    if block_has_hidden_flag(block_text):
        continue
    icon_id = block_field_value(block_text, "DefaultIcon")
    if icon_id:
        visible_uniticon_ids.add(icon_id)
for ident, block_text in tileimp_blocks.items():
    if block_has_hidden_flag(block_text):
        continue
    icon_id = block_field_value(block_text, "Icon")
    if icon_id:
        visible_uniticon_ids.add(icon_id)

unresolved_uniticon_text_refs = []
for icon_id in sorted(visible_uniticon_ids):
    line = UNITICON_LINES.get(icon_id, "")
    if not line:
        continue
    for field, ref in uniticon_text_refs(line):
        if ref not in gl_all and ref not in gl_str_ids:
            unresolved_uniticon_text_refs.append(f"{icon_id}.{field} -> {ref}")
if unresolved_uniticon_text_refs:
    sample = unresolved_uniticon_text_refs[:10]
    more = f"\n  ...and {len(unresolved_uniticon_text_refs)-10} more" if len(unresolved_uniticon_text_refs) > 10 else ""
    check(FAIL, "cross-refs", f"uniticon.txt: {len(unresolved_uniticon_text_refs)} unresolved text ref(s)",
          "\n".join(sample) + more)
else:
    check(PASS, "cross-refs", "uniticon.txt: all symbolic text refs resolve to GL sections or strings")

unit_build_lists_path = AIDATA / "UnitBuildLists.txt"
advance_lists_path = AIDATA / "AdvanceLists.txt"
strategy_path = AIDATA / "strategies.txt"
if not unit_build_lists_path.exists():
    check(FAIL, "cross-refs", "UnitBuildLists.txt: scenario override exists",
          f"File not found: {unit_build_lists_path}")
else:
    active_unit_build_text = "\n".join(
        line.split("//", 1)[0]
        for line in unit_build_lists_path.read_text(encoding='utf-8', errors='replace').splitlines()
    )
    unit_build_refs = re.findall(r'\bUnit\s+(UNIT_[A-Z0-9_]+)\b', active_unit_build_text)
    unresolved_unit_build_refs = sorted(set(ref for ref in unit_build_refs if ref not in unit_ids))
    hidden_unit_ids = {
        ident for ident, block_text in unit_blocks.items()
        if re.search(r'^\s*(NoIndex|GLHidden)\s*$', block_text, re.MULTILINE)
    }
    hidden_unit_build_refs = sorted(set(ref for ref in unit_build_refs if ref in hidden_unit_ids))
    if unresolved_unit_build_refs:
        sample = unresolved_unit_build_refs[:10]
        more = f"\n  ...and {len(unresolved_unit_build_refs)-10} more" if len(unresolved_unit_build_refs) > 10 else ""
        check(FAIL, "cross-refs", f"UnitBuildLists.txt: {len(unresolved_unit_build_refs)} unresolved unit ref(s)",
              "\n".join(sample) + more)
    elif hidden_unit_build_refs:
        sample = hidden_unit_build_refs[:10]
        more = f"\n  ...and {len(hidden_unit_build_refs)-10} more" if len(hidden_unit_build_refs) > 10 else ""
        check(FAIL, "cross-refs", f"UnitBuildLists.txt: {len(hidden_unit_build_refs)} hidden/base unit ref(s)",
              "\n".join(sample) + more)
    else:
        check(PASS, "cross-refs", f"UnitBuildLists.txt: all {len(unit_build_refs)} AI unit refs are visible MoM units")

    strategy_unit_lists = set(re.findall(
        r'\b\w+UnitList\s+(UNIT_BUILD_LIST_[A-Z0-9_]+)',
        strategy_path.read_text(encoding='utf-8', errors='replace') if strategy_path.exists() else "",
    ))
    unit_build_list_ids = block_ids(unit_build_lists_path)
    missing_strategy_lists = sorted(strategy_unit_lists - unit_build_list_ids)
    if missing_strategy_lists:
        sample = missing_strategy_lists[:10]
        more = f"\n  ...and {len(missing_strategy_lists)-10} more" if len(missing_strategy_lists) > 10 else ""
        check(FAIL, "cross-refs", f"strategies.txt: {len(missing_strategy_lists)} missing UNIT_BUILD_LIST refs",
              "\n".join(sample) + more)
    else:
        check(PASS, "cross-refs", f"strategies.txt: all {len(strategy_unit_lists)} UNIT_BUILD_LIST refs are scenario-owned")

advance_blocks = block_texts(GAMEDATA / "Advance.txt", "ADVANCE_")
advance_ids = set(advance_blocks)
hidden_advance_ids = {
    ident for ident, block_text in advance_blocks.items()
    if re.search(r'^\s*(NoIndex|GLHidden)\s*$', block_text, re.MULTILINE)
}
goody_excluded_advance_ids = {
    ident for ident, block_text in advance_blocks.items()
    if re.search(r'^\s*GoodyHutExcluded\s*$', block_text, re.MULTILINE)
}
goody_hut_visible_base_advances = sorted(hidden_advance_ids - goody_excluded_advance_ids)
if goody_hut_visible_base_advances:
    sample = goody_hut_visible_base_advances[:10]
    more = f"\n  ...and {len(goody_hut_visible_base_advances)-10} more" if len(goody_hut_visible_base_advances) > 10 else ""
    check(FAIL, "cross-refs", f"Advance.txt: {len(goody_hut_visible_base_advances)} hidden/base advance(s) still eligible for goody huts",
          "\n".join(sample) + more)
else:
    check(PASS, "cross-refs", f"Advance.txt: all {len(hidden_advance_ids)} hidden/base advance(s) are excluded from goody huts")
if not advance_lists_path.exists():
    check(FAIL, "cross-refs", "AdvanceLists.txt: scenario override exists",
          f"File not found: {advance_lists_path}")
else:
    active_advance_list_text = "\n".join(
        line.split("//", 1)[0]
        for line in advance_lists_path.read_text(encoding='utf-8', errors='replace').splitlines()
    )
    advance_list_refs = re.findall(r'\bAdvance\s+(ADVANCE_[A-Z0-9_]+)\b', active_advance_list_text)
    unresolved_advance_list_refs = sorted(set(ref for ref in advance_list_refs if ref not in advance_ids))
    hidden_advance_list_refs = sorted(set(ref for ref in advance_list_refs if ref in hidden_advance_ids))
    if unresolved_advance_list_refs:
        sample = unresolved_advance_list_refs[:10]
        more = f"\n  ...and {len(unresolved_advance_list_refs)-10} more" if len(unresolved_advance_list_refs) > 10 else ""
        check(FAIL, "cross-refs", f"AdvanceLists.txt: {len(unresolved_advance_list_refs)} unresolved advance ref(s)",
              "\n".join(sample) + more)
    elif hidden_advance_list_refs:
        sample = hidden_advance_list_refs[:10]
        more = f"\n  ...and {len(hidden_advance_list_refs)-10} more" if len(hidden_advance_list_refs) > 10 else ""
        check(FAIL, "cross-refs", f"AdvanceLists.txt: {len(hidden_advance_list_refs)} hidden/base advance ref(s)",
              "\n".join(sample) + more)
    else:
        check(PASS, "cross-refs", f"AdvanceLists.txt: all {len(advance_list_refs)} AI advance refs are visible MoM advances")

    strategy_advance_lists = set(re.findall(
        r'\b(?:Research|StopResearch)\s+(ADVANCE_LIST_[A-Z0-9_]+)',
        strategy_path.read_text(encoding='utf-8', errors='replace') if strategy_path.exists() else "",
    ))
    advance_list_ids = block_ids(advance_lists_path)
    missing_strategy_advance_lists = sorted(strategy_advance_lists - advance_list_ids)
    if missing_strategy_advance_lists:
        sample = missing_strategy_advance_lists[:10]
        more = f"\n  ...and {len(missing_strategy_advance_lists)-10} more" if len(missing_strategy_advance_lists) > 10 else ""
        check(FAIL, "cross-refs", f"strategies.txt: {len(missing_strategy_advance_lists)} missing ADVANCE_LIST refs",
              "\n".join(sample) + more)
    else:
        check(PASS, "cross-refs", f"strategies.txt: all {len(strategy_advance_lists)} ADVANCE_LIST refs are scenario-owned")

# ===========================================================================
# DIMENSION 7 — GL text quality
# ===========================================================================
print("\n=== Dimension 7: GL Text Quality ===")

stats_lines    = gl_stats_lines(ENGDATA / "Great_Library.txt")
raw_age_hits   = [(sec, ln) for sec, ln in stats_lines if re.match(r'Age:\s*AGE_[0-9]', ln)]
semicolon_hits = [(sec, ln) for sec, ln in stats_lines if re.match(r'Branch:.*;', ln)]

if raw_age_hits:
    sample = [f"  {s}: {l}" for s, l in raw_age_hits[:5]]
    check(FAIL, "gl-quality", f"{len(raw_age_hits)} STATISTICS sections with raw age ID (AGE_0 etc.)",
          "\n".join(sample))
else:
    check(PASS, "gl-quality", "No raw AGE_0/1/2 in STATISTICS sections")

if semicolon_hits:
    sample = [f"  {s}: {l}" for s, l in semicolon_hits[:5]]
    check(FAIL, "gl-quality", f"{len(semicolon_hits)} STATISTICS sections with ; in Branch line",
          "\n".join(sample))
else:
    check(PASS, "gl-quality", "No semicolon comment bleed in Branch lines")

missing_advance_strings = sorted(a for a in advance_ids if a not in gl_str_ids)
if missing_advance_strings:
    sample = missing_advance_strings[:10]
    more = f"\n  ...and {len(missing_advance_strings)-10} more" if len(missing_advance_strings) > 10 else ""
    check(FAIL, "gl-quality", f"{len(missing_advance_strings)} advances missing gl_str display names",
          "\n".join(sample) + more)
else:
    check(PASS, "gl-quality", "All advances have gl_str display names")

# ===========================================================================
# 4-Part Asset Pipeline Sanity Check (Prevent Whack-a-Mole)
# ===========================================================================
units_path = SCENARIO / "default" / "gamedata" / "Units.txt"
newsprite_path = SCENARIO / "default" / "gamedata" / "newsprite.txt"

if units_path.exists() and newsprite_path.exists():
    units_text = units_path.read_text(encoding='utf-8', errors='replace')
    newsprite_text = newsprite_path.read_text(encoding='utf-8', errors='replace')
    
    # Extract all DefaultSprite values from Units.txt
    default_sprites = set(re.findall(r'DefaultSprite\s+([A-Z0-9_]+)', units_text))
    
    # Extract all defined sprite names from newsprite.txt (must be NAME <integer>)
    defined_sprites = set(re.findall(r'^([A-Z0-9_]+)\s+\d+\s*$', newsprite_text, re.MULTILINE))
    
    # Check for missing definitions
    missing_sprites = default_sprites - defined_sprites
    if missing_sprites:
        check(FAIL, "asset-pipeline", f"Missing newsprite.txt definitions for: {', '.join(sorted(missing_sprites))}")
    else:
        check(PASS, "asset-pipeline", "All DefaultSprite values have matching newsprite.txt definitions")
    
    # Check for spaces in sprite names (causes "expected integer" parser crash)
    bad_sprites = re.findall(r'DefaultSprite[ \t]+([A-Z0-9_]+[ \t]+[A-Z0-9_]+)', units_text)
    if bad_sprites:
        check(FAIL, "asset-pipeline", f"DefaultSprite names contain spaces (will crash parser): {', '.join(bad_sprites)}")
    else:
        check(PASS, "asset-pipeline", "No DefaultSprite names contain spaces")
else:
    check(WARN, "asset-pipeline", "Units.txt or newsprite.txt not found for cross-reference check")

# ===========================================================================
# SPR file validation — existence and correct FRPS magic/version
# ===========================================================================
print("\n=== SPR file validation ===")

_newsprite_path = GAMEDATA / "newsprite.txt"
if _newsprite_path.exists():
    _mom_sprs: list[tuple[str, int]] = []
    for _line in _newsprite_path.read_text(encoding="latin-1").splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#"):
            continue
        _parts = _line.split()
        if len(_parts) == 2 and _parts[1].isdigit():
            _num = int(_parts[1])
            if _num >= MOM_SPRITE_MIN:
                _mom_sprs.append((_parts[0], _num))

    _missing: list[str] = []
    _bad_magic: list[str] = []
    for _name, _num in _mom_sprs:
        _spr = SPRITES_DIR / f"GU{_num:02d}.SPR"
        if not _spr.exists():
            _missing.append(f"{_name} -> GU{_num:02d}.SPR")
        else:
            _hdr = _spr.read_bytes()[:8]
            if _hdr != SPR_MAGIC:
                _got = " ".join(f"{b:02X}" for b in _hdr)
                _bad_magic.append(f"{_name} GU{_num:02d}.SPR: {_got}")

    if _missing:
        check(FAIL, "spr-files", f"{len(_missing)} MoM SPR file(s) missing",
              "\n".join(_missing))
    else:
        check(PASS, "spr-files", f"All {len(_mom_sprs)} MoM SPR files present")

    if _bad_magic:
        _exp = " ".join(f"{b:02X}" for b in SPR_MAGIC)
        check(FAIL, "spr-files",
              f"{len(_bad_magic)} SPR file(s) have wrong magic/version (expected {_exp})",
              "\n".join(_bad_magic))
    elif _mom_sprs:
        check(PASS, "spr-files", f"All {len(_mom_sprs)} MoM SPR files have correct FRPS v1.3 header")
else:
    check(WARN, "spr-files", "newsprite.txt not found — skipping SPR validation")

# ===========================================================================
# Summary
# ===========================================================================
print("\n" + "="*60)
print("SUMMARY")
print("="*60)

counts = defaultdict(int)
for status, dim, name, detail in results:
    counts[status.strip()] += 1

print(f"  PASS: {counts['PASS']}")
print(f"  FAIL: {counts['FAIL']}")
print(f"  WARN: {counts['WARN']}")
print(f"  INFO: {counts['INFO']}")
print()

if counts['FAIL'] == 0 and counts['WARN'] == 0:
    print("ALL CHECKS PASSED — scenario is ready to test.")
elif counts['FAIL'] == 0:
    print(f"No hard failures. {counts['WARN']} warning(s) to review.")
else:
    print(f"{counts['FAIL']} FAILURE(S) — fix before testing:")
    for status, dim, name, detail in results:
        if status == FAIL:
            print(f"  [{dim}] {name}")

sys.exit(1 if counts['FAIL'] > 0 else 0)
