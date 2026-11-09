# WORKPLAN AV — Aviso de posición de elección

Estado: **ENTREGADA (9-nov-2026)** — plan confirmado por Victor; implementada y validada en el contenedor. Pendiente: tests en su máquina, publicación y prueba en la app.
Requisitos: `REQUISITOS_AVISO_VARIANTE.md` (AV-01..AV-15, cerrados).

## 1. Decisión técnica: la marca (AV-02)

**Propiedad propia en el SGF generado**, escrita por `generate_joseki_problems.py`:

    ;B[qf]TVALERT[choice:Low Enclosure]C[Low Enclosure]...
    ;W[qb]IT[]TVALERT[whatif:Corner Hane]C[...]...

- Valor `<tipo>:<nombre>`, con `tipo` = `choice` (bifurcación) o `whatif` (¿y si?). El
  nombre se escapa como cualquier valor SGF (`]` → `\]`); el cliente separa por el primer `:`.
- **Va en el nodo de la jugada esperada** (el hijo), no en la posición desde la que se juega.
  Motivo: WGo no guarda en la raíz las propiedades que no conoce (las manda a `kifu.info`,
  que `parseSgfTree` no devuelve), y la primera elección de un problema cuelga de la raíz.
  Un nodo con jugada nunca es la raíz, así que la marca siempre llega al cliente.
  Comprobado con el WGo real: `hijo.TVALERT = "choice:Low ] Enclosure"`; en la raíz, `undefined`.
- **Mismo criterio que la instrucción de hoy**: se marca exactamente cada jugada para la que
  el generador escribe «→ Ahora: …» o «→ ¿Y si…? …» (función `instruction()`), así que
  marca y texto nunca divergen. Las ramas WRONG no llevan marca.
- `sgf_lib.validate_problem` ignora la propiedad (comprobado: sin incidencias), así que
  `import_my_collections` no cambia.
- Descartado: parsear el texto del comentario (depende de la redacción y del idioma).

## 2. Cliente (`tsumevault.html`)

Todo dentro del motor interactivo (`setupInteractiveMode`) y fuera del perímetro de
`extract_bundle.py`: el harness no cambia.

- **`choiceAlertOf(node)`** (pura, en el bloque de funciones puras): recorre
  `node.children`; si alguno trae `TVALERT`, devuelve `{ kind, sym, name }`
  (`choice` → `⑂`, `whatif` → `?`); si no, `null`.
- **Disparo** cuando le toca jugar al jugador en un nodo con aviso:
  - al montar el problema (raíz) — Run, Review, Free y Focus pasan por ahí;
  - en `playOpponent`, tras la piedra del rival, si el problema no ha terminado;
  - en `_studyRestart` (raíz) y en `_studyBack` (posición anterior);
  - el salto de variante (T24) acaba en `playOpponent`, así que queda cubierto (AV-04).
- **`startChoiceAlert(info)`**: clase `board-choice` en `#board-wrap` (borde azul `#4a8fe7`,
  el azul de los fantasmas ¿y si?); destello en `#result-flash` con `sym + ' ' + name` en azul
  durante 1,2 s; `playSound('choice')`; bloqueo de clics hasta que se apaga el destello.
- **`clearChoiceAlert()`**: quita borde, destello, temporizador y bloqueo. Se llama al jugar,
  en `showResult`, al cambiar de problema, en Back/Restart (antes de volver a evaluar) y al
  entrar en Explorar. El temporizador comprueba que el problema sigue siendo el mismo.
- **Clic bloqueado** (AV-09): al principio del manejador de clics del tablero, si el bloqueo
  está activo, `return` sin hacer nada (no piedra, no fallo, no sonido).
- **Repintar** (AV-06): `_studyRedraw` no toca la clase del borde, así que se conserva.
- **Explorar** (AV-15): al entrar, `clearChoiceAlert()`; al salir, si `choiceAlertOf(currentNode)`
  y le toca al jugador, solo se vuelve a poner el borde.
- **Sonido** (AV-10): `SFX.choice = new Audio('audio/variant.mp3')`, un elemento propio
  (así no se pisa con el de la transición T26 y se puede cambiar de fichero sin tocar más).
- **Orden del sonido** a mitad de problema: el aviso se lanza en el mismo momento en que se
  pinta la piedra del rival, así que «clic de piedra» y aviso suenan casi juntos. Si al
  probarlo se pisan, se añade un pequeño retardo (ajuste, no requisito).

## 3. Generador (`generate_joseki_problems.py`)

- En `build_sgf`, al escribir cada jugada del jugador (`chain(k)`), si `need(k)` devuelve
  instrucción, se añade `TVALERT[<tipo>:<nombre escapado>]` tras las marcas de calidad.
- No cambia nada más: mismos ids, rutas, capítulos y orden. **Cambia el contenido** de los
  problemas con elección (una propiedad más), así que al regenerar salen como «cambiados».
  El SM-2 se conserva porque el id no cambia.

## 4. Despliegue

1. Regenerar y publicar los problemas (`joseki_04_publicar_produccion.bat`): los ficheros con
   elección cambian de contenido.
2. Desplegar el HTML con el `.bat` habitual, que sube `CACHE_VERSION`. Hace falta: el SW sirve
   los `.sgf` cache-first por ruta, y sin cambio de versión seguiría dando los viejos sin marca.

