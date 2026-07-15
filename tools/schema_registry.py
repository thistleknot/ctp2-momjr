"""
schema_registry.py — Builds a SQLite schema registry from diff_engine.py output.

Reads all diff JSON files from diff_results/ and populates schema_registry.db with:
  - mod_pairs, file_diffs, block_diffs, field_diffs
  - entity_recipes: per entity-type (unit/improvement/wonder/advance), which files
    and fields are needed when adding a new entity, derived from added blocks

Also emits schema_discovery.md — a human-readable schema reference.

Usage:
  python schema_registry.py              # rebuild registry from all diffs
  python schema_registry.py --markdown   # regenerate schema_discovery.md only
"""
import json
import re
import sqlite3
import sys
from pathlib import Path
from collections import defaultdict

TOOLS       = Path(__file__).parent
DIFF_OUT    = TOOLS / "diff_results"
DB_PATH     = TOOLS / "data_csv" / "schema_registry.db"
MD_PATH     = TOOLS / "data_csv" / "schema_discovery.md"
MOD_PAIRS   = TOOLS / "mod_pairs.json"

# Block-ID prefix → entity type
_PREFIX_TO_ENTITY = {
    "UNIT_":      "unit",
    "IMPROVE_":   "improvement",
    "WONDER_":    "wonder",
    "ADVANCE_":   "advance",
    "TERRAIN_":   "terrain",
    "GOVERN_":    "government",
    "GOODS_":     "goods",
    "ICON_UNIT_": "unit_icon",
    "ICON_IMPROVE_": "improvement_icon",
    "ICON_WONDER_":  "wonder_icon",
    "ICON_ADVANCE_": "advance_icon",
}

# CIV2 section name → entity type
_CIV2_SECTION_ENTITY = {
    "@UNITS":       "unit",
    "@IMPROVE":     "improvement",
    "@ADVANCE":     "advance",
    "@TERRAIN":     "terrain",
    "@GOVERNMENTS": "government",
    "@LEADERS":     "leader",
}


def _entity_type_for_block(block_id: str) -> str:
    for prefix, etype in _PREFIX_TO_ENTITY.items():
        if block_id.startswith(prefix):
            return etype
    return "other"


def _entity_type_for_civ2(section: str) -> str:
    return _CIV2_SECTION_ENTITY.get(section.upper(), "other")


# ---------------------------------------------------------------------------
# DB setup
# ---------------------------------------------------------------------------
DDL = """
CREATE TABLE IF NOT EXISTS mod_pairs (
    id TEXT PRIMARY KEY,
    parser TEXT,
    baseline TEXT,
    mod TEXT,
    notes TEXT
);
CREATE TABLE IF NOT EXISTS file_diffs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pair_id TEXT,
    file_rel TEXT,
    status TEXT,          -- modified | added_in_mod | removed_in_mod
    parser TEXT,
    summary_json TEXT,
    UNIQUE(pair_id, file_rel)
);
CREATE TABLE IF NOT EXISTS block_diffs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pair_id TEXT,
    file_rel TEXT,
    block_id TEXT,
    change_type TEXT,     -- added | removed | modified
    entity_type TEXT
);
CREATE TABLE IF NOT EXISTS field_diffs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pair_id TEXT,
    file_rel TEXT,
    block_id TEXT,
    field_type TEXT,
    field_key TEXT,
    old_val TEXT,
    new_val TEXT,
    change_type TEXT      -- added | removed | changed
);
CREATE TABLE IF NOT EXISTS entity_recipes (
    entity_type TEXT,
    file_rel TEXT,
    field_key TEXT,
    field_type TEXT,
    pair_count INTEGER,   -- how many pairs have this field in added blocks
    total_pairs INTEGER,
    required INTEGER,     -- 1 if pair_count / total_pairs >= 0.5
    sample_val TEXT,
    PRIMARY KEY (entity_type, file_rel, field_key, field_type)
);
CREATE TABLE IF NOT EXISTS cross_game_map (
    civ2_section TEXT,
    ctp2_file TEXT,
    entity_type TEXT,
    notes TEXT
);
"""


def open_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.executescript(DDL)
    db.commit()
    return db


# ---------------------------------------------------------------------------
# Load diffs into DB
# ---------------------------------------------------------------------------

