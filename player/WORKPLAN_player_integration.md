# WORKPLAN — Integración del Go Lesson Player en el proyecto TsumeVault

## Contexto

Victor tiene un segundo HTML standalone (`player.html`) ya desarrollado, junto
con un servidor de guardado local (`player_save_server.py`), que sirve para
filtrar y reproducir "lecciones" (SGF + JSON de eventos + audio OGG +
subtítulos opcionales), con seguimiento de qué lecciones se han estudiado y
cuáles se han grabado como vídeo. Se quiere incorporar como un módulo más del
proyecto, sirviéndose desde el mismo dominio que TsumeVault
(`tsumevault.duckdns.org`).

## Decisiones ya tomadas (respuestas de Victor)

1. **Ubicación**: el Player se sirve desde el mismo dominio/servidor que
   TsumeVault.
2. **studied.json / recorded.json**: se mantienen en el servidor local
   (`player_save_server.py`, puerto 3001). Uso exclusivamente de escritorio —
   no se integra en `tsumevault_server.py`.
3. **Assets de lecciones (sgf/json/ogg)**: por ahora solo en local. No se
   suben al Hetzner en esta fase.

## Diagnóstico del código actual

- `player.html` hace fetch de rutas **relativas** a su propia ubicación:
  - `player/all_lessons.json`, `player/studied.json`, `player/recorded.json`
    (manifest y estado, en una subcarpeta `player/` junto al HTML).
  - `lessonDir()` construye `../lessons/{type}/{col}/{name}[/{suffix}]/` — un
    nivel **por encima** de donde vive `player.html`.
- Carga `wgo/wgo.min.js`, `wgo/sgfparser.js`, `wgo/kifu.js` — **la misma ruta
  relativa exacta** que ya usa `tsumevault.html`. Si `player.html` se coloca
  en el mismo directorio raíz estático que `tsumevault.html`, puede
  reutilizar la carpeta `wgo/` ya existente en el servidor, sin duplicarla.
- `saveToServer()` apunta a `http://localhost:3001/save` (hardcoded). Cuando
  `player.html` se sirva por HTTPS desde Hetzner, ese fetch fallará por
  mixed-content — pero ya está en un `try/catch` y tanto `studied` como
  `recorded` escriben primero en `localStorage`, así que el comportamiento
  se degrada exactamente como se quiere: en remoto/móvil queda marcado
  localmente; en local, con `player_save_server.py` corriendo, además se
  persiste a fichero. **No requiere cambios.**
- El grabador (MediaRecorder + `canvas.captureStream`) no depende del
  servidor local salvo para el bookkeeping de "grabada"
  (`saveRecorded()`); la exportación del `.webm` en sí funciona igual esté
  donde esté servido el HTML.
- `tsumevault_server.py` es puramente una API (404 en cualquier ruta no
  registrada en `GET_ROUTES`/`POST_ROUTES`) — el servido de estáticos
  (`tsumevault.html`, `wgo/`, SGF, audio) corre por otra vía (nginx u otro)
  que no está en el project knowledge. Confirmar con Victor dónde vive ese
  directorio raíz estático en el Hetzner.

## ESTADO: cambios aplicados (2026-08-27)

Estructura de carpetas confirmada por Victor: `player.html` en la raíz;
`lessons/` (antes en la raíz) pasa a vivir **dentro** de `player/`. Objetivo
inmediato: servir esto desde Hetzner solo para VER lecciones (sin grabación
remota, que sigue siendo flujo de escritorio con `player_save_server.py`).

Estructura final esperada en el servidor (junto a `tsumevault.html`):

```
<raíz estática del sitio>/
  tsumevault.html
  player.html
  wgo/                    ← REUTILIZADA, ya existe (compartida con tsumevault.html)
  img/icons/...           ← REUTILIZADA si ya existe
  player/
    all_lessons.json
    studied.json          (opcional; si no está, cae a localStorage)
    recorded.json          (opcional; si no está, cae a localStorage)
    lessons/
      {type}/{col}/{name}/[{suffix}/]{id}.sgf
                                          {id}.json
                                          {id}.ogg
                                          {id}_subtitles.json (opcional)
```

`player_save_server.py` sigue ejecutándose SOLO en local (Windows), apuntando
a la carpeta `player/` local de Victor — no se toca ni se sube al servidor.

### Cambios aplicados en `player.html` (diff mínimo, 5 puntos)

1. Nuevas constantes junto a las demás globales del script:
   ```js
   const PLAYER_DATA_BASE = 'player/';
   const LESSONS_BASE     = 'player/lessons/';
   ```
