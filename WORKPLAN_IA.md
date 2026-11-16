# WORKPLAN_IA — Jugar contra KataGo en TsumeVault

Estado: **Plan aprobado (13-nov-2026). IA0 ✔ hecha en el VPS. IA1 ✔ entregada. IA2 ✔ entregada (test_server.py 244 PASS; test_ai_sync.js 21 PASS). IA3 ✔ e IA4 ✔ entregadas (test_ai.js 48 PASS; prueba de humo de la ventana de estadísticas en Chrome headless). Pendiente: checklists manuales M-IA3/M-IA4 y despliegue IA5.**
Ficheros base: `tsumevault_server.py` y `tsumevault.html` adjuntados el 13-nov-2026 (schema servidor v5).

---

## 0. Resumen de requisitos (cerrados en el análisis)

- Rival: KataGo en el VPS (ARM, 2 núcleos, 3,7 GB + 2 GB swap), solo con conexión.
  - Niveles 20k–9d: modelo humano `b18c384nbt-humanv0` + `g170e-b15c192` como modelo principal (config `gtp_human5k_example.cfg`: la jugada se sortea de la política humana).
  - Nivel "Máximo": `g170e-b15c192` con la config normal y ~50 visitas.
- Partida: 19×19; handicap 0–9 llevado por Victor o por la IA (handicap 1 = negras sin piedras extra, komi 0,5); reglas japonesas por defecto o chinas; sin deshacer; doble toque según `tapConfirm`.
- Final por pases: recuento y piedras muertas automáticos (KataGo). Abandono de cualquiera: score = estimación de KataGo.
- Partida en curso: retomable solo en el dispositivo donde empezó (local).
- Partidas terminadas: tabla sincronizada con SGF y borrado lógico (LWW, patrón Focus/tags).
- Pestaña nueva con la partida y las estadísticas: histórico (+ SGF por fila), rejilla nivel × handicap con medias, nivel objetivo manual, handicaps pendientes, escalera de igualadas con reglas de cierre configurables (local).
- Fuera: nivel en kyu estimado, otros tamaños, guiado, deshacer, reloj, sync de la partida en curso.

---

## IA0 — Verificaciones en el VPS (antes de escribir código)

**Resultados (13-nov-2026):**
1. `kata-set-param humanSLProfile` funciona en caliente → un solo proceso para todos los niveles humanos.
2. `kata-set-rules chinese/japanese` funciona; cambia el komi → el komi se envía después de las reglas.
3. `set_free_handicap D4 Q16` funciona.
4. `final_score` ~15–20 s; `kata-raw-nn 0` instantáneo (whiteLead −11,4 vs B+12,5).
5. `maxVisits 2` mantiene la variedad a 15k (D17, K10, D4); tiempo por jugada aceptable.
6. "Máximo" en el mismo proceso (`humanSLChosenMoveProp 0`, `maxVisits 50`): ~5 s por jugada.
7. Memoria con KataGo cargado: 1,3 GB usados, 2,4 GB disponibles (KataGo ≈ 0,75 GB). Holgado.

Pruebas originales:

1. **¿Se puede cambiar el nivel sin reiniciar KataGo?** `kata-set-param humanSLProfile rank_10k` y luego `genmove`.
   - Si funciona: un proceso para todos los niveles.
   - Si no: el servidor reinicia el proceso humano al cambiar de nivel (unos segundos la primera jugada tras el cambio). Ambas variantes caben en el diseño de IA1.
2. **Reglas por comando:** `kata-set-rules japanese` / `kata-set-rules chinese`.
3. **Handicap:** `set_free_handicap D4 Q16` tras `clear_board`.
4. **Recuento:** `final_score` y `final_status_list dead` en una posición acabada y en una a mitad de partida (para la estimación al abandonar), y cuánto tardan.
5. **Velocidad con menos visitas:** repetir la prueba de 3×`genmove` con `maxVisits=2`; si la variedad y el nivel se mantienen, se usa 2–3 en vez de 8.

Ficheros a crear en `/opt/katago-models/` (copia, no se toca el original del repo de KataGo):
- `tv_human.cfg` = `gtp_human5k_example.cfg` con `logDir = /opt/katago-models/logs` (el original usa una ruta relativa al directorio de arranque), `maxVisits = 2`, `numSearchThreads = 2`, `humanSLProfile = rank_15k`. No hace falta `tv_max.cfg`: "Máximo" se fija por parámetros en el mismo proceso.

### Diseño abierto a otros motores (petición de Victor, 13-nov)

Para poder añadir más adelante otro motor GTP (p. ej. GNU Go) sin rehacer nada:
- La clase `GtpEngine` es genérica (lanzar, enviar comando, leer respuesta, cerrar por inactividad). Lo específico de cada motor (cómo fijar el nivel, reglas y recuento) va en un "driver" pequeño: `KataGoDriver` usa `kata-set-param`, `kata-set-rules`, `kata-raw-nn`; un futuro `GnuGoDriver` usaría `level` y comandos GTP estándar.
- Los niveles van con espacio de nombres: `katago:rank_15k`, `katago:max` (futuro: `gnugo:10`). El servidor publica la lista en `GET /ai/status`, y el cliente pinta el selector desde ahí.
- El recuento siempre lo hace KataGo, sea cual sea el rival.
- `ai_games.model` ya separa las estadísticas por motor.

---

## IA1 — Servidor: motor KataGo y endpoints `/ai/*`

**Entregado (13-nov-2026):** `ai_engines.py` (nuevo, junto al servidor), `tsumevault_server.py` (rutas `/ai/*` fuera de `DB_LOCK`, cierre del motor al apagar), `fake_gtp.py` (motor falso para tests, válido también en Windows) y `test_server.py` (+36 checks: 503 sin motor, validaciones, orden de comandos GTP, Máximo sin reiniciar, recuento final/estimado, muerte y relanzado del motor, 403/401, sync no bloqueado — verificado con mutante —, cierre por inactividad, servidor sin `ai_engines.py`).
Variables reales: `KATAGO_BIN`, `KATAGO_CFG`, `KATAGO_MODEL`, `KATAGO_HUMAN_MODEL`, `KATAGO_IDLE_S`, `KATAGO_LOG` (sustituyen a `KATAGO_CFG_HUMAN`/`KATAGO_CFG_MAX` de abajo: un solo proceso y un solo cfg).
`/ai/move` responde también `model` (`humanv0` | `b15c192`), que el cliente guardará en `ai_games.model`. Niveles con prefijo de motor: `katago:rank_20k` … `katago:rank_9d`, `katago:max`.

