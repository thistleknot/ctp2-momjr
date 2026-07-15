"""
diff_engine.py — Structural diff between baseline and modded game installations.

Supports two parsers:
  - 'ctp2': CTP2 block files (delegates to ctp2_roundtrip.py EAV parser)
  - 'civ2': CIV2 section-based files (RULES.TXT @SECTION format)

For each mod pair, produces per-file JSON diffs capturing:
  - blocks_added, blocks_removed, blocks_modified (field-level changes)
  - binary_added, binary_removed (presence-only for non-text files)

Usage:
  python diff_engine.py                  # runs all pairs in mod_pairs.json
  python diff_engine.py ctp2-ae-mom      # single pair by ID
  python diff_engine.py --list           # list configured pairs
"""
import json
import re
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
TOOLS = Path(__file__).parent
MOD_PAIRS_FILE = TOOLS / "mod_pairs.json"
DIFF_OUT = TOOLS / "diff_results"
sys.path.insert(0, str(TOOLS))

# ---------------------------------------------------------------------------
# CTP2 parser (delegates to existing round-trip parser)
# ---------------------------------------------------------------------------
TEXT_BINARY_EXTENSIONS = {
    ".tga", ".bmp", ".gif", ".spr", ".avi", ".wav", ".mp3",
    ".exe", ".dll", ".zip", ".rar", ".7z", ".ico",
}
TEXT_EXTENSIONS = {".txt", ".slc", ".tsv", ".csv", ".json", ".md"}


def _is_binary(path: Path) -> bool:
    return path.suffix.lower() in TEXT_BINARY_EXTENSIONS


def _parse_ctp2_blocks(text: str) -> dict[str, list]:
    """Return {block_id: [items]} using ctp2_roundtrip parser."""
    from ctp2_roundtrip import parse_file
    return parse_file(text)


def _eav_block(items) -> list[tuple[str, str, str]]:
    """Convert a list of ctp2_roundtrip items → list of (type, key, val)."""
    from ctp2_roundtrip import KV, Flag, SubList, Nested
    result = []
    for item in items:
        if isinstance(item, KV):
            result.append(("kv", item.key, item.val))
        elif isinstance(item, Flag):
            result.append(("flag", item.name, ""))
        elif isinstance(item, SubList):
            result.append(("sublist", item.key, item.val))
        elif isinstance(item, Nested):
            result.append(("nested", item.name, ""))
    return result


def diff_ctp2_file(baseline_text: str, mod_text: str) -> dict[str, Any]:
    """Structural block-level diff between two CTP2 block files."""
    base_blocks = _parse_ctp2_blocks(baseline_text)
    mod_blocks  = _parse_ctp2_blocks(mod_text)

    base_ids = set(base_blocks)
    mod_ids  = set(mod_blocks)

    added   = sorted(mod_ids  - base_ids)
    removed = sorted(base_ids - mod_ids)
    common  = base_ids & mod_ids

    modified = []
    for bid in sorted(common):
        base_eav = _eav_block(base_blocks[bid])
        mod_eav  = _eav_block(mod_blocks[bid])
        if base_eav == mod_eav:
            continue
        base_set = set(base_eav)
        mod_set  = set(mod_eav)
        fields_added   = sorted(mod_set  - base_set)
        fields_removed = sorted(base_set - mod_set)
        modified.append({
            "block_id":       bid,
            "fields_added":   fields_added,
            "fields_removed": fields_removed,
        })

    # Include field data for added blocks so the registry can build entity recipes
    added_data = {bid: _eav_block(mod_blocks[bid]) for bid in added}

    return {
        "parser": "ctp2",
        "summary": {
            "blocks_added":    len(added),
            "blocks_removed":  len(removed),
            "blocks_modified": len(modified),
        },
        "blocks_added":      added,
        "blocks_added_data": added_data,
        "blocks_removed":    removed,
        "blocks_modified":   modified,
    }


