#!/usr/bin/env python3
"""
T17: reconstruye sm2_state desde el historial COMPLETO de attempts (solo
run_id IS NOT NULL, es decir Runs/Review — igual que en produccion), re-
jugando cada secuencia en orden cronologico con la misma logica que
updateSm2() en tsumevault.html (version corregida T16: 'interval' guarda
SIEMPRE el valor puro/canonico, el jitter solo decide due_date de cada paso).

La logica de sm2_replay.py esta validada por separado, campo a campo, contra
el codigo JS real (ver validate_js.js / compare_js_python.py): no es una
reimplementacion "de memoria", reproduce exactamente updateSm2().

ALCANCE (decisiones acordadas con Victor):
  - Se cuenta el historial COMPLETO, incluidos los intentos anteriores al
    lanzamiento de SM-2 (no hay forma de saber "que se habria calculado
    entonces"; se reconstruye como si el sistema hubiera existido siempre).
  - Se reconstruye repetitions, interval, easiness Y due_date (no solo
    repetitions): el intervalo/fecha son precisamente lo que estaba mal.
  - Se recalculan TODOS los problemas con al menos un intento run_id IS NOT
    NULL, no solo los que hoy muestran discrepancia (T16 tambien pudo haber
    inflado 'interval' en problemas donde 'repetitions' ya coincidia).

USO:
  Dry-run (por defecto, NO escribe nada en la base de datos):
    python3 recalc_sm2.py /ruta/a/tsumeVault.db

  Aplicar de verdad:
    python3 recalc_sm2.py /ruta/a/tsumeVault.db --apply

  Limitar a un source concreto (util para probar primero, ej. el mas pequeno):
    python3 recalc_sm2.py /ruta/a/tsumeVault.db --source 101_weiqi

Salida: SIEMPRE genera un informe CSV (sm2_recalc_report_<timestamp>.csv) en
el directorio actual, con una fila por problema con historial, antes/despues
de cada campo y si cambia o no. Con --apply, ademas escribe en sm2_state y
deja la base de datos consolidada (WAL truncado, journal_mode=DELETE) para
poder subirla de vuelta sin ficheros -wal/-shm sueltos.
"""
import sqlite3, sys, csv, random, argparse, io, re
from datetime import datetime, timedelta, timezone
from collections import defaultdict

from sm2_replay import replay_sm2