### Gestor del motor (diseño original; implementado en `ai_engines.py`)

- Configuración por variables de entorno (como `TSUMEVAULT_TOKEN`): `KATAGO_BIN`, `KATAGO_MODEL`, `KATAGO_HUMAN_MODEL`, `KATAGO_CFG_HUMAN`, `KATAGO_CFG_MAX`, `KATAGO_IDLE_S` (900 por defecto). Si `KATAGO_BIN` no está definido o no existe, los endpoints `/ai/*` responden **503** y el resto del servidor funciona igual (local/Windows y tests no se ven afectados).
- Clase `GtpEngine`: lanza `katago gtp` con `subprocess.Popen` en el **primer uso**; `stdin`/`stdout` en pipe; **`stderr` a un fichero de log** (no a pipe: si nadie lo lee, el buffer se llena y KataGo se bloquea). Un hilo lector mete las líneas de stdout en una `queue.Queue` para poder leer con timeout. Respuesta GTP = líneas hasta la línea en blanco; `=` éxito, `?` error.
- **Un solo proceso** (IA0: todo se cambia en caliente con `kata-set-param`), lanzado con `tv_human.cfg`, `-model g170e-b15c192…` y `-human-model b18c384nbt-humanv0…`. Antes de cada `genmove` el servidor fija **todos** los parámetros del nivel pedido (nunca depende de lo que dejó la petición anterior):
  - nivel humano: `humanSLProfile rank_Xk`, `humanSLChosenMoveProp 1`, `maxVisits 2`, `chosenMoveTemperatureEarly 0.85`, `chosenMoveTemperature 0.70` (valores de `gtp_human5k_example.cfg`).
  - "Máximo": `humanSLChosenMoveProp 0`, `maxVisits 50`, `chosenMoveTemperatureEarly 0.5`, `chosenMoveTemperature 0.10` (valores de `gtp_example.cfg`; ~5 s por jugada en IA0).
  Un único lock para el motor (las peticiones se atienden de una en una).
- Hilo vigilante: cierra el proceso tras `KATAGO_IDLE_S` sin uso. Si el proceso muere, la siguiente petición lo relanza. Al apagar el servidor (SIGTERM) se cierran.
- Timeouts: arranque 90 s, `genmove` 60 s, `final_score` 30 s. Si vence, se mata el proceso y se responde 504.

### Punto crítico: no bloquear la sincronización

`_dispatch` ejecuta todos los handlers bajo `DB_LOCK`. Una jugada de KataGo tarda segundos, así que las rutas `/ai/*` van en un diccionario aparte (`AI_ROUTES`) que se despacha **sin `DB_LOCK`** (mismo `_gate`, misma validación de body, mismo manejo de errores). Así un sync no espera a que la IA piense.

### Reconstrucción de la posición en cada petición

`boardsize 19` → `clear_board` → `kata-set-rules R` → `komi K` (**después** de las reglas: IA0 vio que `kata-set-rules chinese` cambia el komi a 6,5) → (`set_free_handicap …` si hay) → `play` de cada jugada → `kata-set-param humanSLProfile …` (IA0: funciona en caliente, un solo proceso). Coste: milisegundos.

Nota IA0: con reglas chinas y handicap, KataGo aplica `whiteHandicapBonus: N` (blancas reciben N puntos, la compensación estándar del recuento chino). Es lo correcto y queda reflejado en el score.

### Endpoints

| Ruta | Body | Respuesta |
|---|---|---|
| `POST /ai/move` | `{level, rules, komi, handicap_stones:[vértices GTP], moves:[["B","Q16"],["W","pass"],…], to_play}` | `{move: "D4" \| "pass" \| "resign", ms}` |
| `POST /ai/score` | igual sin `level`/`to_play` | `{result: "W+3.5", score_white: 3.5, dead: [vértices]}` |
| `GET /ai/status` | — | `{available, engines:{human, max: running/stopped}}` |

- `level`: `rank_20k` … `rank_9d` o `max`. El recuento siempre con el modelo principal (`b15c192`).
- **Recuento (IA0):** fin por pases → `final_score` + `final_status_list dead` (preciso, pero ~15–20 s en el VPS: la app muestra "contando…"). Abandono → `kata-raw-nn 0`, una sola evaluación, instantánea; `whiteLead` (−11,4 frente a B+12,5 de `final_score` en la prueba) es estimación suficiente. `/ai/score` lleva un campo `mode: "final" | "estimate"`.
- Validación estricta: niveles de una lista cerrada, `rules` ∈ {japanese, chinese}, komi numérico acotado, vértices con regex GTP (A–T sin I, 1–19), ≤ 9 piedras de handicap, ≤ 1000 jugadas. Nunca se interpola texto del cliente en GTP sin validar.

### Tests

`test_server.py`: un **motor falso** (script Python de pocas líneas que habla GTP y responde jugadas fijas) apuntado con `KATAGO_BIN`, para probar sin KataGo: 503 sin motor, validaciones 400, `/ai/move` y `/ai/score` felices, relanzado tras muerte del proceso, y que un `/sync/*` no espera a una `/ai/move` lenta.

---

## IA2 — Tabla `ai_games` y su sincronización

### Esquema (servidor: migración **v6** encadenada tras `_migrate_v5_focus`; cliente: `createSchema` + `migrateSyncColumns`)

