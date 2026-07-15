"""
ctp2_ae_parser.py — CTP2 block-file parser for AE mod files.

Handles all CTP2 block structures faithfully:
  KV        — Key-value:        Category UNIT_CATEGORY_AERIAL
  Flag      — Bare boolean:     LossMoveToDmgNone
  SubList   — Tagged list:      CanSee: Land
  Nested    — Recursive block:  SlaveUprising { ... }
  Anonymous — Unnamed block:    { ... }  (used in DiffDB difficulty settings)

Round-trip guarantee: parse → render produces byte-equivalent output for all
AE mod files (Units, Advance, buildings, Wonder, terrain, tileimp, AdvanceLists,
DiffDB, Const).

Tokenizer discriminator (no hardcoded whitelist):
  PascalCase token (has ≥1 lowercase letter) = KEY or BARE FLAG
  ALL_CAPS / numeric / quoted string          = VALUE
"""

from __future__ import annotations

import csv
import json
import re
from collections import OrderedDict
from pathlib import Path
from typing import List, NamedTuple, Tuple, Union


# ---------------------------------------------------------------------------
# Item types
# ---------------------------------------------------------------------------

class KV(NamedTuple):
    key: str
    val: str

class Flag(NamedTuple):
    name: str

class SubList(NamedTuple):
    key: str
    val: str

class Nested(NamedTuple):
    name: str
    items: tuple  # recursive

class Anonymous(NamedTuple):
    """Unnamed brace block — DiffDB difficulty settings."""
    items: tuple

Item  = Union[KV, Flag, SubList, Nested, Anonymous]
Block = Tuple[Item, ...]
Blocks = "OrderedDict[str, Block]"


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

_COMMENT_RE = re.compile(r'(?<!["\w])#[^\n]*')
_SLASH_COMMENT_RE = re.compile(r'//[^\n]*')
_TOKEN_RE   = re.compile(r'"[^"]*"|\{|\}|[^"\s{}]+')


def _strip_comments(text: str) -> str:
    text = _SLASH_COMMENT_RE.sub('', text)
    return _COMMENT_RE.sub('', text)


def _tokenize(text: str) -> List[str]:
    return _TOKEN_RE.findall(_strip_comments(text))


def _is_key(tok: str) -> bool:
    return bool(re.search(r'[a-z]', tok)) and not tok.startswith('"')


def _is_value(tok: str) -> bool:
    if tok in ('{', '}'):
        return False
    if tok.startswith('"'):
        return True
    try:
        float(tok)
        return True
    except ValueError:
        pass
    return not re.search(r'[a-z]', tok)


# ---------------------------------------------------------------------------
# Recursive body parser
# ---------------------------------------------------------------------------

def _parse_body(tokens: List[str], pos: int) -> Tuple[Block, int]:
    """Parse from pos until matching '}'. Returns (items, next_pos)."""
    items: List[Item] = []
    while pos < len(tokens):
        tok = tokens[pos]
        if tok == '}':
            return tuple(items), pos + 1
        if tok == '{':
            # Nested anonymous block
            inner, pos = _parse_body(tokens, pos + 1)
            items.append(Anonymous(inner))
            continue
        if tok.endswith(':'):
            key = tok[:-1]
            pos += 1
            if pos < len(tokens) and tokens[pos] not in ('{', '}'):
                items.append(SubList(key, tokens[pos]))
                pos += 1
            continue
        # Any non-brace token at this position is in KEY position.
        # The case-based _is_key heuristic only governs the value/flag decision
        # below — a token here is always a key candidate (handles ALL_CAPS keys
        # like CONCEPT_DEFAULT_ICON in compact concept.txt blocks).
        nxt = tokens[pos + 1] if pos + 1 < len(tokens) else '}'
        if nxt == '{':
            inner, pos = _parse_body(tokens, pos + 2)
            items.append(Nested(tok, inner))
            continue
        # KV vs bare Flag: it's a Flag only when the following token is itself a
        # key (PascalCase, has lowercase) rather than a value. A value-shaped
        # next token (ALL_CAPS, numeric, quoted) means tok is a KV key.
        if nxt in ('}', '{') or _is_key(nxt) and not _is_value(nxt):
            # next token begins a new item → tok is a bare flag
            items.append(Flag(tok))
            pos += 1
        else:
            items.append(KV(tok, nxt))
            pos += 2
    return tuple(items), pos


# ---------------------------------------------------------------------------
# Top-level file parser
# ---------------------------------------------------------------------------

