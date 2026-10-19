# Procedimiento: curso nuevo de Awesome Baduk, con lecciones y problemas, hasta la web

Documento de trabajo (estado a 9 de octubre de 2026; actualizado el 19 de octubre de 2026 con el dibujo a mano,
la corrección de lecciones ya publicadas y los permisos tras subir). Cubre todo el camino de un curso nuevo:
bajarlo, convertir sus lecciones y sus problemas, corregir lo que haga falta, validarlo, probarlo en local
y subirlo a producción.

Complementa a `PROCEDIMIENTO_curso_nuevo_awesome_baduk.md`, que describe la conversión de **lecciones**
(vídeo/audio/tablero) con más detalle. Este documento añade los **problemas** de las lecciones, el parche del
catálogo, los cambios hechos al flujo de audio y el despliegue completo. Donde dice «ver el otro procedimiento»
es porque ese tramo no se repite aquí. **Si hay contradicción, manda este documento** (es posterior).

---

## 0. Resumen del flujo

```
 A. LECCIONES (ver el otro procedimiento)
    export lessons.json  ->  awesome_to_player.py  ->  lessons + all_lessons.new.json + lesson_ids.json
         |
 B. PROBLEMAS DE LAS LECCIONES
    lesson_problems.json  ->  lecciones_problemas.py plan  ->  lecciones_problemas.py
         ->  salida_awesome_lessons\  ->  copiar a ..\..\awesome_lessons\  ->  validar  ->  importar en local
         |
 C. CATALOGO DE LECCIONES
    parchear_catalogo.py  ->  merge_lessons.py  ->  all_lessons.json
         |
 D. PRODUCCION
    SGF por git  ->  tsumevault.html  ->  importar en el servidor  ->  subir all_lessons.json  ->  subir lecciones
```

Orden obligatorio en producción: **primero los SGF y la web, después la importación en la base de datos**
(si no, la base de datos apuntaría a ficheros que todavía no existen).

Para **corregir lecciones ya publicadas** sin reconvertir el audio (tras arreglar el conversor), ver la
sección 11.

---

## 1. Carpetas y ficheros

Raíz del proyecto: `C:\Users\victor.diaz\Documents\All\Go\tsumevault`

