# WORKPLAN_ARCHIVO — Archivo de partidas profesionales (estructura de kifumaster)

Estado: **Plan aprobado por Victor (26-nov-2026). AR0 ✔ desplegada y probada. AR1.0 ✔. AR1 ✔ (primer ciclo real hecho en el portátil). AR2 ✔ desplegada. AR3a ✔ entregada (rama `ar3a-board-core`), pendiente de probar en el móvil; AR3b después.**
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

Ajuste de diseño al implementar (26-nov): el núcleo de tablero (`initBoard`, `clearBoard`, marcas, sonidos…) está muy ligado al estado de la app (fondo y juego de piedras, volumen, `comment-box`, `welcome`). Sacarlo en AR0 multiplicaba el riesgo sin beneficio inmediato, así que **AR0 mueve solo el visor y AN2, tal cual**, y el núcleo de tablero se extrae en AR3, cuando `archive.html` lo necesite.

Entregado:
1. `js/game_viewer.js` (644 líneas): estado del visor, `gmOpenGame`…`gmInitControls` y todo AN2, movidos sin cambiar una línea (solo sin la sangría). Se carga con `<script src>` justo antes del script principal y comparte con él el ámbito global.
2. Se quedan en `tsumevault.html`: la lista de colecciones de Games (`gmCollections`, `gmLoadCollections`, `gmLoadGameList` y su listener) y el estado del servidor (ST1).
3. Contrato con la página documentado al final de `game_viewer.js`: 26 nombres que el visor toma de la página (tablero, sonido, `sgfUrl`, `lsGet/lsSet`, `aiPost/aiToGtp/aiFromGtp/AI_OWN_HANDLER` y las funciones puras `an*` del bloque IA3) y 6 que la página toma del visor. Calculado con un parser de JS: ninguna declaración duplicada y ninguna dependencia sin resolver.
4. `sw.js`: `/tsumevault/js/game_viewer.js` en `STATIC_ASSETS`.
5. `tests/test_game_viewer.js` (28 checks): estructura (etiqueta y orden, nada duplicado, nada olvidado en la página, contrato completo) y prueba de humo del visor real con el WGo real (abrir, ▶ ◀, comentario, variantes, ↩, captura con su sonido, cambio de tamaño). Mutaciones comprobadas: sin `<script src>`, `gmActive` duplicado, ▶ siguiendo la variante equivocada, la página sin `clearBoard`, sin sonido al avanzar → todas fallan.

Validación: misma línea base antes y después (server 344, ai 111, clock 80, focus 72, sfx 23, lp1 OK; joseki no se puede correr en el contenedor por fixtures no versionados), los cinco bundles extraídos por los tests (ai, focus, sfx, joseki, joseki_ui) idénticos byte a byte, `node --check`, y prueba en Chrome sin interfaz de la página real antes/después con resultados idénticos y sin errores de JavaScript.

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

### Descubrimiento de AR1.0 (26-nov) y diseño final

Las páginas de torneo y edición son una carcasa vacía de SvelteKit (6.117 B, iguales todas): el contenido se pinta en el navegador a partir de **JSON públicos**, que son lo que bajamos. No hay que leer HTML.
- `seo/t/xx.json`: torneos con su lista de ediciones; `seo/ts/xx.json`: ediciones con sus **secciones** (p. ej. "8th Kisei Title Match" y "8th Kisei") y, por sección, partidas `[id, negras, blancas, fecha, resultado]` y fases `t = [[fase, nº], …]`. Las partidas de cada fase son bloques consecutivos al final de la lista, en el orden de `t` (verificado con el Meijin 52 contra las tablas de la página: 30 + 16 + 39 = 85).
- Las cuatro familias (`g`, `te`, `t`, `ts`) tienen 256 repartos y llevan ETag. Total: 1028 peticiones, ~2 h el primer ciclo a 6–8 s.

Mientras el proceso no esté controlado, todo corre en el portátil de Victor, en `kifumaster/` (scripts en git, `kifumaster/data/` fuera). Dos pasos separados:
1. `kifumaster/kifu_crawl.py` (`kifu_crawl.bat`): **solo descarga**, tal cual, a `data/raw/`. Reglas de cortesía del §0, petición condicional (ETag/Last-Modified → 304), backoff 1/5/30 min ante 429/5xx y parada, validación del contenido (no guarda un JSON roto), estado en `data/raw/_estado.json` tras cada petición, ciclos (`--nuevo-ciclo` para el mensual).
2. `kifumaster/kifu_build.py` (`kifu_build.bat`): construye `data/archive.db` y las listas **sin red**; se repite cuando se quiera (conserva `first_seen`).

