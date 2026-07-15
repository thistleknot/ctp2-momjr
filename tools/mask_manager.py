#!/usr/bin/env python
"""
Mask Manager - Track and apply dimension masks for incremental debugging
=========================================================================

Allows masking out individual records (units, advances, improvements, etc.)
for iterative debugging and fixing without having to rollback entire dimensions.

Maintains a persistent mask state and provides CLI commands to:
  - mask <dimension> <record_id>   : Add record to removal mask
  - unmask <dimension> <record_id> : Remove record from mask
  - list [dimension]               : Show all masked records
  - apply                          : Generate override files with masked records removed
  - reset                          : Clear all masks
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Set

MASK_DB_FILE = "mask_state.json"


class MaskManager:
    def __init__(self, mask_file: str = MASK_DB_FILE):
        self.mask_file = mask_file
        self.state = self._load_state()

    def _load_state(self) -> Dict:
        """Load mask state from JSON file."""
        if os.path.exists(self.mask_file):
            with open(self.mask_file, "r") as f:
                return json.load(f)
        return {
            "version": 1,
            "units": [],
            "advances": [],
            "improvements": [],
            "wonders": [],
            "tileimps": [],
        }

    def _save_state(self):
        """Save mask state to JSON file."""
        with open(self.mask_file, "w") as f:
            json.dump(self.state, f, indent=2)

    def mask(self, dimension: str, record_id: str, auto_scan: bool = True) -> bool:
        """Add a record to removal mask."""
        if dimension not in self.state:
            print(f"Unknown dimension: {dimension}")
            print(f"Valid dimensions: {', '.join(k for k in self.state.keys() if k != 'version')}")
            return False

        masked = self.state[dimension]
        if record_id not in masked:
            masked.append(record_id)
            self._save_state()
            print(f"[MASK] {dimension}: {record_id}")
            
            # Auto-scan interconnections
            if auto_scan:
                self._run_interconnection_scan(dimension, record_id)
            
            return True
        else:
            print(f"[SKIP] {record_id} already masked in {dimension}")
            return False
    
    def _run_interconnection_scan(self, dimension: str, record_id: str):
        """Run interconnection scanner and report findings."""
        try:
            from scan_interconnections import InterconnectionScanner
            scanner = InterconnectionScanner(dimension, record_id)
            interconnections = scanner.scan_all()
            
            if interconnections:
                print(f"\n⚠ INTERCONNECTIONS DETECTED:")
                for category, files in interconnections.items():
                    if files:
                        category_name = category.replace('_', ' ').title()
                        print(f"  {category_name}: {', '.join(sorted(set(files)))}")
                print(f"\n💡 Tip: Run 'python apply_masks.py --apply' to auto-remove all references\n")
            else:
                print(f"✓ No interconnections found\n")
        except ImportError:
            # scan_interconnections.py not available
            pass

    def unmask(self, dimension: str, record_id: str) -> bool:
        """Remove a record from removal mask."""
        if dimension not in self.state:
            print(f"Unknown dimension: {dimension}")
            return False

        masked = self.state[dimension]
        if record_id in masked:
            masked.remove(record_id)
            self._save_state()
            print(f"[UNMASK] {dimension}: {record_id}")
            return True
        else:
            print(f"[SKIP] {record_id} not in {dimension} mask")
            return False

    def list_masked(self, dimension: str = None) -> Dict[str, List[str]]:
        """List all masked records, optionally filtered by dimension."""
        if dimension:
            if dimension not in self.state:
                print(f"Unknown dimension: {dimension}")
                return {}
            return {dimension: self.state[dimension]}

        result = {k: v for k, v in self.state.items() if k != "version" and v}
        return result

    def print_list(self, dimension: str = None):
        """Print masked records in human-readable format."""
        masked = self.list_masked(dimension)
        if not masked:
            print("[EMPTY] No masked records")
            return

        for dim, records in masked.items():
            if records:
                print(f"\n{dim.upper()} ({len(records)} masked):")
                for rec in sorted(records):
                    print(f"  - {rec}")

    def reset(self) -> bool:
        """Clear all masks."""
        self.state = {
            "version": 1,
            "units": [],
            "advances": [],
            "improvements": [],
            "wonders": [],
            "tileimps": [],
        }
        self._save_state()
        print("[RESET] All masks cleared")
        return True

    def get_masked(self, dimension: str) -> Set[str]:
        """Get set of masked record IDs for a dimension."""
        if dimension not in self.state:
            return set()
        return set(self.state[dimension])


def main():
    """CLI entry point."""
    import sys

    mgr = MaskManager()

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python mask_manager.py mask <dimension> <record_id>")
        print("  python mask_manager.py unmask <dimension> <record_id>")
        print("  python mask_manager.py list [dimension]")
        print("  python mask_manager.py reset")
        print("\nDimensions: units, advances, improvements, wonders, tileimps")
        return

    cmd = sys.argv[1]

    if cmd == "mask" and len(sys.argv) >= 4:
        dimension = sys.argv[2]
        record_id = sys.argv[3]
        mgr.mask(dimension, record_id)
    elif cmd == "unmask" and len(sys.argv) >= 4:
        dimension = sys.argv[2]
        record_id = sys.argv[3]
        mgr.unmask(dimension, record_id)
    elif cmd == "list":
        dimension = sys.argv[2] if len(sys.argv) >= 3 else None
        mgr.print_list(dimension)
    elif cmd == "reset":
        mgr.reset()
    else:
        print(f"Unknown command: {cmd}")


if __name__ == "__main__":
    main()
