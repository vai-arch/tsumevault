# AUDITORÍA TÉCNICA EXHAUSTIVA — TsumeVault (preparación v2.0)

Archivos analizados: `tsumevault.html` (4.183 líneas), `tsumevault_server.py` (1.089 líneas), `db_schema.sql` (117 líneas).
Fecha: 2026-07-04.

> Nota de contexto: sistema mono-usuario, desplegado en Hetzner tras Caddy (`tsumevault.duckdns.org`), frontend en GitHub Pages, cliente offline-first con sql.js + IndexedDB. La auditoría evalúa el sistema con criterios profesionales, señalando también qué riesgos son aceptables por ser mono-usuario y cuáles NO lo son aunque solo haya un usuario.

---

# 1. ARQUITECTURA GENERAL

## 1.1 Organización del sistema

```
┌────────────────────────── Cliente (navegador) ──────────────────────────┐
│ tsumevault.html (monolito)                                              │
│  ├─ UI (HTML+CSS inline, 1.590 líneas)                                  │
│  ├─ Capa de datos local: sql.js (SQLite en WASM, en memoria)            │
│  ├─ Persistencia: IndexedDB (export binario completo de la DB)          │
│  ├─ Motor de estudio: WGo.js (tablero, kifu, game)                      │
│  ├─ Motor SM-2 (spaced repetition) en JS                                │
│  ├─ Sincronizador bidireccional (pull/push attempts, runs, sm2,         │
│  │   mostrar, games, snapshot)                                          │
│  └─ Service Worker (PWA, precache SGF)                                  │
└──────────────────────────────────────────────────────────────────────────┘
                 │ HTTPS (Caddy reverse proxy)
┌────────────────▼──────────── Servidor ───────────────────────────────────┐
│ tsumevault_server.py — HTTPServer stdlib, single-thread                  │
│  ├─ ~20 endpoints (GET/POST/PUT) → funciones handler planas              │
│  └─ sqlite3 → tsumeVault.db (WAL)                                        │
└──────────────────────────────────────────────────────────────────────────┘
```

## 1.2 Responsabilidades reales de cada archivo

- **tsumevault.html**: es a la vez la vista, el controlador, el modelo (schema + queries), el motor de sincronización, el algoritmo SM-2, el visor de partidas, la gestión de PWA/cache y la configuración visual. Es el **verdadero backend lógico** de la aplicación: casi toda la lógica de negocio vive aquí.
- **tsumevault_server.py**: hoy es esencialmente un **hub de sincronización + snapshot**. Los endpoints CRUD "clásicos" (`/db/collections`, `/db/chapters`, `/db/problems`, `/db/problem`, `/db/runs`, `/db/run/items`, `/db/last_run_stats`, `/db/last_run_stats_all`, `/db/struggling`, `/db/difficulty_range`, `POST /db/attempt`, `POST /db/run`, `PUT /db/run`) **ya no son llamados por este frontend** (todo se resuelve localmente en sql.js). Son código vivo en el servidor pero muerto en el sistema.
- **db_schema.sql**: schema del servidor. Diverge del schema del cliente (ver §6).

## 1.3 Flujo de datos y ciclo de vida de una operación (intento de problema)

1. Usuario hace click en el tablero → `window._boardClickHandler` → `onBoardClickExecute`.
2. Se valida el movimiento contra el árbol SGF; `checkResult`/`playOpponent` deciden correcto/incorrecto.
3. `recordAttempt(result)` → `localInsertAttempt`:
   - INSERT en `attempts` (sql.js, memoria) con `uuid` cliente.
   - Si hay run: UPDATE `runs.done`, cierre condicional, UPDATE `run_items.result`, `updateSm2` (recalcula intervalo/easiness/due_date).
4. Persistencia: **solo cada 10 intentos** se llama `saveDB()` (export binario completo → IndexedDB). En el resto de casos se confía en que `doSync` termine con `saveDB()`.
5. `tryAutoSync(true)` → `doSync`:
   - PULL `/sync/pull` con cursores (`MAX(id) WHERE uuid IS NULL`).
   - PUSH `/sync/push` con **TODOS** los attempts/runs con `uuid IS NOT NULL` (historial completo, ver §3.1).
   - Sync de `mostrar` (envía TODOS los chapters), SM-2 (cursor `updated_at`), games, snapshot condicional.
6. Servidor deduplica por uuid, mapea run_ids cliente→servidor, hace commit.

## 1.4 Problemas de arquitectura detectados

| # | Problema | Gravedad |
|---|----------|----------|
| A1 | **Monolito frontend de 4.183 líneas** en un solo `<script>`: UI, datos, sync, SM-2, visor de partidas y PWA mezclados sin módulos. | Alta |
| A2 | **Doble implementación de la capa de datos**: cada query existe dos veces (Python y JS) con divergencias ya reales (`ORDER BY chapter_num` en servidor vs `ORDER BY ch.name` en cliente; `problem_stats` como vista en servidor vs subquery inline repetida 3 veces en cliente). | Alta |
| A3 | **~13 endpoints muertos** en el servidor que siguen exponiendo superficie de ataque y coste de mantenimiento. | Media |
| A4 | **Protocolo de sync sin contrato formal**: los cursores mezclan semánticas (id autoincrement para attempts/runs, timestamp para SM-2, dump completo para mostrar/games). Cuatro estrategias distintas en el mismo `doSync`. | Alta |
| A5 | **Estado global disperso en el cliente**: ~20 variables globales (`activeRunId`, `runMode`, `runIdx`, `runItems`, `allProblems`, `waitingForNext`, `sessionOk`…) mutadas desde docenas de funciones. El "modo" actual (run / free / review / games) se infiere de combinaciones de flags en vez de una máquina de estados explícita. | Alta |
| A6 | **`window._boardClickHandler` / `window._studyRestart` / `window._studyBack` como canal de comunicación global** entre modos: frágil, los modos compiten por él. | Media |
| A7 | **Responsabilidades mezcladas en funciones**: `setupInteractiveMode` (≈75 líneas efectivas) contiene lógica de juego, snapshots, ghost-stone, tap-confirm, grabación de intentos y navegación. `doSync` orquesta 6 sub-sincronizaciones distintas. | Media |
| A8 | `localInsertRun` hace `alert()` (capa de datos hablando con el usuario). | Baja |

## 1.5 Arquitectura propuesta (v2.0)

Sin cambiar de stack (mantener single-file deployable si se quiere, vía build step):

**Frontend — separar en módulos ES (bundle a un solo fichero con esbuild si GitHub Pages lo exige):**
```
src/
  core/db.js          → sql.js wrapper, schema, migraciones, saveDB
  core/repo.js        → TODAS las queries locales (única fuente)
  core/sync.js        → protocolo de sync (un solo mecanismo, ver abajo)
  core/sm2.js         → algoritmo puro (testeable)
  core/state.js       → store central con máquina de estados de sesión
                        (IDLE | RUN | FREE | REVIEW | GAMES)
  ui/board.js         → WGo, interactive mode, ghost, tap-confirm
  ui/panels.js        → collections/runs/free/review/games
  ui/modals.js        → config, stats
  sw-bridge.js        → precache, versión
```

**Protocolo de sync unificado**: una sola semántica — *event log con uuid + updated_at* para todo (attempts, runs, run_items, sm2, mostrar). Cursor único por tabla = `updated_at` del último registro aplicado. Elimina los 4 mecanismos actuales y los bugs de §3.1–3.3.

