#!/usr/bin/env python
"""probe_save_load.py -- verify save/load does not crash after N turns.

The `unit_t[160]` array was removed in a recent session to fix a save/load crash.
This script proves the fix holds: boot, play N turns, save, load, confirm alive.

WHAT THIS PROVES: the game survives a full save/load cycle without crashing.
The process is alive after load = PASS. Process dead = the serialization path
still has a fatal defect.

EXIT CODES:
  0 = PASS (save/load survived, process alive)
  1 = FAIL (crash during or after save/load)
  2 = FAIL (could not reach the save point -- boot or turn failure)
"""
from __future__ import annotations

import argparse
import ctypes
import json
import sys
import time
from pathlib import Path

import cv2

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import uiwalk   # noqa: E402
import turnloop  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Save/load crash probe")
    ap.add_argument("--turns", type=int, default=5,
                    help="number of turns to play before save/load")
    ap.add_argument("--marker", default="MagicMenu",
                    help="exe marker check (use 'none' to skip)")
    args = ap.parse_args()

    uiwalk.PREFER_RELEASE = True
    if args.marker.lower() != "none":
        uiwalk.preflight_exe(args.marker)
    uiwalk.preflight_display()
    ctypes.windll.user32.SetProcessDPIAware()

    run_dir = uiwalk.RUNS / (time.strftime("%Y%m%d-%H%M%S") + "-saveload")
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"artifacts -> {run_dir}")
    turnloop._CALIB_DEBUG_DIR = run_dir

    game = uiwalk.Game()
    watcher = turnloop.ErrorWatcher(set())
    watcher.start()
    reached = 0
    verdict = "INCOMPLETE"

    try:
        # --- BOOT ---
        game.launch(None, [])
        boot_results = turnloop.boot(game, run_dir)
        failed_boot = [r for r in boot_results if not r[3]]
        if failed_boot:
            verdict = "BOOT_FAILED"
            print("boot asserts failed: " + ", ".join(r[0] for r in failed_boot))
            return 2
        if watcher.hits:
            verdict = "SLIC_ERROR_AT_LOAD"
            return 2

        inp = uiwalk.PostInput(game)
        prev = game.screenshot()
        cv2.imwrite(str(run_dir / "turn_000.png"), prev)

        # --- TURN LOOP ---
        for turn in range(1, args.turns + 1):
            if not turnloop.alive(game):
                verdict = f"CRASH_BEFORE_TURN_{turn}"
                return 2

            turnloop.dismiss_message(game, inp)
            pre = game.screenshot()

            advanced = False
            for attempt in range(1, turnloop.END_TURN_ATTEMPTS + 1):
                turnloop.engine_ping(inp)
                turnloop.end_turn(game, inp, "button")
                time.sleep(1.0)
                uiwalk.wait_stable(game, 25000)

                if not turnloop.alive(game):
                    verdict = f"CRASH_DURING_TURN_{turn}"
                    return 2
                if watcher.hits:
                    verdict = f"SLIC_ERROR_TURN_{turn}"
                    return 2

                shot = game.screenshot()
                advanced = turnloop.date_changed(pre, shot)
                if advanced:
                    break
                if attempt < turnloop.END_TURN_ATTEMPTS:
                    time.sleep(turnloop.END_TURN_RETRY_S)

            cv2.imwrite(str(run_dir / f"turn_{turn:03d}.png"), shot)
            print(f"turn {turn:3d}  advanced={advanced}", flush=True)
            prev = shot

            if not advanced:
                verdict = f"TURN_DID_NOT_ADVANCE_AT_{turn}"
                return 2
            reached = turn

        # --- SAVE/LOAD SEQUENCE ---
        print(f"\n--- SAVE/LOAD after {reached} turns ---", flush=True)

        # Open save dialog
        inp.hotkey(["ctrl", "s"])
        time.sleep(3)

        # Confirm save
        inp.hotkey(["enter"])
        time.sleep(3)

        if not turnloop.alive(game):
            verdict = "CRASH_DURING_SAVE"
            print(f"\nVERDICT: SAVE_LOAD_CRASH (code={game.proc.returncode})")
            return 1

        cv2.imwrite(str(run_dir / "post_save.png"), game.screenshot())
        print("save completed, process alive", flush=True)

        # Open load dialog
        inp.hotkey(["ctrl", "l"])
        time.sleep(3)

        # Confirm load (loads the save just made)
        inp.hotkey(["enter"])
        time.sleep(5)

        if not turnloop.alive(game):
            code = game.proc.returncode
            verdict = f"CRASH_DURING_LOAD (code={code})"
            print(f"\nVERDICT: SAVE_LOAD_CRASH (code={code})")
            return 1

        # Wait for load to fully settle
        uiwalk.wait_stable(game, 15000)

        # --- VERDICT ---
        if game.proc.poll() is None:
            verdict = "SAVE_LOAD_OK"
            cv2.imwrite(str(run_dir / "post_load.png"), game.screenshot())
            print(f"\nVERDICT: SAVE_LOAD_OK")
            return 0
        else:
            code = game.proc.returncode
            verdict = f"SAVE_LOAD_CRASH (code={code})"
            print(f"\nVERDICT: SAVE_LOAD_CRASH (code={code})")
            return 1

    except (RuntimeError, TimeoutError) as e:
        verdict = f"HARNESS_ERROR: {e}"
        print(f"\nVERDICT: HARNESS_ERROR ({e})")
        return 2
    finally:
        watcher.stop()
        (run_dir / "probe_save_load.json").write_text(json.dumps({
            "verdict": verdict,
            "turns_before_save": reached,
            "slic_errors": watcher.hits,
        }, indent=2))
        game.kill()


if __name__ == "__main__":
    sys.exit(main())
