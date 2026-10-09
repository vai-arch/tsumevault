# Añadir un curso nuevo de Awesome Baduk al catálogo de lecciones

Procedimiento para cuando aparece un curso nuevo (o se modifica uno existente) en awesomebaduk.com:
descargar el audio, convertir el curso al formato del `player.html`, unirlo al catálogo y subirlo al servidor.

**Idea general.** Cada clip de la web (vídeo de Vimeo + árbol de tablero + eventos con tiempo) se convierte en una lección
del player antiguo: un `.sgf`, un `.json` de eventos y un `.ogg` de audio. El player no se toca.

```
lessons.json (export de la web)
   │  download_vimeo_batch.py       -> out\cursos\<Curso>\<vimeoId>.m4a
   │  build_final_collection.py     -> out\cursos_final\...   (solo los audios que usan los clips)
   │  awesome_to_player.py          -> player_test\player\lessons\Awesome Baduk\<Curso>\Clip NN\<id>.sgf/.json/.ogg
   │                                   player_test\player\all_lessons.new.json   (filas del catálogo)
   │  (copiar a la carpeta real)    -> player\lessons\Awesome Baduk\<Curso>  +  player\lessons_sources\awesome_baduk_lessons.json
   │  merge_lessons.py              -> player\all_lessons.json   (Guo Juan + Awesome Baduk)
   └─ _subir_lecciones_a_Hetzner.bat -> servidor /opt/tsumevault/player/...
```

---

## 0. Carpetas y ficheros clave

Variables que se usan en los comandos de abajo (PowerShell). Ajusta la ruta de `yt-dlp` a la tuya:

```powershell
$W  = "C:\Users\victor.diaz\Documents\All\Go\tsumevault\_sources_scripts\awesome_baduk"   # scripts y datos de trabajo
$P  = "C:\Users\victor.diaz\Documents\All\Go\tsumevault\player"                           # player real (copia local del servidor)
$YT = "C:\Users\victor.diaz\Documents\All\Videos\yt-dlp.exe"                              # ajusta
```

| Ruta | Qué es |
|---|---|
| `$W\lessons.json` | Export de la web (todos los cursos). Se sustituye en cada actualización. |
| `$W\out\cursos\<Curso>\<vimeoId>.m4a` | Audios descargados. |
| `$W\out\cursos_final\` | Solo los audios usados por clips, + `cursos.csv` y `report.json`. |
| `$W\player_test\player\` | **Carpeta de salida del conversor** (siempre la misma, ver aviso). |
| `...\player\lesson_ids.json` | **Registro de IDs (clave `idCurso/uuidVideo` → lessonId). No perder.** |
| `...\player\all_lessons.new.json` | Filas del catálogo de Awesome Baduk (se acumulan entre ejecuciones). |
| `...\player\lessons\Awesome Baduk\` | Lecciones generadas. |
| `...\player\convert_report.json`, `skipped_no_audio.json`, `errors_courses.json` | Informes de la última ejecución. |
| `$W\player_test\player.html` + `wgo\` | Player de prueba (con `PLAYER_DATA_BASE='player/'` y `LESSONS_BASE='player/lessons/'`). |
| `$P\lessons\Awesome Baduk\` | Copia local de lo que hay en el servidor. |
| `$P\lessons_sources\guo_juan_lessons.json` | Catálogo de la otra web (fuente 1). |
| `$P\lessons_sources\awesome_baduk_lessons.json` | Catálogo de Awesome Baduk (fuente 2) = copia de `all_lessons.new.json`. |
| `$P\all_lessons.json` | Catálogo final que lee el player (resultado de `merge_lessons.py`). **No se edita a mano.** |

> **AVISO.** Usa siempre la misma carpeta `--out player_test\player` en el conversor. Ahí viven `lesson_ids.json`
> y `all_lessons.new.json`; si se pierde `lesson_ids.json`, los IDs cambian. Guárdalo en git junto con `lessons_sources\`.

---

## 1. Obtener el export actualizado (`lessons.json`)

> **PENDIENTE DE RELLENAR:** aquí va cómo se obtiene el export de la web (script/consulta que genera `lessons.json`).
> No está documentado en este procedimiento; es el mismo método que se usó la primera vez.

Debe contener, por curso: `title`, `target-group`, `board.variations`, `vimeo-ids`, `clips[]` (`video-id`, `runtime`, `events`, `draw-events`).

## 2. (Opcional, recomendado) Censo: ver en qué estado está el curso nuevo

```powershell
cd $W
python census_courses.py lessons.json --out census_nuevo --delimiter ";"
```

Abre `census_nuevo\census_courses.csv` y busca el curso. Columna `Estado`:

| Estado | Significado |
|---|---|
| `LISTO` | Solo usa comportamientos validados. |
| `REVISAR` | Algo no validado (hoy: valores de color raros en diagramas). |
| `PROBLEMA` | Alguna anomalía (jugada sobre punto ocupado, color inesperado, clip sin vídeo…). Se convierte igual, con un tramo posiblemente mal. |

Para ver un momento concreto de un clip (qué eventos hay y qué tablero espera el conversor):

```powershell
python inspect_clip.py lessons.json --course "<título o id>" --clip 2 --at 6:14 --window 20 --out player_test\player
```

## 3. Descargar el audio

```powershell
cd $W
python download_vimeo_batch.py lessons.json -o out --ytdlp "$YT"
```

- Salta lo que ya está descargado; por defecto solo baja los `vimeo-ids` que usa algún clip y solo el audio (`.m4a`).
- Opciones: `--ffmpeg "<ruta>"` si ffmpeg no está en el PATH · `--referer` (por defecto `https://awesomebaduk.com/`) ·
  `--attempts N` reintentos · `--pause S` espera entre descargas · `--force` rebajar · `--video` / `--video-only` (no hace falta).