| Ruta | Qué es |
|---|---|
| `_sources_scripts\awesome_baduk\` | Scripts de trabajo (esta carpeta, con «e»). Todos los comandos de este documento se lanzan desde aquí salvo que se indique lo contrario. |
| `_sources_scripts\awesome_baduk\problems_raw\` | Caché de problemas descargados (`<id de 20 caracteres>.json`). Compartida con la serie Level. Reanudable. |
| `_sources_scripts\awesome_baduk\salida_awesome_lessons\` | Salida del generador (colecciones, capítulos, SGF). Se puede borrar y regenerar. |
| `awesome_lessons\` (raíz del proyecto) | Copia de la salida que se valida, se importa y se sube por git. |
| `player\lessons\Awesome Baduk\` | Ficheros de las lecciones convertidas (`.sgf`, `.json`, `.ogg`). |
| `player\lessons_sources\awesome_baduk_lessons.json` | Catálogo de las lecciones de Awesome Baduk (formato `{"rows": [...]}`). |
| `player\lessons_sources\awesome_baduk_lessons_ids.json` | **`lesson_ids.json` de verdad** (curso/clip → `lessonId`). Se pasa al conversor con `--ids`. Si se pierde, cambian todos los `lessonId`: guardarlo en git. |
| `player\all_lessons.json` | Catálogo unido que lee `player.html`. Se genera con `merge_lessons.py`. |
| Servidor | `root@46.225.97.185`, ruta `/opt/tsumevault/player` |

### Scripts

| Script | Para qué | Notas |
|---|---|---|
| `awesome_to_player.py` | Convierte lecciones del export al formato del player (`.sgf`, `.json`, `.ogg` y `_draw.json`). Contiene `difficulty_from_group` (regla de niveles) y `load_course`. | Origen único de la regla de niveles. Versión v30. Modos `--draw-only` y `--board-only` en la sección 11. Se detiene si no hay `lesson_ids.json` con contenido (salvo `--new-ids`). |
| `diag_ocupadas.py` | Solo lectura: lista las jugadas sobre punto ocupado de un curso (instante, punto, piedra que ya había, eventos previos). | Usa el `awesome_to_player.py` de la misma carpeta. |
| `compare_board.py` | Solo lectura: compara lo que se ve en el tablero entre lo publicado y lo regenerado con `--board-only`. | Sección 11. |
| `census_draw.py` | Censo de los `draw-events` de `lessons.json` (tipos, colores, rango de coordenadas). | Confirmó el lienzo de 600×600. |
| `recorded_quitar_draw.py` | Quita de `recorded.json` las lecciones con dibujo, para volver a grabarlas en vídeo. | Hace copia `.bak`. |
| `_subir_draw.bat` | Sube solo `*_draw.json` (se niega si hay otra cosa) y hace el `chmod`. | Origen por defecto `draw_out\lessons`; otro como argumento. |
| `_subir_board.bat` | Sube solo `<id>.sgf` y `<id>.json` regenerados con `--board-only` y hace el `chmod`. | Origen por defecto `board_out\lessons`. |
| `extract_lesson_problems.py` | De `lessons.json` saca `lesson_problems.json` (clip → ids de problemas). | |
| `lecciones_problemas.py` | Descarga, convierte y organiza los problemas de las lecciones en la source `awesome_lessons`. | Modo `plan` sin red. |
| `parchear_catalogo.py` | Rellena dificultades vacías y quita cursos/lecciones sobrantes del catálogo. | Idempotente. |
| `niveles_academia.py` | Serie Level. De aquí `lecciones_problemas.py` reutiliza `descargar`, `ya_descargado` y la caché. | No se ejecuta aquí. |
| `convert_problems.py` | `problem_to_sgf`: EDN a SGF. | **Modificado**: ignora nodos sin `:move` (ver sección 8). |
| `list_inventory.py` | `login()`; lleva la clave de API en claro. | No subir a un repositorio público. |
| `analyze_all.py` | `parse_edn`. | |
| `..\..\import_my_collections.py` | Valida e importa una carpeta de colecciones en el servidor. | Opciones `--source`, `--sgf-prefix`, `--server`, `--token`, `--validate-only`. |
| `importar_awesome_lessons_prod.bat` | Validar, pedir confirmación e importar en producción. | Ver sección 6. |
| `..\..\player\merge_lessons.py` / `merge_lessons.bat` | Une los catálogos de las fuentes en `all_lessons.json`. | Hace copia con fecha del anterior. |
| `_subir_lecciones_a_Hetzner.bat` | Sube las lecciones (carpeta `Awesome Baduk` o un curso) y `all_lessons.json`. | Ver el otro procedimiento. **Debe terminar con el `chmod` de la sección 6.** |
| `remove_source.py` | Borra todas las filas de una source en la base de datos. | Marcha atrás de una importación. |
| `download_vimeo_batch.py` | Baja los audios (`.m4a`) de Vimeo a `out\cursos\<curso>\`. | **Parcheado** con `--skip-catalog` (ver sección 3). |
| `parche_download_vimeo.py` | Aplica ese parche a `download_vimeo_batch.py` (idempotente, con copia `.bak`). | Ya aplicado; se conserva por si se restaura el original. |
| `build_final_collection.py` | Copia de `out\cursos` a `out\cursos_final` solo los audios que usan los clips. | Escribe también `cursos.csv`, `report.json`, `course.json`. |
| `find_chapters.py` | Vuelca los cursos de Firestore a `find_chapters_dump.json` (= `lessons.json`). | Necesita `list_inventory.py`, `analyze_all.py` y el token. |
| `census_courses.py`, `inspect_clip.py` | Censo de cursos (estado de cada uno) e inspección de un clip. | Ver el otro procedimiento. |
| `convertir_audios.bat` | Conversión de audio (llama a `--audio-root out\cursos_final --convert-audio`). | No revisado en detalle. |

`lecciones_problemas.py` importa a su vez `niveles_academia`, `convert_problems`, `analyze_all`,
`list_inventory` y `awesome_to_player`: tienen que estar todos en la misma carpeta.

### Secretos (no subir a git ni pegar en ningún chat)

- `awesomebaduk_rt`: refresh token de la sesión de Awesome Baduk. Necesario solo para descargar.
- `list_inventory.py`: contiene la clave de API en claro.
- `TSUMEVAULT_TOKEN`: variable de entorno con el token del servidor de TsumeVault.
- El repositorio de GitHub es público: los SGF de `awesome_lessons` salen de un sitio de pago; es una decisión
  tomada, igual que con `my_collections`.

---

## 2. Reglas y convenciones (las decisiones ya tomadas)

### 2.1 Nivel de un curso

El nivel sale de `target-group` con `awesome_to_player.difficulty_from_group` (acepta mayúsculas, espacios,
`_` y `-`, así que `group-D` es lo mismo que `group-d`).

| Nivel | `target-group` | Rango en la web | Colección | Marcador de dificultad |
|---|---|---|---|---|
| 0 | `group-all` | todos los niveles | `Lessons 0 - All levels` | `difficulty-30k` |
| 1 | `group-beginners` | sin rango | `Lessons 1 - Beginners` | `difficulty-20k` |
| 2 | `group-d` | 10K-15K | `Lessons 2 - Group D` | `difficulty-12k` |
| 3 | `group-c` | 6K-9K | `Lessons 3 - Group C` | `difficulty-8k` |
| 4 | `group-b` | 1K-5K | `Lessons 4 - Group B` | `difficulty-3k` |
| 5 | `group-a` | 1D-5D | `Lessons 5 - Group A` | `difficulty-3d` |

- En el catálogo de lecciones el nivel 0 va como **texto `"0"`**: el player trata el número 0 como
  «sin dificultad» y no lo cuenta en el filtro.
- En TsumeVault el marcador se convierte con `2100 - 100*n` (kyu) o `2000 + 100*n` (dan): `30k` da -900. Se probó
  y la web lo muestra bien como «30k».
- Los rangos en kyu son el punto medio redondeado de lo que indica la web. Si se cambian, hay que editar el
  diccionario `DIFFICULTY` de `lecciones_problemas.py`.

### 2.2 Cursos sin `target-group`

Regla acordada: **toman el nivel del primer curso de su serie; si no pertenecen a ninguna serie, nivel 0.**
Se declaran a mano, por `courseId`, en dos sitios que deben mantenerse iguales:

- `SIN_GRUPO` en `lecciones_problemas.py` (colecciones de problemas).
- `DIFICULTAD` en `parchear_catalogo.py` (catálogo de lecciones).

Para que el filtro por nivel del player y la colección de problemas muestren los mismos cursos, las dos
tablas deben dar el mismo nivel a cada curso. Estado actual: 12 cursos (9 con problemas más 3 partidas
profesionales).

### 2.3 Cursos descartados

- Curso duplicado con audio incompleto: `f8SCiKxyZ2lEGDARMP1H` (`Where are my Ko threats?`), se conserva
  `Ejwk2Zg0c0HQBTgLDkqW`. Constante `DESCARTAR` en `lecciones_problemas.py` y entrada en `QUITAR_CURSOS` de
  `parchear_catalogo.py`.
- Cursos de relleno quitados del catálogo: `Test` (`4FMUbz3OOMUipXZ9v6gl`) y los `New course` vacíos
  (`1mN2oDp7QXiVE0KH89IX`, `luwirvB0TxmtvSNuFoxh`).
- Los ficheros de las lecciones quitadas **se dejan en el servidor**; solo se quitan del catálogo.

### 2.4 Estructura de la source `awesome_lessons`

```
awesome_lessons\
  Lessons 3 - Group C\                      <- una colección por nivel
    <titulo del curso>\                     <- un capítulo por curso
      difficulty-8k                         <- marcador (fichero vacío), uno por capítulo
      01_<id8>.sgf, 02_<id8>.sgf, ...       <- problemas en orden de clip