# ---------------------------------------------------------------------------
# CIV2 parser — RULES.TXT @SECTION format
# ---------------------------------------------------------------------------

# Column schemas for known sections (name → column headers).
# Partial — just enough to give field names; remaining columns are 'col_N'.
_CIV2_SCHEMAS: dict[str, list[str]] = {
    "@UNITS": [
        "name", "moves", "range", "sea_support", "attack", "defense",
        "firepower", "cost", "tech_prereq", "obsolete_by", "unique",
        "phalanx", "slider", "domain", "air_defense",
    ],
    "@IMPROVE": [
        "name", "cost", "maintenance", "tech_prereq", "science",
        "tax", "luxury", "happiness", "culture",
    ],
    "@ADVANCE": [
        "name", "ai_value", "prereq1", "prereq2", "prereq3",
    ],
    "@TERRAIN": [
        "name", "move_cost", "defense_bonus", "food", "shields", "trade",
        "irrigation_result", "mining_result",
    ],
    "@GOVERNMENTS": [
        "name", "title_male", "title_female",
    ],
    "@LEADERS": [
        "leader_name", "civilization_name", "adjective",
    ],
}


def _parse_civ2_rules(text: str) -> dict[str, list[dict[str, str]]]:
    """
    Parse CIV2 RULES.TXT into {section_name: [row_dict, ...]}.
    Sections begin with '@SECTIONNAME' and continue until the next '@' line.
    Lines starting with ';' are comments. Blank lines skipped.
    Each data line is comma-separated; columns named from _CIV2_SCHEMAS.
    """
    sections: dict[str, list[dict[str, str]]] = {}
    current_section = None
    current_rows: list[dict[str, str]] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith("@"):
            # Save previous section
            if current_section is not None:
                sections[current_section] = current_rows
            current_section = line.split()[0].upper()
            current_rows = []
            continue
        if current_section is None:
            continue

        # Data line — strip inline comment
        if ";" in line:
            line = line[:line.index(";")].rstrip()

        parts = [p.strip() for p in line.split(",")]
        headers = _CIV2_SCHEMAS.get(current_section, [])
        row: dict[str, str] = {}
        for i, val in enumerate(parts):
            key = headers[i] if i < len(headers) else f"col_{i}"
            row[key] = val
        current_rows.append(row)

    if current_section is not None:
        sections[current_section] = current_rows

    return sections


def _parse_civ2_pedia(text: str) -> dict[str, str]:
    """
    Parse PEDIA.TXT into {entry_name: body_text}.
    Entries begin with a bare name line (no spaces, no comma) followed by
    a body that ends at the next entry name or EOF.
    """
    entries: dict[str, str] = {}
    entry_re = re.compile(r'^([A-Z][A-Z0-9_]{2,})\s*$', re.MULTILINE)
    matches = list(entry_re.finditer(text))
    for i, m in enumerate(matches):
        name = m.group(1)
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        entries[name] = text[body_start:body_end].strip()
    return entries


def diff_civ2_file(filename: str, baseline_text: str, mod_text: str) -> dict[str, Any]:
    """Structural diff for a CIV2 text file."""
    fname_upper = filename.upper()

    if fname_upper == "RULES.TXT":
        base_parsed = _parse_civ2_rules(baseline_text)
        mod_parsed  = _parse_civ2_rules(mod_text)
        return _diff_civ2_rules(base_parsed, mod_parsed)

    if fname_upper == "PEDIA.TXT":
        base_parsed = _parse_civ2_pedia(baseline_text)
        mod_parsed  = _parse_civ2_pedia(mod_text)
        return _diff_civ2_keyed(base_parsed, mod_parsed, "pedia_entry")

    # Generic line-level diff for other text files
    return _diff_raw_lines(baseline_text, mod_text)


