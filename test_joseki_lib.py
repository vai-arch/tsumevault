#!/usr/bin/env python3
"""
test_joseki_lib.py — Tests de la fase J1 (importador de josekis).

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

from joseki_lib import compile_joseki, serialize  # noqa: E402

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


def cards(res):
    return res["data"]["cards"]


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
        self.assertEqual([c["path"] for c in cards(r)], [["pd", "nc"], ["pd", "nc"]])


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
        # Regresión: el pase implícito solo tiene hijos IT y no debe generar
        # tarjetas propias (fallo detectado al probar con 4-4 Joseki.sgf).
        r = run(";B[pd];W[nc](;W[qf]IT[]C[a])(;W[qh]IT[]C[b])")
        paths = sorted(".".join(c["path"]) for c in cards(r))
        self.assertNotIn("pd.nc.pass", paths)
        self.assertIn("pd.nc", paths)               # la línea principal sigue teniendo tarjeta
        self.assertIn("pd.nc.pass.qf", paths)
        self.assertIn("pd.nc.pass.qh", paths)

    def test_implicit_pass_not_required_from_player(self):
        # La tarjeta de B en la rama ¿y si? existe aunque B "pase" implícitamente.
        r = run(";B[pd];W[nc];W[qf]IT[]C[a];B[qh]")
        colors = {(c["color"], c["whatif"]) for c in cards(r) if "qf" in c["path"]}
        self.assertEqual(colors, {("B", True), ("W", True)})

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


class TestCards(unittest.TestCase):
    def test_learn_cards_per_line_and_colour(self):
        r = run(";B[pd];W[nc](;B[qf]C[a])(;B[pf]C[b])")
        self.assertEqual(len(cards(r)), 4)
        self.assertTrue(all(c["kind"] == "learn" and not c["whatif"] for c in cards(r)))
        self.assertEqual([c["order"] for c in cards(r)], [1, 1, 2, 2])

    def test_punish_card(self):
        r = run(";B[pd];W[nc]BM[1];B[qc]")
        self.assertEqual([(c["color"], c["kind"]) for c in cards(r)], [("B", "punish")])

    def test_doubtful(self):
        # Dudosa propia: no hay tarjeta; dudosa del rival: tarjeta normal, no castigo.
        r = run(";B[pd];W[nc]DO[1];B[qc]")
        self.assertEqual([(c["color"], c["kind"]) for c in cards(r)], [("B", "learn")])

    def test_line_without_cards_warns(self):
        r = run(";B[pd]BM[1];W[nc]BM[1]")
        self.assertEqual(cards(r), [])
        self.assertTrue(has(warnings(r), "línea sin tarjetas"))

    def test_whatif_does_not_alter_main_line(self):
        base = run(";B[pd];W[nc];B[qc]")
        with_it = run(";B[pd];W[nc];B[qc];W[qd]IT[]C[Si corta]")
        main = [c for c in cards(with_it) if not c["whatif"]]
        self.assertEqual([c["id"] for c in main], [c["id"] for c in cards(base)])
        self.assertEqual(len([c for c in cards(with_it) if c["whatif"]]), 2)

    def test_id_format_and_determinism(self):
        r1 = run(";B[pd];W[nc];B[tt]C[tenuki]", name="4-4 Joseki")
        r2 = run(";B[pd];W[nc];B[tt]C[tenuki]", name="4-4 Joseki")
        self.assertEqual(cards(r1)[0]["id"], "4-4 Joseki#pd.nc.pass#B")
        self.assertEqual(serialize(r1["data"]), serialize(r2["data"]))
        self.assertNotIn(b"_cards", serialize(r1["data"]))

    def test_sample_file(self):
        r = compile_joseki(SAMPLE.encode("utf-8"), "4-4 Joseki")
        self.assertTrue(r["ok"], r["issues"])
        self.assertEqual(r["cards"], 13)
        fixed = (SAMPLE.replace("(;B[qb]C[If we play", "(;B[qb]IT[]C[If we play")
                       .replace("(;B[tt]C[If Tenuki]", "(;B[tt]BM[1]C[If Tenuki]"))
        self.assertNotEqual(fixed, SAMPLE)  # anti-vacío: las correcciones se aplicaron
        r2 = compile_joseki(fixed.encode("utf-8"), "4-4 Joseki")
        self.assertEqual(r2["cards"], 14)
        self.assertIn("4-4 Joseki#pd.nc.qf.pb.qc.kc#B", [c["id"] for c in cards(r2)])


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
        self.assertTrue(os.path.isfile(os.path.join(self.folder, "a.json")))

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


if __name__ == "__main__":
    unittest.main(verbosity=1)
