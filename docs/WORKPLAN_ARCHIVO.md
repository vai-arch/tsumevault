# WORKPLAN_ARCHIVO — Archivo de partidas profesionales (estructura de kifumaster)

Estado: **Borrador para revisión de Victor (26-nov-2026). Nada implementado.**
Base revisada: `main` del 26-nov-2026 (`tsumevault.html` 10.135 líneas, `server/tsumevault_server.py` 3.367 líneas).

---

## 0. Resumen de requisitos (cerrados en el análisis del 26-nov)

**Origen de los datos**
- La **estructura** sale de los datos públicos de kifumaster.org (sin protección), descargados a ritmo tranquilo:
  - índice de partidas `seo/g/00.json` … `ff.json` (id → negras, blancas, evento, fecha, resultado; ~820 partidas por fichero, ~210.000 en total);
  - mapa evento → torneo/edición `seo/te/*.json` (p. ej. "52nd Meijin" → `meijin/52`);
  - CSV de normalización `database/aliases.csv`, `aliasesevent.csv`, `aliasesrank.csv`, `event_families.csv`;
  - páginas de edición `tournament/<torneo>/<edición>`, que dan la **fase** de cada partida (tabla principal, "Preliminary B", …).
- Las **jugadas (SGF) no se descargan por script**: están tras Firebase App Check. Victor las descarga a mano desde la web de kifumaster y las coloca en su carpeta.
- Ritmo del descargador: una petición cada 5–10 s (+ margen aleatorio), una sola conexión, 24/7, backoff ante 429/5xx (1 → 5 → 30 min; si se repite, para y avisa), reanudable, User-Agent identificable con contacto, respeta robots.txt (nada de `?step=`).
- Se ejecuta **periódicamente** (mensual) en el VPS y solo trae lo nuevo.

**Organización**
- Jerarquía: torneo → edición → **fase** (desde el principio) → partida. Jugadores normalizados con sus alias.
- Metadatos "oficiales" (nombres, evento, fecha, resultado) = los del índice público, buscando por id. Del SGF solo se toman las jugadas y los datos que el índice no trae: rangos (traducidos con `aliasesrank.csv`, 四段 → 4p), komi, lugar (tal cual). Se guardan también los nombres originales del SGF.

**Almacenamiento**
- SGF en el VPS en `archive/sgf/<xx>/<id>.sgf` (`xx` = dos primeras cifras hex del id). El fichero no se mueve nunca; torneo/edición/fase son datos.
- Catálogo en una base SQLite propia, `archive.db`, separada de `tsumeVault.db`.
- **Nada del archivo entra en el repo de GitHub** (problema previo de Pages con ~119k ficheros). En el portátil, `archive/` va en `.gitignore`.

**Flujo de Victor**
- `games.txt` por edición: una fila por partida, `<id> archive/sgf/<xx>/<id>.sgf`.
- Victor descarga el SGF desde kifumaster y lo deja en esa ruta dentro de su copia local de `archive/`.
- `_subir_archivo.bat`: sube por SCP los ficheros nuevos y lanza en el VPS el escaneo, que valida (fecha y jugadores del SGF frente al índice; si no cuadran, avisa y **no** importa) y marca la partida "con SGF". Después baja `games_pendientes.txt` actualizado.

**Página**
- Página independiente `archive.html`, **totalmente separada** de la pestaña Games (Games sigue siendo para partidas propias comentadas/estudiadas).
- Catálogo **mixto (opción C)**: la estructura ligera (torneos, ediciones, fases, recuentos) se cachea en el navegador para navegar sin conexión; las listas de partidas se piden al servidor al abrirlas y quedan en caché.
- Filtros (combinados con Y; orden por fecha descendente): torneo → edición → fase encadenados; jugador con autocompletado por alias (cualquier color / solo negras / solo blancas); dos jugadores (enfrentamientos directos); rango de años; "solo con SGF". Sin ficha de jugador por ahora.
- Partida sin SGF: sus datos + enlace a kifumaster. Con SGF: **el mismo visor de Games, completo** (navegación, reproducción automática, variantes, comentarios y análisis con KataGo).

**Fuera de alcance (por ahora)**: ficha de jugador, enviar partidas a Games, subida desde el móvil, búsqueda por apertura/patrón, descarga automática de SGF.

---

## AR0 — Refactor: visor compartido (sin cambios de comportamiento)

Objetivo: sacar de `tsumevault.html` el visor de Games y su análisis para que `archive.html` lo reutilice. **Dificultad: Media-Alta** (riesgo de regresión en problemas, josekis y Play).

