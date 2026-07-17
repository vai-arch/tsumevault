# TsumeVault v2 Progress

## Completed

- 3.1 Push del historial completo + duplicación local de attempts
- 3.2 syncDeletedRuns borra runs offline no pusheados
- 3.3 purgeEmptyRuns envía ids locales al servidor
- 3.4 Ventana de pérdida de hasta 9 intentos
- 3.5 Doble incremento de sessionOk en Free Practice
- 3.6 Regresión de zona horaria en Review (fechas de review en base local vía localDateStr; timestamps del protocolo siguen en UTC)
- 3.7 Listeners acumulativos (registro único con guard en fp-col/fp-start/rv-col/rv-start; barrido completo: el resto de listeners persistentes son de init único)
- 3.8 Runs de review inconsistentes (total real en startReview; cierre y liberación de activeRunId al terminar la sesión; sin migración de históricos)
- 3.9 Resize resetea el problema en curso (rehidratación vía window._studyRedraw sin reconstruir el estado del intento; visor de partidas excluido)
- 4.5 / R11 XSS almacenado en el cliente (esc() aplicado a todas las interpolaciones de datos en innerHTML: nombres de colecciones/capítulos/runs, sources, mensajes de error; ids dinámicos coherentes en atributo y lookup; verificador check_esc.js)
- Cursores en sync_meta (tabla en la DB del cliente: datos y cursores viven, mueren y se persisten ATÓMICAMENTE juntos; migración con import único desde localStorage; cierra también el reset parcial que la corrección mínima no cubría)
- 4.1 Autenticación (X-Auth-Token) + CORS restringido + verificación de Origin
- 4.2 DoS estructural (ThreadingHTTPServer + timeout de socket + límite de body 10 MB)
- 4.3 Fuga de información (500 sin detalle interno, sin bodies en logs, sync_push_log.json eliminado)
- R1 Sync v2: pendientes marcados + dedup por uuid en pull + índices uuid
- R5 Auth token + CORS restringido + ThreadingHTTPServer + límites

## Partially completed

- 3.10 Carreras de sincronización — implementado SOLO: (a) cursor SM-2 fijado con el mayor `updated_at` confirmado, nunca con el reloj del cliente; (b) los cursores de sync (pull attempts/runs y SM-2) se persisten únicamente tras un `saveDB()` exitoso, para que ningún cursor adelante a la DB persistida; (c) `>=` en la frontera del cursor SM-2 (cliente y servidor) para no excluir registros escritos en el mismo segundo. Implementado también (T6): el botón de sync delega en tryAutoSync (sección crítica única) y setSyncStatus usa un temporizador único cancelable. NO implementado: transaccionalidad completa de doSync.
- 3.11 Errores silenciosos y validación — lado servidor completo: validación de campos y tipos en `/sync/push`, `/sync/sm2/push`, `/sync/chapters_mostrar`, `PUT /db/run` (400 si falta `status`), `POST /db/attempt` (result ∈ {correct,wrong}); `_read_body` con JSON malformado → 400 y Content-Length inválido → 400/413 (antes colgaba la conexión); parámetros malformados → 400 genérico; 500 sin `str(e)`. NO implementado: los `catch (e) { }` vacíos del cliente (limpieza fuera del alcance de esta fase).
- 4.4 CSRF / manipulación de parámetros — Origin verificado en escrituras y token; `mostrar` normalizado a 0/1 en `/sync/chapters_mostrar`. Validación exhaustiva de rangos en los endpoints CRUD muertos no abordada.
- 4.6 BAJA / N.A. — `local_ip` ya no impide arrancar el servidor. `sgf_path` verificado: NO toca el filesystem del servidor (solo SELECT/INSERT en DB; los SGF los sirve el hosting estático), así que no procede validación de rutas en el servidor.
- 5.1 Cliente, puntos calientes — P2 corregido (push solo de pendientes), fase A de R3 (saveDB debounced) y P3 (struggling en una query con window function, equivalencia en compare_struggling.js; ídem servidor). P1 completo (DB fría/caliente) y P4-P9 no.
- 5.2 Servidor — índices `idx_attempts_uuid`/`idx_runs_uuid` creados (los lookups del push dejan de ser full scans); `sync_push_log.json` fuera del hot path. Caché del snapshot gzip no implementada.
- 6.2 Problemas del schema — índices únicos parciales sobre uuid añadidos (cliente, servidor y `db_schema.sql`); migración automática con dedup previo de duplicados históricos. `idx_chapters_mostrar`, `virtual_*` y fechas sin tocar.
- 8 BACKEND — ThreadingHTTPServer, logging con niveles, validaciones, dispatch unificado de POST/PUT mediante tablas de rutas, arranque robusto. schema_version formal (PRAGMA user_version, migraciones históricas selladas como v1) y apagado limpio SIGTERM/SIGINT (shutdown desde hilo aparte + server_close) implementados. Sin HTTP/1.1 keep-alive (decisión conservadora: no cambiar semántica de conexión a través de Caddy sin poder probarla en producción).
- R3 Persistencia fiable — fase A completa (saveDB debounced tras cada intento + flush en visibilitychange/pagehide). Fase B (split DB fría/caliente) no.
- 3.12 Otros — resueltos: resumeRun de run completado, bare columns (6 queries reescritas a SQL estándar con equivalencia verificada en compare_queries.js) y AE en getSetupStones. Pendientes: PK de run_items (requiere rebuild), resolución de segundo en dedup sin uuid, SFX iOS.
- R10 Purga de endpoints + logging + validación — logging y validación sí; los endpoints muertos NO se eliminan (prohibido en esta fase), solo la ruta por ids de `/db/runs/delete` queda marcada con TODO.