## 5. Tests

- **`test_generate_joseki.py`**:
  - la marca está en cada jugada con «→ Ahora:» (tipo `choice`) y con «→ ¿Y si…?» (tipo `whatif`),
    y en ninguna otra (comparando marca e instrucción en todos los problemas generados);
  - nunca en la raíz ni en una rama WRONG;
  - primera elección del problema: la marca va en la primera jugada del jugador;
  - nombre con `]`: escapado y legible por `sgf_lib`;
  - actualizar los SGF literales que lleven elección (p. ej. Low Enclosure · B).
- **Comparación con el código actual**: ids, rutas, capítulos y orden idénticos; el contenido
  solo difiere por las propiedades `TVALERT` (quitándolas, byte a byte igual).
- **`test_joseki_problems_client.js`** (WGo real + motor real `setupInteractiveMode`):
  - al cargar un problema con elección inicial: borde, destello con `⑂ Low Enclosure`, sonido `choice`;
  - un clic durante el destello no hace nada; al vencer el temporizador, el mismo clic juega;
  - elección a mitad (tras la piedra del rival) y tipo `whatif` con `?`;
  - al jugar, el borde azul desaparece y aparece el verde o el rojo de siempre;
  - Back y Restart repiten el aviso completo; `_studyRedraw` conserva el borde sin sonido;
  - Explorar oculta el borde y lo devuelve al salir, sin destello;
  - un problema sin marca no avisa nunca (anti-vacío);
  - el temporizador de un problema anterior no afecta al siguiente.
- **Validación habitual**: CRLF del HTML, `node --check`, `harness_bundle.js` idéntico,
  mutaciones de lo nuevo (sin bloqueo, sin borde, sin repetición en Back, marca en WRONG,
  marca sin escapar…).

## 6. Ficheros que necesito de tu disco

Mi última copia de estos es del 20-oct; desde entonces has hecho la sección Focus y puede
que alguno haya cambiado. Pásame la versión actual de:

- `generate_joseki_problems.py`, `joseki_lib.py`, `test_generate_joseki.py`
- `test_joseki_problems_client.js`
- `sgf_lib.py` e `import_my_collections.py` (si han cambiado)

(El HTML ya lo tengo: `tsumevault-20261109-1251`.)

## Checkpoint de entrega (9-nov-2026)

- **Generador**: `TVALERT` en cada jugada del jugador para la que se escribe «→ Ahora: …» o
  «→ ¿Y si…? …» (misma función `instruction()`; se calcula sin repetir los errores de `need`).
  - `test_generate_joseki.py`: **135 checks OK** (128 + 7 de AV). Auditoría sobre todos los
    problemas de prueba y tu 4-4 real: cada instrucción tiene su marca en la jugada esperada,
    con el mismo tipo y nombre, y no hay marcas sin instrucción; nunca en la raíz, en WRONG ni
    en jugadas del rival; nombre con `]` escapado y legible por `sgf_lib`.
  - **Comparación con el código actual**: mismos 194 problemas, ids, rutas, capítulos, orden,
    payload, errores y avisos; el contenido solo cambia por `TVALERT` (quitándolo, byte a byte igual).
  - Tus maestros: llevan marca **10 de 21** problemas del 3-4 y **44 de 68** del 4-4 (salen como
    «cambiados» al regenerar; el SM-2 se conserva porque el id no cambia).
- **Cliente** (`tsumevault.html`, 65 líneas más):
  - `choiceAlertOf` (pura) y `CHOICE_ALERT_MS = 1200`; `SFX.choice` → `audio/variant.mp3`.
  - Dentro de `setupInteractiveMode`: `maybeChoiceAlert` / `clearChoiceAlert`, ganchos al
    empezar, tras la jugada del rival, en Back, Restart y salida de Explorar; bloqueo de clics;
    clase `board-choice` y destello `show choice` (26 px, fondo oscuro, nombre completo).
  - Los 8 reinicios de borde existentes (`remove('board-ok','board-bad')`) quitan también el azul.
  - CRLF intactos (7978, sin CR sueltos); `node --check` OK; **`harness_bundle.js` idéntico**.
- **`test_joseki_problems_client.js`**: **55 checks OK** (32 + 23 de AV).
  - Entorno simulado puesto al día con el HTML actual (`ghostMode`, Focus, `totalPaused`), con
    `classList` real, `querySelector` memoizado y `clearTimeout` que cancela de verdad.
  - Corregido de paso: `start()` sacaba siempre negro (leía `root.properties`, que con WGo no
    existe); ahora usa `PL[...]`.
  - Casos: aviso al empezar y a mitad (tras un pase del rival, tipo ¿y si?); bloqueo y fin del
    bloqueo; borde que se va al jugar; Back y Restart repiten; repintar conserva el borde sin
    sonido; Explorar lo quita y al salir vuelve solo el borde; problema sin marca no avisa;
    el temporizador de un problema anterior no toca el siguiente.
- `test_joseki.js` **109 OK** y `test_joseki_lib.py` **59 OK**, sin cambios.
- **Mutaciones: 18/18 detectadas** (14 del cliente, 4 del generador).
