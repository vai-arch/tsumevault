import sqlite3

con = sqlite3.connect('tsumeVault.db')

print('--- collections ---')
for r in con.execute(
    "SELECT set_id, name, folder, difficulty_num, num_problems, chapter_count, on_disk "
    "FROM collections WHERE source='my_collections'"
):
    print(r)

print('--- chapters ---')
for r in con.execute(
    "SELECT id, set_id, chapter_num, name, diff_avg, problem_count, mostrar "
    "FROM chapters WHERE source='my_collections' ORDER BY set_id, chapter_num"
):
    print(r)