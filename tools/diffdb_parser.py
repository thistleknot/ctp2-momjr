"""
diffdb_parser.py — Dedicated parser for CTP2 DiffDB.txt.

DiffDB uses ALL_CAPS identifiers as both keys and values, unlike normal block
files where PascalCase = key and ALL_CAPS = value. The 6 difficulty blocks are
anonymous (no block ID), delimited by bare { }.

Parse strategy:
  - Top-level: collect anonymous { } blocks as difficulty settings
  - Within each block: ALL_CAPS token followed by '{' → Nested
                       ALL_CAPS token followed by anything else → KV
                       Handles multi-value rows like: KEY VALUE VALUE VALUE
"""
from __future__ import annotations
import re
from typing import List, NamedTuple, Tuple
from ctp2_ae_parser import KV, Nested, _strip_comments, _tokenize, DIFF_NAMES


Block = Tuple


def _is_block_name(tok: str) -> bool:
    """Token could be a block/key name: ALL_CAPS or PascalCase, not purely numeric."""
    if not tok or tok in ('{', '}'):
        return False
    if tok.startswith('"'):
        return False
    try:
        float(tok)
        return False
    except ValueError:
        pass
    return bool(re.match(r'^[A-Za-z]', tok))


def _is_number(tok: str) -> bool:
    """True if tok parses as an int or float (a numeric value, not an identifier)."""
    try:
        float(tok)
        return True
    except ValueError:
        return False


def _parse_diffdb_body(tokens: List[str], pos: int) -> Tuple[tuple, int]:
    """Parse until matching '}'. Returns (items_tuple, next_pos)."""
    items = []
    while pos < len(tokens):
        tok = tokens[pos]
        if tok == '}':
            return tuple(items), pos + 1
        if tok == '{':
            # Nested anonymous (shouldn't happen in DiffDB body, but handle it)
            inner, pos = _parse_diffdb_body(tokens, pos + 1)
            items.append(Nested('__inner__', inner))
            continue
        if not _is_block_name(tok):
            pos += 1
            continue
        # Peek
        nxt = tokens[pos + 1] if pos + 1 < len(tokens) else '}'
        if nxt == '{':
            # Named nested block: TIME_SCALE { ... } or PERIOD { ... }
            inner, pos = _parse_diffdb_body(tokens, pos + 2)
            items.append(Nested(tok, inner))
            continue
        if nxt == '}':
            # Bare token at end of block — skip
            pos += 1
            continue
        # Collect values after this key. The first token after the key is always
        # a value (even if it is ALL_CAPS like BC_YEAR_FORMAT). Subsequent tokens
        # are additional values only when they look like numbers; an ALL_CAPS or
        # PascalCase token after at least one value begins the NEXT key.
        # This resolves the ambiguity where both key and value are ALL_CAPS
        # (e.g. NEGATIVE_YEAR_FORMAT BC_YEAR_FORMAT) which the game requires.
        pos += 1
        vals = []
        # first value is unconditional (if present and not a brace)
        if pos < len(tokens) and tokens[pos] not in ('{', '}'):
            vals.append(tokens[pos])
            pos += 1
            # additional values: only numeric tokens (multi-value rows like
            # AI_MIN_BEHIND_TECHNOLOGY_COST 1.0 1.0 1.0 1.0 1.0)
            while pos < len(tokens) and tokens[pos] not in ('{', '}') and _is_number(tokens[pos]):
                vals.append(tokens[pos])
                pos += 1
        if vals:
            items.append(KV(tok, ' '.join(vals)))
        else:
            # bare token with no value (rare) — keep as KV with empty value would
            # break the game; treat as a flag-like token preserved via KV("", ...) is wrong.
            # Emit nothing only if truly trailing; otherwise preserve as keyless is unsafe.
            # In practice DiffDB has no bare flags, so a valueless token is a parse error.
            pass
    return tuple(items), pos


def parse_diffdb(text: str) -> List[tuple]:
    """
    Parse DiffDB.txt into a list of 6 anonymous difficulty blocks.
    Returns list[tuple-of-items] in Beginner…Impossible order.
    """
    tokens = _tokenize(text)
    blocks = []
    pos = 0
    while pos < len(tokens):
        tok = tokens[pos]
        if tok == '{':
            block, pos = _parse_diffdb_body(tokens, pos + 1)
            blocks.append(block)
        else:
            pos += 1
    return blocks


