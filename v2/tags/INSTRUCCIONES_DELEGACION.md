# INSTRUCCIONES DE TRABAJO — TsumeVault (preámbulo para tareas delegadas)

Eres un asistente de programación trabajando sobre **TsumeVault**, una aplicación
personal de tsumego (problemas de go), offline-first. Estas instrucciones son
OBLIGATORIAS y tienen prioridad sobre cualquier atajo que se te ocurra. Léelas
completas antes de tocar nada. Después de estas instrucciones recibirás UNA tarea
concreta y acotada: haz SOLO esa tarea.

---

## 1. Mapa de archivos

| Archivo | Rol | ¿Puedes modificarlo? |
|---|---|---|
| `tsumevault.html` | Cliente completo (HTML+CSS+JS, ~4.500 líneas, sql.js). El JS vive en el bloque `<script>` más largo. | SÍ, solo lo que pida la tarea |
| `tsumevault_server.py` | Servidor Python + SQLite | Solo si la tarea lo pide explícitamente |
| `run_all.sh` | Orquestador de validación: 3 baterías (servidor, cliente, compat) | NO |
| `test_server.py` | Batería 1: tests del servidor (puerto 3477) | NO (salvo que la tarea pida AÑADIR tests) |
| `harness.js` | Batería 2: ejecuta el código REAL del cliente en Node contra el servidor real (puerto 3488) | NO (ídem) |
| `harness_compat.js` | Batería 3: cliente antiguo ↔ servidor nuevo (puerto 3489) | NO |
| `extract_bundle.py` | Extrae del cliente las funciones de sync → `harness_bundle.js` y todo el script → `client_script.js` | NO |
| `db_schema.sql` | Fixture de esquema LEGACY para las baterías | NO |
| `extract_tags.py` + `test_tags.js` | Batería aparte (T23): API local de etiquetas y filtro de `localGetProblems` en Node. `python3 extract_tags.py && node test_tags.js` | NO (salvo que la tarea pida AÑADIR tests) |
| `harness_bundle_old.js` | Fixture ESTÁTICO (bundle del cliente antiguo). No se regenera | NO, jamás |
| `client_script.js`, `harness_bundle.js`, `tags_bundle.js`, `.out_*.txt`, `t_run/`, `h_run/`, `c_run/` | GENERADOS por el kit. No los edites a mano; se sobrescriben | NO |

## 2. Reglas de oro (sin excepciones)

1. **Plan antes de código.** Antes de editar, escribe: qué archivo, qué función,
   qué líneas aproximadas, qué NO vas a tocar. Si la tarea es ambigua, pregunta;
   no supongas.
2. **Arreglo mínimo.** Cambia lo imprescindible. Prohibido: refactorizar,
   renombrar, reordenar funciones, "mejorar de paso", cambiar formato de líneas
   que no tocas. Un diff pequeño y legible vale más que un diff elegante.
3. **Validar antes de cerrar.** Una tarea SOLO está terminada cuando
   `bash run_all.sh` imprime `✔ TODO OK` (código de salida 0). "Compila" o
   "parece que funciona" NO es terminado. Si un test falla, arregla TU código;
   está prohibido modificar tests o fixtures para ponerlos en verde.
4. **Nunca toques el código de sync sin que la tarea lo pida.** Las funciones que
   `extract_bundle.py` extrae (busca los `grab(...)` dentro de ese script:
   `syncFetch`, `doSync`, `tryAutoSync`, `saveDB`, `updateSm2`,
   `localInsertAttempt`, `purgeEmptyRuns`, etc.) son la zona crítica del
   proyecto. Truco de verificación para tareas de UI: guarda
   `harness_bundle.js` antes y después de tu cambio y haz `diff`; si la tarea
   era de UI, deben ser byte-idénticos.
5. **No inventes esquema ni datos.** Si necesitas saber cómo es una tabla o una
   función, LÉELA en el archivo (grep/view). No respondas de memoria.

## 3. TRAMPA CRÍTICA: finales de línea CRLF

`tsumevault.html` usa **CRLF** (`\r\n`) y `extract_bundle.py` hace
`split("\r\n")`: si el archivo acaba con finales LF, la extracción falla con
`no encontrado: 'const SYNC_TOKEN_KEY'`.

- Comprueba SIEMPRE antes de empezar: `grep -c $'\r' tsumevault.html`
  (debe dar miles). Si da 0, el archivo se normalizó a LF: restáuralo con
  `sed -i 's/$/\r/' tsumevault.html` (solo si NO queda ningún `\r`).
- Al editar, conserva CRLF. En Python abre siempre con `newline=""` al leer y
  al escribir: `io.open(p, encoding="utf-8", newline="")`.
- El entregable final debe ser CRLF.

## 4. Cómo editar `tsumevault.html` de forma segura

