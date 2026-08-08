"""Shared utilities for wiki_import extractors.

All extractors use these functions for consistent parsing, furniture stripping,
and CSV emission.
"""
import json
import re
from pathlib import Path

WIKI_PATH = Path(r"F:\Documents\wiki\games\mom\site\index.json")
WIKI_DIR = WIKI_PATH.parent
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "momjr_csv"

# Pre-compiled patterns for wiki furniture stripping
_FURNITURE_PATTERNS = [
    # Category/navigation chrome
    re.compile(r"^Categories?:.*$", re.M),
    re.compile(r"^Navigation.*$", re.M),
    re.compile(r"^Main Page.*$", re.M),
    # "Research Required" banners
    re.compile(r"Research Required[:\s]*\d+\s*RP", re.I),
    # Table of contents
    re.compile(r"^Contents\s*\[.*?\].*$", re.M),
    re.compile(r"^\d+(\.\d+)*\s+(Overview|Description|Strategy|Acquisition).*$", re.M),
    # Wiki edit links
    re.compile(r"\[edit\]", re.I),
]


def load_corpus() -> list[dict]:
    """Load the wiki corpus. Returns list of {t, s, x} dicts."""
    return json.loads(WIKI_PATH.read_text(encoding="utf-8"))


def strip_furniture(text: str) -> str:
    """Remove wiki navigation chrome, banners, and edit links from article text.

    Guarantee: idempotent — stripping twice produces the same result.
    """
    for pat in _FURNITURE_PATTERNS:
        text = pat.sub("", text)
    # Collapse multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def sanitize_ident(name: str) -> str:
    """Convert a display name to a CTP2-safe identifier component.

    'Fire Bolt' -> 'FIRE_BOLT'
    'Phantom Warriors' -> 'PHANTOM_WARRIORS'
    """
    s = name.upper().strip()
    s = re.sub(r"[^A-Z0-9]+", "_", s)
    s = s.strip("_")
    return s


def extract_number(text: str, label: str) -> int | None:
    """Extract a labeled integer from wiki text.

    Looks for patterns like 'Casting Cost: 50' or 'Cost: 100 MP'
    """
    patterns = [
        re.compile(rf"{label}\s*[:=]\s*(\d+)", re.I),
        re.compile(rf"{label}\s+(\d+)", re.I),
    ]
    for pat in patterns:
        m = pat.search(text)
        if m:
            return int(m.group(1))
    return None


def extract_field(text: str, label: str) -> str | None:
    """Extract a labeled string value from wiki text.

    Looks for 'Label: Value' or 'Label  Value' patterns.
    Returns the value portion trimmed.
    """
    pat = re.compile(rf"{label}\s*[:=]\s*(.+?)(?:\n|$)", re.I)
    m = pat.search(text)
    if m:
        return m.group(1).strip()
    return None