Esquema real de `archive.db` (v1; sustituye al borrador de arriba): `ar_tournaments` (slug, nombre, nombre local, años, nº de partidas, historia), `ar_editions` (etiqueta, slug, nº de partidas y de jugadores, fechas, orden), `ar_sections` (evento, orden, fases tal cual), `ar_games` (id, evento, fecha, negras, blancas, resultado corto y largo, edición, sección, **fase** — `''` = tabla principal —, orden en la sección, `has_sgf`, `first_seen`), `ar_players`, `ar_player_aliases`, `ar_event_aliases`, `ar_rank_aliases`, `ar_meta`. Se eliminan `ar_phases` y `ar_crawl` del borrador: la fase es un texto de la partida y el estado de descarga vive en `_estado.json`. Los datos que salen del SGF (rangos, komi, lugar…) se añaden en AR4.

Primer ciclo real (26-nov, portátil): 1028 ficheros sin un error; catálogo con 57 torneos, 1.724 ediciones, 2.541 secciones, 179.994 partidas (113.800 en su sección, 16.237 con fase), 6.772 jugadores. El 37 % (66.193 partidas, 4.237 eventos) son de eventos que kifumaster no organiza en torneos; 13.230 no tienen evento.

**"Otros eventos"** (decidido por Victor el 26-nov): se agrupan en torneos propios con `kind='otros'` (los de kifumaster, `kind='kifumaster'`) y slug `otros-…`. Regla (`otros_family`): un número ordinal o un año al principio del nombre es la edición ("2nd Lanke Cup" → Lanke Cup / 2; "2016 National League" → National League / 2016; "2017-2018 Pro-Ama League" → Pro-Ama League / 2017-2018); sin número, el evento es un torneo de edición única (`unica`); sin evento, "Sin evento" por año. Una sección por edición y sin fases. Ocultos por ahora (ver «Otros eventos ocultos y promocionados»).

Listas (adelantadas de AR4): `data/lists/<torneo>/<edición>/games.txt` (`<id> archive/sgf/<xx>/<id>.sgf`, en el orden de la página) y `games_pendientes.txt` (las que aún no están en esa ruta del repo); las de otros eventos, en `data/lists/otros-…/<edición>/`.

Tests: `tests/test_kifu.py` (51 checks) con un servidor HTTP falso: reanudación, 429/503 con espera, 404, gzip, condicional/304 y cambio detectado, parada ante 503 persistente y ante JSON roto, pausa real entre peticiones, catálogo (secciones, fases, alias, nacionalidad, ediciones por `te`, sin clasificar, `has_sgf`), listas y `first_seen`. Mutaciones comprobadas (fases al principio, sin condicional, sin esperas, sin guardar estado, sin mirar los SGF, sin validar, sin pausa): todas fallan.

---

## Otros eventos ocultos y promocionados (26-nov, decidido por Victor) ✔ (rama `archivo-promocionados`)

Los 57 torneos de kifumaster (1.724 ediciones, ~113.800 partidas: el 63 % del archivo en el 3 % de los torneos) bastan para empezar. Los "otros eventos" siguen en `archive.db` con `kind='otros'` pero **no se muestran**: `ar_games.visible = 0` (esquema v4, índice `ix_g_visible`), sin `sgf_path` ni carpeta en `lists/`, fuera del árbol, de la lista y del autocompletado (que además solo cuenta partidas visibles).
- `kifumaster/promocionados.txt` (en git): `<torneo-actual> [carpeta-nueva] [nombre para mostrar]` por línea; sin carpeta nueva se quita el `otros-`. El torneo pasa a `kind='promocionado'` y se muestra tras los de kifumaster. Si la carpeta nueva choca con un torneo existente, se avisa y se promociona con su slug de siempre; los nombres que no existen se avisan y se ignoran. Quitar la línea lo vuelve a ocultar (sus listas se quitan; los SGF no se tocan y siguen contando).
- Tests: `test_kifu.py` 64 checks, `test_archive_server.py` 41; mutaciones (lista y árbol enseñando ocultos, no quitar el `otros-`, carpetas para ocultos, autocompletar jugadores solo de ocultos): todas fallan.

