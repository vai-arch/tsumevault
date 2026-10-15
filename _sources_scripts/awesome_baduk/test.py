import json, sys
sys.path.insert(0, '.')
import awesome_to_player as a

CID = 'd7P7EfIVERczbQP2BLuG'
for cid, course in a.load_course('lessons.json'):
    if cid != CID:
        continue
    clip = course['clips'][1]            # Clip 02
    ev = a.edn(clip['events'])
    for ms, e in ev:
        if 93000 <= ms <= 115000:
            print(f'{ms/1000:7.1f}s  {e}')