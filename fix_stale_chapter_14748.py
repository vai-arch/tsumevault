#!/usr/bin/env python3
"""T33 one-off: borra el capitulo huerfano 'my_collections / 01-L-shape' (id 14748),
sus problemas y sus intentos. Hace backup (.backup API) antes. Uso:
    python fix_stale_chapter_14748.py tsumevault.db            # simulacion (no cambia nada)
    python fix_stale_chapter_14748.py tsumevault.db --apply    # aplica
"""
import sqlite3, sys, time, os

CH = 14748
db = sys.argv[1]
apply = "--apply" in sys.argv
con = sqlite3.connect(db)
con.row_factory = sqlite3.Row

ch = con.execute("SELECT * FROM chapters WHERE id=?", (CH,)).fetchone()
assert ch is not None, "capitulo 14748 no existe (ya borrado?)"
assert ch["source"] == "my_collections" and ch["name"] == "01-L-shape", dict(ch)
probs = con.execute("SELECT source, problem_id FROM problems WHERE chapter_id=?", (CH,)).fetchall()
assert len(probs) == 15, f"se esperaban 15 problemas, hay {len(probs)}"
q = "FROM {t} WHERE (source, problem_id) IN (SELECT source, problem_id FROM problems WHERE chapter_id=?)"
n_att = con.execute("SELECT COUNT(*) " + q.format(t="attempts"), (CH,)).fetchone()[0]
n_ri = con.execute("SELECT COUNT(*) " + q.format(t="run_items"), (CH,)).fetchone()[0]
n_sm = con.execute("SELECT COUNT(*) FROM sm2_state WHERE (source, problem_id) IN "
                   "(SELECT source, CAST(problem_id AS TEXT) FROM problems WHERE chapter_id=?)", (CH,)).fetchone()[0]
n_run = con.execute("SELECT COUNT(*) FROM runs WHERE chapter_id=?", (CH,)).fetchone()[0]
print(f"capitulo {CH}: problemas={len(probs)} intentos={n_att} run_items={n_ri} sm2={n_sm} runs={n_run}")
assert n_ri == 0 and n_sm == 0 and n_run == 0, "hay dependencias inesperadas; aborto"
col_before = con.execute("SELECT num_problems, chapter_count FROM collections WHERE source=? AND set_id=?",
                         (ch["source"], ch["set_id"])).fetchone()
print("coleccion antes:", dict(col_before) if col_before else None)
if not apply:
    print("SIMULACION: nada modificado. Repite con --apply"); sys.exit(0)

bak = f"{os.path.splitext(db)[0]}_backup_{time.strftime('%Y%m%d_%H%M%S')}.db"
b = sqlite3.connect(bak); con.backup(b); b.close()
print("backup:", bak)

with con:  # una transaccion
    con.execute("DELETE " + q.format(t="attempts"), (CH,))
    con.execute("DELETE FROM problems WHERE chapter_id=?", (CH,))
    con.execute("DELETE FROM chapters WHERE id=?", (CH,))
    con.execute("UPDATE collections SET "
                "num_problems=(SELECT COUNT(*) FROM problems WHERE source=? AND set_id=?), "
                "chapter_count=(SELECT COUNT(*) FROM chapters WHERE source=? AND set_id=?) "
                "WHERE source=? AND set_id=?",
                (ch["source"], ch["set_id"]) * 3)
col_after = con.execute("SELECT num_problems, chapter_count FROM collections WHERE source=? AND set_id=?",
                        (ch["source"], ch["set_id"])).fetchone()
print("coleccion despues:", dict(col_after))
assert con.execute("SELECT COUNT(*) FROM chapters WHERE id=?", (CH,)).fetchone()[0] == 0
print("OK")