2. `lessonDir()`: `../lessons/...` → `${LESSONS_BASE}...`
3. `loadStudied()`: `fetch('player/studied.json')` → `fetch(PLAYER_DATA_BASE + 'studied.json')`
4. `loadRecorded()`: `fetch('player/recorded.json')` → `fetch(PLAYER_DATA_BASE + 'recorded.json')`
5. `loadLesson()` (las dos ramas): `fetch('player/all_lessons.json')` → `fetch(PLAYER_DATA_BASE + 'all_lessons.json')`

### Bug preexistente corregido de paso (no introducido por esta tarea)

`saveStudied()`/`saveRecorded()` llamaban a `saveToServer('player/studied.json', ...)`
y `saveToServer('player/recorded.json', ...)`. La whitelist de
`player_save_server.py` (`ALLOWED = {'study_stats.json','studied.json','recorded.json'}`)
solo acepta el nombre pelado, y `PLAYER_DIR` ya asume ser la carpeta `player/`
— con el prefijo, el guardado local devolvía 400 siempre y nunca escribía en
disco (silenciado por el `try/catch`). Corregido a `saveToServer('studied.json', ...)`
y `saveToServer('recorded.json', ...)`.

Verificado: `node --check` sobre el `<script>` extraído → sintaxis válida.
Sin restos de las rutas antiguas (`../lessons/`, `'player/all_lessons.json'`,
`'player/studied.json'`, `'player/recorded.json'` como argumentos de fetch).

Entregable: `/mnt/user-data/outputs/player.html`

### Pendiente para el despliegue real

- Reorganizar en local: mover `lessons/` dentro de `player/` (para que
  `player_save_server.py` y el uso local sigan funcionando igual, ya que su
  `PLAYER_DIR` y las rutas de guardado no dependen de `lessons/`).
- Subir a Hetzner: `player.html` + la carpeta `player/` completa (con
  `lessons/` anidada) a la raíz estática, junto a `tsumevault.html`.
- Confirmar que `wgo/` en el servidor sirve igual para ambos HTML (debería,
  misma ruta relativa `wgo/...`).
- El enlace "← Index" sigue apuntando a `index.html` — sin cambios, pendiente
  de decidir si debe existir o apuntar a otro sitio (fuera de alcance de este
  cambio).

### Persistencia de filtros en `lessons.html` (2026-08-27)

Problema: al filtrar en `lessons.html`, abrir una lección en `player.html` y
volver con el enlace "← Index", `lessons.html` se recarga desde cero y el
filtro se pierde (los `<select>` no persistían su valor entre cargas de
página).

Solución: los 5 filtros (`type`, `col`, `name`, `diff`, `studied`) se guardan
en `localStorage` (`go_lessons_filters`) cada vez que se aplican
(`applyFilters()`), y se restauran al cargar la página, antes del primer
render — así funciona igual venga la vuelta por el enlace, por una pestaña
nueva o por el botón "atrás" del navegador.

Cambios:
- Nueva clave `LS_FILTERS_KEY` + `saveFilters()`/`loadSavedFilters()`.
- `loadData()`: tras `buildFilters()`, restaura `type`/`diff`/`studied`
  directamente (si el valor guardado sigue existiendo entre las opciones), y
  pasa `col`/`name` guardados a `updateCollections(forceCol, forceName)`.
- `updateCollections()`/`updateNames()` aceptan un valor "forzado" opcional
  (`forceCol`/`forceName`), usado solo en la restauración inicial; todas las
  llamadas interactivas existentes (cambio de select, botón "Clear") siguen
  invocándolas sin argumentos y se comportan exactamente igual que antes.
- Un único punto de guardado, al inicio de `applyFilters()` — cubre cambios
  de cualquier select, "Clear" y la carga inicial, sin duplicar lógica.

Verificado: `node --check` sobre el `<script>` extraído → sintaxis válida.
Las llamadas existentes a `updateCollections()`/`updateNames()` sin
argumentos quedan intactas (comprobado por grep).

## Arquitectura: 2 páginas separadas (no fusionadas)

Victor tenía además un `index.html` (catálogo/tabla filtrable de lecciones,
para elegir una y abrirla en `player.html`) que no invocaba bien al player.
Se decidió **mantener 2 páginas** en lugar de fusionarlas en una sola:

- **`lessons.html`** (antes `index.html`, renombrado a petición): catálogo —
  tabla con filtros combinables (type/collection/name/diff/studied), orden
  por columna, chequeo de existencia de audio (`HEAD` sobre el `.ogg`),
  toggle de "estudiada" con export manual. Abre `player.html?id=…` en pestaña
  nueva al hacer clic en una fila.
- **`player.html`**: reproductor de una lección (por `?id=`, por sus propios
  desplegables, o en cola para grabar en lote). Tablero + audio + grabador.

Motivo: son layouts genuinamente distintos (tabla ancha vs. tablero+sidebar)
y el player ya carga bastante lógica propia (parser IGS, MediaRecorder);
fusionarlos complicaría el fichero para ahorrar solo "abrir una pestaña".