**Servidor**: eliminar endpoints muertos; quedarse con `/sync/*`, `/db/runs/delete` (por uuid), y mover a `ThreadingHTTPServer` + capa de auth (ver §4). Idealmente migrar a un framework mínimo (Flask/FastAPI) para routing, validación y errores consistentes — pero es opcional: el diseño actual de handlers planos es razonable para este tamaño si se limpia.

---

# 2. CALIDAD DEL CÓDIGO

## 2.1 Duplicación

| Dónde | Qué | Gravedad |
|---|---|---|
| Cliente | La subquery de stats por problema (`COUNT/SUM/AVG sobre attempts GROUP BY source,problem_id`) está copiada **3 veces** (`localGetProblems`, `localGetProblem`, `localGetCollections`/`localGetChapters` variantes). | Media |
| Cliente | El CTE de madurez (`visible/ranked_attempts/last5/seen`) está duplicado **íntegro** en `localGetMaturity` y `localGetMaturityByLevel` (~60 líneas cada uno); solo cambia la condición de `visible`. | Media |
| Cliente | El cálculo `{ok,total,pct,duration_ms}` sobre run_items se repite 4 veces (`localGetLastRunStatsAll` ×2, `localGetLastRunStats` ×2). | Media |
| Cliente | `const PCT_YELLOW = 80` + la función `color(pct)` se redeclara localmente en `renderByLevel`, `bylevelUpdateRow`, `renderStatsTable`, `renderMaturity`, ignorando la global `pctColor()` ya existente. | Baja |
| Cliente | Shuffle Fisher-Yates copiado inline en `localInsertRun` y `startFreePractice`. | Baja |
| Cliente | El bloque "estado vacío" (ocultar board, mostrar welcome, resetear pills) copiado en `startFreePractice` y `startReview` (~8 líneas idénticas). | Baja |
| Cliente/Servidor | Toda la lógica de `last_run_stats`, `struggling`, `difficulty_range`, `get_problems`… duplicada JS/Python (A2). | Alta |
| Servidor | `do_PUT` repite 3 veces el patrón try/respond en vez de usar una tabla de rutas como `GET_ROUTES`. | Baja |

## 2.2 Funciones demasiado largas / complejidad

- `setupInteractiveMode` (~75 líneas, 8 closures internas, 6 flags de estado locales + globales). Es el corazón del producto y el punto más difícil de razonar.
- `doSync` (~110 líneas, 6 fases secuenciales con manejo de error distinto en cada una).
- `handle_sync_push` (Python, ~145 líneas): logging, dedup de runs, dedup de attempts, mapeo de ids, tres estrategias de fallback para resolver `run_id`.
- `applyCollectionFilters` (~85 líneas): 3 filtros × 2 rutas (cache/DB) × 2 niveles (colección/chapter) anidados.
- `renderChapterList`: render + listeners + fetch de mostrar + stats en una sola función.

## 2.3 Código muerto / obsoleto

| Ítem | Ubicación |
|---|---|
| ~13 endpoints REST no usados por el frontend | server.py (ver §10) |
| `handle_post_run` con soporte `virtual` y tablas `virtual_collections`/`virtual_items`: el frontend nunca crea runs virtuales ni las pobla | server.py + schema |
| `wgoBoard._studyListener`: se "limpia" en `renderProblem` (línea 3661) pero **nunca se asigna** en ninguna parte — resto de una implementación anterior | tsumevault.html:3661 |
| `item.appendChild(deleteBtn); item.appendChild(deleteBtn);` — doble append del mismo nodo (no-op, pero es basura) | tsumevault.html:3291-3292 |
| Prints de depuración `print("1")…print("9")` en `do_POST` y `print("[handle] nueva conexión")` en cada request | server.py:947, 975-1009 |
| `sync_push_log.json`: volcado de debug del payload completo en cada push, sobrescrito | server.py:763-784 |
| Variable global `lightMode` del cliente: se lee en `initDB` pero **jamás se escribe**; siempre false | tsumevault.html:1624 |
| Comentario "← añadir esta línea" fosilizado | tsumevault.html:2970 |
| `pause` de runs: `paused_ms` existe solo en el schema cliente; el servidor lo desconoce y se pierde al sincronizar (el push no lo envía, el schema servidor no lo tiene) | ambos |

## 2.4 Nombres y encapsulación

- `doSync(lightMode = false)`: el parámetro **sombrea la global `lightMode`** y además significa otra cosa ("silent/skip-snapshot"). `tryAutoSync(silent)` pasa `silent` como `lightMode`. Funciona de casualidad; es una trampa. Renombrar a `skipHeavySync`.
- `handle_sync_pull` usa `since_attempt_id`/`since_run_id` mientras SM-2 usa `since` (timestamp): mismos prefijos, semánticas incompatibles.
- `chaptersCache` se puebla en 2 sitios (`updateFreeChapters`, `renderChapterList`) y se invalida en otros 2; no hay dueño claro.
- Acceso directo a internos de WGo (`obj_arr`, `pixelRatio`, `fieldWidth`) en 6 funciones: acoplamiento fuerte a detalles no públicos de la librería (asumido conscientemente, pero conviene concentrarlo en un solo adaptador `boardAdapter`).

## 2.5 Acoplamiento / cohesión

- El cliente conoce y usa **ids autoincrement del servidor** (chapters.id como identificador global en visibility JSON, run ids en purge). Esto acopla ambas bases: si algún día se regenera la DB del servidor, los ids de chapters cambian y el fichero de visibilidad y los sm2/attempts quedan huérfanos. Los chapters deberían tener clave natural (`source,set_id,chapter_num`) en todos los intercambios.
- `updateSessionUI` escribe en 8 elementos del DOM incluyendo pills del modal de config (`cfg-pill-*`): la UI de sesión y la de config comparten elementos.

---

# 3. BUGS POTENCIALES (y reales)

Ordenados por gravedad. Los marcados 🔴 son defectos con pérdida de datos o corrupción de métricas.

## 3.1 🔴 Push del historial COMPLETO en cada sync + riesgo de duplicación local de attempts

`doSync` (líneas 2241-2242):
```js
const newAttempts = dbQuery('SELECT * FROM attempts WHERE uuid IS NOT NULL', []);
const newRuns = dbQuery('SELECT * FROM runs WHERE uuid IS NOT NULL', []);
```
El `uuid` nunca se anula tras un push exitoso, así que **cada sync envía todos los attempts y runs históricos del cliente** (con sus run_items). El servidor los deduplica por uuid, pero:

1. **Coste O(historial)** en cada auto-sync — que se dispara tras *cada intento* (`recordAttempt` → `tryAutoSync(true)`). Con miles de intentos, cada solución de un problema dispara un POST de megabytes.
2. **Duplicación local en el pull**: el cursor de pull es `MAX(id) WHERE uuid IS NULL`. Los attempts propios (con uuid) no avanzan ese cursor. Cuando el servidor asigna a un attempt propio un `server_id` mayor que el cursor, el siguiente pull lo devuelve y el cliente lo inserta con `INSERT OR IGNORE` **por PK `id`** — sin comprobar uuid (a diferencia de los runs, que sí comprueban uuid en línea 2233). Resultado: el mismo intento puede existir dos veces en la DB local (id local + id servidor, mismo uuid), **duplicando las estadísticas** (`pct_correct`, `total_attempts`, struggling, madurez). Que hoy no se manifieste depende únicamente de que los rangos de ids coincidan por casualidad.
3. Además, como los pulls devuelven también los attempts con uuid y estos no avanzan el cursor, **cada pull re-descarga el mismo rango** una y otra vez.

