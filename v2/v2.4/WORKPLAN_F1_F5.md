# WORKPLAN F1–F5 — Mejoras funcionales (auditoría §12.1–12.5)

Si la sesión se corta, retomar desde la primera NO marcada [x].
Directorio: /home/claude/tsumevault. Línea base: 35/73/8 ✔ (md5 html 8aba65a3).
Todo es CLIENTE salvo indicación; el protocolo de sync NO se toca.
Checkpoint a outputs tras cada mejora.

## Decisiones de diseño (tomadas por el arquitecto, documentar en STATUS)
- F1 (indicador pendientes): contador `attempts synced=0 (con uuid)` + `runs
  synced<>1 (con uuid)`; badge junto al estado de sync del header/config;
  refresco tras cada intento y tras cada sync (hook en setSyncStatus +
  scheduleSaveDB path). Cero consultas al servidor.
- F2 (pausa en fallo en runs): en runMode, un fallo YA NO auto-avanza a 1 s;
  el comentario de refutación queda visible y se avanza al tocar el tablero
  (o botón). Free practice no cambia (allí ya se podía reintentar).
- F3 (second chance): toggle en config (localStorage 'second_chance', default
  OFF). En runMode con fallo, el problema entra en una cola de repesca EN
  MEMORIA (retryQueue, dedupe por problem_id: UNA repesca por problema).
  Al agotar runItems se sirve la cola antes de endRun, con indicador visual.
  Los intentos de repesca se registran con run_id=NULL: el attempt cuenta en
  historial/SM-2 pero NO incrementa done, NO reescribe run_items (el wrong
  original es la verdad del run) y NO puede cerrar/falsear el run.
- F4 (heatmap): agregado `substr(created_at,1,10)` (día UTC; nota: los
  timestamps del protocolo son UTC — bucketing de visualización, desvío ±2h
  asumido y documentado), últimas 26 semanas, grid 7×26 en el modal de stats,
  5 niveles de color por umbrales fijos (0 / 1-4 / 5-14 / 15-29 / 30+).
- F5 (evolución de madurez): tabla LOCAL daily_stats(date, source, dominated,
  seen, total) NO sincronizada (analítica local); snapshot INSERT OR REPLACE
  por (date, source) al terminar sesión (endRun y fin de review/FP) con los
  mismos agregados que renderMaturity; gráfica SVG de línea (dominated en el
  tiempo) en el modal de stats. Migración: CREATE TABLE IF NOT EXISTS en
  migrateSyncColumns + createSchema.

## Estado
- [x] F1 — indicador de pendientes de sync
- [x] F2 — pausa en fallo durante runs (comentario visible hasta tap)
- [x] F3 — second chance configurable (cola de repesca)
- [x] F4 — heatmap de actividad en stats
- [x] F5 — daily_stats + gráfica de evolución de madurez
- [x] Cierre: STATUS (sección 12 parcial: 1-5 [x], 6-10 [ ]), run_all final,
      entrega completa.

## Notas acumuladas

- F1: countPendingSync + updatePendingBadge; badge en boton config + detalle en modal; hooks en setSyncStatus, recordAttempt e init. Escenario F1 en arnes (+2). 
- F2: tapToAdvance; showResult no auto-avanza en run+fallo (hint 'Tap board to continue'); click handler avanza; reset en nextProblem.
- F3: retryQueue/retryQueued/retryPhase; encolado en showResult (dedupe, sin reveals ni retries); servido en nextProblem antes de endRun; loadAndRender propaga _isRetry con indicador; recordAttempt con run_id NULL en repescas y sin tocar runItems; resets en arranque de run, resumeRun y endRun; toggle cfg-second-chance (default OFF).

- F4: tab Activity nuevo en el modal de stats; heatmap 26 semanas alineado a lunes, niveles 0/1-4/5-14/15-29/30+, resumen de totales; dia UTC documentado.
- F5: daily_stats en createSchema + migracion idempotente; snapshotDailyStats desde localGetMaturity (dominated/total_seen/total_visible) con fecha LOCAL; hooks en endRun y fin de review/FP; grafica SVG con 3 series y estado vacio explicativo. Escenario F5 en arnes (+2). Suite final 35/77/8 TODO OK. TRABAJO F1-F5 COMPLETADO.