## Not implemented

- 1.1–1.5 Arquitectura general (descriptivo; la reorganización propuesta es Fase 2)
- 2.1–2.5 Calidad del código (duplicación, funciones largas, código muerto, nombres, acoplamiento)
- 4.5 XSS almacenado en el cliente (R11)
- 4.7 Tabla resumen (descriptivo)
- 5.3 Red (mostrar/games completos en cada sync, ETag)
- 5.4 Renderizado/DOM
- 6.1 Divergencia de schemas y unificación de tipos (R9; prohibido salvo bug crítico)
- 6.3 Escalabilidad del schema (agregados materializados)
- 7.1–7.5 Frontend (CSS inline, accesibilidad, estado, memoria, UX)
- 9 API endpoint por endpoint (inventario)
- 10 Código innecesario (borrado prohibido en esta fase)
- 11 Escalabilidad (bootstrap paginado, pull paginado)
- 12 Mejoras funcionales — implementadas 1–5: (1) indicador de pendientes de sync (badge en el header + detalle en config, basado en la columna synced, cero red); (2) pausa en fallo durante runs con el comentario de refutación visible hasta tocar el tablero; (3) second chance configurable (cola de repesca al final del run; los reintentos se registran con run_id NULL: cuentan en historial/SM-2 sin falsear el run); (4) heatmap de actividad (26 semanas, día UTC documentado) en el nuevo tab Activity del modal de stats; (5) tabla local daily_stats (no sincronizada) con snapshot por (día local, source) al cerrar sesión + gráfica SVG de evolución (dominated/seen/total). Pendientes 6–10: export manual, filtro de tiempo en FP, runs virtuales, atajos U/R, soft-delete (=R2).
- R2 Soft-delete de runs (los bugs 3.2/3.3 se corrigieron por la vía conservadora sin cambiar el modelo de borrado)
- R4 Registro único de listeners
- R6 Capa repo.js
- R7 Máquina de estados de sesión
- R8 Modularizar el monolito
- R9 Unificar tipos
- R11 Escapado HTML sistemático
- R12 Queries N+1 → window functions
- 14 Calidad profesional (evaluación, descriptivo)

Checklist completa de la auditoría:

