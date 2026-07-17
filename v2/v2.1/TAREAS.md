# TAREAS — TsumeVault v2 · Plan de trabajo delegable

Preparado por el arquitecto/jefe de proyecto (Claude, Mythos-class) para su
ejecución por modelos inferiores (Sonnet 4.6 / Opus) en chats de este mismo
proyecto de claude.ai. Cada tarea es atómica, autovalidable e independiente.

---

## FLUJO OPERATIVO (leer antes de lanzar nada)

1. **Prerequisito único (una vez)**: reemplaza en el conocimiento del proyecto
   los archivos por sus versiones ACTUALES (las de outputs de la sesión del
   arquitecto): `tsumevault.html`, `tsumevault_server.py`, `db_schema.sql`,
   `IMPLEMENTATION_STATUS.md`, y sube el kit de validación completo:
   `KIT_README.md`, `run_all.sh`, `test_server.py`, `harness.js`,
   `harness_compat.js`, `extract_bundle.py`, `harness_bundle_old.js`.
   Mantén también `AUDITORIA_TSUMEVAULT_v2.md`.
2. **Un chat nuevo por tarea.** Pega el PREÁMBULO COMÚN + el bloque de la
   tarea, juntos, como primer mensaje.
3. **Nunca dos tareas en paralelo**: todas tocan el mismo monolito; los
   resultados serían inmezclables.
4. **Al terminar cada tarea**: comprueba que el modelo reporta `✔ TODO OK`,
   descarga sus outputs y **reemplaza los archivos del proyecto** por los
   nuevos antes de lanzar la siguiente tarea (incluido `harness.js` /
   `extract_bundle.py` si la tarea los amplió).
5. **Si el modelo duda, se desvía del alcance o no consigue TODO OK**: aborta
   el chat y trae la tarea de vuelta al arquitecto. No dejes que "lo arregle
   con más cambios".
6. **Orden recomendado**: el de numeración. Son independientes, pero T1→T8
   son las más pequeñas (rodaje del flujo) y T9 conviene hacerla sola y con
   calma (toca el corazón del sync).

---

## PREÁMBULO COMÚN (pegar al inicio de CADA tarea, tal cual)

```
Eres un ingeniero senior ejecutando UNA tarea acotada sobre TsumeVault v2, una
aplicación personal offline-first de tsumego: cliente single-file
tsumevault.html (sql.js en el navegador, ~4.300 líneas) + servidor Python
tsumevault_server.py (SQLite). Los archivos ACTUALES y un kit de validación
están en el conocimiento del proyecto (/mnt/project). Lee KIT_README.md antes
de empezar.

REGLAS DE ORO (orden de prioridad): 1) no perder datos, 2) no duplicar datos,
3) no romper compatibilidad cliente↔servidor (nunca un cambio que exija
desplegar ambos a la vez), 4) ante dos soluciones, SIEMPRE la más conservadora.

PROHIBIDO SALVO QUE LA TAREA LO PIDA: modularizar o dividir archivos, renombrar
funciones existentes, cambiar tipos de columnas, reordenar código no
relacionado, "aprovechar para limpiar", tocar endpoints o funciones ajenas a la
tarea, eliminar código.

MÉTODO DE TRABAJO OBLIGATORIO:
1. Prepara el entorno:
   mkdir -p /home/claude/work && cp /mnt/project/* /home/claude/work/ && cd /home/claude/work && bash run_all.sh
   La línea base DEBE terminar en "✔ TODO OK". Si no, DETENTE e informa: no
   toques nada sobre una base rota.
2. EXPLICA tu plan y el alcance exacto de los cambios ANTES de editar código,
   y espera confirmación solo si detectas ambigüedad real; si la tarea es
   clara, procede tras exponer el plan.
3. tsumevault.html usa CRLF: edita con un script Python que verifique que cada
   patrón a sustituir aparece EXACTAMENTE 1 vez y aborte si no. Las líneas de
   la auditoría están desfasadas: localiza por NOMBRE de función.
4. Tras cada edición del cliente: regenera y valida sintaxis
   (python3 extract_bundle.py && node --check client_script.js).
5. Al terminar: bash run_all.sh de nuevo → "✔ TODO OK" íntegro (nada de lo
   existente se rompe) + tus verificaciones específicas en verde.

ENTREGABLES (copiar a /mnt/user-data/outputs y presentarlos):
- Los archivos modificados (tsumevault.html y/o tsumevault_server.py, y
  harness.js / extract_bundle.py / test_server.py si los ampliaste).
- IMPLEMENTATION_STATUS.md actualizado: marca el apartado de la auditoría
  correspondiente y añade una entrada breve en "Decisions".
- NOTA_TAREA.md: qué cambiaste, dónde (funciones), por qué, decisiones tomadas
  y cómo lo validaste.
NO des la tarea por terminada sin el run_all.sh final en verde.
```

