"""
modelo/jugadores.py
===================
Líneas por jugador: tiros al arco, faltas, tarjeta, gol.

La regla del módulo: primero se estiman los MINUTOS que va a jugar, y
recién después se aplica su tasa por 90. Un delantero que rinde
excelente pero entra a los 70 tiene números bajos, y eso es correcto.
"""

import math

from datos import almacen
from modelo.partido import prob_mas_de

# Minutos típicos según el rol en la alineación probable.
MINUTOS = {"titular_fijo": 88, "titular": 80, "rotativo": 62, "suplente": 22}

PUESTO_ES = {"Goalkeeper": "Arquero", "Defender": "Defensor",
             "Midfielder": "Mediocampista", "Attacker": "Delantero"}

# Qué líneas tiene sentido mostrar para cada puesto. Un arquero con
# "más de 0.5 tiros al arco" es ruido.
LINEAS_POR_PUESTO = {
    "Goalkeeper": ["atajadas"],
    "Defender": ["despejes", "faltas", "tarjeta"],
    "Midfielder": ["faltas", "tiros", "tarjeta"],
    "Attacker": ["tiros", "gol", "faltas"],
}

PALABRA = {"tiros": "tiros al arco", "faltas": "faltas cometidas",
           "despejes": "despejes", "atajadas": "atajadas",
           "regates": "regates completados"}


def minutos_esperados(jugador):
    """Cuánto se espera que juegue. Es lo que más error mete."""
    if jugador.get("minutos_esperados"):
        return int(jugador["minutos_esperados"])
    rol = jugador.get("rol", "titular")
    return MINUTOS.get(rol, 80)


def escalar(tasa_por_90, minutos):
    """Una tasa por 90 minutos, llevada a los minutos que va a jugar."""
    return float(tasa_por_90) * minutos / 90.0


def lineas_jugador(jugador, contra=None):
    """Las líneas de un jugador, ya en umbrales .5.

    `jugador` trae sus tasas por 90: {tiros: 1.4, faltas: 1.1, ...}
    """
    mins = minutos_esperados(jugador)
    puesto = jugador.get("puesto", "Midfielder")
    permitidas = LINEAS_POR_PUESTO.get(puesto, ["faltas", "tarjeta"])

    salida = []
    for clave in permitidas:
        if clave == "tarjeta":
            p = jugador.get("prob_tarjeta")
            if p is None:
                p = _prob_tarjeta(jugador, mins)
            if p and p >= 0.08:
                salida.append({"etiqueta": "Recibe tarjeta",
                               "prob": round(p * 100)})
            continue

        if clave == "gol":
            p = jugador.get("prob_gol")
            if p is None:
                p = _prob_gol(jugador, mins)
            if p and p >= 0.08:
                salida.append({"etiqueta": "Marca un gol",
                               "prob": round(p * 100)})
            continue

        tasa = jugador.get(clave)
        if tasa is None:
            continue
        esp = escalar(tasa, mins)
        salida.extend(_umbrales(PALABRA[clave], esp))

    return salida


def _umbrales(palabra, esperado, cuantos=2):
    """De un esperado a dos líneas .5 con probabilidad razonable.

    Se descartan las que están por encima del 92% o por debajo del 12%:
    una línea que casi siempre sale no dice nada.
    """
    base = math.floor(esperado) + 0.5
    out = []
    for i in range(cuantos):
        u = base + i
        if u < 0.5:
            continue
        p = prob_mas_de(esperado, u)
        if 0.12 <= p <= 0.92:
            out.append({"etiqueta": f"Más de {u:.1f} {palabra}",
                        "prob": round(p * 100)})
    return out


def _prob_tarjeta(jugador, mins):
    """Aproximación desde las faltas: más faltas, más riesgo de amarilla."""
    faltas = jugador.get("faltas")
    if faltas is None:
        return None
    esp_faltas = escalar(faltas, mins)
    # Regla empírica: alrededor de una amarilla cada seis faltas.
    return min(0.65, 1 - math.exp(-esp_faltas / 6.0))


def _prob_gol(jugador, mins):
    tiros = jugador.get("tiros")
    if tiros is None:
        return None
    esp = escalar(tiros, mins)
    conversion = jugador.get("conversion", 0.30)
    return min(0.75, 1 - math.exp(-esp * conversion))


def tasas_guardadas(nombre):
    """Las tasas de un jugador desde la base, si las hay."""
    filas = almacen.consultar(
        "SELECT campo, por_90, n_partidos FROM tasas WHERE equipo = ?",
        (nombre,))
    if not filas:
        return None
    return {f["campo"]: f["por_90"] for f in filas}


def nota_jugadores():
    """El texto que acompaña al bloque. Se escribe una sola vez, acá."""
    return ("Calculado sobre los minutos que se esperan para cada jugador, "
            "no sobre el partido completo.")
