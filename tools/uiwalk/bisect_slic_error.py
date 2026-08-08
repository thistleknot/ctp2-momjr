"""bisect_slic_error.py -- find which handler raises a runtime SLIC error.

WHY A SCRIPT. A CTP2 RUNTIME error ("Slic Error", lowercase c) reports no file
and no line -- the failure comes from inside a builtin, so there is no SLIC frame
to attribute it to. Reading the code and guessing is exactly what produced two
wrong fixes for this one already. The only instrument that works is: disable a
handler, launch, see whether the error survives.

HOW. Each candidate is neutralised by renaming its HandleEvent segment to a name
the engine never fires, which leaves the file parsing and every declaration
intact -- so a disabled handler cannot change symbol visibility or include order
and produce a different bug than the one under test.

The error fires before turn 1 (units die during initial placement), so two turns
is enough to reproduce and the whole sweep is cheap.

Usage:  python tools/uiwalk/bisect_slic_error.py
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAMEDATA = HERE.parent.parent / "scen0000/default/gamedata"
PY = sys.executable

# (file, HandleEvent segment name) -- every handler added or changed in the
# artifact work, newest first, because the newest code is the likeliest suspect.
CANDIDATES = [
    ("mom_artifacts.slc", "MomGenieFreesVessel"),
    ("mom_artifacts.slc", "MomArtifactScan"),
]


def _disable(path: Path, seg: str) -> str:
    text = path.read_text(encoding="latin-1")
    pat = re.compile(r"(HandleEvent\(\w+\)\s+')" + re.escape(seg) + r"(')")
    if not pat.search(text):
        raise SystemExit(f"segment {seg} not found in {path.name}")
    path.write_text(pat.sub(r"\1" + seg + "_DISABLED" + r"\2", text), encoding="latin-1")
    return text


def _run(tag: str) -> tuple[bool, str]:
    """Launch the probe. Returns (error_seen, first error text)."""
    log = Path("C:/Users/user/.claude/jobs/ba4e8825/tmp") / f"bisect_{tag}.log"
    subprocess.run([PY, str(HERE / "probe_artifacts.py"), "--turns", "2"],
                   capture_output=True, text=True, timeout=900,
                   cwd=str(HERE.parent.parent))
    out = log.read_text(errors="replace") if log.exists() else ""
    return ("", "")


def main() -> int:
    print("Baseline first: does the error reproduce with everything enabled?")
    for path_name, seg in CANDIDATES:
        path = GAMEDATA / path_name
        original = _disable(path, seg)
        print(f"\n=== disabled {seg} -- launching ===", flush=True)
        r = subprocess.run(
            [PY, str(HERE / "probe_artifacts.py"), "--turns", "2"],
            capture_output=True, text=True, timeout=1200,
            cwd=str(HERE.parent.parent))
        out = r.stdout + r.stderr
        path.write_text(original, encoding="latin-1")
        hit = "not a valid player index" in out
        print(f"    error present: {hit}", flush=True)
        if not hit:
            print(f"\nCULPRIT: {seg} in {path_name}")
            return 0
        time.sleep(2)
    print("\nError survives every candidate -- it is NOT in these handlers.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
