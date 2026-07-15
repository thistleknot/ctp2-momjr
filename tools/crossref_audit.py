"""Cross-reference audit for MoM CTP2 gamedata files.

Purpose:
    Parse selected CTP2 database files with the existing ctp2_roundtrip parser and
    report missing cross-references in a consistent PASS/FAIL format.

Preconditions:
    - This script must live in the MoM tools directory beside ctp2_roundtrip.py.
    - The MoM scenario gamedata files must exist under ../scen0000/default/gamedata/.

Failure modes:
    - Missing input files or parser import failures raise immediately.
    - Malformed files are surfaced by ctp2_roundtrip.parse_file during parsing.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable, Iterator

TOOLS_DIR = Path(__file__).resolve().parent
GAMEDATA_DIR = TOOLS_DIR.parent / "scen0000" / "default" / "gamedata"

sys.path.insert(0, str(TOOLS_DIR))
from ctp2_roundtrip import parse_file, KV, Flag, SubList, Nested  # noqa: E402


AUDIT_FILES = [
    "Advance.txt",
    "Units.txt",
    "Improve.txt",
    "buildings.txt",
    "Wonder.txt",
    "tileimp.txt",
    "Orders.txt",
    "govern.txt",
    "goods.txt",
    "feat.txt",
]


def load_blocks(filename: str) -> dict[str, tuple]:
    """Load and parse one gamedata file.

    Require:
        filename names a file inside GAMEDATA_DIR.
    Guarantee:
        Returns the OrderedDict-like block mapping produced by parse_file.
    Failure modes:
        Raises if the file is missing or unreadable.
    """
    path = GAMEDATA_DIR / filename
    text = path.read_text(encoding="cp1252", errors="replace")
    return parse_file(text)


def iter_kvs(items: Iterable[object]) -> Iterator[KV]:
    """Yield every KV entry from a block body, including nested blocks.

    Require:
        items comes from ctp2_roundtrip.parse_file.
    Guarantee:
        Recurses through Nested items and yields only KV entries.
    Failure modes:
        None beyond malformed parser output.
    """
    for item in items:
        if isinstance(item, KV):
            yield item
        elif isinstance(item, Nested):
            yield from iter_kvs(item.items)
        elif isinstance(item, (Flag, SubList)):
            continue


def collect_advance_ref_issues(blocks: dict[str, tuple], advance_ids: set[str]) -> list[tuple[str, str, str]]:
    """Return missing ADVANCE_* references found in KV values.

    Require:
        blocks is a parsed file and advance_ids contains valid Advance.txt block IDs.
    Guarantee:
        Returns (block_id, field_name, bad_value) tuples for every missing reference.
    Failure modes:
        None.
    """
    issues: list[tuple[str, str, str]] = []
    for block_id, items in blocks.items():
        for item in iter_kvs(items):
            if isinstance(item.val, str) and item.val.startswith("ADVANCE_") and item.val not in advance_ids:
                issues.append((block_id, item.key, item.val))
    return sorted(issues)


def collect_field_ref_issues(
    blocks: dict[str, tuple],
    field_names: set[str],
    valid_ids: set[str],
) -> list[tuple[str, str, str]]:
    """Return missing references for a selected set of KV field names.

    Require:
        field_names contains the exact KV keys to validate.
    Guarantee:
        Returns (block_id, field_name, bad_value) tuples for values absent from valid_ids.
    Failure modes:
        None.
    """
    issues: list[tuple[str, str, str]] = []
    for block_id, items in blocks.items():
        for item in iter_kvs(items):
            if item.key in field_names and item.val not in valid_ids:
                issues.append((block_id, item.key, item.val))
    return sorted(issues)


def collect_set_diff_issues(left_ids: set[str], right_ids: set[str], missing_field: str) -> list[tuple[str, str, str]]:
    """Return set-difference issues in report-ready tuple form.

    Require:
        left_ids and right_ids are block-ID sets from related files.
    Guarantee:
        Returns (block_id, missing_field, block_id) tuples for left-only IDs.
    Failure modes:
        None.
    """
    return [(block_id, missing_field, block_id) for block_id in sorted(left_ids - right_ids)]


def print_check(description: str, issues: list[tuple[str, str, str]]) -> tuple[int, int]:
    """Print one audit section and return (pass_count, fail_count)."""
    if not issues:
        print(f"PASS: {description}")
        return 1, 0

    print(f"FAIL: {description}")
    for block_id, field_name, bad_value in issues:
        print(f"  - {block_id}: {field_name} = {bad_value}")
    return 0, 1


def main() -> int:
    """Run the full cross-reference audit and print a summary.

    Require:
        All referenced gamedata files exist.
    Guarantee:
        Emits PASS/FAIL sections plus final totals.
    Failure modes:
        Raises immediately on missing files or parse failures.
    """
    parsed = {filename: load_blocks(filename) for filename in AUDIT_FILES}
    specattack_blocks = load_blocks("specattack.txt")
    age_blocks = load_blocks("age.txt")

    advance_ids = set(parsed["Advance.txt"].keys())
    improve_ids = set(parsed["Improve.txt"].keys())
    building_ids = set(parsed["buildings.txt"].keys())
    goods_ids = set(parsed["goods.txt"].keys())
    specattack_ids = set(specattack_blocks.keys())
    age_ids = set(age_blocks.keys())

    checks: list[tuple[str, list[tuple[str, str, str]]]] = []

    for filename in AUDIT_FILES:
        checks.append(
            (
                f"{filename} ADVANCE_* references resolve in Advance.txt",
                collect_advance_ref_issues(parsed[filename], advance_ids),
            )
        )

    building_parity_issues = []
    building_parity_issues.extend(
        collect_set_diff_issues(building_ids, improve_ids, "MISSING_IN_IMPROVE")
    )
    building_parity_issues.extend(
        collect_set_diff_issues(improve_ids, building_ids, "MISSING_IN_BUILDINGS")
    )
    checks.append(("buildings.txt and Improve.txt block IDs match", building_parity_issues))

    checks.append(
        (
            "Units.txt SpecialAttackType values resolve in specattack.txt",
            collect_field_ref_issues(parsed["Units.txt"], {"SpecialAttackType"}, specattack_ids),
        )
    )
    checks.append(
        (
            "Units.txt GoodyType values resolve in goods.txt",
            collect_field_ref_issues(parsed["Units.txt"], {"GoodyType"}, goods_ids),
        )
    )
    checks.append(
        (
            "tileimp.txt BuildingSupport values resolve in Improve.txt or buildings.txt",
            collect_field_ref_issues(parsed["tileimp.txt"], {"BuildingSupport"}, improve_ids | building_ids),
        )
    )
    checks.append(
        (
            "Advance.txt Age values resolve in age.txt",
            collect_field_ref_issues(parsed["Advance.txt"], {"Age"}, age_ids),
        )
    )

    total_pass = 0
    total_fail = 0
    total_issues = 0
    for description, issues in checks:
        passed, failed = print_check(description, issues)
        total_pass += passed
        total_fail += failed
        total_issues += len(issues)

    print()
    print(f"Summary: total PASS = {total_pass}, total FAIL = {total_fail}, total issues found = {total_issues}")
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
