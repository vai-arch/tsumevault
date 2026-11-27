# Archivo de partidas (kifumaster): guía de uso

Qué hacer para traer partidas nuevas de kifumaster.org y tenerlas en la página del archivo (棋 en TsumeVault).
Todos los `.bat` están en la raíz del proyecto.

## Buscar partidas nuevas (una vez al mes, más o menos)

1. **`.\kifu_crawl.bat --nuevo-ciclo`**
   Repasa los datos públicos de kifumaster (torneos, ediciones, partidas), con calma: una petición cada 6–8 s.
   Tarda unas 2 horas; lo que no ha cambiado no se vuelve a descargar.
   Si se corta (apagas el portátil, se va la red…), vuelve a lanzarlo **sin** `--nuevo-ciclo` y sigue donde se quedó.
   Termina con «Ciclo N completo».

2. **`.\kifu_build.bat`**
   Reconstruye la base de datos del archivo con lo descargado (no necesita red, tarda poco).
   Actualiza en cada edición los ficheros `games.txt` y `games_pendientes.txt` y crea las carpetas de las ediciones nuevas.
   No borra ni toca tus SGF.

3. Ejecutar python download_games.py desde la carpeta kifumaster

4. **`.\_subir_archivo.bat`**
   Sube al servidor la base de datos nueva (solo si ha cambiado) y los SGF que hayas bajado. No borra nada en el servidor.
   Con `--simular` enseña lo que haría sin subir nada.

Después, en la página del archivo ya aparecen los torneos, ediciones y partidas nuevas (en gris las que aún no tienes).

Si guardas un SGF en la carpeta equivocada, `kifu_build.bat` lo mueve a la suya.

## Opcional

- **Torneos de «otros eventos»** (ocultos por defecto): para traer uno a la lista principal, añade una línea a `kifumaster\promocionados.txt` (`<torneo-actual> [carpeta-nueva] [nombre]`) y ejecuta los pasos 2 y 3.
- **País de un torneo**: si un torneo sale en el país equivocado, añade a `kifumaster\paises.txt` una línea `<torneo> <país>` (japan, korea, china, taiwan, international u other) y ejecuta los pasos 2 y 3.

## Si algo falla

- `kifu_build.bat` dice que no puede reemplazar `archive.db`: cierra lo que la tenga abierta (DB Browser, otra ventana) y repite.
- `kifu_crawl.bat` se para tras varios errores seguidos: es a propósito, para no molestar al servidor de kifumaster. Prueba otro día.
- Detalles técnicos: `kifumaster\README.md` y `docs\WORKPLAN_ARCHIVO.md`.

## Notas
La base de datos no cambia por bajar SGF:

archive.db solo guarda lo que viene de kifumaster: torneos, ediciones, partidas y jugadores. Cambia únicamente cuando ejecutas kifu_build.bat después de un ciclo de descarga.
Qué partidas tienen SGF no lo saca el servidor de la base de datos, sino de mirar los ficheros que tiene en disco. Al subir, el script avisa al servidor de que hay ficheros nuevos, y la página ya muestra en blanco esas 2.126 partidas.

Si ahora ejecutas .\kifu_build.bat (por ejemplo, para que games_pendientes.txt deje de listar las que ya tienes), la base de datos sí cambiará un poco, porque también anota qué partidas tienen SGF. El siguiente _subir_archivo.bat la subirá. No pasa nada: el servidor seguirá fiándose de los ficheros.

