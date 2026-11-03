# WORKPLAN FC1 — Focus: servidor (migración v5 + sincronización)

Estado: **CERRADA** (3-nov-2026). `run_all.sh` → `✔ TODO OK`.

## Requisito

Base de servidor para la sección Focus (REQUISITOS_FOCUS.md + decisiones técnicas del 3-nov):
tablas de Focus, vínculo intento → sesión y sincronización LWW. Sin cambios en el cliente.

## Cambios (`tsumevault_server.py`)

| Zona | Cambio |
|---|---|
| Docstring de cabecera | Endpoints FC1 listados. |
| `_migrate_v4_joseki` | Encadena `_migrate_v5_focus(con)` al final. |
| `_migrate_v5_focus` (nueva) | `attempts.session_uuid` (+ índice parcial `idx_attempts_session`); tablas `focus`, `focus_chapters`, `focus_sessions` con índice por `updated_at`; sella `user_version = 5`. Idempotente. |
| `migrate_db` | `version >= 5` → nada; `version >= 4` → solo v5. |
| `handle_sync_push` | Valida `session_uuid` opcional (texto 1–64) y lo guarda al insertar el attempt. `/sync/pull` lo devuelve sin cambios (`SELECT a.*`). |
| `_FOCUS_TABLES`, `_focus_validate`, `handle_sync_focus_pull`, `handle_sync_focus_push` (nuevas) | `GET /sync/focus/pull?since=ISO` (`>=`, como sm2/tags) y `POST /sync/focus/push` (LWW estricto por `updated_at`; valida TODO el payload antes de escribir; nombre normalizado, máx. 60). |
| `GET_ROUTES` / `POST_ROUTES` | Rutas FC1 registradas. |

### Esquema v5

```
focus          (uuid PK, name, archived 0/1, deleted 0/1, created_at, updated_at)
focus_chapters (focus_uuid, chapter_id, promoted 0/1, active 0/1, updated_at, PK(focus_uuid, chapter_id))
focus_sessions (uuid PK, focus_uuid, started_at, ended_at NULL, completed 0/1, updated_at)
attempts.session_uuid TEXT NULL
```

Nunca se borran filas: `deleted`, `archived` y `active` son flags que viajan por LWW.
El servidor no impone reglas de negocio (un capítulo en un solo Focus, nombre único, etc.): las aplica el cliente.

## Tests (`test_server.py`, entrega completa)

- Fase A: 22 tests FC1 (migración legacy, push/pull, LWW en ambos sentidos, frontera `>=`,
  8 casos de 400, atomicidad de la validación, Origin ajeno 403, `session_uuid` en push/pull,
  cliente antiguo sin `session_uuid`). Limpieza al final del bloque.
- `user_version` esperado 4 → 5 (Fase A y Fase D, igual que se hizo en J2 al pasar de 3 a 4).
- Fase E nueva (5 tests): BD en v4 sin tablas Focus ni columna → migra a v5 sin tocar datos; rearranque idempotente.

## Validación

```
línea base (sin cambios):  servidor 153 | cliente 150 | compat 8  ✔ TODO OK
tras FC1:                  servidor 180 | cliente 150 | compat 8  ✔ TODO OK
```

- `tsumevault.html` y `harness_bundle.js`: byte-idénticos a la línea base.
- Finales de línea: `tsumevault_server.py` y `test_server.py` se recibieron en **LF** y se entregan en LF.
- Prueba adicional sobre `schema_real.sql` (BD de producción simulada en v4): migra a v5 sin pérdida.

## Despliegue

Al arrancar, el servidor migra la BD de producción de v4 a v5 automáticamente. Hacer copia antes
(`sqlite3 tsumeVault.db ".backup tsumeVault_pre_fc1.db"`). Un cliente actual sigue funcionando igual:
no envía `session_uuid` ni llama a `/sync/focus/*`.

## Siguiente

FC2 — cliente, capa de datos y sync (única tarea que toca la zona crítica de sync).
