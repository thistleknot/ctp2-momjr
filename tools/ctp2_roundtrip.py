"""
CTP2 block file round-trip parser and test harness.

MAP:    parse(Units.txt)  → export_csv(units_eav.csv)
REDUCE: import_csv(units_eav.csv) → render() → reconstructed Units.txt
TEST:   compare reconstructed parse-tree to original parse-tree

The parser handles all CTP2 block structures:
  - Bare boolean flags:     LossMoveToDmgNone
  - Key-value fields:       Category UNIT_CATEGORY_AERIAL
  - Sub-block list fields:  CanSee: Land  (colon syntax, repeatable)
  - Nested blocks:          SlaveUprising { Sound ... }
  - Multi-value keys:       Prerequisites ADVANCE_X  (same key, N times)

Tokenizer discriminator (no hardcoded whitelist needed):
  KEY / BARE-FLAG  ↔  token has at least one lowercase letter  (PascalCase)
  VALUE            ↔  ALL_CAPS (with or without underscores), quoted string,
                       or numeric literal

  When PascalCase token T is followed by VALUE → T is a KEY, next is its value.
  When PascalCase token T is followed by PascalCase or } → T is a BARE FLAG.
"""

import re
import csv
import json
import sys
import subprocess
from collections import OrderedDict
from pathlib import Path
from typing import List, Tuple, Union, NamedTuple


# ---------------------------------------------------------------------------
# Item types — one per CTP2 field structure
# ---------------------------------------------------------------------------

class KV(NamedTuple):
    """Simple key-value:   Category UNIT_CATEGORY_AERIAL"""
    key: str
    val: str


class Flag(NamedTuple):
    """Bare boolean flag:   LossMoveToDmgNone"""
    name: str


class SubList(NamedTuple):
    """Tag-list entry:      CanSee: Land    (key ends with colon in source)"""
    key: str
    val: str


class Nested(NamedTuple):
    """Nested brace block:  SlaveUprising { Sound ... }"""
    name: str
    items: tuple  # recursive; tuple so it's hashable / comparable


Item = Union[KV, Flag, SubList, Nested]
Block = Tuple[Item, ...]        # ordered, immutable for comparison
Blocks = "OrderedDict[str, Block]"


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

_COMMENT_RE = re.compile(r'(?<!["\w])#[^\n]*')
_TOKEN_RE   = re.compile(r'"[^"]*"|\{|\}|[^"\s{}]+')


def _strip_comments(text: str) -> str:
    return _COMMENT_RE.sub('', text)


def _tokenize(text: str) -> List[str]:
    return _TOKEN_RE.findall(_strip_comments(text))


def _is_key(tok: str) -> bool:
    """PascalCase: has at least one lowercase letter, not a quoted string."""
    return bool(re.search(r'[a-z]', tok)) and not tok.startswith('"')


def _is_value(tok: str) -> bool:
    """ALL_CAPS identifier, quoted string, or numeric literal."""
    if tok in ('{', '}'):
        return False
    if tok.startswith('"'):
        return True
    try:
        float(tok)
        return True
    except ValueError:
        pass
    return not re.search(r'[a-z]', tok)   # no lowercase  →  ALL_CAPS


# ---------------------------------------------------------------------------
# Recursive block body parser
# ---------------------------------------------------------------------------

def _parse_body(tokens: List[str], pos: int) -> Tuple[Block, int]:
    """Parse tokens from pos until matching '}'.  Returns (items, next_pos)."""
    items: List[Item] = []

    while pos < len(tokens):
        tok = tokens[pos]

        if tok == '}':
            return tuple(items), pos + 1

        if tok == '{':            # stray brace — skip
            pos += 1
            continue

        # Sub-block list entry:  CanSee: Land
        if tok.endswith(':'):
            key = tok[:-1]
            pos += 1
            if pos < len(tokens) and tokens[pos] not in ('{', '}'):
                items.append(SubList(key, tokens[pos]))
                pos += 1
            continue

        if not _is_key(tok):     # unexpected value-like token at key position
            pos += 1
            continue

        # Peek at next token
        nxt = tokens[pos + 1] if pos + 1 < len(tokens) else '}'

        if nxt == '{':
            # Nested block:  SlaveUprising { ... }
            inner, pos = _parse_body(tokens, pos + 2)
            items.append(Nested(tok, inner))
            continue

        if _is_value(nxt):
            # Key-value pair
            items.append(KV(tok, nxt))
            pos += 2
        else:
            # Bare flag (next token is another key or '}')
            items.append(Flag(tok))
            pos += 1

    return tuple(items), pos


# ---------------------------------------------------------------------------
# Top-level file parser
# ---------------------------------------------------------------------------