```
ai_games (
  uuid        TEXT PRIMARY KEY,
  played_at   TEXT NOT NULL,      -- fin de la partida, ISO UTC
  my_color    TEXT NOT NULL,      -- 'B' | 'W'
  ai_level    TEXT NOT NULL,      -- 'rank_15k' … 'rank_9d' | 'max'
  model       TEXT NOT NULL,      -- 'humanv0' | 'b15c192' (separar estadísticas por IA en el futuro)
  handicap    INTEGER NOT NULL,   -- con signo desde Victor: +N recibe, -N da, 0 igualada
  rules       TEXT NOT NULL,      -- 'japanese' | 'chinese'
  komi        REAL NOT NULL,
  end_type    TEXT NOT NULL,      -- 'passes' | 'resign_me' | 'resign_ai'
  score       REAL NOT NULL,      -- con signo desde Victor: + gana, - pierde
  sgf         TEXT NOT NULL,
  deleted     INTEGER NOT NULL DEFAULT 0,
  updated_at  TEXT NOT NULL
  -- cliente: + synced INTEGER NOT NULL DEFAULT 0
)
```

**Entregado (13-nov-2026):**
- Servidor: migración v6 (`ai_games` + columna solo-servidor `server_at`), `GET /sync/ai_games/pull?since=`, `POST /sync/ai_games/push`, checks de auditoría `IA2a` (dominio, ERROR) e `IA2b` (abandono con signo contrario, WARNING). Los tests de `user_version` pasan de 5 a 6.
- Cliente: tabla en `createSchema` y `migrateSyncColumns`; bloque de sync **dentro de `doSync`** tras el de Focus (perímetro de `extract_bundle.py`: no puede llamar a funciones fuera del bundle). Diff del bundle limitado a esas tres zonas. Las funciones locales de alta/borrado de partidas llegan con IA3, donde se usan.
- **Cambio sobre el plan: el cursor del pull es `server_at` (hora del servidor), no `updated_at`.** Una partida terminada offline llega con un `updated_at` anterior al cursor de los demás dispositivos y, con cursor por `updated_at`, se la saltarían (verificado con mutante en `test_ai_sync.js` S4). Así el pull ya no es completo en cada sync.
- `test_ai_sync.js` (nuevo): 21 checks con el `doSync` real contra el servidor real; arranca su propio servidor (válido en Windows: `python extract_bundle.py` y `node test_ai_sync.js`).
- No ejecutados en el contenedor: `harness.js` y `harness_compat.js` (pendientes en la máquina de Victor).

### Sync (diseño original)

- `GET /sync/ai_games/pull` y `POST /sync/ai_games/push` con LWW por `updated_at`; validación como `_focus_validate`. Pull completo en cada sync (pocas filas; el SGF de una partida son unos KB).
- Cliente: bloque nuevo en `doSync` tras el de Focus; servidor antiguo (404) → no-op.
- Borrado lógico: `deleted=1` + `updated_at` nuevo; el histórico y las estadísticas filtran `deleted=0`.
- Auditoría `/db/audit`: un check nuevo de dominio (`my_color`, `end_type`, `deleted`, `handicap` en −9..9).

---

## IA3 — Pantalla de partida (pestaña nueva "Play")

**Entregado (13-nov-2026):** pestaña `Play`, barra `#ai-controls` (Pasar, Abandonar, Reintentar) y bloque JS `IA3` en `tsumevault.html`, antes de `switchTab`. Fuera del perímetro de `extract_bundle.py`: el bundle del harness no cambia respecto a IA2.
- Funciones puras entre los marcadores `// ── IA3: funciones puras` y `// ── fin IA3 funciones puras ──`; `extract_ai.py` las extrae y `test_ai.js` las prueba (29 PASS): coordenadas GTP↔WGo↔SGF, piedras de handicap, configuración de partida, turnos, dos pases, score con signo y regla del abandono, SGF.
- **Espera mínima de la IA configurable** (decisión de Victor): campo en el formulario, `localStorage` `ai_min_delay_ms`, 1000 ms por defecto, 0–10000.
- Una partida a la vez: con una en curso el panel solo ofrece "Continuar"; al entrar en la pestaña se retoma sola si le tocaba a la IA o faltaba el recuento.
- Piedras de handicap: 2 = D4 Q16; 3 añade Q4; 4 D16; 5 K10; 6 D10 Q10; 7 K10; 8 K4 K16; 9 K10.
- Fin: dos pases → `final` (marca piedras muertas con ✕); abandono de cualquiera → `estimate`; se forma el SGF y se inserta en `ai_games` (sync con IA2). Si falla la red: "Reintentar", sin perder la partida.

**Checklist manual M-IA3** (en el PC, sin KataGo: servidor local con el motor falso; en PowerShell, desde la carpeta del servidor, `$env:KATAGO_BIN="fake_gtp.py"; $env:KATAGO_CFG="fake_gtp.py"; $env:KATAGO_MODEL="fake_gtp.py"; $env:KATAGO_HUMAN_MODEL="fake_gtp.py"; python tsumevault_server.py`, y en ⚙ el servidor `http://localhost:3002`):
- M1 La pestaña Play cabe en la barra de pestañas del móvil (7 pestañas).
- M2 Sin servidor: "Motor no disponible" y Empezar deshabilitado.
- M3 Igualada con negras: juegas, la IA responde tras la espera mínima; con blancas, la IA abre sola.
- M4 Recibir 3: aparecen D4 Q16 Q4 y la IA (blancas) juega primero. Dar 2: tú con blancas, la IA tiene las piedras.
- M5 Jugada ilegal (ocupada, ko, suicidio) no hace nada. Con "Tap para confirmar": primer toque = fantasma, segundo = jugada.
- M6 Pasar dos veces seguidas (tú y la IA) → "Contando…" → resultado y ✕ en las muertas. La partida aparece en ai_games y se sincroniza.
- M7 Abandonar → confirmación → derrota con score negativo.
- M8 Cerrar la app mientras la IA piensa y volver a entrar en Play: retoma sola.
- M9 Apagar el servidor a mitad: mensaje y "Reintentar"; al volver el servidor, Reintentar continúa.
- M10 Girar el móvil durante la partida: el tablero se repinta sin perder nada.
- M11 Volver a Collections/Free tras jugar: los problemas funcionan como siempre.

