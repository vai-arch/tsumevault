#!/usr/bin/env python3
"""fake_gtp.py — motor GTP falso para test_server.py (IA1). Imita lo justo de
KataGo para probar ai_engines.py sin KataGo. Controlado por entorno:
    FAKE_GTP_LOG        fichero donde apunta cada comando recibido
    FAKE_GTP_DELAY      segundos que tarda genmove (0 por defecto)
    FAKE_GTP_DIE_FILE   si existe al llegar un genmove: lo borra y muere sin responder
    FAKE_GTP_SEARCH_DELAY  segundos que tarda kata-search_analyze (0 por defecto)
Juega en el primer punto libre de su lista y, si la última jugada fue un pase,
pasa también (así se puede probar el final por dos pases).
"""
import os
import sys
import time

log_path = os.environ.get("FAKE_GTP_LOG")
delay = float(os.environ.get("FAKE_GTP_DELAY", "0") or 0)
die_file = os.environ.get("FAKE_GTP_DIE_FILE")
search_delay = float(os.environ.get("FAKE_GTP_SEARCH_DELAY", "0") or 0)
occupied = set()
last_play = None
ORDER = ["Q16", "D4", "Q4", "D16", "K10"] + [c + str(r) for r in range(19, 0, -1) for c in "ABCDEFGHJKLMNOPQRST"]


def out(ok, text=""):
    sys.stdout.write(("= " if ok else "? ") + text + "\n\n")
    sys.stdout.flush()


for raw in sys.stdin:
    line = raw.strip()
    if not line:
        continue
    if log_path:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    parts = line.split()
    cmd, args = parts[0], parts[1:]
    if cmd == "quit":
        out(True)
        break
    if cmd == "clear_board":
        occupied.clear()
        last_play = None
        out(True)
    elif cmd in ("boardsize", "komi", "kata-set-rules", "kata-set-param", "protocol_version",
                 "go_rules"):   # go_rules: rules_cmd de un motor extra (ai_engines.json) en los tests
        out(True, "2" if cmd == "protocol_version" else "")
    elif cmd == "set_free_handicap":
        occupied.update(args)
        out(True)
    elif cmd == "play":
        v = args[1]
        last_play = v
        if v != "pass" and v in occupied:
            out(False, "illegal move")
        else:
            if v != "pass":
                occupied.add(v)
            out(True)
    elif cmd == "genmove":
        if die_file and os.path.exists(die_file):
            os.remove(die_file)
            sys.exit(1)
        time.sleep(delay)
        if last_play == "pass":
            out(True, "pass")
            continue
        mv = next((v for v in ORDER if v not in occupied), "pass")
        occupied.add(mv)
        out(True, mv)
    elif cmd == "kata-search_analyze":
        time.sleep(search_delay)
        free = [v for v in ORDER if v not in occupied][:3]
        leads = (3.5, 1.2, -0.8)
        infos = " ".join(
            f"info move {v} visits {40 - 10 * i} winrate 0.6 scoreLead {leads[i]} prior 0.2 order {i} pv {v} {free[(i + 1) % len(free)]}"
            for i, v in enumerate(free))
        sys.stdout.write("= info move Q16 visits 1 scoreLead 0 order 0 pv Q16\n")   # línea intermedia (se ignora)
        sys.stdout.write(infos + " rootInfo visits 90 winrate 0.6 scoreLead 3.4\nplay " + free[0] + "\n\n")
        sys.stdout.flush()
    elif cmd == "final_score":
        out(True, "W+3.5")
    elif cmd == "final_status_list":
        out(True, "D4 E5\nQ16")
    elif cmd == "kata-raw-nn":
        lead = round(-2.37 + 0.5 * (len(occupied) - 3), 2)   # varía con la posición (gráfica)
        own = "\n".join(" ".join("0.9" if c > 9 else "-0.8" if c < 9 else "0.0" for c in range(19)) for _ in range(19))
        out(True, "symmetry 0\nwhiteWin 0.3\nwhiteLead " + str(lead) + "\npolicy\n0.1 0.2\nwhiteOwnership\n" + own)
    else:
        out(False, "unknown command")
