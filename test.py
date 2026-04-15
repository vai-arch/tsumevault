import os, re

base = r'D:\GoVideos\Guo Juan\tsumevault\guo_juan\problems_std'
count = 0
total = 0
for root, dirs, files in os.walk(base):
    for f in files:
        if f.endswith('.sgf'):
            total += 1
            path = os.path.join(root, f)
            with open(path, encoding='utf-8', errors='ignore') as fh:
                content = fh.read()
            if 'DONOTSWAP' in content:
                count += 1

print(f'DONOTSWAP: {count} / {total}')