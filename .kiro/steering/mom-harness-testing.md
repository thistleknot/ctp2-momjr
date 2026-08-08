---
inclusion: fileMatch
fileMatchPattern: "**/uiwalk/**"
---

# MoM Harness & Testing

Included when working on the `uiwalk` headless playtest harness.

## What uiwalk Is

Claude-driven, zero-human-input, background-window playtest of CTP2. The game
runs windowed and unfocused; input is posted via `PostMessage` (not `SendInput`),
screenshots via `PrintWindow`. The user can work in other windows untouched.

## Entry Point

```powershell
cd "H:\Program Files(x86)\Activision\Call To Power 2\Scenarios\mom\tools\uiwalk"
C:\Users\user\py310\Scripts\python uiwalk.py --preflight
C:\Users\user\py310\Scripts\python turnloop.py --turns 5
```

## Key Facts (Measured, Do Not Re-Derive)

- **Engine resolution**: `userprofile.txt` → `ScreenResWidth=1280, ScreenResHeight=1024, WindowedMode=Yes`
- **Display**: `\\.\DISPLAY9` primary at 1920x1080, orientation=0
- **Capture geometry**: PrintWindow gets the game's rendered surface (may be DPI-scaled)
- **Engine reflows UI** to its window size — it does NOT letterbox a fixed surface
- **EndTurnButtonActionCallback** early-returns when `GetCurPlayer() != GetVisiblePlayer()` (transient after load; retry 3× with 3s gap)
- **End-turn requires a mouse message** reaching the engine — `engine_ping` posts `WM_MOUSEMOVE` (not a click) to satisfy this
- **KEY_FUNCTION_ENDTURN** is compiled out (`#ifdef _PLAYTEST`) in Final-SDL — the 'A' keypress is dead
- **Menus are mouse-polled** (SDL event-driven, not GetCursorPos) — PostMessage clicks don't register on menus/lists
- **Alertbox arms** are not addressable by LDL string (all share `StandardResponseButton`; only MinimizeButton is in the table)

## Coordinate Classes (The Recurring Defect)

Absolute pixel constants are the #1 defect class in this file. The engine runs at
different resolutions (1024×768, 1024×1280, 1280×1024) and the UI reflows.

Rules:
- X positions scale proportionally with render width
- The control panel is BOTTOM-anchored, fixed pixel height
- Derive coordinates from the detected `render_rect()` at capture time
- Never hardcode a constant derived from one resolution
- `content_scale()` measures geometry but is NOT the send factor (those differ per surface)

## Send Scale (Per-Surface, Empirical)

The capture→send transform is NOT derivable from geometry. It is latched per
surface by `_calibrate()`:
- Message surface: latches ~0.80 at DPI-scaled geometry
- Alertbox surface: latches ~1.25 at DPI-scaled geometry
- At 1:1 geometry (1024×1024 content in 1024 client): identity x1.00

x1.25 on the message surface is PROCESS-LETHAL (0xC0000005, 2/2 runs).
Identity-first reorder when geometry says 1:1.

## Golden Save Requirement

The harness boots from a saved game (`uiwalk_start`) to skip menus (mouse-required).
The save must have: a founded city, Mayor ON, optionally a research goal set.
Redo after any DB-shape change (add/remove units/advances/buildings).

## Intermittent Setup Crash

0xC0000005 in setup, no crash.txt, DB loaded clean — retry once automatically.
Do not investigate. See `mom-intermittent-setup-crash` memory.

## Error Channel

SLIC errors surface as native Win32 `MessageBox` dialogs (class `#32770`, caption
ends in "Error"). `ErrorWatcher` enumerates, captures text, and answers IDYES
(continue) to keep the run headless. Any hit stops the run.