**Fix**: (a) marcar attempts como sincronizados (columna `synced INTEGER` o poner `uuid_pushed=1`) y pushear solo pendientes; (b) en el pull, deduplicar attempts por uuid igual que se hace con runs; (c) índice sobre `attempts(uuid)` en ambos lados.

## 3.2 🔴 `syncDeletedRuns` borra runs locales creados offline que aún no se han pusheado

Orden de arranque (líneas 4110-4114): `initDB → purgeEmptyRuns → syncDeletedRuns → loadCollections → tryAutoSync`.

`syncDeletedRuns` pregunta al servidor qué uuids no existen y **borra localmente** los que falten. Un run creado ayer sin conexión (uuid asignado, push fallido en silencio) todavía no existe en el servidor → en el siguiente arranque se elimina **antes** de que `tryAutoSync` tenga oportunidad de pushearlo. Se pierden el run y sus run_items; los attempts quedan huérfanos apuntando a un run_id inexistente.

**Fix**: ejecutar `syncDeletedRuns` solo *después* de un push exitoso en la misma sesión, o marcar runs con `pushed_at` y excluir de la comprobación los nunca-pusheados.

## 3.3 🔴 `purgeEmptyRuns` envía **ids locales** al servidor

Línea 2208: `body: JSON.stringify({ ids })` — ids autoincrement **locales**. Para runs creados en otro dispositivo o con divergencia de secuencias, esos ids pueden corresponder en el servidor a runs distintos → **borrado de runs equivocados en el servidor**. `deleteRun` sí usa uuid cuando existe; `purgeEmptyRuns` no. Además purga runs de *cualquier* source y también los que pudieran estar abiertos en otro dispositivo (>2h sin resultados).

**Fix**: enviar `{uuids}` (los runs locales siempre tienen uuid al crearse); excluir runs sin uuid.

## 3.4 🔴 Ventana de pérdida de hasta 9 intentos

`recordAttempt`: `saveDB()` solo cada 10 intentos; en los demás confía en que `doSync` (que termina con `await saveDB()`) tenga éxito. **Sin conexión**, `tryAutoSync` falla silenciosamente y no se persiste nada: cerrar la pestaña/PWA pierde hasta 9 intentos (y sus actualizaciones SM-2 y run_items). sql.js vive solo en memoria.

**Fix**: `saveDB()` incondicional (debounced ~1-2 s) tras cada intento; el export completo es caro (§5) pero la corrección va primero — o mejor, journal incremental en IndexedDB (ver refactor R3).

## 3.5 🔴 Doble incremento de `sessionOk` en Free Practice

Línea 3698 (`playOpponent`, rama "sin hijos = correcto"):
```js
showResult(true, ''); if (!hadWrong) { recordAttempt('correct'); if (!runMode) sessionOk++; }
```
`recordAttempt` **ya** incrementa `sessionOk` cuando `!runMode` (línea 3683). Todo problema resuelto cuyo nodo final no lleve comentario `RIGHT` suma **2** al contador de sesión en Free Practice/Review → el % de sesión mostrado es incorrecto. (No afecta a la DB, solo a la UI de sesión.)

## 3.6 🔴 Regresión de zona horaria en Review

`localGetReviewProblems` y `localCountReviewPending` (líneas 1968, 1988) usan:
```js
const today = new Date().toISOString().slice(0, 10);  // fecha UTC
```
En CEST (UTC+2), entre las 00:00 y las 02:00 locales la fecha UTC es "ayer": los problemas que vencen hoy no aparecen hasta las 2 AM. `updateSm2` calcula `due_date` con la misma base UTC, con el desfase inverso. En esta versión del fichero **no está** el fix de `toLocaleDateString('sv')` que sí existía en la lógica del Review tab según el histórico del proyecto — o es una regresión o esta copia es anterior al fix. En cualquier caso, en el código entregado el bug está presente y afecta a las tres funciones (`localGetReviewProblems`, `localCountReviewPending`, `updateSm2`).

## 3.7 Listeners acumulativos → acciones duplicadas

- `populateFreeFilters` (3334-3335) añade `change` a `fp-col` y `click` a `fp-start` **cada vez que se llama**, y se llama desde `loadCollections` (arranque, tras cada sync manual, tras aplicar visibilidad, tras cambiar source). Tras N recargas, un click en "Start practice" ejecuta `startFreePractice` N veces.
- `populateReviewFilters` (3417-3421) igual con `rv-start` y `rv-col`. Aquí es peor: `startReview` **inserta un run en la DB** (`type='review'`) por invocación → N clicks fantasma = N runs basura creados y sincronizados.
- Mitigación trivial: `{ once:false }` no vale; mover el `addEventListener` fuera (registro único en init) o `replaceWith(cloneNode)` / usar `onclick=`.

## 3.8 Runs de review con `total=0` se cierran en el primer intento y quedan inconsistentes

`startReview` crea el run con `total=0, done=0`. `localInsertAttempt` hace `done=done+1` y luego cierra si `done>=total` → **se cierra tras el primer intento**, pero `activeRunId` sigue activo y los siguientes intentos siguen incrementando `done` sobre un run `closed` (done=25, total=0). Además `showSessionEnd` al acabar la review **no limpia `activeRunId`** (solo `endRun` lo hace, y la review nunca pasa por `endRun` porque `runMode=false`): si el usuario después pulsa "Next" en algún flujo residual, los intentos se atribuirían al run de review cerrado. Estado incoherente en DB (`done>total`, closed con actividad posterior).

## 3.9 Redimensionar la ventana resetea el problema en curso

El handler de `resize` (línea 4102) hace `initBoard + renderProblem(currentProblem)`: reconstruye el modo interactivo desde el nodo raíz. Si el usuario había jugado la primera jugada correcta y está a mitad de secuencia, **pierde el progreso del intento** (aunque `attemptRecorded` también se resetea → podría registrar el intento dos veces si ya había fallado: `hadWrong` se pierde, un fallo previo ya registrado + acierto posterior registra un `correct` adicional → **doble attempt del mismo problema**). En móvil esto se dispara con el cambio de orientación o la aparición del teclado.

## 3.10 Carreras de sincronización

- `tryAutoSync` protege con `syncInProgress`, pero el handler del botón de sync (2858) implementa su propia sección crítica duplicada; ambos manipulan `setSyncStatus` con temporizadores que pueden pisarse (el `setTimeout` de 3 s del estado "ok" puede rehabilitar el botón en mitad de un sync posterior).
- `doSync` no es transaccional: si el push tiene éxito pero `saveDB()` final falla (IndexedDB lleno), el servidor tiene datos que el cliente cree no haber enviado — benigno por dedup uuid, pero el cursor `last_sm2_sync` (localStorage) sí puede avanzar sin que la DB local persistida refleje el pull SM-2 → estados SM-2 perdidos hasta el siguiente cambio.
- `last_sm2_sync` se fija a `new Date()` **del cliente**: si el reloj del cliente va adelantado respecto al servidor, registros del servidor con `updated_at` entre ambos relojes se saltan para siempre. Cursor correcto: `MAX(updated_at)` de los registros efectivamente recibidos/enviados.
- Servidor single-thread (ver §4/§5): no hay carreras SQL entre requests porque se serializan, pero dos dispositivos sincronizando a la vez se bloquean mutuamente y los timeouts de 8 s del cliente pueden abortar pushes a medias (el servidor seguirá procesando y commiteando: el cliente reintentará; dedup lo salva — de nuevo, el uuid es el único airbag del sistema).