Lo que hay hoy (líneas aprox. del 26-nov):
- `// ══ GAMES VIEWER ══` (7364–7639, ~270 líneas): navegación, timer, variantes, comentarios, click en tablero.
- `// ══ AN2: ANÁLISIS ══` (7669–8064, ~400 líneas): gráfica, mejores jugadas, errores, tiempos.
- Dependencias del núcleo de tablero compartido con problemas/josekis/Play: `wgoBoard`, `boardSize`, `initBoard`, `clearBoard`, `addLastMoveMark`, `moveQualityMark`, `playStoneSound`, `capturedAny`, `sgfUrl`.
- Usos desde fuera: la pestaña Play llama a ~10 funciones `an*` (`anGameInfoRows`, `anMistakes`, `anPosition`, …); los cambios de pestaña tocan `gmActive`; el repintado al girar llama a `gmRenderCurrentNode`.

Trabajo:
1. `js/board_core.js`: núcleo de tablero y utilidades comunes (sin estado de problema).
2. `js/game_viewer.js`: visor + AN2. Recibe por un `init({...})` lo que hoy toma de globales específicos de la app (SGF a cargar, contenedor de controles, URL del servidor de análisis). La lista de colecciones de Games **se queda** en `tsumevault.html`.
3. `tsumevault.html` carga ambos con `<script src>` y se comporta exactamente igual.
4. `sw.js`: añadir los dos ficheros a `STATIC_ASSETS`.
5. Tests: adaptar `extract_*.py`/harness para que concatenen los nuevos `.js` con el script de la página. La referencia "bundle byte-idéntico" pasa a ser "bundle equivalente": mismo código, otro orden de ficheros.

Validación: línea base antes del cambio y mismas cifras después (`python tests/test_server.py`, `python tests/extract_ai.py && node tests/test_ai.js && node tests/test_clock.js`, joseki, focus, sfx), `node --check` de cada `.js`, mutaciones que demuestren que el harness carga de verdad los ficheros nuevos.
Checklist manual (M-AR0): Games (abrir, navegar, timer, variantes, comentarios, análisis), revisión de partidas de Play (gráfica, errores), josekis, Run/Free/Review de un problema, giro de pantalla en el móvil, funcionamiento sin conexión tras actualizar el service worker.
Despliegue: rama `archivo-ar0-visor`; `_desplegar_rama.bat` + `_subir_git.bat` (toca `sw.js`).

---

## AR1 — `archive.db` y descargador de metadatos (VPS)

**Dificultad: Media.** Ficheros nuevos en `tools/` y `server/`; no toca nada existente.

### Esquema `archive.db` (v1)

```sql
CREATE TABLE ar_tournaments (            -- familia: Meijin, Kisei, Samsung Cup…
  slug TEXT PRIMARY KEY,                 -- 'meijin' (de seo/te)
  name TEXT NOT NULL,                    -- 'Meijin' (base de event_families.csv)
  numbering TEXT,                        -- ord | year | season
  game_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE ar_editions (
  id INTEGER PRIMARY KEY,
  tournament_slug TEXT NOT NULL REFERENCES ar_tournaments(slug),
  edition TEXT NOT NULL,                 -- '52', '2017'
  event_name TEXT NOT NULL UNIQUE,       -- '52nd Meijin' (clave del índice)
  year_from INTEGER, year_to INTEGER,
  game_count INTEGER NOT NULL DEFAULT 0,
  phases_crawled_at TEXT,                -- NULL = página de edición aún sin leer
  UNIQUE (tournament_slug, edition)
);
CREATE TABLE ar_phases (
  id INTEGER PRIMARY KEY,
  edition_id INTEGER NOT NULL REFERENCES ar_editions(id),
  name TEXT NOT NULL,                    -- '' = tabla principal; 'Preliminary B'…
  ord INTEGER NOT NULL,                  -- orden de aparición en la página
  UNIQUE (edition_id, name)
);
CREATE TABLE ar_players (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,             -- canónico ('Seto Taiki')
  nationality TEXT
);
CREATE TABLE ar_player_aliases (
  alias TEXT NOT NULL, player_id INTEGER NOT NULL REFERENCES ar_players(id),
  script TEXT, PRIMARY KEY (alias, player_id)
);
CREATE TABLE ar_games (
  id TEXT PRIMARY KEY,                   -- 32 hex de kifumaster
  edition_id INTEGER REFERENCES ar_editions(id),   -- NULL si el evento no está en seo/te
  phase_id INTEGER REFERENCES ar_phases(id),
  event_name TEXT NOT NULL,
  date TEXT,                             -- ISO tal cual del índice
  black_id INTEGER REFERENCES ar_players(id),
  white_id INTEGER REFERENCES ar_players(id),
  result TEXT,                           -- texto del índice
  has_sgf INTEGER NOT NULL DEFAULT 0,
  -- solo con SGF:
  black_rank TEXT, white_rank TEXT, komi TEXT, place TEXT,
  black_orig TEXT, white_orig TEXT, event_orig TEXT, moves INTEGER,
  sgf_imported_at TEXT,
  first_seen_at TEXT NOT NULL
);
CREATE INDEX ix_g_edition ON ar_games(edition_id, date);
CREATE INDEX ix_g_black ON ar_games(black_id, date);
CREATE INDEX ix_g_white ON ar_games(white_id, date);
CREATE INDEX ix_g_date ON ar_games(date);
CREATE TABLE ar_crawl (                  -- estado reanudable del descargador
  url TEXT PRIMARY KEY, status TEXT NOT NULL,      -- pending | done | error
  etag TEXT, last_modified TEXT, fetched_at TEXT, error TEXT, tries INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE ar_meta (key TEXT PRIMARY KEY, value TEXT);   -- schema_version, último ciclo…
```

