"""probe_magic_menu.py -- Boot game, press J, screenshot the magic menu."""
import ctypes, json, sys, time
from pathlib import Path
import cv2

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import uiwalk

PROLOGUE = 53

def main() -> int:
    uiwalk.PREFER_RELEASE = True
    uiwalk.preflight_exe("MagicMenu")
    uiwalk.preflight_display()
    ctypes.windll.user32.SetProcessDPIAware()

    steps = json.loads((HERE / "steps/full_game_v3.json").read_text())
    row = uiwalk.scenario_pack_index("mom")
    for s in steps[:PROLOGUE]:
        if s.get("path") == "ScenarioWindow.AvailableListBox" and s.get("index"):
            s["index"] = row
            break
    prologue = steps[:PROLOGUE]

    run_dir = HERE / "runs" / (time.strftime("%Y%m%d-%H%M%S") + "-magic-menu")
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"artifacts -> {run_dir}")

    game = uiwalk.Game()
    try:
        game.launch(None, [])
        inp = uiwalk.PostInput(game)
        uiwalk.run_steps(game, inp, prologue, run_dir, baseline=False, dry=False)

        # Press J to open magic menu
        time.sleep(2)
        uiwalk.run_steps(game, inp, [
            {"do": "key", "keys": "j"},
            {"do": "wait_stable", "ms": 5000},
            {"do": "shot", "name": "magic_menu"},
        ], run_dir, baseline=False, dry=False)

        shot = game.screenshot()
        out_path = str(run_dir / "magic_menu_final.png")
        cv2.imwrite(out_path, shot)
        print(f"Screenshot: {out_path}")
        return 0
    finally:
        game.kill()

if __name__ == "__main__":
    sys.exit(main())
