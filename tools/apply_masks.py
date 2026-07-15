#!/usr/bin/env python
"""
Apply Masks - Remove masked records from game files
====================================================

Processes game data files (Units.txt, Advance.txt, etc.) and removes
any records that have been masked for removal, generating clean override files.

Usage:
  python apply_masks.py [--dry-run]  # Preview changes without writing
  python apply_masks.py --apply      # Apply masks to game files
"""

import re
import os
from pathlib import Path
from mask_manager import MaskManager


GAMEDATA_DIR = "../scen0000/default/gamedata"
GL_DIR = "../scen0000/english/gamedata"


def parse_advance_block(content: str, record_id: str) -> tuple:
    """
    Extract a single ADVANCE_* block from Advance.txt.
    Returns (start_pos, end_pos, block_content).
    """
    # Match: ADVANCE_ID { ... }
    pattern = re.compile(
        rf"^{re.escape(record_id)}\s*\{{\s*(.*?)\n}}\s*$",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(content)
    if match:
        return match.start(), match.end(), match.group(0)
    return None, None, None


def parse_unit_block(content: str, record_id: str) -> tuple:
    """Extract a single UNIT_* block from Units.txt."""
    pattern = re.compile(
        rf"^{re.escape(record_id)}\s*\{{\s*(.*?)\n}}\s*$",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(content)
    if match:
        return match.start(), match.end(), match.group(0)
    return None, None, None


def parse_improve_block(content: str, record_id: str) -> tuple:
    """Extract a single IMPROVE_* block from Improve.txt."""
    pattern = re.compile(
        rf"^{re.escape(record_id)}\s*\{{\s*(.*?)\n}}\s*$",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(content)
    if match:
        return match.start(), match.end(), match.group(0)
    return None, None, None


def remove_records(filepath: str, masked_ids: set, parser_fn) -> tuple:
    """
    Remove masked records from a file.
    Returns (modified_content, removed_count, removed_ids).
    """
    if not os.path.exists(filepath):
        return None, 0, []

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    removed = []
    for record_id in sorted(masked_ids):
        start, end, block = parser_fn(content, record_id)
        if start is not None:
            # Remove the entire block including trailing whitespace
            content = content[:start] + content[end :].lstrip("\n")
            removed.append(record_id)

    return content, len(removed), removed


def remove_string_table_entries(filepath: str, masked_ids: set) -> tuple:
    """Remove string table entries (tab-delimited key-value pairs)."""
    if not os.path.exists(filepath):
        return None, 0, []

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    removed = []
    for record_id in sorted(masked_ids):
        # Match lines that start with RECORD_ID followed by tab
        pattern = rf"^{re.escape(record_id)}\t.*?$\n?"
        if re.search(pattern, content, re.MULTILINE):
            content = re.sub(pattern, "", content, flags=re.MULTILINE)
            removed.append(record_id)

    return content, len(removed), removed


def apply_masks(dry_run: bool = True):
    """Apply all masks to game files."""
    mgr = MaskManager()
    masked = {k: v for k, v in mgr.state.items() if k != "version"}

    if not any(masked.values()):
        print("[EMPTY] No masked records to apply")
        return

    print(f"\n{'='*60}")
    print("MASK APPLICATION REPORT")
    print(f"{'='*60}\n")

    # Process each dimension
    if masked.get("advances"):
        filepath = os.path.join(GAMEDATA_DIR, "Advance.txt")
        content, count, removed = remove_records(
            filepath, set(masked["advances"]), parse_advance_block
        )
        if count > 0:
            print(f"ADVANCES ({count} removed):")
            for adv in removed:
                print(f"  - {adv}")
            if not dry_run and content:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                print(f"  [WRITTEN] {filepath}\n")
            elif dry_run:
                print(f"  [DRY-RUN] Would write to {filepath}\n")

    if masked.get("units"):
        filepath = os.path.join(GAMEDATA_DIR, "Units.txt")
        content, count, removed = remove_records(
            filepath, set(masked["units"]), parse_unit_block
        )
        if count > 0:
            print(f"UNITS ({count} removed):")
            for unit in removed:
                print(f"  - {unit}")
            if not dry_run and content:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                print(f"  [WRITTEN] {filepath}\n")
            elif dry_run:
                print(f"  [DRY-RUN] Would write to {filepath}\n")
        
        # Also remove from string tables
        str_files = [
            ("gl_str.txt", GL_DIR),
            ("junk_str.txt", GL_DIR),
        ]
        for str_file, dir_path in str_files:
            str_filepath = os.path.join(dir_path, str_file)
            str_content, str_count, str_removed = remove_string_table_entries(
                str_filepath, set(masked["units"])
            )
            if str_count > 0 and str_removed:
                print(f"STRING TABLE ({str_file}): {str_count} entries removed")
                if not dry_run and str_content:
                    with open(str_filepath, "w", encoding="utf-8") as f:
                        f.write(str_content)
                    print(f"  [WRITTEN] {str_filepath}\n")
                elif dry_run:
                    print(f"  [DRY-RUN] Would write to {str_filepath}\n")

    if masked.get("improvements"):
        filepath = os.path.join(GAMEDATA_DIR, "Improve.txt")
        content, count, removed = remove_records(
            filepath, set(masked["improvements"]), parse_improve_block
        )
        if count > 0:
            print(f"IMPROVEMENTS ({count} removed):")
            for imp in removed:
                print(f"  - {imp}")
            if not dry_run and content:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                print(f"  [WRITTEN] {filepath}\n")
            elif dry_run:
                print(f"  [DRY-RUN] Would write to {filepath}\n")

    if masked.get("wonders"):
        filepath = os.path.join(GAMEDATA_DIR, "Wonder.txt")
        content, count, removed = remove_records(
            filepath, set(masked["wonders"]), parse_unit_block
        )
        if count > 0:
            print(f"WONDERS ({count} removed):")
            for wonder in removed:
                print(f"  - {wonder}")
            if not dry_run and content:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                print(f"  [WRITTEN] {filepath}\n")
            elif dry_run:
                print(f"  [DRY-RUN] Would write to {filepath}\n")

    if masked.get("tileimps"):
        filepath = os.path.join(GAMEDATA_DIR, "tileimp.txt")
        content, count, removed = remove_records(
            filepath, set(masked["tileimps"]), parse_unit_block
        )
        if count > 0:
            print(f"TILE IMPROVEMENTS ({count} removed):")
            for imp in removed:
                print(f"  - {imp}")
            if not dry_run and content:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                print(f"  [WRITTEN] {filepath}\n")
            elif dry_run:
                print(f"  [DRY-RUN] Would write to {filepath}\n")

    print(f"{'='*60}")
    if dry_run:
        print("DRY-RUN: Use --apply to write changes")
    else:
        print("Changes applied to game files")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    import sys

    dry_run = "--apply" not in sys.argv
    apply_masks(dry_run=dry_run)