---

## TAREA 1 — Bug 3.5: doble incremento de `sessionOk` en Free Practice

```
TAREA: corregir el bug 3.5 de la auditoría (doble incremento de sessionOk).

CONTEXTO: en la función playOpponent del cliente, en la rama "sin hijos =
correcto" hay un bloque similar a:
  showResult(true, ''); if (!hadWrong) { recordAttempt('correct'); if (!runMode) sessionOk++; }
recordAttempt YA incrementa sessionOk cuando !runMode, así que todo problema
resuelto cuyo nodo final no lleve comentario RIGHT suma 2 al contador de
sesión en Free Practice/Review. Solo afecta a la UI de sesión, no a la DB.

CAMBIO REQUERIDO: eliminar el incremento duplicado (el `if (!runMode)
sessionOk++;` de playOpponent), dejando recordAttempt como único responsable.
Antes de tocar nada, busca TODOS los puntos donde se incrementa sessionOk y
verifica cuáles duplican a recordAttempt: corrige exactamente los duplicados y
ninguno más. Documenta en NOTA_TAREA.md cada punto encontrado y tu veredicto.

VALIDACIÓN: run_all.sh íntegro (este bug es de UI y el arnés no lo cubre;
tu validación específica es el análisis exhaustivo de los call sites de
sessionOk documentado en la nota, más una lectura del flujo showResult →
recordAttempt confirmando que cada resolución suma exactamente 1).

FUERA DE ALCANCE: cualquier otro contador, el flujo de runs (runMode true).
```

## TAREA 2 — Bug 3.6: zona horaria en Review (fecha UTC vs local)

```
TAREA: corregir el bug 3.6 de la auditoría (regresión de zona horaria).

CONTEXTO: localGetReviewProblems, localCountReviewPending y updateSm2 usan
  new Date().toISOString().slice(0, 10)
que es la fecha UTC. En CEST (UTC+2), entre las 00:00 y las 02:00 locales la
fecha UTC es "ayer": los problemas que vencen hoy no aparecen hasta las 2 AM,
y updateSm2 calcula due_date con el mismo desfase inverso.

CAMBIO REQUERIDO: crea UNA función auxiliar localDateStr(d = new Date()) que
devuelva la fecha LOCAL en formato YYYY-MM-DD (implementación recomendada:
d.toLocaleDateString('sv-SE'), o construcción manual con getFullYear/getMonth/
getDate con padding). Sustituye la expresión UTC por localDateStr() en las
TRES funciones (y solo en el contexto de fechas de review/due_date; busca si
hay más usos de .toISOString().slice(0, 10) ligados a due_date y decide caso a
caso, documentándolo). NO toques los timestamps completos (created_at,
started_at, updated_at…): esos siguen en ISO UTC y así deben quedarse — son
los que viajan por el protocolo de sync.

NOTA DE COHERENCIA: due_date se almacena como cadena YYYY-MM-DD y se compara
con <=; al cambiar la base de UTC a local, algún due_date existente puede
adelantarse/atrasarse un día una única vez. Es aceptable y esperado;
documéntalo en la nota.

VALIDACIÓN: run_all.sh íntegro. Añade además al final de harness.js un
mini-escenario que verifique que updateSm2 produce un due_date == fecha local
de hoy + interval días (calculada con la misma lógica local en el test), y
que localCountReviewPending (añádela a extract_bundle.py) cuenta un registro
con due_date de hoy local. Ejecuta run_all.sh con el escenario incluido.

FUERA DE ALCANCE: el algoritmo SM-2 en sí, el formato de due_date en DB, los
timestamps del protocolo de sync.
```

## TAREA 3 — Bug 3.7 / R4: listeners acumulativos (registro único)

