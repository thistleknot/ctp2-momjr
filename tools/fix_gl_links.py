#!/usr/bin/env python
"""fix_gl_links.py — neutralize dangling Great Library cross-reference links.

CTP2 validates every Great Library <L:DATABASE_<TYPE>,<TOKEN>> hyperlink against the
named database at load and hard-errors ("X not found in <Y> database") on the first
token that isn't defined. The base AE Great Library references many base/WAW entities
that the MoM scenario doesn't include. Per dimension_inventory.md (never delete to
hide; base fallback), the correct repair for a link to an entity that genuinely does
not exist in this mod is to strip the link wrapper, keeping the display text.

Driven entirely by the actual DB files (the parser's source of truth), across ALL 10
dimensions, in one pass — so it can't miss a class the way launch-by-launch does.

Usage: python fix_gl_links.py            # report + fix
       python fix_gl_links.py --check    # report only
"""
import re, sys, pathlib

GD = pathlib.Path("../scen0000/default/gamedata")
ENG = pathlib.Path("../scen0000/english/gamedata")

# DATABASE_<TYPE> -> (db files, id prefix)
DIMS = {
    "ADVANCES":          (["Advance.txt"], "ADVANCE_"),
    "UNITS":             (["Units.txt"], "UNIT_"),
    "BUILDINGS":         (["Improve.txt", "buildings.txt"], "IMPROVE_"),
    "WONDERS":           (["Wonder.txt"], "WONDER_"),
    "TERRAIN":           (["terrain.txt"], "TERRAIN_"),
    "GOVERNMENTS":       (["govern.txt"], "GOVERNMENT_"),
    "TILE_IMPROVEMENTS": (["tileimp.txt"], "TILEIMP_"),
    "CONCEPTS":          (["concept.txt"], "CONCEPT_"),
    "ORDERS":            (["Orders.txt"], "ORDER_"),
    "RESOURCE":          (["goods.txt"], "GOOD_"),
}


def defined_ids(files, pfx):
    s = set()
    for f in files:
        p = GD / f
        if p.exists():
            s |= set(re.findall(r"^(" + pfx + r"[A-Z0-9_]+)\s*\{",
                                p.read_text(encoding="latin-1"), re.M))
    return s


def main():
    check_only = "--check" in sys.argv
    valid = {t: defined_ids(f, p) for t, (f, p) in DIMS.items()}
    total = 0
    for glname in ("Great_Library.txt", "WAW_Great_Library.txt"):
        p = ENG / glname
        if not p.exists():
            continue
        text = p.read_text(encoding="latin-1")
        per_file = 0

        def repl(m):
            nonlocal per_file
            dbtype, token, display = m.group(1), m.group(2), m.group(3)
            if dbtype in valid and token not in valid[dbtype]:
                per_file += 1
                return display  # strip the dead link, keep the words
            return m.group(0)

        new = re.sub(r"<L:DATABASE_([A-Z_]+),([A-Z0-9_]+)>(.*?)<e>", repl, text)
        total += per_file
        print(f"  {glname}: {per_file} dangling link(s) "
              + ("would be" if check_only else "") + " neutralized")
        if per_file and not check_only:
            p.write_text(new, encoding="latin-1")
    print(f"TOTAL: {total} dangling GL link(s)" + ("" if check_only else " fixed"))
    return 1 if (check_only and total) else 0


if __name__ == "__main__":
    raise SystemExit(main())