- [ ] 1.1  [ ] 1.2  [ ] 1.3  [ ] 1.4  [ ] 1.5
- [ ] 2.1  [ ] 2.2  [ ] 2.3  [ ] 2.4  [ ] 2.5
- [x] 3.1  [x] 3.2  [x] 3.3  [x] 3.4  [x] 3.5  [x] 3.6  [x] 3.7  [x] 3.8  [x] 3.9  [~] 3.10  [~] 3.11  [~] 3.12
- [x] 4.1  [x] 4.2  [x] 4.3  [~] 4.4  [x] 4.5  [~] 4.6  [ ] 4.7
- [~] 5.1  [~] 5.2  [ ] 5.3  [ ] 5.4
- [ ] 6.1  [~] 6.2  [ ] 6.3
- [ ] 7.1  [ ] 7.2  [ ] 7.3  [ ] 7.4  [ ] 7.5
- [~] 8
- [ ] 9  [ ] 10  [ ] 11  [~] 12
- [x] R1  [ ] R2  [~] R3  [x] R4  [x] R5  [ ] R6  [ ] R7  [ ] R8  [ ] R9  [~] R10  [x] R11  [~] R12
- [ ] 14

## Decisions

1. **Semántica de `synced`** (columna nueva en cliente, `INTEGER DEFAULT 0`):
   - `attempts.synced`: 0 = pendiente de push, 1 = confirmado por el servidor. Los attempts son inmutables: una vez confirmados no vuelven a enviarse.
   - `runs.synced`: 0 = nunca pusheado, 1 = pusheado y sin cambios, 2 = pusheado pero modificado después. Los runs mutan tras el push (done, status, run_items) y el servidor actualiza runs existentes, así que un run "sucio" (2) se re-envía hasta quedar limpio. `localInsertAttempt` y `localUpdateRunStatus` marcan 1→2.
   - Tras un push exitoso se marca `synced=1` SOLO lo enviado en ese push (por lista de ids, en chunks de 400): los intentos creados con el push en vuelo conservan 0. Un run solo pasa a 1 si sus `done`/`status` no cambiaron durante el vuelo.
