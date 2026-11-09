# WORKPLAN FC3–FC14 — Focus: interfaz completa

Estado: **CERRADAS** (3-nov-2026). `run_all.sh` → `✔ TODO OK`; `test_focus.js` → `TODO OK`;
prueba E2E en Chrome real → 42/42.

Solo cambia `tsumevault.html`. La zona de sync (`harness_bundle.js`) es **byte-idéntica** a la de FC2.

## FC3 — Runs pasa a modal 🗂; la pestaña se llama Focus

- Cabecera: botón `#runs-btn` 🗂 (antes de 📊) → `openRuns()` / `closeRuns()` / `onRunsOverlayClick()`.
- Modal `#runs-overlay` con el mismo `#runs-list` de siempre (`loadRuns()` sin cambios salvo cerrar el modal al reanudar).
- Pestaña `data-tab="runs"` → `data-tab="focus"` (mismo hueco); `#tab-runs` → `#tab-focus`.
- `startRun` ya no hace `switchTab('runs')` ni `loadRuns()`: te quedas en la pestaña donde estabas (el progreso se ve en la barra lateral).
- Sync manual: refresca la lista de Runs solo si el modal está abierto. Escape cierra el modal.
- Móvil: `#hdr` con `min-width:0` y botones de cabecera algo más compactos (con 🗂 no cabía en 390 px y ensanchaba toda la columna; medido: original 390, sin arreglo 408, con arreglo 390).

## FC4 — Botón 🎯 en cada capítulo de Collections

- Junto a ▶ y 🧩. Sin Focus: `🎯`. En un Focus activo: `🎯 Nombre` en dorado. En un Focus archivado: borde discontinuo.
- Menú flotante `#focus-pop` (se crea al pulsar; no carga la pantalla): Focus activos + «Nuevo Focus…»; si ya está en uno, solo «Sacar del Focus»; si está en uno archivado, solo el aviso.
- `localFocusChapterMap()` una vez por lista de capítulos (sin consultas por fila).
- Cierre: al pulsar fuera o con Escape.

## FC5 — Pestaña Focus

- **Pending today**: cada Focus activo (pendiente / hecho / sin capítulos en trabajo); pulsar «▶ pendiente» lanza la sesión.
- **Filtro** Todos / En trabajo / Listos para Run / Promocionados (guardado en `localStorage` `focus_filter`) y **contadores siempre visibles**.
- **＋ Nuevo Focus** y **Mostrar archivados**.
- **Tarjeta por Focus**: % de la última sesión completada (color `pctColor`), recuento por estado, avisos de capítulos no encontrados, «▶ Sesión (n problemas)».
- **Detalle** (al desplegar): Renombrar, Archivar, Borrar (solo sin sesiones) / Reabrir; capítulos por estado (Listos, En trabajo, Promocionados plegado) con su % y acciones:
  - En trabajo → ⬆ Promocionar (activa show, actualiza el checkbox de Collections y pregunta si lanzar el Run).
  - Listo → ▶ Run (cambia de source si hace falta) y ⬇ En trabajo.
  - Promocionado → ⬇ En trabajo.
  - No encontrado → ✕ Sacar.
- Archivar: bloqueado con capítulos listos (lista cuáles); si no, confirma mostrando los En trabajo que quedan libres.
- Se refresca sola al terminar un Run, tras sync manual, al recargar colecciones y tras cada acción.

## FC6 — Sesiones

- `startFocusSession(uuid)`: problemas visibles de los capítulos En trabajo, orden aleatorio, motor de Free tal cual (todas las ayudas disponibles).
- Cada intento lleva `session_uuid` (`recordAttempt` → `localInsertAttempt`); al primer intento de cada problema sale de pendientes.
- Next tras el último vuelve al primer pendiente (los saltados siguen pendientes).
- Se completa sola: aviso en el tablero (`🎯 Focus completado — 17/20 (85%)`), te quedas en el tablero, etiqueta en la barra lateral, lista con ○ pendiente / ● hecho.
- Ocultar 🚫 en sesión: sale de la lista y de pendientes (clave source+problem_id, necesaria al mezclar sources).
- Lanzar Free, Review, un Run, reanudar un Run, cambiar de source o terminar la práctica cierran la sesión (si no estaba completa, queda sin contar).

## FC7 — Filtro Focus en Free

- Selector `#fp-focus` (Focus activos). Solo sus capítulos En trabajo existentes; ignora el source de la cabecera salvo que se elija una Collection; se cruza con Chapters, Collection, etiquetas, dificultad, estado, ID y orden. No crea sesión. También vale para «Bulk tag».

## Corrección (3-nov, tras la primera prueba de Victor)

- **Bug FC7:** con «Only visible chapters» marcado (se guarda entre sesiones), el filtro Focus de Free daba
  «0 problems match», porque los capítulos En trabajo suelen tener `show` desactivado. Ahora, con un Focus
  elegido, ese check no se aplica (el Focus ya dice qué capítulos). Reproducido en E2E antes de corregirlo.

## FC8 — Añadir a un Focus los capítulos marcados en Free

- «🎯 → Focus» junto a «Clear» en el checklist de Chapters de Free.
- Menú con los Focus activos y «Nuevo Focus…»; añade los marcados y se salta en silencio los que ya
  están en un Focus (activo o archivado). Resumen en la línea de recuento de Free.
