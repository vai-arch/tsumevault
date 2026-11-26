#!/usr/bin/env python3
"""AR2 (WORKPLAN_ARCHIVO.md): sube al VPS lo nuevo del archivo de partidas.

    python kifumaster/kifu_upload.py              (o _subir_archivo.bat desde la raíz)
    python kifumaster/kifu_upload.py --simular    enseña lo que haría, sin subir nada

1. SGF: compara kifumaster/data/lists/<torneo>/<edición>/<id>.sgf del portátil con el sgf/ del
   servidor (misma estructura) y sube solo los que faltan (scp por carpeta, en tandas). Si el servidor
   ya lo tiene en otra ruta (la partida cambió de edición, o el antiguo sgf/<xx>/), lo mueve allí mismo
   en vez de subirlo otra vez. Los que no parecen un SGF ("(;" al principio) se saltan y se avisa.
   Al terminar toca sgf/.stamp para que el servidor vea los cambios al momento.
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
    """id → (ruta local, ruta relativa <torneo>/<edición>/<id>.sgf) de lists/; y los que no valen."""
    root = os.path.join(DATA, "lists")
    ok, bad = {}, []
    if not os.path.isdir(root):
        return ok, bad
    for d, _, files in os.walk(root):
        for n in sorted(files):
            if not n.lower().endswith(".sgf"):
                continue
            p = os.path.join(d, n)
            rel_parts = os.path.relpath(p, root).replace("\\", "/").split("/")
            gid = n[:-4].lower()
            if not _ID.match(gid) or len(rel_parts) != 3:
                bad.append((p, "no sigue lists/<torneo>/<edición>/<id>.sgf")); continue
            with open(p, "rb") as f:
                head = f.read(64).lstrip(b"\xef\xbb\xbf \t\r\n")
            if not head.startswith(b"(;"):
                bad.append((p, "no parece un SGF")); continue
            if gid in ok:
                bad.append((p, f"repetido (ya está en {ok[gid][1]}; ejecuta kifu_build)")); continue
            ok[gid] = (p, "/".join(rel_parts[:2] + [gid + ".sgf"]))
    return ok, bad


def sh_quote(s):
    """Comillas para el shell remoto (los slugs pueden llevar caracteres no ASCII)."""
    return "'" + s.replace("'", "'\\''") + "'"


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
    remote = {}
    for l in remote_txt.splitlines():
        l = l.strip()
        if l.endswith(".sgf"):
            rel = l[2:] if l.startswith("./") else l
            remote.setdefault(os.path.basename(rel)[:-4].lower(), rel)
    new = sorted(g for g in local if g not in remote)
    move = sorted(g for g in local if g in remote and remote[g] != local[g][1])
    print(f"SGF: {len(local)} en el portátil, {len(remote)} en el servidor, {len(new)} por subir, {len(move)} por mover.")
    dirs = sorted({local[g][1].rsplit("/", 1)[0] for g in new + move})
    if dirs:
        ssh("mkdir -p " + " ".join(sh_quote(f"{REMOTE}/sgf/{d}") for d in dirs), a.simular, capture=not a.simular)
    for g in move:
        ssh(f"mv -n {sh_quote(REMOTE + '/sgf/' + remote[g])} {sh_quote(REMOTE + '/sgf/' + local[g][1])}", a.simular, capture=not a.simular)
    if move:
        print(f"  movidos en el servidor {len(move)}.")
    for d in sorted({local[g][1].rsplit("/", 1)[0] for g in new}):
        files = [local[g][0] for g in new if local[g][1].rsplit("/", 1)[0] == d]
        for i in range(0, len(files), BATCH):
            scp(files[i:i + BATCH], f"{REMOTE}/sgf/{d}/", a.simular)
    if new:
        print(f"  subidos {len(new)}.")
    if new or move:
        ssh(f"touch {REMOTE}/sgf/.stamp", a.simular, capture=not a.simular)

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