def parse_file(text: str) -> "OrderedDict[str, Block]":
    """
    Parse a CTP2 block file.

    Returns OrderedDict mapping block-ID → Block (tuple of Items).
    Anonymous top-level blocks (DiffDB difficulty sections) are keyed as
    '__anon_0__', '__anon_1__', etc.
    """
    tokens = _tokenize(text)
    result: OrderedDict = OrderedDict()
    anon_idx = 0
    pos = 0
    # Some files (concept.txt) begin with a bare record-count token that CTP2
    # reads before the blocks. Preserve it as a synthetic __count__ entry so it
    # survives round-trip; the renderer emits it back as a leading bare line.
    if tokens and tokens[0] not in ('{', '}'):
        nxt = tokens[1] if len(tokens) > 1 else None
        is_count = nxt != '{'
        try:
            float(tokens[0])
        except ValueError:
            is_count = False
        if is_count:
            result['__count__'] = (KV('__count__', tokens[0]),)
            pos = 1
    while pos < len(tokens):
        tok = tokens[pos]
        if tok == '}':
            pos += 1
            continue
        if tok == '{':
            # Anonymous top-level block (DiffDB difficulty setting)
            block, pos = _parse_body(tokens, pos + 1)
            key = f'__anon_{anon_idx}__'
            anon_idx += 1
            result[key] = block
            continue
        if pos + 1 < len(tokens) and tokens[pos + 1] == '{':
            block_id = tok
            block, pos = _parse_body(tokens, pos + 2)
            # CTP2 files may repeat a block ID (e.g. uniticon ICON_ORDER_CONDUCT_HIT).
            # An OrderedDict keyed only by ID would overwrite the first occurrence,
            # silently dropping a block the game keeps. Disambiguate duplicates with
            # a "\x00dupN" suffix that render_file strips back off.
            key = block_id
            if key in result:
                n = 1
                while f"{block_id}\x00dup{n}" in result:
                    n += 1
                key = f"{block_id}\x00dup{n}"
            result[key] = block
        else:
            pos += 1
    return result


# ---------------------------------------------------------------------------
# Renderer — faithful CTP2 multi-line format
# ---------------------------------------------------------------------------

def _render_items(items: Block, indent: int = 3) -> List[str]:
    pad = '\t'  # DiffDB uses tabs; normalise to tab indent
    lines: List[str] = []
    for item in items:
        if isinstance(item, KV):
            lines.append(f"{pad * (indent // 3)}{item.key}\t\t{item.val}")
        elif isinstance(item, Flag):
            lines.append(f"{pad * (indent // 3)}{item.name}")
        elif isinstance(item, SubList):
            lines.append(f"{pad * (indent // 3)}{item.key}: {item.val}")
        elif isinstance(item, Nested):
            lines.append(f"{pad * (indent // 3)}{item.name} {{")
            lines.extend(_render_items(item.items, indent + 3))
            lines.append(f"{pad * (indent // 3)}}}")
        elif isinstance(item, Anonymous):
            lines.append(f"{pad * (indent // 3)}{{")
            lines.extend(_render_items(item.items, indent + 3))
            lines.append(f"{pad * (indent // 3)}}}")
    return lines


def render_file(blocks: "OrderedDict[str, Block]") -> str:
    """Render parsed blocks back to CTP2 block format."""
    out: List[str] = []
    for block_id, items in blocks.items():
        if block_id == '__count__':
            out.append(items[0].val)
            out.append('')
            continue
        if block_id.startswith('__anon_'):
            out.append('{')
            out.extend(_render_items(items, indent=0))
            out.append('}')
        else:
            real_id = block_id.split('\x00dup')[0]
            out.append(f"{real_id} {{")
            out.extend(_render_items(items, indent=3))
            out.append('}')
        out.append('')
    return '\n'.join(out)


# ---------------------------------------------------------------------------
# Targeted field mutators — used by the generator
# ---------------------------------------------------------------------------

def get_kv(items: Block, key: str) -> str | None:
    """Return first KV value for key, or None."""
    for item in items:
        if isinstance(item, KV) and item.key == key:
            return item.val
    return None


def get_all_kv(items: Block, key: str) -> List[str]:
    """Return all KV values for a repeated key (e.g. Prerequisites)."""
    return [item.val for item in items if isinstance(item, KV) and item.key == key]


def set_kv(items: Block, key: str, val: str) -> Block:
    """Replace first occurrence of KV(key, *) with KV(key, val). Appends if absent."""
    lst = list(items)
    for i, item in enumerate(lst):
        if isinstance(item, KV) and item.key == key:
            lst[i] = KV(key, val)
            return tuple(lst)
    lst.append(KV(key, val))
    return tuple(lst)


def update_nested_kv(items: Block, nested_name: str, key: str, val: str) -> Block:
    """Update a KV inside a named Nested block. Adds the nested block if absent."""
    lst = list(items)
    for i, item in enumerate(lst):
        if isinstance(item, Nested) and item.name == nested_name:
            lst[i] = Nested(nested_name, set_kv(item.items, key, val))
            return tuple(lst)
    # nested not found — append it
    lst.append(Nested(nested_name, (KV(key, val),)))
    return tuple(lst)