## 3.11 Errores silenciosos y validación

- `handle_put_run` con body sin `status` responde `{ok:true}` sin hacer nada.
- `/sync/chapters_mostrar` y `handle_sync_sm2_push` explotan con KeyError→500 si falta un campo (sin validación), y el 500 devuelve `str(e)` al cliente.
- `handle_post_attempt` no valida que `result ∈ {correct, wrong}` ni tipos.
- Cliente: `catch (e) { }` vacíos en ~10 sitios (visualConfig, presets, refreshCollectionStats, renderMaturity…): fallos invisibles.
- `_read_body`: `json.loads` de body malformado → excepción **fuera** del try de `do_POST` (se lee antes del try) → traceback sin respuesta al cliente y conexión colgada hasta timeout. Igual en `do_PUT`.
- `int(set_id)` sobre query params no numéricos → 500 con mensaje interno.

## 3.12 Otros

- `resumeRun` de un run abierto con todos los items respondidos: `findIndex → -1`, `runIdx=-2 → -1` → **rejuega desde el item 0** un run terminado (y `recordAttempt` añadiría attempts nuevos actualizando run_items ya resueltos).
- `handle_get_last_run_stats*` usa `GROUP BY chapter_id HAVING id = MAX(id)`: *bare column* no estándar; funciona por comportamiento documentado de SQLite pero se rompería en cualquier otra DB y es frágil ante cambios de query planner. Igual en las versiones JS.
- `run_items` PK `(run_id, problem_id)` sin `source`: dos problemas de sources distintos con el mismo `problem_id` en un run virtual colisionarían (hoy runs virtuales no se usan, pero el endpoint existe).
- `now_iso()` con resolución de segundo: el dedup de attempts sin uuid por `(source, problem_id, created_at)` puede colisionar con intentos rápidos legítimos (retry inmediato del mismo problema).
- `SFX` con `new Audio()` global: en iOS Safari el primer `play()` sin gesto falla (capturado por try vacío — sonido simplemente no suena la primera vez; comportamiento conocido pero sin feedback).
- `getSetupStones` solo lee `AB/AW`, ignora `AE` (empty) en la rama de `properties`; si algún SGF de setup usa AE en el root, se renderizarían piedras que deberían estar borradas.

---

# 4. SEGURIDAD

Contexto: el servidor está **expuesto a Internet** (Caddy + DuckDNS). Aunque sea mono-usuario, la superficie es pública.

## 4.1 🔴 CRÍTICA — Ausencia total de autenticación + CORS `*` en endpoints de escritura

Todos los endpoints, incluidos los destructivos, son públicos:

- `POST /db/runs/delete` — cualquiera puede borrar todos los runs (basta iterar ids).
- `POST /sync/push` — inyección arbitraria de attempts/runs → corrompe todas las estadísticas y el estado SM-2 derivado.
- `POST /sync/sm2/push` — reescritura del estado de repetición espaciada completo.
- `PUT /sync/chapters_mostrar`, `PUT /db/chapter/mostrar`, `PUT /db/run` — modificación de estado.
- `POST /admin/import_games` — un endpoint llamado **admin** sin auth.
- `GET /sync/snapshot` — descarga completa de la base de datos por cualquiera.

Con `Access-Control-Allow-Origin: *` cualquier web que visites puede además lanzar estas llamadas desde tu propio navegador (CSRF trivial: los endpoints aceptan `Content-Type: application/json` pero no verifican Origin; incluso sin CORS el atacante directo no necesita navegador).

**Mitigación mínima proporcional al proyecto**: token estático en header (`X-Auth-Token`) verificado en `Handler` antes de rutear + restringir `Access-Control-Allow-Origin` a `https://vai-arch.github.io` + validar `Origin` en escrituras. Caddy puede añadir además `basicauth` o mTLS si se quiere defensa en profundidad. Coste: ~20 líneas.

## 4.2 ALTA — Denegación de servicio estructural

- `HTTPServer` **single-thread**: una conexión lenta (slowloris: abrir socket y no enviar) congela el servicio entero. Sin timeouts de socket configurados.
- `_read_body` lee `Content-Length` sin límite → un POST de 2 GB agota la RAM del CAX11.
- `handle_sync_snapshot` serializa toda la DB en memoria y bloquea el proceso durante segundos con 64k+ problemas: cualquier cliente puede pedirlo en bucle.

**Fix**: `ThreadingHTTPServer` + `Handler.timeout = 30` + rechazar `Content-Length > 10 MB` (413) + rate limiting en Caddy.

## 4.3 ALTA — Fuga de información

- Los 500 devuelven `str(e)` (rutas, nombres de columnas, detalles sqlite).
- `sync_push_log.json` escribe en disco un volcado del último push (datos + estructura), en el directorio del script servido… no está bajo el docroot de Caddy (a verificar), pero es un fichero de datos sin rotación ni propósito en producción.
- Logs a stdout imprimen bodies completos de cada POST (`print(f"[do_POST] ... body={body}")`) → el journal de systemd acumula todos los datos enviados.

## 4.4 MEDIA — CSRF / manipulación de parámetros

Cubierto en 4.1: sin token anti-CSRF ni verificación de Origin; todos los parámetros se aceptan sin validar tipo/rango (ids negativos, sources inexistentes, `mostrar=999` → `int(bool())` lo normaliza en un endpoint pero no en `/sync/chapters_mostrar`, que escribe el valor tal cual).

## 4.5 MEDIA — XSS almacenado en el cliente

`innerHTML` con datos de la DB sin escapar: `col.name`, `chap.name`, `run.label`, `r.collection_name`, `r.source` (renderCollectionsList, renderChapterList, loadRuns, renderStatsTable, renderByLevel, renderGlobalPending). Hoy los datos vienen del propio pipeline, **pero** combinado con 4.1 (cualquiera puede escribir en la DB del servidor vía push/import y esos datos llegan al cliente vía snapshot/pull), un atacante puede conseguir ejecución JS en tu navegador → robo de IndexedDB, pivotar al servidor con tu sesión. La cadena completa es real mientras 4.1 exista. Escapar con `textContent`/función `esc()` en todos los sinks.

## 4.6 BAJA / N.A.

- **SQL Injection**: no encontrada. Todos los queries usan placeholders; los `placeholders = ",".join("?" * len(ids))` interpolan solo el *número* de `?`, correcto. En cliente igual. ✔
- **Path traversal**: el servidor Python no sirve ficheros; los SGF los sirve Caddy/GitHub Pages. `sgf_path` viaja del servidor al cliente y se usa en `fetch(SGF_BASE + path)` — un `sgf_path` malicioso (`../../`) solo alcanzaría rutas del mismo origen estático; riesgo residual bajo, pero normalizar en el import.
- **SQLite locking**: con WAL y servidor single-thread no hay contención entre requests; el riesgo real es el procedimiento manual de transferencia de la DB (ya cubierto por tu protocolo checkpoint→scp).
- `local_ip = socket.gethostbyname(...)` en arranque puede lanzar excepción en hosts sin resolución del hostname → el servidor no arranca (robustez, no seguridad).