### Cambios aplicados en `lessons.html` (antes `index.html`)

1. Añadidas las mismas constantes que en `player.html`:
   ```js
   const PLAYER_DATA_BASE = 'player/';
   const LESSONS_BASE     = 'player/lessons/';
   ```
   `LESSONS_JSON`/`STUDIED_JSON` ahora se construyen a partir de
   `PLAYER_DATA_BASE` en vez de tener la ruta duplicada a mano.
2. **Bug corregido** — `lessonDir()` seguía usando `../lessons/...` (ruta
   antigua, de antes de mover `lessons/` dentro de `player/`): ahora usa
   `LESSONS_BASE`, igual que `player.html`. Sin este fix, la columna de
   estado (●/○, "¿existe el audio?") siempre daba "no" aunque el fichero
   existiera.
3. **Bug corregido** — al abrir una lección se hacía
   `new URL(PLAYER_URL, window.location.origin)`, que descarta cualquier
   subcarpeta (p. ej. `/tsumevault/`) y siempre construye la URL desde la
   raíz del dominio → 404 si `lessons.html`/`player.html` no viven en la
   raíz. Corregido a `new URL(PLAYER_URL, window.location.href)`.
4. **Explícitamente NO aplicado** (decisión de Victor): NO se añadió
   `saveToServer()` al marcar "estudiada" desde el catálogo. Sigue siendo
   solo `localStorage` + botón manual "↓ Save", igual que antes.

### Renombrado `index.html` → `lessons.html`

Única referencia externa encontrada y corregida: el enlace "← Index" en la
cabecera de `player.html` (`href="index.html"` → `href="lessons.html"`).
`index.html`/`lessons.html` no se autorreferenciaba en ningún sitio.

Verificado: `node --check` sobre el `<script>` extraído de ambos ficheros →
sintaxis válida en los dos. Sin restos de `index.html` ni de las rutas
antiguas en ninguno de los dos ficheros.

Entregables: `/mnt/user-data/outputs/player.html` (actualizado),
`/mnt/user-data/outputs/lessons.html` (nuevo, antes `index.html`).

### Pendiente para el despliegue

- Local: renombrar tu `index.html` a `lessons.html` en tu carpeta de trabajo
  (o sustituir por el fichero entregado).
- Subir `lessons.html` al servidor junto a `player.html` y `tsumevault.html`
  (misma raíz estática), además de lo ya pendiente de la tarea anterior
  (`player/` con `lessons/` anidada).

## Cambios propuestos en `player.html`

1. Sustituir las rutas hardcoded por dos constantes de configuración al
   inicio del script, siguiendo el mismo patrón que `SGF_BASE` en
   `tsumevault.html`:
   ```js
   const LESSONS_BASE = '../lessons/';   // pendiente de confirmar valor final
   const PLAYER_DATA_BASE = 'player/';   // manifest + studied/recorded
   ```
   Con los valores por defecto actuales, esto **no cambia nada** en
   funcionamiento; solo permite ajustar el despliegue sin tocar lógica si la
   estructura de carpetas en el Hetzner acaba siendo distinta a la de la
   máquina local de Victor.
2. Sin más cambios funcionales: el resto del fichero es autocontenido, no
   toca la base de datos de TsumeVault ni el protocolo de sync (SM-2,
   attempts, runs) — es un módulo independiente.
3. Opcional: el enlace "← Index" del header apunta a `index.html`. Confirmar
   si existe una página índice compartida en el servidor, o si debe apuntar
   a `tsumevault.html`, o retirarse.

## Pendiente de confirmación (antes de tocar código)

- **Estructura de carpetas actual en la máquina de Victor**: ¿dónde está
  `player.html` hoy respecto a la carpeta `player/` (datos) y respecto a
  `lessons/`? Con eso se fijan los valores exactos de las constantes.
- **Ruta de publicación deseada** en el Hetzner (p. ej.
  `tsumevault.duckdns.org/player.html` en la raíz, o
  `tsumevault.duckdns.org/go-player/player.html` en subcarpeta).
- **Convención CRLF**: `tsumevault.html`/`tsumevault_server.py` usan CRLF
  por convención del proyecto; `player.html` es un fichero nuevo e
  independiente — ¿se homogeneiza a CRLF o se deja con su terminación
  actual, dado que ninguna herramienta de extracción (`extract_bundle.py`)
  lo toca?

## Fuera de alcance por ahora

- Subida de los assets de lecciones (sgf/json/ogg) al Hetzner.
- Migración de `studied`/`recorded` a SQLite o al servidor remoto.
- Cambios en `tsumevault_server.py` o `tsumevault.html`.

## Siguiente paso

Con la estructura de carpetas confirmada, se aplica el cambio mínimo (las
dos constantes), se deja claro qué copiar al servidor y a qué ruta, y se
verifica en local antes de publicar.
