import re

file_path = r'H:\Program Files(x86)\Activision\Call To Power 2\Scenarios\mom\tools\ctp2_generator.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Update _pick_sprite to use SPRITE_SETTLER for peasants/settlers
old_logic = """    if any(k in n for k in ('cavalry', 'unicorn', 'paladin', 'horseman')):
        return 'SPRITE_CAVALRY'
    if attack >= 40:
        return 'SPRITE_KNIGHT'
    if attack >= 20:
        return 'SPRITE_HOPLITE'
    return 'SPRITE_WARRIOR'"""

new_logic = """    if any(k in n for k in ('cavalry', 'unicorn', 'paladin', 'horseman')):
        return 'SPRITE_CAVALRY'
    if 'peasant' in n or 'settler' in n:
        return 'SPRITE_SETTLER'
    if attack >= 40:
        return 'SPRITE_KNIGHT'
    if attack >= 20:
        return 'SPRITE_HOPLITE'
    return 'SPRITE_WARRIOR'"""

content = content.replace(old_logic, new_logic)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print('Updated _pick_sprite to use SPRITE_SETTLER for peasants/settlers')