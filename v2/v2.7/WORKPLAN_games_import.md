# WORKPLAN — Importación de games/game_collections (T-games-1)

## Requisito
Poder cargar `game_collections`/`games` en TsumeVault desde la carpeta `games/`
en disco, con soporte para que las colecciones o partidas eliminadas en disco
desaparezcan también del servidor y de los clientes (no solo aditivo).

## Hallazgo previo (antes de tocar nada)
La infraestructura ya existía parcialmente:
- Servidor: `POST /admin/import_games` y `GET /sync/games` ya estaban
  implementados y enrutados, pero eran **aditivos** (insertar-si-no-existe,
  nunca borraban).
- Cliente: `doSync` ya llamaba a `/sync/games` en cada sync no-light y hacía
  `INSERT OR IGNORE` local — también aditivo.
- El visor de partidas (games viewer) ya existía y funcionaba sobre esas
  tablas.
- Lo único que faltaba de verdad era el script que escanea `games/` y habla
  con el servidor.
- Comprobado en `db_schema.sql` y en el esquema local del cliente: ninguna
  otra tabla referencia `games`/`game_collections` → reemplazo completo es
  seguro (no deja huérfanos).
- `handle_admin_import_games` no la llama nadie más que este script nuevo →
  cambiar su semántica no rompe otros consumidores.

## Cambios realizados

### 1. `import_games.py` (NUEVO, no existía)
Script standalone. Escanea `games/<coleccion>/*.sgf` y hace
`POST /admin/import_games` con el listado completo. Reemplaza al script
antiguo que escribía SQLite directamente (`import_games(con)`).
- `--server-url` (o `TSUMEVAULT_SERVER_URL`), por defecto `http://localhost:3002`.
- `--games-dir`, por defecto `games/` junto al script.
- `--dry-run` para inspeccionar el payload sin tocar el servidor.
- Envía `X-Auth-Token` solo si `TSUMEVAULT_TOKEN` está definida (hoy no lo
  está en producción, según lo confirmado).
- Si `games/` no existe o está vacía, aborta sin tocar el servidor.

### 2. `tsumevault_server.py` — `handle_admin_import_games` (línea ~758)
Cambiado de "insertar si no existe" a **reemplazo transaccional completo**:
`DELETE FROM games` → `DELETE FROM game_collections` → insertar lo recibido.
Orden de borrado respeta `PRAGMA foreign_keys=ON`. Añadida validación de
payload (400 si `game_collections`/`games` no son listas o faltan campos).
Las partidas cuya `collection_name` no está en el mismo payload se cuentan en
`skipped_games` (no rompen el import).
Respuesta: `{"collections": N, "games": N, "skipped_games": M}` (antes
`inserted_collections`/`inserted_games`).

### 3. `tsumevault.html` — bloque `// ── Sync games ──` dentro de `doSync` (línea ~2665)
Cambiado de `INSERT OR IGNORE` (aditivo) a `DELETE` + `INSERT` (reemplazo
completo), dentro del mismo ciclo de sync normal — sin flujo ni botón nuevo.
El `DELETE` solo se ejecuta si la petición a `/sync/games` tuvo éxito.
Zona de sync crítica: diff de `harness_bundle.js` revisado, contiene
exactamente este cambio y nada más.

### 4. Tests nuevos (ninguno existente se ha tocado ni debilitado)
- `test_server.py` — sección "FASE C": import inicial, re-import con
  reemplazo (colección eliminada, partida sustituida), partida con colección
  huérfana (`skipped_games`), validaciones 400.
- `harness.js` — "Escenario G1": mismo flujo pero a través del cliente real
  (`doSync`/`tryAutoSync`), verificando que el reemplazo se propaga a la DB
  local. **Nota de depuración**: `lightMode` en `doSync(lightMode)` es en
  realidad el parámetro `silent` de `tryAutoSync` reenviado tal cual — todos
  los escenarios previos llaman `tryAutoSync(true)` (modo silencioso), lo que
  de paso saltaba siempre el bloque de sync de games. Por eso no tenía
  cobertura. El escenario G1 usa `tryAutoSync(false)` a propósito.

## Validación
`bash run_all.sh` ejecutado dos veces (para descartar flakiness):

```
servidor: 50 PASS (antes 35, +15)
cliente:  90 PASS (antes 82, +8)
compat:    8 PASS (sin cambios — no toca games)
✔ TODO OK
```

También validado manualmente end-to-end fuera de la batería: servidor real +
`import_games.py` contra una carpeta `games/` de prueba con 2 colecciones/3
SGFs, comprobando inserción inicial, reemplazo (colección eliminada + partida
nueva), `--dry-run`, y carpeta inexistente (no toca nada).

## Limitaciones / cosas a tener en cuenta
- El reemplazo completo significa que los `id` de `game_collections`/`games`
  **no son estables** entre imports (autoincrement sigue subiendo). Confirmado
  que nada depende de esos ids permanecer, pero si en el futuro se añade algo
  que sí dependa (favoritos, notas por partida), habría que revisar esto.
- Si el cliente está offline mucho tiempo y mientras tanto se borra una
  colección en el servidor, el primer sync tras reconectar la eliminará
  también localmente sin aviso — es el comportamiento esperado (espejo de
  solo lectura), pero queda anotado por si se quiere un aviso visual en el
  futuro.
- No se ha tocado `run_all.sh`, `extract_bundle.py`, `db_schema.sql` ni
  `harness_bundle_old.js`, según las prohibiciones expresas.

## Cómo ejecutar el script en producción
```bash
# En el Hetzner, junto a tsumevault_server.py:
python3 import_games.py
# o, si el server corre en otro host/puerto:
python3 import_games.py --server-url http://mi-servidor:PUERTO
```