def _render_diffdb_items(items: tuple, indent: int = 0) -> List[str]:
    tab = '\t' * indent if indent > 0 else ''
    lines = []
    for item in items:
        if isinstance(item, KV):
            # Pad key and value with tab for readability
            lines.append(f"{tab}{item.key}\t\t\t{item.val}")
        elif isinstance(item, Nested):
            if item.name == '__inner__':
                lines.append(f"{tab}{{")
                lines.extend(_render_diffdb_items(item.items, indent))
                lines.append(f"{tab}}}")
            else:
                lines.append(f"{tab}{item.name}{{")
                lines.extend(_render_diffdb_items(item.items, indent + 1))
                lines.append(f"{tab}}}")
    return lines


def render_diffdb(diff_blocks: List[tuple]) -> str:
    """Render 6 difficulty blocks to DiffDB.txt format."""
    DIFF_COMMENTS = ['Beginner', 'Easy', 'Medium', 'Hard', 'Very Hard', 'Impossible']
    out = ['## there must be 6 difficulty settings', '']
    for i, block in enumerate(diff_blocks):
        if i < len(DIFF_COMMENTS):
            out.append(f'## {DIFF_COMMENTS[i]}')
        out.append('{')
        out.extend(_render_diffdb_items(block, indent=0))
        out.append('}')
        out.append('')
    return '\n'.join(out)


def get_kv_diffdb(block: tuple, key: str) -> str | None:
    """Get first KV value for key in a difficulty block."""
    for item in block:
        if isinstance(item, KV) and item.key == key:
            return item.val
    return None


def set_kv_diffdb(block: tuple, key: str, val: str) -> tuple:
    """Replace or append KV in a difficulty block."""
    lst = list(block)
    for i, item in enumerate(lst):
        if isinstance(item, KV) and item.key == key:
            lst[i] = KV(key, val)
            return tuple(lst)
    lst.append(KV(key, val))
    return tuple(lst)


def set_period_ypt_diffdb(block: tuple, period_idx: int, ypt: int) -> tuple:
    """Set YEARS_PER_TURN for period_idx inside TIME_SCALE nested block."""
    lst = list(block)
    for i, item in enumerate(lst):
        if isinstance(item, Nested) and item.name == 'TIME_SCALE':
            ts = list(item.items)
            period_count = 0
            for j, sub in enumerate(ts):
                if isinstance(sub, Nested) and sub.name == 'PERIOD':
                    if period_count == period_idx:
                        from ctp2_ae_parser import set_kv
                        ts[j] = Nested('PERIOD', set_kv(sub.items, 'YEARS_PER_TURN', str(ypt)))
                        break
                    period_count += 1
            lst[i] = Nested('TIME_SCALE', tuple(ts))
            return tuple(lst)
    return tuple(lst)


def get_ypt_diffdb(block: tuple, period_idx: int) -> int | None:
    """Extract YEARS_PER_TURN for period_idx from TIME_SCALE."""
    for item in block:
        if isinstance(item, Nested) and item.name == 'TIME_SCALE':
            periods = [x for x in item.items if isinstance(x, Nested) and x.name == 'PERIOD']
            if period_idx < len(periods):
                from ctp2_ae_parser import get_kv
                v = get_kv(periods[period_idx].items, 'YEARS_PER_TURN')
                return int(v) if v else None
    return None


def verify_roundtrip(path) -> bool:
    """Parse → render → reparse and check structural identity."""
    from pathlib import Path
    text = Path(path).read_text(encoding='utf-8', errors='replace')
    b1 = parse_diffdb(text)
    rendered = render_diffdb(b1)
    b2 = parse_diffdb(rendered)
    ok = len(b1) == len(b2) == 6 and all(a == b for a, b in zip(b1, b2))
    print(f"  DiffDB.txt: {'PASS ✓' if ok else 'FAIL ✗'}  ({len(b1)} blocks)")
    if not ok:
        for i, (a, b) in enumerate(zip(b1, b2)):
            if a != b:
                print(f"  Block {i} differs:")
                print(f"    orig  len={len(a)}")
                print(f"    rtrip len={len(b)}")
    return ok
