import os
import re
import json

# Carpeta donde se ejecuta el script
base_folder = os.getcwd()

# Buscar patrones [IDXXXX]
pattern = re.compile(r'\[ID(\d+)\]')

recorded = []

# Recorrer todas las carpetas y subcarpetas
for root, dirs, files in os.walk(base_folder):
    for file in files:
        if file.lower().endswith('.mp4'):
            match = pattern.search(file)

            if match:
                recorded.append(int(match.group(1)))

# Eliminar duplicados y ordenar
recorded = sorted(set(recorded))

# JSON final
data = {
    "recorded": recorded
}

# Guardar archivo
with open("recorded.json", "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)

print(f"IDs encontrados: {len(recorded)}")
print("Archivo generado: recorded.json")