2. **Backfill conservador**: los datos existentes quedan con `synced=0`, de modo que el primer sync tras actualizar re-envía el historial una única vez (el servidor deduplica por uuid, como hasta ahora) y lo deja marcado. Sin pasos manuales.
3. **Dedup en pull por índice único**: `CREATE UNIQUE INDEX ... ON attempts(uuid) WHERE uuid IS NOT NULL` (ídem runs) hace que el `INSERT OR IGNORE` existente deduplique también por uuid, cerrando la vía de duplicación de estadísticas de 3.1 sin reescribir el pull. La migración (cliente y servidor) elimina primero duplicados históricos conservando el registro más antiguo y repuntando attempts/run_items al run conservado.
4. **Cursores de pull persistentes**: se añade `last_pull_attempt_id`/`last_pull_run_id` (localStorage) porque el cursor antiguo (`MAX(id) WHERE uuid IS NULL`) no avanzaba con filas con uuid y cada pull re-descargaba el mismo rango. El cursor avanza SOLO con ids realmente recibidos en el pull — nunca con los `server_id` del push, que podrían saltarse filas intermedias de otros dispositivos. El heurístico antiguo se conserva como suelo (si se borra localStorage, se re-descarga una vez y el dedup lo absorbe).
5. **Cursores tras persistencia**: todos los cursores (pull y SM-2) se escriben en localStorage únicamente después de un `saveDB()` exitoso. Si `saveDB` falla, el siguiente sync repite el rango (inocuo por dedup/LWW) en lugar de saltárselo para siempre.
6. **Cursor SM-2 sin reloj de cliente** (3.10 parcial, según lo aprobado): avanza al mayor `updated_at` recibido del servidor o confirmado en el push; no avanza si el push falla. Frontera con `>=` en el push del cliente y en el pull del servidor: re-recibir/re-enviar el registro frontera es un no-op (LWW) y elimina la exclusión de registros escritos en el mismo segundo que el cursor.
7. **`run_uuid` en cada attempt** (protocolo nuevo): permite al servidor resolver el run de un attempt aunque el run ya no viaje en el payload (consecuencia de enviar solo pendientes). El servidor conserva íntegros los fallbacks del protocolo antiguo.
8. **purgeEmptyRuns**: además de pasar a uuids (3.3), se añade `done = 0` al criterio y se excluye el run activo. Motivo: los runs de review no tienen run_items, por lo que el criterio anterior (“0 run_items con resultado”) los consideraba vacíos y borraba runs con historial válido — exactamente la clase de borrado que esta fase debe eliminar. Los runs sin uuid solo se eliminan localmente.
9. **syncDeletedRuns**: excluye runs nunca pusheados (`synced=0`) y se ejecuta únicamente tras un push exitoso en la sesión (antes corría antes del primer sync). Riesgo residual documentado: un run borrado en el servidor mientras otro dispositivo lo tiene “sucio” puede resucitar al re-pushearse; eliminarlo del todo requiere soft-delete (R2, Fase 2). Es el lado conservador correcto: ante la duda, no borrar.
10. **Servidor multihilo con lock global**: `ThreadingHTTPServer` (una conexión lenta ya no congela el servicio) + `threading.Lock` alrededor de todo acceso SQLite, preservando exactamente la serialización previa: cero carreras SQL nuevas.
11. **Auth opt-in por entorno**: `TSUMEVAULT_TOKEN` sin definir = auth desactivada (nada se rompe al desplegar); definido = 401 sin cabecera correcta. Orígenes CORS/Origin configurables con `TSUMEVAULT_ORIGINS` (por defecto GitHub Pages + localhost). Peticiones sin cabecera Origin (scripts propios, curl) se permiten en escrituras: el token es la barrera real; el Origin corta el CSRF desde navegador.
12. **Token en el cliente**: campo nuevo en el modal de configuración (localStorage `sync_token`); vacío = sin cabecera. Todas las llamadas al servidor de sync pasan por un único `syncFetch()`.
13. **db_schema.sql** actualizado con los dos índices únicos (solo documental: la migración automática del servidor los crea en instalaciones existentes, con dedup previo).
14. **CHECKs**: SQLite no permite añadir CHECK a tablas existentes sin reconstruirlas (riesgo prohibido en esta fase); la validación equivalente se hace en el código del servidor (400) y los CHECK quedan para el schema de instalaciones nuevas en Fase 2 si se decide reconstruir tablas.
15. **Validación**: servidor y cliente modificados verificados con baterías automatizadas: 35 comprobaciones de servidor (migración, dedup, auth, CORS, Origin, límites, 400/413, run_uuid en pull), 82 escenarios de cliente ejecutando el código real extraído del HTML contra el servidor real (instalación desde cero, actualización con datos duplicados históricos, crear/resolver/cerrar runs, reinicio, sync doble, dos dispositivos, creación offline y reconexión, purga, borrado propagado, review-run protegido, SM-2, token, y reset de DB con cursores huérfanos en localStorage, colisión de ids servidor/local con remapeo por uuid, fechas de review en base local, coherencia de runs de review, y resumeRun de runs completados), y 8 comprobaciones de convivencia cliente antiguo ↔ servidor nuevo ↔ cliente nuevo. Todas en verde.
16. **Cursores huérfanos** (corrección posterior aprobada): localStorage y la DB del navegador (IndexedDB) tienen ciclos de vida independientes; tras un reset de la DB, los cursores antiguos apuntaban por delante de los datos y el pull no recuperaba el historial. Ahora, si la tabla local correspondiente está vacía, el cursor guardado se ignora (equivale a 0): `last_pull_attempt_id`/`attempts`, `last_pull_run_id`/`runs` y `last_sm2_sync`/`sm2_state` — este último era un defecto preexistente a la Fase 1. Al terminar el sync el cursor se reescribe con el valor correcto (autocurativo). Un reset parcial (DB no vacía pero por detrás de los cursores) no queda cubierto; la solución completa es mover los cursores a una tabla `sync_meta` dentro de la propia DB (Fase 2).

17. **Los ids del servidor ya no se reutilizan como PK local** (corrección posterior aprobada; resuelve la colisión de ids preexistente): en el pull, las filas con uuid se insertan con autoincrement local y toda la correlación pasa a ser por uuid — el servidor añade `run_uuid` a cada attempt del pull (LEFT JOIN) y el cliente remapea `run_id` al id local del run (procesando runs antes que attempts, con caché por lote). Antes, una fila del servidor cuyo id ya estaba ocupado por un id local autoincrement (datos creados en el dispositivo antes de su primer sync) se descartaba en silencio y no volvía jamás, porque el cursor avanzaba igual. Reglas del remapeo: run_uuid con valor → id local por uuid (NULL si el run no existe localmente); run_uuid null → `a.run_id` solo si existe un run local con ese id y sin uuid (runs legacy conservan el id del servidor por construcción); clave `run_uuid` ausente (servidor antiguo) → `a.run_id` tal cual (semántica previa, solo transición). Las filas legacy sin uuid conservan íntegro el comportamiento anterior. El arreglo es retroactivo: un reset de los cursores de pull re-descarga y recupera las filas antes colisionadas, sin borrar la DB.

