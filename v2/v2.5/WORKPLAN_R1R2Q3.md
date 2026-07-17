# WORKPLAN R1–R2+Q3 — Visibilidad por nivel, redescarga SGF y badge pegado

Si la sesión se corta, retomar desde la primera NO marcada [x].
Directorio: /home/claude/tsumevault. Base esperada: 35/77/8 ✔ (md5 1149a024).

## Q3 — diagnóstico preliminar (confirmar en código)
El badge "2" tras cada problema = 1 attempt pendiente + 1 run sucio, que es
CORRECTO en el instante de resolver. Hipótesis del "se queda pegado":
recordAttempt lanza tryAutoSync(true), pero si YA hay un sync en vuelo (del
problema anterior), tryAutoSync retorna false por syncInProgress y ese intento
queda pendiente SIN ningún reintento programado → al parar de resolver, el
badge se queda en 2 hasta el siguiente intento/sync manual/recarga.
FIX previsto: al terminar un doSync con éxito, si countPendingSync().total>0
(llegó trabajo durante el vuelo), encadenar otro tryAutoSync(true) con ~1,5 s
de retraso (converge al pausar; sin cadena si el sync falla). + escenario arnés.

## R1 — botón "aplicar visibilidad por nivel" (tab By Level)
Para CADA source: mostrar=1 en los capítulos con dificultad igual o MÁS FÁCIL
(difficulty_num >= valor del combo bylevel-sel-{source}); mostrar=0 al resto.
Nota: el usuario dice "runs" pero mostrar es propiedad de CAPÍTULOS (es lo que
hoy cambia uno a uno). Tras aplicar: saveDB + sync (doSync ya empuja el mostrar
de todos los capítulos) + refrescar colecciones y el propio tab + confirmación.
PENDIENTE INVESTIGAR: columna real de dificultad del capítulo y de dónde salen
las opciones del combo (renderByLevel).

## R2 — botón de redescarga forzada de SGFs
Junto al botón actual de precache (que salta los ya cacheados), otro que
FUERZA la descarga y sobrescribe la caché (para problemas corregidos en
origen). PENDIENTE INVESTIGAR: implementación actual del precache (Cache API /
service worker) para reutilizarla con un flag force.

## Estado
- [x] Investigación (combo bylevel + columna dificultad + precache SGF)
- [x] Q3-fix — cadena de re-sync si quedó pendiente durante el vuelo + escenario
- [x] R1 — botón visibilidad por nivel (+ validación arnés si es extraíble:
      la lógica SQL de mostrar sí lo es)
- [x] R2 — botón force redownload
- [x] Cierre: STATUS (decisión 21), run_all final, entrega, respuesta a Q3.

## Notas acumuladas

- Confirmado: escala interna diff_avg menor=más fácil (15k=600…1d=2100); el '<=' replica UP TO LEVEL. Precache en SW externo → force via Cache API delete desde la página. Q3: causa = rebote en syncInProgress sin reintento; fix = cadena a +1,5s tras sync exitoso con pendientes. Suite final 35/82/8 TODO OK. COMPLETADO.
