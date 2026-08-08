"""Summon a creature with REAL cursor clicks and screenshot the unit panel."""
import ctypes, json, sys, time, os
from pathlib import Path
import cv2, numpy as np
import win32api, win32con, win32gui

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.chdir(HERE)

import uiwalk
import turnloop

uiwalk.PREFER_RELEASE = True
uiwalk.preflight_exe('MagicMenu')
uiwalk.preflight_display()
ctypes.windll.user32.SetProcessDPIAware()

run_dir = uiwalk.RUNS / (time.strftime('%Y%m%d-%H%M%S') + '-icon-verify')
run_dir.mkdir(parents=True, exist_ok=True)
print(f'artifacts -> {run_dir}')

steps = json.loads((HERE / 'steps/full_game_v3.json').read_text())
boot_steps = steps[:53]
cycle_steps = steps[53:60]


def real_click(game, x, y):
    """Bring window to foreground, move REAL cursor, do a REAL click via pyautogui."""
    import pyautogui
    hwnd = game.hwnd
    # Bring to foreground
    ctypes.windll.user32.SetForegroundWindow(hwnd)
    time.sleep(0.3)
    # Get client origin in screen coords
    pt = win32gui.ClientToScreen(hwnd, (x, y))
    # Real mouse move + click
    pyautogui.click(pt[0], pt[1])
    time.sleep(0.3)


game = uiwalk.Game()
watcher = turnloop.ErrorWatcher(set())
watcher.start()

try:
    game.launch(None, [])
    inp = uiwalk.PostInput(game)
    uiwalk.run_steps(game, inp, boot_steps, run_dir, baseline=False, dry=False)
    print('Prologue done')

    for t in range(15):
        uiwalk.run_steps(game, inp, cycle_steps, run_dir, baseline=False, dry=False)
    print('15 turns done')

    # Open magic menu
    inp.hotkey(['j'])
    time.sleep(4)
    frame = game.screenshot()
    cv2.imwrite(str(run_dir / '01_magic.png'), frame)
    print('Magic menu open')

    # Click Summon Creature with REAL cursor (measured center x=252, y=374)
    real_click(game, 252, 374)
    time.sleep(4)
    frame = game.screenshot()
    cv2.imwrite(str(run_dir / '02_after_summon_click.png'), frame)
    print('After Summon click')

    # Click creature button 1 (leftmost in the summon picker)
    # Buttons render [1][2][3][X] left-to-right after our fix.
    # Approximate: btn 1 center around x=50, same y band
    real_click(game, 50, 374)
    time.sleep(3)
    frame = game.screenshot()
    cv2.imwrite(str(run_dir / '03_after_pick.png'), frame)
    print('After creature pick')

    # Run 2 turns for the rung-1 summon to arrive
    for t in range(2):
        uiwalk.run_steps(game, inp, cycle_steps, run_dir, baseline=False, dry=False)
    print('2 arrival turns done')

    # Check magic status to confirm mana spent
    inp.hotkey(['j'])
    time.sleep(4)
    frame = game.screenshot()
    cv2.imwrite(str(run_dir / '04_magic_after.png'), frame)
    print('Magic status after summon')

    # Close magic menu
    real_click(game, 339, 374)
    time.sleep(2)

    # Click near city to select the summoned creature
    real_click(game, 530, 400)
    time.sleep(2)
    frame = game.screenshot()
    cv2.imwrite(str(run_dir / '05_unit_select.png'), frame)
    print('Unit select attempt')

finally:
    watcher.stop()
    game.kill()
    print(f'Done. {run_dir}')
    print(f'SLIC errors: {len(watcher.hits)}')