18. **Lote T1–T7 (bugs de la auditoría 3.5–3.9, 3.10 UI y 3.12a)**: detalle de decisiones en WORKPLAN_T1_T7.md. Destacables: las fechas de review usan día local (localDateStr) manteniendo los timestamps del protocolo en UTC; el fin de sesión de review cierra el run si quedó abierto (problemas saltados) además de liberar activeRunId; la rehidratación del resize excluye el visor de partidas (gmActive); resumeRun trata los runs sin items pendientes (incluidos los de review, sin run_items) como no reanudables y los cierra; los runs de review históricos incoherentes (done>total) se dejan como están.

19. **Lote T8–T12** (detalle en WORKPLAN_T8_T12.md): las reescrituras de SQL (bare columns y struggling) se validaron con scripts de comparación vieja-vs-nueva sobre DB sintética antes de sustituir nada (compare_queries.js 6/6, compare_struggling.js 8/8); en struggling, el orden entre intentos con created_at empatado era NO determinista en la versión antigua — la nueva desempata por id (mejora, no regresión), y el comparador evita asertar sobre ese comportamiento indefinido. sync_meta escribe los cursores antes del saveDB final (atomicidad datos+cursores) y mantiene localStorage como fallback de downgrade sin escribirlo más. La validación de parámetros no numéricos (T11-D) ya estaba cubierta por el catch ValueError→400 de la Fase 1: se añadieron solo tests de regresión.

20. **Lote F1–F5 (mejoras funcionales §12.1–12.5)**: detalle en WORKPLAN_F1_F5.md. Decisiones destacables: la repesca de second chance es UNA por problema y sus intentos van con `run_id NULL` (el wrong original es la verdad del run: done, run_items y cierre quedan intactos); la pausa por fallo solo aplica a runs (Free Practice ya permitía reintentar); el heatmap agrupa por día UTC (los timestamps del protocolo son UTC; desvío ±2h asumido como visualización de hábito); `daily_stats` es local y NO se sincroniza (analítica de un solo usuario; evita tocar el protocolo), con clave (fecha LOCAL, source) e idempotencia por REPLACE. Nada de F1–F5 modifica el protocolo de sync ni el servidor.

21. **Peticiones de Victor (visibilidad por nivel, redescarga SGF) + fix del badge pegado**: (a) botón "Aplicar visibilidad ≤ nivel" en el tab By Level — para cada fuente pone `mostrar=1` en los capítulos con `diff_avg <=` el nivel de su combo (mismo criterio exacto que la columna "UP TO LEVEL"; los capítulos sin dificultad quedan visibles, como en ese cálculo), con confirmación previa, sync automático (doSync ya empuja el mostrar de todos los capítulos) y refresco de UI; núcleo SQL testeado en el arnés. (b) botón "⟳ Redescargar todo" en Cache offline — el precache vive en el service worker (fuera del repo), así que el force borra esas URLs de todas las caches vía Cache API desde la página antes de relanzar el precache normal, que las re-descarga del origen; con confirmación. (c) Diagnóstico del badge "2" persistente: los intentos registrados mientras un sync está en vuelo rebotan en `syncInProgress` sin reintento programado y quedaban pendientes hasta el siguiente intento; ahora un sync exitoso que termina con pendientes encadena otro `tryAutoSync` a +1,5 s (converge al pausar; sin cadena si falla). El primer intento de test del escenario reveló además que un insert durante la fase de pull sí entra en el push del mismo sync: el test definitivo inyecta el intento en el instante exacto del fetch del push.

## Compatibility notes

