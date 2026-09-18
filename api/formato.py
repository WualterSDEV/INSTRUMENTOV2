"""
api/formato.py
==============
La única capa que escribe texto y arma líneas .5.

Todo lo que el usuario lee sale de acá: los resúmenes, las
explicaciones, los veredictos. El front no redacta ni calcula. Si algo
se lee mal, se arregla en este archivo y nada más.
"""

import math

import config
from modelo.partido import prob_mas_de


def pct(p):
    """0-1 o 0-100 -> entero 0-100. Nunca decimales en pantalla."""
    if p is None:
        return None
    p = float(p)
    return int(round(p * 100 if p <= 1.0 else p))


def umbral_bajo(x):
    """4.8 -> 4.5 ; 2.0 -> 1.5. Nunca un entero.

    Una línea tiene que poder pasarse o no. "Más de 2 goles" es ambiguo
    cuando salen exactamente dos.
    """
    return math.floor(float(x)) + 0.5


def linea_mas(palabra, umbral, prob):
    return {"etiqueta": f"Más de {umbral:.1f} {palabra}", "prob": pct(prob)}


def linea_menos(palabra, umbral, prob):
    return {"etiqueta": f"Menos de {umbral:.1f} {palabra}", "prob": pct(prob)}


def estrellas(n_partidos, datos_completos=True):
    """Cuánta información tiene el modelo: 1 a 5.

    No es qué tan probable es un resultado. Es cuántos partidos
    parecidos tiene para aprender de este.
    """
    if not n_partidos:
        return 1
    n = int(n_partidos)
    base = 5 if n >= 60 else 4 if n >= 38 else 3 if n >= 22 else 2 if n >= 10 else 1
    return base if datos_completos else max(1, base - 1)


# --- Los ocho temas --------------------------------------------------------
TEMAS = [
    ("resultado", "Quién gana", "1X2"),
    ("goles", "Goles", "Totales (over/under)"),
    ("ambos", "Ambos marcan", "BTTS"),
    ("tarjetas", "Tarjetas", "Tarjetas totales"),
    ("tiros", "Tiros al arco", "Tiros al arco (SOT)"),
    ("corners", "Córners", "Córners totales"),
    ("faltas", "Faltas", "Faltas totales"),
    ("jugadores", "Jugadores", "Player props"),
]

PALABRA = {"tarjetas": "tarjetas", "tiros": "tiros al arco",
           "corners": "córners", "faltas": "faltas"}

CALCULO = {
    "resultado": "Se estima cuántos goles suele meter cada equipo y cuántos "
                 "suele recibir, ajustado por localía y por la fuerza del "
                 "rival. Con eso se arma la tabla de todos los marcadores "
                 "posibles y se suman los que dan cada resultado.",
    "goles": "Los goles de cada equipo se modelan por separado y después se "
             "combinan, con una corrección para los partidos de pocos goles, "
             "donde el método simple falla.",
    "ambos": "Sale de la misma tabla de marcadores: es la suma de todas las "
             "celdas donde los dos anotaron al menos uno.",
    "tarjetas": "Parte de las tarjetas que suele recibir cada equipo y las "
                "que suele provocar en el rival, y se corrige por el árbitro "
                "designado.",
    "tiros": "Usa el volumen de remate de cada equipo cruzado con lo que "
             "concede el rival. Los partidos viejos pesan menos que los "
             "recientes.",
    "corners": "Se estima a partir de cuántos córners genera y concede cada "
               "equipo, corregido por cuánto se espera que domine cada uno.",
    "faltas": "Se apoya en el promedio de faltas de los dos equipos y en el "
              "ritmo esperado del partido.",
    "jugadores": "Primero se estiman los minutos que va a jugar cada uno, y "
                 "sobre esos minutos se aplica su tasa histórica por cada 90. "
                 "Por eso un suplente da números bajos aunque rinda bien.",
}


def tema_resultado(m, local, visitante):
    pl, pe, pv = pct(m["prob_local"]), pct(m["prob_empate"]), pct(m["prob_visitante"])
    d = abs(pl - pv)
    fav = local if pl > pv else visitante
    return {
        "id": "resultado", "nombre": "Quién gana", "nombre_tecnico": "1X2",
        "resumen": "Partido cerrado" if d <= 8 else f"Favorito {fav}",
        "signo": f"{pl} · {pe} · {pv}",
        "senal": d > 8,
        "lineas": [
            {"etiqueta": f"Gana {local}", "prob": pl},
            {"etiqueta": "Empate", "prob": pe},
            {"etiqueta": f"Gana {visitante}", "prob": pv},
        ],
        "porque": ("Ninguno de los tres resultados se despega." if d <= 8
                   else f"{fav} crea más y concede menos, pero el empate "
                        "sigue vivo."),
        "calculo": CALCULO["resultado"],
    }