```

- Nombre del capítulo = título del curso limpiado: `/` pasa a ` - `, se quitan `< > : " \ | ? * ` y
  caracteres de control, espacios colapsados, límite de **120 caracteres** (`LIMITE_NOMBRE`). No se pretende
  que coincida letra por letra con el título del player (`?` y `:` no se pueden conservar); sí que el número de
  parte de una serie (`... 1`, `... 2`) no se pierda, de ahí el límite alto.
- Nombre del fichero: `NN_<8 primeros caracteres del id>.sgf`; el número cuenta todos los problemas del curso
  en orden de clip (con huecos si alguno se omite).
- Un problema sin ninguna hoja `RIGHT` **no se genera** (diagramas sin solución o solo respuestas incorrectas).
- Todos los SGF llevan `CA[UTF-8]`; las hojas, `C[RIGHT]` o `C[WRONG]`; la `description` del sitio va como
  comentario del nodo raíz (sin el «Black/White to play» inicial o final).
- Sin tamaño de tablero en el origen se asume 19 (misma lógica que la serie Level).
- **La identidad de un problema en TsumeVault sale de su ruta.** No renombrar ni mover colecciones, capítulos
  ni ficheros ya importados.

### 2.5 Enlace lección ↔ problemas

`awesome_lessons_links.json` guarda, por curso, su colección y capítulo, y por cada clip su `lessonId`,
`vimeoId` y los problemas con el fichero SGF generado (`null` si se omitió). El player no lo usa todavía;
se conserva por si se quiere un botón de la lección a sus problemas. No subir a git.

### 2.6 Dibujo a mano del profesor

- Cada clip con tinta lleva un `<id>_draw.json` junto a su `.json`. El player lo pide como los subtítulos: si
  no existe, no pasa nada. 283 clips de 1.557 tienen dibujo.
- Formato: `{"size": 600, "strokes": [{"t": s, "c": "#color", "p": [[dt, x, y], ...]}], "clears": [s, ...]}`.
  `t` y `clears` en segundos, en el mismo eje que el audio; `x, y` en píxeles de un lienzo de 600×600 que ocupa
  todo el tablero.
- Solo se guardan los puntos con tinta (entre `start-drawing` y `stop-drawing`). Un trazo sin `set-color` previo
  en su clip toma `#f44336` (el rojo, que es el color mayoritario).
- Un trazo que empieza en el mismo instante que un borrado posterior no se guarda: es el dibujo del clip anterior,
  que la web restaura en t=0 y borra en t=0 (v30).
- En el player, el lienzo del dibujo va dentro de `#board` con `z-index: 1000` (WGo usa 100/200/300 en sus capas),
  para quedar por encima de las piedras y entrar en el vídeo grabado.

---

## 3. Fase A. Lecciones (export, audio, conversión)

Detalle y opciones del conversor: `PROCEDIMIENTO_curso_nuevo_awesome_baduk.md`. Aquí, el flujo con los cambios
posteriores. `$W` = `_sources_scripts\awesome_baduk`, `$P` = `player` (ambos bajo la raíz del proyecto).

1. **Export `lessons.json`** en `$W` (todos los cursos; se sustituye en cada actualización). Se obtiene con
   `find_chapters.py`, que vuelca a `find_chapters_dump.json` las colecciones `courses`, `josekichallenge26` y
   `auto-challenges` de Firestore con los documentos completos (clips, eventos, `vimeo-ids`, `problems`...). Ese fichero
   **es** `lessons.json` (493 documentos con claves `courses/<idCurso>` en la última versión comprobada):

   ```powershell
   Copy-Item lessons.json "lessons.json.bak-$(Get-Date -Format yyyyMMdd)"    # copia del anterior
   python find_chapters.py                                                   # necesita awesomebaduk_rt (login)
   Move-Item -Force find_chapters_dump.json lessons.json
   ```

   `find_chapters.py` imprime además un listado de colecciones «Chapter» que aquí no interesa. Confirmado: `lessons.json`
   es `find_chapters_dump.json` con el nombre cambiado a mano. La lectura de la API es de solo lectura.
2. **Localizar el curso nuevo**: `python census_courses.py lessons.json --out census_nuevo --delimiter ";"` y
   mirar la columna `Estado` (otro procedimiento, sección 2). `inspect_clip.py` sirve para mirar un clip concreto.
3. **Descargar el audio** (solo los `vimeo-ids` que usa algún clip):

   ```powershell
   python download_vimeo_batch.py lessons.json -o out --ytdlp "<ruta a yt-dlp.exe>" --skip-catalog ..\..\player\lessons_sources\awesome_baduk_lessons.json
   ```

   - `--skip-catalog` **hay que ponerlo siempre**. Salta los audios cuyo id de Vimeo ya es el `sourceVimeoId`
     de una lección publicada. Sin él, el script volvería a bajar todos los audios antiguos, porque ya no están
     en disco (ver «Estado de `out`» más abajo).
   - La opción la añade `parche_download_vimeo.py`. Si se restaurara el original, volver a aplicarlo
     (`python parche_download_vimeo.py`; si ya está aplicado, no hace nada).
   - Los audios de las 6 lecciones quitadas del catálogo no están en la lista y se volverían a bajar: son pocos.