### Diseño original

- Pestaña `Play` en `#left`, con dos vistas internas: **Partida** y **Estadísticas** (IA4). Modo propio (`aiActive`) en `switchTab`, igual que `gmActive`/`jsActive`; barra de controles propia (`#ai-controls`: Pasar, Abandonar).
- Formulario de nueva partida: nivel (20k…9d, Máximo), mi color (en igualadas), handicap 0–9 y quién lo lleva, reglas (japonesas por defecto). Si hay partida en curso, botón "Continuar".
- Reglas en el cliente con un `WGo.Game` de reglas reales (captura, ko), como el modo Explorar (T31): una jugada ilegal no se envía.
- Flujo de turno: jugada de Victor → se guarda en local → `POST /ai/move` → se pinta la respuesta. Indicador "pensando…" y bloqueo de clics mientras tanto. Fallo de red → mensaje y botón "Reintentar"; la partida no se pierde.
- Persistencia de la partida en curso: `localStorage` (`ai_current_game`: configuración + jugadas + inicio), guardada tras cada jugada.
- Final:
  - Dos pases seguidos → `POST /ai/score` → se marcan las piedras muertas y se muestra el resultado.
  - Abandono de Victor (con confirmación) o `resign` de la IA → `POST /ai/score` como estimación.
  - Si el recuento falla por red, la partida queda "pendiente de recuento" y se reintenta.
- Al cerrar: se genera el SGF en el cliente (SZ, KM, HA, RU, AB, PB/PW con el nivel, RE, jugadas), se inserta la fila en `ai_games` y se sincroniza.
- Conversión de coordenadas GTP ↔ WGo (columnas sin I; fila GTP = 19 − y) en funciones puras con test.

---

## IA4 — Estadísticas

**Entregado (13-nov-2026):** botón 📈 Estadísticas en la pestaña Play que abre la ventana `#ai-stats-overlay` (la rejilla de 29×19 no cabe en el panel lateral). Contenido: configuración local (nivel objetivo + las tres reglas de cierre, `localStorage` `ai_stats_cfg`, botón "Reglas por defecto"), resumen "Para superar N" (igualadas cerradas o no + handicaps pendientes), rejilla con medias (verde > 0, rojo ≤ 0, "–" verde = superada por una casilla más difícil, borde dorado = handicap que toca), escalera de igualadas e histórico (⬇ SGF, 🗑 borrado lógico con confirmación).
Funciones puras nuevas en el mismo bloque que IA3 (`aiRankIdx`, `aiRankLevel`, `aiGrid`, `aiCellImplied`, `aiHcRequired`, `aiHandicapStatus`, `AI_CLOSE_RULES`, `aiLadder`), probadas en `test_ai.js` (incluye el caso del Excel: objetivo 12k, 9k pendiente recibiendo 3, 15k superado dando 6). Solo cuentan niveles `katago:rank_*`; "Máximo" se juega y queda en el histórico, pero fuera de rejilla y escalera.

**Checklist manual M-IA4:**
- N1 Tras unas partidas de prueba, el histórico, la rejilla y la escalera coinciden con lo jugado.
- N2 Cambiar el nivel objetivo mueve el borde dorado y el resumen.
- N3 Cambiar una regla de cierre se refleja al instante y persiste al reabrir; "Reglas por defecto" vuelve a 3/100/100, 5/80/15, 12/75/0,5.
- N4 ⬇ SGF descarga un fichero que KaTrain abre con jugadas, handicap y resultado.
- N5 🗑 pide confirmación, la partida desaparece de todo y el borrado llega al otro dispositivo tras sincronizar.
- N6 En el móvil la ventana se desplaza en horizontal sin romper la página.

### Diseño original

Funciones **puras** (sin DOM), extraídas y probadas en Node con un `extract_ai.py` + `test_ai.js` nuevos (patrón `extract_hint.py`; no se toca el perímetro de `extract_bundle.py`):

- `aiRankIdx(level)`: 20k=0 … 1k=19, 1d=20 … 9d=28. "Máximo" queda fuera de rejilla y escalera.
- **Rejilla**: filas = nivel del rival, columnas = handicap +9…−9; celda = media de `score`; verde si media > 0.
- **Handicap requerido** para superar el nivel objetivo N contra el rival L: `h_req = aiRankIdx(L) − aiRankIdx(N)` (positivo = recibo). La fila L está **superada** si alguna celda de esa fila con `h ≤ h_req` está en verde. Solo cuentan filas con |h_req| ≤ 9 y L ≠ N. Las casillas "dadas por superadas" (más fáciles que una ganada) se pintan como los guiones verdes del Excel.
- **Pendientes de handicap**: filas no superadas, con el handicap que falta (columna AS del Excel).
- **Escalera de igualadas** (handicap 0): por nivel, partidas, victorias, winrate, score medio y "Cerrado" según los puntos de control configurables (ver pregunta 2 resuelta al final: 3 / 100 % / >100; 5 / ≥80 % / >15; desde 12 / ≥75 % / >0,5; un nivel cerrado no se reabre).
- **Histórico**: fecha, mi color, nivel, handicap, score, ⬇ SGF y 🗑 (borrado lógico con confirmación).
- Configuración local (`localStorage`, solo móvil): nivel objetivo y las tres reglas de cierre.

---

## IA5 — Despliegue

1. VPS: subir `ai_engines.py` y el nuevo `tsumevault_server.py` a `/opt/tsumevault/`; `tv_human.cfg` ya existe (IA0); añadir a la unidad systemd:
   `KATAGO_BIN=/opt/KataGo/cpp/katago`, `KATAGO_CFG=/opt/katago-models/tv_human.cfg`, `KATAGO_MODEL=/opt/katago-models/g170e-b15c192-s1672170752-d466197061.txt.gz`, `KATAGO_HUMAN_MODEL=/opt/katago-models/b18c384nbt-humanv0.bin.gz`, `KATAGO_LOG=/opt/katago-models/logs/stderr.log`. Reiniciar el servicio (la migración v6 corre sola) y comprobar `GET /ai/status`.
