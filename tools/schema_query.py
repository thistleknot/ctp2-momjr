"""
schema_query.py — CLI query interface for the schema registry.

Commands:
  entity-recipe <type>       Show what files/fields are needed to add an entity
  file-schema <filename>     Show the field schema for a specific file across mods
  cross-game <civ2_section>  Show the CIV2→CTP2 file mapping for a section
  what-changed <pair_id>     Summarize what changed in a specific mod pair
  added <pair_id> <type>     List added entities of a given type in a pair
  pairs                      List all mod pairs in the registry

Examples:
  python schema_query.py entity-recipe unit
  python schema_query.py entity-recipe improvement
  python schema_query.py file-schema buildings.txt
  python schema_query.py cross-game @IMPROVE
  python schema_query.py what-changed ctp2-ae-mom
  python schema_query.py added ctp2-ae-mom improvement
"""
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent / "data_csv" / "schema_registry.db"


def _db() -> sqlite3.Connection:
    if not DB_PATH.exists():
        print(f"Registry not found at {DB_PATH}")
        print("Run: python schema_registry.py")
        sys.exit(1)
    return sqlite3.connect(DB_PATH)


def _print_table(headers: list[str], rows: list[tuple], max_col_width: int = 50) -> None:
    if not rows:
        print("  (no results)")
        return
    widths = [len(h) for h in headers]
    str_rows = []
    for row in rows:
        sr = [str(c or "")[:max_col_width] for c in row]
        str_rows.append(sr)
        for i, v in enumerate(sr):
            widths[i] = max(widths[i], len(v))
    fmt = "  " + "  ".join(f"{{:<{w}}}" for w in widths)
    sep = "  " + "  ".join("-" * w for w in widths)
    print(fmt.format(*headers))
    print(sep)
    for sr in str_rows:
        print(fmt.format(*sr))


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_pairs(db: sqlite3.Connection, _args: list[str]) -> None:
    """List all mod pairs and their coverage."""
    rows = db.execute("""
        SELECT mp.id, mp.parser,
               COUNT(DISTINCT fd.file_rel) files,
               COUNT(DISTINCT CASE WHEN bd.change_type='added' THEN bd.block_id END) added,
               mp.notes
        FROM mod_pairs mp
        LEFT JOIN file_diffs fd ON fd.pair_id = mp.id
        LEFT JOIN block_diffs bd ON bd.pair_id = mp.id
        GROUP BY mp.id
        ORDER BY mp.id
    """).fetchall()
    _print_table(["Pair ID", "Parser", "Files", "Blocks Added", "Notes"], rows)


def cmd_entity_recipe(db: sqlite3.Connection, args: list[str]) -> None:
    """Show what files and fields are required to add a given entity type."""
    if not args:
        print("Usage: entity-recipe <type>  (e.g., unit, improvement, advance, wonder)")
        return
    etype = args[0].lower()
    rows = db.execute("""
        SELECT file_rel, field_key, field_type,
               pair_count || '/' || total_pairs AS coverage,
               CASE WHEN required=1 THEN 'YES' ELSE '' END required,
               sample_val
        FROM entity_recipes
        WHERE entity_type = ?
        ORDER BY required DESC, pair_count DESC, file_rel, field_key
    """, (etype,)).fetchall()
    if not rows:
        print(f"No recipe found for entity type '{etype}'.")
        etypes = [r[0] for r in db.execute("SELECT DISTINCT entity_type FROM entity_recipes").fetchall()]
        print("Available types:", etypes)
        return
    print(f"\nEntity recipe: {etype}")
    print("Fields that appear when adding a new entity of this type:\n")
    _print_table(["File", "Field", "Type", "Coverage", "Required", "Sample"], rows)

    # Also show cross-game map if this type is in there
    section_rows = db.execute("""
        SELECT civ2_section, GROUP_CONCAT(ctp2_file, ', '), notes
        FROM cross_game_map WHERE entity_type = ?
        GROUP BY civ2_section
    """, (etype,)).fetchall()
    if section_rows:
        print(f"\nCross-game mapping for '{etype}':")
        _print_table(["CIV2 Section", "CTP2 Files", "Notes"], section_rows)


def cmd_file_schema(db: sqlite3.Connection, args: list[str]) -> None:
    """Show field schema for a specific file across all mod pairs."""
    if not args:
        print("Usage: file-schema <filename>  (e.g., buildings.txt, Units.txt)")
        return
    fname = args[0]
    # Match by filename only (ignore path prefix)
    rows = db.execute("""
        SELECT bd.entity_type, fd.field_key, fd.field_type,
               COUNT(DISTINCT fd.pair_id) pairs,
               MIN(fd.new_val) sample
        FROM field_diffs fd
        JOIN block_diffs bd
          ON fd.pair_id = bd.pair_id
         AND fd.file_rel = bd.file_rel
         AND fd.block_id = bd.block_id
        WHERE fd.file_rel LIKE ? AND bd.change_type = 'added'
        GROUP BY bd.entity_type, fd.field_key, fd.field_type
        ORDER BY pairs DESC, bd.entity_type, fd.field_key
    """, (f"%{fname}%",)).fetchall()
    if not rows:
        # Fuzzy search
        avail = [r[0] for r in db.execute(
            "SELECT DISTINCT file_rel FROM file_diffs ORDER BY file_rel"
        ).fetchall()]
        matches = [f for f in avail if fname.lower() in f.lower()]
        if matches:
            print(f"No exact match for '{fname}'. Similar files: {matches[:5]}")
        else:
            print(f"No data found for file '{fname}'.")
        return
    print(f"\nField schema from added blocks in files matching '{fname}':\n")
    _print_table(["Entity Type", "Field", "Type", "Pairs", "Sample"], rows)


