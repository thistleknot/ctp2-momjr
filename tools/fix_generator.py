import re

file_path = r'H:\Program Files(x86)\Activision\Call To Power 2\Scenarios\mom\tools\ctp2_generator.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Use regex to match the block, allowing for any characters in the comment
old_pattern = r'if \(_pics_dir / _extracted_tga\)\.exists\(\):\s*#.*?\s*_block\["FirstFrame"\] = f\'"{_extracted_tga}"\'\s*_block\["Icon"\] = f\'"{_extracted_tga}"\'\s*patched_units \+= 1\s*_block\["FirstFrame"\] = f\'"{_extracted_tga}"\'\s*_block\["Icon"\] = f\'"{_extracted_tga}"\'\s*patched_units \+= 1'

new_text = '''if (_pics_dir / _extracted_tga).exists():
            # MoM art exists on disk - force the uniticon block to use it for all icon sizes
            _block["FirstFrame"] = f'"{_extracted_tga}"'
            _block["Icon"] = f'"{_extracted_tga}"'
            _block["LargeIcon"] = f'"{_extracted_tga}"'
            _block["SmallIcon"] = f'"{_extracted_tga}"'
            patched_units += 1'''

content = re.sub(old_pattern, new_text, content, flags=re.DOTALL)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print('Replacement successful')