def parse_file(text: str) -> "OrderedDict[str, Block]":
    """Parse a CTP2 block file. Returns OrderedDict mapping block-ID → Block."""
    tokens = _tokenize(text)
    result: OrderedDict = OrderedDict()
    pos = 0
    while pos < len(tokens):
        tok = tokens[pos]
        if tok in ('{', '}'):
            pos += 1
            continue
        if pos + 1 < len(tokens) and tokens[pos + 1] == '{':
            block_id = tok
            block, pos = _parse_body(tokens, pos + 2)
            result[block_id] = block
        else:
            pos += 1
    return result


# ---------------------------------------------------------------------------
# Renderer — canonical multi-line CTP2 format
# ---------------------------------------------------------------------------

def _render_items(items: Block, indent: int = 3) -> List[str]:
    pad = ' ' * indent
    lines: List[str] = []
    for item in items:
        if isinstance(item, KV):
            lines.append(f"{pad}{item.key} {item.val}")
        elif isinstance(item, Flag):
            lines.append(f"{pad}{item.name}")
        elif isinstance(item, SubList):
            lines.append(f"{pad}{item.key}: {item.val}")
        elif isinstance(item, Nested):
            lines.append(f"{pad}{item.name} {{")
            lines.extend(_render_items(item.items, indent + 3))
            lines.append(f"{pad}}}")
    return lines


def render_file(blocks: "OrderedDict[str, Block]") -> str:
    """Render parsed blocks back to canonical CTP2 block format."""
    out: List[str] = []
    for block_id, items in blocks.items():
        out.append(f"{block_id} {{")
        out.extend(_render_items(items))
        out.append("}")
        out.append("")
    return '\n'.join(out)


# ---------------------------------------------------------------------------
# CSV export / import  (EAV: entity–attribute–value)
# ---------------------------------------------------------------------------

_CSV_FIELDS = ('block_id', 'seq', 'type', 'key', 'val')


def _flatten_items(block_id: str, items: Block, seq_start: int = 0,
                   prefix: str = '') -> List[dict]:
    rows: List[dict] = []
    seq = seq_start
    for item in items:
        bid = f"{block_id}{prefix}"
        if isinstance(item, KV):
            rows.append(dict(block_id=bid, seq=seq, type='kv',
                             key=item.key, val=item.val))
        elif isinstance(item, Flag):
            rows.append(dict(block_id=bid, seq=seq, type='flag',
                             key=item.name, val=''))
        elif isinstance(item, SubList):
            rows.append(dict(block_id=bid, seq=seq, type='sublist',
                             key=item.key, val=item.val))
        elif isinstance(item, Nested):
            # Encode nested items as JSON so one CSV row per nested block
            rows.append(dict(block_id=bid, seq=seq, type='nested',
                             key=item.name,
                             val=json.dumps(_items_to_json(item.items))))
        seq += 1
    return rows


def _items_to_json(items: Block) -> list:
    result = []
    for item in items:
        if isinstance(item, KV):
            result.append({'t': 'kv', 'k': item.key, 'v': item.val})
        elif isinstance(item, Flag):
            result.append({'t': 'flag', 'k': item.name})
        elif isinstance(item, SubList):
            result.append({'t': 'sublist', 'k': item.key, 'v': item.val})
        elif isinstance(item, Nested):
            result.append({'t': 'nested', 'k': item.name,
                           'v': _items_to_json(item.items)})
    return result


def _json_to_items(data: list) -> Block:
    items: List[Item] = []
    for entry in data:
        t = entry['t']
        if t == 'kv':
            items.append(KV(entry['k'], entry['v']))
        elif t == 'flag':
            items.append(Flag(entry['k']))
        elif t == 'sublist':
            items.append(SubList(entry['k'], entry['v']))
        elif t == 'nested':
            items.append(Nested(entry['k'], _json_to_items(entry['v'])))
    return tuple(items)


