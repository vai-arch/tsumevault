# REQUISITOS FOCUS — TsumeVault

Estado: análisis funcional cerrado (3-nov-2026). Fase siguiente: análisis técnico y desarrollo, en un chat aparte.
Alcance de este documento: solo requisitos funcionales. No hay decisiones técnicas tomadas (tablas, sincronización, migraciones, etc.).

---

## 1. Contexto y objetivo

Flujo de trabajo actual de Victor:

1. Agrupa capítulos que aún no domina con **etiquetas** (hoy asignadas problema a problema; el modo Free permite etiquetar en bloque todos los problemas de un filtro).
2. Los trabaja en modo **Free** filtrando por etiqueta.
3. Cuando siente que ya entiende los conceptos, hace **Runs** de esos capítulos, que entran en **SM-2** (Review).

Las etiquetas se usan aquí como "sala de espera" de capítulos. Victor no necesita conservar el tipo de problema, solo agrupar conceptos en los que trabaja ahora (ej.: corner patterns, lateral patterns, cho chikun, awesome lessons), meter y sacar capítulos, y descartar el grupo cuando el tema deja de hacer falta.

**Objetivo:** una sección nueva, **Focus**, de uso diario junto a Review. Cada día: Review para lo consolidado (SM-2) y Focus para los conceptos en trabajo. Debe ser fluido añadir capítulos, promocionarlos y saber lo cerca que se está de promocionar.

**Principio de diseño:** un Focus es pequeño por definición (no tiene sentido un Focus de 1000 problemas). No se añaden mecanismos para manejar Focus enormes; la presión de tamaño la ejerce el propio concepto y la opción de promocionar.

---

## 2. Modelo de conceptos

- **Focus:** agrupación con nombre de capítulos en los que se está trabajando un concepto.
- **Capítulo en un Focus:** cada capítulo tiene un estado dentro del Focus.
- Un capítulo pertenece **como máximo a un Focus**.
- Un Focus **puede mezclar capítulos de distintas sources**. La sección Focus **no depende del selector de source** de la cabecera.
- **Focus sustituye a las etiquetas** para este fin (agrupar capítulos en trabajo). Las etiquetas siguen existiendo para agrupar problemas sueltos y no cambian.
- **No hay migración automática** de las etiquetas actuales: Victor las pasa a mano (son pocas).

### Estados de un capítulo dentro de un Focus

| Estado | Significado |
|---|---|
| **En trabajo** | Se practica; todavía no está listo para Runs. |
| **Listo para Run** | Promocionado, pero aún sin su primer Run completado. Visible siempre en la sección Focus para que no dependa de la memoria. |
| **Promocionado** | Ya tiene su Run; sus problemas están en SM-2. Se muestra plegado para no estorbar. |

El capítulo conserva su pertenencia al Focus tras promocionarse (historial de qué se trabajó en cada Focus).

---

## 3. Añadir capítulos a un Focus

- Desde **Colecciones**: un botón nuevo junto a ▶ (Run) y 🧩 (Free) en cada capítulo.
- Al pulsarlo: menú con los **Focus activos** y la opción **"Nuevo Focus…"** (se puede crear un Focus en ese mismo momento). También se puede crear un Focus desde la sección Focus.
- Si el capítulo **ya está en un Focus**: el botón cambia de aspecto, indica en cuál está y **solo permite sacarlo** (no hay "mover"; para cambiarlo, sacar y añadir al correcto).
- El menú se dibuja solo al pulsar el botón (no debe cargar la pantalla de Colecciones).
- Cross-source: es válido, el código ya trabaja con identificadores de capítulo únicos en toda la app.
- Si un capítulo de un Focus deja de existir (p. ej. reimportación con nuevo identificador), la sección Focus **avisa** en vez de fallar en silencio.

**Aparcado (no se hace ahora):** añadir capítulos desde la sección Focus con una lista filtrable de colecciones/capítulos. Se valorará más adelante si hace falta.

---

## 4. Promoción

- Es una **acción manual del usuario**, **capítulo a capítulo**. Se puede promocionar uno, varios o todos, y seguir añadiendo capítulos al Focus en cualquier momento.
- La decisión es siempre del usuario; la app solo muestra datos de apoyo (colores y % de la última sesión).

**Al promocionar un capítulo:**

