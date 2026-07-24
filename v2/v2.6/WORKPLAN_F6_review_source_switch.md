# WORKPLAN — F6: refresco de pendientes post-review + cambio de source desde "pending today"

**Estado: COMPLETADO ✔** (2026-07-23)

## Requisitos
1. Al terminar una Review Run, los contadores de pendientes por source (y el "N due today") deben refrescarse. Antes quedaban stale (72 pending tras resolver 50).
2. Los nombres de source en "pending today" actúan como cambiador de source SIN salir de la pestaña review. El usuario pulsa Start él mismo (no auto-start).

## Cambios en tsumevault.html (4 toques, todos comentados con "F6")
1. **`changeSource(src, { keepTab })`** (junto al viejo handler de `source-sel`, ~L4715): extrae el cuerpo del handler del dropdown. `keepTab=false` (default) conserva el flujo previo exacto (`switchTab('collections')`); `keepTab=true` mantiene la pestaña. Sincroniza el dropdown solo si la opción existe (sources huérfanos de `sm2_state` cambian igualmente sin tocar el dropdown). El handler del dropdown ahora delega en `changeSource`.
2. **`renderGlobalPending()`** (~L3881): filas construidas con `createElement` + `textContent` (sin innerHTML para el nombre → sin superficie XSS nueva). El nombre del source es clicable (`changeSource(source, { keepTab: true })`), salvo el source actual, que se resalta en dorado. Sin acumulación de listeners: las filas se reconstruyen en cada render (cf. patrón T3/3.7).
3. **Fin de sesión de review** (rama no-runMode de `nextProblem`, ~L4046): tras `showSessionEnd()`, llama `renderGlobalPending()` + `refreshReviewMaturity()` (helper nuevo junto a `renderMaturity` que relee el filtro `rv-col` vigente).
4. **Entrada a la pestaña review** (handler de tabs, ~L4680): mismo refresco — cubre staleness causado por runs normales u otros flujos que tocaron SM-2 fuera de la pestaña.

## Validación
- Batería CLIENTE (harness.js contra servidor real, puerto 3488): **82 PASS baseline / 82 PASS post-cambio — TODO OK** en ambas.
- `harness_bundle.js` **byte-idéntico** pre/post (diff vacío): el código de sync no se toca; el riesgo del cambio es puramente de flujo UI.
- Pre-checks: servidor compila, `node --check` de `client_script.js` y del bundle OK.
- Test ad-hoc `test_f6.js` (14 PASS): render de filas, listeners solo en sources no actuales, click cambia source sin `switchTab`, resets de estado completos, dropdown sincronizado, source huérfano, flujo del dropdown intacto.

## Limitaciones de esta sesión
- **Baterías 1 (servidor) y 3 (compat) NO ejecutadas**: `test_server.py` y `harness_compat.js` no se subieron. Justificación de riesgo: `tsumevault_server.py` no se modificó (byte-idéntico) y el bundle de sync del cliente tampoco → esas baterías no pueden cambiar de resultado. Aun así, **ejecutar `run_all.sh` completo en local antes de dar por cerrado** (metodología: ✔ TODO OK sin excepciones).
- `db_schema.sql` fue **reconstruido** en sesión (fixture legacy mínimo: tablas sin uuid/mostrar/índices únicos) solo para arrancar el servidor de la batería 2. NO sustituye al real.
- El mount del proyecto normalizó el HTML a LF; se restauró CRLF (formato real, requerido por `extract_bundle.py`). **El entregable es CRLF** — verificar que el diff local no muestre el archivo entero como cambiado por line endings.

## Entregables en outputs
- `tsumevault.html` (modificado, CRLF)
- `test_f6.js` (test ad-hoc reutilizable; requiere `client_script.js` generado por `extract_bundle.py`)
- Este WORKPLAN

## Fuera de alcance (anotado, no implementado)
- La sesión de review cierra su run pero no dispara `tryAutoSync()` (a diferencia de `endRun`). Comportamiento previo, sin cambios. Candidato a tarea futura si se quiere sync inmediato post-review.
