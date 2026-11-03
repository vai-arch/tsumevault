# T35 — Bulk tag (etiquetado en bloque desde Free)

## Requisito
Añadir o quitar una etiqueta a un conjunto de problemas a la vez, reutilizando los filtros de la pestaña Free.
Decisiones: modal aparte; añadir Y quitar; crear la etiqueta desde el panel; solo confirmación (sin límite duro).

## Cambios (solo `tsumevault.html`)
- `freeFilteredProblems()` (nueva, ~l.5097): cuerpo de filtrado extraído de `startFreePractice` sin cambios de lógica; devuelve `{ problems, order }`.
- `startFreePractice` (~l.5147): llama a `freeFilteredProblems()`; resto (0 resultados, barajado, arranque) intacto.
- Botón `#fp-bulk` "🏷 Bulk tag…" bajo "Start practice" (~l.1612), `onclick="openBulkTag()"`.
- Modal `#bt-overlay` (~l.1474, antes de `#mob-overlay`): resumen, campo de etiqueta + datalist, Add / Remove, Select all / None, lista.
- Bloque JS `// ══ T35: BULK TAG ══` antes de `// ══ REVIEW ══` (~l.5168): `openBulkTag`, `closeBulkTag`, `onBulkTagOverlayClick`, `renderBulkTagTagList`, `renderBulkTagList`, `updateBulkTagSummary`, `btSelectAll`, `applyBulkTag`.
- Escape: `closeBulkTag()` añadido a la línea de `keydown`.

## Diseño
- Selección en un `Set` (clave `source\u0001problem_id`), por defecto todo marcado; la lista pinta máx. 500 filas, el resto queda incluido salvo "None".
- Aplicar: una consulta para saber quién ya tiene la etiqueta, `confirm()`, bucle de `localSetProblemTag` dentro de `BEGIN/COMMIT` (ROLLBACK si falla), un único `scheduleSaveDB()` + `refreshTagViews()` + `tryAutoSync(true)`.
- Quitar solo actúa sobre los que la tienen activa (tombstone `active=0`, LWW como siempre).
- La etiqueta nueva se crea vía `localSetProblemTag` (`INSERT OR IGNORE` en `tags`). `normTag` normaliza espacios; `tag` es NOCASE.
- El `onkeydown` del modal hace `stopPropagation` para que los atajos globales (P, Espacio, Enter) no interfieran al escribir.
- DOM con `createElement`/`textContent`; sin HTML dinámico.

## No tocado
`doSync`, `localSetProblemTag`, `localGetProblems`, servidor, tests, `extract_*.py`, `run_all.sh`. Ninguna función de los `grab()` de `extract_bundle.py` / `extract_tags.py` fue modificada.

## Validación
- CRLF byte a byte: 7073 CRLF, 0 LF sueltos.
- `node --check` del script principal: OK.
- Prueba de humo desechable (sql.js 1.10.2, código REAL extraído; NO incluida en el proyecto): 28 PASS / 0 FAIL — filtro Free (source, all-sources, ID parcial, ocultos), modal con 600 (>500) problemas, add/remove, re-add sin cambios, NOCASE, tag nuevo normalizado, confirm cancelado, ROLLBACK a mitad del bucle, DB operativa tras rollback, alertas de entrada inválida.
- NO ejecutado aquí: `run_all.sh` y baterías (no hay servidor ni harness en este entorno). Pendiente en tu máquina; al ser cambio de UI, `harness_bundle.js` debe quedar byte-idéntico.

## Limitaciones / observaciones
- Push grande: un bulk de miles de filas va en un único POST a `/sync/problem_tags/push` con timeout de 8 s en el cliente. Si se agota, las filas siguen en `synced=0` y se reintentan en el siguiente sync (sin pérdida). Probar primero con unos miles. Trocear exigiría tocar `doSync` (fuera de alcance).
- El bucle es síncrono: con muchos miles de filas la UI se congela 1–2 s.
- Observación fuera de alcance (NO arreglada): el `keydown` global hace `preventDefault()` en `KeyP` sin comprobar si el foco está en un `<input>`; parece impedir escribir la letra "p" en otros campos de texto (p. ej. `#cfg-tag-new`, `#fp-problem-id`). El modal nuevo lo evita con `stopPropagation`.

---
# T36 — 🧩 de Collections vuelve a quedarse en los filtros de Free
- `practiceChapterFree` (~l.5080): eliminada la llamada `await startFreePractice();` tras `switchTab('free')`; comentario F9/F11 actualizado. La precarga de colección+capítulo y la limpieza de filtros no cambian.
- Causa: el fichero recibido ya incluía esa llamada (no la introdujo T35).
- Validación: CRLF 0 LF sueltos, `node --check` OK, prueba de humo T35 sigue en 28 PASS. Cambio solo de UI; no toca código de sync. Pendiente en tu máquina: baterías habituales.
