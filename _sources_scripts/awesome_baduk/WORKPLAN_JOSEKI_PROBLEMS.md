# WORKPLAN JP — Josekis como problemas de tsumego (sustituye a J4)

Estado: **PLAN — pendiente de confirmación de Victor**. Decidido en la conversación del 19-oct-2026 tras probar J4 ("las cosas no funcionan como esperaba").

## Por qué cambiamos

J4 (tarjetas con cola propia) obligaba a jugar desde el tablero vacío (el 4-4 trivial) y a adivinar qué variante buena quería la tarjeta. En su lugar, un **generador** convierte cada fichero maestro en problemas normales de la source `my_collections`, que entran en Run / Review / Free / SM-2 / sync / etiquetas sin tocar el cliente.

- **J4 no se despliega** (los ficheros entregados se descartan). `tsumevault.html` sigue en J3.1.
- **J3/J3.1 se quedan**: la pestaña Joseki con el modo aprender sigue siendo útil para estudiar.
- **J2 (servidor) ya está desplegado**: sus tablas `joseki_*` quedan vacías y sin uso; no estorban.

## Decisiones tomadas

1. **Un problema por línea y color** (las mismas líneas que las tarjetas de J1: incluye ramas ¿y si? y líneas de castigo).
2. **Posición inicial**: el motor no deja que el rival juegue primero (tu color = el de la primera jugada del SGF). Por eso las jugadas previas a tu primera jugada van como **piedras de inicio** (`AB`/`AW`), con la última marcada con un círculo (`CR`).
   - Juegas B: Q16 y O17 puestas; empiezas tú.
   - Juegas W: Q16 puesta; empiezas tú.
3. **Comentario inicial**: `<fichero> · Juegas B/W` + el comentario de la última jugada puesta + la instrucción si toca.
4. **Instrucción** («→ Ahora: <nombre>» o «→ ¿Y si…? <nombre>»), en el comentario de la jugada del rival anterior (o en el inicial), **solo** cuando en tu turno hay **2+ jugadas buenas** o tu jugada **abre una rama ¿y si? (IT)**. Con una única jugada buena no se dice nada.
5. **Error del generador** si hace falta instrucción y la rama no tiene nombre (primera línea del comentario).
6. **Línea lineal**: el rival solo juega la jugada de esa línea; sus alternativas son otros problemas.
7. **Tus jugadas malas o dudosas** del fichero (hermanas de tu jugada, `BM`/`DO`) se copian como ramas `WRONG <comentario>`: fallas, pero ves por qué. Lo que no está en el fichero falla sin comentario.
8. **Final**: la última jugada lleva `RIGHT <comentario>`.
9. **Pases del rival** (tenuki, también los implícitos): se generan como pase; el motor los juega sin piedra. Su comentario empieza por «Tenuki.».
10. **Tu tenuki**: en tsumego no se puede pasar.
    - Si tu pase es el final de la línea: el problema acaba justo antes, en `RIGHT … → Ahora tenuki`.
    - Si la línea sigue después: el problema acaba ahí y **lo que sigue es otro problema**, con todo lo anterior como piedras de inicio y la instrucción «Has hecho tenuki…».
11. **Líneas de castigo que acaban en el error del rival** (sin tu jugada de castigo): se generan igual (ves el error y su comentario, ✓) y el generador **avisa** para que añadas el castigo en el maestro. En tu 4-4 hay dos.
12. **Orientación**: la del fichero. La rotación para todos los problemas queda como tarea futura del cliente.

## Identidad y SM-2

- **`problem_id` = fichero + color + secuencia de jugadas** del problema (p. ej. `4-4_Joseki-B-pd.nc.qf.pb.qc.kc`). No depende de comentarios, marcas ni orden de ramas.
- Misma secuencia → mismo id → el importador actualiza el SGF y **conserva SM-2 e historial**.
- Secuencia distinta (alargar, cambiar o borrar una línea) → problema nuevo; el viejo **se retira**. Al alargar una línea se pierde su SM-2 (aceptado: la línea memorizada estaba incompleta).
- **Retirada automática** (cambio pequeño de servidor, JP2): el capítulo de un fichero maestro se importa con la lista completa de sus ids vigentes; el servidor pone `hidden=1` a los del capítulo que falten. Nunca borra historial. Llega a los dispositivos en el siguiente sync (T13 ya propaga la lista de ocultos del servidor).
  - *Corrección a lo dicho en la conversación*: si una línea retirada vuelve idéntica, **no** se des-oculta sola (no se puede distinguir de un ocultado tuyo a mano en Free). Se des-oculta a mano. Caso raro.