## 4.7 Tabla resumen

| Vulnerabilidad | Clase | Gravedad |
|---|---|---|
| Endpoints de escritura/borrado sin auth, expuestos a Internet | AuthN/AuthZ | **Crítica** |
| CORS `*` + sin verificación de Origin (CSRF) | CSRF | **Crítica** (misma raíz) |
| Snapshot de DB completa pública | Info disclosure | Alta |
| Single-thread sin timeouts ni límite de body (DoS) | Disponibilidad | Alta |
| `str(e)` en respuestas 500 + bodies en logs | Info disclosure | Alta/Media |
| XSS almacenado vía innerHTML (explotable en cadena con auth ausente) | XSS | Media |
| Validación de entrada inexistente (tipos, rangos, enums) | Input validation | Media |
| `sync_push_log.json` en disco | Info disclosure | Baja |
| `sgf_path` sin normalizar | Path handling | Baja |

---

# 5. RENDIMIENTO

## 5.1 Cliente — puntos calientes reales

| # | Problema | Impacto | Mejora |
|---|---|---|---|
| P1 | **`saveDB()` = `db.export()` completo → IndexedDB** tras cada 10 intentos, cada run, cada cambio de mostrar, cada sync. Con 64k problemas + attempts la DB puede superar decenas de MB: cada save serializa TODO el binario en memoria y lo escribe entero. En móvil produce jank y presión de GC. | Alto | Corto plazo: debounce + `requestIdleCallback`. Medio: separar datos estáticos (problems/chapters, inmutables) de datos calientes (attempts/runs/sm2) en dos DBs sql.js → exportar solo la caliente (100× menor). |
| P2 | **Push del historial completo por intento** (bug 3.1): red + CPU JSON en cada respuesta del usuario. | Alto | Fix 3.1 (solo pendientes). |
| P3 | **N+1 masivo en `localGetStruggling`**: una query por problema del scope; "Struggling (last 20)" sobre un source de 64k problemas = 64k prepares. Igual en el servidor (`handle_get_struggling`). | Alto | Una sola query con `ROW_NUMBER() OVER (PARTITION BY problem_id ORDER BY created_at DESC)` y `HAVING SUM(result='wrong')>0` sobre `rn<=n`. |
| P4 | **N+1 en stats de runs**: `localGetLastRunStatsAll` hace una query de agregación por run; `localGetAllMaturity` ejecuta el CTE pesado (window function sobre attempts) **una vez por colección** al abrir el modal de stats. | Medio | Agregar en una sola query con `GROUP BY run_id` (JOIN al set de "últimos runs") y mover el CTE a agrupación por `set_id`. |
| P5 | `refreshCollectionStats` llama `localGetLastRunStats` por cada colección expandida y re-consulta `applyCollectionFilters` (que hace queries por colección si no hay cache). Se ejecuta al cambiar de tab. | Medio | Reutilizar `lastRunStatsAll` ya cargado. |
| P6 | `updateSessionUI`/`updateRunProgress` recorren `runItems` con 3 `filter()` cada uno, en cada jugada. Irrelevante para <5k items pero es O(n) evitable con contadores. | Bajo | Contadores incrementales. |
| P7 | `@import` de Google Fonts dentro del `<style>`: bloquea el primer render (descarga en serie tras el CSS). | Bajo | `<link rel="preconnect">` + `<link rel="stylesheet">`. |
| P8 | sql.js WASM desde CDN sin fallback local ni versión fijada en SW cache: primera carga offline tras limpiar cache falla. | Medio | Servir sql-wasm desde el propio repo y precachearlo. |
| P9 | `imgCache` de piedras: `img.onload = () => board.redraw()` reasignado por cada piedra pendiente → múltiples redraws completos al cargar un set nuevo. | Bajo | Redraw único con debounce. |

## 5.2 Servidor

- Single-thread: la latencia de cualquier request es la suma de la cola. Un snapshot de 30 MB gzip bloquea los pushes del móvil.
- `handle_sync_push`: lookups `SELECT id FROM runs WHERE uuid=?` y `SELECT id FROM attempts WHERE uuid=?` **sin índice sobre uuid** → full scan por cada elemento del payload; con el bug 3.1 (payload = historial completo) el coste es O(historial²) por sync. Crear `CREATE INDEX idx_attempts_uuid ON attempts(uuid)` y `idx_runs_uuid ON runs(uuid)`.
- `handle_sync_push` abre transacción implícita larga (todo el payload) — correcto para atomicidad, pero con WAL y single-thread está bien; documentarlo.
- Escritura de `sync_push_log.json` en el hot path (I/O síncrono por push).
- `gzip.compress` nivel 6 sobre snapshot completo en cada petición: cachear el snapshot gzip y regenerarlo solo cuando `static_version` cambie.
- `problem_stats` (vista) se agrega sobre TODOS los attempts en cada `GET /db/collections` — endpoints hoy muertos, pero si se reactivan, materializar o indexar está ya cubierto por `idx_attempts_source_problem_created`.

## 5.3 Red

- `/sync/chapters_mostrar` envía TODOS los chapters (miles) en cada sync aunque nada haya cambiado → mandar solo modificados (dirty flag o updated_at).
- `/sync/games` descarga todo el catálogo de games en cada sync no-light.
- Sin `ETag`/`If-None-Match` en snapshot (el mecanismo `static_version` lo suple, aceptable).

## 5.4 Renderizado/DOM

- Uso intensivo de `innerHTML` por ítem en listas (colecciones ~cientos, chapters ~749): aceptable; el mayor coste real es el re-render completo de `col-list` en cada `loadCollections`. Virtualización innecesaria a esta escala; basta no reconstruir la lista cuando solo cambian stats (ya se hace parcialmente con `refreshColPct`).
- Estilos inline masivos → bloqueos de estilo recalculado triviales; problema de mantenibilidad más que de rendimiento (§7).

---

# 6. BASE DE DATOS

## 6.1 Divergencia de schemas cliente/servidor (problema raíz)

| Campo | Servidor | Cliente | Consecuencia |
|---|---|---|---|
| `attempts.result` | `INTEGER NOT NULL -- 1=correct, 0=wrong` | `TEXT` | El comentario del schema servidor es falso: **todo el código escribe/compara strings** (`'correct'`/`'wrong'`). Funciona por la afinidad laxa de SQLite, pero el schema documenta lo contrario de la realidad. Igual en `run_items.result`. |
| `problems.problem_id` | `INTEGER` | `TEXT` | Afinidad distinta; JOINs texto↔entero en SQLite dependen de la afinidad de columna. Hoy funciona porque ambos lados almacenan enteros coercionados, pero `sm2_state.problem_id` es `TEXT` **también en el servidor** → JOIN sm2↔problems en el servidor compara TEXT vs INTEGER (afinidades distintas: `'123' = 123` es falso sin coerción de columna). El servidor no hace ese JOIN hoy; el cliente sí (problems TEXT ↔ sm2 TEXT, coherente). Bomba latente si se añade lógica server-side sobre sm2. |
| `attempts.problem_id` | `INTEGER` | `TEXT` | Ídem. |
| `runs.paused_ms` | **no existe** | `INTEGER DEFAULT 0` | `paused_ms` se pierde en cada sync (push no lo envía; aunque lo enviara, el INSERT del servidor no lo tiene). La duración neta de runs solo es correcta en el dispositivo donde se jugó. |
| `chapters` | `UNIQUE(source,set_id,chapter_num)` + FK | sin UNIQUE ni FK | El cliente confía en los ids del snapshot. |
| FKs en general | attempts sin FK a problems/runs; run_items→runs sí | ninguna FK activada (sql.js sin `PRAGMA foreign_keys`) | Huérfanos posibles (ya ocurren con 3.2/3.3). |