4. **Preparar los audios para convertir**: `python build_final_collection.py lessons.json --delimiter ";"`.
   Copia a `out\cursos_final` solo los usados. Su resumen (`Totales: {...}`) contará como `missing` todos los clips
   antiguos, cuyo audio ya no está en disco; **mirar solo los del curso nuevo** (en `report.json`).
5. **Convertir el curso** (siempre con `--only`, siempre la misma carpeta de salida):

   ```powershell
   python awesome_to_player.py lessons.json --out player_test\player --ids ..\..\player\lessons_sources\awesome_baduk_lessons_ids.json --manifest-copy --audio-root out\cursos_final --convert-audio --require-audio --only "<título o id del curso>"
   ```

   - **`--only` es obligatorio**: sin él, el conversor intentaría procesar todo el export y los clips antiguos
     no tienen ya su `.m4a` en `cursos_final`.
   - `--ids` apunta al `lesson_ids.json` de verdad, en `player\lessons_sources\awesome_baduk_lessons_ids.json`. El
     conversor le añade los clips nuevos al terminar. Sin `--ids` buscaría `player_test\player\lesson_ids.json`, y
     esa carpeta ya se ha vaciado alguna vez: desde la v22 el conversor se **detiene** si no encuentra un
     `lesson_ids.json` con contenido, en lugar de repartir IDs desde 900000 y chocar con los publicados.
     `--new-ids` solo para empezar de cero.
   - `--out player_test\player` es siempre el mismo: ahí vive `all_lessons.new.json`, que **acumula** (antiguas +
     nuevas).
   - Salida: `player_test\player\lessons\Awesome Baduk\<Curso>\Clip NN\<id>.sgf|.json|.ogg`, más `<id>_draw.json`
     en los clips con dibujo.
   - `--ffmpeg "<ruta>"` si ffmpeg no está en el PATH.
6. **Probar en local** (otro procedimiento, sección 6): carga, suena, el tablero sigue a la voz, dificultad no vacía.
7. **Copiar a la carpeta real**:

   ```powershell
   robocopy "$W\player_test\player\lessons\Awesome Baduk\$curso" "$P\lessons\Awesome Baduk\$curso" /E
   Copy-Item -Force "$W\player_test\player\all_lessons.new.json" "$P\lessons_sources\awesome_baduk_lessons.json"
   ```

8. **Inmediatamente después, `parchear_catalogo.py` (Fase C).** La copia de `all_lessons.new.json` del paso 7
   machaca el catálogo y borra el parche: reaparecen las dificultades vacías y las lecciones quitadas.

El `lessonId` de un clip (los de 900000 en adelante) es lo que une la lección con sus problemas en
`lesson_problems.json`.

### Estado de `out` (9-oct-2026)

- `out\cursos`: sin los `.m4a` de las lecciones publicadas (se borraron los 900 sobrantes de la primera pasada y los
  1.536 usados). Contiene los `.json`, el `.log` y el `.csv` de las descargas.
- `out\cursos_final`: sin `.m4a`; solo `cursos.csv`, `report.json` y los `course.json`. Se regenera con el paso 4.
- Los `.ogg` que sirve la web están en `player\lessons\Awesome Baduk`; los `.m4a` ya no hacen falta para el player.
- Si hubiera que **reconvertir** una lección antigua (otra calidad, por ejemplo), habría que volver a bajar su
  audio: ejecutar la descarga **sin** `--skip-catalog`, con un export reducido a ese curso (sin la opción el script
  intenta bajar todos los audios que falten), y repetir los pasos 4 y 5.

---

## 4. Fase B. Problemas de las lecciones

Todos los comandos, desde `_sources_scripts\awesome_baduk`.

### B1. Generar `lesson_problems.json`

```powershell
python extract_lesson_problems.py lessons.json --ids ..\..\player\lessons_sources\awesome_baduk_lessons_ids.json --out lesson_problems.json
```

Imprime clips totales, clips con problemas, cursos, referencias, ids distintos y entradas sin `lessonId`.
Referencia (9-oct-2026): 1.557 clips, 1.178 con problemas, 444 cursos, 5.586 ids distintos, 5 entradas sin
`lessonId`. Un id que aparezca en más de un clip sería una sorpresa y habría que mirarlo.

### B2. Plan (sin red, sin login)

```powershell
python lecciones_problemas.py plan
```

Escribe `plan_awesome_lessons.txt` y muestra el resumen. Qué mirar:

| Línea del plan | Qué hacer si no es lo esperado |
|---|---|
| `cursos SIN nivel (no se generan)` con algún curso | Es un curso nuevo sin `target-group`. Decidir su nivel con la regla 2.2 y añadirlo a `SIN_GRUPO` (y a `DIFICULTAD` de `parchear_catalogo.py`). Repetir el plan hasta que salga vacío. |
| `capitulos renombrados por llamarse igual` | Dos cursos con el mismo título en el mismo nivel. Mirar si son cursos distintos o un duplicado (comparar `vimeoId` en `lesson_problems.json`). Si uno está mal, añadirlo a `DESCARTAR` y a `QUITAR_CURSOS`. |
| `capitulos recortados por LONGITUD` | Un nombre supera 120 caracteres. Subir `LIMITE_NOMBRE` o aceptarlo. |
| `clips sin lessonId` | Clips que no se convirtieron como lección (sin audio, p. ej.). Se generan igual, sin enlace a lección. |
| Totales por nivel | Comprobar que cuadran con los cursos nuevos esperados. |

