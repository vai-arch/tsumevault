# kifumaster/ — herramientas del archivo de partidas

Plan completo: `docs/WORKPLAN_ARCHIVO.md`. Mientras el proceso no esté controlado, todo corre en el portátil de Victor (Windows); después, los mismos scripts pasan al VPS.

- Solo se descarga lo **público** de kifumaster.org: índice `seo/g`, mapa `seo/te`, CSV de `database/` y páginas de torneo/edición. Los SGF **no** (están tras App Check): Victor los baja a mano desde la web.
- Cortesía: una petición cada 5–10 s, de una en una, User-Agent identificable, se para ante 429/5xx, reanudable, respeta robots.txt (nada de `?step=`).
- `data/` no va a git (`.gitignore`). GitHub Pages tampoco publica `.py` ni `.md`.

## Scripts

| Script | Lanzador (raíz) | Qué hace |
|---|---|---|
| `kifu_probe.py` | `kifu_probe.bat` | AR1.0: baja 7 muestras a `data/probe/` y escribe `resumen.txt` (código, tamaño, tipo, si hay ETag/Last-Modified, nº de claves de los JSON). |

## Estructura de `data/`

```
data/
  probe/       muestras de AR1.0
  raw/         copia tal cual de lo descargado (para rehacer el catálogo sin volver a pedir nada)
  archive.db   catálogo
  logs/
```