```
TAREA: corregir el bug 3.7 de la auditoría (listeners duplicados).

CONTEXTO: populateFreeFilters añade listeners ('change' a fp-col, 'click' a
fp-start) CADA VEZ que se llama, y se llama desde loadCollections (arranque,
tras cada sync manual, tras cambiar visibilidad o source). Tras N recargas, un
click en "Start practice" ejecuta startFreePractice N veces.
populateReviewFilters hace lo mismo con rv-start y rv-col, y es peor: cada
click fantasma en rv-start crea e inserta UN RUN de review en la DB, que
además se sincroniza (runs basura reales).

CAMBIO REQUERIDO: registro único. Patrón recomendado (mínimo y mecánico): en
cada una de esas funciones, proteger los addEventListener con un guard de
inicialización única, p. ej. un flag en el propio elemento:
  const el = document.getElementById('fp-start');
  if (!el.dataset.bound) { el.dataset.bound = '1'; el.addEventListener(...); }
Aplícalo a los CUATRO listeners citados. Después, haz una pasada de búsqueda
de OTROS addEventListener dentro de funciones que se llamen repetidamente
(cualquier populate*/render*/load* invocada más de una vez) y aplica el mismo
guard donde proceda, documentando cada caso en la nota. OJO: los listeners
registrados una sola vez en el init NO se tocan.

CUIDADO: si el listener captura variables del closure que cambian entre
llamadas (p. ej. la lista de colecciones actual), el guard congelaría valores
obsoletos. En esos casos el listener debe leer el estado en el momento del
click (desde el DOM o variables globales), no del closure. Verifica esto para
los cuatro casos y documéntalo.

VALIDACIÓN: run_all.sh íntegro + demostración en la nota: para cada listener
corregido, explica qué estado lee y por qué sigue siendo correcto tras N
llamadas a populate*.

FUERA DE ALCANCE: refactorizar el sistema de eventos, delegación de eventos
global, cambiar la estructura del DOM.
```

## TAREA 4 — Bug 3.8: runs de review con `total=0` inconsistentes

```
TAREA: corregir el bug 3.8 de la auditoría (runs de review incoherentes).

CONTEXTO: startReview crea un run con total=0, done=0. localInsertAttempt hace
done=done+1 y cierra el run si done>=total → el run de review se CIERRA tras
el primer intento, pero activeRunId sigue apuntándole y los siguientes
intentos siguen incrementando done sobre un run closed (p. ej. done=25,
total=0). Además, al terminar la review, showSessionEnd no limpia activeRunId
(solo endRun lo hace, y la review nunca pasa por endRun porque runMode=false):
intentos posteriores de otros flujos podrían atribuirse al run de review
cerrado.

CAMBIO REQUERIDO (enfoque conservador, dos piezas):
1. startReview debe crear el run con total = número de problemas de la sesión
   de review (la lista ya se conoce al arrancar la review). Así el cierre
   por done>=total ocurre exactamente al terminar, como en los runs normales.
2. Al finalizar la sesión de review (el punto donde se muestra el fin de
   sesión), limpiar activeRunId (ponerlo a null) si el run activo es de
   review. Localiza el flujo real: showSessionEnd o equivalente.
Con la pieza 1, el guard existente de localInsertAttempt (done>=total &&
status='open') deja de dispararse en el primer intento; NO toques
localInsertAttempt.

MIGRACIÓN DE DATOS: NO retoques runs de review históricos ya incoherentes
(done>total) — quedan como están; solo se corrige el comportamiento futuro.
Documenta esta decisión.

VALIDACIÓN: run_all.sh íntegro. Añade al final de harness.js un escenario que
(añadiendo startReview y las funciones que necesite a extract_bundle.py, o
simulando su efecto con localInsertRun de tipo review + total=N si startReview
arrastra demasiado DOM — decide y documenta): cree un run de review con 3
problemas, registre 3 intentos, y verifique que el run queda closed con
done=3, total=3, y que un cuarto intento con activeRunId ya limpiado no
incrementa done. Ejecuta run_all.sh con el escenario.

FUERA DE ALCANCE: el flujo de runs normales (endRun), el algoritmo SM-2,
runs históricos.
```

## TAREA 5 — Bug 3.9: resize resetea el problema en curso