- **Caché**: el SW sirve los `.sgf` cache-first por URL. Para que un problema actualizado (mismo id, contenido nuevo) se vea sin redescargas manuales, el **nombre del fichero lleva un hash del contenido** (`<id>.<hash8>.sgf`). El `sgf_path` cambia, el id no. El generador es dueño de su carpeta y borra los `.sgf` que ya no correspondan.

## JP1 — Generador (`generate_joseki_problems.py`, Python, local)

- Reutiliza `joseki_lib.py` (J1) para compilar el maestro: mismas validaciones y mismas líneas.
- Por cada línea y color → uno o más problemas (corte en tu tenuki a mitad de línea, decisión 10).
- **Salida**: `my_collections/Josekis/<fichero>/<id>.<hash8>.sgf` con `CA[UTF-8]`; colección `Josekis`, un capítulo por fichero maestro. Orden en el capítulo = orden de las líneas en el fichero, B antes que W.
- **Publicación**: POST a `/admin/import_my_collection` con `retire_missing` en cada capítulo de josekis, reutilizando la conexión, auth y detección local/remoto de `import_my_collection.py`.
- **Informe**: líneas, problemas, nuevos / actualizados / retirados, errores (rama sin nombre) y avisos (castigo sin castigo). Modo `--dry-run` que no escribe ni publica.
- Tests (`test_generate_joseki.py`): el 4-4 real produce exactamente los SGF esperados (el del ejemplo de Low Enclosure literal), instrucciones solo donde tocan, ramas WRONG, pases, corte por tenuki, error por rama sin nombre, avisos, estabilidad del id ante cambios de comentarios u orden de ramas, cambio de id al alargar, hash y limpieza de la carpeta. Y un test de que **cada SGF generado lo parsea `sgf_lib.py`** y empieza con tu color (`PL`).

## JP2 — Servidor: retirada (`tsumevault_server.py`, CRLF)

- `/admin/import_my_collection` acepta en cada capítulo un campo opcional `"retire_missing": true`. Con él: `UPDATE problems SET hidden=1` a los del capítulo que no vengan en la lista y estén visibles. Nuevo contador `problems_retired`.
- **Sin el campo, todo igual que hoy**: tus colecciones a mano nunca se ven afectadas.
- No hay cambio de esquema.
- Tests nuevos en `test_server.py`, sin debilitar ninguno:
  - retira solo los que faltan en ese capítulo, y no los de otros capítulos ni otras sources;
  - sin el flag no retira nada;
  - no des-oculta;
  - conserva el historial;
  - el retirado aparece en `/sync/problems_hidden`.

## Cliente

**Sin cambios.** `harness_bundle.js` byte-idéntico. Se verifica con un SGF generado en la prueba de humo:
- el motor real lo carga con las piedras de inicio, la marca, el color y el comentario inicial;
- un acierto llega a RIGHT;
- una rama WRONG falla mostrando su comentario;
- el pase del rival funciona.

## Validación

1. `run_all.sh`: **137+N / 132 / 8** (servidor con los tests nuevos; cliente y compat iguales).
2. `test_generate_joseki.py` en verde.
3. Mutaciones:
   - instrucción siempre o nunca;
   - id dependiente del comentario;
   - WRONG sin comentario;
   - retirar sin flag;
   - retirar fuera del capítulo.
4. CRLF byte a byte en el servidor, `ast.parse`, diff revisado.
5. En tu máquina: `--dry-run` sobre el 4-4, revisión del informe, publicación y checklist en navegador y móvil.

## Pendiente de Victor

1. **Confirmar este plan.**
2. **Pasarme `import_my_collection.py`** (no lo tengo en el contenedor): de él reutilizo la conexión al servidor, el token y la detección local/remoto.
3. **Dificultad del capítulo de josekis**: sin dificultad (por defecto) o un valor fijo (p. ej. `difficulty-10k`). ¿Cuál?
4. Al desplegar: primero el servidor JP2 (con `.backup` previo), luego generar y publicar.