def cmd_cross_game(db: sqlite3.Connection, args: list[str]) -> None:
    """Show the CIV2→CTP2 file mapping for a section or entity type."""
    if not args:
        print("Usage: cross-game <@SECTION or entity_type>")
        return
    query = args[0].upper()
    rows = db.execute("""
        SELECT civ2_section, entity_type, ctp2_file, notes
        FROM cross_game_map
        WHERE UPPER(civ2_section) LIKE ? OR UPPER(entity_type) LIKE ?
        ORDER BY civ2_section, ctp2_file
    """, (f"%{query}%", f"%{query}%")).fetchall()
    if not rows:
        print(f"No cross-game map entries for '{query}'.")
        all_sections = [r[0] for r in db.execute("SELECT DISTINCT civ2_section FROM cross_game_map").fetchall()]
        print("Available CIV2 sections:", all_sections)
        return
    print(f"\nCross-game mapping for '{query}':\n")
    _print_table(["CIV2 Section", "Entity Type", "CTP2 File", "Notes"], rows)


def cmd_what_changed(db: sqlite3.Connection, args: list[str]) -> None:
    """Summarize what changed in a specific mod pair."""
    if not args:
        print("Usage: what-changed <pair_id>")
        return
    pair_id = args[0]
    # Files
    file_rows = db.execute("""
        SELECT fd.file_rel, fd.status,
               COUNT(DISTINCT CASE WHEN bd.change_type='added'    THEN bd.block_id END),
               COUNT(DISTINCT CASE WHEN bd.change_type='removed'  THEN bd.block_id END),
               COUNT(DISTINCT CASE WHEN bd.change_type='modified' THEN bd.block_id END)
        FROM file_diffs fd
        LEFT JOIN block_diffs bd ON bd.pair_id = fd.pair_id AND bd.file_rel = fd.file_rel
        WHERE fd.pair_id = ? AND fd.status != 'unchanged'
        GROUP BY fd.file_rel, fd.status
        ORDER BY (COUNT(DISTINCT bd.block_id)) DESC
    """, (pair_id,)).fetchall()
    if not file_rows:
        print(f"No data for pair '{pair_id}'. Run diff_engine.py first.")
        return
    print(f"\nChanges in '{pair_id}':\n")
    _print_table(["File", "Status", "Added", "Removed", "Modified"], file_rows)

    # Entity type breakdown
    etype_rows = db.execute("""
        SELECT entity_type,
               COUNT(DISTINCT CASE WHEN change_type='added'   THEN block_id END) added,
               COUNT(DISTINCT CASE WHEN change_type='removed' THEN block_id END) removed
        FROM block_diffs WHERE pair_id = ?
        GROUP BY entity_type ORDER BY added DESC
    """, (pair_id,)).fetchall()
    if etype_rows:
        print(f"\nEntity type breakdown:\n")
        _print_table(["Entity Type", "Added", "Removed"], etype_rows)


def cmd_added(db: sqlite3.Connection, args: list[str]) -> None:
    """List entity blocks added in a specific pair and type."""
    if len(args) < 2:
        print("Usage: added <pair_id> <entity_type>")
        return
    pair_id, etype = args[0], args[1].lower()
    rows = db.execute("""
        SELECT block_id, file_rel FROM block_diffs
        WHERE pair_id = ? AND entity_type = ? AND change_type = 'added'
        ORDER BY file_rel, block_id
    """, (pair_id, etype)).fetchall()
    if not rows:
        print(f"No added '{etype}' blocks in pair '{pair_id}'.")
        etypes = [r[0] for r in db.execute(
            "SELECT DISTINCT entity_type FROM block_diffs WHERE pair_id=? AND change_type='added'",
            (pair_id,)
        ).fetchall()]
        print("Available entity types in this pair:", etypes)
        return
    print(f"\nAdded '{etype}' blocks in '{pair_id}' ({len(rows)} entries):\n")
    _print_table(["Block ID", "File"], rows)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------
COMMANDS = {
    "pairs":          cmd_pairs,
    "entity-recipe":  cmd_entity_recipe,
    "file-schema":    cmd_file_schema,
    "cross-game":     cmd_cross_game,
    "what-changed":   cmd_what_changed,
    "added":          cmd_added,
}


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] in ("--help", "-h", "help"):
        print(__doc__)
        return

    cmd = args[0]
    rest = args[1:]
    if cmd not in COMMANDS:
        print(f"Unknown command: {cmd}")
        print("Commands:", list(COMMANDS))
        sys.exit(1)

    db = _db()
    COMMANDS[cmd](db, rest)
    db.close()


if __name__ == "__main__":
    main()