```
TAREA: corregir el bug 3.9 de la auditoría (resize pierde el progreso del
intento y puede duplicar attempts).

CONTEXTO: el handler de resize hace initBoard + renderProblem(currentProblem),
reconstruyendo el modo interactivo desde el nodo raíz: si el usuario está a
mitad de secuencia pierde el progreso, y como attemptRecorded/hadWrong se
resetean, un fallo ya registrado seguido de acierto tras el resize registra un
attempt 'correct' adicional (doble attempt del mismo problema). En móvil se
dispara con el cambio de orientación o la aparición del teclado.

CAMBIO REQUERIDO (enfoque conservador): NO reconstruyas el estado lógico en el
resize; solo re-renderiza el tablero con el estado ACTUAL. Analiza qué
distingue "estado visual" (canvas/tamaños) de "estado de la partida en curso"
(nodo actual de la secuencia, hadWrong, attemptRecorded, jugadas colocadas) en
el código real, y modifica el handler de resize para redibujar sin resetear lo
segundo. Si el board object no permite redimensionar sin reconstruir,
reconstrúyelo pero restaura después el estado lógico guardado (posición
actual de piedras + variables de intento). Elige la vía que exija menos
cambios y explícala en el plan ANTES de implementar.

Añade además un debounce de ~200 ms al handler de resize (los móviles disparan
ráfagas de eventos durante la rotación).

VALIDACIÓN: run_all.sh íntegro (este flujo es de UI/canvas y el arnés no lo
cubre). Tu validación específica: en la nota, describe el recorrido completo
del estado ante un resize (qué variables sobreviven y por qué), y enumera los
tres casos verificados mentalmente: (a) resize antes de tocar nada, (b) resize
a mitad de secuencia sin fallos, (c) resize después de un fallo registrado y
acierto posterior → debe registrarse 0 attempts nuevos en (b) y (c).

FUERA DE ALCANCE: cambios visuales o de layout, el sistema de renderizado en
general, otros handlers de eventos.
```

## TAREA 6 — Bug 3.10 (resto UI): unificar el botón de sync con tryAutoSync

```
TAREA: eliminar la sección crítica duplicada del botón de sincronización
(parte pendiente del 3.10 de la auditoría).

CONTEXTO: tryAutoSync protege la concurrencia con la variable syncInProgress y
devuelve true/false según el resultado, pero el handler del botón manual de
sync implementa su PROPIA sección crítica y su propia gestión de setSyncStatus
con temporizadores que pueden pisarse (el setTimeout de ~3 s del estado "ok"
puede rehabilitar el botón en mitad de un sync posterior).

CAMBIO REQUERIDO:
1. El handler del botón pasa a delegar en tryAutoSync(false) (modo no
   silencioso) y elimina su lógica duplicada de exclusión. Conserva cualquier
   comportamiento EXCLUSIVO del sync manual que detectes (p. ej. si tras el
   sync manual se llama a loadCollections o syncDeletedRuns, mantenlo,
   encadenado al resultado de tryAutoSync).
2. Centraliza los temporizadores de setSyncStatus: si hay un setTimeout que
   restaura el estado visual, guárdalo en una variable y haz clearTimeout
   antes de programar el siguiente, para que un sync nuevo no sea pisado por
   el temporizador de uno anterior.
Estudia primero el handler completo y lista en tu plan qué conserva, qué
elimina y qué delega.

VALIDACIÓN: run_all.sh íntegro (tryAutoSync y doSync están cubiertos por el
arnés; tu cambio no debe alterar su firma ni su semántica — si el arnés se
rompe, tu cambio fue más allá del alcance). En la nota: tabla antes/después
del flujo del botón.

FUERA DE ALCANCE: doSync, la transaccionalidad del sync, los cursores,
cualquier cambio de protocolo.
```

## TAREA 7 — Bug 3.12a: `resumeRun` de un run ya completado

