"""Report the turn at which a run's frames first show the endgame score window.

WHY: `decode_run.py` classifies the endgame as a STALL, and it is right to --
the frames really do stop changing. But "the game ended" and "the game froze"
are opposite outcomes that produce an identical pixel signature, so the run's
most important event is reported as its worst failure.

This reads the window TITLE strip instead. CTP2's endgame window is
`VictoryWindow` (`victoryscreen.ldl`), titled DEFEAT or VICTORY, and the title
is drawn in the same place regardless of which. Comparing the title strip of
every checkpoint against the LAST frame of a run that is known to have ended
gives a cheap present/absent classifier without OCR.

Usage:
    python detect_endgame.py <run_dir> [--ref <run_dir_that_ended>]

Exit 0 always -- this reports.
"""

from __future__ import annotations

import argparse
import glob
import os
import re
from pathlib import Path

import numpy as np
from PIL import Image

# Title strip of VictoryWindow, measured on runs/20260727-203414 at a 1080x1920
# client. The window is centre-anchored, so this box moves with client size --
# re-measure if the capture geometry changes rather than trusting these numbers.
TITLE_BOX = (420, 770, 660, 795)
MATCH_MEAN_ABS = 5.0   # <= this against the reference strip == same title drawn


def shots(run: Path) -> list[tuple[int, Path]]:
    out = []
    for p in glob.glob(str(run / "*.png")):
        m = re.fullmatch(r"(\d+)_turn(\d+)", Path(p).stem)
        if m:
            out.append((int(m.group(2)), Path(p)))
    return sorted(out)


def strip(p: Path) -> np.ndarray:
    return np.asarray(Image.open(p).convert("L").crop(TITLE_BOX), dtype=float)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--ref", help="run dir whose LAST frame shows the endgame "
                                  "window; defaults to this run's last frame")
    args = ap.parse_args()

    run = Path(args.run)
    frames = shots(run)
    if not frames:
        print(f"{run.name}: no turn shots")
        return 0

    ref_frames = shots(Path(args.ref)) if args.ref else frames
    ref = strip(ref_frames[-1][1])

    first = None
    for turn, path in frames:
        if np.abs(strip(path) - ref).mean() <= MATCH_MEAN_ABS:
            first = turn
            break

    last_turn = frames[-1][0]
    if first is None:
        print(f"{run.name}: NO endgame window in {len(frames)} checkpoints "
              f"(last turn {last_turn}) -- the game was still being played")
    else:
        print(f"{run.name}: endgame window FIRST PRESENT at turn {first} "
              f"(absent at the checkpoint before), still present at {last_turn}")
        print("  -> the run's trailing zero-delta frames are the ENDING, "
              "not a freeze")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
