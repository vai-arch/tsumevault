# TsumeVault

Aplicación personal para estudiar problemas de Go (tsumego) con repaso espaciado SM-2,
jugar contra la IA y repasar lecciones y josekis. Web: GitHub Pages; servidor: VPS de Hetzner.

## Dónde está cada cosa

| Carpeta / fichero | Qué es |
|---|---|
| `tsumevault.html`, `player.html`, `lessons.html`, `sw.js`, `manifest.json` | La app web (GitHub Pages la publica tal cual) |
| `*.bat` | Panel de mandos en Windows: subir, bajar, desplegar, importar. Se lanzan desde la raíz (`.\_subir_git.bat`) |
| `server/` | Espejo de `/opt/tsumevault` en el VPS: `tsumevault_server.py`, `ai_engines.py` (+ `ai_engines.json`, `fuego_tv.cfg`), `Caddyfile`, `db_schema.sql` y la BD `tsumeVault.db` |
| `tests/` | Baterías de pruebas (`test_*.py`, `test_*.js`), extractores de bundles y el motor falso `fake_gtp.py` |
| `tools/` | Scripts de importación (`import_*.py`, `generate_joseki_problems.py`, `sgf_lib.py`, `joseki_lib.py`) y de mantenimiento de la BD (`recalc_sm2.py`, `repair_t21.py`, `fix_*.py`, …) |
| `docs/` | Documentos de trabajo y planes (`WORKPLAN_IA.md`, …). Los requisitos pendientes están en Notion |
| `101_weiqi/`, `go_problems/`, `my_collections/`, `games/`, `joseki/`, … | Datos: problemas, partidas y josekis |
| `audio/`, `img/`, `wgo/`, `player/` | Recursos de la web |
| `_sources_scripts/` | Scripts de descarga y conversión de cada fuente (no se publica) |

## Pruebas

Desde la raíz:

```
python tests/test_server.py
python tests/extract_ai.py && node tests/test_ai.js && node tests/test_clock.js
```
