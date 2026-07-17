# WORKPLAN T1–T7 — Ejecución por el arquitecto

Si la sesión se corta, retomar desde la primera tarea NO marcada [x].
Specs completas de cada tarea: TAREAS.md (en outputs y en el proyecto).
Directorio: /home/claude/tsumevault. Si el contenedor se reseteó: los archivos
más recientes están en /mnt/user-data/outputs (el md5 del html al inicio de
T1 era 13f8af63; cada checkpoint actualiza outputs).

Validación: bash run_all.sh → "✔ TODO OK". Línea base confirmada: 32/60/8.
Plan de validación: run_all completo tras T2 (añade escenario), T4 (añade
escenario) y T7 (cierre); sintaxis (extract_bundle + node --check) tras cada
tarea. Checkpoint a outputs tras cada tarea: tsumevault.html + este archivo
(+ harness.js/extract_bundle.py si cambiaron + IMPLEMENTATION_STATUS.md al final).

## Estado
- [x] T1 — 3.5 sessionOk doble (playOpponent vs recordAttempt)
- [x] T2 — 3.6 zona horaria (localDateStr en localGetReviewProblems,
      localCountReviewPending, updateSm2) + escenario arnés
- [x] T3 — 3.7 listeners acumulativos (fp-col, fp-start, rv-col, rv-start
      + barrido de otros populate*/render*/load*) con guard dataset.bound
- [x] T4 — 3.8 review runs (startReview total=N + limpiar activeRunId al
      terminar la review) + escenario arnés
- [x] T5 — 3.9 resize (redibujar sin resetear estado lógico + debounce 200ms)
- [x] T6 — 3.10 botón sync delegando en tryAutoSync + timers centralizados
- [x] T7 — 3.12a resumeRun de run completado (cerrar + avisar, no rejugar)
- [x] Cierre: IMPLEMENTATION_STATUS.md (marcar 3.5–3.9, ampliar 3.10/3.12 a
      parcial/completado según corresponda), run_all final, entrega completa.

## Notas acumuladas
(decisiones tomadas durante la ejecución)

- T1: unico duplicado era playOpponent rama sin-hijos (3918); 3913/3914 correctos. sessionNo no tiene duplicados (solo recordAttempt linea 3900).
- T2: localDateStr junto a makeUUID; aplicado en las 2 funciones de review y en updateSm2 (today + calculo de due, ambos en local; updated_at sigue UTC). Bundle ampliado con localDateStr y localCountReviewPending. Suite 32/62/8 OK.
- T3: guards dataset.bound en los 4 listeners (fp-col/fp-start/rv-col/rv-start). Barrido completo con analisis de funcion contenedora: el resto de getElementById().addEventListener son top-level init (1 sola vez); gmInitControls se llama 1 vez. Closures verificados: los 4 handlers leen estado en el momento del evento.
- T4: startReview con total=problems.length; fin de sesion (nextProblem rama !runMode) cierra review abierta si procede y suelta activeRunId (startFreePractice ya limpiaba). Sin migracion de historicos (decision spec). Escenario T4 en arnes (3 checks). Suite 32/65/8 OK.
- T5: hook window._studyRedraw (closure: redrawFromGame + renderLabels(currentNode)); resize = initBoard + rehidratar (el click sobrevive via _boardClickHandler global que initBoard re-registra); guard gmActive (no repintar problemas sobre el visor); hook invalidado en showSessionEnd; debounce 200ms ya existia. Casos verificados: (a) resize sin tocar = repinta setup; (b) a mitad de secuencia = posicion+labels intactas, 0 attempts nuevos; (c) tras fallo registrado = hadWrong/attemptRecorded viven en el closure superviviente, 0 attempts extra.
- T6: boton delega en tryAutoSync(false) conservando exclusivos (loadCollections, refresh runItems, loadRuns, alert via lastSyncError); guard de lectura contra alert obsoleto en doble click; setSyncStatus con temporizador unico cancelable. tryAutoSync solo gana 2 asignaciones a lastSyncError (firma y semantica intactas, arnes no afectado).
- T7: resumeRun con firstPending===-1 → cerrar si open + avisar + loadRuns, sin tocar activeRunId/runMode; cubre review runs sin run_items; clamp antiguo eliminado (ya innecesario). Escenario T7 (4 checks). Suite final 32/69/8 TODO OK. TRABAJO T1-T7 COMPLETADO.
