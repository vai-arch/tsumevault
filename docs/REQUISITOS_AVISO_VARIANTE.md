# REQUISITOS — Aviso de posición de elección (AV)

Estado: **REQUISITOS FUNCIONALES CERRADOS** (9-nov-2026) — siguiente paso: diseño.
La decisión técnica (cómo se marca la posición en el problema) se toma después, en el diseño.

## Motivación

En los problemas generados de joseki hay posiciones en las que el problema espera una
variante concreta entre varias posibles. La instrucción ya va en el comentario
(«→ Ahora: …», «→ ¿Y si…? …»), pero en la práctica no siempre se lee. Hace falta un aviso
visual y sonoro que obligue a parar y fijarse antes de jugar.

## Definiciones

- **AV-01 Posición de elección**: posición en la que le toca jugar al jugador y el problema
  espera una variante concreta. Hay dos tipos:
  - **Bifurcación**: en el maestro, el jugador tiene 2 o más jugadas buenas en ese punto.
  - **¿Y si?**: la jugada esperada es una rama ¿y si? (IT) del maestro.
- **AV-02 Marca**: cada posición de elección va marcada en el problema, junto con su tipo y
  el nombre de la variante. El aviso funciona con **cualquier problema** que lleve la marca,
  de cualquier source; hoy solo la llevarán los problemas de la source `joseki`.

## Cuándo salta

- **AV-03** El aviso salta en el momento en que la posición de elección queda lista para jugar:
  - al **cargar el problema**, si la primera jugada del jugador ya es de elección;
  - **a mitad del problema**, justo después de que el rival haya jugado (piedra y sonido de
    piedra incluidos).
- **AV-04** Tras un **salto de variante** (alternativas del rival, T24), si la posición a la que
  se llega es de elección, el aviso salta igual.
- **AV-05** **Back** y **Restart** que devuelven a una posición de elección **repiten el aviso
  completo** (borde, destello, sonido y bloqueo).
- **AV-06** **Redimensionar o repintar** el tablero conserva el borde azul, sin destello ni sonido.

## Cómo es

- **AV-07 Borde azul**: el tablero se enmarca con un borde azul, distinto del verde (acierto)
  y del rojo (fallo). Se mantiene mientras siga la posición de elección y desaparece en cuanto
  el jugador juega; a partir de ahí los bordes verde y rojo funcionan como siempre.
- **AV-08 Destello**: en el centro del tablero aparece durante **1,2 s** un destello con un
  símbolo y el **nombre de la variante**, al estilo del ✓ de las transiciones de variante:
  - bifurcación: `⑂ <nombre>` (p. ej. «⑂ Low Enclosure»);
  - ¿y si?: `? <nombre>` (p. ej. «? Corner Hane»).
- **AV-09 Bloqueo**: mientras el destello está visible, los clics en el tablero se ignoran:
  no ponen piedra, no cuentan como fallo y no suenan. Al desaparecer el destello se puede jugar.
- **AV-10 Sonido**: suena `variant.mp3`, el mismo sonido de las transiciones de variante (T26).
  Respeta el interruptor y el volumen generales de sonido. Se registra como un sonido propio
  del aviso que hoy apunta a ese fichero, para poder cambiarlo más adelante sin tocar código.
- **AV-11 Comentario**: sin cambios; la caja de comentario sigue mostrando la instrucción.

## Dónde

- **AV-12 Modos**: Run, Review, Free y Focus (que usa Free), con el mismo comportamiento.
- **AV-13 Compatibilidad**: los fantasmas de Free (T37), la pista y el tiempo del intento siguen
  como hoy. El tiempo del destello cuenta en el tiempo del intento, como cualquier otro.
- **AV-15 Explorar (Free, T31)**: al entrar en Explorar el borde azul se oculta; al salir, si
  sigue la posición de elección, vuelve el borde sin destello ni sonido.

## Lo que no cambia

- **AV-14 Fallo**: en una posición de elección, jugar otra cosa es fallo, como hoy. El problema
  solo contiene la variante buscada y las jugadas malas o dudosas como WRONG; las otras jugadas
  buenas del maestro no están en el problema.

## Fuera de alcance

- Tratar la otra jugada buena como «válida, pero se busca otra variante» sin penalizar.
- Un ajuste para activar o desactivar el aviso.
- Avisos para otras situaciones (contexto, castigo tras doble error de JP.6, tenuki propio).

## Decisiones (9-nov-2026)

- Duración del destello y del bloqueo: 1,2 s.
- Sonido: se reutiliza `variant.mp3`. En los problemas de joseki no hay hoy transiciones de
  variante (el rival tiene una sola respuesta), así que no coinciden los dos usos.
- Símbolos `⑂` (bifurcación) y `?` (¿y si?).
- Explorar: AV-15.

## Para el diseño (decisión técnica)

Cómo se marca la posición en el problema (AV-02). Inclinación: una propiedad propia en el SGF
generado, escrita por `generate_joseki_problems.py` en el nodo donde toca elegir, con tipo y
nombre; mejor que parsear el texto «→ Ahora:», que depende de la redacción del comentario.