## 6.2 Problemas del schema en sí

- **`attempts` sin FK** a `problems` ni a `runs`, sin `CHECK (result IN ('correct','wrong'))`, sin `UNIQUE(uuid)`. El uuid es la clave de deduplicación de todo el sistema y no tiene ni índice ni unicidad.
- **`runs.uuid` / `attempts.uuid` sin índice** (impacto §5.2). `runs` sin `CHECK (status IN ('open','closed'))` ni `CHECK (type IN (...))` — ya existe un cuarto type `'review'` no documentado que el servidor acepta por sync pero rechaza por `POST /db/run`.
- **Denormalización sin mantenimiento**: `collections.num_problems`, `collections.chapter_count`, `chapters.problem_count` se calculan en el pipeline de import y nada los actualiza si cambian los problemas. Aceptable (datos estáticos) pero documentarlo; `runs.total/done` es denormalización caliente y ya produce estados `done>total` (bug 3.8).
- **`problem_stats` (vista)**: correcta y bien indexada por `idx_attempts_source_problem_created`. Nota: la vista compara `result='correct'` confirmando que el tipo real es TEXT.
- **Índices**: faltan `attempts(uuid)`, `runs(uuid)`, `sm2_state(due_date)` (el Review filtra por due_date; hoy hay índice solo por updated_at) y `runs(source, status, set_id, chapter_id)` para las queries de last_run_stats (hoy escanean runs filtrando por source). `idx_chapters_mostrar ON chapters(id, mostrar)` es casi inútil: `id` es PK (lookup directo); un índice útil sería `chapters(source, mostrar)` o parcial `WHERE mostrar=1`.
- **`sqlite_sequence`** volcada en el schema: artefacto del dump, ignorar.
- **`virtual_collections`/`virtual_items`**: sin uso real desde el frontend (solo el endpoint muerto). Decidir: implementar la feature o eliminar tablas+endpoint.
- **Fechas como TEXT ISO8601**: elección correcta para SQLite; el problema no es el tipo sino la mezcla UTC/local (bug 3.6) y la resolución de segundos (3.12).

## 6.3 Escalabilidad del schema

Con millones de attempts: la vista `problem_stats` y los CTE de madurez con `ROW_NUMBER()` sobre attempts crecerán linealmente. Mitigación natural: tabla agregada `problem_stats_mat` actualizada por trigger o en `localInsertAttempt` (el cliente ya tiene el punto único de escritura). No urgente por debajo de ~1M attempts.

---

# 7. FRONTEND

## 7.1 HTML/CSS

- **Estilos inline en ~80 elementos** (modal stats completo, config, pills, tablas generadas): imposibilita theming coherente y duplica valores (`padding:6px 8px` repetido 12 veces en templates JS). Mover a clases; ya existe un sistema de variables CSS bien planteado (`:root`) que los inline ignoran a veces (`var(--green, #4caf50)` inventa una variable inexistente — línea 4146; `var(--hover)` en gmLoadGameList tampoco existe → background vacío).
- Handlers `onclick=` en HTML mezclados con `addEventListener` en JS: dos convenciones.
- `#stats-modal` con `z-index:301` dentro de overlay `z-index:1300` con `isolation:isolate` — funciona, pero la gestión de z-index (300 hardcodeado por WGo, 400 flash, 10 pause, 1300 stats) merece una escala documentada.
- `overflow:hidden` en body + grid fijo: correcto para app-shell.

## 7.2 Accesibilidad

- Sin `aria-*` en tabs, modales ni botones icónicos (⚙, 📊, ☰ tienen `title`, insuficiente para lectores).
- Los modales no atrapan foco ni se cierran con foco gestionado (Escape sí funciona).
- Contraste: `--dim2 #7a6e60` sobre `#0e0c08` ≈ 4.0:1 en textos de 8-9px — por debajo de WCAG AA para texto pequeño. Para uso personal es una decisión estética válida; anotado.
- El tablero es canvas puro sin alternativa por teclado (inherente al dominio; aceptable).

## 7.3 Gestión de estado y eventos

- Ya cubierto en A5/3.7: estado global + listeners acumulativos es el defecto estructural nº1 del frontend.
- Monkey-patching de funciones para responsive (`loadAndRender = async function(...)`) — funciona pero rompe la trazabilidad (la función referenciada dentro de closures previas es la original). Concretamente: `loadAndRender` es llamada solo desde `nextProblem`, que resuelve el nombre en scope global → OK hoy; frágil.
- `window._boardClickHandler` compartido entre modo estudio y visor de partidas con arbitraje manual en `switchTab` — un flag `gmActive` adicional dentro del handler de games lo protege dos veces (defensa redundante que delata la fragilidad).

## 7.4 Memoria

- `idbOpen()` abre una **conexión IndexedDB nueva por operación** y nunca la cierra. Los navegadores las recolectan al perder referencia, pero con saves frecuentes se acumulan handles. Cachear la conexión (singleton).
- `imgCache` crece sin límite (aceptable: decenas de imágenes).
- Al cambiar de source se resetean arrays pero `chaptersCache` conserva claves por set_id **sin namespacing por source**: dos sources con el mismo `set_id` colisionan en el cache → chapters de un source mostrados/filtrados con datos de otro. **Bug real** si dos sources comparten set_ids (probable: ambos empiezan en 1). Se limpia en el change handler de source (línea 4105), lo que lo mitiga, pero `applyCollectionFilters` y `updateFreeChapters` escriben/leen sin source → clave compuesta `${source}:${set_id}` recomendada.

## 7.5 UX

- Auto-avance de 1 s tras acierto: bien. En fallo dentro de run también avanza (1 s) — no da tiempo a leer el refutation comment; considerar pausa en fallo con "tap to continue" (coherente con `_isReveal`).
- `alert()`/`confirm()` nativos para errores y borrados: bloqueantes y feos en PWA; sustituir por toasts/modal propio.
- El botón "↻ Sync" vive dentro del modal de config; el badge rojo en ⚙ ya orienta, pero un indicador de "pendientes sin sincronizar" (nº de attempts no pusheados) daría confianza real de no perder datos.
- Resize reset (bug 3.9) es también un problema de UX grave en móvil.

---

# 8. BACKEND

