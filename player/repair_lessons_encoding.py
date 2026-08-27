#!/usr/bin/env python3
"""
repair_lessons_encoding.py - Corrige doble-codificacion UTF-8 en all_lessons.json

Problema: algunos textos (nombres, sufijos, descripciones) se generaron con un
caracter acentuado en UTF-8 (p.ej. "c" -> bytes C3 A7) que luego se
reinterpreto como Latin-1 y se re-codifico a UTF-8, dando dos caracteres
en vez de uno: "A" + seccion" (U+00C3 + U+00A7) en vez de "c" (U+00E7).

Como el JSON usa escapes \\uXXXX para todo lo no-ASCII (ensure_ascii),
el patron corrupto aparece literalmente como la secuencia de 12 caracteres:
    \\u00c3\\u00XX   (XX entre 80 y bf en hexadecimal)

Esto cubre CUALQUIER caracter Latin-1 doble-codificado de esta forma, no
solo "c" (tambien "e", "a", "n", "u", etc.), calculando el codepoint
correcto: YY = XX + 0x40.

Uso:
    python3 repair_lessons_encoding.py all_lessons.json            # dry-run
    python3 repair_lessons_encoding.py all_lessons.json --apply    # escribe

Dry-run muestra cada coincidencia con contexto, sin tocar el fichero.
--apply hace backup (.bak) antes de escribir.
"""
import io
import re
import sys

PATTERN = re.compile(r'\\u00c3\\u00([89ab][0-9a-f])', re.IGNORECASE)


def fix(match: 're.Match') -> str:
    xx = int(match.group(1), 16)
    yy = xx + 0x40
    return f'\\u{yy:04x}'


def context(text: str, start: int, end: int, pad: int = 40) -> str:
    lo = max(0, start - pad)
    hi = min(len(text), end + pad)
    return text[lo:hi].replace('\n', '\\n')


def main() -> None:
    if len(sys.argv) < 2:
        print("Uso: python3 repair_lessons_encoding.py all_lessons.json [--apply]")
        sys.exit(1)

    path = sys.argv[1]
    apply = '--apply' in sys.argv[2:]

    text = io.open(path, encoding='utf-8', newline='').read()

    matches = list(PATTERN.finditer(text))
    if not matches:
        print("Sin coincidencias. No hay nada que arreglar.")
        return

    print(f"Encontradas {len(matches)} coincidencias de doble-codificacion:\n")
    for m in matches:
        before = m.group(0)
        after = fix(m)
        print(f"  {before}  ->  {after}    ...{context(text, m.start(), m.end())}...")

    if not apply:
        print("\nModo dry-run (por defecto). Relanza con --apply para escribir los cambios.")
        return

    backup_path = path + '.bak'
    io.open(backup_path, 'w', encoding='utf-8', newline='').write(text)
    print(f"\nBackup guardado en: {backup_path}")

    new_text = PATTERN.sub(fix, text)
    io.open(path, 'w', encoding='utf-8', newline='').write(new_text)
    print(f"Aplicado. {len(matches)} coincidencias corregidas en: {path}")


if __name__ == '__main__':
    main()
