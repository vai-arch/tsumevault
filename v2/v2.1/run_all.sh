#!/bin/bash
# ══════════════════════════════════════════════════════════════════════════
# TsumeVault v2 — Kit de validación. Ejecuta las TRES baterías completas:
#   1) Servidor  (test_server.py, puerto 3477)
#   2) Cliente   (harness.js contra servidor real, puerto 3488)
#   3) Compat    (harness_compat.js: cliente antiguo <-> servidor nuevo, 3489)
# Uso:  bash run_all.sh        (desde el directorio con todos los archivos)
# Sale con código 0 solo si TODO está en verde.
# NOTA: en este contenedor no existen fuser/ss/lsof — la limpieza de procesos
# se hace vía /proc y la comprobación de puertos con bind real.
# ══════════════════════════════════════════════════════════════════════════
set -u
cd "$(dirname "$0")"
FAIL=0

say() { echo; echo "══════ $1 ══════"; }

kill_servers() {
python3 - <<'EOF'
import os, signal, socket, sys, time
for pid in filter(str.isdigit, os.listdir('/proc')):
    try:
        with open(f'/proc/{pid}/cmdline','rb') as f:
            argv = f.read().decode(errors='replace').split('\0')
        if len(argv) >= 2 and argv[0].endswith('python3') and argv[1].endswith('tsumevault_server.py'):
            os.kill(int(pid), signal.SIGKILL)
            print(f'  (matado servidor previo pid={pid})')
    except (OSError, IOError):
        pass
time.sleep(0.5)
for port in (3477, 3488, 3489):
    s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try: s.bind(('0.0.0.0', port)); s.close()
    except OSError as e:
        print(f'ERROR: puerto {port} sigue ocupado: {e}'); sys.exit(1)
EOF
}

fresh_db() {  # $1 = directorio destino
python3 - "$1" <<'EOF'
import sqlite3, io, sys, os
d = sys.argv[1]
os.makedirs(d, exist_ok=True)
con = sqlite3.connect(os.path.join(d, 'tsumeVault.db'))
sql = io.open('db_schema.sql', encoding='utf-8', errors='replace').read().replace('CREATE TABLE sqlite_sequence(name,seq);','')
# fixture LEGACY: sin los indices unicos de Fase 1 (la migracion debe crearlos)
sql = '\n'.join(l for l in sql.splitlines() if 'idx_attempts_uuid' not in l and 'idx_runs_uuid' not in l and not l.strip().startswith('-- Fase 1'))
con.executescript(sql); con.commit(); con.close()
EOF
}

start_server() {  # $1 = dir, $2 = puerto
  cp tsumevault_server.py "$1/"
  (cd "$1" && setsid python3 tsumevault_server.py "$2" > server.log 2>&1 < /dev/null &)
  sleep 1.5
  if grep -q "Address already in use" "$1/server.log" 2>/dev/null; then
    echo "ERROR: bind falló en puerto $2"; head -5 "$1/server.log"; return 1
  fi
  if ! curl -sf "http://127.0.0.1:$2/sync/static_version" > /dev/null; then
    echo "ERROR: servidor en $2 no responde"; head -20 "$1/server.log"; return 1
  fi
  return 0
}

# ── Comprobaciones previas ──
say "PRE-CHECKS"
python3 -c "import py_compile; py_compile.compile('tsumevault_server.py', doraise=True); print('  servidor: compila OK')" || FAIL=1
if [ ! -d node_modules/sql.js ]; then
  echo "  instalando sql.js…"; npm install sql.js@1.10.2 --no-audit --no-fund > /dev/null 2>&1 || { echo "ERROR npm"; exit 1; }
fi
python3 extract_bundle.py || FAIL=1
node --check client_script.js && echo "  cliente: sintaxis OK" || FAIL=1
node --check harness_bundle.js || FAIL=1
[ $FAIL -ne 0 ] && { echo "PRE-CHECKS FALLIDOS — no se ejecutan las baterías"; exit 1; }

# ── 1) Batería del servidor ──
say "1/3 SERVIDOR"
kill_servers || exit 1
rm -rf t_run
timeout 150 python3 test_server.py > .out_server.txt 2>&1
RC=$?
tail -1 .out_server.txt
S_PASS=$(grep -c '^PASS' .out_server.txt || true)
[ $RC -ne 0 ] && { FAIL=1; grep '^FAIL' .out_server.txt; }

# ── 2) Batería del cliente ──
say "2/3 CLIENTE"
kill_servers || exit 1
rm -rf h_run && fresh_db h_run && start_server h_run 3488 || exit 1
timeout 180 node harness.js > .out_client.txt 2>&1
RC=$?
tail -1 .out_client.txt
C_PASS=$(grep -c '^PASS' .out_client.txt || true)
[ $RC -ne 0 ] && { FAIL=1; grep '^FAIL' .out_client.txt; }

# ── 3) Batería de compatibilidad ──
say "3/3 COMPATIBILIDAD"
kill_servers || exit 1
rm -rf c_run && fresh_db c_run && start_server c_run 3489 || exit 1
timeout 120 node harness_compat.js > .out_compat.txt 2>&1
RC=$?
tail -1 .out_compat.txt
K_PASS=$(grep -c '^PASS' .out_compat.txt || true)
[ $RC -ne 0 ] && { FAIL=1; grep '^FAIL' .out_compat.txt; }

kill_servers > /dev/null 2>&1

say "RESUMEN"
echo "  servidor: $S_PASS PASS | cliente: $C_PASS PASS | compat: $K_PASS PASS"
if [ $FAIL -eq 0 ]; then echo "  ✔ TODO OK"; exit 0; else echo "  ✘ HAY FALLOS — revisa .out_server.txt / .out_client.txt / .out_compat.txt"; exit 1; fi
