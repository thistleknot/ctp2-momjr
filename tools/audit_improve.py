"""
audit_improve.py - Cross-reference audit for CTP2 gamedata files.

Checks all ENABLING_ADVANCE / EnabledBy references across every dimension
against the actual Advance.txt block IDs. Reports missing/truncated/placeholder
advance names that would cause silent crashes.
"""
import csv
import sys
from pathlib import Path

TOOLS = Path(__file__).parent
GAMEDATA = TOOLS.parent / "scen0000" / "default" / "gamedata"

sys.path.insert(0, str(TOOLS))
from ctp2_roundtrip import parse_file, KV, Flag, SubList, Nested

PASS_COUNT = 0
FAIL_COUNT = 0
ISSUE_COUNT = 0


def report_pass(msg):
    global PASS_COUNT
    PASS_COUNT += 1
    print(f"PASS: {msg}")


def report_fail(msg, issues):
    global FAIL_COUNT, ISSUE_COUNT
    FAIL_COUNT += 1
    ISSUE_COUNT += len(issues)
    print(f"FAIL: {msg}")
    for issue in issues:
        print(f"  - {issue}")


def load_block_ids(path):
    txt = path.read_text(encoding="utf-8", errors="replace")
    return set(parse_file(txt).keys())


def load_all_kv(path):
    """Return dict of block_id -> {key: val} for KV items."""
    txt = path.read_text(encoding="utf-8", errors="replace")
    blocks = parse_file(txt)
    result = {}
    for bid, items in blocks.items():
        result[bid] = {}
        for item in items:
            if isinstance(item, KV):
                result[bid][item.key] = item.val
    return result


def check_advance_refs(label, path, advance_ids, advance_fields):
    """Check that all advance-reference fields point to existing advances."""
    blocks = load_all_kv(path)
    issues = []
    for bid, kv in blocks.items():
        for field in advance_fields:
            val = kv.get(field, "").strip()
            if not val or val == "NULL":
                continue
            if val not in advance_ids:
                issues.append(f"{bid}: {field} = '{val}'  [NOT IN Advance.txt]")
    if issues:
        report_fail(f"{label} advance refs", issues)
    else:
        report_pass(f"{label} advance refs")


def check_csv_advance_refs(label, csv_path, id_col, advance_fields, advance_ids):
    """Check advance refs in a CSV source file."""
    issues = []
    with open(csv_path, encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            row_id = row.get(id_col, row.get("id", "?")).strip()
            for field in advance_fields:
                val = row.get(field, "").strip()
                if not val or val == "NULL":
                    continue
                if val not in advance_ids:
                    issues.append(f"{row_id}: {field} = '{val}'  [NOT IN Advance.txt]")
    if issues:
        report_fail(f"{label} (CSV) advance refs", issues)
    else:
        report_pass(f"{label} (CSV) advance refs")


# ── main ──────────────────────────────────────────────────────────────────────

print("=" * 70)
print("CTP2 Cross-Reference Audit")
print("=" * 70)
print()

# Load Advance.txt block IDs
advance_ids = load_block_ids(GAMEDATA / "Advance.txt")
print(f"Advance.txt: {len(advance_ids)} advances loaded")
print()

# ── 1. Improve.txt (inline format) ───────────────────────────────────────────
check_advance_refs(
    "Improve.txt",
    GAMEDATA / "Improve.txt",
    advance_ids,
    ["ENABLING_ADVANCE", "OBSOLETE_ADVANCE"],
)

# ── 2. Improve.csv source ────────────────────────────────────────────────────
if (TOOLS / "data_csv" / "improve.csv").exists():
    check_csv_advance_refs(
        "improve.csv",
        TOOLS / "data_csv" / "improve.csv",
        "id",
        ["ENABLING_ADVANCE", "OBSOLETE_ADVANCE"],
        advance_ids,
    )

# ── 3. buildings.txt ─────────────────────────────────────────────────────────
check_advance_refs(
    "buildings.txt",
    GAMEDATA / "buildings.txt",
    advance_ids,
    ["EnableAdvance"],
)

# ── 4. Units.txt ─────────────────────────────────────────────────────────────
check_advance_refs(
    "Units.txt",
    GAMEDATA / "Units.txt",
    advance_ids,
    ["EnabledBy", "EnableAdvance", "ObsoleteAdvance"],
)

# ── 5. Wonder.txt ─────────────────────────────────────────────────────────────
check_advance_refs(
    "Wonder.txt",
    GAMEDATA / "Wonder.txt",
    advance_ids,
    ["EnabledBy", "EnableAdvance", "ObsoleteAdvance"],
)

# ── 6. tileimp.txt ────────────────────────────────────────────────────────────
check_advance_refs(
    "tileimp.txt",
    GAMEDATA / "tileimp.txt",
    advance_ids,
    ["EnabledBy", "EnableAdvance", "ObsoleteAdvance"],
)

# ── 7. Orders.txt ─────────────────────────────────────────────────────────────
check_advance_refs(
    "Orders.txt",
    GAMEDATA / "Orders.txt",
    advance_ids,
    ["EnabledBy", "EnableAdvance"],
)

# ── 8. govern.txt ─────────────────────────────────────────────────────────────
check_advance_refs(
    "govern.txt",
    GAMEDATA / "govern.txt",
    advance_ids,
    ["EnabledBy", "EnableAdvance"],
)

# ── 9. goods.txt ──────────────────────────────────────────────────────────────
check_advance_refs(
    "goods.txt",
    GAMEDATA / "goods.txt",
    advance_ids,
    ["EnabledBy", "EnableAdvance"],
)

# ── 10. feat.txt ──────────────────────────────────────────────────────────────
check_advance_refs(
    "feat.txt",
    GAMEDATA / "feat.txt",
    advance_ids,
    ["EnabledBy", "EnableAdvance"],
)

# ── 11. buildings.txt vs Improve.txt block overlap ────────────────────────────
bld_ids = load_block_ids(GAMEDATA / "buildings.txt")
imp_ids = load_block_ids(GAMEDATA / "Improve.txt")
bld_only = sorted(bld_ids - imp_ids)
imp_only = sorted(imp_ids - bld_ids)
in_both  = sorted(bld_ids & imp_ids)

print()
print(f"buildings.txt vs Improve.txt overlap:")
print(f"  In both:          {len(in_both)}")
print(f"  buildings.txt only (MoM-specific): {len(bld_only)}")
print(f"  Improve.txt only (base CTP2):      {len(imp_only)}")

# ── 12. Specifically: empty ENABLING_ADVANCE in Improve.txt ──────────────────
blocks = load_all_kv(GAMEDATA / "Improve.txt")
empty_enable = [bid for bid, kv in blocks.items()
                if "ENABLING_ADVANCE" in kv and not kv["ENABLING_ADVANCE"].strip()]
if empty_enable:
    report_fail("Improve.txt ENABLING_ADVANCE empty",
                [f"{bid}: ENABLING_ADVANCE = ''" for bid in empty_enable])
else:
    report_pass("Improve.txt ENABLING_ADVANCE not empty")

# ── Summary ───────────────────────────────────────────────────────────────────
print()
print("=" * 70)
print(f"SUMMARY: {PASS_COUNT} PASS  |  {FAIL_COUNT} FAIL  |  {ISSUE_COUNT} issues")
print("=" * 70)