- Si hay errores 403 o formatos raros: actualiza yt-dlp (`yt-dlp -U`).
- Si algún vídeo falla, repite el mismo comando: solo reintenta lo que falta.

## 4. Preparar la colección final de audios

```powershell
python build_final_collection.py lessons.json --delimiter ";"
```

Copia de `out\cursos` a `out\cursos_final` solo los audios que usan los clips. La última línea es el resumen:

```
Totales: {'clips': N, 'present': N, 'missing': N, 'orphans': N, 'copied': N}
```

`missing` debe ser 0 o ser vídeos que sabemos que están **mal subidos por la academia (sin pista de audio)**.
Para ver cuáles faltan:

```powershell
$r = Get-Content out\cursos_final\report.json -Raw | ConvertFrom-Json
$r.courses.PSObject.Properties | Where-Object { $_.Value.missing.Count -gt 0 } | ForEach-Object { "$($_.Value.title): $($_.Value.missing -join ', ')" }
```

Prueba a abrirlos en la web: si no tienen audio, no se pueden recuperar (el conversor los omite con `--require-audio`).
Los `orphans` son audios que ningún clip usa; no molestan.

## 5. Convertir el curso

```powershell
cd $W
python awesome_to_player.py lessons.json --out player_test\player --manifest-copy --audio-root out\cursos_final --convert-audio --require-audio --only "<título o id del curso>"
```

- `--only` filtra por **trozo del título** o por **id** del curso; repítelo para varios cursos. Sin `--only` convierte todo
  (los `.ogg` ya existentes se saltan, solo tarda por los SGF/JSON).
- La **primera línea** que imprime es la versión (`awesome_to_player v20 ...`). Si no sale, se está ejecutando una copia antigua.
- Una línea por clip: `OK` = auto-comprobación correcta; `!!` = el SGF/eventos no cuadran (avisar). Columna `audio:` debe decir `ogg OK`.
- Al final imprime:
  - `Clips omitidos por no tener audio: N` (lista en `skipped_no_audio.json`).
  - `Cursos omitidos por error: N` (lista en `errors_courses.json`); un curso con datos raros no para el resto.
  - `Cursos sin nivel de dificultad (target-group no reconocido): {...}` — ver «Escala de dificultad» más abajo.
  - `Carpetas de curso generadas`: **el nombre exacto de la carpeta** que hay que copiar/subir (paso 7 y 9).
- Los IDs nuevos se asignan a continuación del último del registro `lesson_ids.json` (el primero fue 900000).
  Si el curso ya existía, sus lecciones conservan el ID.
- `--manifest-copy` escribe también `player_test\player\all_lessons.json` (el que lee el player de prueba).
- Para que `ffmpeg` se encuentre: `--ffmpeg "C:\ruta\ffmpeg.exe"` si no está en el PATH.

## 6. Probar en local

```powershell
cd "$W\player_test"
python ..\serve_range.py
```

Abre `http://localhost:8000/player.html?id=<lessonId>`. Para saber el ID:

```powershell
(Get-Content "$W\player_test\player\all_lessons.json" -Raw | ConvertFrom-Json).rows | Where-Object collectionName -like "*<título>*" | Select-Object lessonId, lessonName, lessonLength, lessonDifficulty
```