### B3. Descargar y convertir

```powershell
python lecciones_problemas.py
```

- Pide el login (necesita `awesomebaduk_rt` en la carpeta).
- Reanudable: lo que ya está en `problems_raw` no se baja. Se puede parar con Ctrl+C.
- **Ejecutarlo siempre con todos los niveles** (sin argumento): `awesome_lessons_links.json` se reescribe con
  lo procesado en esa ejecución, y con un solo nivel se quedaría con un fichero parcial.
- Borra y regenera las carpetas de colección dentro de `salida_awesome_lessons`.
- Al final imprime: ficheros escritos, tamaños de tablero, hojas `RIGHT`/`WRONG`, omitidos y avisos.
  Referencia de la primera carga completa: 5.573 SGF escritos de 5.578 problemas.

### B4. Revisar el informe

```powershell
Get-Content informe_awesome_lessons.txt
```

Casos conocidos y qué significan:

| Línea | Significado | Acción |
|---|---|---|
| `OMITIDO, diagrama sin soluciones` / `sin ninguna hoja RIGHT` | El problema no se puede resolver. | Ninguna. Decisión tomada: excluirlos. |
| `problema XXXXXXXX sin descargar` + `error ...: HTTP 404` | El curso referencia un problema que ya no existe en el sitio. | Ninguna (reintentar no sirve). Queda `file: null` en el fichero de enlaces. |
| `NO CONVERTIDO (':move')` | Nodo sin jugada en el árbol. Ya corregido en `convert_problems.py`. | Si reaparece con otra causa, subir el JSON de `problems_raw` y analizarlo. |
| `primera jugada del color contrario` | Rama que empieza con el color que no mueve. | Ver B5: el importador lo trata como ERROR. |

### B5. Copiar a la raíz del proyecto

Primera vez: la carpeta no existe, se puede copiar entera. Cursos nuevos después: copiar **sin borrar** lo que ya
hay (no usar `/MIR`):

```powershell
robocopy salida_awesome_lessons ..\..\awesome_lessons /E
```

(`robocopy` devuelve códigos 0 a 7 cuando todo va bien.)

**Atención:** al regenerar, vuelven a aparecer los SGF que el importador rechaza y que se borraron a mano.
Hoy son estos dos, del curso `the shapes are all related! End Game lecture!`:

```powershell
Remove-Item "..\..\awesome_lessons\Lessons 5 - Group A\the shapes are all related! End Game lecture!\06_Y1jrdM2g.sgf", "..\..\awesome_lessons\Lessons 5 - Group A\the shapes are all related! End Game lecture!\09_KPYi1Doy.sgf"
```

Son problemas con una rama inicial del color contrario (`B[os]` cuando mueve blanco); se decidió no cargarlos.
Si aparecen otros con el mismo error, decidir caso a caso (borrar o corregir la rama).

### B6. Validar

```powershell
python ..\..\import_my_collections.py ..\..\awesome_lessons --source awesome_lessons --sgf-prefix awesome_lessons --validate-only
```

No contacta con ningún servidor. Debe terminar con `0` ERRORS y `0` BROKEN y la línea
`N problem(s) ready to load`. `--force` solo levanta el bloqueo de los BROKEN; **no sirve con ERRORS**: hay
que borrar o corregir esos ficheros. El aviso `WRONG comment but still has children` es informativo. Referencia:
5.571 problemas en 6 colecciones, 1 aviso.

### B7. Importar en el servidor local y comprobar

Con el servidor local en marcha (puerto 3002; la base de datos local es una copia de pruebas):

```powershell
python ..\..\import_my_collections.py ..\..\awesome_lessons --source awesome_lessons --sgf-prefix awesome_lessons
```

La respuesta debe ser `200`. Referencia de la primera carga: `collections 6, chapters_new 443,
problems_upserted 5571`. En cargas posteriores, los capítulos que ya existían salen en `chapters_updated`.

Comprobar en la web local (Ctrl+F5 y sincronizar): elegir `awesome_lessons` en el desplegable, ver las seis
colecciones con sus dificultades (30k, 20k, 12k, 8k, 3k, 3d), abrir un capítulo del curso nuevo y resolver
algún problema.

---

## 5. Fase C. Catálogo de lecciones

### C1. Parche

```powershell
python parchear_catalogo.py --dry-run
python parchear_catalogo.py
```

- Rellena `lessonDifficulty` donde está vacío usando `DIFICULTAD`; **no sobrescribe** una dificultad ya
  existente (avisa si es distinta).
- Quita los cursos de `QUITAR_CURSOS` y las lecciones de `QUITAR_LECCIONES`.
- Al final imprime `lecciones que siguen sin dificultad`: debe ser **0**. Si no lo es, hay un curso nuevo sin
  `target-group` que falta en la tabla.
- Hace copia con fecha del catálogo antes de escribir. Es seguro volver a ejecutarlo; hay que hacerlo cada vez que
  se regenere el catálogo desde `all_lessons.new.json`, porque el conversor no conoce estas excepciones.

Referencia del primer parche: 29 lecciones con dificultad fijada en 12 cursos, 6 filas quitadas (1.542 → 1.536).

### C2. Merge

Desde `player` (`cd ..\..\player`):

```powershell
python merge_lessons.py lessons_sources\guo_juan_lessons.json lessons_sources\awesome_baduk_lessons.json --out all_lessons.json --dry-run --check-files lessons --check-source awesome
python merge_lessons.py lessons_sources\guo_juan_lessons.json lessons_sources\awesome_baduk_lessons.json --out all_lessons.json
```

