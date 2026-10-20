#!/usr/bin/env python3
"""JP1: pruebas de generate_joseki_problems.py (sin servidor).

    python test_generate_joseki.py      (luego: node test_joseki_problems_client.js)

Usa dos ficheros de prueba propios en jp_fixtures/ (no tu joseki/, que va
cambiando): una copia de tu 4-4 con la rama ¿y si? de W en R18 nombrada
("Corner Hane") y un 3-3 sintético con jugadas malas, dudosas, comentarios que
empiezan por RIGHT y un ']' en un comentario. Deja los SGF generados en
jp_test_out/ para la prueba de humo con el parser real de WGo.
"""
import io
import os
import shutil
import sys
import tempfile

import generate_joseki_problems as G
from joseki_lib import compile_joseki
from sgf_lib import parse_sgf, validate_problem

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "jp_fixtures")
FAILS = []
N = [0]


def check(name, cond, extra=""):
    N[0] += 1
    print(("PASS " if cond else "FAIL ") + name + (("  " + str(extra)) if extra and not cond else ""))
    if not cond:
        FAILS.append(name)


def read(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as fh:
        return fh.read()


def gen(text, stem):
    res = compile_joseki(text.encode("utf-8"), stem)   # como el generador
    assert res["ok"], res["issues"]
    return G.generate_file(res["data"], stem)


def byid(problems):
    return {p["problem_id"]: p for p in problems}


def quiet_run(*a, **k):
    lines = []
    rc = G.run(*a, out=lines.append, **k)
    return rc, "\n".join(lines)


T44 = read("4-4 Joseki.sgf")
T33 = read("3-3 Test.sgf")

# ── 4-4: estructura ──────────────────────────────────────────────────────────
P44, E44, W44 = gen(T44, "4-4 Joseki")
I44 = byid(P44)
check("4-4: sin errores", E44 == [], E44)
EXPECTED_IDS = {
    "4-4 Joseki/B-pdncqfpbqckc", "4-4 Joseki/W-pdncqfpbqckc",
    "4-4 Joseki/B-pdncqfpbqckcttqbqi", "4-4 Joseki/W-pdncqfpbqckcttqbqi",
    "4-4 Joseki/W-pdncqfpbqckcttqbttqh",
    "4-4 Joseki/B-pdncqfpbqckcttqhqb", "4-4 Joseki/W-pdncqfpbqckcttqhqb",
    "4-4 Joseki/B-pdncqfpbqckcqboc",
    "4-4 Joseki/W-pdncqfpbqckcqb", "4-4 Joseki/W-pdncqfpbqckcqbttobocpcnbpa",
    "4-4 Joseki/B-pdncqfpbqckcqbttobocpcnbpatt",
    "4-4 Joseki/B-pdncpfpbqckcqj", "4-4 Joseki/W-pdncpfpbqckcqj",
    "4-4 Joseki/W-pdncpfpbqckcttqhqbrf", "4-4 Joseki/W-pdncpfpbqckcttqhqf",
}
check("4-4: exactamente los 15 problemas esperados (14 línea×color, +1 por el corte de tu tenuki)",
      set(I44) == EXPECTED_IDS, sorted(set(I44) ^ EXPECTED_IDS))
check("4-4: ids únicos", len(P44) == len(I44))
check("4-4: capítulos = familia × color",
      {p["chapter"] for p in P44} == {"Keima Approach · B", "Keima Approach · W"})
check("4-4: orden dentro del capítulo 1..n sin huecos",
      all(sorted(p["order"] for p in P44 if p["chapter"] == ch) == list(range(1, 1 + sum(1 for q in P44 if q["chapter"] == ch)))
          for ch in {p["chapter"] for p in P44}))
check("4-4: rutas estables joseki_problems/<fichero>/<id corto>.sgf",
      all(p["rel_path"] == p["problem_id"] + ".sgf" for p in P44))
check("4-4: avisa de las dos líneas de castigo que acaban en el error del rival",
      len(W44) == 2 and all(w["sev"] == "warn" and "castigo" in w["problem"] for w in W44), W44)

# ── 4-4: el ejemplo literal acordado con Victor ──────────────────────────────
LOW_B = ("(;GM[1]FF[4]CA[UTF-8]SZ[19]PL[B]AB[pd]AW[nc]CR[nc]C[4-4 Joseki · Juegas B\n"
         "Keima Approach\n"
         "→ Ahora: Low Enclosure];B[qf]C[Low Enclosure];W[pb]C[Slide];B[qc]C[Take the corner];W[kc]C[RIGHT\n"
         "2 spaces extension])\n")
check("ejemplo Low Enclosure · B: SGF literal (Q16+O17 puestas, O17 marcada, instrucción, RIGHT final)",
      I44["4-4 Joseki/B-pdncqfpbqckc"]["sgf"] == LOW_B, I44["4-4 Joseki/B-pdncqfpbqckc"]["sgf"])
lw = I44["4-4 Joseki/W-pdncqfpbqckc"]["sgf"]
LOW_W = ("(;GM[1]FF[4]CA[UTF-8]SZ[19]PL[W]AB[pd][qf]AW[nc]CR[qf]C[4-4 Joseki · Juegas W\n"
         "Low Enclosure];W[pb]C[Slide];B[qc]C[Take the corner];W[kc]C[RIGHT\n"
         "2 spaces extension])\n")
check("W: tu 1.ª piedra (O17) ya puesta con la respuesta de negro (R14, marcada y con su comentario); empiezas en Q18",
      lw == LOW_W, lw)
import re as _re
def _setup(sgf, prop):
    m = _re.search(prop + r"((?:\[[a-s]{2}\])+)", sgf.split(";")[1])
    return set(_re.findall(r"[a-s]{2}", m.group(1))) if m else set()
def _first_move(sgf):
    return _re.search(r";([BW])\[([a-s]{0,2})\]", sgf[sgf.index(";", 1):]).groups()
check("toda línea: tu primera piedra va siempre puesta (B: Q16; W: O17) y nunca empiezas jugándola",
      all("pd" in _setup(p["sgf"], "AB") and (p["color"] == "B" or "nc" in _setup(p["sgf"], "AW"))
          and _first_move(p["sgf"]) not in (("B", "pd"), ("W", "nc")) for p in P44),
      [p["problem_id"] for p in P44 if not ("pd" in _setup(p["sgf"], "AB") and (p["color"] == "B" or "nc" in _setup(p["sgf"], "AW")))])
check("toda línea: cada problema tiene al menos una jugada tuya", all(";%s[" % p["color"] in p["sgf"] for p in P44 + gen(T33, "3-3 Test")[0]))
check("High 1 point · B: instrucción con el nombre de la otra rama buena",
      "→ Ahora: High 1 point extension" in I44["4-4 Joseki/B-pdncpfpbqckcqj"]["sgf"])

# ── 4-4: pases y tenuki ──────────────────────────────────────────────────────
s = I44["4-4 Joseki/W-pdncqfpbqckcttqbqi"]["sgf"]
check("pase del rival (implícito): B[] con 'Tenuki.' e instrucción ¿y si? para tu jugada IT",
      ";B[]C[Tenuki.\n→ ¿Y si…? Corner Hane];W[qb]" in s, s)
s = I44["4-4 Joseki/B-pdncqfpbqckcttqbqi"]["sgf"]
check("tu pase implícito: el tramo previo no se genera y la continuación empieza tras R18 de W",
      "PL[B]AB[pd][qc][qf]AW[kc][nc][pb][qb]CR[qb]" in s and "(Tras tu tenuki)" in s and s.count(";B[") == 1, s)
s = I44["4-4 Joseki/W-pdncqfpbqckcqb"]["sgf"]
check("tu tenuki a mitad de línea: el problema acaba antes con '→ Ahora tenuki'",
      s.rstrip().endswith("→ Ahora tenuki. Tenuki])") and "RIGHT" in s, s)
s = I44["4-4 Joseki/W-pdncqfpbqckcqbttobocpcnbpa"]["sgf"]
check("…y lo que sigue es otro problema con todo lo anterior puesto",
      "PL[W]AB[ob][pd][qb][qc][qf]AW[kc][nc][pb]CR[ob]" in s and "(Tras tu tenuki)" in s
      and s.rstrip().endswith("→ Ahora tenuki])"), s)
check("tu tenuki al final de la línea: no hay continuación", not any(k.endswith("pa" + "tt") and "/W-" in k for k in I44))
s = I44["4-4 Joseki/B-pdncqfpbqckcqbttobocpcnbpatt"]["sgf"]
check("pase final del rival: W[] con RIGHT y 'Tenuki.'", s.rstrip().endswith(";W[]TE[1]C[RIGHT\nTenuki.])"), s)
check("ningún tramo duplicado (fusión por secuencia)", len(P44) == len(set(p["sgf"] for p in P44)))
s = I44["4-4 Joseki/W-pdncpfpbqckcttqhqf"]["sgf"]
check("marcas del maestro (TR) copiadas a la jugada", ";B[qf]TR[pf]BM[1]C[RIGHT" in s, s)

# ── T33: marcas de calidad copiadas a los SGF generados ─────────────────────
s = I44["4-4 Joseki/B-pdncqfpbqckcqboc"]["sgf"]
check("T33: tu jugada ¿y si? lleva IT[] y la mala del rival BM[1]", ";B[qb]IT[]C[" in s and ";W[oc]TR[pb]BM[1]C[RIGHT" in s, s)
s = I44["4-4 Joseki/B-pdncqfpbqckcttqbqi"]["sgf"]
check("T33: la buena con TE lleva TE[1]", ";B[qi]TE[1]C[RIGHT" in s, s)
s = I44["4-4 Joseki/W-pdncqfpbqckcttqbqi"]["sgf"]
check("T33: el pase implícito NO lleva IT (no es una jugada del fichero); la rama ¿y si? sí", ";B[]C[Tenuki." in s and ";W[qb]IT[]C[Corner Hane]" in s, s)
check("T33: las jugadas sin marca no llevan ninguna (el ejemplo Low Enclosure no cambia)",
      not any(t in I44["4-4 Joseki/B-pdncqfpbqckc"]["sgf"] for t in ("IT[", "BM[", "DO[", "TE[")))

# ── 3-3 sintético: WRONG, dudosas, escapes ───────────────────────────────────
P33, E33, W33 = gen(T33, "3-3 Test")
I33 = byid(P33)
T55 = read("5-5 Ctx.sgf")
P55, E55, W55 = gen(T55, "5-5 Ctx")
I55 = byid(P55)
T66 = read("6-6 Errores.sgf")
P66, E66, W66 = gen(T66, "6-6 Errores")
I66 = byid(P66)
check("3-3: sin errores", E33 == [], E33)
check("3-3: problemas esperados (B no tiene problema normal donde juega mal; W castiga cada error de B)",
      set(I33) == {"3-3 Test/B-pdqcqdpcodqfqg", "3-3 Test/W-pdqcqdpcodqfqg", "3-3 Test/W-pdqcpcqdrd",
                   "3-3 Test/W-pdqcqdpcoc", "3-3 Test/W-pdqcqdpcob",
                   "3-3 Test/B-pdqcqdpcodqfttrgrh", "3-3 Test/W-pdqcqdpcodqfttrgrh",
                   "3-3 Test/B-pdqcpcqd"}, sorted(I33))   # JP.6 (C): tu tramo bueno antes de tu error en S16
c = I33["3-3 Test/B-pdqcqdpcodqfttrgrh"]["sgf"]
check("pase implícito a mitad de línea: no se genera el tramo previo (acabaría en RIGHT donde aún te toca jugar)",
      "3-3 Test/B-pdqcqdpcodqf" not in I33 and "PL[B]" in c and "CR[rg]" in c and "(Tras tu tenuki)" in c and "Extra hane" in c, c)
c = I33["3-3 Test/W-pdqcqdpcodqfttrgrh"]["sgf"]
check("…y en W tu jugada ¿y si? tras el pase implícito del rival lleva su instrucción",
      ";B[]C[Tenuki.\n→ ¿Y si…? Extra hane];W[rg]" in c, c)
b33 = I33["3-3 Test/B-pdqcqdpcodqfqg"]["sgf"]
check("tus jugadas malas del maestro → rama WRONG con su comentario", "(;B[oc]BM[1]C[WRONG Too tight])" in b33, b33)
check("tus jugadas dudosas → rama WRONG 'Dudosa.' con su comentario", "(;B[ob]DO[1]C[WRONG Dudosa. Strange])" in b33, b33)
check("comentario intermedio que empieza por RIGHT se neutraliza", "C[· RIGHT is not what we say]" in b33, b33)
check("']' escapado en el comentario", "C[Live \\] with bracket]" in b33, b33)
check("final sin comentario → RIGHT a secas", ";B[qg]C[RIGHT])" in b33, b33)
check("las ramas WRONG cuelgan del nodo del rival anterior", ";W[pc](;B[od]" in b33, b33)
check("3-3: capítulo con el nombre de la 2.ª jugada", {p["chapter"] for p in P33} == {"3-3 Invasion · B", "3-3 Invasion · W"})

# ── validación con sgf_lib (lo que hará import_my_collections) ───────────────
allp = P44 + P33 + P55 + P66
ok = True
for p in allp:
    r = validate_problem(parse_sgf(p["sgf"]))
    if r["issues"] or r["color_to_play"] != p["color"]:
        ok = False
        print("   ", p["problem_id"], r)
check("todos los SGF generados validan con sgf_lib sin ninguna incidencia y con su color", ok)
try:
    G.self_validate(allp)
    sv = True
except G.GeneratorError:
    sv = False
check("self_validate acepta los generados", sv)
bad = dict(P33[0], sgf=P33[0]["sgf"].replace("C[RIGHT])", ")"))
try:
    G.self_validate([bad]); sv = False
except G.GeneratorError:
    sv = True
check("self_validate rechaza un SGF roto (hoja del jugador sin RIGHT)", sv)

# ── errores de nombres ───────────────────────────────────────────────────────
_, e, _ = gen(T33.replace("C[Block right]", ""), "3-3 Test")
check("error si tu bifurcación no tiene nombre: dice la jugada, las buenas y qué arreglar",
      any(x["sev"] == "fix" and x["where"] == ["pd", "qc", "qd"] and "varias jugadas buenas (R16, Q17)" in x["problem"]
          and "negro R16" in x["fix"] for x in e), e)
_, e, _ = gen(T33.replace("C[3-3 Invasion]", ""), "3-3 Test")
check("error si la 2.ª jugada (familia) no tiene nombre", any(x["where"] == ["pd", "qc"] and "familia" in x["problem"] for x in e), e)
_, e, _ = gen(T44.replace("C[Corner Hane]", ""), "4-4 Joseki")
check("error si tu jugada ¿y si? no tiene nombre (caso real de tu 4-4)",
      any(x["where"][-1] == "qb" and "¿y si?" in x["problem"] and "blanco R18" in x["fix"] for x in e), e)
check("anti-vacío: con nombre no hay ese error", E44 == [])

# ── informe legible (lo que ve Victor en la consola) ─────────────────────────
def report_of(text, name="X.sgf"):
    tmp = tempfile.mkdtemp()
    try:
        os.makedirs(os.path.join(tmp, "j"))
        with open(os.path.join(tmp, "j", name), "w", encoding="utf-8") as fh:
            fh.write(text)
        return quiet_run(os.path.join(tmp, "j"), os.path.join(tmp, "o"), dry_run=True)
    finally:
        shutil.rmtree(tmp)

DRAGO = read(os.path.join("report", "3-4 Joseki (Drago).sgf"))
rc, log = report_of(DRAGO, "3-4 Joseki.sgf")
check("informe: tu 3-4 de Drago → la piedra inicial colocada (AB) con su coordenada y cómo arreglarlo",
      rc == 1 and "HAY QUE ARREGLAR (1)" in log and "Inicio del fichero" in log and "La piedra inicial (R16) está COLOCADA" in log
      and "AB[qd] → ;B[qd]" in log, log)
step1 = DRAGO.replace("CA[UTF-8]AB[qd]\n(", "CA[UTF-8]\n;B[qd]\n(")
assert step1 != DRAGO
rc, log = report_of(step1, "3-4 Joseki.sgf")
check("informe: tras el paso 1 salen los TRES errores de una vez (familia sin nombre + tus dos buenas sin nombre)",
      rc == 1 and "HAY QUE ARREGLAR (3)" in log and " 1. Jugada: 1.B R16  2.W R17\n" in log
      and "Jugada: 1.B R16  2.W R17  3.B Q17  4.W S17  5.B Q16" in log and "varias jugadas buenas (Q16, R18) y R18 no tiene nombre" in log, log)
check("informe: un mensaje por jugada (la familia afecta a 3 líneas y sale una vez)", log.count("empieza una familia") == 1, log)
check("informe: los avisos de 'sin nombre' de jugadas que ya están en HAY QUE ARREGLAR no se repiten",
      "5.B Q16\n   Hay varias" not in log and "AVISOS, no bloquean (3)" in log, log)   # JP.6: la línea W Q17✕ B O17✕ ya genera problema
check("informe: el aviso del nombre repetido dice la secuencia con colores y el nombre",
      "8.W K17\n   Dos variantes de este mismo punto empiezan con la misma primera línea «From 2 extend 3»" in log, log)
rc, log = report_of(T44.replace(";W[pb]C[Slide]", ";W[pb]C[Slide];C[comentario suelto]"), "4-4 Joseki.sgf")
check("informe: nodo vacío → 'Justo después de' la jugada anterior, con colores, y cómo borrarlo",
      rc == 1 and "Justo después de: 1.B Q16  2.W O17  3.B R14  4.W Q18" in log and "NODO VACÍO" in log and "borra el nodo vacío" in log, log)
rc, log = report_of(T44.replace("(;W[qb]IT[]C[Corner Hane]", "(;W[qb]IT[]"), "4-4 Joseki.sgf")
check("informe: el tenuki implícito sale como tal en la secuencia",
      "6.W L17  7.B tenuki (implícito)  8.W R18" in log and "abre una rama ¿y si? (IT)" in log, log)
rc, log = report_of(T44, "4-4 Joseki.sgf")
check("informe: fichero correcto → sin HAY QUE ARREGLAR, con sus avisos y el resumen", rc == 0 and "HAY QUE ARREGLAR" not in log
      and "AVISOS, no bloquean (3)" in log and "15 problemas en 2 capítulos" in log, log)

# ── JP.2: tu tenuki marcado IT no es «→ Ahora tenuki» ─────────────────────────
fixed34 = step1
for a, b in [("(;W[qc]BM[1];B[pc]", "(;W[qc]BM[1]C[3-3 Invasion];B[pc]"), ("(;B[pd];W[pb];B[ob]", "(;B[pd]C[Hane A];W[pb];B[ob]"),
             ("(;B[qb];W[rd]", "(;B[qb]C[Hane B];W[rd]"), ("C[From 2 extend 3\nInfluence", "C[Extend 3 (influence)\nInfluence")]:
    assert fixed34.count(a) == 1, a
    fixed34 = fixed34.replace(a, b)
P, e, _ = gen(fixed34, "3-4 Joseki")
I = byid(P)
check("JP.2 anti-vacío: el 3-4 arreglado genera sin errores y la rama del tenuki IT de negro está", e == [] and "B[tt]IT[]C[If Black Tenuki" in fixed34, e)
check("JP.2: tu tenuki marcado IT no genera el tramo previo (ningún problema acaba en «→ Ahora tenuki» por él)",
      "3-4 Joseki/B-qdocpcod" not in I and not any("→ Ahora tenuki. If Black Tenuki" in p["sgf"] for p in P), sorted(I))
c = I.get("3-4 Joseki/B-qdocpcodttpdqcqfqepfrfrgreqh", {}).get("sgf", "")
check("JP.2: la continuación existe y lo presenta como «¿Y si haces tenuki? <nombre>»",
      "PL[B]" in c and "¿Y si haces tenuki? If Black Tenuki" in c and "(Tras tu tenuki)" not in c, c)
c = I44["4-4 Joseki/W-pdncqfpbqckcqbttobocpcnbpa"]["sgf"]
check("JP.2: un tenuki tuyo SIN IT sigue igual (corte con «→ Ahora tenuki» y continuación «(Tras tu tenuki)»)",
      "4-4 Joseki/W-pdncqfpbqckcqb" in I44 and "(Tras tu tenuki)" in c, c)

# ── JP.4 / JP.5: contexto y letras ───────────────────────────────────────────
check("JP.4: 5-5 sin errores ni avisos, 8 problemas (4 líneas × 2 colores), capítulos por familia",
      E55 == [] and W55 == [] and len(P55) == 8 and {p["chapter"] for p in P55} == {"3-3 Invasion · B", "3-3 Invasion · W"}, (E55, W55, sorted(I55)))
c = I55["5-5 Ctx/B-pdqcctx-Bjcpcqdqe"]["sgf"]
check("JP.4: contexto tras la familia: piedra de contexto puesta con cuadrado, «Contexto: nombre» + resto del comentario, primero el escenario",
      "PL[B]AB[jc][pd]AW[qc]CR[qc]SQ[jc]C[5-5 Ctx · Juegas B\nContexto: Ladder breaker\nBlack has a stone at K17\n3-3 Invasion];B[pc]" in c, c)
check("JP.5: letra de una jugada (L[jc] → A) escrita como LB en esa jugada", ";W[qd]LB[jc:A];B[qe]" in c, c)
c = I55["5-5 Ctx/B-pdqcqdpcctx-Wncobnb"]["sgf"]
check("JP.4: contexto a mitad de línea → el problema empieza DESPUÉS (Q17 y P17 puestas, tú juegas O18)",
      "PL[B]AB[pd][qd]AW[nc][pc][qc]CR[pc]SQ[nc]" in c and c.count(";B[") == 1 and ";B[ob]" in c, c)
check("JP.4: no hay problema que meta el contexto a mitad de la partida (ningún SGF lleva AB/AW fuera de la raíz)",
      all(";AB" not in p["sgf"] and ";AW" not in p["sgf"] for p in P55))
c = I55["5-5 Ctx/W-pdqcctx-Wcccdqdpcod"]["sgf"]
check("JP.4: contexto de varias piedras del otro color, con PL correcto, y LB[od:X] tal cual",
      "AW[cc][cd][qc]" in c and "SQ[cc][cd]" in c and "Contexto: Far white stones" in c and ";B[od]LB[od:X]C[RIGHT]" in c, c)
check("JP.4: el id lleva el contexto (estable mientras no lo cambies)", "5-5 Ctx/B-pdqcctx-Wcccdqdpcod" in I55)
P, _, _ = gen(T55.replace("C[Far white stones]", "C[Far white stones\notro comentario]"), "5-5 Ctx")
check("JP.4: cambiar el comentario del contexto conserva los ids", set(byid(P)) == set(I55))
P, _, _ = gen(T55.replace("AW[cc][cd]", "AW[cc][ce]"), "5-5 Ctx")
check("JP.4: cambiar las piedras del contexto cambia el id (es otra situación)",
      "5-5 Ctx/B-pdqcctx-Wcccdqdpcod" not in byid(P) and "5-5 Ctx/B-pdqcctx-Wccceqdpcod" in byid(P))
rc, log = report_of(T55.replace(";AB[jc]C[Ladder breaker\nBlack has a stone at K17]", ";AB[jc]"), "5-5 Ctx.sgf")
check("JP.4 informe: contexto sin nombre, con la secuencia y el arreglo",
      rc == 1 and "Jugada: 1.B Q16  2.W R17  3.[contexto K17]" in log and "no tiene nombre" in log and "nombre del contexto" in log, log)
rc, log = report_of(T55.replace(";AB[jc]", ";AB[pd]"), "5-5 Ctx.sgf")
check("JP.4 informe: piedra de contexto en punto ocupado", rc == 1 and "Una piedra de contexto está en Q16, que ya está ocupado" in log, log)

GG = read(os.path.join("report", "4-4 Joseki (GoGrinari).sgf"))
PG, EG, WG = gen(GG, "4-4 Joseki")
IG = byid(PG)
cg = [p for p in PG if "ctx-Bmc" in p["problem_id"]]
check("JP.4: tu 4-4 real (GoGrinari): 68 problemas (62 + 5 de JP.6 + 1 de JP.7), 18 con el contexto N17, capítulos «3-3 Invasion · B/W»",
      len(PG) == 68 and len(cg) == 18 and {p["chapter"] for p in cg} == {"3-3 Invasion · B", "3-3 Invasion · W"}, (len(PG), len(cg)))
c = IG["4-4 Joseki/B-pdqcctx-Bmcqdpcocobnbodncrdreqepeqfrc"]["sgf"]
check("JP.4/JP.5 real: N17 puesta con su letra A (sin cuadrado), «Contexto: SAN-SAN…» y la instrucción",
      "AB[mc][pd]AW[qc]CR[qc]LB[mc:A]C[4-4 Joseki · Juegas B\nContexto: SAN-SAN with O-Keima Extension\n3-3 Invasion" in c
      and "SQ[" not in c and "→ Ahora: Block on the bigger side" in c, c)
check("JP.4 real: los 68 validan con sgf_lib", all(not G.validate_problem(G.parse_sgf(p["sgf"]))["issues"] for p in PG))
rc, log = report_of(GG, "4-4 Joseki.sgf")
check("JP.4 informe real: ya no hay nodo vacío; la secuencia muestra el contexto",
      "NODO VACÍO" not in log and "3.[contexto N17]" in log and "HAY QUE ARREGLAR (11)" in log, log[:400])

# ── JP.6: líneas con errores de los dos colores ──────────────────────────────
check("JP.6: sin errores; problemas esperados (normales + A + C, y nada de «limitar daños»)",
      E66 == [] and set(I66) == {"6-6 Errores/B-pdqcqdpcocob", "6-6 Errores/W-pdqcqdpcocob",      # normales
                                 "6-6 Errores/W-pdqcodqdpe",                                       # W castiga B Q15 (normal)
                                 "6-6 Errores/W-pdqcqererfqf",                                     # W castiga B S14 (normal)
                                 "6-6 Errores/B-pdqcpcqdqererf",                                   # A: B castiga el error de W
                                 "6-6 Errores/B-pdqcqere"},                                        # C: B bien hasta su error
      sorted(I66))
a = I66["6-6 Errores/B-pdqcpcqdqererf"]["sgf"]
check("JP.6 A: empieza tras el error del rival, con tu error marcado (TR) y la nota",
      "PL[B]AB[pc][pd]AW[qc][qd]CR[qd]TR[pc]C[6-6 Errores · Juegas B\nTu Q17 fue un error y blanco también ha fallado con R16: castiga.\nWrong answer];B[qe]C[Punish]" in a, a)
check("JP.6 A: el id y la ruta siguen el esquema de siempre (secuencia completa)", I66["6-6 Errores/B-pdqcpcqdqererf"]["rel_path"] == "6-6 Errores/B-pdqcpcqdqererf.sgf")
check("JP.6: tras tu error, si el rival responde bien (Q14 → R16 bueno), NO hay problema de «limitar daños»",
      not any(k.startswith("6-6 Errores/B-pdqcodqd") for k in I66))
c = I66["6-6 Errores/B-pdqcqere"]["sgf"]
check("JP.6 C: tu tramo bueno hasta justo antes de tu error (acaba en el corte de blanco, RIGHT)",
      "→ Ahora: Hane](;B[qe]C[Hane];W[re]C[RIGHT\nCut])" in c and "[rf]" not in c
      and "(;B[pc]BM[1]C[WRONG Wrong side])" in c, c)
P, _, _ = gen(T66.replace("(;B[qe]C[Hane];W[re]C[Cut];B[rf]BM[1]C[Too slow];W[qf])",
                          "(;B[qe]C[Hane];W[re]C[Cut](;B[rf]BM[1]C[Too slow];W[qf])(;B[rd]C[Extend];W[pc])))"[:-1]), "6-6 Errores")
check("JP.6 C: si otra línea ya practica tus mismas jugadas (Hane → Extend), el tramo no se repite",
      "6-6 Errores/B-pdqcqere" not in byid(P) and "6-6 Errores/B-pdqcqererdpc" in byid(P), sorted(byid(P)))
T66b = T66.replace("(;B[qe]C[Hane];W[re]C[Cut];B[rf]BM[1]C[Too slow];W[qf])",
                   "(;B[qe]C[Hane](;W[re]C[Cut];B[rf]BM[1]C[Too slow];W[qf])(;W[rd]C[Other];B[rc])))"[:-1])
assert T66b != T66
P, _, _ = gen(T66b, "6-6 Errores")
check("JP.6 C: cubierto aunque el rival responda distinto al final (tus jugadas son las mismas que en otra línea)",
      "6-6 Errores/B-pdqcqere" not in byid(P) and "6-6 Errores/B-pdqcqerdrc" in byid(P), sorted(byid(P)))
check("JP.6: los problemas de siempre no cambian (4-4 de pruebas: mismos 15 ids)", set(I44) == EXPECTED_IDS)
rc, log = report_of(GG, "4-4 Joseki.sgf")
check("JP.6/JP.7 informe: de las 6 líneas sin problema solo queda 1 (la que acaba en el error Q18), con su motivo concreto",
      log.count("Esta línea no genera ningún problema") == 0 and log.count("no añade ningún problema nuevo") == 1
      and "acaba en el error de negro (Q18) sin la respuesta que lo castiga" in log and "«#ok» en el comentario de Q18" in log, log[-1500:])
rc, log = report_of(T44, "4-4 Joseki.sgf")
check("JP.6 informe: con dos ramas en la misma coordenada (R18 blanca IT y R18 negra) sale la del color que toca",
      "6.W L17  7.B R18  8.W P17" in log, log)

# ── JP.7: castigo diferido y «#ok» ─────────────────────────────────────────────
c = IG.get("4-4 Joseki/W-pdqcctx-Bmcqdpcocrdrercobqeqfpeodrf", {}).get("sgf", "")
check("JP.7 A ampliado: tu error S16, negro responde bien y falla más tarde (R14) → castigas desde Q15",
      "Tu S16 fue un error y negro también ha fallado con R14: castiga." in c and "TR[rd]" in c and c.count(";W[") >= 1
      and c.split(";")[2].startswith("W[pe]"), c[:600])
T44ok = T44.replace("C[Very Bad move, saving that one stone is supersmall]", "C[Very Bad move, saving that one stone is supersmall\n#ok]")
assert T44ok != T44
rc, log = report_of(T44ok, "4-4 Joseki.sgf")
check("JP.7 #ok: oculta el aviso de castigo sin castigo de P17 y lo cuenta", "error del rival (P17)" not in log and "(1 aviso aceptado con #ok)" in log
      and "error del rival (R14)" in log, log)
P, _, _ = gen(T44ok, "4-4 Joseki")
check("JP.7 #ok: no aparece en ningún SGF generado y el comentario queda limpio",
      all("#ok" not in p["sgf"] for p in P) and "C[RIGHT\nVery Bad move, saving that one stone is supersmall]" in byid(P)["4-4 Joseki/B-pdncqfpbqckcqboc"]["sgf"])
check("JP.7 #ok: los ids y el contenido no cambian por añadirlo", {k: v["sgf"] for k, v in byid(P).items()} == {k: v["sgf"] for k, v in I44.items()})
rc, log = report_of(T44.replace("(;GM[1]FF[4]SZ[19]", "(;GM[1]FF[4]SZ[19]C[#ok]", 1) if "(;GM[1]FF[4]SZ[19]" in T44 else T44 + "XX", "4-4 Joseki.sgf")
check("JP.7 #ok en la raíz: oculta los avisos del inicio del fichero (falta CA[UTF-8])", "Falta CA[UTF-8]" not in log and "aceptado" in log, log[:500])
rc, log = report_of(T33.replace("C[3-3 Invasion]", "C[#ok]"), "3-3 Test.sgf")
check("JP.7 #ok: NUNCA oculta un HAY QUE ARREGLAR (familia sin nombre con #ok)", rc == 1 and "empieza una familia" in log and "HAY QUE ARREGLAR" in log, log[:600])
rc, log = report_of(T44.replace("C[Slide]", "C[Slide\n#ok]"), "4-4 Joseki.sgf")
check("JP.7 #ok que no tapa nada: lo dice, con su jugada", "#ok sin aviso que tapar (puedes quitarlo): 1.B Q16  2.W O17  3.B R14  4.W Q18" in log, log[-400:])

# ── JP.8: --aceptar-avisos ───────────────────────────────────────────────────
def accept_case(text, name, dry=False, raw=None):
    tmp = tempfile.mkdtemp()
    src = os.path.join(tmp, "j")
    os.makedirs(src)
    path = os.path.join(src, name)
    data = raw if raw is not None else text.encode("utf-8")
    with open(path, "wb") as fh:
        fh.write(data)
    rc, log = quiet_run(src, os.path.join(tmp, "o"), dry_run=dry, accept=True)
    with open(path, "rb") as fh:
        after = fh.read()
    bak = None
    if os.path.exists(path + ".bak"):
        with open(path + ".bak", "rb") as fh:
            bak = fh.read()
    wrote_out = os.path.exists(os.path.join(tmp, "o"))
    shutil.rmtree(tmp)
    return rc, log, data, after, bak, wrote_out

rc, log, before, after, bak, wo = accept_case(T44, "4-4 Joseki.sgf", dry=True)
check("JP.8 --dry-run --aceptar-avisos: enseña dónde (P17 y R14) y no escribe nada",
      rc == 0 and after == before and bak is None and not wo and "Se añade «#ok» en:" in log
      and "8.W P17" in log and "9.B R14" in log and "--dry-run: no se escribe nada." in log, log[-700:])
rc, log, before, after, bak, wo = accept_case(T44, "4-4 Joseki.sgf")
exp = T44.replace("C[Very Bad move, saving that one stone is supersmall]", "C[Very Bad move, saving that one stone is supersmall\n#ok]")
exp = exp.replace("C[Bad shape. \nLet's think", "C[Bad shape. \nLet's think", 1)
i = exp.index("it would make no sense]") + len("it would make no sense")
exp = exp[:i] + "\n#ok" + exp[i:]
check("JP.8 --aceptar-avisos: el fichero solo cambia en las dos líneas «#ok» (byte a byte), con copia .bak del original",
      rc == 0 and after == exp.encode("utf-8") and bak == before and not wo and "Hecho: 2 «#ok» añadidos" in log, log[-500:])
P, _, _ = gen(after.decode("utf-8"), "4-4 Joseki")
check("JP.8: tras aceptar, los problemas son idénticos", {k: v["sgf"] for k, v in byid(P).items()} == {k: v["sgf"] for k, v in I44.items()})
rc2, log2 = report_of(after.decode("utf-8"), "4-4 Joseki.sgf")
check("JP.8: tras aceptar, el informe ya no los muestra (2 aceptados) y el de CA[UTF-8] sigue (no es de ese tipo)",
      "(2 avisos aceptados con #ok)" in log2 and "error del rival" not in log2 and "Falta CA[UTF-8]" in log2, log2[:600])
rc, log, before, after, bak, wo = accept_case(None, "4-4 Joseki.sgf", raw=T44.replace("\n", "\r\n").encode("utf-8"))
check("JP.8: respeta los saltos de línea CRLF de Drago (inserta \\r\\n#ok)",
      rc == 0 and after.count(b"\r\n#ok]") == 2 and b"\n#ok" not in after.replace(b"\r\n#ok", b""), log[-300:])
rc, log, before, after, bak, wo = accept_case(None, "4-4 Joseki.sgf", raw=b"\xef\xbb\xbf" + T44.encode("utf-8"))
check("JP.8: conserva el BOM si el fichero lo tiene", rc == 0 and after.startswith(b"\xef\xbb\xbf") and after.count(b"#ok") == 2)
t = T44.replace("C[Very Bad move, saving that one stone is supersmall]", "C[Very Bad \\] move]")
rc, log, before, after, bak, wo = accept_case(t, "4-4 Joseki.sgf")
check("JP.8: un ']' escapado en el comentario no confunde la inserción", rc == 0 and b"C[Very Bad \\] move\n#ok]" in after, after[:400])
rc, log, before, after, bak, wo = accept_case(T33.replace("C[Slack]", ""), "3-3 Test.sgf")
check("JP.8: jugada sin comentario → se crea C[#ok]", rc == 0 and b";B[rd]BM[1]C[#ok]" in after, after)
rc, log, before, after, bak, wo = accept_case(GG, "4-4 Joseki.sgf")
rc2, log2 = report_of(after.decode("utf-8"), "4-4 Joseki.sgf")
check("JP.8 real (GoGrinari): 3 «#ok» (P17, R14, Q18), sin tocar los avisos de nombres, mismos 68 problemas",
      rc == 0 and after.count(b"#ok") == 3 and "(3 avisos aceptados con #ok)" in log2 and "From 2 extend 3" in log2
      and set(byid(gen(after.decode('utf-8'), '4-4 Joseki')[0])) == set(IG), log[-400:])
real_ins = G.insert_ok
G.insert_ok = lambda text, nodes: real_ins(text, nodes).replace("#ok", "#nope")
try:
    rc, log, before, after, bak, wo = accept_case(T44, "4-4 Joseki.sgf")
finally:
    G.insert_ok = real_ins
check("JP.8: si la comprobación no cuadra, restaura el original y sale con 1", rc == 1 and after == before and bak == before
      and "se ha restaurado el fichero original" in log, log[-400:])
G.insert_ok = lambda text, nodes: real_ins(text, nodes).replace("\n#ok]", "\nX\n#ok]")
try:
    rc, log, before, after, bak, wo = accept_case(T44, "4-4 Joseki.sgf")
finally:
    G.insert_ok = real_ins
check("JP.8: si los avisos desaparecen pero cambiara algún problema (texto alterado), también restaura",
      rc == 1 and after == before and "se ha restaurado" in log, log[-300:])

# ── estabilidad del id ───────────────────────────────────────────────────────
P, _, _ = gen(T44.replace("C[Slide]", "C[Slide: cambia el comentario]").replace("TR[pb]", ""), "4-4 Joseki")
check("cambiar comentarios o marcas conserva los ids", set(byid(P)) == EXPECTED_IDS)
check("…pero cambia el contenido", byid(P)["4-4 Joseki/B-pdncqfpbqckc"]["sgf"] != LOW_B)
i0 = T44.index("(;C[Low Enclosure]")
i1 = T44.index("(;B[pf]")
body = T44.rstrip()
assert body.endswith(")")
swapped = body[:i0] + body[i1:-1] + body[i0:i1] + ")"
P, e, _ = gen(swapped, "4-4 Joseki")
check("anti-vacío: el maestro reordenado tiene de verdad High 1 point antes que Low Enclosure",
      [k["m"] for k in compile_joseki(swapped.encode("utf-8"), "x")["data"]["root"]["ch"][0]["ch"][0]["ch"]] == ["pf", "qf"])
check("reordenar las ramas del maestro conserva los ids", e == [] and set(byid(P)) == EXPECTED_IDS,
      sorted(set(byid(P)) ^ EXPECTED_IDS))
P, _, _ = gen(T44.replace("C[Protect the side that's open, more territory but Gote])",
                          "C[Protect the side that's open, more territory but Gote];W[cc])"), "4-4 Joseki")
ids = set(byid(P))
check("alargar una línea cambia su id (la vieja desaparece, la nueva aparece)",
      "4-4 Joseki/B-pdncpfpbqckcqj" not in ids and "4-4 Joseki/B-pdncpfpbqckcqjcc" in ids
      and len(ids ^ EXPECTED_IDS) == 4, sorted(ids ^ EXPECTED_IDS))

# ── payload ──────────────────────────────────────────────────────────────────
pl = G.payload_for("4-4 Joseki", P44)
check("payload: colección = fichero, retire_missing=true",
      pl["folder"] == "4-4 Joseki" and pl["retire_missing"] is True)
check("payload: dificultad 10k (1100) en cada capítulo",
      all(c["difficulty_raw"] == "10k" and c["difficulty_num"] == 1100 for c in pl["chapters"]))
check("payload: todos los problemas, con sgf_path bajo joseki_problems/ y su color",
      sorted(p["problem_id"] for c in pl["chapters"] for p in c["problems"]) == sorted(EXPECTED_IDS)
      and all(p["sgf_path"] == "joseki_problems/" + p["problem_id"] + ".sgf" and p["color_to_play"] == p["problem_id"].split("/")[1][0]
              for c in pl["chapters"] for p in c["problems"]))

# ── run(): disco, dry-run, errores, publicación ──────────────────────────────
tmp = tempfile.mkdtemp()
try:
    src, dst = os.path.join(tmp, "joseki"), os.path.join(tmp, "joseki_problems")
    os.makedirs(src)
    for f in ("4-4 Joseki.sgf", "3-3 Test.sgf"):
        shutil.copy(os.path.join(FIX, f), src)
    posted = []

    def poster(server, source, collections, token):
        posted.append((server, source, collections, token))
        return 200, {"problems_upserted": 18}

    rc, log = quiet_run(src, dst, dry_run=True, poster=poster)
    check("--dry-run: no escribe ni publica", rc == 0 and not os.path.exists(dst) and posted == [], log)
    rc, log = quiet_run(src, dst, publish=False, poster=poster)
    files = sorted(os.listdir(os.path.join(dst, "4-4 Joseki")))
    check("--no-publish: escribe los 15 + 8 ficheros y no publica",
          rc == 0 and len(files) == 15 and len(os.listdir(os.path.join(dst, "3-3 Test"))) == 8 and posted == [], log)
    with io.open(os.path.join(dst, "4-4 Joseki", "B-pdncqfpbqckc.sgf"), encoding="utf-8", newline="") as fh:
        check("fichero en disco = SGF generado (UTF-8, LF)", fh.read() == LOW_B)
    rc, log = quiet_run(src, dst, server="http://x:1", token="tk", poster=poster)
    check("publica una sola vez, con source joseki, server y token",
          rc == 0 and len(posted) == 1 and posted[0][0] == "http://x:1" and posted[0][1] == "joseki" and posted[0][3] == "tk", log)
    check("publica las dos colecciones con retire_missing",
          sorted(c["folder"] for c in posted[0][2]) == ["3-3 Test", "4-4 Joseki"]
          and all(c["retire_missing"] for c in posted[0][2]))
    check("re-ejecutar sin cambios: todo 'iguales'", "15 iguales" in log and "0 a borrar" in log, log)
    # quitar una línea del maestro → su fichero se borra y deja de ir en el payload
    with open(os.path.join(src, "4-4 Joseki.sgf"), "w", encoding="utf-8") as fh:
        fh.write(T44.replace("\n(;B[qj]C[Protect the side that's open, more territory but Gote])", ""))
    rc, log = quiet_run(src, dst, poster=poster)
    files = set(os.listdir(os.path.join(dst, "4-4 Joseki")))
    sent = {p["problem_id"] for c in posted[-1][2] for ch in c["chapters"] for p in ch["problems"]}
    check("línea borrada: sus ficheros se borran del disco y no van en el payload",
          rc == 0 and "B-pdncpfpbqckcqj.sgf" not in files and "W-pdncpfpbqckcqj.sgf" not in files
          and "4-4 Joseki/B-pdncpfpbqckcqj" not in sent and "2 a borrar" in log, log)
    # carpeta huérfana: se avisa y no se toca
    os.makedirs(os.path.join(dst, "Viejo"))
    open(os.path.join(dst, "Viejo", "x.sgf"), "w").close()
    rc, log = quiet_run(src, dst, poster=poster)
    check("carpeta sin maestro: aviso y no se toca", "Viejo sin fichero maestro" in log and os.path.exists(os.path.join(dst, "Viejo", "x.sgf")))
    # un error en cualquier fichero → nada se escribe ni publica
    n_posted = len(posted)
    with open(os.path.join(src, "3-3 Test.sgf"), "w", encoding="utf-8") as fh:
        fh.write(T33.replace("C[3-3 Invasion]", ""))
    before = sorted(os.listdir(os.path.join(dst, "4-4 Joseki")))
    with open(os.path.join(src, "4-4 Joseki.sgf"), "w", encoding="utf-8") as fh:
        fh.write(T44)
    rc, log = quiet_run(src, dst, poster=poster)
    check("con un error: código 1, no escribe (ni la línea restaurada del otro fichero) ni publica",
          rc == 1 and len(posted) == n_posted and sorted(os.listdir(os.path.join(dst, "4-4 Joseki"))) == before, log)
    with open(os.path.join(src, "3-3 Test.sgf"), "w", encoding="utf-8") as fh:
        fh.write(T33)
    rc, log = quiet_run(src, dst, poster=lambda *a: (500, {"error": "x"}))
    check("si el servidor rechaza: código 1", rc == 1)
    real_build, n_posted = G.build_sgf, len(posted)
    G.build_sgf = lambda *a, **k: real_build(*a, **k).replace("C[RIGHT", "C[OK")   # SGF roto a propósito
    before = {f: open(os.path.join(dst, "4-4 Joseki", f), "rb").read() for f in os.listdir(os.path.join(dst, "4-4 Joseki"))}
    try:
        rc, log = quiet_run(src, dst, poster=poster)
    finally:
        G.build_sgf = real_build
    after = {f: open(os.path.join(dst, "4-4 Joseki", f), "rb").read() for f in os.listdir(os.path.join(dst, "4-4 Joseki"))}
    check("autovalidación: un SGF generado roto → código 1, nada escrito ni publicado",
          rc == 1 and "fallo interno del generador" in log and before == after and len(posted) == n_posted, log[-300:])
    rc, log = quiet_run(os.path.join(tmp, "no-existe"), dst, poster=poster)
    check("carpeta de maestros inexistente: código 2", rc == 2)
finally:
    shutil.rmtree(tmp)

# ── JL: qué línea × color da problema normal (antes, las «tarjetas» de J1) ──
def plines(body):
    res = compile_joseki(("(;GM[1]FF[4]CA[UTF-8]SZ[19]" + body + ")").encode("utf-8"), "t")
    assert res["ok"], res["issues"]
    return res, [(c, ".".join(n["m"] for n in nodes)) for c, nodes in G.practice_lines(res["data"]["root"])]

_, pl = plines(";B[pd];W[nc](;B[qf]C[a])(;B[pf]C[b])")
check("practice_lines: una por línea y color, B antes que W, en el orden del fichero",
      pl == [("B", "pd.nc.qf"), ("W", "pd.nc.qf"), ("B", "pd.nc.pf"), ("W", "pd.nc.pf")], pl)
_, pl = plines(";B[pd];W[nc]BM[1];B[qc]")
check("practice_lines: la mala del rival no quita la tuya (castigo)", pl == [("B", "pd.nc.qc")], pl)
_, pl = plines(";B[pd];W[nc]DO[1];B[qc]")
check("practice_lines: dudosa propia excluida, dudosa del rival no", pl == [("B", "pd.nc.qc")], pl)
_, pl = plines(";B[pd];W[nc];B[qc];W[qd]IT[]C[Si corta]")
check("practice_lines: la rama ¿y si? da sus dos colores y no altera la principal",
      pl == [("B", "pd.nc.qc"), ("W", "pd.nc.qc"), ("B", "pd.nc.qc.qd"), ("W", "pd.nc.qc.qd")], pl)
_, pl = plines(";B[pd];W[nc];W[qf]IT[]C[a];B[qh]")
check("practice_lines: tu pase implícito no cuenta como jugada tuya (la ¿y si? da B y W)",
      [c for c, t in pl if "qf" in t] == ["B", "W"], pl)
_, pl = plines(";B[pd];W[qc]C[Inv](;B[qd]C[Normal];W[pc])(;AB[jc]C[Breaker];B[pc];W[qd]))"[:-1])
check("practice_lines: la ruta atraviesa el contexto", ("B", "pd.qc.ctx-Bjc.pc.qd") in pl and ("W", "pd.qc.qd.pc") in pl, pl)
ok_44 = G.practice_lines(compile_joseki(T44.encode("utf-8"), "4-4 Joseki")["data"]["root"])
check("practice_lines: 14 en el 4-4 de pruebas (las 14 «tarjetas» de J1)", len(ok_44) == 14, len(ok_44))

res, pl = plines(";B[pd];W[qc]C[F](;B[qd]C[x];W[pc])(;B[pc]BM[1];W[qd]BM[1]))"[:-1])
both_bad = G.all_lines(res["data"]["root"])[1]
check("anti-vacío: la línea con errores de los dos no da problema normal a nadie",
      G.practice_colors(both_bad) == [] and [n["m"] for n in both_bad] == ["pd", "qc", "pc", "qd"])
_, _, w = G.generate_file(res["data"], "t")
np = [x for x in w if "no añade ningún problema nuevo" in x["problem"]]
check("línea sin ningún problema: aviso propio del generador, con su jugada, el motivo y #ok",
      len(np) == 1 and np[0]["sev"] == "warn" and np[0]["where"] == ["pd", "qc", "pc", "qd"] and np[0].get("okable")
      and "acaba en el error de blanco (R16)" in np[0]["problem"] and w.index(np[0]) == 0, w)
check("…y no sale si la línea ya da problemas A/C (6-6 Errores)",
      any(not G.practice_colors(l) for l in G.all_lines(compile_joseki(T66.encode("utf-8"), "6-6 Errores")["data"]["root"]))
      and not any("no añade ningún problema nuevo" in x["problem"] for x in W66), W66)
check("el compilador ya no da el aviso de J1 «línea sin tarjetas»",
      not any("tarjetas" in m for _, _, m in res["issues"]))

# ── salida para la prueba de humo del cliente ────────────────────────────────
out = os.path.join(HERE, "jp_test_out")
shutil.rmtree(out, ignore_errors=True)
for p in allp:
    path = os.path.join(out, *p["rel_path"].split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(p["sgf"].encode("utf-8"))

print()
print("RESULTADO GENERADOR:", "TODO OK (%d checks)" % N[0] if not FAILS else "%d FALLOS: %s" % (len(FAILS), FAILS))
sys.exit(1 if FAILS else 0)