Comprueba: carga, suena, el tablero sigue a la voz, la barra muestra la duración completa y la dificultad no sale vacía.
Usa `serve_range.py` (no `python -m http.server`: no soporta `Range` y Chrome muestra mal la duración del audio).
Con la caché: abre `F12` → Network → «Disable cache» si algo parece viejo (el servidor ya manda `no-store` para `.json/.html/.sgf`).

## 7. Copiar a la carpeta real del player

```powershell
$curso = "<carpeta que imprimió el conversor>"
robocopy "$W\player_test\player\lessons\Awesome Baduk\$curso" "$P\lessons\Awesome Baduk\$curso" /E
Copy-Item -Force "$W\player_test\player\all_lessons.new.json" "$P\lessons_sources\awesome_baduk_lessons.json"
```

`robocopy` devuelve códigos 0–7 en caso de éxito (≥ 8 es error).

## 8. Unir los catálogos en `all_lessons.json`

```powershell
cd $P
# 1) ensayo: valida, cuenta, comprueba ficheros; no escribe nada
python merge_lessons.py lessons_sources\guo_juan_lessons.json lessons_sources\awesome_baduk_lessons.json --out all_lessons.json --dry-run --check-files lessons --check-source awesome
# 2) escribir de verdad (hace copia all_lessons.json.bak-<fecha> si ya existe)
python merge_lessons.py lessons_sources\guo_juan_lessons.json lessons_sources\awesome_baduk_lessons.json --out all_lessons.json
```

(También sirve `merge_lessons.bat`: es el mismo comando.) El script **se para sin escribir** si hay `lessonLength` no numérico
(causa de `NaNm` en el player) o `lessonId` repetidos. Resultado esperado: `awesome_baduk_lessons.json: N lecciones` con N = anterior + clips del curso nuevo.

## 9. Subir al servidor

```powershell
cd $P
.\_subir_lecciones_a_Hetzner.bat "<carpeta del curso>"      # solo ese curso (rápido)
.\_subir_lecciones_a_Hetzner.bat                             # TODA la carpeta Awesome Baduk (unos 3,5 GB)
```

El script tiene **dos pausas**: tras mirar el servidor (paso 1: aún no se ha tocado nada) y tras verificar los ficheros.
Qué hace: empaqueta con `tar`, sube con `scp` a `root@46.225.97.185`, descomprime en `/opt/tsumevault/player/lessons`
(sin borrar nada), compara nº de ficheros PC/servidor y **se detiene si no coinciden**; después hace copia
`all_lessons.json.bak-<fecha>` en el servidor, sube el nuevo, comprueba que es JSON válido y lo reemplaza de golpe.
Variables a editar al principio: `SRV`, `REMOTE`, `LESSONS`, `MANIFEST`, `REFDIR`.

## 10. Verificar en la web

`Ctrl+F5`, comprobar que «Awesome Baduk» aparece entre los tipos, abrir una lección del curso nuevo (carga, suena, tablero),
y una lección antigua de Guo Juan para confirmar que sigue bien.

## 11. Guardar

En git (o copia): `lesson_ids.json`, `lessons_sources\*.json`, `all_lessons.json`, y estos scripts.

---

## Variantes

- **La academia modifica un curso existente**: mismos pasos con `--only` (los IDs se conservan, los clips nuevos reciben IDs nuevos). En el paso 9 sube la carpeta de ese curso.
- **Cambia el conversor** (o una opción): reconvertir todo sin `--only` (paso 5), copiar toda la carpeta (paso 7 sin `$curso`), unir y subir en modo completo.
- **Varios cursos a la vez**: repite `--only` en el paso 5; en el paso 9 usa el modo completo o repite el `.bat` por carpeta.

## Valores por defecto (validados con datos y vídeo; no cambiar sin comprobar)

| Comportamiento | Valor por defecto | Opción |
|---|---|---|
| `:stones` | Reemplaza la posición | `--stones-mode replace` |
| `:move` con flag `true` | Se ignora el flag (el color alterna igual) | `--flag-mode ignore` |
| `:add` | Nodo hijo; repetir sobre una piedra del mismo color la quita; flag `true` = blanca | `--add-mode child --add-sem toggle --add-flag-true white` |
| Triángulo/cuadrado/círculo repetido | Se quita | `--mark-repeat toggle` |
| Etiquetas A,B / 1,2 | Repetir sobre el punto la quita; la siguiente es la menor libre del nodo | `--label-repeat toggle --label-scope node` |
| Marcas y etiquetas entre clips | Persisten en el nodo | `--marks-persist clip` |
| `:forwards` con varios hijos | Primer hijo | `--forwards first` |
| Nodos creados en vivo | Persisten entre clips (se reconstruyen por camino) | (automático) |
| Valores de color raros (`nil`) en `:stones` | Punto vacío | (automático) |
| Curso sin árbol de tablero | Lección solo audio con tablero vacío | (automático) |
| Clip sin audio | Se omite (sin lección ni fila) | `--require-audio` |