El `--dry-run` con `--check-files` debe decir que todas las lecciones tienen `.sgf`, `.json` y `.ogg`.
Quitar filas del catálogo no da error en el merge. Referencia: 1.514 + 1.536 = 3.050 lecciones.

---

## 6. Fase D. Producción

Antes de nada: **copia de seguridad de la base de datos de producción** con `sqlite3 ... ".backup ..."`
(nunca copiar el fichero a pelo: los `-wal` corrompen la copia).

Orden:

1. **SGF por git.** La carpeta `awesome_lessons` sube con el `.bat` de despliegue habitual, que lleva
   `git add -f awesome_lessons` (igual que `my_collections`). No subir `lesson_problems.json` ni
   `awesome_lessons_links.json`.
2. **Web.** `tsumevault.html` ya tiene `<option value="awesome_lessons">awesome_lessons</option>` en el
   desplegable de fuentes. Para cursos nuevos no hace falta tocarlo. Si se añadiera otra source, el `value` debe
   coincidir exactamente con el de `--source`, y tras editar a mano hay que comprobar los finales de línea
   (CRLF) del fichero.
3. **Importar en la base de datos de producción**, después de los pasos 1 y 2:

   ```powershell
   $env:TSUMEVAULT_TOKEN = "..."     # solo en esa ventana; no escribirlo en ningún fichero
   .\importar_awesome_lessons_prod.bat
   ```

   El `.bat` valida, recuerda las comprobaciones y exige escribir `SI` antes de tocar producción. La variable
   `SERVER` al principio del `.bat` es la URL del servidor de producción; confirmar que es la correcta.
4. **Lecciones y catálogo.** Si el curso es nuevo, subir primero sus ficheros de lección con
   `_subir_lecciones_a_Hetzner.bat "<carpeta del curso>"` (verifica el número de ficheros) y después
   `all_lessons.json`. Para subir solo `all_lessons.json`:

   ```powershell
   scp .\all_lessons.json root@46.225.97.185:/opt/tsumevault/player/all_lessons.json.nuevo; ssh root@46.225.97.185 'cd /opt/tsumevault/player && python3 -m json.tool all_lessons.json.nuevo > /dev/null && cp -p all_lessons.json all_lessons.json.bak-$(date +%Y%m%d-%H%M%S) && chown --reference=all_lessons.json all_lessons.json.nuevo && chmod --reference=all_lessons.json all_lessons.json.nuevo && mv all_lessons.json.nuevo all_lessons.json && echo REEMPLAZADO'
   ```

   Si el `scp` falla o el JSON no es válido, la cadena se corta antes del `mv` y el `all_lessons.json` del
   servidor no se toca. Debe imprimir `REEMPLAZADO`. Recargar la web con Ctrl+F5.

5. **Permisos, siempre después de subir lecciones con `scp -r`.** Desde Windows, `scp -r` deja las carpetas que
   toca en `700` (solo root) y Caddy, que corre como `caddy`, responde **403 a todas las lecciones** que cuelgan
   de ellas, no solo a las nuevas:

   ```powershell
   ssh root@46.225.97.185 "chmod -R a+rX /opt/tsumevault/player/lessons"
   ```

   `a+rX` da lectura a todos y entrada solo a las carpetas. `_subir_draw.bat`, `_subir_board.bat` y
   `_subir_lecciones.bat` ya lo hacen al final; `_subir_lecciones_a_Hetzner.bat` debe hacerlo también.

### Marcha atrás

| Qué | Cómo |
|---|---|
| Importación en la base de datos | `remove_source.py` borra todas las filas de la source (si se hace en producción, restaurar la copia de seguridad si hubiera dudas). |
| `all_lessons.json` | El merge deja `all_lessons.json.bak-<fecha>`; el servidor deja otra con el mismo patrón. |
| Catálogo de lecciones | `awesome_baduk_lessons.json.bak-<fecha>`. |
| `tsumevault.html` | Restaurar desde git. |

---

## 7. Resumen rápido para un curso nuevo