def _diff_civ2_rules(
    base: dict[str, list[dict[str, str]]],
    mod: dict[str, list[dict[str, str]]],
) -> dict[str, Any]:
    """Diff two RULES.TXT section dictionaries."""
    all_sections = sorted(set(base) | set(mod))
    section_diffs: list[dict] = []

    for sec in all_sections:
        base_rows = base.get(sec, [])
        mod_rows  = mod.get(sec, [])
        if base_rows == mod_rows:
            continue

        # Use 'name' field as key when available; fall back to index
        def _keyed(rows):
            out = {}
            for i, row in enumerate(rows):
                key = row.get("name") or str(i)
                out[key] = row
            return out

        bk = _keyed(base_rows)
        mk = _keyed(mod_rows)
        added   = sorted(set(mk) - set(bk))
        removed = sorted(set(bk) - set(mk))
        modified = []
        for k in sorted(set(bk) & set(mk)):
            if bk[k] != mk[k]:
                changed = [
                    (field, bk[k].get(field, ""), mk[k].get(field, ""))
                    for field in sorted(set(bk[k]) | set(mk[k]))
                    if bk[k].get(field) != mk[k].get(field)
                ]
                modified.append({"entry": k, "fields_changed": changed})

        section_diffs.append({
            "section":   sec,
            "added":     added,
            "removed":   removed,
            "modified":  modified,
            "added_data": [mk[k] for k in added],
        })

    total_added = sum(len(s["added"]) for s in section_diffs)
    total_removed = sum(len(s["removed"]) for s in section_diffs)
    total_modified = sum(len(s["modified"]) for s in section_diffs)

    return {
        "parser": "civ2_rules",
        "summary": {
            "sections_changed": len(section_diffs),
            "entries_added":    total_added,
            "entries_removed":  total_removed,
            "entries_modified": total_modified,
        },
        "sections": section_diffs,
    }


def _diff_civ2_keyed(
    base: dict[str, str],
    mod: dict[str, str],
    entry_type: str,
) -> dict[str, Any]:
    """Diff two key→text dictionaries (e.g., PEDIA entries)."""
    added   = sorted(set(mod) - set(base))
    removed = sorted(set(base) - set(mod))
    modified = sorted(k for k in set(base) & set(mod) if base[k] != mod[k])
    return {
        "parser": entry_type,
        "summary": {"added": len(added), "removed": len(removed), "modified": len(modified)},
        "added":   added,
        "removed": removed,
        "modified": modified,
    }


def _diff_raw_lines(base_text: str, mod_text: str) -> dict[str, Any]:
    """Line-level diff for files we can't parse structurally."""
    import difflib
    base_lines = base_text.splitlines()
    mod_lines  = mod_text.splitlines()
    added_lines   = [l for l in mod_lines  if l not in set(base_lines)]
    removed_lines = [l for l in base_lines if l not in set(mod_lines)]
    return {
        "parser": "raw_lines",
        "summary": {"lines_added": len(added_lines), "lines_removed": len(removed_lines)},
        "lines_added":   added_lines[:200],
        "lines_removed": removed_lines[:200],
    }


# ---------------------------------------------------------------------------
# File walker + diff runner
# ---------------------------------------------------------------------------

def _read_text(path: Path) -> str | None:
    for enc in ("utf-8", "windows-1252", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, PermissionError):
            continue
    return None


