import os
import re
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # raíz del repo (este script está en tools/)

version = datetime.now().strftime('%Y%m%d-%H%M')

# Actualizar sw.js
with open(os.path.join(ROOT, 'sw.js'), 'r', encoding='utf-8') as f:
    content = f.read()
content = re.sub(r"const CACHE_VERSION = '[^']*'", f"const CACHE_VERSION = 'tsumevault-{version}'", content)
with open(os.path.join(ROOT, 'sw.js'), 'w', encoding='utf-8') as f:
    f.write(content)

# Actualizar tsumevault.html
with open(os.path.join(ROOT, 'tsumevault.html'), 'r', encoding='utf-8') as f:
    content = f.read()
content = re.sub(r"const SW_VERSION = '[^']*'", f"const SW_VERSION = 'tsumevault-{version}'", content)
with open(os.path.join(ROOT, 'tsumevault.html'), 'w', encoding='utf-8') as f:
    f.write(content)

print(f"Version bumped to: tsumevault-{version}")