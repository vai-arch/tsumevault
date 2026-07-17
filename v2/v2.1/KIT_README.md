# Kit de validación — TsumeVault v2

Tres baterías automatizadas que ejercitan el **código real** del proyecto.
Ninguna tarea se da por terminada sin `bash run_all.sh` terminando en `✔ TODO OK`.

## Contenido

| Archivo | Qué es |
|---|---|
| `run_all.sh` | Orquestador único: pre-checks + las 3 baterías con servidores frescos garantizados. |
| `test_server.py` | Batería del servidor (puerto 3477): migraciones, dedup por uuid, auth, CORS, Origin, límites de body, validaciones 400/413, `run_uuid` en el pull. |
| `harness.js` | Batería del cliente (puerto 3488): ejecuta las funciones de sync REALES extraídas de `tsumevault.html` en contextos `vm` aislados ("dispositivos") contra el servidor real. Escenarios E1–E14: instalación desde cero, migración con duplicados históricos, sync doble, dos dispositivos, creación offline+reconexión, purga, borrado propagado, SM-2, token, reset de DB con cursores huérfanos, colisión de ids servidor/local. |
| `harness_compat.js` | Batería de compatibilidad (puerto 3489): cliente ANTIGUO (protocolo pre-Fase-1, congelado en `harness_bundle_old.js`) contra servidor nuevo, y convivencia con el cliente nuevo. |
| `extract_bundle.py` | Regenera `harness_bundle.js` extrayendo las funciones de sync del `tsumevault.html` actual. Autosuficiente (extrae también `client_script.js`). |
| `harness_bundle_old.js` | Bundle CONGELADO del cliente original. **No regenerar ni editar**: representa a los clientes antiguos desplegados. |

## Uso

```bash
mkdir -p /home/claude/work && cp /mnt/project/* /home/claude/work/ && cd /home/claude/work
npm install sql.js@1.10.2 --no-audit --no-fund   # (run_all.sh lo hace si falta)
bash run_all.sh
```

Salida esperada: recuentos por batería y `✔ TODO OK`. Los detalles quedan en
`.out_server.txt`, `.out_client.txt`, `.out_compat.txt`.

## Reglas al ampliar el arnés (`harness.js`)

1. Los escenarios existentes están **acoplados en orden** (el estado del
   servidor evoluciona a lo largo de la suite). No los reordenes ni los
   modifiques salvo que tu tarea lo pida explícitamente.
2. Añade escenarios nuevos AL FINAL, justo antes de la línea
   `console.log('\nRESULTADO CLIENTE:'…)`, con dispositivos frescos
   (`freshDevice('X')`) y uuids propios.
3. Si tu función nueva no está en el bundle, añádela a la lista `grab(...)` de
   `extract_bundle.py` (respeta el orden de dependencias).
4. El arnés llama a las funciones directamente (no pasa por `recordAttempt` ni
   por el DOM): si tu escenario necesita persistencia entre "reinicios",
   ejecuta `await saveDB()` explícitamente antes de `reloadDevice`.

## Peculiaridades del entorno

- `tsumevault.html` usa **CRLF**. Edita con un script Python que verifique que
  cada patrón a sustituir aparece exactamente 1 vez, y aborte si no.
- En este contenedor **no existen** `fuser`, `ss` ni `lsof`. No intentes matar
  servidores con ellos (fallan en silencio): `run_all.sh` ya limpia vía
  `/proc` y verifica los puertos con un bind real. Un servidor zombi de una
  ejecución anterior contamina TODA la batería con estado acumulado.
- Las referencias a números de línea de `AUDITORIA_TSUMEVAULT_v2.md` están
  DESFASADAS (el archivo ha crecido). Localiza siempre por nombre de función.
