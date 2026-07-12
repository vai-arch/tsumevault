# WORKPLAN — No reutilizar ids del servidor como clave local (aprobado)

Si esta sesión se corta, retomar desde el primer paso NO marcado [x].
Directorio de trabajo: /home/claude/tsumevault (si el contenedor se reseteó,
los entregables actuales están en /mnt/user-data/outputs y este plan también).

## Contexto
Bug preexistente: el pull inserta filas conservando el id del SERVIDOR con
INSERT OR IGNORE; si un id local autoincrement ya ocupa ese valor (datos
creados en el dispositivo antes de su primer sync), la fila del servidor se
descarta silenciosamente y el cursor avanza → runs/attempts que nunca llegan.

## Diseño aprobado
1. SERVIDOR: handle_sync_pull incluye run_uuid en cada attempt (LEFT JOIN runs).
   Clave extra ignorada por clientes antiguos. Nada más cambia en servidor.
2. CLIENTE (doSync, sección pull):
   - Procesar RUNS ANTES que attempts (hoy es al revés; necesario para
     resolver run_uuid de attempts del mismo lote).
   - Runs con uuid no existentes localmente: INSERT SIN id (autoincrement
     local); sus run_items con el id LOCAL recién asignado.
   - Attempts con uuid: INSERT SIN id, con run_id remapeado al id LOCAL del
     run vía run_uuid (Map de caché por lote + consulta por índice único);
     si el run no existe localmente → run_id = NULL (decisión aprobada).
   - Filas LEGACY sin uuid (runs y attempts): comportamiento actual intacto
     (INSERT OR IGNORE con id del servidor) — su id es su única clave dedup.
   - Cursores: sin cambios (siguen usando los ids del SERVIDOR del payload).
   - Push, borrados, syncDeletedRuns, purga: sin cambios.
3. Sin migraciones de esquema. Retroactivo: reset de cursores re-pullea y
   recupera las filas antes colisionadas.

## Validación prevista
- test_server.py: check nuevo → el pull devuelve run_uuid en attempts.
- harness.js:
  - Corregir E5: capturar cUuid ANTES del sync (tras el fix, el último run
    por id local puede ser el de A y la aserción volvería a ser vacua).
  - E14 nuevo: dispositivo con datos locales previos al primer sync cuyos ids
    colisionan con los del servidor → debe recibir TODO, attempts colgando del
    run correcto (verificar por uuid), doble sync sin duplicados, y su propio
    run pusheado.
- harness_compat.js: sin cambios de código; reejecutar (cliente antiguo debe
  ignorar run_uuid y seguir funcionando).
- Ejecutar SIEMPRE con ./run_harness.sh (garantiza servidor fresco; en este
  contenedor no hay fuser/ss/lsof: kill vía /proc + check por bind).

## Estado
- [x] Paso 0: este plan creado y copiado a outputs.
- [x] Paso 1: servidor — run_uuid en pull + check en test_server.py + batería OK.
- [x] Paso 2: cliente — reordenar pull (runs→attempts), inserts sin id,
      remapeo run_uuid→id local, legacy intacto. node --check OK.
- [x] Paso 3: arnés — fix E5 (cUuid antes del sync) + E14 colisión. 
      ./run_harness.sh TODO OK (esperados ~57 PASS).
- [x] Paso 4: compat — servidor fresco puerto 3489 + harness_compat.js TODO OK.
- [x] Paso 5: IMPLEMENTATION_STATUS.md — mover la colisión de ids de
      "Remaining work" a Decisions (nueva entrada 17), actualizar recuentos de
      validación, copiar entregables (tsumevault.html, tsumevault_server.py,
      IMPLEMENTATION_STATUS.md) a /mnt/user-data/outputs y presentarlos.

## Notas de implementación acumuladas
(rellenar al avanzar; decisiones tomadas sobre la marcha van aquí)

- Paso 1 nota: check nuevo 'pull attempts incluyen run_uuid'; bateria 33/33 OK.
- Decision en paso 2 (compat cliente nuevo + servidor ANTIGUO): si la clave run_uuid NO viene en el attempt (servidor antiguo), usar a.run_id tal cual (semantica previa, solo transicion). Si run_uuid es null: usar a.run_id SOLO si existe run local con ese id y uuid IS NULL (run legacy, ids coinciden por construccion); si no, NULL.
- Paso 2 nota: aplicado con edit_client_4.py (marcadores); node --check OK; html copiado a outputs como checkpoint.
- Paso 3 nota: 60/60 PASS (E5 corregido no-vacuo + E14 completo: precondicion de colision real, recepcion total, attachment por uuid, doble sync, push propio).
- Paso 4 nota: compat 8/8 OK (cliente antiguo ignora run_uuid; cliente nuevo remapeado convive).
- Paso 5 nota: STATUS actualizado (Decision 17, recuentos 33/60, nota compat). TRABAJO COMPLETADO.
