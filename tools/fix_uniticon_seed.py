import re

file_path = r'H:\Program Files(x86)\Activision\Call To Power 2\Scenarios\mom\tools\ctp2_generator.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Find the location after patching unit icons and add the cleanup logic
old_text = '''        print(f"  + patched {patched_units} stock unit icon entries in uniticon.txt with MoMJR art")

    gl_library = reg.load("english/gamedata/Great_Library.txt")'''

new_text = '''        print(f"  + patched {patched_units} stock unit icon entries in uniticon.txt with MoMJR art")

    # CRITICAL: Remove base CTP2 unit icon entries from uniticon.txt to prevent seed leakage.
    # If a unit is not in mom_unit_idents and not engine-required, its icon should not exist in the scenario.
    uic_file = reg.load("default/gamedata/uniticon.txt")
    removed_base_icons = 0
    for icon_id in list(uic_file.blocks.keys()):
        if icon_id.startswith("ICON_UNIT_"):
            unit_ident = icon_id.replace("ICON_", "", 1)
            if unit_ident not in mom_unit_idents and unit_ident not in _ENGINE_REQUIRED_UNITS:
                del uic_file.blocks[icon_id]
                removed_base_icons += 1
    
    if removed_base_icons:
        print(f"  + removed {removed_base_icons} base CTP2 unit icon entries from uniticon.txt to prevent seed leakage")

    gl_library = reg.load("english/gamedata/Great_Library.txt")'''

content = content.replace(old_text, new_text)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print('Added uniticon cleanup logic to remove base CTP2 unit icons')