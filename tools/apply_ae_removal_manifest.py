#!/usr/bin/env python3
"""
Apply AE Building Removal Manifest
==================================
Reads ae_building_removal_manifest.json and applies the specified removals/hiding
to the scenario gamedata files. 

For CTP2, "removal" from a scenario override means either:
1. Physically deleting the block (if it was added by the scenario and is now unwanted).
2. Adding `NoIndex` and `GLHidden` flags (if it's a base AE record we want to hide).

This script enforces the control plane: the manifest is the source of truth.
"""

import json
import os
import re
from pathlib import Path

SCENARIO_DIR = Path(__file__).parent.parent / "scen0000"
GAMEDATA_DIR = SCENARIO_DIR / "default" / "gamedata"
GL_DIR = SCENARIO_DIR / "english" / "gamedata"
MANIFEST_PATH = Path(__file__).parent.parent / "ae_building_removal_manifest.json"

def load_manifest():
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def remove_block(filepath: Path, record_id: str) -> bool:
    """Physically remove a { ... } block from a file (handles both multi-line and single-line blocks)."""
    if not filepath.exists():
        return False
    
    content = filepath.read_text(encoding="utf-8", errors="ignore")
    # Match record_id { ... } 
    # Handle both multi-line (.*?\n}) and single-line (.*?}) blocks
    pattern = re.compile(rf"^{re.escape(record_id)}\s*\{{.*?\}}\s*\n?", re.MULTILINE | re.DOTALL)
    
    if pattern.search(content):
        new_content = pattern.sub("", content)
        filepath.write_text(new_content, encoding="utf-8", errors="ignore")
        return True
    return False

def add_hidden_flags(filepath: Path, record_id: str) -> bool:
    """Add NoIndex and GLHidden flags to a block."""
    if not filepath.exists():
        return False
    
    content = filepath.read_text(encoding="utf-8", errors="ignore")
    # Find the block
    pattern = re.compile(rf"^{re.escape(record_id)}\s*\{{(.*?)\n}}\s*", re.MULTILINE | re.DOTALL)
    match = pattern.search(content)
    if match:
        block = match.group(0)
        if "GLHidden" not in block:
            # Insert flags before the closing brace
            new_block = block.rstrip()
            if not new_block.endswith("}"):
                new_block = new_block + "\n   NoIndex\n   GLHidden\n}"
            else:
                new_block = new_block[:-1] + "   NoIndex\n   GLHidden\n}"
            new_content = content[:match.start()] + new_block + content[match.end():]
            filepath.write_text(new_content, encoding="utf-8", errors="ignore")
            return True
    return False

def remove_gl_sections(filepath: Path, record_id: str, sections: list) -> bool:
    """Remove specific Great Library sections for a file."""
    if not filepath.exists():
        return False
    
    # Great Library files often have mixed encodings (cp1252/latin-1). Use errors='ignore' to be safe.
    content = filepath.read_text(encoding="utf-8", errors="ignore")
    modified = False
    
    for section in sections:
        # Match [RECORD_ID_SECTION] ... up to the next [ or EOF
        pattern = re.compile(rf"^\[{re.escape(record_id)}_{section}\].*?(?=\n\[|\Z)", re.MULTILINE | re.DOTALL)
        if pattern.search(content):
            content = pattern.sub("", content)
            modified = True
            
    if modified:
        # Clean up multiple blank lines
        content = re.sub(r'\n{3,}', '\n\n', content)
        filepath.write_text(content, encoding="utf-8", errors="ignore")
        
    return modified

def remove_string_entry(filepath: Path, record_id: str) -> bool:
    """Remove a tab-delimited string table entry."""
    if not filepath.exists():
        return False
    
    content = filepath.read_text(encoding="utf-8", errors="ignore")
    pattern = re.compile(rf"^{re.escape(record_id)}\t.*?\n", re.MULTILINE)
    if pattern.search(content):
        content = pattern.sub("", content)
        filepath.write_text(content, encoding="utf-8", errors="ignore")
        return True
    return False

def apply_manifest(dry_run=False):
    manifest = load_manifest()
    buildings = manifest.get("buildings", [])
    
    print(f"Processing {len(buildings)} building entries from manifest...")
    
    for b in buildings:
        key = b["key"]
        status = b["status"]
        if status != "removed":
            continue
            
        files = b.get("files", {})
        print(f"\nProcessing: {key}")
        
        # 1. buildings.txt
        if files.get("buildings_txt"):
            # For scenario overrides, we physically remove the block if it exists
            if remove_block(GAMEDATA_DIR / "buildings.txt", key):
                print(f"  [REMOVED] {key} from buildings.txt")
                
        # 2. uniticon.txt (often prefixed with ICON_)
        if files.get("uniticon_txt"):
            # Try with and without ICON_ prefix
            if remove_block(GAMEDATA_DIR / "uniticon.txt", key):
                print(f"  [REMOVED] {key} from uniticon.txt")
            elif remove_block(GAMEDATA_DIR / "uniticon.txt", f"ICON_{key}"):
                print(f"  [REMOVED] ICON_{key} from uniticon.txt")
                
        # 3. improveicon.txt
        if files.get("improveicon_txt"):
            if remove_block(GAMEDATA_DIR / "improveicon.txt", key):
                print(f"  [REMOVED] {key} from improveicon.txt")
            elif remove_block(GAMEDATA_DIR / "improveicon.txt", f"ICON_{key}"):
                print(f"  [REMOVED] ICON_{key} from improveicon.txt")
                
        # 4. Great_Library.txt sections
        gl_files = files.get("Great_Library_txt", {})
        if isinstance(gl_files, dict):
            sections_to_remove = [k for k, v in gl_files.items() if v]
            if sections_to_remove:
                if remove_gl_sections(GL_DIR / "Great_Library.txt", key, sections_to_remove):
                    print(f"  [REMOVED GL SECTIONS] {key} {sections_to_remove}")
                    
        # 5. WAW_Great_Library.txt sections
        waw_files = files.get("WAW_Great_Library_txt", {})
        if isinstance(waw_files, dict):
            sections_to_remove = [k for k, v in waw_files.items() if v]
            if sections_to_remove:
                if remove_gl_sections(GL_DIR / "WAW_Great_Library.txt", key, sections_to_remove):
                    print(f"  [REMOVED WAW GL SECTIONS] {key} {sections_to_remove}")
                    
        # 6. gl_str.txt
        if files.get("gl_str_txt"):
            if remove_string_entry(GL_DIR / "gl_str.txt", key):
                print(f"  [REMOVED STRING] {key} from gl_str.txt")
                
        # 7. junk_str.txt
        junk_files = files.get("junk_str_txt", {})
        if isinstance(junk_files, dict):
            # junk_str usually has DESCRIPTION_ and PREREQ_ prefixes
            for prefix, should_remove in junk_files.items():
                if should_remove:
                    entry_key = f"{prefix}_{key}" if prefix else key
                    if remove_string_entry(GL_DIR / "junk_str.txt", entry_key):
                        print(f"  [REMOVED STRING] {entry_key} from junk_str.txt")

    print("\n[COMPLETE] Manifest application finished.")

if __name__ == "__main__":
    apply_manifest(dry_run=False)
