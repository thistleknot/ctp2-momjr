import re

file_path = r'H:\Program Files(x86)\Activision\Call To Power 2\Scenarios\mom\tools\ctp2_generator.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix: Use the sprite from CSV if present, otherwise fall back to _pick_sprite
old_line = "            sprite    = _pick_sprite(name, domain, attack)"
new_line = "            sprite    = row.get('sprite', '').strip() or _pick_sprite(name, domain, attack)"

content = content.replace(old_line, new_line)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed sprite assignment to respect CSV sprite column')