NO uses regex a ciegas ni reescribas bloques grandes de memoria. Usa un script
Python de edición con **anclajes exactos y aserción de ocurrencia única**,
siguiendo este patrón (es el patrón establecido del proyecto):

```python
import io
p = "tsumevault.html"
src = io.open(p, encoding="utf-8", newline="").read()

def rep(old, new):
    global src
    n = src.count(old)
    assert n == 1, f"anclaje aparece {n} veces (esperado 1): {old[:80]!r}"
    src = src.replace(old, new)

NL = "\r\n"   # OJO: los anclajes multilinea deben unirse con \r\n

rep(
    "    function ejemploViejo() {" + NL + "      cuerpo();" + NL + "    }",
    "    function ejemploNuevo() {" + NL + "      cuerpo2();" + NL + "    }",
)

io.open(p, "w", encoding="utf-8", newline="").write(src)
print("cambios aplicados OK")
```

Si un `assert` falta (0 u >1 ocurrencias), NO relajes el anclaje al azar: lee el
archivo alrededor de la zona (`grep -n`) y construye un anclaje más largo y
único. Comenta cada cambio en el código con la etiqueta de la tarea
(p. ej. `// T15: ...`), como hacen los cambios existentes (T1–T12, F1–F6).

## 5. Cómo validar

Desde el directorio con TODOS los archivos:

```bash
bash run_all.sh
```

Salida esperada al final:

```
  servidor: 108 PASS | cliente: 132 PASS | compat: 8 PASS
  ✔ TODO OK
```

(Los números pueden crecer si la tarea añade tests; nunca decrecer.)

Detalles operativos:

- Necesita `node`, `python3` y `sql.js@1.10.2` (el script lo instala con npm si
  falta; requiere red a registry.npmjs.org).
- Si falla, lee `.out_server.txt`, `.out_client.txt` o `.out_compat.txt` y busca
  las líneas `FAIL`. Arregla, y vuelve a lanzar `run_all.sh` COMPLETO.
- **No uses `pkill -f tsumevault_server.py`** para limpiar procesos: el patrón
  coincide con tu propia línea de comandos y te matas a ti mismo. `run_all.sh`
  ya limpia vía `/proc`; si necesitas hacerlo a mano, copia ese bloque Python.
- Puertos 3477/3488/3489 deben quedar libres; el propio script lo comprueba.
- `run_all.sh` regenera `client_script.js` y `harness_bundle.js` en cada
  ejecución: cualquier edición manual sobre ellos se pierde (edita SIEMPRE
  `tsumevault.html`).
- Comprobación rápida de sintaxis sin lanzar todo:
  `python3 extract_bundle.py && node --check client_script.js`.

## 6. Flujo de trabajo obligatorio por tarea

1. Lee la tarea. Escribe el plan (archivos, funciones, alcance, qué no tocas).
2. Ejecuta `bash run_all.sh` ANTES de cambiar nada → confirma línea base verde.
   Si la base ya está roja, PARA e informa: no construyas sobre rojo.
3. (Tareas de UI) guarda copia de `harness_bundle.js` para el diff posterior.
4. Aplica los cambios con el patrón de la sección 4.
5. `python3 extract_bundle.py && node --check client_script.js` (fallo rápido).
6. `bash run_all.sh` → debe acabar en `✔ TODO OK`. Si no, itera (máx. 3
   intentos; si no sale, revierte y reporta el problema con detalle).
7. (Tareas de UI) `diff` del bundle: debe estar intacto.
8. Copia a `/mnt/user-data/outputs/`: el/los archivo(s) modificado(s) + un
   `WORKPLAN_<tarea>.md` con: requisito, cambios exactos (función y línea
   aproximada), resultado de la validación (PASS por batería), limitaciones.
9. En tu respuesta final: resumen breve, qué se validó, y cualquier duda o
   comportamiento observado fuera del alcance (anótalo, NO lo arregles).

## 7. Prohibiciones expresas

- Modificar `run_all.sh`, `extract_bundle.py`, `db_schema.sql`,
  `harness_bundle_old.js` o debilitar tests existentes.
- Tocar `localStorage` de `sync_token` / `sync_server_url` o la tabla
  `sync_meta` salvo tarea explícita (los cursores de sync viven en `sync_meta`,
  atómicos con los datos; el token queda en localStorage a propósito).
- Reutilizar IDs del servidor como claves primarias locales (causó pérdida de
  datos silenciosa en el pasado).
- Registrar listeners sin protección contra acumulación: si el elemento
  persiste entre renders usa el patrón `dataset.bound` (cf. T3/3.7); si la fila
  se reconstruye en cada render, el listener fresco es correcto.
- Insertar HTML con datos dinámicos sin `esc()` — o mejor, usa
  `createElement` + `textContent` (patrón F6).
- Dar una tarea por cerrada sin `✔ TODO OK`.