- **Estructura**: handlers planos + tabla de rutas GET; POST/PUT con rutas inline duplicando el patrón. Unificar en `ROUTES = {(method, path): handler}`.
- **HTTPServer**: cambiar a `ThreadingHTTPServer` (1 línea) + `protocol_version = "HTTP/1.1"` para keep-alive (hoy HTTP/1.0 por defecto: una conexión TCP nueva por request a través de Caddy).
- **Gestión de errores**: patrón `(dict, code)` | `dict` razonable; pero excepciones → 500 con `str(e)` (4.3) y `_read_body` fuera del try (3.11). Añadir helper `error(code, msg)` y capturar json/parse/validación como 400.
- **Logs**: mezcla de prints de depuración, prints de datos y ausencia de niveles. Usar `logging` con nivel INFO por defecto, DEBUG activable; eliminar prints numerados y el body-dump; systemd ya captura stdout (con `-u`, como ya tienes).
- **Validaciones**: inexistentes (tipos, enums, campos requeridos parciales). Un helper `require(body, campo, tipo)` cubriría el 90%.
- **Migraciones**: `migrate_db()` con `PRAGMA table_info` es un patrón casero válido; formalizar con tabla `schema_version` para poder ordenar migraciones futuras y detectar DB demasiado nueva/vieja.
- **Consistencia**: `handle_put_chapter_mostrar` normaliza con `int(bool(mostrar))`, `/sync/chapters_mostrar` escribe crudo — misma operación, dos contratos.
- **Apagado**: `serve_forever()` sin manejo de SIGTERM → systemd mata el proceso; con WAL es seguro, pero un `try/except KeyboardInterrupt` + `server_close()` es más limpio.

---

# 9. API — endpoint por endpoint

Convención evaluada: verbos, códigos, validación, consistencia JSON.

| Endpoint | Estado | Observaciones |
|---|---|---|
| `GET /db/collections` | Muerto (frontend no lo usa) | OK técnico; `NULLS LAST` requiere SQLite ≥3.30. Sin paginación. |
| `GET /db/chapters` | Muerto | Valida set_id presente pero no numérico (500 si no lo es). |
| `GET /db/problems` | Muerto | Tres ramas; sin límite → puede devolver 64k filas. |
| `GET /db/problem` | Muerto | 404 correcto. `problem_id` sin cast (compara TEXT contra INTEGER; funciona por afinidad). |
| `GET /db/runs` | Muerto | OK. |
| `GET /db/run/items` | Muerto | OK. |
| `GET /db/last_run_stats(_all)` | Muertos | N+1 interno; `HAVING id=MAX(id)` no estándar. |
| `GET /db/struggling` | Muerto | N+1 por problema (§5.1 P3). `n` sin límite superior. |
| `GET /db/difficulty_range` | Muerto | OK. |
| `POST /db/attempt` | Muerto | No valida result; usa reloj del servidor (bien) pero el resto del sistema usa reloj cliente (inconsistente). |
| `POST /db/run` | Muerto | Único usuario de `virtual_*`. Devuelve 200 en creación (debería 201). |
| `PUT /db/run` | **Vivo** (¿lo llama algo? el frontend no — revisar apps móviles antiguas) | Sin `status` → ok silencioso (3.11). |
| `PUT /db/chapter/mostrar` | Vivo | OK; normaliza bool. |
| `PUT /sync/chapters_mostrar` | Vivo | Handler inline en `do_PUT` (no en función); sin validación; payload completo cada sync. Semánticamente es un POST bulk-upsert. |
| `GET /sync/snapshot` | Vivo | Sin auth (crítico 4.1); sin paginación; incluye sm2_state (correcto para bootstrap). |
| `GET /sync/pull` | Vivo | Cursores por id: correctos para datos server-side pero interactúan mal con el push (bug 3.1). Devuelve run_items de runs nuevos: bien. |
| `POST /sync/push` | Vivo | El más complejo; dedup uuid bien planteado; log de debug a disco; fallback triple para run_id del attempt (funciona, difícil de mantener); attempts sin uuid deduplicados por timestamp de segundo (frágil). |
| `POST /sync/check_runs` | Vivo | OK; usado por syncDeletedRuns (con el bug de orden 3.2, que es del cliente). |
| `GET /sync/sm2/pull` / `POST /sync/sm2/push` | Vivos | Last-write-wins por `updated_at` (comparación de strings ISO: válida por formato fijo). Sin validación de campos. |
| `GET /sync/static_version` | Vivo | `MAX(rowid) FROM problems` como versión: no detecta ediciones ni borrados (solo inserciones). Sustituir por `PRAGMA user_version` incrementado por el pipeline. |
| `GET /sync/games` | Vivo | Dump completo cada vez. |
| `POST /admin/import_games` | Vivo | "admin" sin auth. Dedup por nombre: razonable. |
| `POST /db/runs/delete` | Vivo | Acepta ids **y** uuids; los ids son peligrosos cross-device (3.3). Debería aceptar solo uuids. |

Transversal: nunca se usa 401/403 (no hay auth), 201, 204, ni 400 para tipos inválidos (van a 500). El envelope JSON es consistente (`{ok}`/`{error}`), bien.

---

# 10. CÓDIGO INNECESARIO (inventario para borrar)

**Servidor** — endpoints/funciones eliminables tras confirmar que ningún cliente antiguo los usa:
`handle_get_collections`, `handle_get_chapters`, `handle_get_problems`, `handle_get_problem`, `handle_get_runs`, `handle_get_last_run_stats`, `handle_get_last_run_stats_all`, `handle_get_struggling`, `handle_get_difficulty_range`, `handle_get_run_items`, `handle_post_attempt`, `handle_post_run` (+ soporte virtual), y sus entradas de routing. También: prints "1"–"9", `print [handle]`, bloque `sync_push_log.json`.

**Cliente**: limpieza `_studyListener` (3661-3662), doble `appendChild` (3292), variable `lightMode` global, comentario fósil (2970), redeclaraciones de `PCT_YELLOW`/`color` (usar `pctColor`), `var(--green)`/`var(--hover)` inexistentes.

**Schema**: `virtual_collections`/`virtual_items` (si se descarta la feature), `idx_chapters_mostrar` (sustituir por índice útil).

---

# 11. ESCALABILIDAD

- **100.000 problemas**: snapshot JSON ≈ 40-60 MB sin gzip (~8-12 MB gzip). El cliente lo parsea entero en memoria + INSERT por fila en sql.js (~100k statements) → decenas de segundos de UI congelada en móvil, y `saveDB()` exporta ~50-80 MB a IndexedDB. **Cuello de botella nº1**: bootstrap. Solución: snapshot por source/paginado + inserts en transacción (sql.js ya agrupa, pero envolver en `BEGIN/COMMIT` explícito acelera 10-50×) + P1 (DB fría/caliente separadas).
- **Miles de usuarios**: el diseño actual no lo soporta ni debe: DB única sin tenant, sin auth, single-thread. Escalar a multiusuario = reescritura del servidor (auth, user_id en cada tabla, Postgres o SQLite-por-usuario). Fuera de alcance salvo decisión de producto.
- **Múltiples clientes sincronizando** (tu caso real: PC + móvil): los bugs 3.1/3.2/3.3 son exactamente los que muerden aquí. Tras corregirlos, el modelo uuid+LWW aguanta bien 2-5 dispositivos. El riesgo restante es el reloj de cliente como cursor SM-2 (3.10).
- **Miles de runs**: `loadRuns` renderiza todos sin paginar y `localGetRuns` agrega ok_count por run — con 5.000 runs el panel tardará; paginar/limitar a últimos 100 + "load more".
- **Millones de intentos**: CTEs con window functions sobre attempts (madurez, struggling) pasan a segundos; materializar agregados (§6.3). `sync/pull` desde cursor 0 en un cliente nuevo descargaría millones de filas JSON: paginar el pull (`limit` + bucle) es imprescindible antes de llegar ahí.

---

# 12. MEJORAS FUNCIONALES (visión de producto)

