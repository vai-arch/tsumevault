import re
from datetime import datetime

version = datetime.now().strftime('%Y%m%d-%H%M')

# Actualizar sw.js
with open('sw.js', 'r', encoding='utf-8') as f:
    content = f.read()
content = re.sub(r"const CACHE_VERSION = '[^']*'", f"const CACHE_VERSION = 'tsumevault-{version}'", content)
with open('sw.js', 'w', encoding='utf-8') as f:
    f.write(content)

# Actualizar tsumevault.html
with open('tsumevault.html', 'r', encoding='utf-8') as f:
    content = f.read()
content = re.sub(r"const SW_VERSION = '[^']*'", f"const SW_VERSION = 'tsumevault-{version}'", content)
with open('tsumevault.html', 'w', encoding='utf-8') as f:
    f.write(content)

print(f"Version bumped to: tsumevault-{version}")