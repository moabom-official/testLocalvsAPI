"""
Remove all hardcoded HTML templates from main_youtube_analysis.py
"""
import re

file_path = r"C:\Users\seank\OneDrive\Desktop\Moabom_Prototype - (4)\main_youtube_analysis.py"

# Read file
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Find and remove all template blocks
# Pattern: from "<html>" or "<!DOCTYPE html>" to the closing """ with everything in between
patterns_to_remove = [
    r'<html>.*?</html>\n"""',
    r'<!DOCTYPE html>.*?</html>\n"""',
]

for pattern in patterns_to_remove:
    content = re.sub(pattern, '', content, flags=re.DOTALL)

# Remove write_templates function
write_templates_pattern = r'# Write templates to files on startup\ndef write_templates\(\):.*?print\("✓ Templates written"\)\n\n'
content = re.sub(write_templates_pattern, '', content, flags=re.DOTALL)

# Remove write_templates() call from startup
content = content.replace('    write_templates()\n', '')

# Remove empty template variable assignments if any
content = re.sub(r'TEMPLATE_\w+\s*=\s*""".*?"""', '', content, flags=re.DOTALL)

# Write back
with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ Removed all hardcoded HTML templates!")
print("✅ Removed write_templates() function!")
print("✅ Removed write_templates() call from startup!")