2. Servidor primero (migración v6 + `/ai/*` + sync), cliente después (regla del proyecto).
3. `CACHE_VERSION`/`SW_VERSION` con el `.bat` de Victor. No hay assets estáticos nuevos.

---

## Orden y validación

IA0 → IA1 → IA2 → IA3 → IA4 → IA5. Cada tarea con la secuencia obligatoria: CRLF byte a byte, `node --check` / `ast.parse`, `run_all.sh` con recuentos estables (+ las baterías nuevas), diff de `harness_bundle.js` contra la base. Ediciones con `assert content.count(old) == 1`.

## Riesgos

- **Bloqueo del sync por el motor** → resuelto con `AI_ROUTES` fuera de `DB_LOCK` (IA1).
- **Memoria**: resuelto en IA0 — un solo proceso, ~0,75 GB, 2,4 GB libres.
- **Calibración de niveles**: los rangos del modelo humano son orientativos; se ajusta jugando, no en código.

## Preguntas abiertas (se resuelven de una en una antes de IA3/IA4)

1. ~~Al abandonar~~ **Resuelta**: quien abandona siempre pierde. Se usa la estimación de KataGo; si su signo contradice el abandono, se registra la derrota mínima (−0,5 si abandona Victor, +0,5 si abandona la IA) para no distorsionar las medias.
2. ~~Reglas de cierre~~ **Resuelta y confirmada por Victor**: son puntos de control sobre TODAS las partidas igualadas de ese nivel, en orden cronológico:
   - al llegar a 3 partidas: cierra si 100 % y media > 100;
   - al llegar a 5 partidas: cierra si ≥ 80 % y media > 15;
   - de 12 partidas en adelante (12, 13, 14…): cierra en cuanto el acumulado tenga ≥ 75 % y media > 0,5;
   - entre 6 y 11 partidas no se puede cerrar;
   - una vez cerrado, el nivel queda cerrado aunque partidas posteriores bajen las cifras (por eso el nivel objetivo lo fija Victor a mano).


## Calibración y perfiles de handicap (14-nov-2026)

- Torneos gomill (ringmaster) del KataGo del VPS (`tv_human.cfg`) contra GNU Go nivel 10, igualadas, reglas chinas: 15k 0-2, 10k 0-4, 8k 0-3 (por poco), 6k 7-3. Equilibrio hacia el 7k del modelo; con GNU Go ≈ 8k (±2), las etiquetas del modelo humano son fiables (como mucho un rango por debajo). Decisión: no tocar temperatura ni configuración de fuerza.
- Quitada la espera artificial de KataGo (`delayMoveScale`/`delayMoveMax = 0.0` en `tv_human.cfg`): era la causa de los 5–6 s por jugada.
- Handicap 9 contra GNU Go: `rank_15k` 8-2, `rank_15k_6k` 10-0. Decisión de Victor: usar perfiles emparejados en partidas con handicap, sin marcar las partidas aparte (aún no había partidas).
  - Cliente: `/ai/move` envía `handicap` (con signo, desde el jugador). Servidor: `handicap_profile()` en `ai_engines.py` → `rank_{negras}_{blancas}` (doy 9 a un 20k → `rank_20k_11k`; recibo 3 de un 12k → `rank_15k_12k`); igualadas o fuera de la escala 20k..9d → perfil normal; sin campo (cliente antiguo) → perfil normal.
  - `test_server.py` 255 PASS.
- Añadidos también: botón ← Atrás (deshace tu última jugada y la respuesta) y 📊 Estimar (número + mapa de propiedad de `kata-raw-nn`).


## AN — Análisis de partidas en el visor de Games (15-nov-2026)

Alcance acordado con Victor: 19×19, partidas normales o con handicap (no posiciones con piedras blancas iniciales ni otros tamaños); gráfica de la ventaja; análisis profundo a petición (~6 s); errores marcados en la gráfica y clic para saltar; coste de la jugada hecha; secuencia de la mejor jugada. Para más adelante: probar jugadas alternativas propias.

- **AN1 (servidor, `ai_engines.py` + rutas en `tsumevault_server.py`):**
  - `POST /ai/graph`: ventaja de blancas con `kata-raw-nn` antes de cada jugada y tras la última (≤ 600 jugadas, una sola petición).
  - `POST /ai/analyze`: `kata-search_analyze` con el modelo principal (`humanSLChosenMoveProp 0`, 100 visitas por defecto, 10–400), hasta 5 candidatas con `scoreLead`, `winrate` y secuencia (≤ 12). Con `played`: si está entre las candidatas con ≥ 30 visitas usa su valor; si no, la juega y hace una búsqueda corta (30 visitas) del rival. Puntuaciones desde quien juega.
  - Formato de `kata-search_analyze` verificado en el VPS (líneas `info move …`, final `play X`); se usa la última línea `info`.
  - `test_server.py` 269 PASS (motor falso ampliado: ventaja variable por posición y `kata-search_analyze`).
- **AN2 (cliente, visor de Games):** botones 📈 Gráfica, 🔍 Analizar y 🔢 Secuencia en `#gm-controls`; gráfica SVG en `#gm-graph` (dentro de los controles: se oculta con ellos). Errores ≥ 5 puntos (naranja) y ≥ 10 (rojo); tocar la gráfica salta a esa jugada de la línea principal. En partidas contra la IA la gráfica va desde tu punto de vista (`persp` = `my_color`); en las de colecciones, desde negras. Análisis: ★ mejor jugada y 2–5 numeradas; texto con puntos y "Se jugó X: −N respecto a la mejor". Funciones puras `anPosition` y `anMistakes` en `test_ai.js` (57 PASS). Prueba de humo de la gráfica en Chrome headless.


## AN3 — Gráfica precisa por tramos y caché de análisis en el servidor (15-nov-2026)

Motivo: la gráfica con la evaluación instantánea (`kata-raw-nn`) tenía picos de ida y vuelta en posiciones tácticas (capturas pendientes, atari) que se marcaban como errores falsos. Decisión de Victor: gráfica precisa aunque tarde más, y guardar los análisis para no recalcularlos (sin sincronizar).