def tema_goles(m):
    esp = m["goles_esperados"]
    p_menos = pct(m["prob_menos_2.5"])
    bajo = p_menos >= 50

    lineas = [
        linea_menos("goles", 2.5, p_menos / 100),
        linea_mas("goles", 2.5, (100 - p_menos) / 100),
    ]
    extra = 3.5 if bajo else 1.5
    clave = f"prob_{'menos' if bajo else 'mas'}_{extra}"
    if clave in m:
        f = linea_menos if bajo else linea_mas
        lineas.append(f("goles", extra, m[clave]))

    return {
        "id": "goles", "nombre": "Goles",
        "nombre_tecnico": "Totales (over/under)",
        "resumen": f"La línea principal es {'menos' if bajo else 'más'} de 2.5 goles",
        "signo": f"{'−' if bajo else '+'}2.5",
        "senal": abs(p_menos - 50) >= 6,
        "lineas": lineas,
        "porque": (f"Se esperan {esp:.1f} goles en total, "
                   f"{'por debajo' if esp < 2.7 else 'por encima'} del "
                   "promedio de la liga."),
        "calculo": CALCULO["goles"],
    }


def tema_ambos(m):
    p = pct(m["prob_btts"])
    return {
        "id": "ambos", "nombre": "Ambos marcan", "nombre_tecnico": "BTTS",
        "resumen": "Más probable que sí" if p >= 50 else "Más probable que no",
        "signo": f"{p}%",
        "senal": abs(p - 50) >= 6,
        "lineas": [
            {"etiqueta": "Sí, ambos marcan", "prob": p},
            {"etiqueta": "No", "prob": 100 - p},
        ],
        "porque": ("Los dos convierten seguido." if p >= 55 else
                   "Al menos uno suele quedarse en cero."),
        "calculo": CALCULO["ambos"],
    }


def tema_conteo(tid, esperado, arbitro=None):
    """Tarjetas, tiros, córners y faltas: todos se arman igual.

    El esperado (4.8) nunca sale de acá. Salen dos o tres líneas .5
    alrededor de él.
    """
    palabra = PALABRA[tid]
    nombre = dict((t[0], t[1]) for t in TEMAS)[tid]
    tecnico = dict((t[0], t[2]) for t in TEMAS)[tid]

    centro = umbral_bajo(esperado)
    lineas = []
    for u in (centro - 1, centro, centro + 1):
        if u < 0.5:
            continue
        p = prob_mas_de(esperado, u)
        if 0.12 <= p <= 0.93:
            lineas.append(linea_mas(palabra, u, p))

    if not lineas:
        return None

    p_centro = next((l["prob"] for l in lineas
                     if f"{centro:.1f}" in l["etiqueta"]), 50)

    return {
        "id": tid, "nombre": nombre, "nombre_tecnico": tecnico,
        "resumen": _resumen_conteo(tid, p_centro, centro, arbitro),
        "signo": f"+{centro:.1f}",
        "senal": abs(p_centro - 50) >= 8,
        "lineas": lineas,
        "porque": _porque_conteo(tid, esperado, arbitro),
        "calculo": CALCULO[tid],
    }


def _resumen_conteo(tid, p, centro, arbitro):
    if p < 55:
        return "Cerca del promedio, sin nada llamativo"
    if tid == "tarjetas" and arbitro and arbitro.get("factor", 1) > 1.15:
        return f"Árbitro exigente: la línea se va a más de {centro:.1f}"
    titulo = {"tarjetas": "Partido de muchas tarjetas",
              "tiros": "Volumen de remate alto",
              "corners": "Bastantes córners esperados",
              "faltas": "Muchas faltas por el ritmo"}[tid]
    return f"{titulo}: más de {centro:.1f}"


def _porque_conteo(tid, esperado, arbitro):
    if tid == "tarjetas":
        if arbitro and arbitro.get("factor", 1) > 1.15:
            dif = int(round(100 * (arbitro["factor"] - 1)))
            return (f"El árbitro designado saca un {dif}% más de tarjetas "
                    "que el promedio de la liga.")
        return "Se apoya en el historial de faltas de los dos equipos."
    if tid == "tiros":
        return ("Cruza el volumen de remate de cada uno con lo que concede "
                "el rival.")
    if tid == "corners":
        return "Depende sobre todo de cuánto se espera que domine cada equipo."
    return ("Dos equipos que presionan alto cortan el juego seguido en la "
            "mitad de cancha.")


def tema_jugadores():
    from modelo.jugadores import nota_jugadores
    return {
        "id": "jugadores", "nombre": "Jugadores",
        "nombre_tecnico": "Player props",
        "resumen": "Elegí un equipo y verás sus jugadores uno por uno",
        "signo": "—", "senal": True, "lineas": [],
        "por_jugador": True,
        "porque": nota_jugadores(),
        "calculo": CALCULO["jugadores"],
    }


