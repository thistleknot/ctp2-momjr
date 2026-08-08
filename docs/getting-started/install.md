# Installation

## Requirements

- **Call To Power 2** (Apolyton Edition recommended)
- Windows 10/11
- Display capable of 1024x1280 (portrait) or 1024x768 (landscape)

## Steps

1. **Install CTP2** to its default location or a folder of your choice.
2. **Copy the MoM scenario** into `Scenarios/mom/` under your CTP2 install directory.
   The folder structure should look like:
   ```
   Call To Power 2/
     Scenarios/
       mom/
         scen0000/
         tools/
         ...
   ```
3. **Set display mode** in `ctp2_program/ctp/userprofile.txt`:
   ```
   ScreenResWidth=1024
   ScreenResHeight=1280
   WindowedMode=Yes
   ```
   Portrait mode (1024x1280) is recommended for the best map view. Landscape
   (1024x768) also works if your display doesn't support portrait rotation.

4. **Launch the game** from the CTP2 executable. Select "Load Scenario" from the
   main menu and choose "Masters of Magic."

## Verifying the Install

When the scenario loads correctly you'll see:

- Five wizard factions on the map (Life, Nature, Sorcery, Death, Chaos)
- Fantasy-themed advance tree (Warrior Code, Mysticism, Alchemy...)
- MoM creatures in the build queue (Spearmen, Swordsmen, Knights...)

If you see stock CTP2 content (tanks, submarines, corporations), the scenario
path is wrong. Check that `scen0000/` is directly under `Scenarios/mom/`.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Black screen on launch | Set `WindowedMode=Yes` in userprofile.txt |
| "Boot asserts failed" | Use 1024x1280, not 768x1024 |
| Stock units visible | Confirm scenario path, restart game |
| SLIC error dialogs | Report the error text; likely a missing string |
