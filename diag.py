import sqlite3
con = sqlite3.connect("tsumeVault.db")
rows = con.execute("PRAGMA integrity_check").fetchall()
print("num filas:", len(rows))
for r in rows[:5]:
    print(repr(r))