def export_csv(blocks: "OrderedDict[str, Block]", filepath: Path):
    """Export parsed blocks to EAV CSV."""
    rows: List[dict] = []
    for block_id, items in blocks.items():
        rows.extend(_flatten_items(block_id, items))
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=_CSV_FIELDS)
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def import_csv(filepath: Path) -> "OrderedDict[str, Block]":
    """Import EAV CSV back into parsed blocks."""
    raw: OrderedDict = OrderedDict()  # block_id → sorted list of (seq, item)
    with open(filepath, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            bid  = row['block_id']
            seq  = int(row['seq'])
            typ  = row['type']
            key  = row['key']
            val  = row['val']
            if bid not in raw:
                raw[bid] = []
            if typ == 'kv':
                raw[bid].append((seq, KV(key, val)))
            elif typ == 'flag':
                raw[bid].append((seq, Flag(key)))
            elif typ == 'sublist':
                raw[bid].append((seq, SubList(key, val)))
            elif typ == 'nested':
                raw[bid].append((seq, Nested(key, _json_to_items(json.loads(val)))))
    result: OrderedDict = OrderedDict()
    for bid, entries in raw.items():
        result[bid] = tuple(item for _, item in sorted(entries, key=lambda x: x[0]))
    return result


# ---------------------------------------------------------------------------
# Round-trip test
# ---------------------------------------------------------------------------

def _diff_blocks(a: "OrderedDict[str, Block]",
                 b: "OrderedDict[str, Block]") -> List[str]:
    """Return list of discrepancy messages between two parsed file dicts."""
    errors: List[str] = []
    a_ids = set(a)
    b_ids = set(b)

    for missing in sorted(a_ids - b_ids):
        errors.append(f"MISSING in round-trip: {missing}")
    for extra in sorted(b_ids - a_ids):
        errors.append(f"EXTRA in round-trip: {extra}")

    for bid in sorted(a_ids & b_ids):
        ai, bi = a[bid], b[bid]
        if ai != bi:
            errors.append(f"DIFF {bid}: {len(ai)} items → {len(bi)} items")
            for idx, (ia, ib) in enumerate(zip(ai, bi)):
                if ia != ib:
                    errors.append(f"  field[{idx}]: {ia!r} ≠ {ib!r}")
            if len(ai) != len(bi):
                extra = bi[len(ai):] if len(bi) > len(ai) else ai[len(bi):]
                errors.append(f"  trailing extra ({len(extra)}): {extra[:3]!r}…")
    return errors


def run_roundtrip(filepath: Path, verbose: bool = True,
                  csv_out: Path = None) -> bool:
    """
    Parse → render → re-parse → compare.
    Optionally also export/import through CSV (full map-reduce cycle).

    Returns True if round-trip is lossless.
    """
    text = filepath.read_text(encoding='utf-8', errors='replace')
    blocks1 = parse_file(text)

    if verbose:
        print(f"\n{'='*60}")
        print(f"File : {filepath.name}")
        print(f"Blocks parsed: {len(blocks1)}")

    # ---- text round-trip ----
    rendered = render_file(blocks1)
    blocks2 = parse_file(rendered)
    text_errors = _diff_blocks(blocks1, blocks2)

    if verbose:
        if text_errors:
            print(f"TEXT round-trip: FAIL ({len(text_errors)} diff(s))")
            for e in text_errors[:20]:
                print(f"  {e}")
        else:
            print(f"TEXT round-trip: PASS ✓")

    # ---- CSV map-reduce round-trip ----
    csv_errors: List[str] = []
    if csv_out:
        n_rows = export_csv(blocks1, csv_out)
        blocks3 = import_csv(csv_out)
        csv_errors = _diff_blocks(blocks1, blocks3)
        if verbose:
            print(f"CSV  round-trip: {'PASS ✓' if not csv_errors else f'FAIL ({len(csv_errors)} diff(s))'}")
            print(f"  Rows exported: {n_rows}")
            for e in csv_errors[:20]:
                print(f"  {e}")

    ok = not text_errors and not csv_errors
    if verbose:
        print(f"Result: {'PASS ✓' if ok else 'FAIL ✗'}")
    return ok


def run_roundtrip_text(label: str, text: str, verbose: bool = True,
                       csv_out: Path = None) -> bool:
    """
    Parse → render → re-parse → compare from an in-memory text payload.

    This is the archive-aware sibling of run_roundtrip(), used when reference
    mods are only available inside .zip or nested .7z -> .rar bundles.
    """
    blocks1 = parse_file(text)

    if verbose:
        print(f"\n{'='*60}")
        print(f"File : {label}")
        print(f"Blocks parsed: {len(blocks1)}")

    rendered = render_file(blocks1)
    blocks2 = parse_file(rendered)
    text_errors = _diff_blocks(blocks1, blocks2)

    if verbose:
        if text_errors:
            print(f"TEXT round-trip: FAIL ({len(text_errors)} diff(s))")
            for e in text_errors[:20]:
                print(f"  {e}")
        else:
            print("TEXT round-trip: PASS ✓")

    csv_errors: List[str] = []
    if csv_out:
        n_rows = export_csv(blocks1, csv_out)
        blocks3 = import_csv(csv_out)
        csv_errors = _diff_blocks(blocks1, blocks3)
        if verbose:
            print(f"CSV  round-trip: {'PASS ✓' if not csv_errors else f'FAIL ({len(csv_errors)} diff(s))'}")
            print(f"  Rows exported: {n_rows}")
            for e in csv_errors[:20]:
                print(f"  {e}")

    ok = not text_errors and not csv_errors
    if verbose:
        print(f"Result: {'PASS ✓' if ok else 'FAIL ✗'}")
    return ok


# ---------------------------------------------------------------------------
# Stats helper — shows bare-flag counts to validate discriminator
# ---------------------------------------------------------------------------

def _count_types(blocks: "OrderedDict[str, Block]") -> dict:
    counts = {'kv': 0, 'flag': 0, 'sublist': 0, 'nested': 0}
    for items in blocks.values():
        for item in items:
            if isinstance(item, KV):      counts['kv']      += 1
            elif isinstance(item, Flag):  counts['flag']    += 1
            elif isinstance(item, SubList): counts['sublist'] += 1
            elif isinstance(item, Nested):  counts['nested']  += 1
    return counts


def _read_text(path: Path) -> str:
    return path.read_text(encoding='utf-8', errors='replace')


def _read_zip_entry(zip_path: Path, member: str) -> str:
    result = subprocess.run(
        ['tar', '-xOf', str(zip_path), member],
        capture_output=True,
        check=True,
    )
    return result.stdout.decode('utf-8', errors='replace')


def _read_nested_archive_entry(outer_archive: Path, inner_member: str, nested_member: str) -> str:
    outer = subprocess.run(
        ['tar', '-xOf', str(outer_archive), inner_member],
        capture_output=True,
        check=True,
    )
    inner_path = Path(__file__).parent / f"_{Path(inner_member).name}"
    inner_path.write_bytes(outer.stdout)
    try:
        nested = subprocess.run(
            ['tar', '-xOf', str(inner_path), nested_member],
            capture_output=True,
            check=True,
        )
        return nested.stdout.decode('utf-8', errors='replace')
    finally:
        inner_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    # Default test targets — override via argv
    AE   = Path(r"H:\Games\ctp2\2025-01-20.CTP2.ApolytonEdition"
                r"\2025-01-20.CTP2.ApolytonEdition\Scenarios\AE_Mod"
                r"\scen0000\default\gamedata")
    AOM  = Path(r"H:\Games\ctp2\Ages of Man-20260424T030047Z-3-001"
                r"\Ages of Man\IV\AOMIV.zip")
    CRADLE = Path(r"H:\Games\ctp2\Cradle of Civilization-20260424T030028Z-3-001"
                  r"\Cradle of Civilization\IV\cradle.7z")
    OUT  = Path(__file__).parent / "roundtrip_csv"
    OUT.mkdir(exist_ok=True)

    targets = [
        ("ae_units", _read_text(AE / "Units.txt"), OUT / "ae_units_eav.csv"),
        ("ae_advance", _read_text(AE / "Advance.txt"), OUT / "ae_advance_eav.csv"),
        ("ae_uniticon", _read_text(AE / "uniticon.txt"), OUT / "ae_uniticon_eav.csv"),
        ("aom_units", _read_zip_entry(AOM, "AOM_IV/ctp2_data/default/gamedata/AOM_Units.txt"), OUT / "aom_units_eav.csv"),
        ("aom_advance", _read_zip_entry(AOM, "AOM_IV/ctp2_data/default/gamedata/AOM_Advance.txt"), OUT / "aom_advance_eav.csv"),
        ("aom_uniticon", _read_zip_entry(AOM, "AOM_IV/ctp2_data/default/gamedata/AOM_uniticon.txt"), OUT / "aom_uniticon_eav.csv"),
        (
            "cradle_units",
            _read_nested_archive_entry(
                CRADLE,
                "Cradle_IV_scen_04_20_13.rar",
                "Call To Power 2/ctp2_data/default/gamedata/A5_MONGOL_Units.txt",
            ),
            OUT / "cradle_units_eav.csv",
        ),
        (
            "cradle_advance",
            _read_nested_archive_entry(
                CRADLE,
                "Cradle_IV_scen_04_20_13.rar",
                "Call To Power 2/ctp2_data/default/gamedata/A5_MONGOL_Advance.txt",
            ),
            OUT / "cradle_advance_eav.csv",
        ),
        (
            "cradle_uniticon",
            _read_nested_archive_entry(
                CRADLE,
                "Cradle_IV_scen_04_20_13.rar",
                "Call To Power 2/ctp2_data/default/gamedata/A5_MONGOL_uniticon.txt",
            ),
            OUT / "cradle_uniticon_eav.csv",
        ),
    ]

    results = []
    for label, text, csv_path in targets:
        ok = run_roundtrip_text(label, text, verbose=True, csv_out=csv_path)
        # Show item-type distribution to verify bare-flag detection
        blocks = parse_file(text)
        counts = _count_types(blocks)
        print(f"  Item types: {counts}")
        results.append((label, ok))

    print(f"\n{'='*60}")
    print("SUMMARY")
    for name, ok in results:
        status = "PASS ✓" if ok else "FAIL ✗"
        print(f"  {status}  {name}")

    all_pass = all(ok for _, ok in results)
    sys.exit(0 if all_pass else 1)