```
TAREA: corregir el primer punto del 3.12 de la auditoría (resumeRun de un run
terminado rejuega desde el item 0).

CONTEXTO: al reanudar un run abierto cuyos items están TODOS respondidos,
findIndex devuelve -1, runIdx queda en -2 → -1, y el run se rejuega desde el
item 0; recordAttempt añadiría attempts nuevos actualizando run_items ya
resueltos.

CAMBIO REQUERIDO: en resumeRun, si no queda ningún item sin responder
(findIndex === -1), NO entrar en modo run: cerrar el run si sigue open
(localUpdateRunStatus(id, 'closed') — ya marca el re-push del cierre al
servidor), informar al usuario con el mecanismo de aviso más simple ya
existente en la app (busca cómo notifica otras situaciones; si no hay nada,
un alert es aceptable en esta app personal), y refrescar la lista de runs.

VALIDACIÓN: run_all.sh íntegro. Si resumeRun es extraíble al arnés sin
arrastrar demasiado DOM (revisa sus dependencias), añade un mini-escenario:
run con todos los items respondidos + resumeRun → el run queda closed y
runMode sigue false. Si no es extraíble limpiamente, documenta por qué y
valida con el análisis del flujo en la nota.

FUERA DE ALCANCE: el flujo normal de reanudación (con items pendientes),
endRun, la UI de la lista de runs más allá del refresco.
```

## TAREA 8 — Bug 3.12b: bare columns en GROUP BY + `AE` en setup SGF

```
TAREA: corregir dos puntos menores del 3.12 de la auditoría (independientes
entre sí; hazlos en este orden).

PARTE A — bare columns: las queries del tipo
  GROUP BY chapter_id HAVING id = MAX(id)
(en las funciones JS de stats del cliente tipo localGetLastRunStats*, y sus
equivalentes del servidor handle_get_last_run_stats*) dependen del
comportamiento no estándar de SQLite con columnas fuera del GROUP BY.
Reescríbelas de forma estándar y equivalente, p. ej. con subconsulta:
  WHERE id IN (SELECT MAX(id) FROM runs ... GROUP BY chapter_id)
o con window function ROW_NUMBER() si encaja mejor. REGLA: el resultado debe
ser EXACTAMENTE el mismo. Antes de sustituir, escribe un script de
comparación (Node con sql.js o Python con sqlite3) que pueble una DB sintética
con varios runs por capítulo y verifique que query vieja y nueva devuelven
filas idénticas; inclúyelo en outputs como compare_queries.{js,py}. Las
versiones del servidor: corrígelas solo si el cambio es el mismo patrón
mecánico; NO las elimines aunque parezcan endpoints muertos.

PARTE B — AE en getSetupStones: la función solo lee las propiedades AB/AW del
SGF e ignora AE (empty) en la rama de properties; si un SGF usa AE en el
setup, se renderizan piedras que deberían estar borradas. Añade el manejo de
AE (eliminar de la posición las coordenadas listadas) de forma simétrica a
como se procesan AB/AW.

VALIDACIÓN: run_all.sh íntegro + compare_queries en verde (parte A) + en la
nota, un SGF de ejemplo con AE y la posición resultante esperada (parte B).

FUERA DE ALCANCE: PK de run_items (requiere reconstruir tabla — NO tocar),
resolución de segundo en now_iso, SFX de iOS.
```

## TAREA 9 — `sync_meta`: cursores de sincronización dentro de la DB del cliente