def load_pair_diffs(db: sqlite3.Connection, pair_id: str, parser: str) -> int:
    """Load all diff JSON files for one pair into the DB. Returns file count."""
    pair_dir = DIFF_OUT / pair_id
    if not pair_dir.exists():
        print(f"  SKIP {pair_id}: no diff_results directory")
        return 0

    db.execute("DELETE FROM file_diffs   WHERE pair_id=?", (pair_id,))
    db.execute("DELETE FROM block_diffs  WHERE pair_id=?", (pair_id,))
    db.execute("DELETE FROM field_diffs  WHERE pair_id=?", (pair_id,))

    count = 0
    for json_file in pair_dir.glob("*.json"):
        if json_file.name.startswith("_"):
            continue  # skip _summary.json
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        file_rel = data.get("rel", json_file.stem)
        status   = data.get("status", "modified")
        file_parser = data.get("parser", parser)
        summary_json = json.dumps(data.get("summary", {}))

        db.execute(
            "INSERT OR REPLACE INTO file_diffs (pair_id, file_rel, status, parser, summary_json) VALUES (?,?,?,?,?)",
            (pair_id, file_rel, status, file_parser, summary_json),
        )
        count += 1

        # Ingest CTP2 block diffs
        if file_parser == "ctp2":
            added_data = data.get("blocks_added_data", {})
            for bid in data.get("blocks_added", []):
                db.execute(
                    "INSERT INTO block_diffs (pair_id, file_rel, block_id, change_type, entity_type) VALUES (?,?,?,?,?)",
                    (pair_id, file_rel, bid, "added", _entity_type_for_block(bid)),
                )
                for ftype, fkey, fval in added_data.get(bid, []):
                    db.execute(
                        "INSERT INTO field_diffs (pair_id, file_rel, block_id, field_type, field_key, old_val, new_val, change_type) VALUES (?,?,?,?,?,?,?,?)",
                        (pair_id, file_rel, bid, ftype, fkey, "", fval, "added"),
                    )
            for bid in data.get("blocks_removed", []):
                db.execute(
                    "INSERT INTO block_diffs (pair_id, file_rel, block_id, change_type, entity_type) VALUES (?,?,?,?,?)",
                    (pair_id, file_rel, bid, "removed", _entity_type_for_block(bid)),
                )
            for mod in data.get("blocks_modified", []):
                bid = mod["block_id"]
                db.execute(
                    "INSERT INTO block_diffs (pair_id, file_rel, block_id, change_type, entity_type) VALUES (?,?,?,?,?)",
                    (pair_id, file_rel, bid, "modified", _entity_type_for_block(bid)),
                )
                for ftype, fkey, fval in mod.get("fields_added", []):
                    db.execute(
                        "INSERT INTO field_diffs (pair_id, file_rel, block_id, field_type, field_key, old_val, new_val, change_type) VALUES (?,?,?,?,?,?,?,?)",
                        (pair_id, file_rel, bid, ftype, fkey, "", fval, "added"),
                    )
                for ftype, fkey, fval in mod.get("fields_removed", []):
                    db.execute(
                        "INSERT INTO field_diffs (pair_id, file_rel, block_id, field_type, field_key, old_val, new_val, change_type) VALUES (?,?,?,?,?,?,?,?)",
                        (pair_id, file_rel, bid, ftype, fkey, fval, "", "removed"),
                    )

        # Ingest CIV2 RULES.TXT section diffs
        elif file_parser == "civ2_rules":
            for sec in data.get("sections", []):
                section_name = sec["section"]
                etype = _entity_type_for_civ2(section_name)
                for entry_name in sec.get("added", []):
                    db.execute(
                        "INSERT INTO block_diffs (pair_id, file_rel, block_id, change_type, entity_type) VALUES (?,?,?,?,?)",
                        (pair_id, f"{file_rel}#{section_name}", entry_name, "added", etype),
                    )
                    # Record fields from added_data
                    added_data = sec.get("added_data", [])
                    idx = sec["added"].index(entry_name)
                    if idx < len(added_data):
                        for fkey, fval in added_data[idx].items():
                            db.execute(
                                "INSERT INTO field_diffs (pair_id, file_rel, block_id, field_type, field_key, old_val, new_val, change_type) VALUES (?,?,?,?,?,?,?,?)",
                                (pair_id, f"{file_rel}#{section_name}", entry_name, "kv", fkey, "", fval, "added"),
                            )
                for entry_name in sec.get("removed", []):
                    db.execute(
                        "INSERT INTO block_diffs (pair_id, file_rel, block_id, change_type, entity_type) VALUES (?,?,?,?,?)",
                        (pair_id, f"{file_rel}#{section_name}", entry_name, "removed", etype),
                    )

    db.commit()
    print(f"  [{pair_id}] loaded {count} file diffs")
    return count