# --- Textos de pantalla ----------------------------------------------------
def titular(temas, conf, local, visitante):
    """Las dos o tres líneas del resumen de arriba.

    Se elige el tema con más señal, no el primero de la lista.
    """
    if conf <= 1:
        return ("El modelo casi no tiene datos de este partido. "
                "Tomá cualquier número con pinzas.")

    con_senal = [t for t in temas if t.get("senal") and t.get("lineas")]
    if not con_senal:
        return ("Partido sin nada que se despegue. El modelo no ve ningún "
                "tema con señal clara.")

    mejor = max(con_senal,
                key=lambda t: max(l["prob"] for l in t["lineas"]))
    linea = max(mejor["lineas"], key=lambda l: l["prob"])

    txt = (f"Lo más destacable son {mejor['nombre'].lower()}: "
           f"{linea['etiqueta'].lower()} al {linea['prob']}%.")
    if conf == 2:
        txt += " El modelo avisa que tiene poco con qué estimar."
    return txt


def titular_lista(m, conf, local, visitante):
    """La frase corta de la tarjeta en la lista de partidos."""
    if not m:
        return "Todavía no hay datos suficientes para este partido."
    if conf <= 2:
        return (f"Pocos datos de {visitante} esta temporada. "
                "El modelo avisa que confía poco.")

    pl, pv = pct(m["prob_local"]), pct(m["prob_visitante"])
    esp = m["goles_esperados"]
    d = abs(pl - pv)

    if d <= 8:
        return (f"Partido muy parejo. Se esperan pocos goles."
                if esp < 2.5 else "Partido muy parejo y de ida y vuelta.")
    fav = local if pl > pv else visitante
    if d >= 25:
        return f"{fav} es claro favorito. Lo interesante está en otros temas."
    return f"Leve ventaja de {fav}, pero el partido está abierto."


def veredicto_vivo(filas):
    """'¿Va como dijo el modelo?' en la pantalla de en vivo."""
    altos = [f["nombre"].lower() for f in filas if f["estado"] == "por encima"]
    bajos = [f["nombre"].lower() for f in filas if f["estado"] == "por debajo"]
    if not altos and not bajos:
        return "Todo va como el modelo había previsto."
    if altos and not bajos:
        return f"Va por encima de lo previsto en {_y(altos)}."
    if bajos and not altos:
        return f"Va por debajo de lo previsto en {_y(bajos)}."
    return f"Por encima en {_y(altos)}, por debajo en {_y(bajos)}."


def _y(lista):
    if len(lista) == 1:
        return lista[0]
    return ", ".join(lista[:-1]) + " y " + lista[-1]


def estado_vivo(real, esperado):
    razon = real / esperado if esperado else 1.0
    if razon > 1.2:
        return "por encima"
    if razon < 0.8:
        return "por debajo"
    return "como se esperaba"


def resumen_jugado(temas):
    ok = sum(1 for t in temas if t.get("ok"))
    n = len(temas)
    if n == 0:
        return ""
    if ok == n:
        return "El modelo acertó en todos los temas."
    if ok == 0:
        return "El modelo falló en todos los temas."
    return f"Acertó {ok} de {n} temas."


def nota_jugado():
    return ("Un tema con 55% que falla no significa que el modelo estuviera "
            "mal: significa que pasó lo otro.")


def h2h_nota(cruces):
    if not cruces:
        return ("Sin historial suficiente, el modelo se apoya solo en la "
                "forma de cada equipo.")
    bajos = sum(1 for c in cruces if c.get("total_goles", 9) <= 2)
    if bajos >= len(cruces) - 1:
        return (f"{bajos} de los últimos {len(cruces)} cruces terminaron con "
                "dos goles o menos. Eso sostiene la línea de menos de 2.5.")
    return f"Los últimos {len(cruces)} cruces fueron parejos y con goles."


def nota_arbitro(perfil, nombre):
    if not nombre:
        return ("Sin designar. Cuando se confirme, el tema de tarjetas se "
                "recalcula.")
    if not perfil:
        return "Sin historial cargado de este árbitro."
    dif = int(round(100 * (perfil["factor"] - 1)))
    tpp = perfil["por_partido"]
    if dif >= 15:
        return (f"Promedia {tpp:.1f} tarjetas por partido, un {dif}% más que "
                "el resto de la liga.")
    if dif <= -15:
        return (f"Promedia {tpp:.1f} tarjetas por partido, un {abs(dif)}% "
                "menos que el resto de la liga.")
    return f"Promedia {tpp:.1f} tarjetas por partido, como el resto."


def pendiente(mensaje):
    """Cuando falta un dato se dice, no se inventa."""
    return {"pendiente": True, "mensaje": mensaje}