## Cambio de estructura de los SGF (26-nov, decidido por Victor) ✔ (rama `archivo-sgf-por-edicion`)

Los SGF se guardan **en la carpeta de su edición**, junto a sus listas: `kifumaster/data/lists/<torneo>/<edición>/<id>.sgf` en el portátil y `/opt/tsumevault/archive/sgf/<torneo>/<edición>/<id>.sgf` en el servidor (sustituye a `archive/sgf/<xx>/`). `games.txt` y `games_pendientes.txt` pasan a una sola columna (el id): la carpeta ya es el destino.
- `kifu_build`: ya no vacía `lists/` (allí viven los SGF); reescribe las listas, quita las de carpetas que ya no son ediciones, guarda `sgf_path` en `ar_games` (esquema v3) y **mueve** a su carpeta cualquier SGF que esté en otra (partida que cambió de edición o el antiguo `archive/sgf/<xx>/`); avisa de repetidos y de SGF de partidas que no están en el catálogo, sin borrar nada.
- `kifu_upload`: sube por carpeta de edición; si el servidor ya tiene el SGF en otra ruta lo **mueve allí** (`mv -n`) en vez de volver a subirlo; al acabar toca `sgf/.stamp`.
- `archive_api`: recorre `sgf/` entero (también la ruta antigua) y lo guarda en caché; recalcula cuando cambia `sgf/.stamp` o la raíz, y cada 5 min como red de seguridad. La ficha devuelve la ruta en el portátil.
- Tests: `test_kifu.py` 57 checks y `test_archive_server.py` 36; mutaciones (no mover, vaciar `lists/`, subir en vez de mover, ignorar `.stamp`, no tocarlo): todas fallan.

## AR2 — Endpoints del servidor ✔ (rama `archivo-ar2`)

Decidido con Victor (26-nov): mientras el descargador corre en el portátil, `archive.db` se construye allí y **viaja al VPS** con `_subir_archivo.bat` (`kifumaster/kifu_upload.py`) junto con los SGF nuevos. Cuando el proceso esté controlado, el descargador pasará al VPS y la base dejará de viajar.

- `server/archive_api.py` (nuevo, como `ai_engines.py`; `_subir_servidor.bat` lo sube): consultas de **solo lectura** a `/opt/tsumevault/archive/archive.db` (conexión `mode=ro` por petición, así que la sustitución con `mv` es segura), **sin `DB_LOCK`**. Si falta la base: 503, y el resto de la app sigue.
- Rutas (GET, con el mismo token): `/archive/tree` (torneos → ediciones → secciones con fases y recuentos; ~870 KB sin comprimir, en caché), `/archive/games` (filtros: `tournament`, `edition`, `section`, `phase` —vacío = tabla principal—, `player` [+`color=b|w`], `player2`, `year_from`, `year_to`, `has_sgf=1`, `offset`, `limit` ≤ 500; orden por fecha descendente), `/archive/players?q=` (por nombre o alias, también en japonés/coreano/chino), `/archive/game?id=` (ficha + enlace a kifumaster + ruta del SGF), `/archive/sgf?id=` (el SGF como JSON).
- **Cambio respecto al borrador: los SGF NO se publican con Caddy** como fichero estático abierto. Son ficheros de kifumaster descargados a mano para estudio personal; servirlos en abierto en internet sería redistribuirlos. Se sirven por `/archive/sgf`, solo con token. `Caddyfile` sin cambios.
- **El disco manda**: qué partidas tienen SGF lo decide el contenido de `archive/sgf/` en el servidor (cacheado por el mtime de las carpetas), no la columna `has_sgf`; un SGF subido aparece sin reconstruir ni reiniciar.
- Rendimiento con un catálogo sintético de 180.000 partidas: árbol 155 ms la primera vez y 1 ms en caché; lista sin filtros 12 ms (índice `ix_g_date (date, id)` y recuento sin JOIN cuando no hace falta); con filtros 2–20 ms; autocompletado 2–23 ms; `has_sgf=1` sobre todo el archivo ~400 ms.
- El servidor conserva los parámetros vacíos solo en `/archive/*` (`parse_qs(keep_blank_values=…)`), para que `phase=` funcione sin cambiar nada en el resto de rutas.