def local_date_str(d):
    return d.strftime('%Y-%m-%d')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('db_path', help='Ruta al fichero tsumeVault.db (backup/snapshot, no la BD viva)')
    ap.add_argument('--apply', action='store_true',
                     help='Escribe los cambios de verdad. Por defecto: solo genera el informe, no toca la BD.')
    ap.add_argument('--source', default=None,
                     help='Limitar a un source concreto (opcional, util para probar primero)')
    args = ap.parse_args()

    con = sqlite3.connect(args.db_path)
    con.row_factory = sqlite3.Row

    # PRAGMA integrity_check primero: si la copia esta genuinamente corrupta,
    # abortar antes de tocar nada. EXCEPCION conocida y verificada: mensajes
    # del tipo "Page N: never used" son paginas huerfanas (reservadas pero
    # no enlazadas a ninguna tabla/indice) — un patron benigno, comun tras un
    # `.backup` de una BD en WAL que sigue viva, y NO indica perdida ni
    # corrupcion de ninguna fila/tabla/indice real. Se confirmo (Victor,
    # T17) que el mismo patron aparece incluso corriendo integrity_check
    # DIRECTAMENTE en el servidor Hetzner (no lo introdujo la descarga), y
    # que PRAGMA quick_check tambien da limpio salvo por estos mismos avisos.
    # Por eso: si TODAS las lineas son "Page N: never used", se continua
    # (con aviso). Cualquier otro tipo de mensaje (indices rotos, filas
    # perdidas, arboles corruptos, etc.) sigue abortando, sin excepcion.
    # NOTA: PRAGMA integrity_check puede devolver los mensajes como una fila
    # por mensaje, O como una sola fila con todos los mensajes concatenados
    # por '\n' dentro del mismo texto (visto en Windows/algunas versiones de
    # sqlite3) — se separa aqui explicitamente para no depender de como los
    # empaquete el driver en cada plataforma.
    raw_rows = [r[0] for r in con.execute("PRAGMA integrity_check").fetchall()]
    rows_integrity = []
    for r in raw_rows:
        rows_integrity.extend(r.split('\n'))

    NEVER_USED_RE = re.compile(r'^Page \d+: never used$')
    HEADER_RE = re.compile(r'^\*\*\* in database .+ \*\*\*$')  # linea de seccion, no es un problema en si

    def is_benign(line):
        return bool(NEVER_USED_RE.match(line) or HEADER_RE.match(line))

    if rows_integrity == ['ok']:
        pass  # limpio del todo
    elif all(is_benign(line) for line in rows_integrity):
        n_paginas = sum(1 for line in rows_integrity if NEVER_USED_RE.match(line))
        print(f"AVISO: integrity_check encontro {n_paginas} paginas 'never used' "
              f"(huerfanas, benignas — verificado que ya estan asi en el servidor). Se continua.")
    else:
        print("ABORTADO: integrity_check encontro problemas que NO son del tipo 'Page N: never used'.")
        print("No se toca la base de datos. Mensajes completos:")
        for line in rows_integrity:
            print("  " + line)
        sys.exit(1)

    where_source = "AND source = ?" if args.source else ""
    params = [args.source] if args.source else []

    print("Leyendo historial de attempts (run_id IS NOT NULL)...")
    rows = con.execute(f"""
        SELECT source, problem_id, result, created_at, id
        FROM attempts
        WHERE run_id IS NOT NULL {where_source}
        ORDER BY source, problem_id, created_at ASC, id ASC
    """, params).fetchall()

    by_problem = defaultdict(list)
    last_attempt_date = {}
    for r in rows:
        key = (r['source'], r['problem_id'])
        by_problem[key].append(r['result'])
        # created_at esta en UTC ('YYYY-MM-DDTHH:MM:SSZ'); tomamos la fecha
        # calendario tal cual (aproximacion deliberada: la diferencia con la
        # fecha local exacta de Victor es como mucho de un dia en el peor
        # caso, insignificante frente a los intervalos que manejamos aqui,
        # de 6 dias en adelante).
        last_attempt_date[key] = r['created_at'][:10]

    print(f"Problemas con historial de Runs/Review: {len(by_problem)}")

    now_iso = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    report_rows = []
    changed = 0
    rng = random.Random()  # generador propio, no afecta a random global

    for (source, problem_id), results in sorted(by_problem.items()):
        num_fallos = sum(1 for r in results if r == 'wrong')

        interval, easiness, repetitions, days_until_due = replay_sm2(results, rng.random)

        # IMPORTANTE: el ancla de la fecha es la fecha del ULTIMO intento
        # real de este problema, NO la fecha en la que se ejecuta este
        # script. updateSm2() en produccion siempre calcula due_date como
        # "el dia en que se juega + dias_hasta_vencer" — aqui reconstruimos
        # historia, asi que el "dia en que se jugo" es el del ultimo intento
        # real, no hoy. Usar 'hoy' como ancla (como se hizo en una version
        # anterior de este script) empuja TODAS las fechas nuevas hacia el
        # futuro desde el momento de la reparacion, sin relacion con cuando
        # se jugo de verdad — un bug real, detectado porque el informe daba
        # sistematicamente 0 problemas vencidos tras la reparacion, algo
        # imposible sabiendo que ya habia 231 vencidos con las fechas viejas.
        anchor = datetime.strptime(last_attempt_date[(source, problem_id)], '%Y-%m-%d')
        due = anchor + timedelta(days=round(days_until_due))
        due_date = local_date_str(due)
        dias_desde_ultimo_intento = (datetime.now() - anchor).days

        current = con.execute("""
            SELECT due_date, interval, easiness, repetitions FROM sm2_state
            WHERE source=? AND problem_id=?
        """, (source, problem_id)).fetchone()

        old_due = current['due_date'] if current else None
        old_interval = current['interval'] if current else None
        old_easiness = current['easiness'] if current else None
        old_repetitions = current['repetitions'] if current else None

        # IMPORTANTE: la decision de "necesita reparacion" se basa SOLO en
        # repetitions/interval/easiness (los campos que el bug pudo haber
        # descuadrado). due_date lleva jitter aleatorio: si lo comparamos
        # tambien, CUALQUIER problema recalculado parece "cambiar" solo
        # porque el sorteo dio un numero distinto al de la ultima vez que se
        # jugo de verdad, aunque el estado ya fuera perfectamente correcto.
        # Eso barajaria fechas de repaso que nunca estuvieron mal. Por eso:
        # si repetitions/interval/easiness YA coinciden, NO se toca la fila
        # (ni siquiera due_date se recalcula) — se deja tal cual estaba.
        needs_fix = (
            current is None or
            old_repetitions != repetitions or
            abs((old_interval or 0) - interval) > 0.01 or
            abs((old_easiness or 0) - easiness) > 0.001
        )

        if needs_fix:
            changed += 1
            new_due_date = due_date
        else:
            new_due_date = old_due  # se conserva la fecha existente, no se re-sortea sin motivo

        report_rows.append({
            'source': source, 'problem_id': problem_id,
            'num_attempts': len(results), 'num_fallos': num_fallos,
            'ultimo_intento': last_attempt_date[(source, problem_id)],
            'dias_desde_ultimo_intento': dias_desde_ultimo_intento,
            'repetitions_antes': old_repetitions, 'repetitions_despues': repetitions,
            'interval_antes': old_interval, 'interval_despues': interval,
            'due_date_antes': old_due, 'due_date_despues': new_due_date,
            'easiness_antes': old_easiness, 'easiness_despues': round(easiness, 3),
            'cambia': 'SI' if needs_fix else 'NO',
        })

        if args.apply and needs_fix:
            con.execute("""
                INSERT INTO sm2_state (source, problem_id, due_date, interval, easiness, repetitions, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source, problem_id) DO UPDATE SET
                    due_date    = excluded.due_date,
                    interval    = excluded.interval,
                    easiness    = excluded.easiness,
                    repetitions = excluded.repetitions,
                    updated_at  = excluded.updated_at
            """, (source, problem_id, due_date, interval, easiness, repetitions, now_iso))

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_path = f"sm2_recalc_report_{ts}.csv"
    if report_rows:
        with io.open(report_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(report_rows[0].keys()))
            writer.writeheader()
            writer.writerows(report_rows)
        print(f"Informe generado: {report_path}")
    else:
        print("Sin problemas que procesar (no hay attempts con run_id).")

    print(f"Problemas con cambios: {changed} de {len(by_problem)}")

    if args.apply:
        con.commit()
        # Consolidar el WAL en un unico fichero .db, sin -wal/-shm sueltos,
        # listo para copiar de vuelta con scp.
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        con.execute("PRAGMA journal_mode=DELETE")
        con.commit()
        print(f"CAMBIOS APLICADOS a la base de datos ({changed} filas escritas en sm2_state).")
        print("Base de datos consolidada (WAL truncado, journal_mode=DELETE).")
    else:
        print("DRY-RUN: no se ha escrito nada. Revisa el CSV y ejecuta con --apply para aplicar.")

    con.close()


if __name__ == '__main__':
    main()