Los jugadores que aparecen en el índice y no en `aliases.csv` se crean igualmente con su nombre del índice.

### `tools/archive_crawl.py`
- Fases del ciclo: (1) CSV, (2) 256 ficheros `seo/g`, (3) 256 ficheros `seo/te`, (4) páginas de edición con `phases_crawled_at` NULL o con partidas nuevas.
- Estimación del primer ciclo: 4 + 256 + 256 peticiones + una por edición (miles) → del orden de horas a una cada 5–10 s. Los ciclos mensuales siguientes: pide con `If-None-Match`/`If-Modified-Since` cuando el servidor lo permita; solo vuelve a leer las páginas de edición con partidas nuevas.
- Reglas de cortesía del §0 (ritmo, backoff, parada, User-Agent, robots).
- Se puede parar con Ctrl-C o reiniciar en cualquier momento: el estado está en `ar_crawl`.
- `--dry-run N`: descarga solo N páginas y muestra lo que haría (para la verificación de AR1.0).
- Al final regenera las listas (ver AR4).

**AR1.0 — Verificación en el VPS antes de escribir el parser** (comandos ssh que Claude da uno a uno): bajar 1 fichero `seo/g`, 1 `seo/te` y 2 páginas de edición (una con fases y otra sin ellas) para fijar el formato exacto del HTML de las fases y confirmar que hay 256 ficheros `seo/te` (clave de reparto).

Tests: `tests/test_archive_crawl.py` con fixtures locales (sin red): parseo de índice, te, CSV y páginas de edición; reanudación tras corte; backoff ante 429/503 con un servidor falso; idempotencia (dos ciclos seguidos = mismas filas); partida nueva en un ciclo posterior.
Ejecución periódica: `systemd timer` mensual en el VPS (o `cron`), con log en `/opt/tsumevault/logs/archive_crawl.log`.

---

## AR2 — Endpoints del servidor y SGF estáticos

**Dificultad: Media.** Toca `tsumevault_server.py` (rutas nuevas, sin cambiar las existentes) y `Caddyfile`.

- `archive.db` se abre aparte (solo lectura para las rutas GET; el escaneo de AR4 escribe con su propio bloqueo). No usa `DB_LOCK` de `tsumeVault.db`.
- Rutas (GET, con el mismo `_gate` de token):
  - `/archive/tree` → torneos, ediciones y fases con recuentos (total y con SGF). Es la "estructura ligera" que se cachea. Lleva `version` para revalidar barato.
  - `/archive/games?edition=&phase=&player=&player2=&color=&year_from=&year_to=&has_sgf=&offset=&limit=` → lista paginada (límite por defecto 200) ordenada por fecha descendente.
  - `/archive/players?q=` → autocompletado (nombre canónico o alias, máx. 20).
  - `/archive/game?id=` → ficha completa de una partida.
- SGF: `Caddyfile` sirve `/archive/sgf/*` desde `/opt/tsumevault/archive/sgf` como fichero estático (igual que `/player/*`), con CORS.
- Tests en `test_server.py`: cada filtro solo y combinado, paginación, jugador por alias en japonés, `player2`, validación de parámetros (400), 401 sin token, servidor arrancando sin `archive.db` (las rutas responden 503 y el resto de la app funciona).

---

## AR3 — `archive.html`

**Dificultad: Media.** Fichero nuevo; no toca `tsumevault.html`.

