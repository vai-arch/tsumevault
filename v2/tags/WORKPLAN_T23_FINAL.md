# WORKPLAN T23 — Etiquetas (tags) de problemas — ✅ COMPLETADA

## Requisito
Dominio global de etiquetas (gestionado en ⚙), asignación de una o varias a cada
problema desde Run o Free (sin parar el cronómetro), filtro en Free por etiquetas
(OR entre las marcadas, AND con el resto de filtros). Sincronización entre
dispositivos, offline-first.

## Validación final
- `bash run_all.sh` → **servidor: 108 PASS | cliente: 132 PASS | compat: 8 PASS · ✔ TODO OK**
  (baseline previa 88/113/8; +20 servidor, +19 cliente).
- `python3 extract_tags.py && node test_tags.js` → **23 PASS · TODO OK** (batería nueva, aparte).
- CRLF: `tsumevault.html` 6045 líneas CRLF / 0 LF; `tsumevault_server.py` 2260 CRLF / 0 LF.
- `harness_bundle.js` vs baseline: diff puramente aditivo (93 líneas `>`, todas T23) en
  `createSchema`, `migrateSyncColumns` y `doSync`. Fases F3–F6 dejaron el bundle byte-idéntico.

⚠ Las subidas de esta sesión llegaron en LF (0 `\r`). Se convirtieron con
`sed -i 's/$/\r/'`. Los entregables son CRLF. Comprueba tu copia local antes de
sobrescribir (`python3 -c "print(open('tsumevault.html','rb').read().count(b'\r'))"`).

## Modelo de datos
Servidor (schema v3, `_migrate_v3_tags`, `user_version=3`):
- `tags(tag TEXT PK COLLATE NOCASE, created_at)`
- `problem_tags(source, problem_id TEXT, tag COLLATE NOCASE, active 0/1, updated_at, PK(source,problem_id,tag))` + `idx_problem_tags_updated`
Cliente: idéntico + columna `synced` en ambas (0 pendiente / 1 confirmado por servidor).
`active=0` = tombstone: propaga la retirada de una etiqueta (LWW por `updated_at`, como sm2_state).

## Endpoints (servidor)
- `PUT /sync/tags {tags:[..]}` → unión; responde `{tags:[lista completa], added}`.
- `POST /sync/tags/delete {tag}` → 409 `{in_use:N}` si hay asignaciones activas; si no, borra tag + sus tombstones.
- `GET /sync/problem_tags/pull?since=` → filas con `updated_at >= since`.
- `POST /sync/problem_tags/push {problem_tags:[..]}` → LWW; ignora problems inexistentes; auto-crea el tag si falta.
- `GET /db/audit`: checks nuevos `T23a` (tag huérfano, ERROR), `T23b` (problem inexistente, WARNING), `T23c` (active∉{0,1}, ERROR).

## Cambios exactos — cliente `tsumevault.html`
- CSS `.tag-chip` / `.tag-x` (antes de `.cfg-section-title`).
- HTML: sección "Etiquetas (tags)" en el modal ⚙ (antes de `<!-- CACHE SGF -->`); fila
  `Tags` + `#pi-tags-editor` en `#prob-info`; sección `Tags` (`#fp-tags-list`, Clear) en la
  pestaña Free tras "Problem ID".
- `createSchema()` y final de `migrateSyncColumns()`: DDL de `tags`/`problem_tags`.
- `doSync()`: bloque `// ── T23: Sync etiquetas ──` entre el bloque T13 y SM-2.
  Dominio: push SOLO `synced=0` (push completo resucitaba en el servidor un tag borrado
  desde otro dispositivo — bug cazado por el harness); respuesta = verdad (borra
  confirmados ausentes, crea faltantes). Asignaciones: pull por cursor `last_tags_sync`
  (sync_meta, vía `cursorUpdates`, atómico con `saveDB`); push `WHERE synced=0` (no depende
  del reloj del cliente, a diferencia de sm2); marca `synced=1` solo la fila enviada (misma
  `updated_at`); el cursor solo avanza si el push tuvo éxito.
- API local (antes de `localGetProblem`): `normTag`, `localGetTags`, `localAddTag`,
  `localTagInUse`, `localGetProblemTags`, `localSetProblemTag` (updated_at estrictamente
  creciente por fila: dos toggles en el mismo segundo no se pierden en el LWW).
  `localGetProblems` acepta `tags` (EXISTS … IN).
- UI ⚙ (antes de `openConfig`): `refreshTagViews`, `renderCfgTags`, `cfgAddTag`,
  `cfgDeleteTag` (bloqueo local si en uso; borrado en servidor primero si el tag está
  confirmado; requiere conexión). Bind en `openConfig` con `dataset.bound`.
- Sidebar: `renderProblemTags`, `renderProblemTagEditor`, `toggleProblemTag`; llamada en
  `renderProblem` tras `pi-color`; reset en `clearSidebar`. Editor se cierra al cambiar de problema.
- Free: `renderFreeTagList` (conserva lo marcado), bind Clear en `populateFreeFilters`,
  `tagSel` → `localGetProblems({tags})` en `startFreePractice`; el botón 🧩 de Collections
  también limpia las tags marcadas. El botón ↻ Sync manual llama a `refreshTagViews()`.

## Cambios — servidor `tsumevault_server.py`
`_migrate_v3_tags` (encadenada desde `_migrate_v2_hidden`; guard `>=3`, `==2`→v3),
`_norm_tag`, 4 handlers antes de `GET_ROUTES`, rutas, bloque `[TAGS]` en `run_audit`.

## Tests añadidos
- `test_server.py`: bloque T23 (17 checks) antes del test de JSON malformado, con limpieza;
  `uv==3` (avance legítimo, como T13 hizo con 2); 3 checks de audit en Fase C.
- `harness.js`: escenario T23 (19 checks): 2 dispositivos, tombstone LWW en ambos sentidos,
  cambio local más antiguo que no gana, offline→reconexión, unión de dominio, borrado
  propagado, tag creado en mitad del vuelo no se pierde, sin re-push, cursor.
- `extract_tags.py` + `test_tags.js` (23 checks): API local y filtro.

## Limitaciones / fuera de alcance (anotadas, NO arregladas)
- Renombrar un tag = crear nuevo + reasignar + borrar viejo (decisión: clave = texto).
- Un tag borrado en el servidor puede "resucitar" si otro dispositivo tenía asignaciones
  offline con él (el push las auto-crea): seguro (sin pérdida), documentado.
- LWW depende del reloj del cliente para *ordenar* conflictos entre dispositivos (igual
  que sm2_state); el *envío* ya no depende del reloj (flag `synced`).
- `tags`/`problem_tags` no viajan en el snapshot estático; `importSnapshot` no las toca.
- Sin tags en Runs/Collections/lista lateral de Free ni "crear run desde tag" (T23-b futuro).
- No se ha podido probar la UI en navegador en este entorno (sin browser): la lógica
  DOM está fuera del harness. Recomendado: abrir ⚙, crear 2 tags, asignar desde un Run y
  desde Free, filtrar en Free, sincronizar desde un segundo dispositivo.
- `INSTRUCCIONES_DELEGACION.md` entregado con la baseline actualizada (108/132/8) y la
  batería `extract_tags.py`/`test_tags.js` en el mapa de archivos.
