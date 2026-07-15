"""
Strict schema check: derive truly-required fields from reference mods (>=N%
coverage), then audit every MoM-generated block against those requirements.

Premises:
  [observed] AE, Cradle, and Ages of Man round-trip EAVs are loaded in eav_data table.
  [observed] MoM Units.txt and Advance.txt are generated files we can parse.
  [inferred] Fields present in >=80% of reference unit blocks are required.
  [inferred] Fields missing from MoM blocks that are required → generator gap.
"""
import sqlite3, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ctp2_roundtrip import parse_file, KV, Flag, SubList, Nested

DB_PATH      = r'C:\Users\user\.copilot\session-state\5cf6a694-6240-47f7-a998-f6bd4314f973\session.db'
MOM_GAMEDATA = Path(__file__).parent.parent / 'scen0000' / 'default' / 'gamedata'

db = sqlite3.connect(DB_PATH)

# ------------------------------------------------------------------
# Helper: load a parsed file into eav_data under a given mod label
# ------------------------------------------------------------------
def load_parsed(blocks, mod_label, file_type):
    db.execute("DELETE FROM eav_data WHERE mod=? AND file_type=?",
               (mod_label, file_type))
    rows = []
    for block_id, items in blocks.items():
        for seq, item in enumerate(items):
            if isinstance(item, KV):
                rows.append((mod_label, file_type, block_id, seq, 'kv', item.key, item.val))
            elif isinstance(item, Flag):
                rows.append((mod_label, file_type, block_id, seq, 'flag', item.name, ''))
            elif isinstance(item, SubList):
                rows.append((mod_label, file_type, block_id, seq, 'sublist', item.key, item.val))
            elif isinstance(item, Nested):
                rows.append((mod_label, file_type, block_id, seq, 'nested', item.name, ''))
    db.executemany("INSERT INTO eav_data VALUES (?,?,?,?,?,?,?)", rows)
    db.commit()
    return len(rows)


# ------------------------------------------------------------------
# Load MoM generated files
# ------------------------------------------------------------------
for fname, ftype in [('Units.txt', 'units'), ('Advance.txt', 'advance')]:
    p = MOM_GAMEDATA / fname
    if p.exists():
        blocks = parse_file(p.read_text(encoding='utf-8', errors='replace'))
        n = load_parsed(blocks, 'mom', ftype)
        print(f"Loaded mom/{fname}: {len(blocks)} blocks, {n} fields")


# ------------------------------------------------------------------
# Strict required field check (>=THRESHOLD coverage in ref mods)
# ------------------------------------------------------------------
THRESHOLD = 0.85

def audit(file_type: str):
    # Total unique blocks in reference mods
    total = db.execute(
        "SELECT COUNT(DISTINCT block_id || '|' || mod) FROM eav_data "
        "WHERE file_type=? AND mod IN ('ae','cradle','aom')",
        (file_type,)
    ).fetchone()[0]

    # Required: present in >= THRESHOLD of all reference blocks
    required = db.execute(f"""
        SELECT key, field_type,
               CAST(COUNT(DISTINCT block_id || '|' || mod) AS REAL)/{total} pct
        FROM eav_data
        WHERE file_type=? AND mod IN ('ae','cradle','aom')
        GROUP BY key, field_type
        HAVING pct >= {THRESHOLD}
        ORDER BY pct DESC
    """, (file_type,)).fetchall()

    print(f"\n=== {file_type.upper()} required fields ({THRESHOLD*100:.0f}%+ coverage, "
          f"{total} ref blocks) ===")
    for k, ft, pct in required:
        print(f"  {k:<30} {ft:<8} {pct:.0%}")
    required_set = {(r[0], r[1]) for r in required}

    # Base blocks (don't audit — those were in the original file)
    base_blocks = {r[0] for r in db.execute(
        "SELECT DISTINCT block_id FROM eav_data WHERE mod='base' AND file_type=?",
        (file_type,)).fetchall()}

    # MoM-added blocks only
    mom_blocks = [r[0] for r in db.execute(
        "SELECT DISTINCT block_id FROM eav_data WHERE mod='mom' AND file_type=?",
        (file_type,)).fetchall()
        if r[0] not in base_blocks]

    print(f"\nAuditing {len(mom_blocks)} MoM-added {file_type} blocks...")

    failures = []
    for bid in mom_blocks:
        have = {(r[0], r[1]) for r in db.execute(
            "SELECT key, field_type FROM eav_data "
            "WHERE mod='mom' AND block_id=? AND file_type=?",
            (bid, file_type)).fetchall()}
        missing = required_set - have
        if missing:
            failures.append((bid, missing))

    if not failures:
        print(f"  All MoM {file_type} blocks have all required fields PASS")
    else:
        print(f"  Blocks with missing required fields: {len(failures)}/{len(mom_blocks)}")
        # Show unique set of missing fields across all failures
        all_missing = {}
        for bid, miss in failures:
            for k, ft in miss:
                all_missing.setdefault((k, ft), []).append(bid)
        print(f"\n  Missing field summary ({len(all_missing)} distinct fields):")
        for (k, ft), bids in sorted(all_missing.items(), key=lambda x: -len(x[1])):
            pct = len(bids) / len(mom_blocks)
            print(f"    {k:<30} {ft:<8} affects {len(bids):>3} blocks ({pct:.0%})")

        print(f"\n  Sample failures:")
        for bid, miss in failures[:5]:
            print(f"    {bid}")
            for k, ft in sorted(miss):
                # Show what reference mods put for this field in similar blocks
                sample = db.execute("""
                    SELECT val FROM eav_data
                    WHERE key=? AND field_type=? AND file_type=?
                      AND mod IN ('ae','cradle','aom') AND val != ''
                    LIMIT 1
                """, (k, ft, file_type)).fetchone()
                sv = sample[0] if sample else '(flag/no-value)'
                print(f"      missing: {ft} {k} = {sv}")

    return failures


units_failures   = audit('units')
advance_failures = audit('advance')

db.close()
print("\nDone.")