- **Servidor:** migración **v7**: tabla `ai_analysis_cache(key, kind, params, result, created_at)`, solo servidor. Clase `AnalysisCache` en `tsumevault_server.py` (toma `DB_LOCK` solo al leer o escribir; cualquier error se ignora). `AiService(cache=…)`.
  - Clave genérica `cache_key(modelo, kind, posición, parámetros)` con `AN_CACHE_VERSION` (súbelo si cambia el cálculo). Tipos actuales: `pos_eval` (gráfica, 16 visitas) y `analyze` (🔍, incluye visitas, quién juega y la jugada hecha).
  - `POST /ai/graph` con `from`/`to` (máx. 40 posiciones por petición): búsqueda corta por posición (`kata-search_analyze`, 16 visitas, `rootInfo`), con caché por posición; partidas que comparten el principio reutilizan lo calculado. Sin `from`/`to` mantiene el modo antiguo instantáneo (compatibilidad con clientes viejos).
  - `test_server.py` 284 PASS (incluye que la caché sobrevive al reinicio y la migración v6 → v7; los checks de `user_version` pasan a 7).
- **Cliente:** la gráfica se pide en tramos de 20 y se dibuja según llega ("Calculando la gráfica… 60/250"); se detiene si se abre otra partida; si se oculta, termina igualmente. `anMistakes`/`anGraphCaption` toleran huecos. `test_ai.js` 71 PASS; prueba de carga progresiva en Chromium.
- Visor: modelo 1 (todo habla de la jugada que se ve), botones en dos filas solo con icono, filtro de errores por color, ficha de la partida en el panel lateral de Games, gráfica de 6 px por jugada con desplazamiento horizontal.

## Idea para el futuro (NO implementar todavía): análisis por niveles con el modelo humano

Propuesta de Victor (15-nov): para una posición, mostrar qué jugaría el modelo humano en distintos niveles (20k, 15k, 10k, 5k, 1d… y KataGo), junto con lo que pierde cada jugada respecto a la mejor. Objetivo: encontrar "la jugada sencilla que casi no pierde" y ver qué concepto aparece al subir de nivel. Matiz: el modelo humano predice lo que *jugaría* ese nivel (errores típicos incluidos), no lo mejor para ese nivel.
- Diseño ya preparado: la caché es genérica; bastaría un `kind` nuevo (p. ej. `human_move` con `params: {profile: 'rank_15k'}`) sin tocar la tabla.
- Técnicamente: `kata-raw-human-nn` por nivel (instantáneo) y el coste de cada jugada con la misma búsqueda de `/ai/analyze`.


## AN4 — Análisis automático en el servidor · ST1 — Estado del servidor en ⚙ (15-nov-2026)

Motivo: con el móvil, la pestaña se congela al apagar la pantalla y los tramos fallaban ("Failed to fetch"). Decisión de Victor: que el servidor calcule por su cuenta; automático para las partidas contra la IA, a petición para las de colecciones; y una sección sencilla en ⚙ para ver si algo va mal (el detalle, por ssh).

- **AN4 (servidor, `ai_engines.py`):** `GraphWorker`: cola en memoria y un hilo que calcula la gráfica posición a posición (de 2 en 2) guardando en la caché de AN3. Prioridad para lo interactivo: `_run(…, interactive=True)` cuenta las peticiones esperando y el trabajador cede (`_yield_to_interactive`) antes de cada turno. Interruptor `KATAGO_BACKGROUND=0` (por defecto activado). `sgf_to_position` lee los SGF de la app (19×19, handicap negro, sin variantes).
  - Automático: al recibir partidas por `/sync/ai_games/push` (después de guardar, sin poder afectar a la respuesta) y al arrancar el servidor (hilo propio; las ya analizadas salen de la caché).
  - `POST /ai/graph_job`: encola una partida a petición (delante de las automáticas). `POST /ai/graph` con `cached_only: true`: devuelve lo guardado (null donde falta) sin tocar el motor.
- **ST1:** `GET /server/status` (solo lectura, con token): versión de BD, tiempo en marcha, KataGo (disponible, cargado, tiempo medio de jugada), análisis automático (activado, cola, partida en curso y progreso, hechas hoy, último error), disco, memoria, carga, tamaño de la caché. En ⚙, sección "Estado del servidor" con semáforo (verde / ámbar con avisos / rojo sin conexión) y ↻.
- **Cliente:** 📈 consulta lo guardado, encarga el resto al servidor y sigue el progreso cada 2,5 s ("Analizando en el servidor… 120/251 · sigue aunque cierres la app"). Si el servidor no tiene análisis automático, calcula por tramos como en AN3.
- **Pruebas:** `test_server.py` 297 PASS (fase I nueva: trabajador, partida por sync, prioridad con jugada < 1,5 s, revisión al arrancar, interruptor, estado; test directo del mecanismo de prioridad, verificado con mutante). `test_ai.js` 75 PASS (`srvStatusSummary`). Flujo de la gráfica y panel de estado comprobados en Chromium con servidor simulado.
- **Despliegue:** sin migración nueva (sigue v7). Opcional en systemd: `Environment=KATAGO_BACKGROUND=0` para apagar el análisis automático.


## AN5 — Correcciones del visor y errores precalculados (15-nov-2026)

1. **Análisis que no aparecía:** si se cambiaba de jugada mientras se analizaba (en el móvil, por ejemplo, al desplazar la gráfica, que el navegador tomaba como toque), el resultado se descartaba y la barra se quedaba en "Analizando…". Ahora los resultados se guardan por jugada (`anState.resByNode`) y se muestran al volver; el mensaje se limpia al terminar; tocar 🔍 en una jugada ya analizada la muestra sin pedir nada; desplazar la gráfica (dedo movido > 8 px o scroll cambiado) ya no salta de jugada.
2. **Gráfica que se salía de la pantalla:** `#board-wrap` es un elemento flexible y crecía hasta el ancho de la gráfica. Arreglo acotado a la gráfica: la zona desplazable usa `width:0; min-width:100%`, así que no aporta ancho a los contenedores. Medido en la página real a 360 px: gráfica 360 px, contenido desplazable 1516 px, centrada en la jugada actual.
3. **Errores precalculados (servidor):** tras la gráfica, el trabajador analiza cada jugada que pierde ≥ 5 puntos (los dos colores, como mucho los 30 mayores) con los mismos parámetros que 🔍, de modo que al pulsarlo sale de la caché. En ⚙ se ve como "… · errores 4/12". `test_server.py` 299 PASS.
4. **Capturas:** no se suman aparte; `scoreLead` de KataGo ya es el resultado final esperado (territorio, capturas hechas y previstas, y komi según las reglas).


