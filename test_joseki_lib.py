#!/usr/bin/env python3
"""
test_joseki_lib.py — Tests del compilador de ficheros maestros de josekis
(joseki_lib.py) y del importador de la pestaña Joseki (import_joseki.py).
Lo que decide qué línea da problema se prueba en test_generate_joseki.py.

    python test_joseki_lib.py

Cada caso que comprueba un ERROR o un AVISO lleva su contrapartida válida
(anti-vacío): así se demuestra que el fallo lo provoca exactamente la
condición probada y no otra cosa del SGF de prueba.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from joseki_lib import compile_joseki, is_endpoint, serialize  # noqa: E402

HEAD = "(;GM[1]FF[4]CA[UTF-8]SZ[19]"

# Copia de 4-4 Joseki.sgf (versión del 14-oct, sin las dos correcciones).
SAMPLE = """(;GM[1]FF[4]SZ[19]AP[SmartGo:3.1.8]RU[Simple];B[pd]
;W[nc]C[Keima Approach]
(;C[Low Enclosure]B[qf];W[pb]C[Slide];C[Take the corner]B[qc];C[2 spaces extension]W[kc]
(;W[qb]IT[]
(;B[qi]TE[1]C[We are safe and take some points])
(;B[tt]C[If Tenuki];W[qh]C[The 3 stones group is very weak now]TE[1]))
(;W[qh]C[If the approach is from here]IT[];B[qb]C[Now we have the corner and we are safe])
(;B[qb]C[If we play this endgame move]
(;W[oc]BM[1]C[Very Bad move, saving that one stone is supersmall]TR[pb])
(;W[tt]TE[1]C[Tenuki];B[ob];W[oc];B[pc];W[nb];B[pa]
;W[tt]TE[1])))
(;B[pf]C[High 1 point extension];W[pb];B[qc];W[kc]
(;B[qj]C[Protect the side that's open, more territory but Gote])
(;B[tt]BM[1];W[qh]
(;B[qb]BM[1];W[rf])
(;B[qf]BM[1]C[Bad shape.
Let's think this move is from a previous move (like the keima enclosure joseki) and I just put the marked stone, it would make no sense]TR[pf]))))
"""


def run(body, head=HEAD, name="t"):
    return compile_joseki((head + body + ")").encode("utf-8"), name)


def errors(res):
    return [m for s, _, m in res["issues"] if s == "ERROR"]


def warnings(res):
    return [m for s, _, m in res["issues"] if s == "WARNING"]


def has(msgs, fragment):
    return any(fragment in m for m in msgs)


def kids(res):
    return res["data"]["root"]["ch"]


class TestCoordsAndPass(unittest.TestCase):
    def test_pass_tt_and_empty(self):
        for p in ("tt", ""):
            r = run(";B[pd];W[%s];B[dd]" % p)
            self.assertTrue(r["ok"], r["issues"])
            self.assertEqual(kids(r)[0]["ch"][0]["m"], "pass")
            self.assertEqual(kids(r)[0]["ch"][0]["c"], "W")

    def test_invalid_coord(self):
        r = run(";B[pd];W[zz]")
        self.assertTrue(has(errors(r), "coordenada no válida"))
        self.assertTrue(run(";B[pd];W[ss]")["ok"])  # anti-vacío: borde válido

    def test_root_with_move(self):
        r = compile_joseki(b"(;GM[1]CA[UTF-8]SZ[19]B[pd];W[nc])", "t")
        self.assertTrue(r["ok"], r["issues"])
        self.assertEqual((kids(r)[0]["m"], kids(r)[0]["ch"][0]["m"]), ("pd", "nc"))
        self.assertEqual(r["tree"], ["  1.B Q16  2.W O17  => fin"])


class TestGoRules(unittest.TestCase):
    def test_occupied(self):
        r = run(";B[pd];W[pd]")
        self.assertTrue(has(errors(r), "punto ocupado"))
        self.assertTrue(run(";B[pd];W[pc]")["ok"])

    def test_capture_frees_point(self):
        # W aa queda capturada por B ba + B ab; luego B puede jugar en aa.
        ok = run(";B[ba];W[aa];B[ab];W[dd];B[aa]")
        self.assertTrue(ok["ok"], ok["issues"])
        # Anti-vacío: sin la captura (B ab no se juega) aa sigue ocupada.
        bad = run(";B[ba];W[aa];B[cc];W[dd];B[aa]")
        self.assertTrue(has(errors(bad), "punto ocupado"))

    def test_suicide(self):
        r = run(";B[ba];W[pp];B[ab];W[aa]")
        self.assertTrue(has(errors(r), "suicidio"))
        # Anti-vacío: si B no cierra ab, W aa tiene libertad.
        self.assertTrue(run(";B[ba];W[pp];B[cc];W[aa]")["ok"])

    KO = ";B[ba];W[ca];B[ab];W[db];B[bc];W[cc];B[pp];W[bb];B[cb]"

    def test_ko(self):
        r = run(self.KO + ";W[bb]")
        self.assertTrue(has(errors(r), "ko"))
        # Anti-vacío: con un intercambio en medio, retomar es legal.
        r2 = run(self.KO + ";W[qq];B[qp];W[bb]")
        self.assertTrue(r2["ok"], r2["issues"])

    def test_illegal_branch_does_not_hide_other_errors(self):
        r = run(";B[pd](;W[pd])(;W[nc]BM[1]DO[1])")
        self.assertTrue(has(errors(r), "punto ocupado"))
        self.assertTrue(has(errors(r), "BM y DO"))


class TestAlternationAndTenuki(unittest.TestCase):
    def test_same_colour_without_it_is_error(self):
        r = run(";B[pd];B[pp]")
        self.assertTrue(has(errors(r), "alternancia rota"))

    def test_same_colour_with_it_inserts_implicit_pass(self):
        r = run(";B[pd];W[nc];W[qf]IT[]C[Aproximación posterior]")
        self.assertTrue(r["ok"], r["issues"])
        nc = kids(r)[0]["ch"][0]
        self.assertEqual(len(nc["ch"]), 1)
        p = nc["ch"][0]
        self.assertEqual((p["m"], p["c"], p.get("implicit"), p.get("it")), ("pass", "B", True, True))
        self.assertEqual(p["ch"][0]["m"], "qf")
        self.assertEqual(p["ch"][0]["name"], "Aproximación posterior")

    def test_it_siblings_share_one_implicit_pass(self):
        r = run(";B[pd];W[nc](;W[qf]IT[]C[a])(;W[qh]IT[]C[b])")
        nc = kids(r)[0]["ch"][0]
        passes = [k for k in nc["ch"] if k.get("implicit")]
        self.assertEqual(len(passes), 1)
        self.assertEqual([k["m"] for k in passes[0]["ch"]], ["qf", "qh"])

    def test_implicit_pass_is_never_a_line_end(self):
        # Regresión: el pase implícito solo tiene hijos IT y no es un final de
        # línea propio (fallo detectado al probar con 4-4 Joseki.sgf).
        r = run(";B[pd];W[nc](;W[qf]IT[]C[a])(;W[qh]IT[]C[b])")
        nc = kids(r)[0]["ch"][0]
        p = nc["ch"][0]
        self.assertTrue(p.get("implicit"))          # anti-vacío: es el pase implícito
        self.assertFalse(is_endpoint(p))
        self.assertTrue(is_endpoint(nc))            # la línea principal sigue acabando en O17
        self.assertEqual(r["lines"], 3)             # pd.nc, pd.nc.pass.qf, pd.nc.pass.qh
        self.assertEqual(r["tree"], ["  1.B Q16  2.W O17  => fin", "  3.B pase (implícito)",
                                     "  +- 4.W R14 IT [a]  => fin", "  +- 4.W R12 IT [b]  => fin"])

    def test_two_passes(self):
        r = run(";B[pd];W[tt];B[tt]")
        self.assertTrue(has(errors(r), "dos pases seguidos"))

    def test_implicit_after_pass_is_error(self):
        r = run(";B[pd];W[tt];W[qq]IT[]")
        self.assertTrue(has(errors(r), "tenuki implícito tras un pase"))

    def test_pass_as_first_move(self):
        r = run(";B[tt];W[pd]")
        self.assertTrue(has(errors(r), "primera jugada"))

    def test_explicit_and_implicit_pass_conflict(self):
        r = run(";B[pd];W[nc](;B[tt]C[x])(;W[qf]IT[]C[y])")
        self.assertTrue(has(errors(r), "pase explícito y tenuki implícito"))
        # Anti-vacío: la forma correcta es colgar la rama del pase explícito.
        self.assertTrue(run(";B[pd];W[nc];B[tt]C[x];W[qf]IT[]C[y]")["ok"])


class TestStructure(unittest.TestCase):
    def test_bm_and_do(self):
        self.assertTrue(has(errors(run(";B[pd];W[nc]BM[1]DO[1]")), "BM y DO"))
        self.assertTrue(run(";B[pd];W[nc]BM[1]")["ok"])

    def test_bm_and_te_warning(self):
        self.assertTrue(has(warnings(run(";B[pd];W[nc]BM[1]TE[1]")), "BM y TE"))

    def test_setup_stones_root_and_node(self):
        self.assertTrue(has(errors(run(";B[pd]", head=HEAD + "AB[dd]")), "piedras de contexto"))
        self.assertTrue(has(errors(run(";B[pd];W[nc]AW[dd]")), "piedras de setup"))

    def test_node_without_move(self):
        self.assertTrue(has(errors(run(";B[pd];C[solo un comentario]")), "nodo sin jugada"))

    def test_both_colours(self):
        self.assertTrue(has(errors(run(";B[pd];B[nc]W[qc]")), "B y de W a la vez"))

    def test_duplicate_children(self):
        r = run(";B[pd](;W[nc])(;W[nc]C[otra vez])")
        self.assertTrue(has(errors(r), "repetida entre hermanos"))

    def test_board_size(self):
        r = compile_joseki(b"(;GM[1]CA[UTF-8]SZ[13];B[dd])", "t")
        self.assertTrue(has(errors(r), "19x19"))
        r = compile_joseki(b"(;GM[1]CA[UTF-8];B[dd])", "t")
        self.assertTrue(r["ok"])
        self.assertTrue(has(warnings(r), "falta SZ"))

    def test_encoding(self):
        r = compile_joseki("(;GM[1]SZ[19];B[pd]C[Pinza baja])".encode("utf-8"), "t")
        self.assertTrue(has(warnings(r), "CA[UTF-8]"))
        self.assertFalse(has(warnings(run(";B[pd]")), "CA[UTF-8]"))
        r = compile_joseki("(;GM[1]CA[UTF-8]SZ[19];B[pd]C[Pinza ñ])".encode("latin-1"), "t")
        self.assertTrue(has(errors(r), "UTF-8"))

    def test_empty_file(self):
        self.assertTrue(has(errors(compile_joseki(b"(;GM[1]SZ[19])", "t")), "no contiene jugadas"))

    def test_marks_and_comments(self):
        r = run(";B[pd];W[nc]TR[pd][zz]C[Línea 1\r\nLínea 2  ]")
        nc = kids(r)[0]["ch"][0]
        self.assertEqual(nc["marks"], {"TR": ["pd"]})
        self.assertTrue(has(warnings(r), "marca TR"))
        self.assertEqual(nc["comment"], "Línea 1\nLínea 2")


class TestNames(unittest.TestCase):
    def test_bifurcation_names_from_first_line(self):
        r = run(";B[pd];W[nc](;B[qf]C[Low Enclosure\nexplicación])(;B[pf]C[High extension])")
        nc = kids(r)[0]["ch"][0]
        self.assertEqual([k.get("name") for k in nc["ch"]], ["Low Enclosure", "High extension"])
        self.assertEqual(nc["ch"][0]["comment"], "Low Enclosure\nexplicación")

    def test_single_good_child_gets_no_name(self):
        r = run(";B[pd];W[nc](;B[qf]C[Low])(;B[pf]BM[1]C[mala])")
        nc = kids(r)[0]["ch"][0]
        self.assertNotIn("name", nc["ch"][0])
        self.assertNotIn("name", nc["ch"][1])

    def test_missing_long_and_duplicate_names(self):
        r = run(";B[pd];W[nc](;B[qf])(;B[pf]C[x])")
        self.assertTrue(has(warnings(r), "bifurcación sin nombre"))
        r = run(";B[pd];W[nc](;B[qf]C[%s])(;B[pf]C[x])" % ("n" * 41))
        self.assertTrue(has(warnings(r), "41 caracteres"))
        self.assertFalse(has(warnings(run(";B[pd];W[nc](;B[qf]C[%s])(;B[pf]C[x])" % ("n" * 40))),
                         "caracteres"))
        r = run(";B[pd];W[nc](;B[qf]C[Pinza])(;B[pf]C[pinza])")
        self.assertTrue(has(warnings(r), "nombre repetido"))

    def test_it_branch_needs_name(self):
        r = run(";B[pd];W[nc](;B[qf])(;B[pf]IT[])")
        self.assertTrue(has(warnings(r), "¿y si…? (IT) sin nombre"))
        r = run(";B[pd];W[nc](;B[qf])(;B[pf]IT[]C[Si pinza])")
        self.assertFalse(has(warnings(r), "sin nombre"))


class TestLines(unittest.TestCase):
    """Finales de línea: el contador `lines` y la marca «=> fin» del informe."""

    def test_count_and_tree(self):
        r = run(";B[pd];W[nc](;B[qf]C[a])(;B[pf]C[b])")
        self.assertEqual(r["lines"], 2)
        self.assertEqual(r["tree"], ["  1.B Q16  2.W O17", "  +- 3.B R14 [a]  => fin", "  +- 3.B Q14 [b]  => fin"])

    def test_bad_lines_are_lines_too(self):
        # Las líneas de errores de los dos colores también cuentan; ya no hay aviso por ellas.
        r = run(";B[pd]BM[1];W[nc]BM[1]")
        self.assertEqual(r["lines"], 1)
        self.assertEqual(warnings(r), [])
        self.assertEqual(r["tree"], ["  1.B Q16 BM  2.W O17 BM  => fin"])

    def test_whatif_branch_ends_its_own_line(self):
        r = run(";B[pd];W[nc];B[qc];W[qd]IT[]C[Si corta]")
        self.assertEqual(r["lines"], 2)       # la principal (acaba en R17) y la ¿y si?
        self.assertEqual(r["tree"], ["  1.B Q16  2.W O17  3.B R17  => fin", "  4.W R16 IT [Si corta]  => fin"])

    def test_json_without_cards_and_deterministic(self):
        r1 = run(";B[pd];W[nc];B[tt]C[tenuki]", name="4-4 Joseki")
        r2 = run(";B[pd];W[nc];B[tt]C[tenuki]", name="4-4 Joseki")
        self.assertEqual(serialize(r1["data"]), serialize(r2["data"]))
        self.assertEqual(set(r1["data"]), {"format", "file", "sgf_hash", "size", "description", "root", "ack_root"})
        self.assertNotIn(b"cards", serialize(r1["data"]))

    def test_sample_file(self):
        r = compile_joseki(SAMPLE.encode("utf-8"), "4-4 Joseki")
        self.assertTrue(r["ok"], r["issues"])
        self.assertEqual(r["lines"], 8)
        self.assertEqual(sum(l.endswith("=> fin") for l in r["tree"]), 8)
        # Con IT en «B qb» la línea principal de Low Enclosure acaba en L17 y gana su final.
        fixed = SAMPLE.replace("(;B[qb]C[If we play", "(;B[qb]IT[]C[If we play")
        self.assertNotEqual(fixed, SAMPLE)  # anti-vacío: la corrección se aplicó
        r2 = compile_joseki(fixed.encode("utf-8"), "4-4 Joseki")
        self.assertEqual(r2["lines"], 9)
        self.assertIn("  +- 3.B R14 [Low Enclosure]  4.W Q18  5.B R17  6.W L17  => fin", r2["tree"])


class TestImporterCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.folder = os.path.join(self.tmp, "joseki")
        os.makedirs(self.folder)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def cli(self, *extra):
        p = subprocess.run([sys.executable, os.path.join(HERE, "import_joseki.py"), self.folder] + list(extra),
                           capture_output=True, text=True, encoding="utf-8")
        return p.returncode, p.stdout

    def write(self, name, text):
        with open(os.path.join(self.folder, name), "w", encoding="utf-8") as fh:
            fh.write(text)

    def manifest(self):
        with open(os.path.join(self.folder, "manifest.json"), encoding="utf-8") as fh:
            return {e["file"]: e for e in json.load(fh)["files"]}

    def test_full_cycle(self):
        good = HEAD + ";B[pd];W[nc])"
        self.write("a.sgf", good)
        self.write("b.sgf", HEAD + ";B[pd];W[qc])")

        code, _ = self.cli("--validate-only")
        self.assertEqual(code, 0)
        self.assertFalse(os.path.exists(os.path.join(self.folder, "manifest.json")))

        code, out = self.cli()
        self.assertEqual(code, 0)
        m = self.manifest()
        self.assertEqual(set(m), {"a", "b"})
        self.assertEqual(set(m["a"]), {"file", "json", "hash", "lines"})   # sin «cards»
        self.assertEqual(m["a"]["lines"], 1)
        self.assertIn("1 líneas — nuevo", out)
        self.assertTrue(os.path.isfile(os.path.join(self.folder, "a.json")))
        with open(os.path.join(self.folder, "a.json"), encoding="utf-8") as fh:
            self.assertNotIn("cards", json.load(fh))

        code, out = self.cli()
        self.assertIn("sin cambios", out)
        self.assertEqual(self.manifest()["a"]["hash"], m["a"]["hash"])

        # Fichero roto: se conserva el JSON anterior y se sale con 1.
        self.write("a.sgf", HEAD + ";B[pd];B[nc])")
        code, out = self.cli()
        self.assertEqual(code, 1)
        self.assertIn("Se conserva el JSON anterior", out)
        self.assertEqual(self.manifest()["a"]["hash"], m["a"]["hash"])

        # SGF borrado: sale del manifiesto, el JSON no se borra.
        os.remove(os.path.join(self.folder, "b.sgf"))
        self.write("a.sgf", good)
        code, out = self.cli()
        self.assertEqual(code, 0)
        self.assertEqual(set(self.manifest()), {"a"})
        self.assertTrue(os.path.isfile(os.path.join(self.folder, "b.json")))

    def test_missing_folder(self):
        p = subprocess.run([sys.executable, os.path.join(HERE, "import_joseki.py"),
                            os.path.join(self.tmp, "no-existe")], capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)



# ── JP.4 / JP.5: contexto y letras (un solo modo: pestaña Joseki y generador) ──
FIX = os.path.join(HERE, "jp_fixtures")

CTX = ";B[pd];W[qc]C[Inv](;B[qd]C[Normal];W[pc])(;AB[jc]C[Breaker\nmore text];B[pc];W[qd]))"


class TestPestanaConContexto(unittest.TestCase):
    """J3.2: el JSON de la pestaña Joseki (import_joseki) lleva contexto y letras."""

    def test_contexto_en_el_json_sin_aviso(self):
        r = run(CTX[:-1])
        self.assertTrue(r["ok"], r["issues"])
        self.assertEqual(warnings(r), [])
        self.assertEqual([k["m"] for k in kids(r)[0]["ch"][0]["ch"]], ["qd", "ctx-Bjc"])
        self.assertEqual(r["lines"], 2)

    def test_letras_en_el_json(self):
        r = run(";B[pd]L[qq];W[qc]LB[dd:Z]")
        self.assertEqual(kids(r)[0]["marks"], {"LB": [["qq", "A"]]})
        self.assertEqual(kids(r)[0]["ch"][0]["marks"], {"LB": [["dd", "Z"]]})

    def test_gogrinari_real_en_la_pestana(self):
        with open(os.path.join(FIX, "report", "4-4 Joseki (GoGrinari).sgf"), "rb") as fh:
            raw = fh.read()
        r = compile_joseki(raw, "4-4 Joseki")
        self.assertTrue(r["ok"], [i for i in r["issues"] if i[0] == "ERROR"])
        self.assertFalse(has(warnings(r), "contexto"))
        qc = next(k for k in kids(r)[0]["ch"] if k["m"] == "qc")
        ctx = qc["ch"][0]
        self.assertEqual((ctx["m"], ctx["ctx"], ctx["name"]), ("ctx-Bmc", {"B": ["mc"], "W": []}, "SAN-SAN with O-Keima Extension"))
        self.assertEqual(qc["marks"]["LB"], [["mc", "A"]])                 # la letra A del 3-3, en la jugada que la pone


class TestContexto(unittest.TestCase):
    def test_nodo_de_contexto(self):
        r = run(CTX[:-1])
        self.assertTrue(r["ok"], r["issues"])
        qc = kids(r)[0]["ch"][0]
        ctx = qc["ch"][1]
        self.assertEqual(ctx["m"], "ctx-Bjc")
        self.assertEqual(ctx["ctx"], {"B": ["jc"], "W": []})
        self.assertEqual(ctx["name"], "Breaker")
        self.assertEqual(ctx["c"], "")
        self.assertEqual([k["m"] for k in ctx["ch"]], ["pc"])

    def test_no_cambia_el_turno(self):
        r = run(";B[pd];W[qc](;AB[jc]C[X];W[pc]))")
        self.assertTrue(has(errors(r), "alternancia rota"))
        r = run(";B[pd];W[qc](;AB[jc]C[X];B[pc]))")
        self.assertTrue(r["ok"], r["issues"])

    def test_lineas_atraviesan_el_contexto(self):
        r = run(CTX[:-1])
        self.assertEqual(r["lines"], 2)
        self.assertEqual(r["tree"], ["  1.B Q16  2.W R17", "  +- 3.B R16  4.W Q17  => fin",
                                     "  +- 3.[contexto B:K17] [Breaker]  4.B Q17  5.W R16  => fin"])

    def test_contexto_no_es_bifurcacion(self):
        # la rama normal SIN nombre junto a un contexto: no es una bifurcación de jugadas buenas
        r = run(";B[pd];W[qc](;B[qd];W[pc])(;AB[jc]C[Breaker];B[pc];W[qd]))")
        self.assertTrue(r["ok"], r["issues"])
        self.assertFalse(has(warnings(r), "bifurcación sin nombre"), r["issues"])
        # anti-vacío: con dos jugadas buenas de verdad sí avisa
        r = run(";B[pd];W[qc](;B[qd];W[pc])(;B[pc];W[qd]))")
        self.assertTrue(has(warnings(r), "bifurcación sin nombre"))

    def test_sin_nombre(self):
        r = run(";B[pd];W[qc](;AB[jc];B[pc]))")
        self.assertTrue(has(errors(r), "contexto sin nombre"))
        self.assertTrue(run(";B[pd];W[qc](;AB[jc]C[N];B[pc]))")["ok"])

    def test_punto_ocupado(self):
        r = run(";B[pd];W[qc](;AB[pd]C[N];B[pc]))")
        self.assertTrue(has(errors(r), "piedra de contexto en un punto ocupado: Q16"))

    def test_ae_no_admitido(self):
        r = run(";B[pd];W[qc](;AE[pd]C[N];B[pc]))")
        self.assertTrue(has(errors(r), "contexto con AE"))

    def test_raiz_sigue_siendo_error(self):
        r = compile_joseki((HEAD + "AB[pd];W[qc];B[pc])").encode("utf-8"), "t")
        self.assertTrue(has(errors(r), "piedras de contexto (AB) en la raíz"))

    def test_pl_que_no_coincide(self):
        r = run(";B[pd];W[qc](;AB[jc]PL[W]C[N];B[pc]))")
        self.assertTrue(has(warnings(r), "PL[W] en el contexto, pero juega B"))
        r = run(";B[pd];W[qc](;AB[jc]PL[B]C[N];B[pc]))")
        self.assertFalse(has(warnings(r), "PL["))

    def test_varios_contextos_acumulan(self):
        r = run(";B[pd];W[qc];AB[jc]C[A];AW[cc]C[B];B[pc];W[qd])")
        self.assertTrue(r["ok"], r["issues"])
        path, n = [], kids(r)[0]
        while True:
            path.append(n["m"])
            if not n["ch"]:
                break
            n = n["ch"][0]
        self.assertEqual(path, ["pd", "qc", "ctx-Bjc", "ctx-Wcc", "pc", "qd"])
        self.assertEqual(r["lines"], 1)

    def test_gogrinari_real(self):
        with open(os.path.join(FIX, "report", "4-4 Joseki (GoGrinari).sgf"), "rb") as fh:
            raw = fh.read()
        r = compile_joseki(raw, "4-4 Joseki")
        self.assertTrue(r["ok"], [i for i in r["issues"] if i[0] == "ERROR"])
        self.assertTrue(any("[contexto B:N17] [SAN-SAN with O-Keima Extension]" in l for l in r["tree"]))


class TestLetras(unittest.TestCase):
    def test_l_formato_antiguo(self):
        r = run(";B[pd]C[x];W[qc]L[le][ne]")
        self.assertEqual(kids(r)[0]["ch"][0]["marks"]["LB"], [["le", "A"], ["ne", "B"]])

    def test_lb(self):
        r = run(";B[pd]LB[dd:Z][dp:2]")
        self.assertEqual(kids(r)[0]["marks"]["LB"], [["dd", "Z"], ["dp", "2"]])

    def test_letra_no_valida(self):
        r = run(";B[pd]L[zz]LB[dd]")
        self.assertTrue(has(warnings(r), "letra L con coordenada no válida"))
        self.assertTrue(has(warnings(r), "etiqueta LB no válida"))
        self.assertNotIn("marks", kids(r)[0])

    def test_letras_en_contexto(self):
        r = run(";B[pd];W[qc];AB[jc]L[jc]C[N];B[pc])")
        self.assertEqual(kids(r)[0]["ch"][0]["ch"][0]["marks"]["LB"], [["jc", "A"]])



class TestOk(unittest.TestCase):
    """JP.7: línea «#ok» en un comentario = avisos de esa jugada aceptados."""

    def test_se_quita_y_marca(self):
        r = run(";B[pd]C[Hola\n#ok];W[qc]C[#OK])")
        b, w = kids(r)[0], kids(r)[0]["ch"][0]
        self.assertEqual(b["comment"], "Hola")
        self.assertTrue(b["ack"])
        self.assertNotIn("comment", w)          # solo «#ok»: comentario vacío
        self.assertTrue(w["ack"])

    def test_no_es_nombre(self):
        r = run(";B[pd];W[qc](;B[qd]C[#ok\nBlock];W[pc])(;B[pc]C[Top];W[qd]))")
        self.assertEqual(kids(r)[0]["ch"][0]["ch"][0]["name"], "Block")

    def test_raiz(self):
        self.assertTrue(run(";B[pd])", head=HEAD + "C[#ok]")["data"]["ack_root"])
        self.assertFalse(run(";B[pd])")["data"]["ack_root"])
        r = compile_joseki(b"(;GM[1]FF[4]CA[UTF-8]SZ[19]B[pd]C[#ok];W[qc])", "t")
        self.assertTrue(r["data"]["ack_root"])               # 1.ª jugada guardada en la raíz (GoGrinari)

    def test_ok_dentro_de_una_frase_no_cuenta(self):
        r = run(";B[pd]C[esto es #ok no])")
        self.assertNotIn("ack", kids(r)[0])
        self.assertEqual(kids(r)[0]["comment"], "esto es #ok no")


if __name__ == "__main__":
    unittest.main(verbosity=1)
