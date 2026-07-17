# WORKPLAN T8–T12 — Ejecución por el arquitecto

Si la sesión se corta, retomar desde la primera tarea NO marcada [x].
Specs completas: TAREAS.md. Directorio: /home/claude/tsumevault.
Si el contenedor se reseteó: archivos más recientes en /mnt/user-data/outputs.
Línea base confirmada: 32/69/8 ✔ TODO OK. md5 html inicial: 6989b957.
Checkpoint a outputs tras cada tarea (html/servidor + este archivo + kit si cambió).

## Estado
- [x] T8 — 3.12b: (A) bare columns GROUP BY→estándar con compare_queries.{js};
      (B) AE en getSetupStones. Solo tras compare en verde se sustituye.
- [x] T9 — sync_meta: tabla en DB cliente (createSchema + migración con import
      único desde localStorage), helpers get/setSyncMeta, doSync lee de
      sync_meta y escribe ANTES del saveDB final (atómico con datos), eliminar
      bloque post-saveDB de localStorage. Guards de tabla vacía se CONSERVAN.
      Adaptar E4 y E13 del arnés (cursores vía DB) + escenario E15 (migración
      desde localStorage sin re-descarga completa). sync_token/sync_server_url/
      static_version SIGUEN en localStorage.
- [x] T10 — R11: esc() + inventario exhaustivo de innerHTML (clasificar a/b/c),
      envolver datos de DB en las 6 funciones citadas y demás casos (a);
      check_esc.js verificador.
- [x] T11 — servidor: (A) PRAGMA user_version=1 gate de migraciones idempotentes;
      (B) SIGTERM/SIGINT → shutdown desde thread aparte + server_close (probar
      manual); (C) sgf_path: validar SOLO si toca filesystem, si no documentar;
      (D) int() de query params → 400 (reutilizar mecanismo de validación
      existente). Tests nuevos en test_server.py: user_version==1 y
      since_attempt_id=abc→400.
- [x] T12 — R12/P3: localGetStruggling en UNA query window function (verificar
      soporte en sql.js primero). Semántica extraída del código real; el caller
      usa Set → comparar como conjuntos. compare_struggling.js con casos límite
      (solo aciertos, solo fallos, mezclas, empates de created_at, <n intentos).
      handle_get_struggling del servidor solo si es el mismo patrón mecánico.
- [x] Cierre: IMPLEMENTATION_STATUS.md, run_all final, entrega completa.

## Notas acumuladas
(rellenar al avanzar)

- T8: 6 queries reescritas (cliente: 3 con rn=1; servidor: 2 con MAX(id) directo + 1 con rn=1); compare_queries.js 6/6 PASS (orden irrelevante: callers indexan por clave en bucles). AE en getSetupStones simetrico a AB/AW (rama properties; la rama node.setup ya venia resuelta por WGo). Ejemplo SGF: (;AB[ab][cd]AW[ef]AE[ab]) => black=[cd], white=[ef].

- T9: sync_meta con helpers get/setSyncMeta; migrateSyncMeta con import unico desde localStorage SOLO si la tabla no existia (createSchema la crea en frescos sin importar); doSync lee de sync_meta y escribe cursorUpdates ANTES de saveDB (atomico); bloque post-saveDB eliminado; localStorage intacto como fallback de downgrade; guards de tabla vacia conservados. E4/E8/E13 adaptados + E15 (migracion sin re-descarga). Suite 32/73/8 OK.

- T10: esc() junto a makeUUID; aplicado en renderCollectionsList (col.name, diffStr, e.message), renderChapterList (chap.name, diffStr), loadRuns (run.label, run.status, date), renderStatsTable (r.source, r.collection_name), renderByLevel (source en celda + ids bylevel-cov/hist/last/tot y selId con lookups coherentes), renderGlobalPending (source). gm list ya usaba textContent (sin cambios). check_esc.js verificador en verde (cazo un ${source} olvidado en bylevel-tot: util real). Suite 32/73/8 OK.

- T11: (A) PRAGMA user_version gate+sello=1, migraciones historicas idempotentes bajo v1; (B) SIGTERM/SIGINT via thread aparte (shutdown desde el mismo hilo se bloquearia) + server_close + exit 0, probado real (puerto cerrado, log limpio); (C) sgf_path NO toca el filesystem del servidor (solo SELECT 571 e INSERT 757) → documentado sin validacion inventada; (D) ya cubierto por el catch ValueError→400 de Fase 1: confirmado empiricamente, solo tests de regresion. +3 checks servidor (35 total).

- T12: cliente y servidor con la misma window function (rn<=n + HAVING SUM(wrong)>0); compare_struggling.js 8/8 con nota de no-determinismo previo en empates (asertar ahi era asertar comportamiento indefinido). Suite final 35/73/8 TODO OK. TRABAJO T8-T12 COMPLETADO.
