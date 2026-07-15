"""
ctp2_line_codec.py — Faithful line-oriented codec for non-block CTP2 text files.

Some CTP2 files are not brace-block structured but are still fully parseable and
editable:

  flat-KV    Const.txt        e.g.  PERCENT_LAND 45 #40 how much is land
  string-db  gl_str.txt       e.g.  STR_KEY  "display text"
             scen_str.txt
             junk_str.txt

These were previously copied verbatim, which made them un-editable through the
control plane. That was wrong. This codec parses them into editable rows while
guaranteeing byte-exact reconstruction for any line whose value is unchanged.

Fidelity strategy
-----------------
Each source line becomes one CSV row carrying:
  line_seq   0-based line number (preserves order and blank lines)
  kind       RAW | KV | STR
  key        field key (KV/STR), "" for RAW
  value      editable value — bare token (KV) or unquoted text (STR)
  raw        the original line, verbatim

Reconstruction rule (per line):
  - RAW            → emit `raw` exactly
  - KV/STR, value unchanged vs the value re-extracted from `raw` → emit `raw` exactly
  - KV/STR, value changed → splice the new value into `raw` at the original value
                            span, preserving leading whitespace, key, separator
                            whitespace, and any trailing inline comment

Result: a file with no edits round-trips byte-for-byte. A file with edits keeps
original formatting everywhere except the single value spans that changed.

Failure modes
-------------
  - A line tagged KV/STR whose `raw` no longer contains a parseable value raises
    ValueError on build (corrupt CSV), rather than silently emitting garbage.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import List, NamedTuple, Optional, Tuple

LINE_HEADERS = ["line_seq", "kind", "key", "value", "raw"]

# flat-KV:  KEY  VALUE  [#comment | ##comment | ; comment]
#   key  = first token (letters/digits/underscore)
#   value spans from after the key-gap to before an inline comment or EOL
_KV_RE = re.compile(
    r'^(?P<lead>\s*)'
    r'(?P<key>[A-Za-z_][A-Za-z0-9_]*)'
    r'(?P<gap>\s+)'
    r'(?P<value>[^#;\s][^#;]*?)'
    r'(?P<trail>\s*(?:[#;].*)?)$'
)

# string-db:  KEY  "value"   (value is everything inside the first quote pair)
_STR_RE = re.compile(
    r'^(?P<lead>\s*)'
    r'(?P<key>[A-Za-z_][A-Za-z0-9_]*)'
    r'(?P<gap>\s+)'
    r'"(?P<value>.*)"'
    r'(?P<trail>\s*(?:[#;].*)?)$'
)


class Line(NamedTuple):
    line_seq: int
    kind: str            # RAW | KV | STR
    key: str
    value: str
    raw: str


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def detect_kind(text: str) -> Optional[str]:
    """
    Return 'flat_kv', 'string_db', or None (not a line file) by sampling lines.

    string_db wins if quoted KEY "value" lines dominate; flat_kv if bare KEY VALUE
    lines dominate. Comments/blank lines don't count toward either.
    """
    kv = strdb = 0
    for ln in text.splitlines():
        s = ln.strip()
        if not s or s.startswith("#") or s.startswith(";"):
            continue
        if _STR_RE.match(ln):
            strdb += 1
        elif _KV_RE.match(ln):
            kv += 1
    if strdb == 0 and kv == 0:
        return None
    return "string_db" if strdb >= kv else "flat_kv"


# ---------------------------------------------------------------------------
# Parse  →  rows
# ---------------------------------------------------------------------------

def parse_lines(text: str, kind: str) -> List[Line]:
    """Parse text into Line rows. `kind` is 'flat_kv' or 'string_db'."""
    pat = _STR_RE if kind == "string_db" else _KV_RE
    out_kind = "STR" if kind == "string_db" else "KV"
    rows: List[Line] = []
    # splitlines(keepends=False); we normalise to \n on output via raw storage.
    for i, raw in enumerate(text.split("\n")):
        m = pat.match(raw)
        if m:
            rows.append(Line(i, out_kind, m.group("key"), m.group("value"), raw))
        else:
            rows.append(Line(i, "RAW", "", "", raw))
    # Trailing newline handling: text.split keeps a final "" if text ended with \n
    return rows


# ---------------------------------------------------------------------------
# Rows  →  text  (line-preserving)
# ---------------------------------------------------------------------------

def _reextract_value(raw: str, kind: str) -> Optional[str]:
    pat = _STR_RE if kind == "STR" else _KV_RE
    m = pat.match(raw)
    return m.group("value") if m else None


def _splice_value(raw: str, kind: str, new_value: str) -> str:
    """Replace only the value span in `raw`, preserving everything else."""
    pat = _STR_RE if kind == "STR" else _KV_RE
    m = pat.match(raw)
    if not m:
        raise ValueError(f"cannot splice value into line: {raw!r}")
    if kind == "STR":
        return f'{m.group("lead")}{m.group("key")}{m.group("gap")}"{new_value}"{m.group("trail")}'
    return f'{m.group("lead")}{m.group("key")}{m.group("gap")}{new_value}{m.group("trail")}'


def render_lines(rows: List[Line]) -> str:
    rows = sorted(rows, key=lambda r: r.line_seq)
    out: List[str] = []
    for r in rows:
        if r.kind == "RAW":
            out.append(r.raw)
            continue
        original_value = _reextract_value(r.raw, r.kind)
        if original_value is None:
            raise ValueError(f"line {r.line_seq} tagged {r.kind} but raw has no value: {r.raw!r}")
        if r.value == original_value:
            out.append(r.raw)            # unchanged → byte-exact
        else:
            out.append(_splice_value(r.raw, r.kind, r.value))
    return "\n".join(out)


# ---------------------------------------------------------------------------
# CSV I/O
# ---------------------------------------------------------------------------

def export_line_csv(rows: List[Line], csv_path: Path) -> int:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LINE_HEADERS)
        w.writeheader()
        for r in rows:
            w.writerow(r._asdict())
    return len(rows)


def import_line_csv(csv_path: Path) -> List[Line]:
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = []
        for d in csv.DictReader(f):
            rows.append(Line(int(d["line_seq"]), d["kind"], d["key"],
                             d["value"], d["raw"]))
    return rows


# ---------------------------------------------------------------------------
# Round-trip verify
# ---------------------------------------------------------------------------

def verify_line_roundtrip(txt_path: Path) -> bool:
    text = txt_path.read_text(encoding="utf-8", errors="replace")
    kind = detect_kind(text)
    if kind is None:
        print(f"  {txt_path.name}: not a line file (skipped)")
        return True
    rows = parse_lines(text, kind)

    # through actual CSV
    import io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=LINE_HEADERS)
    w.writeheader()
    for r in rows:
        w.writerow(r._asdict())
    buf.seek(0)
    rows2 = [Line(int(d["line_seq"]), d["kind"], d["key"], d["value"], d["raw"])
             for d in csv.DictReader(buf)]
    rebuilt = render_lines(rows2)

    ok = rebuilt == text
    data_rows = sum(1 for r in rows if r.kind != "RAW")
    print(f"  {txt_path.name}: {'PASS ✓' if ok else 'FAIL ✗'}  "
          f"({kind}, {data_rows} editable rows)")
    if not ok:
        a, b = text.split("\n"), rebuilt.split("\n")
        for i, (x, y) in enumerate(zip(a, b)):
            if x != y:
                print(f"    line {i}: {x!r}\n          → {y!r}")
                break
    return ok


if __name__ == "__main__":
    import sys
    for f in sys.argv[1:]:
        p = Path(f)
        if p.exists():
            verify_line_roundtrip(p)