1. **Indicador de "datos pendientes de sync"** (nº attempts/runs no confirmados por el servidor) en el header. Justificación: es un sistema offline-first cuyo mayor riesgo percibido es perder trabajo; la confianza es una feature.
2. **Pausa en fallo durante runs** con el comentario de refutación visible hasta tap. Justificación: el valor pedagógico del fallo se pierde con el auto-avance de 1 s.
3. **Modo "second chance" configurable**: tras fallo, opción de reintentar el problema al final del run (cola de repesca). Justificación: estándar en apps SRS; refuerza el aprendizaje inmediato sin falsear stats (el attempt ya quedó como wrong).
4. **Heatmap/calendario de actividad** (attempts por día, estilo GitHub) en el modal de stats. Justificación: los datos ya existen (`created_at`); refuerzo de hábito con coste mínimo.
5. **Gráfica de evolución de madurez por nivel** (serie temporal de `dominated`): requiere snapshot diario de agregados (tabla `daily_stats` alimentada al cerrar sesión). Justificación: hoy solo ves el presente; la tendencia es la métrica motivacional real.
6. **Export/backup manual desde el cliente** (botón "descargar mi DB" → blob del export). Justificación: hoy el usuario depende de IndexedDB + servidor; un backup de un click protege contra limpiezas de navegador.
7. **Filtro de tiempo en Free Practice** ("problemas donde tardo >30s"): `avg_time_ms` ya existe. Justificación: la lentitud es señal de no-dominio que el % de acierto no captura.
8. **Runs virtuales desde la UI** (la infraestructura server existe): crear colecciones ad-hoc desde struggling/review. O eliminarla (decisión pendiente, §10).
9. **Atajos de teclado en runs** (1=restart era imposible, pero P ya existe): añadir `U`=undo visual, `R`=restart también en runMode con confirmación. Justificación: fricción en sesiones largas de escritorio.
10. **Deshacer borrado de run** (soft-delete con `deleted_at` en vez de DELETE): coherente con el sync distribuido y elimina la clase entera de bugs 3.2/3.3 (los borrados se propagan como datos, no como ausencias).

---

# 13. REFACTORIZACIONES RECOMENDADAS (por impacto)

| # | Refactor | Beneficio | Dificultad | Riesgo | Prioridad |
|---|---|---|---|---|---|
| R1 | **Sync v2: marcar pendientes + dedup por uuid en pull + índices uuid** (fixes 3.1) | Corrige duplicación de stats, reduce red/CPU por intento en órdenes de magnitud | Media | Medio (tocar sync exige plan de migración: backfill `synced=1` para lo ya confirmado) | 🔴 |
| R2 | **Soft-delete de runs** (`deleted_at` propagado por sync) y eliminación de `purgeEmptyRuns`/`syncDeletedRuns` actuales (fixes 3.2, 3.3) | Elimina las dos rutas de pérdida de datos cross-device | Media | Medio | 🔴 |
| R3 | **Persistencia fiable**: saveDB debounced tras cada intento; después, split DB fría/caliente (fixes 3.4, P1) | Cierra la ventana de pérdida; habilita escalar a 100k problemas | Fase A baja / Fase B alta | Bajo / Medio | 🔴 / 🟡 |
| R4 | **Registro único de listeners** (init una vez; funciones populate* solo rellenan options) (fix 3.7) | Elimina acciones duplicadas y runs fantasma | Baja | Bajo | 🔴 |
| R5 | **Auth token + CORS restringido + ThreadingHTTPServer + límites** (fixes §4.1-4.3) | Cierra las vulnerabilidades críticas con ~40 líneas | Baja | Bajo | 🔴 |
| R6 | **Capa `repo.js`**: extraer todas las queries locales a un módulo con la subquery de stats y el CTE de madurez definidos una vez | Mata la duplicación §2.1; prerequisito para testear | Media | Bajo | 🟠 |
| R7 | **Máquina de estados de sesión** (IDLE/RUN/FREE/REVIEW/GAMES) que posea `activeRunId`, `runIdx`, contadores | Elimina bugs de estado (3.8) y simplifica setupInteractiveMode | Alta | Medio | 🟠 |
| R8 | **Modularizar el monolito** (esbuild → single file en deploy) | Mantenibilidad a largo plazo; habilita tests | Alta | Medio | 🟠 |
| R9 | **Unificar tipos** (`result` TEXT + CHECK, `problem_id` TEXT en ambos lados, `paused_ms` en servidor y en push) | Elimina bombas de afinidad §6.1 | Media | Medio (migración de datos) | 🟠 |
| R10 | **Purgar endpoints muertos + logging estructurado + validación helper** | Reduce superficie y ruido | Baja | Bajo | 🟡 |
| R11 | Escapado HTML sistemático (`esc()`) en todos los innerHTML con datos | Cierra XSS residual | Baja | Bajo | 🟡 |
| R12 | Queries N+1 → window functions (struggling, last_run_stats, maturity all) | Rendimiento de stats con historial grande | Media | Bajo | 🟡 |

---

# 14. CALIDAD PROFESIONAL — evaluación

Criterio: auditoría como si fuera un producto de empresa. Entre paréntesis, la nota "ajustada a contexto" (herramienta personal mono-usuario construida incrementalmente).

| Área | Nota | Justificación |
|---|---|---|
| Arquitectura | 5/10 (7) | El modelo offline-first con sync por uuid es un diseño *bueno y nada trivial*; lo penalizan el monolito, la doble capa de datos y los 4 protocolos de sync conviviendo. |
| Código | 4.5/10 (6.5) | Denso pero legible localmente; duplicación alta, funciones largas, código muerto, estado global. Los comentarios en puntos delicados (mostrar, SM-2) son buenos. |
| Seguridad | 2/10 (4) | Sin auth en un servidor público con endpoints destructivos es suspenso objetivo aunque no haya datos sensibles. A favor: cero SQL injection, parametrización impecable. |
| Escalabilidad | 5/10 (7) | Sobrada para 1 usuario; bootstrap y sync-completo son los techos reales. El diseño uuid permite crecer con arreglos acotados. |
| Mantenibilidad | 4/10 (6) | Un solo desarrollador con contexto lo mantiene; cualquier otro (o un modelo de IA) sufre: 4.183 líneas sin módulos, estilos inline, sin tests. |
| Rendimiento | 6/10 (7.5) | La app *se siente* rápida (todo local); los costes ocultos (export completo, push-historial, N+1) crecen con el uso. |
| Base de datos | 6/10 (7) | Schema razonable, índices pensados, vista bien usada; penalizan divergencia cliente/servidor, tipos incoherentes y falta de constraints/uuid index. |
| Frontend | 5.5/10 (7) | UI cuidada y coherente estéticamente; gestión de estado y listeners es el punto débil; accesibilidad ausente. |
| Backend | 4.5/10 (6) | Handlers claros y simples; single-thread, sin validación, logs de debug en producción, endpoints muertos. |
| API | 5/10 (6.5) | Envelope consistente y dedup bien pensado; códigos HTTP pobres, sin versionado, mezcla REST/RPC. |
| UX | 7/10 (8) | El flujo de estudio está muy bien resuelto (auto-avance, ghost stone, tap-confirm, pausa, sonido); pierde por alerts nativos, auto-avance en fallo y el reset por resize. |

**Global: 5/10 profesional · 6.7/10 en contexto.** Es un sistema personal maduro y funcional con un núcleo de diseño (offline-first + uuid sync + SM-2 local) por encima de la media de proyectos personales; sus deudas están concentradas y son corregibles: seguridad del servidor, integridad del sync y estructura del monolito.