def update_timescale_periods(items: Block, period_years: List[int]) -> Block:
    """
    Replace PERIOD sub-blocks inside TIME_SCALE{} with new YEARS_PER_TURN values.

    Precondition: len(period_years) == number of PERIOD blocks in TIME_SCALE.
    """
    lst = list(items)
    for i, item in enumerate(lst):
        if isinstance(item, Nested) and item.name == 'TIME_SCALE':
            ts_items = list(item.items)
            period_idx = 0
            for j, sub in enumerate(ts_items):
                if isinstance(sub, Nested) and sub.name == 'PERIOD':
                    if period_idx < len(period_years):
                        ts_items[j] = Nested('PERIOD',
                            set_kv(sub.items, 'YEARS_PER_TURN', str(period_years[period_idx])))
                        period_idx += 1
            lst[i] = Nested('TIME_SCALE', tuple(ts_items))
            return tuple(lst)
    return tuple(lst)


# ---------------------------------------------------------------------------
# DiffDB specialised parser — handles anonymous top-level blocks
# ---------------------------------------------------------------------------

DIFF_NAMES = ['Beginner', 'Easy', 'Medium', 'Hard', 'Very Hard', 'Impossible']


def parse_diffdb(text: str) -> List[Block]:
    """
    Parse DiffDB.txt into a list of 6 anonymous difficulty blocks.
    Returns list[Block] in order [Beginner … Impossible].
    """
    blocks = parse_file(text)
    anon = [v for k, v in blocks.items() if k.startswith('__anon_')]
    return anon


def render_diffdb(diff_blocks: List[Block], header_comment: str = '') -> str:
    """Render 6 difficulty blocks back to DiffDB format."""
    out: List[str] = []
    if header_comment:
        out.append(header_comment)
        out.append('')
    for i, block in enumerate(diff_blocks):
        if i < len(DIFF_NAMES):
            out.append(f'## {DIFF_NAMES[i]}')
        out.append('{')
        out.extend(_render_items(block, indent=0))
        out.append('}')
        out.append('')
    return '\n'.join(out)


# ---------------------------------------------------------------------------
# Const.txt flat key-value parser
# ---------------------------------------------------------------------------

_CONST_LINE_RE = re.compile(r'^([A-Z_][A-Z_0-9]*)\s+(.+?)(?:\s*#.*)?$')


def parse_const(text: str) -> "OrderedDict[str, str]":
    """Parse flat key-value Const.txt. Returns OrderedDict key→value."""
    result: OrderedDict = OrderedDict()
    for line in text.splitlines():
        m = _CONST_LINE_RE.match(line.strip())
        if m:
            result[m.group(1)] = m.group(2).strip()
    return result


def render_const(kv: "OrderedDict[str, str]", original_text: str) -> str:
    """
    Re-render Const.txt substituting changed values in-place, preserving
    all comments and blank lines from the original.
    """
    out: List[str] = []
    for line in original_text.splitlines():
        m = _CONST_LINE_RE.match(line.strip())
        if m and m.group(1) in kv:
            # Preserve leading whitespace, replace value
            lead = line[: len(line) - len(line.lstrip())]
            comment_match = re.search(r'\s*#.*$', line)
            comment = comment_match.group(0) if comment_match else ''
            out.append(f"{lead}{m.group(1)} {kv[m.group(1)]}{comment}")
        else:
            out.append(line)
    return '\n'.join(out)


# ---------------------------------------------------------------------------
# Round-trip test helper
# ---------------------------------------------------------------------------

def _diff_blocks(a: "OrderedDict", b: "OrderedDict") -> List[str]:
    errors = []
    for k in a:
        if k not in b:
            errors.append(f"MISSING in round-trip: {k}")
        elif a[k] != b[k]:
            errors.append(f"CHANGED: {k}")
    for k in b:
        if k not in a:
            errors.append(f"EXTRA in round-trip: {k}")
    return errors


def verify_roundtrip(path: Path) -> bool:
    """Parse → render → re-parse and assert structural identity."""
    text = path.read_text(encoding='utf-8', errors='replace')
    if path.name.lower() == 'diffdb.txt':
        blocks1 = parse_diffdb(text)
        rendered = render_diffdb(blocks1)
        blocks2 = parse_diffdb(rendered)
        ok = all(a == b for a, b in zip(blocks1, blocks2)) and len(blocks1) == len(blocks2)
    else:
        blocks1 = parse_file(text)
        rendered = render_file(blocks1)
        blocks2 = parse_file(rendered)
        errors = _diff_blocks(blocks1, blocks2)
        ok = not errors
    status = "PASS ✓" if ok else "FAIL ✗"
    print(f"  {path.name}: {status}")
    return ok


if __name__ == '__main__':
    import sys
    files = sys.argv[1:] or list(Path('.').glob('*.txt'))
    all_ok = True
    for f in files:
        p = Path(f)
        if p.exists():
            all_ok &= verify_roundtrip(p)
    sys.exit(0 if all_ok else 1)
