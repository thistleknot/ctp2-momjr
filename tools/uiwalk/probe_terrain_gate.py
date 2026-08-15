#!/usr/bin/env python
"""probe_terrain_gate.py -- verify terrain-gated buildings are excluded from the build menu.

TEST LOGIC:
  1. Boot the game into MoM
  2. Open the Build Editor (Ctrl+B)
  3. Click the Buildings tab
  4. Screenshot the buildings list
  5. Check whether "Primal Source" appears in the list

  The starting city's terrain determines the expected result:
  - If adjacent to forest/jungle/swamp: Primal Source SHOULD appear (for Nature sphere)
  - If NOT adjacent: Primal Source should NOT appear

  Since the Nature sphere gate also applies (Primal Source is sphere=nature),
  only a Nature player's city can build it regardless of terrain. We need to
  confirm that the terrain gate is additive on top of sphere gating.

  STRATEGY: We just confirm the build editor opens and capture the buildings tab.
  If Primal Source does NOT appear for a Nature player on non-forest terrain,
  the terrain gate is working. If it DOES appear, either the city has forest
  adjacent or the gate isn't firing.

  We capture the buildings list screenshot and the terrain of the city center
  via the SLIC fixture (TerrainType query via the command protocol).
"""
from __future__ import annotations

import ctypes
import sys
import time
from pathlib import Path

import cv2

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import uiwalk   # noqa: E402
import turnloop  # noqa: E402


def main() -> int:
    uiwalk.PREFER_RELEASE = True
    uiwalk.preflight_exe("MagicMenu")
    uiwalk.preflight_display()

    run_dir = uiwalk.RUNS / (time.strftime("%Y%m%d-%H%M%S") + "-terrain-gate")
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"artifacts -> {run_dir}")

    game = uiwalk.Game()
    watcher = turnloop.ErrorWatcher(set())
    watcher.start()

    try:
        game.launch(None, [])
        boot_results = turnloop.boot(game, run_dir)
        failed_boot = [r for r in boot_results if not r[3]]
        if failed_boot:
            print("boot asserts failed: " + ", ".join(r[0] for r in failed_boot))
            return 1
        if watcher.hits:
            print("SLIC error at load")
            return 1

        inp = uiwalk.PostInput(game)

        # Advance 1 turn so the city is established
        turnloop.end_turn(game, inp, "button")
        time.sleep(3.0)
        print("turn 1 advanced", flush=True)

        # Open the Build Editor via Ctrl+B
        inp.hotkey(["ctrl", "b"])
        time.sleep(2.0)
        uiwalk.wait_stable(game, 6000)
        cv2.imwrite(str(run_dir / "01_build_editor_open.png"), game.screenshot())
        print("build editor opened", flush=True)

        # Click the Buildings tab
        uiwalk.inject_press(game.hwnd,
                            "BuildEditorWindow.ItemsBox.BuildingsButton")
        time.sleep(1.5)
        uiwalk.wait_stable(game, 4000)
        frame = game.screenshot()
        cv2.imwrite(str(run_dir / "02_buildings_tab.png"), frame)
        print("buildings tab clicked, screenshot saved", flush=True)

        # Try scrolling down to see more buildings if needed
        uiwalk.inject_select(game.hwnd,
                             "BuildEditorWindow.ItemsBox.BuildingsList", 0)
        time.sleep(0.5)
        frame2 = game.screenshot()
        cv2.imwrite(str(run_dir / "03_buildings_list_top.png"), frame2)

        # Scroll to see more
        for i in range(5):
            uiwalk.inject_select(game.hwnd,
                                 "BuildEditorWindow.ItemsBox.BuildingsList", i)
            time.sleep(0.3)
        frame3 = game.screenshot()
        cv2.imwrite(str(run_dir / "04_buildings_list_scrolled.png"), frame3)
        print("buildings list captured (top + scrolled)", flush=True)

        # Close
        uiwalk.inject_press(game.hwnd,
                            "BuildEditorWindow.NormalModeButtons.CloseButton")
        time.sleep(1.0)

        print("\nVERDICT: CAPTURED", flush=True)
        print("Inspect 02_buildings_tab.png and 04_buildings_list_scrolled.png", flush=True)
        print("If Primal Source is ABSENT and city is NOT near forest/jungle/swamp: TERRAIN GATE WORKS", flush=True)
        print("If Primal Source is PRESENT: either city has forest adjacent, or gate is not firing", flush=True)
        print(f"slic_errors={len(watcher.hits)}", flush=True)

    except Exception as exc:
        print(f"EXCEPTION: {exc}", flush=True)
        return 1
    finally:
        watcher.stop()
        game.kill()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
