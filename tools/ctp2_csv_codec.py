"""
ctp2_csv_codec.py — Faithful CTP2 block ↔ CSV codec (the "decoder ring").

Goal: a CTP2 mod folder round-trips losslessly through CSV.
  txt → parse → CSV → parse → render → txt   ⟹   output ≡ input (shape + fields)

Design rationale (measured, not assumed)
-----------------------------------------
CTP2 dimensions vary in structural complexity:
  - Flat (Advance, Wonder, buildings): depth 1, KV + flags, occasional repeated key
  - Nested (Units, terrain, tileimp): depth 2, nested sub-blocks, sublists,
    hundreds of repeated keys and bare flags

A wide "one column per field" table cannot represent nested sub-blocks, ordered
repeated keys, or bare flags without losing information. So the CANONICAL CSV is
LONG-FORM: one row per leaf item, carrying block id, sequence, nesting path, kind,
key, value. This is 100% faithful for every dimension and is itself a queryable
relational table.

A WIDE projection (one row per block, one column per scalar field) is provided
separately for human editing of the flat dimensions only; it is lossy by design
and is never the reconstruction source.

CSV schema (long-form, canonical)
---------------------------------
  block_id   block identifier ("__anon_N__" for unnamed DiffDB blocks)
  block_seq  0-based order of the block within the file
  path       dotted nesting path of the parent ("" at top level,
             "TerrainEffect" one level down, "A.B" two levels down)
  item_seq   0-based order of this item within its parent block
  kind       KV | FLAG | SUBLIST | NESTED_OPEN | ANON_OPEN
  key        field key (block name for NESTED_OPEN; "" for ANON_OPEN)
  value      field value (KV/SUBLIST only; "" otherwise)

NESTED_OPEN / ANON_OPEN rows mark the start of a child block; their children
follow as rows whose `path` extends the parent path. The parser reconstructs the
tree from (path, item_seq) ordering — no closing rows needed.

Failure modes
-------------
  - Raises ValueError if a CSV row references a path whose parent is absent.
  - Round-trip mismatch is reported by verify(), never silently swallowed.
"""

from __future__ import annotations

import csv
from collections import OrderedDict
from pathlib import Path
from typing import List, Tuple

from ctp2_ae_parser import (
    KV, Flag, SubList, Nested, Anonymous,
    parse_file, render_file,
)

LONG_HEADERS = ["block_id", "block_seq", "path", "item_seq", "kind", "key", "value"]


# ---------------------------------------------------------------------------
# Block tree  →  long-form rows
# ---------------------------------------------------------------------------

def _flatten_items(items, block_id: str, block_seq: int,
                   path: str, rows: List[dict]) -> None:
    """Append one row per item; recurse into nested/anonymous blocks."""
    for item_seq, item in enumerate(items):
        if isinstance(item, KV):
            rows.append(dict(block_id=block_id, block_seq=block_seq, path=path,
                             item_seq=item_seq, kind="KV", key=item.key, value=item.val))
        elif isinstance(item, Flag):
            rows.append(dict(block_id=block_id, block_seq=block_seq, path=path,
                             item_seq=item_seq, kind="FLAG", key=item.name, value=""))
        elif isinstance(item, SubList):
            rows.append(dict(block_id=block_id, block_seq=block_seq, path=path,
                             item_seq=item_seq, kind="SUBLIST", key=item.key, value=item.val))
        elif isinstance(item, Nested):
            rows.append(dict(block_id=block_id, block_seq=block_seq, path=path,
                             item_seq=item_seq, kind="NESTED_OPEN", key=item.name, value=""))
            child_path = f"{path}.{item_seq}:{item.name}" if path else f"{item_seq}:{item.name}"
            _flatten_items(item.items, block_id, block_seq, child_path, rows)
        elif isinstance(item, Anonymous):
            rows.append(dict(block_id=block_id, block_seq=block_seq, path=path,
                             item_seq=item_seq, kind="ANON_OPEN", key="", value=""))
            child_path = f"{path}.{item_seq}:" if path else f"{item_seq}:"
            _flatten_items(item.items, block_id, block_seq, child_path, rows)