```
TAREA: mover los cursores de sync del cliente de localStorage a una tabla
sync_meta dentro de la propia DB sql.js, para que datos y cursores vivan y
mueran juntos (cierra de raíz los cursores huérfanos, incluido el reset
parcial que la corrección mínima actual no cubre).

⚠ Esta tarea toca el corazón de doSync. Ve despacio, plan detallado primero.

CONTEXTO ACTUAL (léelo en el código antes de nada): doSync lee
last_pull_attempt_id, last_pull_run_id y last_sm2_sync de localStorage (con un
guard que los ignora si la tabla local correspondiente está vacía), acumula
los valores nuevos en un objeto cursorUpdates, y los escribe en localStorage
DESPUÉS del saveDB() final.

CAMBIO REQUERIDO:
1. Migración cliente (en migrateSyncColumns o función hermana llamada desde
   los mismos puntos): CREATE TABLE IF NOT EXISTS sync_meta (key TEXT PRIMARY
   KEY, value TEXT). Si la tabla acaba de crearse Y localStorage tiene valores
   de los tres cursores, impórtalos una única vez (INSERT). Añade la tabla
   también a createSchema para instalaciones nuevas.
2. Helpers: getSyncMeta(key) → string|null y setSyncMeta(key, value).
3. doSync: lee los cursores con getSyncMeta (elimina las lecturas de
   localStorage; conserva INTACTOS los guards de tabla vacía como cinturón).
   Escribe los cursores con setSyncMeta ANTES del saveDB() final (quedan
   atómicos con los datos en el mismo export — esta es la gran ventaja) y
   ELIMINA el bloque post-saveDB de cursorUpdates→localStorage.
4. NO escribas más en localStorage esos tres cursores (las claves viejas
   quedan huérfanas; no las borres: sirven de fallback si el usuario vuelve a
   una versión anterior del cliente).

ADAPTACIÓN DEL ARNÉS (obligatoria, parte de la tarea): los escenarios E4 y E13
de harness.js manipulan/leen los cursores vía B.store/localStorage. Adáptalos
para operar vía la DB (dbExec/dbQueryOne sobre sync_meta) manteniendo su
INTENCIÓN exacta: E4 = re-pull forzado sin duplicados; E13 = reset de DB →
los cursores mueren con ella (con sync_meta esto es automático: verifica que
tras el reset la DB nueva no tiene cursores y se recupera todo). Añade además
un escenario E15: dispositivo con datos y cursores en sync_meta → simular
migración desde localStorage (dispositivo con cursores SOLO en localStorage y
tabla sync_meta ausente → tras migrar, los valores están en sync_meta y el
sync no re-descarga el historial completo).

VALIDACIÓN: run_all.sh íntegro con E4/E13 adaptados y E15 nuevo en verde.

FUERA DE ALCANCE: cursores del lado servidor (no existen), sync_token y
sync_server_url (SIGUEN en localStorage: deben sobrevivir a un reset de DB),
static_version (déjalo donde está), cualquier cambio de protocolo.
```

## TAREA 10 — R11: escapado HTML sistemático (`esc()`)

```
TAREA: cerrar el punto 4.5/R11 de la auditoría (XSS almacenado en el cliente).

CONTEXTO: varios render usan innerHTML interpolando datos de la DB sin
escapar: col.name, chap.name, run.label, r.collection_name, r.source… en
renderCollectionsList, renderChapterList, loadRuns, renderStatsTable,
renderByLevel, renderGlobalPending (y puede haber más). Combinado con un
servidor accesible, datos maliciosos llegarían al DOM con ejecución JS.

CAMBIO REQUERIDO:
1. Función auxiliar única:
   function esc(s) { return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
2. Inventario exhaustivo: lista TODOS los usos de innerHTML (y
   insertAdjacentHTML si hay) del cliente. Clasifica cada interpolación en
   (a) dato de DB/servidor → envolver en esc(), (b) markup propio constante →
   no tocar, (c) número/booleano generado → no hace falta pero esc() no daña.
   Incluye el inventario completo en NOTA_TAREA.md con el veredicto por caso.
3. Aplica esc() a todos los (a). CUIDADO con los atributos: las
   interpolaciones dentro de atributos HTML (title="...", data-*="...")
   también se escapan; las que van dentro de onclick="...(${id})" — si
   existen — escapa el valor Y documenta el caso (no refactorices el patrón
   onclick en esta tarea).

VALIDACIÓN: run_all.sh íntegro (los render son de UI; el arnés cubre que no
rompiste el sync). Validación específica: script rápido (Node) que cargue
client_script.js como texto y verifique que en las 6 funciones citadas no
queda ninguna interpolación ${...} de los campos listados sin envolver en
esc( — inclúyelo como check_esc.js en outputs y su salida en la nota.

FUERA DE ALCANCE: CSP, sanitización del lado servidor, refactor de los render.
```

## TAREA 11 — Servidor: `schema_version` + SIGTERM + `sgf_path` + params numéricos