1. Pasa a **Listo para Run**.
2. Se **activa automáticamente su `show`** (visibilidad), para que sus problemas entren en Review. Motivo: Review solo incluye capítulos con show activo, mientras que un Run de capítulo funciona aunque esté oculto; sin esto los problemas entrarían en SM-2 y nunca saldrían en Review, sin aviso.
3. La app **ofrece lanzar el Run del capítulo en ese momento**; el usuario puede dejarlo para después.

**De Listo para Run a Promocionado:** al **completarse el Run del propio capítulo** (el ▶ de Colecciones o el que ofrece la app al promocionar; da igual desde dónde se lance). Un Run de la colección entera **no** cuenta.

**Caso especial:** si al promocionar el capítulo ya tiene un Run completado, pasa **directamente a Promocionado** (sus problemas ya están en SM-2), sin pasar por Listo para Run.

**Devolver un capítulo a En trabajo** (por ejemplo, si se falla mucho en SM-2): solo cambia su estado dentro del Focus. SM-2, historial y `show` **no se tocan**. Si se vuelve a promocionar, pasa directo a Promocionado (ya tiene Run). Si el usuario no quiere verlo en Review mientras lo reaprende, desmarca el show en Colecciones.

---

## 5. Sesiones de Focus

### 5.1 Qué es y cómo se lanza
- Una sesión **solo se lanza desde un Focus**.
- Una sesión cubre **todos los capítulos En trabajo** del Focus. **Se lanza entera o no se lanza**: no hay selección de capítulos en la sesión.
- Usa el **tablero y el motor del modo Free** tal cual. **No cuenta como Run**: no usa `run_id`, no toca SM-2 ni las estadísticas de Runs.
- **Orden aleatorio**, mezclando los capítulos En trabajo del Focus (el primer intento mide mejor lo que se sabe si el orden no da pistas).

### 5.2 Cuándo cuenta una sesión
- **Completada** cuando **cada problema tiene al menos un intento** (acertado o fallado). Un problema saltado con Next sigue pendiente hasta que se haga.
- Una sesión **no completada no cuenta**: no entra en el progreso ni en los pendientes.

### 5.3 Sesiones a medias
- Se pueden **reanudar el mismo día**, con la misma lista y el mismo orden.
- Al día siguiente se **descartan**: los intentos ya hechos se conservan, pero la sesión no cuenta.

### 5.4 Porcentaje de una sesión
- Para el % cuenta el **primer intento de cada problema**. Los intentos repetidos dentro de la sesión se siguen guardando, pero no entran en esa cifra (el segundo intento mide recordar lo que se acaba de ver).

### 5.5 Qué se guarda de una sesión
- Solo lo que no se puede deducir de los intentos: **cuándo empezó, cuándo terminó, si se completó y a qué Focus pertenece**.
- **No** se guardan source ni filtros: los intentos ya indican a qué problemas/capítulos corresponden.
- Aciertos, fallos y tiempos **no** se duplican en la sesión: se calculan desde los intentos.
- Los intentos de una sesión se **vinculan a ella** (campo nuevo en el intento, análogo a como hoy se vinculan a un run).
- Los intentos de Free anteriores a esta funcionalidad **no tienen sesión** asociada.

### 5.5b Sincronización entre dispositivos
- Se sincroniza **todo**, incluida la sesión a medias: se puede empezar en un dispositivo y terminar en otro.
- Si el mismo problema se contesta en dos dispositivos a la vez, cuenta el **primer intento por hora**; el otro queda guardado pero no cuenta.

---

## 6. Sección Focus (pantalla)

### 6.1 Estructura
- Lista de Focus activos. Por Focus: resumen y, al desplegarlo, **detalle por capítulo**.
- Dentro de cada Focus, los capítulos agrupados por estado: **Listos para Run** (siempre visible), **En trabajo**, **Promocionados** (plegado).

### 6.2 Progreso y color
- Se muestra el **% de la última sesión completada**, con el color de la **misma función de color que ya usan las Colecciones**: verde si el % es igual o superior al umbral configurable (hoy 90%), dorado entre 80% y el umbral, rojo por debajo de 80%. **Se reutiliza el parámetro de umbral existente**; no se crea uno nuevo.
- Regla del verde: **solo la última sesión** (no hay media ni "últimas X sesiones"; el parámetro X queda descartado). No se muestra historial de sesiones anteriores por capítulo.
- Hay % del Focus completo (resumen) y % por capítulo (detalle), ambos calculados con el criterio del primer intento.

