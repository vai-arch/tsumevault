import re, json, sys, os, glob, collections

_TOKEN = re.compile(r'[\s,]*(#\{|[\[\]{}()]|"(?:[^"\\]|\\.)*"|[^\s,\[\]{}()"]+)')

def parse_edn(text):
    toks = _TOKEN.findall(text)
    pos = 0
    def val():
        nonlocal pos
        t = toks[pos]; pos += 1
        if t == '[':
            out = []
            while toks[pos] != ']': out.append(val())
            pos += 1
            return tuple(out)
        if t == '(':
            out = []
            while toks[pos] != ')': out.append(val())
            pos += 1
            return tuple(out)    
        if t == '#{':
            out = []
            while toks[pos] != '}': out.append(val())
            pos += 1
            return frozenset(out)
        if t == '{':
            d = {}
            while toks[pos] != '}':
                k = val(); d[k] = val()
            pos += 1
            return d
        if t.startswith('"'): return json.loads(t)
        if t == 'nil': return None
        if t in ('true', 'false'): return t == 'true'
        if re.fullmatch(r'-?\d+', t): return int(t)
        return t  # keywords como ':black'
    v = val()
    if pos != len(toks): raise ValueError("EDN con tokens sobrantes")
    return v

def leaves(children, path=()):
    for ch in children or ():
        p = path + (ch[':move'],)
        if ch.get(':children'):
            yield from leaves(ch[':children'], p)
        else:
            yield p

def node_keys(children, acc):
    for ch in children or ():
        acc.update(ch.keys()); node_keys(ch.get(':children'), acc)

def main(folder):
    top_keys, nkeys = collections.Counter(), set()
    sizes, toplay = collections.Counter(), collections.Counter()
    sin_correcta, con_marcas, tp_raro, raros = [], [], [], []
    files = sorted(glob.glob(os.path.join(folder, '*.json')))
    for f in files:
        d = json.load(open(f, encoding='utf-8'))
        pid = d['id'][:8]
        t = parse_edn(d['variations'])
        top_keys.update(t.keys()); node_keys(t.get(':children'), nkeys)
        sizes[t.get(':board-size')] += 1; toplay[d['to-play']] += 1
        if t.get(':to-play') and t[':to-play'] != ':' + d['to-play']: tp_raro.append(pid)
        m = t.get(':marks') or {}
        if any(m.get(k) for k in (':circle', ':square')) or t.get(':labels'): con_marcas.append(pid)
        first = ':' + d['to-play']
        ls = list(leaves(t.get(':children')))
        buenas = [l for l in ls if l[-1][1] == first]
        if not ls: raros.append(pid + ' (sin variantes)')
        elif not buenas: sin_correcta.append(pid)
    print('ficheros:', len(files))
    print('campos de nivel superior en variations:', dict(top_keys))
    print('claves de nodo:', sorted(nkeys))
    print('board-size:', dict(sizes), '| to-play:', dict(toplay))
    print('to-play distinto entre campo y EDN:', tp_raro)
    print('con círculos/cuadrados/labels:', con_marcas)
    print('sin variantes:', raros)
    print('sin ninguna línea que acabe en jugada del que empieza:', sin_correcta)

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'problems_raw')