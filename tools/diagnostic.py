"""Diagnostic: Check AdvanceLists.txt content vs expected MoM advances."""
import csv
import re
from pathlib import Path

ROOT = Path(r"H:\Program Files(x86)\Activision\Call To Power 2\Scenarios\mom")
MOMJR = ROOT / "tools" / "momjr_csv"
SCENARIO = ROOT / "scen0000" / "default"
GAMEDATA = SCENARIO / "gamedata"
AIDATA = SCENARIO / "aidata"

# 1. Load MoM advances from advances.csv
mom_advance_ids = set()
with open(MOMJR / "advances.csv", newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        name = (row.get("name") or "").split(";")[0].strip()
        if not name or name.startswith("x") or "Extra Advance" in name or name.lower() == "blah":
            continue
        # Use same sanitize logic as generator
        name_clean = name.upper().replace(' ', '_').replace("'", '')
        ident = f"ADVANCE_{name_clean}"
        ident = re.sub(r'[^A-Z0-9_]', '', ident)
        ident = re.sub(r'_+', '_', ident).strip('_')
        mom_advance_ids.add(ident)

print(f"MoM advances from CSV: {len(mom_advance_ids)}")

# 2. Load Advance.txt and find hidden advances
advance_txt_path = GAMEDATA / "Advance.txt"
advance_text = advance_txt_path.read_text(encoding="latin-1")
advance_blocks = {}
for m in re.finditer(r'^(ADVANCE_[A-Z0-9_]+)\s*\{', advance_text, re.MULTILINE):
    ident = m.group(1)
    # Find the block content (simple approach)
    start = m.end()
    depth = 1
    i = start
    while i < len(advance_text) and depth > 0:
        if advance_text[i] == '{':
            depth += 1
        elif advance_text[i] == '}':
            depth -= 1
        i += 1
    block = advance_text[m.start():i]
    advance_blocks[ident] = block

hidden_advance_ids = {
    ident for ident, block in advance_blocks.items()
    if re.search(r'^\s*(NoIndex|GLHidden)\s*$', block, re.MULTILINE)
}
print(f"Total advances in Advance.txt: {len(advance_blocks)}")
print(f"Hidden advances (NoIndex or GLHidden): {len(hidden_advance_ids)}")

# 3. Load AdvanceLists.txt and extract all Advance refs
advance_lists_path = AIDATA / "AdvanceLists.txt"
if advance_lists_path.exists():
    list_text = advance_lists_path.read_text(encoding="latin-1")
    advance_list_refs = re.findall(r'\bAdvance\s+(ADVANCE_[A-Z0-9_]+)\b', list_text)
    print(f"AdvanceLists.txt contains {len(advance_list_refs)} advance references")
    unique_refs = set(advance_list_refs)
    print(f"Unique advances referenced: {len(unique_refs)}")

    # 4. Categorize
    mom_only_refs = [ref for ref in unique_refs if ref in mom_advance_ids]
    hidden_base_refs = [ref for ref in unique_refs if ref in hidden_advance_ids]
    unresolved_refs = [ref for ref in unique_refs if ref not in advance_blocks]

    print(f"\nBreakdown:")
    print(f"  MoM CSV advances: {len(mom_only_refs)} refs")
    print(f"  Hidden base advances: {len(hidden_base_refs)} refs")
    print(f"  Unresolved (not in Advance.txt): {len(unresolved_refs)} refs")

    if hidden_base_refs:
        print(f"\nHidden base advances in AdvanceLists.txt (first 20):")
        for ref in sorted(hidden_base_refs)[:20]:
            count = advance_list_refs.count(ref)
            print(f"  {ref} (appears {count} time(s))")
else:
    print("AdvanceLists.txt not found!")