## RL — Reloj de entrenamiento (análisis cerrado 15-nov-2026)

Solo para el jugador (la IA no lleva tiempo). Objetivo: acostumbrarse a gestionar el tiempo, también con poco tiempo principal; el reloj no castiga el entrenamiento.

**Decisiones de Victor**
- Configuración en el panel de partida nueva: "sin reloj" o byoyomi con tiempo principal (0 permitido), nº de periodos y segundos por periodo. Solo los tres campos (sin configuraciones predefinidas); se recuerdan los últimos usados en el dispositivo (localStorage). El sistema se guarda con tipo para añadir el **byoyomi canadiense** más adelante.
- Reloj **manual**: la jugada no se envía a la IA hasta pulsar el reloj; pulsar sin jugada no hace nada; pasar + pulsar. Mi tiempo arranca cuando aparece la piedra de la IA (lo que tarda el servidor no cuenta). El botón es la barra bajo el tablero (y la barra espaciadora en el ordenador).
- Al agotar el último periodo, **solo aviso**: reloj en rojo contando en negativo y la partida marcada ⏰; no cambia el resultado ni las estadísticas.
- Pausa ⏸ manual, **pausa automática** al pasar la app a segundo plano, y el reloj **parado mientras la estimación está en pantalla** (tampoco cuenta como tiempo de pensamiento). **"← Atrás" no devuelve tiempo.**
- Avisos: voz del navegador (entrada en byoyomi, cuenta atrás, "quedan N", "último periodo"), sustituible por grabaciones propias en una carpeta; se silencian con el sonido general de ⚙; vibración siempre activa.
- Tiempo de pensamiento medido siempre (también sin reloj), guardado en el SGF; en el histórico: media por jugada, jugada de entrada en byoyomi y ⏰. La barra de tiempos en el analizador, más adelante.

**Fases:** RL1 lógica pura y SGF · RL2 flujo de Play (panel, barra-reloj, pulsación manual, pausas, deshacer) · RL3 avisos (voz, grabaciones, vibración) · RL4 histórico · más adelante: tiempos en el analizador y byoyomi canadiense.

### RL1 — Lógica del reloj (hecho)
- Funciones puras `tc*` en el bloque de funciones puras de `tsumevault.html` (se extraen con `extract_ai.py`):
  - `tcNormalize(cfg)` (límites: principal 0–10800 s, 1–30 periodos, 1–600 s), `tcStart(sys)`.
  - `tcAt(sys, st, e)`: reloj tras pensar `e` ms en el turno (fase `main`/`byo`/`over`). Un periodo solo se consume si se agota; `tcPress` devuelve el estado del turno siguiente (periodo lleno otra vez; pasado el último, `expired` y el exceso sigue acumulándose).
  - `tcEventTimes`/`tcEvents(sys, st, e0, e1]`: entrada en byoyomi (solo si había principal), cuenta atrás de cada periodo desde min(9, periodo − 1), periodo consumido con los que quedan, `timeout`.
  - `tcLabel` ("4:32", "3 × 0:06", "−0:12").
- SGF (`aiBuildSgf`): raíz `TM[principal]OT[5x30 byo-yomi]`; en mis jugadas `TT[s pensados]` (propiedad propia, también sin reloj) y, con reloj, `BL/WL` (restante; del periodo en byoyomi) y `OB/OW` (periodos restantes; `OB[0]` = fuera de tiempo). Sin datos de tiempo, el SGF es idéntico al de antes.
- `tcSgfSummary(sgf, myColor)` para el histórico: media, jugada de entrada en byoyomi, jugada en que se acabó el tiempo.
- Estado de partida previsto para RL2: `game.tc` (sistema) y `game.tlog[i] = {t, a}` por jugada (aparte de `game.moves`, que se envía tal cual al servidor).
- `test_clock.js` 58 PASS (verificado con mutante); `test_ai.js` 75 y `test_ai_sync.js` 21 siguen OK.

### RL2 — Flujo de Play con reloj (hecho)
- Panel de partida nueva: "Reloj" (Sin reloj / Byoyomi) y, con byoyomi, Principal (min, admite decimales y 0), Periodos y Segundos. Se guardan en `localStorage['ai_clock']` (con "sin reloj" se guardan igual los números).
- Partida: `tc`, `clk`, `tlog`, `turnSpent`, `paused`, `pending`. La jugada puesta queda en `pending` (triángulo sobre la piedra, se puede cambiar) y no entra en `moves` hasta pulsar el reloj, así que el servidor no cambia. Pasar con reloj = pase pendiente.
- La barra bajo el tablero es el reloj (`aiClockText`): "● 4:32 · te toca", dorada con "pulsa el reloj", roja "−0:12 fuera de tiempo"; en el turno de la IA muestra el reloj parado. Tocarla o Espacio = pulsar; P o "⏸ Pausa" = pausa (tablero oculto con el aviso de pausa, como en los problemas).
- El tiempo corre solo si: pestaña Play, mi turno, sin pausa, sin estimación en pantalla y app visible. Pausa automática al ocultarse la app y al salir de Play; al volver a entrar, en pausa. Sin reloj solo se detiene la medida y sigue sola.
- Mi turno empieza (contador a 0) cuando aparece la jugada de la IA. "← Atrás" recorta `tlog` y no toca `clk` ni el turno en marcha. Se guarda `turnSpent` cada 5 s por si se cierra la app.
- Sin reloj: flujo idéntico al anterior (jugada directa, sin ⏸), pero con el tiempo medido (`TT`).
- Pruebas: prueba de extremo a extremo en Chromium con WGo real y servidor simulado (31 comprobaciones: panel recordado, piedra pendiente sin envío, cambio de piedra, pulsación por toque y Espacio, pausa con P y con el aviso, tiempo congelado en pausa y con estimación, byoyomi, fuera de tiempo sin terminar la partida, Atrás sin devolver tiempo, pase + pulsación, pausa al ocultar y al cambiar de pestaña, SGF guardado con TM/OT/TT/BL/OB y leído por `tcSgfSummary`, partida sin reloj como antes). `sgf_to_position` del servidor lee el SGF con tiempos.

