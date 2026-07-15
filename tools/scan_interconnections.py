#!/usr/bin/env python
"""
Interconnection Scanner - Find all references to a masked record
================================================================

When a record (unit, advance, improvement, etc.) is masked for removal,
this tool scans all game files to find interconnections that need cleanup:
- Icon definitions (uniticon.txt)
- Great Library entries (gameplay, historical, prereq, statistics, summary)
- Text references in descriptions (advances, units, improvements)
- Unit/improvement/wonder lists that reference the record
- Prerequisites that reference the record

Usage:
  python scan_interconnections.py <dimension> <record_id>
  
Examples:
  python scan_interconnections.py units UNIT_BOMBER
  python scan_interconnections.py advances ADVANCE_MYSTICISM
  python scan_interconnections.py improvements IMPROVE_LIBRARY
"""

import re
import os
from pathlib import Path
from typing import Dict, List, Tuple


GAMEDATA_DIR = "../scen0000/default/gamedata"
GL_DIR = "../scen0000/english/gamedata"


class InterconnectionScanner:
    def __init__(self, dimension: str, record_id: str):
        self.dimension = dimension
        self.record_id = record_id
        self.interconnections = {}

    def scan_all(self) -> Dict[str, List[str]]:
        """Scan all interconnections for a record."""
        self.interconnections = {
            "icon_refs": [],
            "gl_sections": [],
            "gl_text_refs": [],
            "unit_refs": [],
            "advance_refs": [],
            "improve_refs": [],
            "wonder_refs": [],
            "prerequisite_refs": [],
        }

        # Scan based on dimension
        if self.dimension == "units":
            self._scan_unit_interconnections()
        elif self.dimension == "advances":
            self._scan_advance_interconnections()
        elif self.dimension == "improvements":
            self._scan_improve_interconnections()
        elif self.dimension == "wonders":
            self._scan_wonder_interconnections()
        elif self.dimension == "tileimps":
            self._scan_tileimp_interconnections()

        return {k: v for k, v in self.interconnections.items() if v}

    def _scan_unit_interconnections(self):
        """Scan interconnections for a unit (UNIT_*)."""
        # Icon in uniticon.txt
        icon_ref = f"ICON_{self.record_id}"
        self._scan_file(
            os.path.join(GAMEDATA_DIR, "uniticon.txt"),
            icon_ref,
            "icon_refs",
        )

        # String tables (gl_str.txt, junk_str.txt)
        self._scan_file(
            os.path.join(GL_DIR, "gl_str.txt"),
            f"^{self.record_id}\t",
            "icon_refs",
        )
        self._scan_file(
            os.path.join(GL_DIR, "junk_str.txt"),
            f"^{self.record_id}\t",
            "icon_refs",
        )

        # GL sections
        gl_sections = [
            f"{self.record_id}_GAMEPLAY",
            f"{self.record_id}_HISTORICAL",
            f"{self.record_id}_PREREQ",
            f"{self.record_id}_STATISTICS",
            f"{self.record_id}_SUMMARY",
        ]
        for section in gl_sections:
            self._scan_file(
                os.path.join(GL_DIR, "Great_Library.txt"),
                rf"\[{section}\]",
                "gl_sections",
            )

        # Text references in Great Library
        self._scan_text_refs(
            os.path.join(GL_DIR, "Great_Library.txt"), self.record_id, "gl_text_refs"
        )

        # References in Advance descriptions
        self._scan_text_refs(
            os.path.join(GAMEDATA_DIR, "Advance.txt"),
            self.record_id,
            "advance_refs",
        )

        # References in Wonder descriptions
        self._scan_text_refs(
            os.path.join(GAMEDATA_DIR, "Wonder.txt"), self.record_id, "wonder_refs"
        )

        # References in Improve descriptions
        self._scan_text_refs(
            os.path.join(GAMEDATA_DIR, "Improve.txt"),
            self.record_id,
            "improve_refs",
        )

    def _scan_advance_interconnections(self):
        """Scan interconnections for an advance (ADVANCE_*)."""
        # GL sections
        gl_sections = [
            f"{self.record_id}_GAMEPLAY",
            f"{self.record_id}_HISTORICAL",
            f"{self.record_id}_PREREQ",
            f"{self.record_id}_STATISTICS",
        ]
        for section in gl_sections:
            self._scan_file(
                os.path.join(GL_DIR, "Great_Library.txt"),
                rf"\[{section}\]",
                "gl_sections",
            )

        # Text references in GL (links in descriptions)
        self._scan_text_refs(
            os.path.join(GL_DIR, "Great_Library.txt"), self.record_id, "gl_text_refs"
        )

        # Prerequisites in Advance.txt
        self._scan_file(
            os.path.join(GAMEDATA_DIR, "Advance.txt"),
            f"Prerequisites {self.record_id}",
            "prerequisite_refs",
        )

        # Prerequisites in Units.txt
        self._scan_file(
            os.path.join(GAMEDATA_DIR, "Units.txt"),
            f"Prerequisites {self.record_id}",
            "prerequisite_refs",
        )

        # Prerequisites in Improve.txt
        self._scan_file(
            os.path.join(GAMEDATA_DIR, "Improve.txt"),
            f"Prerequisites {self.record_id}",
            "prerequisite_refs",
        )

        # Prerequisites in Wonder.txt
        self._scan_file(
            os.path.join(GAMEDATA_DIR, "Wonder.txt"),
            f"Prerequisites {self.record_id}",
            "prerequisite_refs",
        )

    def _scan_improve_interconnections(self):
        """Scan interconnections for an improvement (IMPROVE_*)."""
        # GL sections
        gl_sections = [
            f"{self.record_id}_GAMEPLAY",
            f"{self.record_id}_HISTORICAL",
            f"{self.record_id}_PREREQ",
            f"{self.record_id}_STATISTICS",
            f"{self.record_id}_SUMMARY",
        ]
        for section in gl_sections:
            self._scan_file(
                os.path.join(GL_DIR, "Great_Library.txt"),
                rf"\[{section}\]",
                "gl_sections",
            )

        # Icon reference
        icon_ref = f"ICON_{self.record_id}"
        self._scan_file(
            os.path.join(GAMEDATA_DIR, "uniticon.txt"),
            icon_ref,
            "icon_refs",
        )

    def _scan_wonder_interconnections(self):
        """Scan interconnections for a wonder (WONDER_*)."""
        # GL sections
        gl_sections = [
            f"{self.record_id}_GAMEPLAY",
            f"{self.record_id}_HISTORICAL",
            f"{self.record_id}_PREREQ",
            f"{self.record_id}_STATISTICS",
        ]
        for section in gl_sections:
            self._scan_file(
                os.path.join(GL_DIR, "Great_Library.txt"),
                rf"\[{section}\]",
                "gl_sections",
            )

        # Icon reference
        icon_ref = f"ICON_{self.record_id}"
        self._scan_file(
            os.path.join(GAMEDATA_DIR, "uniticon.txt"),
            icon_ref,
            "icon_refs",
        )

    def _scan_tileimp_interconnections(self):
        """Scan interconnections for a tile improvement (TILEIMP_*)."""
        # GL sections
        gl_sections = [
            f"{self.record_id}_GAMEPLAY",
            f"{self.record_id}_HISTORICAL",
            f"{self.record_id}_PREREQ",
            f"{self.record_id}_STATISTICS",
        ]
        for section in gl_sections:
            self._scan_file(
                os.path.join(GL_DIR, "Great_Library.txt"),
                rf"\[{section}\]",
                "gl_sections",
            )

        # Icon reference
        icon_ref = f"ICON_{self.record_id}"
        self._scan_file(
            os.path.join(GAMEDATA_DIR, "uniticon.txt"),
            icon_ref,
            "icon_refs",
        )

    def _scan_file(self, filepath: str, pattern: str, category: str):
        """Search a file for a pattern and record matches."""
        if not os.path.exists(filepath):
            return

        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            if re.search(pattern, content, re.IGNORECASE):
                self.interconnections[category].append(
                    os.path.basename(filepath)
                )
        except Exception as e:
            pass

    def _scan_text_refs(self, filepath: str, record_id: str, category: str):
        """Search a file for text references like <L:DATABASE_*,RECORD_ID>."""
        if not os.path.exists(filepath):
            return

        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            # Match <L:DATABASE_*,RECORD_ID> patterns
            pattern = rf"<L:[A-Z_,]*{re.escape(record_id)}[^>]*>"
            if re.search(pattern, content):
                self.interconnections[category].append(
                    os.path.basename(filepath)
                )
        except Exception as e:
            pass

    def print_report(self):
        """Print a formatted interconnection report."""
        print(f"\n{'='*70}")
        print(f"INTERCONNECTION SCAN: {self.dimension.upper()} / {self.record_id}")
        print(f"{'='*70}\n")

        interconnections = self.scan_all()

        if not interconnections:
            print("✓ No interconnections found - safe to remove\n")
            return

        print("⚠ INTERCONNECTIONS FOUND:\n")

        category_labels = {
            "icon_refs": "Icon References",
            "gl_sections": "Great Library Sections",
            "gl_text_refs": "GL Text References",
            "unit_refs": "Unit References",
            "advance_refs": "Advance References",
            "improve_refs": "Improvement References",
            "wonder_refs": "Wonder References",
            "prerequisite_refs": "Prerequisite References",
        }

        for category, files in interconnections.items():
            if files:
                label = category_labels.get(category, category)
                print(f"  {label}:")
                for filepath in sorted(set(files)):
                    print(f"    - {filepath}")
                print()

        print(f"{'='*70}")
        print("ACTION: Use apply_masks.py --apply to remove all above references")
        print(f"{'='*70}\n")


def main():
    """CLI entry point."""
    import sys

    if len(sys.argv) < 3:
        print("Usage: python scan_interconnections.py <dimension> <record_id>")
        print("\nDimensions: units, advances, improvements, wonders, tileimps")
        print("\nExamples:")
        print("  python scan_interconnections.py units UNIT_BOMBER")
        print("  python scan_interconnections.py advances ADVANCE_MYSTICISM")
        return

    dimension = sys.argv[1]
    record_id = sys.argv[2]

    scanner = InterconnectionScanner(dimension, record_id)
    scanner.print_report()


if __name__ == "__main__":
    main()
