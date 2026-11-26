#!/usr/bin/env python3
"""AR2 (WORKPLAN_ARCHIVO.md): sube al VPS lo nuevo del archivo de partidas.

    python kifumaster/kifu_upload.py              (o _subir_archivo.bat desde la raíz)
    python kifumaster/kifu_upload.py --simular    enseña lo que haría, sin subir nada

1. SGF: compara archive/sgf/<xx>/<id>.sgf del portátil con lo que hay en el servidor y sube solo
   los que faltan (scp por carpeta, en tandas). Los que no parecen un SGF ("(;" al principio) se
   saltan y se avisa.
2. archive.db: compara la huella (sha256) con la del servidor; si cambió, la sube como
   archive.db.new y la sustituye con mv (atómico: el servidor nunca lee un fichero a medias).

Nunca borra nada en el servidor. Usa ssh/scp con BatchMode (sin preguntar contraseña).
"""
import argparse, hashlib, os, re, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.environ.get("KIFU_REPO", os.path.dirname(HERE))
DATA = os.environ.get("KIFU_DATA", os.path.join(HERE, "data"))
HOST = os.environ.get("KIFU_HOST", "root@46.225.97.185")
REMOTE = os.environ.get("KIFU_REMOTE_DIR", "/opt/tsumevault/archive")
OPTS = ["-o", "BatchMode=yes", "-o", "ServerAliveInterval=20", "-o", "ServerAliveCountMax=12"]
_ID = re.compile(r"^[0-9a-f]{32}$")
BATCH = 40


def tool(name):
    env = os.environ.get("KIFU_" + name.upper())
    if env:
        return env.split()
    for cand in (shutil.which(name), rf"C:\Windows\Sysnative\OpenSSH\{name}.exe", rf"C:\Windows\System32\OpenSSH\{name}.exe"):
        if cand and os.path.exists(cand):
            return [cand]
    sys.exit(f"No encuentro {name}. ¿Está instalado OpenSSH?")


def ssh(cmd, simular=False, capture=True):
    args = tool("ssh") + OPTS + [HOST, cmd]
    if simular and not capture:
        print("  (simulado) ssh", cmd); return ""
    p = subprocess.run(args, capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        raise RuntimeError(f"ssh falló ({p.returncode}): {cmd}\n{p.stderr.strip()}")
    return p.stdout


def scp(files, dest, simular=False):
    if simular:
        print(f"  (simulado) scp {len(files)} fichero(s) → {dest}"); return
    p = subprocess.run(tool("scp") + OPTS + files + [f"{HOST}:{dest}"], capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        raise RuntimeError(f"scp falló ({p.returncode}) → {dest}\n{p.stderr.strip()}")


def local_sgf():
    root = os.path.join(REPO, "archive", "sgf")
    ok, bad = {}, []
    if not os.path.isdir(root):
        return ok, bad
    for sub in sorted(os.listdir(root)):
        d = os.path.join(root, sub)
        if not os.path.isdir(d):
            continue
        for n in sorted(os.listdir(d)):
            p = os.path.join(d, n)
            gid = n[:-4].lower() if n.lower().endswith(".sgf") else ""
            if not _ID.match(gid) or sub.lower() != gid[:2]:
                bad.append((p, "nombre o carpeta que no siguen archive/sgf/<xx>/<id>.sgf")); continue
            with open(p, "rb") as f:
                head = f.read(64).lstrip(b"\xef\xbb\xbf \t\r\n")
            if not head.startswith(b"(;"):
                bad.append((p, "no parece un SGF")); continue
            ok[gid] = p
    return ok, bad


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Sube al VPS los SGF nuevos y archive.db si cambió.")
    ap.add_argument("--simular", action="store_true")
    a = ap.parse_args(argv)
    print(f"Servidor: {HOST}:{REMOTE}" + ("   [SIMULACIÓN]" if a.simular else ""))

    # 1. SGF
    local, bad = local_sgf()
    for p, why in bad:
        print(f"  AVISO: se salta {p}: {why}")
    remote_txt = ssh(f"mkdir -p {REMOTE}/sgf && cd {REMOTE}/sgf && find . -type f -name '*.sgf'")
    remote = {os.path.basename(l.strip())[:-4] for l in remote_txt.splitlines() if l.strip().endswith(".sgf")}
    new = sorted(g for g in local if g not in remote)
    print(f"SGF: {len(local)} en el portátil, {len(remote)} en el servidor, {len(new)} por subir.")
    if new:
        dirs = sorted({g[:2] for g in new})
        ssh("mkdir -p " + " ".join(f"{REMOTE}/sgf/{d}" for d in dirs), a.simular, capture=not a.simular)
        for d in dirs:
            files = [local[g] for g in new if g[:2] == d]
            for i in range(0, len(files), BATCH):
                scp(files[i:i + BATCH], f"{REMOTE}/sgf/{d}/", a.simular)
        print(f"  subidos {len(new)}.")

    # 2. archive.db
    db = os.path.join(DATA, "archive.db")
    if not os.path.isfile(db):
        print("archive.db: no existe en el portátil (ejecuta kifu_build). No se sube.")
        return 0 if not bad else 1
    mine = sha256(db)
    theirs = ssh(f"sha256sum {REMOTE}/archive.db 2>/dev/null || true").split()
    theirs = theirs[0] if theirs else ""
    if theirs == mine:
        print("archive.db: igual que la del servidor, no se sube.")
    else:
        mb = os.path.getsize(db) / 1e6
        print(f"archive.db: {'distinta' if theirs else 'no está en el servidor'}; subiendo {mb:.1f} MB…")
        scp([db], f"{REMOTE}/archive.db.new", a.simular)
        if not a.simular:
            check = ssh(f"sha256sum {REMOTE}/archive.db.new").split()
            if not check or check[0] != mine:
                raise RuntimeError("la copia del servidor no coincide con la local; no se sustituye (vuelve a lanzarlo)")
        ssh(f"mv -f {REMOTE}/archive.db.new {REMOTE}/archive.db", a.simular, capture=not a.simular)
        print("  sustituida.")
        if not a.simular:
            n = ssh(f"python3 -c \"import sqlite3; print(sqlite3.connect('file:{REMOTE}/archive.db?mode=ro', uri=True).execute('SELECT COUNT(*) FROM ar_games').fetchone()[0])\"").strip()
            print(f"  el servidor la lee: {n} partidas.")
    print("Hecho." + (f" ({len(bad)} fichero(s) saltados: revisa los avisos)" if bad else ""))
    return 0 if not bad else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as e:
        print(f"ERROR: {e}")
        sys.exit(2)