Escala de dificultad (`lessonDifficulty`, desde `target-group`): `group-all` = `"0"` (texto: el player trata el número 0 como vacío),
`group-beginners` = 1, `group-d` = 2, `group-c` = 3, `group-b` = 4, `group-a` = 5. La otra web va de 1 a 11; se mezclan tal cual en el filtro.
Si aparece un `target-group` nuevo, añádelo a `GROUP_LEVELS` (función `difficulty_from_group` de `awesome_to_player.py`) y reconvierte
(solo cambia el manifest). `lessonLength` va en **minutos enteros** (el player los suma; con texto saldría `NaNm`).

## Limitaciones conocidas

- **Dibujo a mano** (`draw-events`, ~19 % de los clips): no se muestra todavía (fase 2; hace falta calibrar el lienzo con una captura del original).
- **Jugada sobre punto ocupado**: ~36 clips (≈ 2 %) tienen algún tramo con una piedra que no cuadra (lecciones de reglas, repeticiones rápidas). Causa no determinada.
- **Vídeos sin audio** en la web: 11 clips reales (más 4 de cursos de prueba) no se publican.
- Cursos de prueba sin `target-group` (31): sin dificultad.

## Problemas conocidos y solución

| Síntoma | Causa / solución |
|---|---|
| `NaNm` al seleccionar lecciones para grabar | `lessonLength` no numérico. `merge_lessons.py` lo detecta; reconvertir con el conversor actual. |
| El player no muestra los cursos nuevos | Falta actualizar `all_lessons.json` (el conversor escribe `all_lessons.new.json`) → paso 8, o `--manifest-copy` en local. |
| Duración del audio mal en local | Usar `serve_range.py`, no `http.server`. |
| Cambios que no se ven en el navegador | `F12` → Network → «Disable cache»; reiniciar el servidor de prueba. |
| Dificultad vacía | `target-group` no reconocido: lo avisa el conversor al final (sección de dificultad). |
| IDs distintos a los de antes | Se perdió `lesson_ids.json`: restaurar de git y reconvertir. |
| `KeyError` / curso que rompe la conversión | Ya se omite con aviso (`errors_courses.json`); revisar ese curso con `inspect_clip.py`. |
| `merge_lessons.py` para con «lessonId repetido» | Dos fuentes comparten ID: revisar que `id_start` de Awesome Baduk (900000+) no choca con la otra web (hoy llega a 2209). |
| El nº de ficheros PC/servidor no coincide | No continuar con el `all_lessons.json`; repetir la subida (idempotente) y revisar nombres de carpeta con caracteres raros. |

## Referencia rápida de opciones

- `download_vimeo_batch.py inputs... [-o OUT] [--ytdlp RUTA] [--ffmpeg RUTA] [--referer URL] [--video|--video-only] [--all-videos] [--attempts N] [--force] [--pause S]`
- `build_final_collection.py inputs... [--src out\cursos] [--dst out\cursos_final] [--include-video] [--check-duration --ffprobe RUTA --tolerance S] [--delimiter ";"] [--force] [--dry-run]`
- `awesome_to_player.py course_json [--out DIR] [--audio-root DIR] [--convert-audio] [--ffmpeg RUTA] [--require-audio] [--manifest-copy] [--only TEXTO|ID]... [--census CSV --estado LISTO,REVISAR] [--type-name "Awesome Baduk"] [--id-start 900000]` + las opciones de comportamiento de la tabla de arriba.
- `census_courses.py inputs... [--out DIR] [--fast] [--examples N] [--compare] [--delimiter ";"]`
- `inspect_clip.py course_json --course TEXTO|ID [--clip N] [--at M:SS] [--window S] [--before S] [--out DIR] [--odd]` + opciones de comportamiento.
- `merge_lessons.py fuente1.json fuente2.json ... --out all_lessons.json [--dry-run] [--no-backup] [--check-files DIR] [--check-source TEXTO]`
- `serve_range.py [puerto]` (desde la carpeta que se quiere servir).
- `_subir_lecciones_a_Hetzner.bat ["carpeta de curso"]`