- **Orden de despliegue recomendado**: servidor primero, cliente después — pero ambas combinaciones cruzadas funcionan y están probadas:
  - Cliente antiguo + servidor nuevo: el push del historial completo, el delete por `ids`, el `check_runs` y el resto del protocolo antiguo funcionan sin cambios (auth desactivada por defecto).
  - Cliente nuevo + servidor antiguo: `run_uuid` y `synced` en los payloads son claves extra que el servidor antiguo ignora; el delete por `uuids` ya existía en el servidor antiguo; la cabecera `X-Auth-Token` solo se envía si el usuario guarda un token.
- **`POST /db/runs/delete` acepta `{ids}` y `{uuids}`**: la ruta por ids locales queda marcada con `TODO(Fase 2)` para su retirada cuando ningún cliente antiguo siga en uso.
- **Activación de la autenticación** (paso manual y reversible): definir `TSUMEVAULT_TOKEN` en el servidor y pegar el mismo token en Configuración → Sync del cliente. Hasta entonces todo funciona como antes. Al activarla, los clientes sin token dejan de sincronizar (comportamiento deseado).
- **Migraciones automáticas en ambos lados**: columnas `synced` (cliente), dedup de uuids duplicados históricos e índices únicos (cliente y servidor) se aplican solas al arrancar; ningún dato se descarta salvo copias exactas duplicadas por uuid (se conserva la más antigua y se repuntan sus referencias).
- **Cursores nuevos en localStorage** (`last_pull_attempt_id`, `last_pull_run_id`): si se borran, el cliente recae en el heurístico antiguo y simplemente re-descarga una vez (dedup por uuid). `last_sm2_sync` conserva su clave y formato.
- **Remapeo de ids y despliegues cruzados**: el `run_uuid` del pull es clave extra que los clientes antiguos ignoran; un cliente nuevo contra un servidor antiguo (sin `run_uuid` en el pull) recae en la semántica previa (`a.run_id` tal cual) hasta que el servidor se actualice.
- **Código temporal duplicado asumido**: la doble ruta ids/uuids del delete y los fallbacks de resolución de `run_id` en el push se mantienen deliberadamente hasta que la flota esté migrada.

## Remaining work

Para una futura Fase 2 (sin orden implícito):

- R2: soft-delete de runs (`deleted_at` propagado por sync) y retirada de `purgeEmptyRuns`/`syncDeletedRuns`; elimina de raíz la clase de bugs 3.2/3.3 y la resurrección residual descrita en Decisions §9.
- Bugs de UI/estado: 3.5 (sessionOk doble), 3.6 (zona horaria en Review), 3.7 (listeners acumulativos / R4), 3.8 (runs de review total=0), 3.9 (resize), 3.12 (resumeRun terminado y resto).
- 3.10 resto: unificar la sección crítica del botón de sync con tryAutoSync y revisar la transaccionalidad de doSync.
- R11: escapado HTML sistemático (`esc()`) en todos los sinks con datos.
- R9: unificación de tipos cliente/servidor (`result`, `problem_id`, `paused_ms` en servidor y en push) con migración de datos; añadir CHECKs reconstruyendo tablas.
- R6/R7/R8: capa repo, máquina de estados de sesión y modularización del monolito (con build a single-file).
- R3 fase B: separar DB fría (problems/chapters) de caliente (attempts/runs/sm2) para abaratar `saveDB()`.
- R10 resto: eliminar los ~13 endpoints muertos y las tablas `virtual_*` si se descarta la feature; retirar la ruta `{ids}` del delete.
- R12 y P3–P9: N+1 de struggling/stats con window functions, caché del snapshot gzip, mostrar/games incrementales, paginación del pull y del snapshot para historiales grandes.
- Backend: `schema_version` formal, manejo de SIGTERM con `server_close()`, valorar HTTP/1.1 keep-alive tras Caddy, rate limiting en Caddy.
- Normalizar `sgf_path` en el import; revisar `catch` vacíos del cliente.
- Propagación de cambios de runs servidor → cliente: el pull solo inserta runs nuevos, nunca actualiza los existentes (un run cerrado en el dispositivo A sigue apareciendo abierto en B). Requiere `runs.updated_at` en el servidor + parámetro de pull incremental + actualización local solo de runs limpios (`synced=1`). Limitación preexistente, confirmada en uso real.
