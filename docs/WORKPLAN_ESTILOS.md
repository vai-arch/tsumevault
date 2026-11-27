# WORKPLAN — Estilo de tablero por sección y estilo plano (tipo kifumaster)

Requisito en Notion: «Estilo de tablero por sección y estilo plano tipo kifumaster» (27-nov-2026).
Estado: **análisis cerrado, pendiente de visto bueno de Victor para empezar E1**.

## Decisiones (Victor, 27-nov)

- Cada sección con tablero tiene su estilo; hay un **estilo por defecto** y **excepciones opcionales** por sección.
- Secciones: **Problemas** (Collections, Focus, Free y Review juntas), **Games**, **Joseki**, **Play** y **Archivo**.
- **Lecciones (player.html) queda fuera**: tiene su propio tablero, aparte del código compartido.
- Solo lo visual: fondo del tablero y piedras. El sonido sigue siendo global.
- Se añade un **estilo plano** inspirado en kifumaster, hecho con código propio:
  - «Piedras planas» es un juego de piedras más y se combina con cualquier fondo (maderas incluidas).
  - Se añaden fondos lisos a la lista de fondos (el verde salvia `#C8D1B0` y algún otro).
  - **Descolocación** de las piedras: **apagada por defecto**, configurable. Cuando está encendida es fija: cada piedra se descoloca siempre igual según su posición, no baila al repintar.

## Cómo está hoy

- `js/board_core.js` lee el fondo (`board_background`) al cargar, por eso el archivo ya lo aplica.
- El juego de piedras (`img/stones/stones.json` + `stone_set_label`) se carga y restaura en `loadVisualConfig()` dentro de `tsumevault.html`: **el archivo no lo aplica** (siempre piedras realistas).
- Todo se guarda en `localStorage`: es por dispositivo, no se sincroniza (igual que ahora).
- Un único tablero WGo (`wgoBoard`, en canvas) para todas las pestañas; `initBoard()` lo crea con `background` y `stoneHandler`.

## Fases

### E1 — Estilo de tablero compartido (arregla el archivo)
- Mover a `board_core.js` la carga de `boards.json` / `stones.json` y la restauración de la elección guardada.
- `archive.html` la usa: el archivo muestra las piedras elegidas en ⚙.
- Sin cambios visibles en `tsumevault.html`. Desplegable por sí sola.

### E2 — Estilos por sección
- Modelo guardado en `board_style_v1` (JSON): `{ default: {bg, stones, jitter}, problems: {...}|null, games, joseki, play, archive }`.
- Migración: si no existe, se crea el `default` a partir de `board_background` y `stone_set_label` actuales. Nadie ve cambio al desplegar.
- `boardStyleFor(sección)`: devuelve la excepción de la sección o el estilo por defecto (función pura, con tests).
- `tsumevault.html` sabe su sección por la pestaña activa (collections, focus, free y review → problems). Al cambiar de pestaña, si el estilo es distinto, se repinta el tablero con el nuevo estilo sin perder la posición.
- ⚙: selector «Aplicar a:» (Todas por defecto / Problemas / Games / Joseki / Play / Archivo), preseleccionado con la sección desde la que abres ⚙, y botón «Usar el de por defecto» para quitar la excepción.
- El archivo no tiene ⚙: su estilo se elige desde ⚙ de la app con «Aplicar a: Archivo».

### E3 — Estilo plano
- Juego de piedras «Planas» dibujado en canvas: color plano, radio algo menor que la casilla (queda una rendija entre piedras vecinas), blancas con borde fino, sombra propia (círculo algo mayor, desplazado abajo a la derecha, degradado suave).
- Fondos lisos nuevos en la lista de fondos (verde salvia y otros a elegir al verlos).
- Opción «Descolocar piedras» por estilo (apagada por defecto); desplazamiento fijo calculado a partir de la posición.
- Sombra suave bajo el tablero en el estilo plano.
- Validar a la vista con capturas y ajustar colores y medidas con Victor.

## Validación
- Tests unitarios: `boardStyleFor`, migración desde las claves antiguas, desplazamiento fijo (mismo resultado siempre, dentro del límite).
- Batería completa (`run_all`) sin cambios en las líneas base.
- Chrome sin ventana: capturas de cada sección con estilos distintos; cambio de pestaña repinta con el estilo correcto; el archivo aplica su estilo.
- Checklist manual en portátil y móvil.