Tests: `tests/test_archive_server.py` (34 checks): token, ids no válidos (sin path traversal), límites, árbol, cada filtro y combinaciones, alias japonés, paginación, otros eventos, ficha, SGF, SGF subido en caliente en varias carpetas, 503 sin base; y la subida con ssh/scp falsos (simular, saltar ficheros que no son SGF, sustitución sin `.new`, no repetir, subir solo la base cambiada, comprobación de lectura en el servidor). Mutaciones comprobadas (sin validar el id, `has_sgf` sin mirar el disco, enfrentamientos en un solo color, subir siempre la base, `phase` vacío ignorado, ordenar carpetas sin clave): todas fallan. Dos fallos reales encontrados y corregidos al probar: `parse_qs` descartaba `phase=` y ordenar entradas de directorio sin clave reventaba con más de una carpeta. `test_server.py` sigue en 344.

---

## AR3 — `archive.html` (plan detallado del 26-nov, pendiente de aprobación)

### Decisiones de diseño (Victor, 26-nov)
- **Navegación: árbol desplegable** como la pestaña Collections. Torneos → ediciones (con recuento "85 · 2 con SGF") → secciones/fases. Cuadro para filtrar torneos por nombre; promocionados al final.
- **Orden de los torneos: por país** (Japón, Corea, China, Taiwán, Internacionales) y dentro, por nº de partidas. El país se deduce del idioma del nombre original (`ll` de `seo/t`); los que no encajen (p. ej. internacionales con nombre en coreano) se corrigen con una tabla pequeña en `kifumaster/paises.txt` (torneo → país), versionada.
- **Filtros en todo el archivo** (jugador con alias y color, dos jugadores, años, solo con SGF). Si hay algo elegido en el árbol, filtran dentro de ello; arriba "Meijin › 52nd ✕" para quitarlo. La lista dice "12 de 85" cuando hay filtro.
- **Por defecto se ven todas las partidas**; las que no tienen SGF, en gris y **sin acción** al tocarlas (Victor las baja con los `games_pendientes.txt`).
- **Fila**: `fecha  negras – blancas  resultado  [fase abreviada]`; en búsquedas por todo el archivo, también "torneo edición". Lo demás (sección, resultado largo, id) en tooltip (S Pen).
- **Visor**: el de Games completo, con análisis KataGo (AR0).
- Recuerda la última selección y los filtros; botón ⇄ entre `tsumevault.html` y `archive.html`; mismo servidor y token (misma origen: comparten `localStorage`).
- Móvil: lista y tablero en dos pantallas; portátil: lado a lado.

### AR3a — `js/board_core.js` y `js/ai_pure.js` (refactor sin cambios de comportamiento) · Dificultad Alta
Lo que el visor necesita de la página, medido con un parser de JS (cierre transitivo de dependencias):
- **Núcleo del tablero: 35 declaraciones, ~150 líneas, en ~10 sitios** de `tsumevault.html`: `wgoBoard`, `boardSize`, `initBoard`, `clearBoard`, `addLastMoveMark`, `moveQualityMark`, `switchToBoard`, `isMobilePortrait`, `buildStoneHandler`, `getImg`, `imgCache`, `pickVariant`, `currentBoardBg`, `currentStoneSet`, `BOARD_BG_KEY`, sonido (`STONE_SFX`, `playStoneSound`, `capturedAny`, `soundEnabled`, `sfxVolume`, `stoneSfxLast`, `SOUND_KEY`, `SFX_VOLUME_KEY` y el bloque «SFX: funciones puras» con `sfxPickIndex`), almacenamiento y servidor (`lsGet`, `lsSet`, `sgfUrl`, `SGF_BASE`, `syncFetch`, `SYNC_SERVER`, `SYNC_SERVER_KEY`, `SYNC_TOKEN_KEY`), IA (`aiPost`, `AI_OWN_HANDLER`) y `jsMarkInfo` (lo usa `moveQualityMark`).
- **Funciones puras de la IA: el bloque «IA3: funciones puras» entero** (58 funciones, ~550 líneas: `an*`, `aiToGtp`, `aiFromGtp`, `AI_COLS`…), que ya está diseñado para vivir aparte (sin DOM ni estado global) y no depende de nada de fuera.
- Ninguna de esas declaraciones necesita, al cargarse, nada que se quede en la página; así que `board_core.js` y `ai_pure.js` se cargan con `<script src>` **antes** de `game_viewer.js` y del script principal, igual que en AR0. Los ajustes (fondo, piedras, volumen) siguen en `localStorage` con las mismas claves, así que `archive.html` los hereda sin hacer nada.

