# kifumaster/ — herramientas del archivo de partidas

Plan completo: `docs/WORKPLAN_ARCHIVO.md`. Mientras el proceso no esté controlado, todo corre en el portátil de Victor (Windows); después, los mismos scripts pasan al VPS.

- Solo se descarga lo **público** de kifumaster.org: índice `seo/g`, mapa `seo/te`, CSV de `database/` y páginas de torneo/edición. Los SGF **no** (están tras App Check): Victor los baja a mano desde la web.
- Cortesía: una petición cada 5–10 s, de una en una, User-Agent identificable, se para ante 429/5xx, reanudable, respeta robots.txt (nada de `?step=`).
- `data/` no va a git (`.gitignore`). GitHub Pages tampoco publica `.py` ni `.md`.

## Scripts

| Script | Lanzador (raíz) | Qué hace |
|---|---|---|
| `kifu_probe.py` | `kifu_probe.bat` | AR1.0: baja 7 muestras a `data/probe/` y escribe `resumen.txt` (código, tamaño, tipo, si hay ETag/Last-Modified, nº de claves de los JSON). |
| `kifu_crawl.py` | `kifu_crawl.bat` | AR1: baja a `data/raw/` los 4 CSV y `seo/{te,t,ts,g}/00…ff.json` (1028 ficheros, ~2 h el primer ciclo). Reanudable; `--nuevo-ciclo` para buscar novedades (condicional por ETag: lo que no cambió no se baja); `--limite N` para pruebas. Log en `data/logs/`. |
| `kifu_build.py` | `kifu_build.bat` | AR1: construye `data/archive.db` y `data/lists/<torneo>/<edición>/games.txt` + `games_pendientes.txt` desde `data/raw/`, sin red. Se puede repetir cuando se quiera. |
| `kifu_upload.py` | `_subir_archivo.bat` | AR2: sube al VPS (`/opt/tsumevault/archive/`) los SGF nuevos de `archive/sgf/` y `data/archive.db` si cambió (huella sha256; sube como `.new` y sustituye con `mv`). Nunca borra nada. `--simular` para ver qué haría. |

## Qué es cada fichero de kifumaster

| Ruta | Contenido |
|---|---|
| `seo/g/xx.json` | índice: `id → {b, w, e (evento), d (fecha), r (resultado largo)}`; el reparto `xx` son las dos primeras cifras del id |
| `seo/te/xx.json` | evento → `torneo/edición` (`"52nd Meijin" → "meijin/52"`) |
| `seo/t/xx.json` | torneo: `n` nombre, `l` nombre local, `t` historia, `g` nº de partidas, `y` años, `s` ediciones `[{k etiqueta, u slug, n partidas, p jugadores, a desde, z hasta}]` |
| `seo/ts/xx.json` | edición: `c` secciones `[{a evento, g [[id, negras, blancas, fecha, resultado corto]], t [[fase, nº]]}]`. Las partidas de cada fase de `t` son bloques consecutivos al **final** de `g`, en ese orden; las primeras, la tabla principal |
| (otros eventos) | las partidas de eventos que kifumaster no organiza en torneos (~37 %) se agrupan por nombre en torneos `otros-…`: el ordinal o año del principio es la edición ("2nd Lanke Cup" → Lanke Cup / 2); sin evento, "Sin evento" por año |
| `database/*.csv` | alias de jugadores (`canonical,alias,script,nationality`), de eventos, de rangos (`九段 → 9p`) y familias de torneos |

## Estructura de `data/`

```
data/
  probe/       muestras de AR1.0
  raw/         copia tal cual de lo descargado (para rehacer el catálogo sin volver a pedir nada)
  archive.db   catálogo
  lists/       games.txt y games_pendientes.txt por edición
  logs/
```
