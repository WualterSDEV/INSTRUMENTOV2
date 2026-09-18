"""
modelo/partido.py
=================
Probabilidades de un partido concreto, a partir de las fuerzas que dejó
modelo/ajuste.py.

La idea: se estiman los goles esperados de cada equipo, se arma la
matriz de todos los marcadores posibles, y cada mercado es una suma de
celdas de esa matriz. Así las probabilidades son coherentes entre sí:
"menos de 2.5" y "más de 2.5" siempre suman 100.
"""

import math

import numpy as np

from datos import almacen
from modelo.ajuste import cargar, tau

MAX_GOLES = 10          # 11x11 celdas cubre más del 99.9% de los casos


def goles_esperados(local, visitante, fuerzas=None):
    """Cuántos goles se espera que meta cada uno."""
    f = fuerzas or cargar()
    eq = f["equipos"]
    if local not in eq or visitante not in eq:
        return None

    l, v = eq[local], eq[visitante]
    lam = math.exp(l["ataque"] - v["defensa"] + f["localia"])
    mu = math.exp(v["ataque"] - l["defensa"])
    return {"local": lam, "visitante": mu,
            "n_partidos": min(l["n"], v["n"])}


def matriz(local, visitante, fuerzas=None):
    """P(marcador) para cada resultado posible, con Dixon-Coles."""
    f = fuerzas or cargar()
    ge = goles_esperados(local, visitante, f)
    if not ge:
        return None

    lam, mu, rho = ge["local"], ge["visitante"], f["rho"]

    def poisson(k, m):
        return math.exp(-m) * m ** k / math.factorial(k)

    m = np.zeros((MAX_GOLES + 1, MAX_GOLES + 1))
    for gl in range(MAX_GOLES + 1):
        for gv in range(MAX_GOLES + 1):
            m[gl, gv] = (poisson(gl, lam) * poisson(gv, mu)
                         * tau(gl, gv, lam, mu, rho))

    total = m.sum()
    if total > 0:
        m /= total          # renormaliza: tau rompe la suma a 1
    return m


def mercados(local, visitante, fuerzas=None):
    """Todo lo que sale de la matriz de marcadores.

    Devuelve probabilidades en 0-1. Quien las muestre las convierte.
    """
    f = fuerzas or cargar()
    m = matriz(local, visitante, f)
    if m is None:
        return None

    ge = goles_esperados(local, visitante, f)
    idx = np.indices(m.shape)
    total_goles = idx[0] + idx[1]

    out = {
        "goles_esperados_local": ge["local"],
        "goles_esperados_visitante": ge["visitante"],
        "goles_esperados": ge["local"] + ge["visitante"],
        "n_partidos": ge["n_partidos"],
        "prob_local": float(np.tril(m, -1).sum()),
        "prob_empate": float(np.trace(m)),
        "prob_visitante": float(np.triu(m, 1).sum()),
        "prob_btts": float(m[1:, 1:].sum()),
    }

    for umbral in (0.5, 1.5, 2.5, 3.5, 4.5):
        bajo = float(m[total_goles < umbral].sum())
        out[f"prob_menos_{umbral}"] = bajo
        out[f"prob_mas_{umbral}"] = 1.0 - bajo

    return out


# --- Conteos: tarjetas, tiros, córners, faltas -----------------------------
def _tasa(equipo, campo):
    r = almacen.uno(
        "SELECT por_90, concede, n_partidos FROM tasas "
        "WHERE equipo = ? AND campo = ?", (equipo, campo))
    return r


def conteo_esperado(local, visitante, campo, arbitro=None):
    """Cuántas tarjetas/tiros/córners/faltas se esperan en total.

    Se combina lo que hace cada equipo con lo que concede el rival:
    si uno comete muchas faltas y el otro las provoca, se suman.
    """
    tl, tv = _tasa(local, campo), _tasa(visitante, campo)
    if not tl or not tv:
        return None

    # media geométrica entre lo que hace uno y lo que provoca el otro
    def combinar(hace, provoca):
        if provoca is None:
            return hace
        return math.sqrt(max(hace, 0.1) * max(provoca, 0.1))

    esp_local = combinar(tl["por_90"], tv["concede"])
    esp_visita = combinar(tv["por_90"], tl["concede"])
    total = esp_local + esp_visita

    if campo == "tarjetas" and arbitro:
        total = _ajustar_por_arbitro(total, arbitro)

    return {"total": total, "local": esp_local, "visitante": esp_visita,
            "n_partidos": min(tl["n_partidos"], tv["n_partidos"])}


def _ajustar_por_arbitro(total, arbitro):
    """El árbitro designado mueve la línea de tarjetas de verdad."""
    r = almacen.uno("SELECT tarjetas_p90, n_partidos FROM arbitros "
                    "WHERE nombre = ?", (arbitro,))
    if not r or r["n_partidos"] < 5:
        return total

    media = almacen.uno(
        "SELECT AVG(tarjetas_p90) AS m FROM arbitros WHERE n_partidos >= 5")
    if not media or not media["m"]:
        return total

    factor = r["tarjetas_p90"] / media["m"]
    peso = almacen.parametros()["arbitro"] / 100.0
    return total * (1 + peso * (factor - 1))


def prob_mas_de(esperado, umbral):
    """P(X > umbral) con Poisson. El umbral siempre termina en .5."""
    from scipy.stats import poisson
    return float(1.0 - poisson.cdf(math.floor(umbral), esperado))


def factor_arbitro(arbitro):
    """Cuánto se aparta este árbitro del promedio. 1.0 = normal."""
    if not arbitro:
        return None
    r = almacen.uno("SELECT tarjetas_p90, n_partidos FROM arbitros "
                    "WHERE nombre = ?", (arbitro,))
    if not r or r["n_partidos"] < 5:
        return None
    media = almacen.uno(
        "SELECT AVG(tarjetas_p90) AS m FROM arbitros WHERE n_partidos >= 5")
    if not media or not media["m"]:
        return None
    return {"factor": r["tarjetas_p90"] / media["m"],
            "por_partido": r["tarjetas_p90"],
            "media_liga": media["m"],
            "n": r["n_partidos"]}
