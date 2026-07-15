"""
golden_test_makespr.py — Byte-parity regression test for makespr.py.

Builds Kull's Cradle 5 Legion (GU16) from its original input TIFs with
makespr.py and byte-compares the result against the makespr.exe-built
GU16.SPR shipped in the same fixture. makespr.py achieved full parity on
2026-07-03; run this after ANY change to makespr.py.

Fixture (Kull, Apolyton/CTP2 Bureau): all animation TIFs + Gu16.txt +
exe-built GU16.SPR. Default location: H:\\Games\\ctp2\\16-makespr\\16
Full MakeSprite kit (MAKESPR.EXE, Cow example, GU00.txt, docs):
H:\\Games\\ctp2\\MakeSprite  (http://www.ctp2.info/download/MakeSprite.zip)

Usage:
    python Scenarios\\mom\\tools\\golden_test_makespr.py [--fixture DIR]

Exit code 0 = byte-identical; 1 = mismatch or error.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_CTP2_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_MAKESPR   = _CTP2_ROOT / "makespr.py"
_FIXTURE   = Path(r"H:\Games\ctp2\16-makespr\16")

SPRITE_ID = 16


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--fixture", type=Path, default=_FIXTURE,
                    help="folder with Gu16.txt, GU16.SPR and the input TIFs")
    args = ap.parse_args()

    fx: Path = args.fixture
    script = next((p for p in fx.iterdir() if p.name.lower() == "gu16.txt"), None)
    golden = next((p for p in fx.iterdir() if p.name.lower() == "gu16.spr"), None)
    if not (script and golden and _MAKESPR.exists()):
        print(f"[ERROR] fixture incomplete at {fx} (need Gu16.txt + GU16.SPR) "
              f"or makespr.py missing at {_MAKESPR}")
        return 1

    with tempfile.TemporaryDirectory(prefix="makespr_golden_") as tmp:
        work = Path(tmp)
        (work / str(SPRITE_ID)).mkdir()
        shutil.copy2(script, work / f"GU{SPRITE_ID}.TXT")
        n = 0
        for tif in fx.iterdir():
            if tif.suffix.lower() == ".tif":
                shutil.copy2(tif, work / str(SPRITE_ID) / tif.name)
                n += 1
        print(f"Staged {n} TIFs; building GU{SPRITE_ID}.SPR with makespr.py ...")

        r = subprocess.run([sys.executable, str(_MAKESPR), "-u", str(SPRITE_ID)],
                           cwd=str(work), capture_output=True, text=True)
        if r.returncode != 0:
            print(f"[FAIL] makespr.py exited {r.returncode}\n{r.stderr.strip()}")
            return 1

        built = (work / f"GU{SPRITE_ID}.SPR").read_bytes()
        ref   = golden.read_bytes()
        if built == ref:
            print(f"[PASS] byte-for-byte identical to makespr.exe output "
                  f"({len(ref):,} bytes)")
            return 0

        nmin  = min(len(built), len(ref))
        first = next((k for k in range(nmin) if built[k] != ref[k]), nmin)
        diffs = sum(1 for k in range(nmin) if built[k] != ref[k])
        print(f"[FAIL] sizes {len(built):,} vs {len(ref):,}; "
              f"first diff at 0x{first:x}; {diffs:,} differing bytes")
        return 1


if __name__ == "__main__":
    sys.exit(main())