### 6.3 Filtro de la página
- Filtro a nivel de página: **En trabajo / Listos / Promocionados / Todos**.
- El valor se **guarda entre sesiones**.
- Los **contadores por estado se muestran siempre**, ej.: `En trabajo (5) · Listos (2) · Promocionados (8)`, para que un filtro olvidado no oculte capítulos pendientes de Run.

### 6.4 Panel "pendiente hoy"
- Similar al "Pending today" de Review.
- Un Focus está **pendiente hoy si no se ha completado ninguna sesión suya ese día**.
- Si se añade un capítulo a un Focus **después** de haber completado la sesión del día, el Focus **no** vuelve a pendiente; el capítulo entra en la sesión de mañana (para probarlo hoy, está Free).

### 6.5 Fase 2 (no se hace ahora)
- Mapa de calor tipo GitHub de sesiones de Focus (ya existe uno de intentos en Stats > Activity; uno específico de sesiones sería un añadido pequeño).

---

## 7. Integración con Free

- Free **no cambia** salvo un **nuevo filtro "Focus"**, combinable con el resto (dificultad, estado, etiquetas, ID, orden…).
- Free sigue siendo **práctica libre**: **no crea sesión**, no cuenta para progreso ni pendientes. Usos previstos: probar problemas de un Focus sin abrir sesión, combinar Focus con etiqueta, o Focus con dificultad para centrarse en los más difíciles, o practicar capítulos concretos de un Focus.

---

## 8. Archivar un Focus

- Un Focus **se archiva** (no se borra): desaparece del día a día y del panel de pendientes, pero **conserva sesiones y capítulos** para consulta, y se puede **reabrir**.
- **Capítulos En trabajo** del Focus archivado: quedan **libres** (sin Focus) y se avisa de cuáles son antes de confirmar.
- **Capítulos Listos para Run**: **bloquean el archivado** hasta que se haga su primer Run o se devuelvan a En trabajo (si no, quedarían sin primer Run y nadie lo recordaría).
- **Capítulos Promocionados**: no afectan; se archivan con el Focus.
- Al reabrir un archivado, si alguno de sus capítulos ya está en otro Focus, se resuelve en ese momento.

---

## 9. Decisiones descartadas o cambiadas durante el análisis

- Mezclar los capítulos pendientes de Run con Review: descartado (viven en Focus).
- Sesiones sobre capítulos concretos: retirado; para eso está Free.
- "Últimas X sesiones" configurable: descartado; solo la última sesión.
- Mover un capítulo entre Focus: descartado; se saca y se añade.
- Filtrado de capítulos al añadir desde la sección Focus: aparcado.

---

## 10. Puntos pendientes de confirmar (surgidos al redactar)

1. **Filtro Focus en Free:** ¿incluye los capítulos de todos los estados del Focus o solo los En trabajo? (No se decidió.)
2. **Capítulos Promocionados de un Focus archivado:** ¿siguen ligados al archivado (y por tanto bloqueados para otro Focus) o quedan libres como los En trabajo?
3. **"Ya tiene un Run completado" (promoción directa):** se asume el Run del propio capítulo, coherente con la regla del primer Run; confirmar.
4. **% por capítulo:** se toma de la última sesión completada que incluyó ese capítulo; confirmar el caso de un capítulo añadido después de la última sesión (sin % hasta su primera sesión).
5. **Sesión en curso y cambios de estado:** se asume que una sesión a medias conserva su lista aunque entretanto se añada o promocione un capítulo; confirmar.

---

## 11. Notas para la fase técnica (observaciones del código actual, no decisiones)

- Free **no registra sesiones** hoy: guarda intentos sueltos con `run_id` vacío; el % de la barra lateral de Free vive en memoria.
- Los intentos con `run_id` nulo no cuentan para SM-2 ni para las estadísticas por problema.
- Las etiquetas son por problema (T23) y se sincronizan con LWW y tombstones; existe etiquetado en bloque en Free (T35).
- Los capítulos tienen `id` único global; un `set_id` solo es único dentro de su source. Free ya tiene modo "All sources" que trabaja con problemas de varias sources.
- Review solo incluye problemas de capítulos con `mostrar=1`; los Runs de capítulo no lo exigen.
- El color por % sale de una función única (`pctColor`) con el umbral `PCT_GREEN`.
- La visibilidad de capítulos (`mostrar`) ya se sincroniza entre dispositivos (T34).
- Mantener el flujo de trabajo de `INSTRUCCIONES_DELEGACION.md` (análisis técnico antes de código; Victor avisará cuando pasemos a generar código).
