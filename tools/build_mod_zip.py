"""Build mom.zip -- the MOD, not the repo.

The repo holds the code: the control plane, the generator, the tooling, the
wiki. None of that belongs in the zip. mom.zip is what a player installs, so it
carries exactly what the engine loads for a scenario, which the shipped
scenarios define by example:

    <scenario>/packicon.tga
    <scenario>/packlist.txt
    <scenario>/scen0000/**

wrapped under a top-level mom/ prefix, so unzipping into Scenarios\\ installs it.

Regenerate the scenario first (ctp2_generator.py + mom_audit.py); this script
only packages what is already on disk.
"""
import argparse
import zipfile
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent

# Exactly what the engine loads. Anything else is code, and code stays in git.
ROOT_FILES = ["packicon.tga", "packlist.txt"]
ROOT_DIRS = ["scen0000"]
PREFIX = "mom"

# Build residue that has no business in a distributed mod. `_icon_backup` is a
# pre-regeneration snapshot of the unit icons that lives beside the real ones in
# scen0000; the engine never loads it, so shipping it was 55 dead TGAs of weight.
SKIP_DIRS = {"__pycache__", ".pytest_cache", "_icon_backup"}
SKIP_SUFFIXES = {".pyc", ".bak", ".bak_recursion", ".tmp", ".orig", ".rej"}


def members(repo: Path):
    for name in ROOT_FILES:
        path = repo / name
        if not path.is_file():
            raise SystemExit(f"missing required scenario file: {path}")
        yield path, f"{PREFIX}/{name}"

    for name in ROOT_DIRS:
        base = repo / name
        if not base.is_dir():
            raise SystemExit(f"missing required scenario dir: {base}")
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(repo)
            if any(part in SKIP_DIRS for part in rel.parts):
                continue
            if path.suffix.lower() in SKIP_SUFFIXES:
                continue
            yield path, f"{PREFIX}/" + str(rel).replace("\\", "/")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(REPO_DIR / "mom.zip"))
    parser.add_argument("--repo", default=str(REPO_DIR))
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    out = Path(args.out).resolve()

    count = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path, arcname in members(repo):
            zf.write(path, arcname)
            count += 1

    # A zip that cannot be read back is not a deliverable.
    with zipfile.ZipFile(out) as zf:
        bad = zf.testzip()
        if bad is not None:
            raise SystemExit(f"corrupt entry in {out}: {bad}")

    print(f"{count} files -> {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