# ---------------------------------------------------------------------------
# Derive entity recipes
# ---------------------------------------------------------------------------

def derive_entity_recipes(db: sqlite3.Connection) -> int:
    """
    For each entity_type + file_rel combination, find which fields appear
    in added blocks across pairs. Fields in >=50% of pairs are marked required.
    """
    db.execute("DELETE FROM entity_recipes")

    # Get all pairs that have any added blocks
    pairs = [r[0] for r in db.execute(
        "SELECT DISTINCT pair_id FROM block_diffs WHERE change_type='added'"
    ).fetchall()]
    total_pairs = len(pairs)
    if total_pairs == 0:
        print("  No added blocks found — run diff_engine.py first.")
        return 0

    # For each (entity_type, file_rel, field_key, field_type):
    # count how many pairs have at least one added block with that field
    rows = db.execute("""
        SELECT
            bd.entity_type,
            fd.file_rel,
            fd.field_key,
            fd.field_type,
            COUNT(DISTINCT fd.pair_id) AS pair_count,
            MIN(fd.new_val) AS sample_val
        FROM field_diffs fd
        JOIN block_diffs bd
          ON fd.pair_id = bd.pair_id
         AND fd.file_rel = bd.file_rel
         AND fd.block_id = bd.block_id
        WHERE bd.change_type = 'added'
          AND fd.change_type = 'added'
          AND fd.field_key != ''
        GROUP BY bd.entity_type, fd.file_rel, fd.field_key, fd.field_type
    """).fetchall()

    for etype, frel, fkey, ftype, pc, sample in rows:
        required = 1 if pc / total_pairs >= 0.5 else 0
        db.execute(
            "INSERT OR REPLACE INTO entity_recipes VALUES (?,?,?,?,?,?,?,?)",
            (etype, frel, fkey, ftype, pc, total_pairs, required, sample),
        )

    db.commit()
    count = db.execute("SELECT COUNT(*) FROM entity_recipes").fetchone()[0]
    print(f"  Derived {count} entity recipe rows across {total_pairs} pair(s)")
    return count


# ---------------------------------------------------------------------------
# Load cross-game map from config
# ---------------------------------------------------------------------------

def load_cross_game_map(db: sqlite3.Connection) -> int:
    config = json.loads(MOD_PAIRS.read_text(encoding="utf-8"))
    db.execute("DELETE FROM cross_game_map")
    count = 0
    for entry in config.get("cross_game_map", []):
        for ctp2_file in entry.get("ctp2_files", []):
            db.execute(
                "INSERT INTO cross_game_map VALUES (?,?,?,?)",
                (entry["civ2_section"], ctp2_file, entry.get("entity_type", ""), entry.get("notes", "")),
            )
            count += 1
    db.commit()
    print(f"  Loaded {count} cross-game map entries")
    return count


# ---------------------------------------------------------------------------
# Markdown generation
# ---------------------------------------------------------------------------

def _md_table(headers: list[str], rows: list[tuple]) -> str:
    sep = " | ".join("---" for _ in headers)
    hdr = " | ".join(headers)
    lines = [f"| {hdr} |", f"| {sep} |"]
    for row in rows:
        cells = " | ".join(str(c or "").replace("|", "\\|")[:60] for c in row)
        lines.append(f"| {cells} |")
    return "\n".join(lines)