1. Fase A: export `lessons.json`; descargar audio con `--skip-catalog`; `build_final_collection.py`; `awesome_to_player.py
   ... --only "<curso>"`; probar; copiar a `player\` (sección 3). Guardar `lesson_ids.json`.
2. `extract_lesson_problems.py ...` → `lesson_problems.json`.
3. `lecciones_problemas.py plan`: sin cursos sin nivel, sin títulos repetidos. Si los hay, tablas (sección 2.2/2.3).
4. `lecciones_problemas.py` (todos los niveles) → revisar `informe_awesome_lessons.txt`.
5. `robocopy salida_awesome_lessons ..\..\awesome_lessons /E`; borrar de nuevo los 2 SGF rechazados.
6. `import_my_collections.py ... --validate-only`: 0 ERRORS y 0 BROKEN.
7. Importar en local y comprobar en la web local.
8. `parchear_catalogo.py` (`--dry-run` y luego real): 0 lecciones sin dificultad. **Siempre después de copiar `all_lessons.new.json`.**
9. `merge_lessons.py` (`--dry-run --check-files` y luego real).
10. Copia de seguridad de la base de datos de producción.
11. Subir SGF por git y desplegar `tsumevault.html`.
12. `importar_awesome_lessons_prod.bat`.
13. Subir ficheros de lección y `all_lessons.json`; **`chmod -R a+rX`** en el servidor; Ctrl+F5 y comprobar.

---

## 8. Problemas encontrados y cómo se resolvieron

| Problema | Causa | Solución |
|---|---|---|
| `Get-Content` muestra `tÃ­tulo` o `â­•` | PowerShell 5 lee UTF-8 como ANSI. | Es solo visualización. Para comprobar un fichero, abrirlo con Python con `encoding='utf-8'`. |
| `KeyError ':move'` al convertir | Algunos problemas traen un nodo `{:stones {}, :id ...}` sin jugada. | `build_children` de `convert_problems.py` ignora los nodos sin `:move`. Cambio permanente (afecta también a la serie Level, sin efecto en lo ya generado). |
| HTTP 404 al descargar un problema | El curso referencia un id que ya no existe en el sitio. | Sin solución posible; queda sin SGF. |
| Problema con todas las hojas `WRONG` | El autor solo escribió respuestas incorrectas (`"comment": "AI recommendation"`). | Se omite (sin `RIGHT` no se puede resolver). |
| El importador rechaza un SGF: `inconsistent first-move color across branches` | Una rama empieza con el color que no mueve. | Es ERROR, no BROKEN; `--force` no lo salva. Borrar el SGF o quitar esa rama. |
| El desplegable no filtra por `awesome_lessons` | El `value` de la opción copiada seguía siendo `awesome_baduk`. | `value` y texto deben ser el nombre exacto de la source. |
| Dos cursos con el mismo título | Un curso regrabado o subido otra vez, uno con audio incompleto. | Comparar `vimeoId`; descartar el malo (`DESCARTAR` + `QUITAR_CURSOS`). |
| Lecciones sin dificultad en el player | Curso sin `target-group`. | Tabla de excepciones y `parchear_catalogo.py`. |
| Nombres de capítulo cortados | `limpiar()` de `niveles_academia.py` corta a 60 caracteres y pierde el número de la serie. | `lecciones_problemas.py` usa su propia limpieza con límite de 120. |
| Todas las lecciones dan **403** tras subir | `scp -r` desde Windows deja las carpetas en `700`; Caddy no puede entrar. | `chmod -R a+rX /opt/tsumevault/player/lessons` (sección 6, paso 5). No es un baneo: `all_lessons.json` sigue dando 200. |
| `lesson_ids.json` vacío (2 bytes) | El conversor lo creaba vacío si no lo encontraba en `--out`. | Desde la v22 se detiene; usar `--ids` con la ruta de verdad (sección 3, paso 5). |
| Clip de un curso sin árbol con el tablero vacío todo el vídeo | Una sola jugada sobre punto ocupado hace que el conversor descarte el clip entero (solo audio). La causa: los `:add` hechos en la raíz se guardaban **en** la raíz, y tras un `:navigate nil` (que en el original deja el tablero vacío) la apertura nueva chocaba con ellos. | v28: en cursos sin árbol, un `:add` en la raíz crea un nodo hijo. Recuperó 900598 y 900817. Diagnóstico con `diag_ocupadas.py`. |
| Un dibujo visible desde 0:00 que el original no muestra | La web restaura en t=0 el dibujo del clip anterior y lo borra en t=0; en el `_draw.json` se perdía ese orden. | v30: ese trazo no se guarda. Afectó a 4 clips (2 corregidos, 2 sin dibujo). |
| El dibujo pasa por debajo de las piedras | Las capas de WGo llevan `z-index` 100/200/300. | `z-index: 1000` en el lienzo del dibujo (`player.html`). |
| Los cambios hechos en local no se ven en el player | El player pide **siempre** al servidor (`LESSONS_BASE` apunta a producción) y el navegador cachea los `.json`. | Subir antes de probar; F12 → Network → «Disable cache» y Ctrl+F5. |

---

## 9. Lo que este documento no cubre o hay que confirmar

- **Export `lessons.json`**: se documenta en la sección 3 (paso 1) como salida de `find_chapters.py`, renombrada. El otro
  procedimiento lo deja como «PENDIENTE DE RELLENAR»; esta es la respuesta. En el próximo export, comparar con la copia
  `lessons.json.bak-…` (más documentos, mismo formato) por si el sitio cambiara algo.
- Opciones completas del conversor y del resto de pasos de lecciones: `PROCEDIMIENTO_curso_nuevo_awesome_baduk.md`.
- La URL exacta del servidor de producción para `--server` (el `.bat` trae `https://tsumevault.duckdns.org`
  como valor por defecto; comprobar si lleva puerto).
- El `.bat` de despliegue a GitHub y su `git add -f awesome_lessons`: confirmado como hecho y funcionando, no
  se ha guardado aquí su contenido.
- El enlace visible de la lección a sus problemas dentro del player: no existe; los datos están en
  `awesome_lessons_links.json`.
- Si el sitio añade problemas a un curso ya importado, el número de orden de los ficheros (`NN_...`) puede
  cambiar y, con él, la identidad (basada en la ruta). Para cursos ya subidos, comprobar que lo nuevo solo
  se añade al final antes de volver a importar.
- Mejora pendiente: que `lecciones_problemas.py` omita por sí mismo los dos problemas rechazados
  (`Y1jrdM2g`, `KPYi1Doy`), para no tener que borrarlos a mano en cada regeneración.
- Dibujo a mano: 1.139 trazos (54 %) empiezan sin `set-color` y se pintan en rojo `#f44336`. Si el original
  recordara el color entre clips, alguno saldría de otro color: revisar si se ve alguno raro.
- Vídeos grabados antes del dibujo: las lecciones con `_draw.json` que ya estaban en `recorded.json` hay que
  grabarlas otra vez (`recorded_quitar_draw.py` las quita de la lista).

---

## 10. Qué guardar en git y qué no (carpeta `_sources_scripts\awesome_baduk`)

**Subir**: los scripts del flujo y los documentos.

- Problemas y catálogo: `extract_lesson_problems.py`, `lecciones_problemas.py`, `parchear_catalogo.py`,
  `convert_problems.py`, `niveles_academia.py`, `analyze_all.py`, `importar_awesome_lessons_prod.bat`.