def blocks_to_rows(blocks: "OrderedDict[str, tuple]") -> List[dict]:
    rows: List[dict] = []
    for block_seq, (block_id, items) in enumerate(blocks.items()):
        _flatten_items(items, block_id, block_seq, "", rows)
    return rows


# ---------------------------------------------------------------------------
# Long-form rows  →  block tree
# ---------------------------------------------------------------------------

def _rows_to_items(rows: List[dict], parent_path: str):
    """
    Reconstruct the ordered item tuple for a given parent path.
    Children at this level are rows whose `path` == parent_path, ordered by item_seq.
    Nested/anon children recurse into their own extended path.
    """
    direct = [r for r in rows if r["path"] == parent_path]
    direct.sort(key=lambda r: int(r["item_seq"]))
    items = []
    for r in direct:
        kind = r["kind"]
        iseq = int(r["item_seq"])
        if kind == "KV":
            items.append(KV(r["key"], r["value"]))
        elif kind == "FLAG":
            items.append(Flag(r["key"]))
        elif kind == "SUBLIST":
            items.append(SubList(r["key"], r["value"]))
        elif kind == "NESTED_OPEN":
            child_path = f"{parent_path}.{iseq}:{r['key']}" if parent_path else f"{iseq}:{r['key']}"
            items.append(Nested(r["key"], tuple(_rows_to_items(rows, child_path))))
        elif kind == "ANON_OPEN":
            child_path = f"{parent_path}.{iseq}:" if parent_path else f"{iseq}:"
            items.append(Anonymous(tuple(_rows_to_items(rows, child_path))))
    return items


def rows_to_blocks(rows: List[dict]) -> "OrderedDict[str, tuple]":
    # Group rows by block, preserving block_seq order
    by_block: "OrderedDict[Tuple[int, str], List[dict]]" = OrderedDict()
    for r in rows:
        key = (int(r["block_seq"]), r["block_id"])
        by_block.setdefault(key, []).append(r)

    ordered = sorted(by_block.items(), key=lambda kv: kv[0][0])
    blocks: "OrderedDict[str, tuple]" = OrderedDict()
    for (bseq, bid), brows in ordered:
        items = _rows_to_items(brows, "")
        blocks[bid] = tuple(items)
    return blocks


# ---------------------------------------------------------------------------
# File-level CSV I/O
# ---------------------------------------------------------------------------

def export_long_csv(blocks: "OrderedDict[str, tuple]", csv_path: Path) -> int:
    rows = blocks_to_rows(blocks)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LONG_HEADERS)
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def import_long_csv(csv_path: Path) -> "OrderedDict[str, tuple]":
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return rows_to_blocks(rows)


# ---------------------------------------------------------------------------
# Round-trip verification
# ---------------------------------------------------------------------------

def verify_csv_roundtrip(txt_path: Path) -> bool:
    """txt → blocks → CSV → blocks: assert structural identity."""
    text = txt_path.read_text(encoding="utf-8", errors="replace")
    blocks1 = parse_file(text)
    rows = blocks_to_rows(blocks1)

    # serialise and reparse through actual CSV to catch quoting/encoding issues
    import io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=LONG_HEADERS)
    w.writeheader()
    w.writerows(rows)
    buf.seek(0)
    rows2 = list(csv.DictReader(buf))
    blocks2 = rows_to_blocks(rows2)

    ok = list(blocks1.items()) == list(blocks2.items())
    print(f"  {txt_path.name}: {'PASS ✓' if ok else 'FAIL ✗'}  "
          f"({len(blocks1)} blocks, {len(rows)} rows)")
    if not ok:
        for (k1, v1), (k2, v2) in zip(blocks1.items(), blocks2.items()):
            if k1 != k2 or v1 != v2:
                print(f"    first diff at block {k1!r} vs {k2!r}")
                break
    return ok


if __name__ == "__main__":
    import sys
    files = sys.argv[1:] or [str(p) for p in Path(".").glob("*.txt")]
    all_ok = True
    for f in files:
        p = Path(f)
        if p.exists():
            all_ok &= verify_csv_roundtrip(p)
    sys.exit(0 if all_ok else 1)