- Carga `wgo/*`, `js/board_core.js` y `js/game_viewer.js` (AR0). Mismo estilo visual que la app.
- Panel izquierdo: filtros del §0 y lista de resultados (fecha · negras · blancas · resultado · indicador con/sin SGF). Etiquetas mínimas; las explicaciones van en tooltips (que funcionen con el S Pen).
- Navegación: torneo → edición → fase como selects encadenados alimentados por `/archive/tree`.
- Caché: `/archive/tree` y las listas abiertas en IndexedDB (o `caches` del service worker). Sin conexión: se navega la estructura y las listas ya abiertas; los SGF ya vistos quedan en la caché.
- Partida sin SGF: datos + enlace "abrir en kifumaster" + su ruta de destino (para copiarla).
- Partida con SGF: visor compartido completo, con análisis KataGo cuando hay conexión.
- Enlaces: botón para ir a `archive.html` desde `tsumevault.html` (junto al de lecciones 📚) y para volver.
- `sw.js`: `archive.html` en `STATIC_ASSETS`.
- Tests: `tests/extract_archive.py` + `tests/test_archive.js` (filtros encadenados, construcción de la query, render de lista, caché sin conexión con fetch simulado).
- Checklist manual M-AR3 (portátil y móvil): navegar Meijin 52 por fases, buscar "瀬戸大樹" y "Seto Taiki", enfrentamientos de dos jugadores, rango de años, "solo con SGF", abrir una partida con y sin SGF, análisis, modo avión.

---

## AR4 — Listas, subida y escaneo

**Dificultad: Baja-Media.**

- Listas generadas en el VPS por el descargador y por el escaneo, en `archive/lists/<torneo>/<edición>/`:
  - `games.txt`: todas las partidas de la edición, una por línea: `<id> archive/sgf/<xx>/<id>.sgf`.
  - `games_pendientes.txt`: las que aún no tienen SGF (mismo formato).
- `tools/archive_scan.py` (VPS): recorre `archive/sgf/`, para cada fichero nuevo o cambiado:
  - extrae el id de los 32 hex del nombre (tolera prefijos/sufijos);
  - parsea el SGF; comprueba `DT` frente a la fecha del índice y `PB`/`PW` frente a los jugadores (por alias o nombre; si el jugador no tiene alias conocidos, solo se exige la fecha);
  - si cuadra: rellena rangos (vía `aliasesrank.csv`), komi, lugar, originales, nº de jugadas, `has_sgf=1`;
  - si no cuadra o no parsea: lo deja fuera y lo lista en el informe (no lo borra).
  - al final regenera los `games_pendientes.txt` afectados y escribe el informe.
- `_subir_archivo.bat` (raíz del repo, portátil):
  1. compara la carpeta local `archive\sgf\` con la lista del servidor (`ssh … ls`) y sube por SCP solo los nuevos, con keep-alive (`-o ServerAliveInterval=20 -o ServerAliveCountMax=12`);
  2. `ssh … python3 /opt/tsumevault/tools/archive_scan.py` y muestra el informe;
  3. baja `archive/lists/` actualizado a la carpeta local.
- `.gitignore`: `archive/`.
- Tests: `tests/test_archive_scan.py` (id con prefijo, SGF correcto, fecha que no cuadra, jugador por alias japonés, SGF corrupto, regeneración de pendientes, idempotencia).

---

## AR5 — Despliegue y puesta en marcha

1. Copia de seguridad en el VPS de los `.py` y de `tsumeVault.db` (`.backup`).
2. Desplegar AR0 → probar M-AR0 en el móvil.
3. Desplegar AR1 + AR2 (`_desplegar_rama.bat`, `_subir_servidor.bat`, `_subir_caddy.bat`); crear `/opt/tsumevault/archive/`; lanzar el primer ciclo del descargador en segundo plano (`systemd-run` o `nohup`) y seguir el log.
4. Desplegar AR3 + AR4 (+ `_subir_git.bat`); probar M-AR3 con las dos partidas del Meijin 52 ya descargadas (`2f193e52…`, `0a128ad6…`).
5. Activar el timer mensual.

---

## Riesgos y decisiones abiertas

- **Formato de las páginas de edición**: es la única parte en la que hay que leer HTML; si kifumaster lo cambia, el parser de fases falla. Mitigación: el parser registra la edición como `error` y las partidas siguen entrando sin fase (la fase se rellena en el siguiente ciclo, cuando se arregle).
- **Eventos sin entrada en `seo/te`**: partidas con `edition_id` NULL; la página las muestra en un grupo "Sin clasificar" por nombre de evento.
- **Tamaño de la caché en el móvil**: la estructura ligera (miles de ediciones) se estima en pocos cientos de KB comprimida; las listas, solo las abiertas.
- **Licencia**: kifumaster no publica términos de uso. Se usa solo lo público y para estudio personal. Si en algún momento se quiere el archivo completo de SGF, el camino es pedirles un volcado.
