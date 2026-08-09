# ESTADO — Borrado lógico de problemas (T13) — ✅ TAREA COMPLETADA

Ver WORKPLAN_T13_borrado_logico_FINAL.md para el cierre completo.

Checkpoint de reanudación. Si la sesión se corta, retomar desde la primera fase NO marcada ✅.
Los ficheros modificados hasta el último checkpoint están en /mnt/user-data/outputs/.
Decisiones cerradas con Victor: flag `hidden` (0=visible), runs abiertos conservan ocultos,
deshacer = UPDATE manual en BD servidor, botón con confirmación en Free, problem_count visible
calculado dinámicamente, snapshot manda todo, .db estático = mismo fichero físico, precache SGF
fuera de alcance. Endpoint ÚNICO de merge `/sync/problems_hidden` (aprobado, sustituye al par
individual+bloque del workplan original). Etiqueta de tarea: T13.

## F0 ✅ Baseline: 35/82/8 ✔ TODO OK. Bundle referencia en /tmp/baseline_bundle.js.

## F1 ✅ Esquema (validado 35/82/8 ✔)
- Servidor: helper `_migrate_v2_hidden(con)` antes de `migrate_db()`; guard `>=2` retorna,
  `==1` aplica solo v2; el bloque v1 termina llamando a `_migrate_v2_hidden` (sella 2).
- Cliente: `createSchema()` añade `hidden INTEGER NOT NULL DEFAULT 0` a problems;
  `initDB()` rama IndexedDB añade ALTER idempotente junto al de mostrar;
  `importSnapshot()` usa upsert dedicado para problems (ON CONFLICT preserva hidden local,
  insert fresco toma `r.hidden ?? 0` del snapshot — compatible con servidor viejo).
- test_server.py: expectativa `user_version==1` actualizada a `==2` (avance legítimo de la
  constante de versión por la migración v2, no debilitamiento).

## F2 ✅ Sync — endpoint merge (validado 42/91/8 ✔)
- Servidor: `handle_sync_problems_hidden(body)` — recibe {problems:[{source,problem_id}]},
  marca hidden=1 (unión, nunca 0), responde {hidden:[...todos los ocultos...], updated:N}.
  Ruta PUT `/sync/problems_hidden` en el dict de rutas junto a chapters_mostrar.
- Cliente: en doSync, tras el bloque "── Sync mostrar ──": enviar ocultos locales, aplicar
  respuesta como verdad absoluta (reset a 0 + set lista a 1). try/catch tolerante (404 de
  servidor viejo → no-op).
- Tests: test_server (push+merge+respuesta, entrada inválida 400, unhide manual propaga);
  harness (doSync propaga hidden bidireccional).
- IMPLEMENTADO con semántica de 3 estados en cliente (servidor solo 0/1):
  0=visible, 2=oculto PENDIENTE (lo pone la UI/offline), 1=oculto CONFIRMADO.
  doSync empuja SOLO hidden=2; la respuesta convierte 2->1 y resetea a 0 los
  hidden=1 ausentes de la lista (unhide manual propagado). Motivo: empujar la
  lista completa hacía que clientes ya sincronizados re-ocultaran problemas
  des-ocultados a mano (bug real cazado por el test T13 del harness).
  ⚠ F3 y F4 deben usar: filtro de visibilidad = `hidden=0`; la UI oculta con
  `hidden=2` (NUNCA con 1).

## F3 ✅ Filtrado lecturas (validado 46/96/8 ✔) (ambos lados de cada par, AND hidden=0)
Cliente: localGetProblems, localGetStruggling, localGetReviewProblems, localCountReviewPending,
localGetMaturity, localGetMaturityByLevel, localInsertRun (3 queries), localGetCollections,
localGetChapters, localGetDifficultyRange, y la query de lista lateral de Free (~línea 2523).
Servidor: handle_get_problems (3), handle_get_struggling, handle_get_difficulty_range,
handle_post_run (2), handle_get_collections, handle_get_chapters.
NO tocar: localGetProblem/handle_get_problem, localGetRunItems/handle_get_run_items,
handle_sync_snapshot, precache.
- IMPLEMENTADO: 12 sitios cliente + 9 servidor con `hidden = 0` (excluye 1 y 2).
- Rama `virtual` de handle_post_run NO filtrada a propósito (virtual_items es
  lista curada a mano = intención explícita; documentar como limitación).
- Tests añadidos: 4 servidor (baseline anti-vacuo + exclusión en /db/problems y
  POST /db/run) y 6 harness (T13b: localInsertRun, run_items,
  localCountReviewPending, con guardias anti-test-vacuo en ambos sentidos).

## F4 ✅ UI Free (validado 46/96/8 ✔, bundle byte-idéntico): botón 🚫 junto a #btn-hint, patrón window._study*, confirm() antes de
ocultar, marca hidden=1 local + saveDB + refresca lista/navega + tryAutoSync(true).

## F5 ✅ Contadores visibles (validación FINAL 48/96/8 ✔) "X probs" con COUNT dinámico WHERE hidden=0 (no tocar columna
problem_count almacenada) + validación final + WORKPLAN de cierre.

## Validación por fase: CRLF check, extract_bundle+node --check, bash run_all.sh → ✔ TODO OK.