```
TAREA: cuatro mejoras menores de robustez del servidor (independientes; en
este orden). Solo tsumevault_server.py.

A) schema_version formal: PRAGMA user_version. Al arrancar, tras las
   migraciones existentes, si user_version < 1 → set a 1. Envuelve las
   migraciones actuales en un guard "if user_version < 1" SOLO si son
   idempotentes tal cual (léelas: ALTER en try, CREATE IF NOT EXISTS, dedup);
   si alguna no lo es, deja el guard fuera de ella y documenta. Objetivo:
   futuras migraciones se escriben como "if user_version < N: ... ; set N".

B) SIGTERM/SIGINT limpio: signal handler que haga server.shutdown() +
   server_close() y salga con código 0, para que systemd/docker no maten a
   mitad de request. OJO: shutdown() no puede llamarse desde el mismo hilo que
   serve_forever — hazlo desde el handler de señal con threading si hace
   falta; pruébalo arrancando y mandando SIGTERM.

C) sgf_path: en los puntos donde el servidor construye rutas de archivo a
   partir de sgf_path de la DB o de parámetros (busca os.path.join con datos),
   normaliza y valida que la ruta resultante queda DENTRO del directorio base
   esperado (os.path.realpath + startswith del base). Si no hay ningún punto
   donde sgf_path toque el filesystem del servidor, documéntalo y no inventes
   validación.

D) Parámetros de query no numéricos: los int(...) sobre query params (p. ej.
   set_id, since_attempt_id) que hoy explotan en 500 → responder 400 genérico.
   Localiza todos con grep de "int(" sobre los handlers GET.

VALIDACIÓN: run_all.sh íntegro + añade a test_server.py: (1) check de que
PRAGMA user_version == 1 tras arrancar sobre DB legacy, (2) check de 400 con
?since_attempt_id=abc, y para B una prueba manual documentada (arrancar,
kill -TERM, verificar salida limpia en el log).

FUERA DE ALCANCE: endpoints muertos (ni validarlos a fondo ni quitarlos),
HTTP keep-alive, rate limiting.
```

## TAREA 12 — R12/P3: `struggling` sin N+1 (window functions)

```
TAREA: eliminar el N+1 masivo de localGetStruggling (P3 de la auditoría): hoy
hace una query POR PROBLEMA del scope (64k prepares en un source grande).

CAMBIO REQUERIDO: reescribir localGetStruggling como UNA sola query con window
function, conservando EXACTAMENTE la semántica actual. Patrón orientativo (la
auditoría sugiere):
  WITH ranked AS (
    SELECT source, problem_id, result,
           ROW_NUMBER() OVER (PARTITION BY source, problem_id ORDER BY created_at DESC, id DESC) rn
    FROM attempts WHERE <mismo scope que hoy>
  )
  SELECT ... FROM ranked WHERE rn <= <n> GROUP BY source, problem_id
  HAVING SUM(result='wrong') > 0 ...
PERO: primero LEE la implementación actual y extrae su semántica exacta (qué
n usa, qué ordena, qué campos devuelve, cómo desempata, qué filtros de scope
aplica) — tu query debe replicarla, no la de este ejemplo.

MÉTODO OBLIGATORIO (igual que la Tarea 8A): antes de sustituir, script de
comparación (Node + sql.js) que pueble una DB sintética con casos límite
(problemas con solo aciertos, solo fallos, mezclas, empates de created_at en
el mismo segundo, menos de n intentos) y verifique que implementación vieja y
nueva devuelven resultados idénticos. Inclúyelo como compare_struggling.js.
sql.js soporta window functions (SQLite ≥3.25) — verifícalo al empezar con
una query trivial y, si no las soporta, DETENTE e informa.

El equivalente del servidor (handle_get_struggling): aplica el mismo cambio
solo si es el mismo patrón mecánico; no lo elimines.

VALIDACIÓN: run_all.sh íntegro + compare_struggling.js en verde (adjunta su
salida en la nota).

FUERA DE ALCANCE: la UI de struggling, otros stats (Tarea 13), añadir índices.
```

## TAREA 13 — P4/P5: stats de runs y maturity sin N+1