def generate_markdown(db: sqlite3.Connection) -> str:
    lines = [
        "# Schema Discovery Registry",
        "",
        "> Auto-generated by `schema_registry.py`. Do not edit manually.",
        "",
    ]

    # 1. Mod pairs summary
    lines += ["## Mod Pairs", ""]
    pairs_rows = db.execute("""
        SELECT mp.id, mp.parser, mp.notes,
               COUNT(DISTINCT fd.file_rel) files_diffed,
               COUNT(DISTINCT CASE WHEN bd.change_type='added' THEN bd.block_id END) blocks_added
        FROM mod_pairs mp
        LEFT JOIN file_diffs fd ON fd.pair_id = mp.id
        LEFT JOIN block_diffs bd ON bd.pair_id = mp.id
        GROUP BY mp.id
    """).fetchall()
    lines.append(_md_table(
        ["Pair ID", "Parser", "Files Diffed", "Blocks Added", "Notes"],
        [(r[0], r[1], r[3], r[4], r[2]) for r in pairs_rows]
    ))
    lines.append("")

    # 2. Cross-game map
    lines += ["## Cross-Game Entity Map", ""]
    cgm_rows = db.execute("""
        SELECT civ2_section, entity_type, GROUP_CONCAT(ctp2_file, ', '), notes
        FROM cross_game_map GROUP BY civ2_section
        ORDER BY civ2_section
    """).fetchall()
    lines.append(_md_table(
        ["CIV2 Section", "Entity Type", "CTP2 Files", "Notes"],
        cgm_rows
    ))
    lines.append("")

    # 3. Entity recipes per type
    lines += ["## Entity Recipes", ""]
    etypes = [r[0] for r in db.execute(
        "SELECT DISTINCT entity_type FROM entity_recipes ORDER BY entity_type"
    ).fetchall()]

    for etype in etypes:
        lines += [f"### `{etype}`", ""]
        recipe_rows = db.execute("""
            SELECT file_rel, field_key, field_type, pair_count, total_pairs, required, sample_val
            FROM entity_recipes
            WHERE entity_type = ?
            ORDER BY required DESC, pair_count DESC, file_rel, field_key
        """, (etype,)).fetchall()
        lines.append(_md_table(
            ["File", "Field", "Type", "Pairs", "Total", "Required", "Sample"],
            recipe_rows
        ))
        lines.append("")

    # 4. Per-file change summary (top changed files)
    lines += ["## Most-Changed Files", ""]
    file_rows = db.execute("""
        SELECT fd.file_rel,
               COUNT(DISTINCT CASE WHEN bd.change_type='added'    THEN bd.block_id END) added,
               COUNT(DISTINCT CASE WHEN bd.change_type='removed'  THEN bd.block_id END) removed,
               COUNT(DISTINCT CASE WHEN bd.change_type='modified' THEN bd.block_id END) modified,
               COUNT(DISTINCT fd.pair_id) pairs
        FROM file_diffs fd
        LEFT JOIN block_diffs bd ON bd.pair_id = fd.pair_id AND bd.file_rel = fd.file_rel
        WHERE fd.status = 'modified'
        GROUP BY fd.file_rel
        ORDER BY (added + removed + modified) DESC
        LIMIT 40
    """).fetchall()
    lines.append(_md_table(
        ["File", "Added", "Removed", "Modified", "Pairs"],
        file_rows
    ))
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(markdown_only: bool = False) -> None:
    db = open_db()

    if not markdown_only:
        config = json.loads(MOD_PAIRS.read_text(encoding="utf-8"))

        # Load mod pair metadata
        db.execute("DELETE FROM mod_pairs")
        for p in config["mod_pairs"]:
            db.execute(
                "INSERT INTO mod_pairs VALUES (?,?,?,?,?)",
                (p["id"], p["parser"], p["baseline"], p["mod"], p.get("notes", "")),
            )
        db.commit()

        # Load diffs
        print("Loading diffs into registry...")
        for p in config["mod_pairs"]:
            load_pair_diffs(db, p["id"], p["parser"])

        # Load cross-game map
        print("Loading cross-game map...")
        load_cross_game_map(db)

        # Derive entity recipes
        print("Deriving entity recipes...")
        derive_entity_recipes(db)

    # Generate markdown
    print("Generating schema_discovery.md...")
    md = generate_markdown(db)
    MD_PATH.parent.mkdir(parents=True, exist_ok=True)
    MD_PATH.write_text(md, encoding="utf-8")
    print(f"  Wrote {MD_PATH}")

    db.close()
    print("Done.")


if __name__ == "__main__":
    markdown_only = "--markdown" in sys.argv
    main(markdown_only)
