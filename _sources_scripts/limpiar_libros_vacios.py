# limpiar_books_vacios.py
import os, sys

root = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), '101_weiqi', 'problems')
do_delete = '--delete' in sys.argv

removed = 0
for book_id in os.listdir(root):
    book_path = os.path.join(root, book_id)
    if not os.path.isdir(book_path):
        continue
    contents = os.listdir(book_path)
    has_chapters = any(os.path.isdir(os.path.join(book_path, d)) for d in contents)
    if not has_chapters:
        print(f"{'BORRAR' if do_delete else 'DRY-RUN'} book vacío: {book_path}  ({contents})")
        if do_delete:
            for f in contents:
                os.remove(os.path.join(book_path, f))
            os.rmdir(book_path)
        removed += 1

print(f"\n{'Borrados' if do_delete else 'Encontrados'}: {removed} books vacíos")
if not do_delete:
    print("Usa --delete para borrar de verdad.")