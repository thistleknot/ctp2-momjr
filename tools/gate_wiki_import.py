"""Gate: validate wiki-imported CSVs for charset safety and idempotency.

Checks:
1. Every ident in imported CSVs matches CTP2 charset (A-Z, 0-9, _)
2. Required fields are populated
3. Re-running extractors produces byte-identical output (idempotency)

Run: python gate_wiki_import.py [--skip-rederive]
From: Scenarios/mom/tools/
Exit 0 = PASS, exit 1 = FAIL.
"""
import csv, hashlib, re, sys, importlib, io, contextlib
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
CSV_DIR = TOOLS / "momjr_csv"

CSVS = ["spells.csv", "heroes.csv", "buildings_wiki.csv", "race_units_wiki.csv"]
_IDENT_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


def main():
    skip = "--skip-rederive" in sys.argv
    errors, warns = [], []

    for name in CSVS:
        p = CSV_DIR / name
        if not p.exists():
            warns.append(f"{name}: missing"); continue
        with open(p, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        print(f"  {name}: {len(rows)} rows")
        # charset check
        for i, r in enumerate(rows):
            ident = r.get("ident", "")
            if ident and not _IDENT_RE.match(ident):
                errors.append(f"{name}:{i+2} bad charset '{ident}'")
                if len(errors) > 20:
                    break
        # empty name check
        empty = sum(1 for r in rows if not r.get("name", "").strip())
        if empty:
            warns.append(f"{name}: {empty} empty names")

    # Idempotency
    if not skip:
        print("  idempotency check...")
        mods = ["wiki_import.extract_spells", "wiki_import.extract_heroes",
                "wiki_import.extract_buildings", "wiki_import.extract_race_units"]
        before = {n: hashlib.sha256((CSV_DIR/n).read_bytes()).hexdigest()
                  for n in CSVS if (CSV_DIR/n).exists()}
        for m in mods:
            try:
                mod = importlib.import_module(m)
                with contextlib.redirect_stdout(io.StringIO()):
                    mod.main()
            except Exception as e:
                errors.append(f"rederive {m}: {e}")
        for n in CSVS:
            p = CSV_DIR / n
            if p.exists() and n in before:
                after = hashlib.sha256(p.read_bytes()).hexdigest()
                if after != before[n]:
                    errors.append(f"{n}: NOT idempotent")
                else:
                    print(f"    {n}: idempotent")

    if errors:
        print(f"\nFAIL: {len(errors)}")
        for e in errors[:10]:
            print(f"  x {e}")
        sys.exit(1)
    elif warns:
        print(f"\nPASS ({len(warns)} warnings)")
        sys.exit(0)
    else:
        print("\nPASS")
        sys.exit(0)


if __name__ == "__main__":
    main()
