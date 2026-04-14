import sqlite3
con = sqlite3.connect('tsumeVault.db')
rows = con.execute("SELECT name, problem_count FROM chapters WHERE source='guo_juan' LIMIT 20").fetchall()
for r in rows: print(r)
print("Total chapters:", con.execute("SELECT COUNT(*) FROM chapters WHERE source='guo_juan'").fetchone()[0])