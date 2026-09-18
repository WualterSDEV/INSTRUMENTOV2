"""
modelo/ajuste.py
================
Estima la fuerza de ataque y defensa de cada equipo a partir de los
resultados, con decaimiento temporal: un partido de hace seis meses pesa
la mitad que uno de esta semana.

    python -m modelo.ajuste --reajustar

Es el corazón del modelo. Todo lo demás (goles, tarjetas, jugadores)
sale de acá o usa la misma idea.
"""

import math
from datetime import date, datetime

import numpy as np
from scipy.optimize import minimize

import config
from datos import almacen


def peso_temporal(fecha_partido, hoy=None, vida_media=180):
    """Un partido viejo cuenta menos. Vida media en días.

    A los 180 días pesa 0.5, a los 360 pesa 0.25. Sin esto el modelo
    trata igual un partido de la temporada pasada que el del domingo.
    """
    hoy = hoy or date.today()
    if isinstance(fecha_partido, str):
        fecha_partido = datetime.fromisoformat(fecha_partido[:10]).date()
    dias = (hoy - fecha_partido).days
    if dias < 0:
        return 1.0
    return 0.5 ** (dias / vida_media)


def _partidos_para_ajuste(liga_id=None, minimo_por_equipo=5):
    q = """SELECT fecha, local, visitante, goles_local, goles_visitante
           FROM partidos
           WHERE estado = 'jugado' AND goles_local IS NOT NULL"""
    params = ()
    if liga_id:
        q += " AND liga_id = ?"
        params = (liga_id,)
    filas = almacen.consultar(q + " ORDER BY fecha", params)

    cuenta = {}
    for f in filas:
        cuenta[f["local"]] = cuenta.get(f["local"], 0) + 1
        cuenta[f["visitante"]] = cuenta.get(f["visitante"], 0) + 1

    ok = {e for e, n in cuenta.items() if n >= minimo_por_equipo}
    return [f for f in filas
            if f["local"] in ok and f["visitante"] in ok], sorted(ok)


def tau(gl, gv, lam, mu, rho):
    """Corrección de Dixon-Coles para resultados bajos.

    Poisson simple subestima los 0-0 y 1-1 y sobreestima los 1-0 y 0-1.
    Esta función arregla exactamente esas cuatro celdas. Sin ella, el
    modelo da mal las líneas de pocos goles, que son las más usadas.
    """
    if gl == 0 and gv == 0:
        return 1 - lam * mu * rho
    if gl == 0 and gv == 1:
        return 1 + lam * rho
    if gl == 1 and gv == 0:
        return 1 + mu * rho
    if gl == 1 and gv == 1:
        return 1 - rho
    return 1.0


def _log_verosimilitud(x, partidos, equipos, pesos):
    """Lo que el optimizador minimiza (en negativo)."""
    n = len(equipos)
    idx = {e: i for i, e in enumerate(equipos)}
    ataque = x[:n]
    defensa = x[n:2 * n]
    localia, rho = x[2 * n], x[2 * n + 1]

    total = 0.0
    for p, w in zip(partidos, pesos):
        i, j = idx[p["local"]], idx[p["visitante"]]
        lam = math.exp(ataque[i] - defensa[j] + localia)
        mu = math.exp(ataque[j] - defensa[i])
        gl, gv = int(p["goles_local"]), int(p["goles_visitante"])

        t = tau(gl, gv, lam, mu, rho)
        if t <= 0:
            t = 1e-10

        ll = (math.log(t)
              - lam + gl * math.log(lam) - math.lgamma(gl + 1)
              - mu + gv * math.log(mu) - math.lgamma(gv + 1))
        total += w * ll

    return -total


def ajustar(liga_id=None, verbose=True):
    """Calcula ataque y defensa de cada equipo. Devuelve un dict."""
    par = almacen.parametros()
    partidos, equipos = _partidos_para_ajuste(liga_id)

    if len(partidos) < 30:
        if verbose:
            print(f"  solo {len(partidos)} partidos: no alcanza para ajustar")
        return {}

    hoy = date.today()
    pesos = [peso_temporal(p["fecha"], hoy, par["vida_media"])
             for p in partidos]

    n = len(equipos)
    x0 = np.concatenate([np.zeros(n), np.zeros(n),
                         [par["localia"]], [-0.05]])

    # El promedio de ataque se fija en cero: si no, el modelo puede
    # subir todos los ataques y bajar todas las defensas sin cambiar
    # ninguna predicción, y el optimizador nunca converge.
    restriccion = {"type": "eq", "fun": lambda x: x[:n].sum()}

    res = minimize(_log_verosimilitud, x0,
                   args=(partidos, equipos, pesos),
                   constraints=[restriccion],
                   method="SLSQP",
                   options={"maxiter": 200, "ftol": 1e-6})

    if not res.success and verbose:
        print(f"  aviso: el ajuste no convergió del todo ({res.message})")

    x = res.x
    salida = {
        "equipos": {},
        "localia": float(x[2 * n]),
        "rho": float(x[2 * n + 1]),
        "n_partidos": len(partidos),
    }
    cuenta = {}
    for p in partidos:
        cuenta[p["local"]] = cuenta.get(p["local"], 0) + 1
        cuenta[p["visitante"]] = cuenta.get(p["visitante"], 0) + 1

    for i, e in enumerate(equipos):
        salida["equipos"][e] = {
            "ataque": float(x[i]),
            "defensa": float(x[n + i]),
            "n": cuenta.get(e, 0),
        }

    if verbose:
        print(f"  {n} equipos, {len(partidos)} partidos, "
              f"localía {salida['localia']:.3f}, rho {salida['rho']:.3f}")
    return salida