### RL3 — Avisos (hecho)
- `tcEventCue(ev)` (pura): entrada en byoyomi "Byoyomi" (con un solo periodo, "Byoyomi. Último periodo"), cuenta atrás en palabras ("nueve" … "uno"), "Quedan N", "Último periodo", "Fuera de tiempo"; cada aviso con su patrón de vibración. `tcCueKeys(sys)`: grabaciones posibles.
- Voz del navegador en `es-ES` (`aiSpeak`; cada aviso corta el anterior, así la cuenta atrás no se acumula). Se "despierta" con un toque (Empezar, pulsar, pausa) porque algunos móviles solo hablan tras un gesto.
- Grabaciones propias: `audio/clock/<key>.mp3` (`byoyomi`, `1`…`9`, `quedan_2`…, `ultimo_periodo`, `fuera_de_tiempo`). Se prueba primero `byoyomi.mp3`; si no está, no se pide ninguna más. Con un juego incompleto, las que falten van con voz.
- Silencio general de ⚙ (`soundEnabled`) calla voz y grabaciones; la vibración va siempre. Volumen = volumen de efectos.
- Avisos atrasados (app congelada > 1,5 s) no se recitan.
- Pantalla encendida (Wake Lock) mientras hay partida con reloj en Play sin pausa; se libera en pausa, al salir o al terminar. Sin esto, la pantalla se apagaría al pensar y el reloj se pausaría.
- Pruebas: `test_clock.js` 69 PASS; prueba en Chromium con voz, vibración y pantalla simuladas (secuencia completa de avisos, silencio con vibración, grabaciones parciales mezcladas con voz, liberación en pausa).

### RL4 — Tiempos en el histórico (hecho)
- `tcHistoryText(tcSgfSummary(sgf, mi color))` (pura): corto para la fila ("⏱ 24 s/jug · byo 87 · ⏰ 142") y largo para el título al pasar el ratón ("Media pensada por jugada: 24 s (95 jugadas) · reloj 10 min + 5 × 30 s · entraste en byoyomi en la jugada 87 · se te acabó el tiempo en la jugada 142"). Partidas anteriores al reloj: nada. `tcSgfSummary` lee también `TM`.
- Histórico de estadísticas: columna nueva tras el tipo de final (en rojo si hubo ⏰); `localAiGames` trae `sgf`. Panel de Play, "Última partida": la línea larga.
- Pruebas: `test_clock.js` 76 PASS; en Chromium, fila del histórico y panel tras una partida real con reloj.

**Pendiente para más adelante:** barra de tiempos por jugada en el analizador (con "pensaste 4 s" en el texto de la jugada) y byoyomi canadiense.

### AN5b — Corrección: caché que no servía en partidas con handicap (15-nov-2026)
- Síntoma: tras el análisis automático (7 partidas al arrancar), 🔍 sobre un error seguía calculando.
- Causa: la clave de la caché incluía las piedras de handicap en el orden recibido. El trabajador las lee del SGF (D4, Q16, Q4…) y la app las manda recorriendo el tablero por columnas (D4, Q4, Q16…): misma posición, clave distinta. En partidas igualadas no afectaba.
- Arreglo: `cache_key` ordena las piedras de handicap. Las entradas antiguas de partidas con handicap quedan huérfanas; al reiniciar, la revisión al arrancar las recalcula con la clave buena.
- `test_server.py` 301 PASS (AN5b, verificado con mutante).

### AN5c — Errores con umbrales de KaTrain y solo los míos (15-nov-2026)
- Diagnóstico (`diag_analisis.py`, solo lectura, en el VPS): la caché funcionaba, pero las partidas a 20k tenían 80–90 errores de ≥5 (de los dos colores) y solo se preparaban los 30 mayores.
- Umbrales de KaTrain: error ≥ 6, grave ≥ 12 (app `AN_MISTAKE`/`AN_BLUNDER`; servidor `AN_PRE_MISTAKE = 5.95`).
- El trabajador prepara **solo mis errores** (todos, de mayor a menor; tope de seguridad 200): `enqueue(..., mine)` con `my_color` de `ai_games`; `/ai/graph_job` acepta `mine` (la app lo manda al revisar una partida contra la IA). Partidas de colecciones: los dos colores. Los errores de la IA se calculan al pulsar 🔍.
- `test_server.py` 302 PASS (AN5c, verificado con mutante).

### Idea en análisis — Accuracy como medida de progreso
- KaTrain (`katrain/core/ai.py`, `game_report`): pérdida por jugada = ventaja antes − después (desde quien juega). Accuracy = 100 × 0,75^(pérdida ponderada); peso de cada jugada = complejidad (media de pointsLost de las candidatas ponderada por prior, tope 1), ajustado a max(0,05, min(1, max(complejidad, pérdida/4))). Mean Point Loss = media simple. Best move % = 1.ª de KataGo; Top 5 % = 1.ª o de las 5 primeras con pérdida < 0,5. Tramos: apertura < 14 % del tablero (jugada 51), medio medio hasta 40 % (145), final después. Umbrales del histograma: 0,5 · 1,5 · 3 · 6 · 12.
- Recomendación: Accuracy como métrica única de progreso. Requiere guardar las candidatas (prior y scoreLead) de la búsqueda de la gráfica, no solo la ventaja.