```
TAREA: eliminar los N+1 de estadísticas (P4 y P5 de la auditoría).

CONTEXTO: localGetLastRunStatsAll hace una query de agregación POR RUN;
localGetAllMaturity ejecuta un CTE pesado UNA VEZ POR COLECCIÓN;
refreshCollectionStats re-llama a localGetLastRunStats por colección expandida
en cada cambio de tab en lugar de reutilizar lo ya cargado.

CAMBIO REQUERIDO (tres piezas, en orden, validando cada una antes de seguir):
1. localGetLastRunStatsAll → una sola query: JOIN del conjunto de "últimos
   runs" (reutiliza el patrón estándar de la Tarea 8A si ya está hecha; si no,
   subconsulta WHERE id IN (SELECT MAX(id)... GROUP BY ...)) con la agregación
   GROUP BY run_id.
2. localGetAllMaturity → mover el CTE a UNA ejecución agrupada por set_id (o
   la dimensión que use la versión actual), devolviendo el mismo shape.
3. refreshCollectionStats → reutilizar el resultado ya cargado de
   lastRunStatsAll (busca dónde se cachea o cárgalo una vez) en lugar de
   re-consultar por colección.
MÉTODO OBLIGATORIO para 1 y 2: script de comparación con DB sintética
(compare_stats.js) verificando salida idéntica vieja vs nueva, incluyendo
colecciones sin runs y runs sin attempts.

VALIDACIÓN: run_all.sh íntegro + compare_stats.js en verde.

FUERA DE ALCANCE: la UI del modal de stats, P6/P7/P9 (Tarea 14), índices
nuevos, el servidor.
```

## TAREA 14 — Micro-rendimiento UI: P6 + P7 + P9

```
TAREA: tres micro-mejoras de rendimiento del cliente (P6, P7, P9 de la
auditoría). Independientes; hazlas en este orden y valida tras cada una.

P6 — updateSessionUI/updateRunProgress recorren runItems con varios filter()
en cada jugada: sustituye por contadores incrementales O por un único bucle
que calcule los tres valores de una pasada (elige lo que menos código toque;
si eliges contadores, identifica TODOS los puntos que mutan runItems para
mantenerlos coherentes, y documéntalos).

P7 — @import de Google Fonts dentro del <style> bloquea el primer render:
sustitúyelo por <link rel="preconnect" href="https://fonts.googleapis.com">
+ <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin> +
<link rel="stylesheet" href="...misma URL de la fuente..."> en el <head>,
manteniendo la MISMA fuente y pesos.

P9 — imgCache de piedras reasigna img.onload = () => board.redraw() por cada
piedra pendiente → múltiples redraws completos al cargar un set: unifica en
un redraw con debounce (~50 ms) compartido por todas las cargas de imagen.

VALIDACIÓN: run_all.sh íntegro (nada de esto toca sync). En la nota, para P6:
lista de los puntos de mutación de runItems auditados; para P7: confirmación
de que la fuente renderizada es la misma; para P9: descripción del flujo de
carga antes/después.

FUERA DE ALCANCE: P8 (servir sql-wasm localmente — requiere decisión de
despliegue del propietario), cualquier cambio visual, el service worker.
```

---

## SEGUNDA OLEADA (prompts pendientes de redactar cuando aterrice la primera)

- **Snapshot gzip cacheado (5.2)** — ⚠ requiere diseño previo: el snapshot
  incluye `sm2_state` (datos calientes); cachear el gzip por `static_version`
  serviría SM-2 obsoleto. Hay que separar la parte estática cacheable de la
  caliente manteniendo compatibilidad de respuesta. Lo especificará el
  arquitecto.
- **mostrar/games incrementales + ETag (5.3)** — toca protocolo cliente+servidor.
- **Paginación del pull y del snapshot (§11)** — toca protocolo; mejor tras 5.3.
- **R10 resto** — retirar endpoints muertos y la ruta `{ids}` de
  `/db/runs/delete`: SOLO cuando toda la flota de clientes esté migrada
  (decisión del propietario).
- **`catch (e) {}` vacíos del cliente** — pasar a `console.warn` con contexto;
  mecánica pero transversal, mejor tras T1–T8 para no generar conflictos.

## EN ESPERA DE DECISIÓN DEL PROPIETARIO (no lanzar)

- **Propagación de cierres de runs servidor→cliente** (`runs.updated_at` +
  pull incremental): diseño ya esbozado por el arquitecto; Victor la aparcó
  ("no sincronizo con runs a medio terminar").
- **P8** — servir sql-wasm desde el propio repo (afecta a despliegue/PWA).
- **PK de `run_items` con `source`** y **CHECKs en tablas existentes** —
  requieren reconstruir tablas: riesgo alto, solo con supervisión.

## EXCLUIDAS DE ESTA FASE (acordado)

R6 (repo.js), R7 (máquina de estados), R8 (modularización), R9 (unificación de
tipos con migración), R3 fase B (DB fría/caliente).
