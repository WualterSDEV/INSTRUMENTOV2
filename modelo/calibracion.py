"""
modelo/calibracion.py
=====================
Dos cosas:

  1. Resolver una línea guardada contra lo que realmente pasó.
  2. Medir si el modelo está bien calibrado: cuando dice 70%, ¿pasa
     el 70% de las veces?

La calibración importa más que el porcentaje de acierto. Un modelo que
solo predice favoritos acierta mucho y no sirve para nada.
"""

import re

from datos import almacen

# Cómo se lee una línea escrita en español.
PATRON = re.compile(
    r"(más|menos) de (\d+\.5) (goles|tarjetas|tiros al arco|córners|faltas)",
    re.IGNORECASE)

CAMPO = {"goles": "goles", "tarjetas": "tarjetas", "tiros al arco": "tiros",
         "córners": "corners", "faltas": "faltas"}


def evaluar_linea(tema, linea, partido):
    """¿Se cumplió esta línea? True, False o None si no se puede saber.

    None no es un fallo: significa que faltan los datos de ese campo
    en ese partido. Mejor dejarla pendiente que contarla mal.
    """
    l = (linea or "").strip().lower()

    m = PATRON.search(l)
    if m:
        direccion, umbral, palabra = m.group(1), float(m.group(2)), m.group(3)
        campo = CAMPO[palabra.lower()]
        total = _total(partido, campo)
        if total is None:
            return None
        return total > umbral if direccion == "más" else total < umbral

    gl, gv = partido.get("goles_local"), partido.get("goles_visitante")
    if gl is None or gv is None:
        return None
    gl, gv = int(gl), int(gv)

    if l.startswith("sí, ambos marcan") or l == "ambos marcan":
        return gl > 0 and gv > 0
    if l == "no":
        return not (gl > 0 and gv > 0)
    if l == "empate":
        return gl == gv
    if l.startswith("gana "):
        equipo = linea[5:].strip()
        if equipo == partido.get("local"):
            return gl > gv
        if equipo == partido.get("visitante"):
            return gv > gl
        return None

    return None


def _total(partido, campo):
    if campo == "goles":
        gl, gv = partido.get("goles_local"), partido.get("goles_visitante")
        return None if gl is None or gv is None else int(gl) + int(gv)
    a, b = partido.get(f"{campo}_local"), partido.get(f"{campo}_visitante")
    return None if a is None or b is None else int(a) + int(b)


# --- Calibración -----------------------------------------------------------
BANDAS = [(0.50, 0.60), (0.60, 0.70), (0.70, 0.80), (0.80, 1.01)]


def calibracion(liga_id=None, dias=90, usuario=None):
    """Por cada banda de probabilidad: qué dijo el modelo y qué pasó."""
    from datetime import datetime, timedelta

    q = """SELECT prob, acierto, tema FROM predicciones
           WHERE resuelta = 1 AND creada >= ?"""
    params = [(datetime.now() - timedelta(days=dias)).isoformat()]
    if liga_id:
        q += " AND liga_id = ?"
        params.append(liga_id)
    if usuario:
        q += " AND usuario = ?"
        params.append(usuario)

    filas = almacen.consultar(q, tuple(params))
    if not filas:
        return []

    salida = []
    for lo, hi in BANDAS:
        g = [f for f in filas if lo <= f["prob"] / 100.0 < hi]
        if len(g) < 5:
            continue
        dicho = sum(f["prob"] for f in g) / len(g)
        paso = 100.0 * sum(f["acierto"] for f in g) / len(g)
        salida.append({
            "rango": f"{int(lo*100)}-{int(hi*100)}%",
            "n": len(g),
            "dijo": round(dicho, 1),
            "paso": round(paso, 1),
            "sesgo": round(dicho - paso, 1),
        })
    return salida


def por_tema(liga_id=None, dias=90, usuario=None):
    """Acierto y calibración por familia de mercado."""
    from datetime import datetime, timedelta

    q = """SELECT tema, prob, acierto FROM predicciones
           WHERE resuelta = 1 AND creada >= ?"""
    params = [(datetime.now() - timedelta(days=dias)).isoformat()]
    if liga_id:
        q += " AND liga_id = ?"
        params.append(liga_id)
    if usuario:
        q += " AND usuario = ?"
        params.append(usuario)

    filas = almacen.consultar(q, tuple(params))
    grupos = {}
    for f in filas:
        grupos.setdefault(f["tema"], []).append(f)

    salida = []
    for tema, g in grupos.items():
        acierto = 100.0 * sum(x["acierto"] for x in g) / len(g)
        dicho = sum(x["prob"] for x in g) / len(g)
        salida.append({
            "tema": tema,
            "acierto": int(round(acierto)),
            "n": len(g),
            "nota": nota_calibracion(acierto, dicho, len(g)),
        })
    return sorted(salida, key=lambda x: -x["n"])


def nota_calibracion(acierto, dicho, n):
    """La frase que lee el admin. La escribe acá, no el front."""
    if n < 30:
        return (f"Solo {n} casos cerrados. Con esta muestra cualquier "
                "resultado es ruido.")
    sesgo = dicho - acierto
    if abs(sesgo) < 4:
        return "Bien calibrado: lo que da al 70% sale cerca del 70%."
    if sesgo > 0:
        return (f"Sobreestima por {sesgo:.0f} puntos: promete más de lo "
                "que ocurre.")
    return (f"Subestima por {abs(sesgo):.0f} puntos: pasa más seguido de "
            "lo que dice.")


def por_confianza(usuario=None, dias=365):
    """Acierto según las estrellas que tenía el partido.

    Si el modelo es honesto, cinco estrellas debe acertar bastante más
    que dos. Si no, las estrellas no significan nada.
    """
    from datetime import datetime, timedelta

    q = """SELECT confianza, acierto FROM predicciones
           WHERE resuelta = 1 AND confianza IS NOT NULL AND creada >= ?"""
    params = [(datetime.now() - timedelta(days=dias)).isoformat()]
    if usuario:
        q += " AND usuario = ?"
        params.append(usuario)

    filas = almacen.consultar(q, tuple(params))
    grupos = {}
    for f in filas:
        grupos.setdefault(int(f["confianza"]), []).append(f["acierto"])

    return [{"estrellas": e,
             "acierto": int(round(100.0 * sum(v) / len(v))),
             "n": len(v)}
            for e, v in sorted(grupos.items(), reverse=True) if len(v) >= 3]
