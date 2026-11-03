# WORKPLAN T32 — Pestaña "By Level": filtro mostrar, PENDING y capítulos fuera

Fecha: 2026-10-26 · Estado: **terminado y validado**

## Requisito (acordado con Victor)

1. Columna **PENDING** = `total − seen` (problemas del objetivo nunca intentados en Run/Review).
2. Checkbox **"Solo capítulos mostrados"** en la cabecera del tab, marcado por defecto y recordado en `localStorage` (`bylevel_only_shown`). Activo: las cifras cuentan solo capítulos con `mostrar=1`. Desmarcado: preview de todo lo ≤ nivel (comportamiento anterior, salvo el punto 3).
3. Los capítulos **sin `diff_avg`** quedan fuera de las cifras, en los dos modos.
4. **Indicador** `⚠ +N cap · M p` junto a TOTAL, solo con el filtro activo, cuando hay capítulos `mostrar=1` (con algún problema visible) fuera de las cifras: por encima del nivel o sin dificultad. Detalle en `title` (escritorio) y en `alert` al tocar (móvil).
5. El 👁 (`applyMostrarUpTo`) **no toca** los capítulos sin dificultad: conservan su `mostrar`.
6. Mastery sin cambios (By Level sobre el total; Review sobre lo visto).

Fuera de alcance: agrupado de niveles por `ROUND(diff_avg/100)` y capítulos sin dificultad (fase de dificultades), Mastery de Review.

## Cambios en `tsumevault.html`

| Zona (línea aprox.) | Cambio |
|---|---|
| HTML `#stats-pane-bylevel` (~1443) | Barra con el checkbox `#bl-only-shown` |
| Tras `bylevelLoad` (~3996) | `BYLEVEL_ONLY_SHOWN_KEY` + `bylevelOnlyShown()` |
| `localGetMaturityByLevel` (~4003) | 3er parámetro `onlyShown`; CTE `visible`: `diff_avg IS NOT NULL AND diff_avg <= ?` y `(? = 0 OR ch.mostrar = 1)` |
| Nueva `localGetByLevelOutside` (~4071) | Capítulos `mostrar=1` con algún problema `hidden=0` por encima del nivel o sin dificultad |
| `applyMostrarUpTo` (~4086) | Rama `WHEN diff_avg IS NULL THEN mostrar`; comentario R1 actualizado |
| `renderByLevel` (~4124) | Enlace del checkbox (patrón `dataset.bound`); `<th>` PENDING; `<td id="bylevel-pend-…">`; eliminadas `PCT_YELLOW`/`color`, que no se usaban |
| `bylevelUpdateRow` (~4237) | Pasa `onlyShown`; rellena PENDING; indicador con `createElement`/`textContent` |

## Cambios en `harness.js` (autorizados por Victor)

- Escenario R1: la expectativa pasa a `ch4 → mostrar 0` y `shown=2, hidden=2`.
- Nueva guardia anti-test-vacuo `R1 (T32)`: un capítulo sin dificultad con `mostrar=1` sigue en 1 y el de `mostrar=0` sigue en 0 tras re-aplicar.

## Validación

- CRLF: 7300 CRLF, 0 LF sueltos, 0 CR sueltos (verificado por bytes).
- `extract_bundle.py` + `node --check client_script.js`: OK.
- `diff harness_bundle.js` contra la base: solo cambia `applyMostrarUpTo` (las 2 líneas del `CASE`).
- `run_all.sh` con el `test_server.py` vigente (J2, espera `user_version = 4`): **servidor 137 PASS · cliente 133 PASS · compat 8 PASS · ✔ TODO OK**.
  - Cliente: 132 → 133 (la guardia nueva de R1).
  - Primera pasada con la copia antigua de `test_server.py` del proyecto: 1 FAIL previo a T32 (esperaba v3); salida idéntica antes y después del cambio.
- Prueba aislada de queries (sql.js real, `test_t32.js`): 10/10, incluida una guardia que demuestra que con el código anterior el capítulo sin dificultad sí pasaba a 1.
- Smoke test DOM (jsdom, `dom_t32.js`): 11/11. Cabecera, checkbox por defecto y sin re-enlazar, filtro/preview, PENDING, indicador (texto, detalle, toque) y cambio de nivel sin acumular indicadores.

## Notas y limitaciones

- `test_server.py` del proyecto actualizado a la versión vigente (J2).
- **`SW_VERSION` no se ha tocado.** Si el service worker cachea `tsumevault.html`, puede hacer falta subirlo para que los dispositivos reciban el cambio.
- Hasta que se asigne dificultad a todos los capítulos, los que no la tienen no cuentan en By Level aunque estén en Review y Collections. El indicador los muestra.
- Observado y no tocado: en `renderByLevel`, el bucle final busca `'bylevel-sel-' + source` sin `esc()`, a diferencia del resto (T10). Inofensivo con nombres de fuente normales.
