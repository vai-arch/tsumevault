from pathlib import Path

BASE_DIR = Path("many_faces", "problems_std")


def rename_sgf_files():
    for chapter_dir in BASE_DIR.iterdir():
        if not chapter_dir.is_dir():
            continue

        chapter_name = chapter_dir.name

        for sgf in chapter_dir.glob("*.sgf"):
            if sgf.name.startswith(chapter_name + "_"):
                continue  # ya está renombrado

            new_name = f"{chapter_name}_{sgf.name}"
            new_path = sgf.with_name(new_name)

            print(f"{sgf.name} -> {new_name}")
            sgf.rename(new_path)

    print("OK")


if __name__ == "__main__":
    rename_sgf_files()