- Lecciones y audio: `awesome_to_player.py`, `download_vimeo_batch.py` (ya parcheado), `parche_download_vimeo.py`,
  `build_final_collection.py`, `find_chapters.py`, `census_courses.py`, `inspect_clip.py`, `convertir_audios.bat`, `bajar_academia.bat`,
  `_subir_lecciones_a_Hetzner.bat`.
- Dibujo y correcciones: `census_draw.py`, `diag_ocupadas.py`, `compare_board.py`, `recorded_quitar_draw.py`,
  `_subir_draw.bat`, `_subir_board.bat`, `_subir_lecciones.bat`.
- `PROCEDIMIENTO_curso_nuevo_awesome_baduk.md` y este documento.
- `player\lessons_sources\awesome_baduk_lessons_ids.json` (**imprescindible**: es el `lesson_ids.json`) y el resto de
  `player\lessons_sources\*.json`.
- `list_inventory.py` **solo si se saca antes la clave de API** (el repositorio es público).
- Scripts de colecciones anteriores (`convertir_libro.py`, `generar_sgfs*.bat`, `download_days.py`, etc.): opcionales;
  mejor en una subcarpeta `_historico`.

**No subir** (`.gitignore` sugerido en esa carpeta):

```
awesomebaduk_rt
lessons.json
lesson_problems.json
awesome_lessons_links.json
draw_out*/
board_out/
prueba_*/
problems_raw/
out/
player_test/
salida_*/
__pycache__/
*.txt
*.bak
```

(`player_test/` puede ignorarse porque `lesson_ids.json` vive ya en `player\lessons_sources\`.)

**Se puede borrar sin riesgo** (se regenera): `__pycache__`, `salida_*`, los `.txt` de informes y planes, y los
ficheros de datos del primer import (`challenge.json`, `days.json`). Conservar `problems_raw` (caché de más de 5.500
problemas, que requiere login para volver a bajarse) y `awesomebaduk_rt`.

---

## 11. Corregir lecciones ya publicadas (sin reconvertir el audio)

Cuando se arregla el conversor, las lecciones publicadas no cambian solas. Los `.m4a` ya no están en disco, así
que **no** se reconvierten: se regeneran solo el tablero o solo el dibujo, se comparan con lo publicado y se sube
únicamente lo que cambia. Todo desde `_sources_scripts\awesome_baduk`, con estas dos variables en la ventana de
PowerShell:

```powershell
$IDS = "..\..\player\lessons_sources\awesome_baduk_lessons_ids.json"
$PUB = "..\..\player\lessons\Awesome Baduk"
```

### 11.1 Tablero (`.sgf` + `.json`)

```powershell
python awesome_to_player.py lessons.json --board-only --ids $IDS --published-dir $PUB --out board_out
python compare_board.py board_out $PUB
```

- `--board-only` escribe en `board_out\lessons\Awesome Baduk\...` solo las lecciones cuyo `.sgf` o `.json` cambia,
  en la **misma ruta** que tienen publicadas, y deja la lista en `board_out\board_changes.json`. No toca `.ogg`,
  dibujos, catálogos ni informes.
- `compare_board.py` reproduce cada lección vieja y nueva como el player y compara las piedras instante a
  instante: `IGUAL` (solo cambia la numeración interna de los nodos) o `DISTINTO` (con los instantes y las piedras
  de más o de menos). Los `DISTINTO` se comprueban contra el vídeo original antes de subir.
- Referencia (v28, 19-oct-2026): 1.542 publicadas, 1.515 sin cambios, 27 cambiadas: 25 `IGUAL` y 2 recuperadas.

### 11.2 Dibujo (`_draw.json`)

```powershell
python awesome_to_player.py lessons.json --draw-only --ids $IDS --published-dir $PUB --out draw_out2
```

- Con `--published-dir` escribe solo los dibujos que cambian (o nuevos) y lista los `_draw.json` publicados que hay
  que **borrar** (clips que se quedan sin dibujo), también en `draw_out2\draw_changes.json`.
- Sin `--published-dir` escribe todos, como al principio.
- Referencia (v30): 283 publicados, 279 sin cambios, 2 cambiados, 2 a borrar.

### 11.3 Aplicar en local y en el servidor

Primero la copia local (para que siga siendo un espejo del servidor y la próxima pasada no vuelva a dar estas
lecciones como cambiadas), después el servidor y al final los permisos:

```powershell
robocopy "board_out\lessons\Awesome Baduk" "$PUB" *.sgf *.json /S
robocopy "draw_out2\lessons\Awesome Baduk" "$PUB" *_draw.json /S
scp -r "board_out\lessons" root@46.225.97.185:/opt/tsumevault/player/
scp -r "draw_out2\lessons" root@46.225.97.185:/opt/tsumevault/player/
ssh root@46.225.97.185 "chmod -R a+rX /opt/tsumevault/player/lessons"
```

(O `_subir_board.bat` y `_subir_draw.bat "draw_out2\lessons"`, que comprueban el contenido y hacen el `chmod`.)

Los dibujos a borrar se quitan a mano en los dos sitios (`Remove-Item` en local, `ssh ... "rm -v '<ruta>'"` en
el servidor) y se comprueba el total con `find /opt/tsumevault/player/lessons -name '*_draw.json' | wc -l`.

### 11.4 Comprobar

- El player pide al **servidor**: probar después de subir, con la caché desactivada (F12 → Network → «Disable
  cache», Ctrl+F5).
- Si alguna lección cambiada está en `recorded.json`, su vídeo grabado está desfasado: quitarla de la lista y
  volver a grabarla.
