#!/usr/bin/env python3
"""Consolidate core pipeline scripts into a single markdown file for bird's-eye review."""
import os
from pathlib import Path

TOOLS_DIR = Path(__file__).parent

CORE_FILES = [
    "ctp2_generator.py",
    "sync_excel_to_csv.py",
    "ctp2_parser.py",
    "ctp2_ae_parser.py",
    "ctp2_line_codec.py",
    "ctp2_csv_codec.py",
    "validate_all_surfaces.py",
    "token_verify.py",
    "build_schema.py",
    "schema_registry.py",
]

OUTPUT_FILE = TOOLS_DIR / "CORE_PIPELINE_REVIEW.md"

with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
    out.write("# Core Pipeline Review\n\n")
    for filename in CORE_FILES:
        filepath = TOOLS_DIR / filename
        if filepath.exists():
            out.write(f"\n## {filename}\n\n```python\n")
            out.write(filepath.read_text(encoding="utf-8"))
            out.write("\n```\n\n")
        else:
            out.write(f"\n## {filename}\n\n*FILE NOT FOUND*\n\n")

print(f"Consolidated {len(CORE_FILES)} files into {OUTPUT_FILE}")
