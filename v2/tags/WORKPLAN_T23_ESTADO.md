# ESTADO — Etiquetas de problemas (T23) — ✅ TAREA COMPLETADA (ver WORKPLAN_T23_FINAL.md)

Si la sesión se corta, retomar desde la primera fase NO marcada ✅. Los ficheros
modificados hasta el último checkpoint están en /mnt/user-data/outputs/.
Entorno de trabajo: /home/claude/w (copia de /mnt/project + tsumevault.html +
tsumevault_server.py convertidos a CRLF con `sed -i 's/$/\r/'` porque las subidas
llegaron en LF). Bundle de referencia: /tmp/baseline_bundle.js (regenerable: F0).

## Decisiones cerradas con Victor
- Dominio de tags GLOBAL (todas las fuentes). Clave = texto del tag (case-insensitive).
  Solo nombre. Empieza vacío. Borrar tag del dominio: BLOQUEADO si tiene asignaciones
  activas; borrar solo con conexión (endpoint). Crear tag: offline OK (unión).
- Asignaciones: tabla `problem_tags(source, problem_id, tag, active 0/1, updated_at)`,
  LWW por fila por `updated_at` (patrón sm2_state), cursor `last_tags_sync` en sync_meta.
- Solo sync incremental; snapshot/importSnapshot NO tocan tags.
- UI: gestión del dominio en el modal ⚙ (sección nueva); asignación desde el sidebar
  #prob-info (Run y Free, en cualquier momento, sin parar cronómetro); filtro en Free
  por checklist de tags, OR entre tags, AND con el resto de filtros; sin "sin etiqueta".
- Fuera de alcance: tags en Runs/Collections/lista lateral, crear run desde tag.
- Audit: checks T23 (tag huérfano, asignación a problem inexistente, active fuera 0/1).
- Tests locales de funciones fuera del perímetro: extract_tags.py + test_tags.js (patrón F10).

## F0 ✅ Baseline: 88/113/8 ✔ TODO OK.
## F1 ✅ Esquema (validado junto a F2: 105/132/8 ✔)
- Servidor: `_migrate_v3_tags(con)` (tags, problem_tags, idx) encadenada desde `_migrate_v2_hidden`; guard `>=3`, `==2` aplica solo v3. test_server espera `uv==3`.
- Cliente: `createSchema()` + bloque idempotente al final de `migrateSyncColumns()` (cubre IndexedDB y fallback). Cliente añade columna `synced` en tags y problem_tags (no existe en servidor).
## F2 ✅ Sync (validado 105/132/8 ✔)
- Servidor: `_norm_tag`, `handle_sync_tags` (PUT, unión, responde lista completa), `handle_sync_tags_delete` (POST, 409 si active=1), `handle_sync_problem_tags_pull` (GET since >=), `handle_sync_problem_tags_push` (POST, LWW, ignora problem inexistente, auto-crea tag). Rutas añadidas.
- Cliente: bloque `// ── T23: Sync etiquetas ──` en doSync entre T13 y SM-2. Dominio: push SOLO synced=0 (push completo resucitaba tags borrados — bug cazado por harness), respuesta = verdad (borra confirmados ausentes, crea faltantes). Asignaciones: pull por cursor `last_tags_sync` (sync_meta, via cursorUpdates), push WHERE synced=0 (no depende del reloj), marca synced=1 solo la fila enviada (misma updated_at).
- Tests: 17 en test_server (bloque T23 antes del test de JSON malformado, con limpieza) y 19 en harness (escenario T23 al final).
## F3 ✅ API local (test_tags.js 27 PASS; bundle de sync intacto respecto a F2)
- `normTag`, `localGetTags`, `localAddTag`, `localTagInUse`, `localGetProblemTags`, `localSetProblemTag` justo antes de `localGetProblem`. `localGetProblems` acepta `tags` (EXISTS ... IN, OR entre tags).
- Nuevos ficheros `extract_tags.py` + `test_tags.js` (patrón F10; fuera de run_all.sh): `python3 extract_tags.py && node test_tags.js`.
## F4 ✅ UI ⚙ gestión de tags (bundle intacto): CSS .tag-chip, sección "Etiquetas" antes de CACHE SGF, JS refreshTagViews/renderCfgTags/cfgAddTag/cfgDeleteTag antes de openConfig, bind en openConfig. F5 ✅ UI sidebar (bundle intacto): fila Tags + #pi-tags-editor en #prob-info; JS renderProblemTags/renderProblemTagEditor/toggleProblemTag antes de openConfig; llamada en renderProblem tras pi-color y reset en clearSidebar. F6 ✅ Filtro Free (bundle intacto): sección Tags tras Problem ID, renderFreeTagList tras populateFreeFilters (bind Clear con dataset.bound), tagSel en startFreePractice, reset en el botón 🧩 de Collections. F7 ⬜ Audit checks + WORKPLAN final.