def guardar(salida):
    """Persiste las fuerzas para que la API no reajuste en cada request."""
    if not salida:
        return 0
    ahora = datetime.now().isoformat(timespec="seconds")
    filas = [{"equipo": e, "liga_id": None, "ataque": v["ataque"],
              "defensa": v["defensa"], "n_partidos": v["n"],
              "ajustado": ahora}
             for e, v in salida["equipos"].items()]
    almacen.guardar_muchos("fuerzas", filas)
    almacen.escribir_ajuste("localia_ajustada", salida["localia"])
    almacen.escribir_ajuste("rho", salida["rho"])
    almacen.escribir_ajuste("ajustado", ahora)
    return len(filas)


def cargar():
    """Las fuerzas guardadas. Lo que usa la API en cada request."""
    filas = almacen.consultar("SELECT * FROM fuerzas")
    return {
        "equipos": {f["equipo"]: {"ataque": f["ataque"],
                                  "defensa": f["defensa"],
                                  "n": f["n_partidos"]} for f in filas},
        "localia": almacen.leer_ajuste("localia_ajustada",
                                       config.PARAMETROS["localia"]),
        "rho": almacen.leer_ajuste("rho", -0.05),
        "ajustado": almacen.leer_ajuste("ajustado"),
    }


def tasas_conteo(verbose=True):
    """Tarjetas, tiros, córners y faltas por equipo: cuántas hace y
    cuántas provoca en el rival.

    No necesita Dixon-Coles: con el promedio ponderado por tiempo
    alcanza, porque son conteos mucho más estables que los goles.
    """
    par = almacen.parametros()
    hoy = date.today()
    campos = ["tarjetas", "tiros", "corners", "faltas"]

    filas = almacen.consultar(
        """SELECT fecha, local, visitante,
                  tarjetas_local, tarjetas_visitante,
                  tiros_local, tiros_visitante,
                  corners_local, corners_visitante,
                  faltas_local, faltas_visitante
           FROM partidos WHERE estado = 'jugado'""")

    acum = {}
    for f in filas:
        w = peso_temporal(f["fecha"], hoy, par["vida_media"])
        for campo in campos:
            for lado, otro in (("local", "visitante"), ("visitante", "local")):
                equipo = f[lado]
                propio = f[f"{campo}_{lado}"]
                rival = f[f"{campo}_{otro}"]
                if propio is None:
                    continue
                k = (equipo, campo)
                a = acum.setdefault(k, {"w": 0.0, "hizo": 0.0,
                                        "concedio": 0.0, "n": 0})
                a["w"] += w
                a["hizo"] += w * float(propio)
                a["concedio"] += w * float(rival or 0)
                a["n"] += 1

    salida = []
    for (equipo, campo), a in acum.items():
        if a["w"] <= 0 or a["n"] < 4:
            continue
        salida.append({
            "equipo": equipo, "campo": campo,
            "por_90": a["hizo"] / a["w"],
            "concede": a["concedio"] / a["w"],
            "n_partidos": a["n"],
        })

    almacen.guardar_muchos("tasas", salida)
    if verbose:
        print(f"  {len(salida)} tasas de conteo guardadas")
    return len(salida)


def perfiles_arbitro(verbose=True):
    """Cuántas tarjetas saca cada árbitro por partido.

    Es el único dato externo que mueve de verdad la línea de tarjetas.
    """
    filas = almacen.consultar(
        """SELECT arbitro, tarjetas_local, tarjetas_visitante, faltas_local,
                  faltas_visitante
           FROM partidos
           WHERE estado = 'jugado' AND arbitro IS NOT NULL
                 AND tarjetas_local IS NOT NULL""")

    acum = {}
    for f in filas:
        a = acum.setdefault(f["arbitro"], {"t": 0, "f": 0, "n": 0})
        a["t"] += int(f["tarjetas_local"]) + int(f["tarjetas_visitante"])
        a["f"] += int(f["faltas_local"] or 0) + int(f["faltas_visitante"] or 0)
        a["n"] += 1

    salida = [{"nombre": nombre, "tarjetas_p90": a["t"] / a["n"],
               "faltas_p90": a["f"] / a["n"] if a["f"] else None,
               "n_partidos": a["n"]}
              for nombre, a in acum.items() if a["n"] >= 5]

    almacen.guardar_muchos("arbitros", salida)
    if verbose:
        print(f"  {len(salida)} árbitros con historial suficiente")
    return len(salida)


def reajustar_todo(verbose=True):
    """Lo que corre el cron después de la ingesta diaria."""
    almacen.crear_tablas()
    if verbose:
        print("Ajustando fuerzas de ataque y defensa…")
    guardar(ajustar(verbose=verbose))
    if verbose:
        print("Calculando tasas de conteo…")
    tasas_conteo(verbose)
    if verbose:
        print("Perfilando árbitros…")
    perfiles_arbitro(verbose)
    if verbose:
        print("Listo.")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--reajustar", action="store_true")
    a = ap.parse_args()
    reajustar_todo()