**Garantía principal — reconstrucción byte a byte.** Cada bloque movido deja en la página una línea `// ⇢ js/board_core.js #N` y empieza en el `.js` con `// ⇠ #N (antes en tsumevault.html, …)`. Un script de test (`tests/page_source.py` y su gemelo `.js`) **reconstruye la página tal como era** sustituyendo cada marca por su bloque; se comprueba que el resultado es **idéntico byte a byte** al `tsumevault.html` anterior. Todos los extractores de tests (`extract_ai`, `extract_sfx`, `extract_joseki`, `extract_focus`, `test_joseki_problems_client`…) leen esa página reconstruida, así que sus bundles salen **idénticos** a los de antes y ninguna batería pierde cobertura (también las de josekis, que no se pueden correr en el contenedor).

Más comprobaciones: sin declaraciones duplicadas ni dependencias sin resolver (parser), ninguna declaración movida usa al cargar nada de la página (TDZ), `test_game_viewer.js` ampliado a los tres ficheros, línea base de todas las baterías igual antes y después, `node --check`, y prueba en Chrome sin interfaz de la página real antes/después (problemas, Games con análisis, Play, josekis, ajustes de sonido y tablero) con resultados idénticos y sin errores. Checklist manual en el móvil antes de seguir. Rama propia; nada de AR3b hasta que AR3a esté desplegada y probada.

**AR3a entregada (26-nov, rama `ar3a-board-core`)**: 93 declaraciones movidas en 18 bloques: `js/board_core.js` (183 líneas: el núcleo de 35 declaraciones más el bloque «SFX: funciones puras») y `js/ai_pure.js` (549 líneas: el bloque «IA3: funciones puras» entero); `tsumevault.html` pasa de 9.518 a 8.824 líneas. La herramienta de división verificó: cierre de dependencias, ninguna línea mezcla código que se va con código que se queda, sangría reversible y TDZ en el orden de carga. Validación: reconstrucción **idéntica byte a byte** (Python y JS, también con CRLF); los cinco bundles de los extractores (ai, focus, sfx, joseki, joseki_ui) **idénticos**; mismas cifras (server 344, ai 111, clock 80, focus 72, sfx 23, lp1 OK, game_viewer 28); nuevo `tests/test_page_split.js` (15 checks: orden de `<script>`, marcas ↔ bloques, nada duplicado, lo movido fuera de la página, carga en orden sin la página, núcleo con el WGo real) con 5 mutaciones que fallan; Chrome sin interfaz con la página real antes/después: siete pestañas, visor, tablero, ajustes y funciones de IA con resultados idénticos y sin errores de JavaScript. Los tests de josekis que necesitan fixtures no versionados (`test_joseki.js`, `test_joseki_problems_client.js`) hay que pasarlos en el portátil: leen la página reconstruida.

### AR3b — la página · Dificultad Media
- `archive.html` nueva: carga `wgo/*`, `board_core.js`, `ai_pure.js`, `game_viewer.js` y su propio script (árbol, filtros, lista, estado). No toca `tsumevault.html` salvo el botón ⇄.
- País por torneo: `kifu_build` añade `country` a `ar_tournaments` (idioma + `paises.txt`); `/archive/tree` lo devuelve y agrupa.
- Caché sin conexión: `/archive/tree` y las listas abiertas en IndexedDB; SGF ya vistos, en caché.
- `sw.js`: `archive.html`, `js/board_core.js`, `js/ai_pure.js` en `STATIC_ASSETS`.
- Tests: `tests/test_archive_page.js` (árbol y agrupación por país, filtros encadenados y "Meijin › 52nd ✕", construcción de la query, filas y tooltips, gris sin acción, estado recordado, caché sin conexión con fetch simulado) + prueba en Chrome sin interfaz contra un servidor local con el fixture de `test_archive_server.py`.
- Checklist manual M-AR3 (portátil y móvil): árbol por país, Meijin › 52nd › Preliminary B, buscar "瀬戸大樹" y "Seto Taiki", enfrentamientos, años, solo con SGF, abrir una partida con SGF y analizar, fila gris sin acción, modo avión, volver a `tsumevault.html`.

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
