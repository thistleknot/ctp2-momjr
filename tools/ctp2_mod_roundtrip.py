"""
ctp2_mod_roundtrip.py — Faithful CTP2 mod ↔ CSV control plane.

Round-trips an entire CTP2 mod folder through a CSV control plane:

    extract:  <mod>/**/*.txt  →  <csv_dir>/<file>.csv   (one long-form CSV per file)
    build:    <csv_dir>/*.csv  →  <out_mod>/**/*.txt      (reconstructed mod folder)
    verify:   parse(original) == parse(reconstructed)      per file, field-for-field

Success criterion (the load-bearing test): a mod extracted then rebuilt must match
the original in shape (same files, same blocks, same order) and field contents
(every KV / flag / sublist / nested value preserved). Files the codec cannot
round-trip are copied verbatim so the output mod is always complete and playable.

Block files (parsed via the codec):
    Advance Wonder buildings Units terrain tileimp AdvanceLists concept risks
    Improve govern goods Orders   — any *.txt that parses to ≥1 non-empty block
DiffDB.txt is handled by the dedicated diffdb_parser.
Everything else (gl_str, Great_Library, civilisation, *.bmp, *.tga, scenario.txt …)
is copied verbatim — it is not block-structured.

Usage
-----
    python ctp2_mod_roundtrip.py extract --mod <scen0000> --csv-dir <dir>
    python ctp2_mod_roundtrip.py build   --csv-dir <dir>  --out <new_scen0000> --mod <scen0000>
    python ctp2_mod_roundtrip.py verify  --mod <scen0000> --out <new_scen0000>
    python ctp2_mod_roundtrip.py roundtrip --mod <scen0000> --out <new_scen0000> [--csv-dir <dir>]

`roundtrip` runs extract → build → verify in one shot and reports per-file fidelity.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from collections import OrderedDict
from pathlib import Path
from typing import List, Tuple

from ctp2_ae_parser import parse_file, render_file
from ctp2_csv_codec import (
    blocks_to_rows, rows_to_blocks, export_long_csv, import_long_csv,
    LONG_HEADERS,
)
from ctp2_line_codec import (
    detect_kind as detect_line_kind, parse_lines, render_lines,
    export_line_csv, import_line_csv,
)
import diffdb_parser
import re as _re


def _ctp2_tokens(text: str):
    """Tokenize the way CTP2's database parser does: strip // and # comments,
    then split on whitespace and braces. This is the acceptance criterion —
    if original and rebuilt produce the same token stream, the game accepts it."""
    text = _re.sub(r'//[^\n]*', '', text)
    text = _re.sub(r'#[^\n]*', '', text)
    return _re.findall(r'\{|\}|[^\s{}]+', text)


# Files that are block-structured but use a different parser
DIFFDB_NAMES = {"diffdb.txt"}

# Extensions that are never block files — always copied verbatim
COPY_EXTENSIONS = {".bmp", ".tga", ".gif", ".spr", ".wav", ".mp3", ".avi",
                   ".scn", ".sav", ".bin", ".dat"}

# .txt files that are NOT handled by any codec yet — copied verbatim.
# Great_Library uses [SECTION]...[END]; civilisation has its own record format.
# These need dedicated codecs (not yet built) — until then, verbatim copy keeps
# the output mod complete. Everything else is probed and parsed.
VERBATIM_TXT_HINTS = (
    "great_library", "civilisation", "civ_str", "pedia", "readme",
)


def _is_verbatim_txt(name: str) -> bool:
    low = name.lower()
    return any(h in low for h in VERBATIM_TXT_HINTS)


def _classify(path: Path) -> str:
    """Return 'diffdb' | 'block' | 'line' | 'copy'."""
    if path.suffix.lower() in COPY_EXTENSIONS:
        return "copy"
    if path.name.lower() in DIFFDB_NAMES:
        return "diffdb"
    if path.suffix.lower() != ".txt":
        return "copy"
    if _is_verbatim_txt(path.name):
        return "copy"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return "copy"
    # Block files take priority: at least one non-empty brace block.
    blocks = parse_file(text)
    if blocks and any(items for items in blocks.values()):
        return "block"
    # Line files: flat-KV (Const) or string-DB (gl_str, junk_str) with data lines.
    if detect_line_kind(text) is not None:
        return "line"
    return "copy"


def _rel_to_csv_name(rel: Path) -> str:
    """Map a relative txt path to a flat CSV filename (path components joined)."""
    parts = list(rel.parts)
    parts[-1] = rel.stem + ".csv"
    return "__".join(parts)


def _csv_name_to_rel(csv_name: str) -> Path:
    stem = csv_name[:-4] if csv_name.endswith(".csv") else csv_name
    parts = stem.split("__")
    parts[-1] = parts[-1] + ".txt"
    return Path(*parts)


# ---------------------------------------------------------------------------
# extract
# ---------------------------------------------------------------------------

def extract(mod: Path, csv_dir: Path) -> Tuple[int, int, int, int]:
    """
    Walk the mod folder; write a long-form CSV for each block file, a DiffDB CSV
    for DiffDB.txt, and a line CSV for flat-KV / string-DB files. Record a
    manifest of verbatim-copy files.

    Returns (block_files, diffdb_files, line_files, copy_files).
    """
    csv_dir.mkdir(parents=True, exist_ok=True)
    manifest_lines: List[str] = []
    n_block = n_diff = n_line = n_copy = 0

    for path in sorted(mod.rglob("*")):
        if path.is_dir():
            continue
        rel = path.relative_to(mod)
        kind = _classify(path)

        if kind == "block":
            blocks = parse_file(path.read_text(encoding="utf-8", errors="replace"))
            csv_name = _rel_to_csv_name(rel)
            export_long_csv(blocks, csv_dir / csv_name)
            manifest_lines.append(f"block\t{rel.as_posix()}\t{csv_name}")
            n_block += 1
        elif kind == "diffdb":
            diff_blocks = diffdb_parser.parse_diffdb(
                path.read_text(encoding="utf-8", errors="replace"))
            # Serialise DiffDB to long CSV by wrapping its anonymous blocks
            wrapped: "OrderedDict[str, tuple]" = OrderedDict()
            for i, blk in enumerate(diff_blocks):
                wrapped[f"__anon_{i}__"] = blk
            csv_name = _rel_to_csv_name(rel)
            export_long_csv(wrapped, csv_dir / csv_name)
            manifest_lines.append(f"diffdb\t{rel.as_posix()}\t{csv_name}")
            n_diff += 1
        elif kind == "line":
            text = path.read_text(encoding="utf-8", errors="replace")
            line_kind = detect_line_kind(text)
            rows = parse_lines(text, line_kind)
            csv_name = _rel_to_csv_name(rel)
            export_line_csv(rows, csv_dir / csv_name)
            manifest_lines.append(f"line\t{rel.as_posix()}\t{csv_name}")
            n_line += 1
        else:
            manifest_lines.append(f"copy\t{rel.as_posix()}\t")
            n_copy += 1

    (csv_dir / "_manifest.tsv").write_text(
        "kind\trel_path\tcsv_name\n" + "\n".join(manifest_lines) + "\n",
        encoding="utf-8")

    print(f"  extracted: {n_block} block, {n_diff} diffdb, {n_line} line, {n_copy} verbatim")
    return n_block, n_diff, n_line, n_copy


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------

def build(csv_dir: Path, out: Path, mod: Path, force: bool = False) -> Tuple[int, int, int, int]:
    """
    Reconstruct the mod folder from CSVs.  Block/diffdb files are rebuilt from
    their CSVs; verbatim files are copied from the original `mod` folder.

    Precondition: `mod` is the original folder (source of verbatim files).
    """
    manifest_path = csv_dir / "_manifest.tsv"
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest not found: {manifest_path} (run extract first)")
    if out.exists():
        if not force:
            raise RuntimeError(f"output exists: {out} (use --force)")
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    n_block = n_diff = n_line = n_copy = 0
    for line in manifest_path.read_text(encoding="utf-8").splitlines()[1:]:
        if not line.strip():
            continue
        kind, rel_str, csv_name = (line.split("\t") + ["", "", ""])[:3]
        rel = Path(rel_str)
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)

        if kind == "block":
            blocks = import_long_csv(csv_dir / csv_name)
            dst.write_text(render_file(blocks), encoding="utf-8")
            n_block += 1
        elif kind == "diffdb":
            wrapped = import_long_csv(csv_dir / csv_name)
            diff_blocks = list(wrapped.values())
            dst.write_text(diffdb_parser.render_diffdb(diff_blocks), encoding="utf-8")
            n_diff += 1
        elif kind == "line":
            rows = import_line_csv(csv_dir / csv_name)
            dst.write_text(render_lines(rows), encoding="utf-8")
            n_line += 1
        else:  # copy
            src = mod / rel
            if src.exists():
                shutil.copy2(src, dst)
            n_copy += 1

    print(f"  built: {n_block} block, {n_diff} diffdb, {n_line} line, {n_copy} verbatim → {out}")
    return n_block, n_diff, n_line, n_copy


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------

def verify(mod: Path, out: Path) -> bool:
    """
    Compare original vs reconstructed, field-for-field, for every block/diffdb
    file. Verbatim files are compared byte-for-byte.
    Returns True iff every file matches.
    """
    all_ok = True
    checked = 0

    for path in sorted(mod.rglob("*")):
        if path.is_dir():
            continue
        rel = path.relative_to(mod)
        out_path = out / rel
        kind = _classify(path)

        if not out_path.exists():
            print(f"  MISSING in output: {rel.as_posix()}")
            all_ok = False
            continue

        if kind == "block":
            a = parse_file(path.read_text(encoding="utf-8", errors="replace"))
            b = parse_file(out_path.read_text(encoding="utf-8", errors="replace"))
            ok = list(a.items()) == list(b.items())
            # Acceptance gate: rebuilt token stream must match the original's,
            # the way CTP2 reads it. Catches silently-dropped tokens that a
            # parser-vs-parser check would miss.
            tok_ok = _ctp2_tokens(path.read_text(encoding="utf-8", errors="replace")) == \
                     _ctp2_tokens(out_path.read_text(encoding="utf-8", errors="replace"))
            checked += 1
            if not ok:
                all_ok = False
                _report_block_diff(rel, a, b)
            if not tok_ok:
                all_ok = False
                print(f"  FAIL (token stream): {rel.as_posix()} — game would reject")
        elif kind == "diffdb":
            a = diffdb_parser.parse_diffdb(path.read_text(encoding="utf-8", errors="replace"))
            b = diffdb_parser.parse_diffdb(out_path.read_text(encoding="utf-8", errors="replace"))
            ok = len(a) == len(b) and all(x == y for x, y in zip(a, b))
            tok_ok = _ctp2_tokens(path.read_text(encoding="utf-8", errors="replace")) == \
                     _ctp2_tokens(out_path.read_text(encoding="utf-8", errors="replace"))
            checked += 1
            if not ok:
                all_ok = False
                print(f"  FAIL (diffdb): {rel.as_posix()}  blocks {len(a)} vs {len(b)}")
            if not tok_ok:
                all_ok = False
                print(f"  FAIL (diffdb token stream): {rel.as_posix()} — game would reject")
        elif kind == "line":
            la = detect_line_kind(path.read_text(encoding="utf-8", errors="replace"))
            a = parse_lines(path.read_text(encoding="utf-8", errors="replace"), la)
            lb = detect_line_kind(out_path.read_text(encoding="utf-8", errors="replace"))
            b = parse_lines(out_path.read_text(encoding="utf-8", errors="replace"), lb or la)
            # Compare key→value pairs (RAW lines compared by raw content)
            av = [(r.kind, r.key, r.value) for r in a]
            bv = [(r.kind, r.key, r.value) for r in b]
            ok = av == bv
            checked += 1
            if not ok:
                all_ok = False
                for i, (x, y) in enumerate(zip(av, bv)):
                    if x != y:
                        print(f"  FAIL (line): {rel.as_posix()}  row {i}: {x} vs {y}")
                        break
        else:
            # verbatim — compare bytes
            ok = path.read_bytes() == out_path.read_bytes()
            checked += 1
            if not ok:
                all_ok = False
                print(f"  FAIL (verbatim bytes differ): {rel.as_posix()}")

    print(f"\n  verified {checked} files: {'ALL FAITHFUL ✓' if all_ok else 'MISMATCHES FOUND ✗'}")
    return all_ok


def _report_block_diff(rel: Path, a: "OrderedDict", b: "OrderedDict") -> None:
    a_keys, b_keys = list(a.keys()), list(b.keys())
    if a_keys != b_keys:
        only_a = set(a_keys) - set(b_keys)
        only_b = set(b_keys) - set(a_keys)
        print(f"  FAIL (blocks): {rel.as_posix()}  "
              f"count {len(a_keys)}→{len(b_keys)}"
              + (f"  dropped={sorted(only_a)[:3]}" if only_a else "")
              + (f"  added={sorted(only_b)[:3]}" if only_b else ""))
        return
    for k in a_keys:
        if a[k] != b[k]:
            print(f"  FAIL (fields): {rel.as_posix()}  block {k}")
            # show first differing item
            for i, (ia, ib) in enumerate(zip(a[k], b[k])):
                if ia != ib:
                    print(f"      item {i}: {ia!r}  vs  {ib!r}")
                    break
            return


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description="Faithful CTP2 mod ↔ CSV round-trip")
    sub = p.add_subparsers(dest="cmd", required=True)

    pe = sub.add_parser("extract", help="mod → CSV control plane")
    pe.add_argument("--mod", type=Path, required=True)
    pe.add_argument("--csv-dir", type=Path, required=True)

    pb = sub.add_parser("build", help="CSV → reconstructed mod")
    pb.add_argument("--csv-dir", type=Path, required=True)
    pb.add_argument("--out", type=Path, required=True)
    pb.add_argument("--mod", type=Path, required=True, help="original mod (verbatim source)")
    pb.add_argument("--force", action="store_true")

    pv = sub.add_parser("verify", help="compare original vs reconstructed")
    pv.add_argument("--mod", type=Path, required=True)
    pv.add_argument("--out", type=Path, required=True)

    pr = sub.add_parser("roundtrip", help="extract + build + verify")
    pr.add_argument("--mod", type=Path, required=True)
    pr.add_argument("--out", type=Path, required=True)
    pr.add_argument("--csv-dir", type=Path, default=None)
    pr.add_argument("--force", action="store_true")

    args = p.parse_args()

    if args.cmd == "extract":
        extract(args.mod, args.csv_dir)
        return 0
    if args.cmd == "build":
        build(args.csv_dir, args.out, args.mod, force=args.force)
        return 0
    if args.cmd == "verify":
        return 0 if verify(args.mod, args.out) else 1
    if args.cmd == "roundtrip":
        csv_dir = args.csv_dir or (args.out.parent / (args.out.name + "_csv"))
        print(f"[1/3] extract → {csv_dir}")
        extract(args.mod, csv_dir)
        print(f"[2/3] build → {args.out}")
        build(csv_dir, args.out, args.mod, force=True)
        print(f"[3/3] verify")
        ok = verify(args.mod, args.out)
        return 0 if ok else 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
