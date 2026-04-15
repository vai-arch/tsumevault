import sqlite3
con = sqlite3.connect('tsumeVault.db')
con.execute("DELETE FROM problems WHERE source='guo_juan'")
con.execute("DELETE FROM chapters WHERE source='guo_juan'")
con.execute("DELETE FROM collections WHERE source='guo_juan'")
con.commit()
con.close()