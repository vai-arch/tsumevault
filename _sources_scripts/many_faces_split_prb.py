import os
import re

BASE_DIR = os.path.join(os.path.dirname(__file__), "many_faces")

def split_sgf(content):
    """
    Extrae partidas SGF individuales usando balanceo de paréntesis.
    """
    games = []
    stack = 0
    start = None

    for i, char in enumerate(content):
        if char == '(':
            if stack == 0:
                start = i
            stack += 1
        elif char == ')':
            stack -= 1
            if stack == 0 and start is not None:
                games.append(content[start:i+1])
                start = None

    return games


def process_prb_file(filepath):
    filename = os.path.basename(filepath)
    name, _ = os.path.splitext(filename)

    output_dir = os.path.join(BASE_DIR, name)
    os.makedirs(output_dir, exist_ok=True)

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    games = split_sgf(content)

    for i, game in enumerate(games, start=1):
        output_file = os.path.join(output_dir, f"problem_{i:03}.sgf")
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(game)

    print(f"{filename}: {len(games)} problemas extraídos.")


def main():
    for file in os.listdir(BASE_DIR):
        if file.endswith(".prb"):
            process_prb_file(os.path.join(BASE_DIR, file))


if __name__ == "__main__":
    main()