def run_pair(pair: dict) -> dict[str, Any]:
    """
    Run the full diff for one mod pair.
    Returns a summary dict; individual file diffs written to DIFF_OUT/<pair_id>/.
    """
    pair_id = pair["id"]
    parser  = pair["parser"]
    base_dir = Path(pair["baseline"])
    mod_dir  = Path(pair["mod"])

    if not base_dir.exists():
        print(f"  SKIP {pair_id}: baseline not found at {base_dir}")
        return {"pair_id": pair_id, "error": "baseline_missing"}
    if not mod_dir.exists():
        print(f"  SKIP {pair_id}: mod not found at {mod_dir}")
        return {"pair_id": pair_id, "error": "mod_missing"}

    out_dir = DIFF_OUT / pair_id
    out_dir.mkdir(parents=True, exist_ok=True)

    base_files = {f.relative_to(base_dir): f for f in base_dir.rglob("*") if f.is_file()}
    mod_files  = {f.relative_to(mod_dir):  f for f in mod_dir.rglob("*")  if f.is_file()}
    all_rels   = sorted(set(base_files) | set(mod_files))

    summary = {
        "pair_id":    pair_id,
        "parser":     parser,
        "baseline":   str(base_dir),
        "mod":        str(mod_dir),
        "files_total": len(all_rels),
        "files_binary_added":   0,
        "files_binary_removed": 0,
        "files_text_only_added": 0,
        "files_text_only_removed": 0,
        "files_diffed": 0,
        "files_unchanged": 0,
        "files_skipped": 0,
    }
    print(f"\n  [{pair_id}] {len(all_rels)} files total")

    for rel in all_rels:
        in_base = rel in base_files
        in_mod  = rel in mod_files

        if _is_binary(rel):
            if not in_base:
                summary["files_binary_added"] += 1
            elif not in_mod:
                summary["files_binary_removed"] += 1
            continue

        out_path = out_dir / (str(rel).replace("\\", "__").replace("/", "__") + ".json")

        if not in_base:
            summary["files_text_only_added"] += 1
            text = _read_text(mod_files[rel]) or ""
            result = {"status": "added_in_mod", "rel": str(rel), "line_count": len(text.splitlines())}
            out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
            continue

        if not in_mod:
            summary["files_text_only_removed"] += 1
            text = _read_text(base_files[rel]) or ""
            result = {"status": "removed_in_mod", "rel": str(rel), "line_count": len(text.splitlines())}
            out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
            continue

        base_text = _read_text(base_files[rel])
        mod_text  = _read_text(mod_files[rel])
        if base_text is None or mod_text is None:
            summary["files_skipped"] += 1
            continue

        if base_text == mod_text:
            summary["files_unchanged"] += 1
            continue

        # Structural diff
        try:
            if parser == "ctp2":
                diff = diff_ctp2_file(base_text, mod_text)
            elif parser == "civ2":
                diff = diff_civ2_file(rel.name, base_text, mod_text)
            else:
                diff = _diff_raw_lines(base_text, mod_text)
        except Exception as exc:
            diff = {"error": str(exc), "parser": parser}
            summary["files_skipped"] += 1

        result = {"status": "modified", "rel": str(rel), **diff}
        out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        summary["files_diffed"] += 1

    # Write pair summary
    summary_path = out_dir / "_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"  [{pair_id}] diffed={summary['files_diffed']} unchanged={summary['files_unchanged']} "
          f"added={summary['files_text_only_added']} removed={summary['files_text_only_removed']} "
          f"bin_added={summary['files_binary_added']} bin_removed={summary['files_binary_removed']} "
          f"skipped={summary['files_skipped']}")
    return summary


def run_all(pair_filter: str | None = None) -> list[dict]:
    config = json.loads(MOD_PAIRS_FILE.read_text(encoding="utf-8"))
    pairs = config["mod_pairs"]
    if pair_filter:
        pairs = [p for p in pairs if p["id"] == pair_filter]
        if not pairs:
            print(f"No pair with id '{pair_filter}' found.")
            print("Available:", [p["id"] for p in config["mod_pairs"]])
            return []
    DIFF_OUT.mkdir(parents=True, exist_ok=True)
    summaries = []
    for pair in pairs:
        s = run_pair(pair)
        summaries.append(s)
    return summaries


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--list" in args:
        config = json.loads(MOD_PAIRS_FILE.read_text(encoding="utf-8"))
        for p in config["mod_pairs"]:
            print(f"  {p['id']:30s}  {p.get('notes','')}")
        sys.exit(0)

    pair_id = args[0] if args else None
    summaries = run_all(pair_id)
    print(f"\nDone. {len(summaries)} pair(s) processed.")