- Sin capítulos marcados: aviso.
- `focusPopEnsure` / `focusPopPlace`: el menú de Collections y el de Free comparten creación y posición.

## FC9 — % de la tarjeta = capítulos En trabajo actuales (4-nov)

- Antes: % de la última sesión completada (incluía capítulos promocionados después de esa sesión).
- Ahora: `localFocusWorkPct(chapters, progress)` suma aciertos/problemas de los capítulos En trabajo
  existentes, cada uno con su última sesión completada; cada problema pesa igual. Un promocionado
  sale en el acto; uno sin sesiones no cuenta; sin datos → `—`. El % de cada fila no cambia.
- Tests: 4 en `test_focus.js` (57 en total) y 2 en E2E.

## FC10 — Contadores de la sesión: solo el primer intento (4-nov)

- Bug: en una sesión de Focus, volver atrás y repetir un problema sumaba seen/aciertos/fallos
  (contadores de Free en `recordAttempt`). Ahora, en sesión, solo suma si el problema seguía
  pendiente (su primer intento). El intento repetido se sigue guardando. Free sin sesión: igual que antes.
- E2E: comprobación nueva; con la versión anterior falla (6|4|2|67%) y con el arreglo pasa (5|4|1|80%).

## FC11 — Problemas que no cargan en una sesión (9-nov)

- Bug (reportado: Focus de 56 problemas que se quedaba en 45 vistos y repetía): `loadAndRender` salta
  en silencio un problema que no carga (sin `sgf_path`, SGF 404, SGF ilegible). En sesión se quedaba
  pendiente para siempre; al volver al "primer pendiente" fallaba otra vez, el motor avanzaba al
  siguiente ya hecho y la sesión repetía problemas sin completarse nunca.
- Arreglo: `focusDropUnloadable()` lo quita de la sesión (lista, pendientes y total), la sesión puede
  completarse con los que sí cargan, y la etiqueta lo avisa («⚠ N sin cargar», detalle en el tooltip
  y en consola). Si el roto era el último pendiente, la sesión se completa y te quedas en el tablero.
- Base: el `tsumevault.html` de Victor del 9-nov (incluye su poda de catálogo en `doSync`); la zona
  de sync es idéntica a la de ese fichero.
- Prueba en Chrome (`repro.js`): SGF 404 en orden aleatorio y siendo el último; con la versión
  anterior falla y con el arreglo pasa.

## FC12 — SGF en carpetas con `%` (9-nov)

- Causa de los 12 problemas que no cargaban: carpeta `awesome_lessons/Lessons 2 - Group D/This Endgame
  appears 100%`. La URL se construía pegando `sgf_path` tal cual; el navegador codifica espacios pero
  no `%`, y `100%/0` no es un escape válido → GitHub Pages responde HTTP 400.
- Arreglo mínimo: `sgfUrl(path)` junto a `SGF_BASE`; solo codifica `%`, `#` y `?` (lo único que rompe
  una ruta). Usado en `loadAndRender`, partidas (Games) y las dos listas de precarga offline. Las
  URLs que ya funcionaban salen idénticas, así que la caché offline existente sigue valiendo.
- Prueba local: SGF en `This Endgame appears 100%/` y en un nombre con `#` y `?` → 200; sesión
  completa sin fallos; rutas normales (espacios, acentos, paréntesis, `\`) idénticas a antes.
  (El servidor local de Python tolera el `%` sin codificar; la comprobación final es en GitHub Pages.)

## FC13 — Lanzar la sesión pulsando el nombre en «Pending today» (9-nov)

- Como en Review: en el panel «Pending today» de la pestaña Focus, el nombre del Focus lanza su
  sesión (si tiene capítulos En trabajo). «▶ pendiente» sigue funcionando igual.
- E2E: la sesión principal se lanza ahora pulsando el nombre.

## FC14 — Nº de problemas en «Pending today» (9-nov)

- Como en Review: un Focus pendiente muestra «▶ N pendientes», donde N son los problemas de su
  sesión (visibles de los capítulos En trabajo existentes). `localFocusTodayStatus` devuelve `problems`.
- Tests: 1 en `test_focus.js` (58 en total); E2E ajustado («▶ 5 pendientes»).

## Validación

```
run_all.sh:     servidor 180 | cliente 168 | compat 8   ✔ TODO OK
test_focus.js:  58 PASS                                  TODO OK
E2E (Chrome):   42 PASS                                  TODO OK
```

E2E sobre la app real (WGo v2 + sql.js) contra el servidor de FC1 con BD sembrada (2 sources):
crear Focus desde Collections, añadir/sacar, pestaña Focus, sesión completa con un fallo, un salto
y un intento repetido (80 %, el primer intento cuenta), sync de sesión e intentos al servidor,
promoción (show + checkbox), bloqueo de archivado, Run desde Focus → Promocionado, filtro de Free,
modal de Runs, archivar/reabrir y sin errores de JavaScript. Capturas en escritorio y móvil (390 px).

## Limitaciones conocidas

- El botón 🎯 muestra el nombre del Focus recortado (máx. 72 px) para no apretar el nombre del capítulo; el nombre completo está en el tooltip y en el menú.
- Mapa de calor de sesiones: fase 2 (no incluido, como dicen los requisitos).
