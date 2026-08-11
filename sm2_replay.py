"""Reconstruccion en Python de updateSm2() (version T16 ya corregida) de
tsumevault.html, fiel al codigo real. Usada tanto por el script de reparacion
como por su propia validacion cruzada contra el JS real."""
import math

def js_round(x):
    """Replica Math.round de JS: redondea .5 siempre hacia arriba (no banker's
    rounding como el round() nativo de Python)."""
    return math.floor(x + 0.5)

def replay_sm2(results, rand_source):
    """results: lista de 'correct'/'wrong' en orden cronologico.
    rand_source: funcion sin argumentos que devuelve un float en [0,1),
    llamada una vez por cada resultado 'correct' (nunca por 'wrong').
    Devuelve (interval, easiness, repetitions, days_until_due)."""
    interval = 6.0
    easiness = 2.5
    repetitions = 0
    days_until_due = 6.0
    for result in results:
        if result == 'correct':
            repetitions += 1
            next_base = 6.0 if repetitions == 1 else js_round(interval * easiness)
            next_next = js_round(next_base * easiness)
            span = max(1, next_next - next_base)
            jitter = next_base + math.floor(rand_source() * span)
            days_until_due = jitter
            interval = next_base
        else:
            repetitions = 0
            interval = 1.0
            days_until_due = interval
            easiness = max(1.3, easiness - 0.2)
    return interval, easiness, repetitions, days_until_due
