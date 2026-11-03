# WORKPLAN FC2 — Focus: cliente, capa de datos y sync

Estado: **CERRADA** (3-nov-2026). `run_all.sh` → `✔ TODO OK`; batería aislada `test_focus.js` → `TODO OK`.

## Requisito

Capa de datos local de la sección Focus (sin UI todavía) y su sincronización con los
endpoints de FC1. Única tarea del plan que toca la zona crítica de sync.

## Cambios (`tsumevault.html`)

### Zona de sync (extraída por `extract_bundle.py`)

| Función | Cambio |
|---|---|
| `migrateSyncColumns` | `attempts.session_uuid` + tablas `focus`, `focus_chapters`, `focus_sessions` (con `synced`) + índice parcial. Idempotente. |
| `createSchema` | Mismo DDL para instalaciones nuevas. |
| `localInsertAttempt` | 6.º parámetro opcional `session_uuid` (los llamantes actuales no cambian → NULL). |
| `doSync` (pull de attempts) | Guarda `a.session_uuid`. El push ya lo enviaba (`SELECT a.*`). |
| `doSync` (bloque nuevo FC2, antes de SM-2) | Pull **completo** de las tres tablas (sin cursor), LWW por `updated_at` estrictamente mayor; push de `synced=0`; confirmación solo de las filas enviadas (misma `updated_at`). Servidor antiguo (404) → no-op. |

**Decisión: sin cursor.** Con un cursor por `updated_at` (como en etiquetas), una fila creada
offline en otro dispositivo con fecha anterior al cursor ya alcanzado no se recibiría nunca.
Las tablas de Focus son pequeñas, así que el pull completo es barato y elimina ese riesgo.
No se usa `sync_meta`.

No se tocan: `countPendingSync`, cursores, `sync_meta`, ningún otro bloque de sync.

### API local nueva (fuera de la zona de sync, antes de `localGetProblem`)

- Helpers: `focusNorm`, `focusStamp` (updated_at estrictamente creciente), `focusTouch`, `focusSetChapterRow`, `focusPct`, `focusFirstAttempts`.
- Focus: `localFocusGet`, `localFocusList(includeArchived)`, `localFocusNameTaken`, `localFocusCreate`, `localFocusRename`, `localFocusDelete` (solo sin sesiones; libera capítulos), `localFocusArchiveCheck`, `localFocusArchive` (bloquea con *ready*; libera *work*; conserva *promoted*), `localFocusReopen`.
- Capítulos: `localFocusOfChapter`, `localFocusChapterMap` (para Colecciones), `localFocusAddChapter`, `localFocusRemoveChapter`, `localFocusSetPromoted` (activa `show` al promocionar), `localFocusChapters` (estado calculado + `missing`).
- Estado calculado: `localChapterHasCompletedRun` (Run `type='chapter'` del propio capítulo, con run_items y ninguno sin resultado), `focusChapterState` → `work` / `ready` / `promoted`.
- Sesiones: `localFocusSessionProblems` (visibles de los *work* existentes, aleatorio), `localFocusSessionStart`, `localFocusSessionComplete`, `localFocusSessionStats`, `localFocusProgress` (última sesión completada; por capítulo, la última que lo incluyó), `localFocusTodayStatus` (pendiente = hay *work* con problemas y ninguna sesión completada hoy, día local).

Las funciones de escritura devuelven `{ ok: true, ... }` o `{ error: '<código>' }`
(`invalid`, `duplicate`, `missing`, `has_sessions`, `not_active`, `no_chapter`, `in_focus`,
`not_member`, `ready`, `not_archived`).

## Tests

- `harness.js` (entrega completa): escenario FC2 con 18 comprobaciones — `session_uuid` en
  `localInsertAttempt`, push/pull de las tres tablas, segundo sync sin re-push, segundo
  dispositivo, LWW en ambos sentidos, pull completo (fila antigua recién llegada), offline y
  reconexión, cambio en mitad del vuelo, migración local de instalación existente e idempotencia.
- `extract_focus.py` + `test_focus.js` (nuevos, batería aislada como la de etiquetas):
  53 comprobaciones de la API local. Uso: `python3 extract_focus.py && node test_focus.js`.

## Validación

```
tras FC1:  servidor 180 | cliente 150 | compat 8   ✔ TODO OK
tras FC2:  servidor 180 | cliente 168 | compat 8   ✔ TODO OK
test_focus.js: 53 PASS — TODO OK
```

- `tsumevault.html` en CRLF (7.4k líneas, 0 LF sueltos).
- Diff de `harness_bundle.js` revisado: solo migración, esquema, `localInsertAttempt`, pull de attempts y bloque de sync de Focus.

## Despliegue

Se puede publicar ya: sin UI, el cliente solo sincroniza tablas vacías. Requiere el servidor de FC1.

## Observación fuera de alcance (no tocada)

El sync de etiquetas (T23) usa cursor por `updated_at` de cliente: una asignación hecha offline
en otro dispositivo con fecha anterior al cursor ya alcanzado podría no llegar nunca. Riesgo bajo
(pocas etiquetas, poco uso offline); si interesa, se arregla igual que aquí (pull completo).

## Siguiente

FC3 — UI: la pestaña Runs pasa a un modal (🗂) y `startRun` deja de cambiar de pestaña.
