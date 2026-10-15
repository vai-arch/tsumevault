import awesome_to_player as a
B, W = a.B, a.W
# misma transcripcion de la captura que diag_inicio.py
REAL_TXT = {
    0: {17: 'B'},
    1: {14: 'W', 15: 'W', 16: 'W', 17: 'B', 18: 'W'},
    2: {14: 'B', 15: 'B', 16: 'W', 17: 'B'},
    3: {11: 'W', 13: 'W', 14: 'W', 15: 'W', 16: 'B', 17: 'B', 18: 'B'},
    4: {12: 'W', 13: 'B', 14: 'B', 15: 'B', 16: 'W', 17: 'W', 18: 'W'},
    5: {16: 'W', 18: 'W'},
    6: {13: 'B', 15: 'B', 16: 'B', 17: 'W'},
    7: {17: 'B'},
    8: {16: 'B'},
    11: {2: 'W', 3: 'W', 4: 'W', 5: 'B', 6: 'B', 7: 'W'},
    12: {0: 'W', 1: 'W', 2: 'W', 3: 'B', 4: 'B', 5: 'W', 6: 'W'},
    13: {0: 'B', 1: 'B', 2: 'B', 3: 'B', 4: 'W'},
    14: {0: 'W', 1: 'W', 2: 'W', 3: 'B', 7: 'W'},
    15: {1: 'W', 2: 'W', 3: 'B', 4: 'B', 5: 'W'},
    16: {0: 'B', 1: 'W', 2: 'B', 3: 'B', 4: 'W', 5: 'W'},
    17: {0: 'B', 1: 'W', 2: 'B', 4: 'B', 5: 'W'},
    18: {1: 'W', 2: 'B', 3: 'B', 4: 'B', 5: 'W'},
}
REAL = {(x, y): (B if c == 'B' else W) for y, row in REAL_TXT.items() for x, c in row.items()}


def show(g, title, size=19):
    print(f'\n{title}')
    print('   ' + ' '.join(chr(97 + i) for i in range(size)))
    for y in range(size):
        print(f'{chr(97 + y)}  ' + ' '.join({B: 'X', W: 'O'}.get(g.get((x, y)), '.') for x in range(size)))



