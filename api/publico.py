"""
api/publico.py
==============
Las rutas que consume la app. Ninguna hace cálculo: piden al modelo,
pasan por api/formato.py y devuelven JSON listo para pintar.
"""

from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, request, session

import config
from api import formato as fmt
from datos import almacen
from datos.equipos import id_partido
from modelo import partido as mod

publico = Blueprint("publico", __name__, url_prefix="/api")


def _usuario():
    return session.get("usuario", "invitado")


def _liga(liga_id):
    return config.LIGAS.get(liga_id, {"nombre": "—", "slug": "xx"})


# --- Partidos --------------------------------------------------------------
@publico.route("/partidos")
def partidos():
    """?fecha=2026-09-19 — por defecto hoy. Días pasados traen resultado."""
    try:
        f = (datetime.strptime(request.args["fecha"], "%Y-%m-%d").date()
             if request.args.get("fecha") else date.today())
    except ValueError:
        return jsonify({"error": "fecha inválida"}), 400

    apagadas = set(almacen.leer_ajuste("ligas_apagadas") or [])
    filas = almacen.consultar(
        "SELECT * FROM partidos WHERE fecha = ? ORDER BY liga_id",
        (f.isoformat(),))
    filas = [p for p in filas if str(p["liga_id"]) not in apagadas]

    pasado = f < date.today()
    salida = [(_tarjeta_jugada(p) if pasado else _tarjeta(p)) for p in filas]

    return jsonify({
        "fecha": f.isoformat(),
        "etiqueta": config.etiqueta_fecha(f),
        "jugados": pasado,
        "partidos": [s for s in salida if s],
    })


def _tarjeta(p):
    m = mod.mercados(p["local"], p["visitante"])
    conf = fmt.estrellas(m["n_partidos"] if m else 0, bool(p["arbitro"]))
    liga = _liga(p["liga_id"])
    return {
        "id": p["id"],
        "liga": liga["nombre"],
        "liga_id": liga["slug"],
        "hora": p.get("hora", ""),
        "local": p["local"],
        "visitante": p["visitante"],
        "prob_local": fmt.pct(m["prob_local"]) if m else None,
        "prob_visitante": fmt.pct(m["prob_visitante"]) if m else None,
        "confianza": conf,
        "titular": fmt.titular_lista(m, conf, p["local"], p["visitante"]),
    }


def _tarjeta_jugada(p):
    if p["goles_local"] is None:
        return None
    temas = _temas_jugados(p)
    liga = _liga(p["liga_id"])
    return {
        "id": p["id"],
        "liga": liga["nombre"],
        "liga_id": liga["slug"],
        "local": p["local"],
        "visitante": p["visitante"],
        "marcador": f"{int(p['goles_local'])} — {int(p['goles_visitante'])}",
        "confianza": None,
        "titular": (f"Terminó {int(p['goles_local'])} — "
                    f"{int(p['goles_visitante'])}. "
                    + fmt.resumen_jugado(temas)),
    }


@publico.route("/partidos/<pid>/analisis")
def analisis(pid):
    """Los ocho temas, armados y en umbrales .5."""
    p = almacen.uno("SELECT * FROM partidos WHERE id = ?", (pid,))
    if not p:
        return jsonify(fmt.pendiente("No encontré ese partido.")), 404

    m = mod.mercados(p["local"], p["visitante"])
    if not m:
        return jsonify(fmt.pendiente(
            "El modelo todavía no tiene datos de estos equipos."))

    arb = mod.factor_arbitro(p["arbitro"])
    temas = [
        fmt.tema_resultado(m, p["local"], p["visitante"]),
        fmt.tema_goles(m),
        fmt.tema_ambos(m),
    ]

    for tid in ("tarjetas", "tiros", "corners", "faltas"):
        c = mod.conteo_esperado(p["local"], p["visitante"], tid, p["arbitro"])
        if c:
            t = fmt.tema_conteo(tid, c["total"], arb)
            if t:
                temas.append(t)

    temas.append(fmt.tema_jugadores())

    conf = fmt.estrellas(m["n_partidos"], bool(p["arbitro"]))
    return jsonify({
        "id": pid,
        "local": p["local"],
        "visitante": p["visitante"],
        "confianza": conf,
        "titular": fmt.titular(temas, conf, p["local"], p["visitante"]),
        "temas": temas,
    })


def _temas_jugados(p):
    """Qué dijo el modelo y qué pasó, para un partido terminado."""
    from modelo.calibracion import evaluar_linea

    m = mod.mercados(p["local"], p["visitante"])
    if not m:
        return []

    candidatas = [
        ("goles", "Menos de 2.5 goles", fmt.pct(m["prob_menos_2.5"])),
        ("ambos", "Ambos marcan", fmt.pct(m["prob_btts"])),
        ("resultado", f"Gana {p['local']}", fmt.pct(m["prob_local"])),
    ]

    c = mod.conteo_esperado(p["local"], p["visitante"], "tarjetas",
                            p["arbitro"])
    if c:
        u = fmt.umbral_bajo(c["total"])
        candidatas.append(("tarjetas", f"Más de {u:.1f} tarjetas",
                           fmt.pct(mod.prob_mas_de(c["total"], u))))

    out = []
    for tema, linea, prob in candidatas:
        ok = evaluar_linea(tema, linea, p)
        if ok is not None:
            out.append({"tema": linea, "prob": prob, "ok": ok})
    return out


@publico.route("/partidos/<pid>/resultado")
def resultado(pid):
    p = almacen.uno("SELECT * FROM partidos WHERE id = ?", (pid,))
    if not p or p["goles_local"] is None:
        return jsonify(fmt.pendiente("Todavía no hay resultado cargado."))
    return jsonify({
        "marcador": f"{int(p['goles_local'])} — {int(p['goles_visitante'])}",
        "temas": _temas_jugados(p),
        "nota": fmt.nota_jugado(),
    })


# --- Contexto --------------------------------------------------------------
@publico.route("/partidos/<pid>/contexto")
def contexto(pid):
    p = almacen.uno("SELECT * FROM partidos WHERE id = ?", (pid,))
    if not p:
        return jsonify(fmt.pendiente("No encontré ese partido.")), 404

    return jsonify({
        "arbitro": {
            "nombre": p["arbitro"] or "Sin designar",
            "nota": fmt.nota_arbitro(mod.factor_arbitro(p["arbitro"]),
                                     p["arbitro"]),
        },
        "descanso": [_descanso(p["local"], p["fecha"]),
                     _descanso(p["visitante"], p["fecha"])],
        "h2h": _h2h(p["local"], p["visitante"], p["fecha"]),
        "h2h_nota": fmt.h2h_nota(_h2h(p["local"], p["visitante"], p["fecha"])),
        "forma": [_forma(p["local"], p["fecha"]),
                  _forma(p["visitante"], p["fecha"])],
    })


def _descanso(equipo, hasta):
    r = almacen.uno(
        """SELECT fecha FROM partidos
           WHERE (local = ? OR visitante = ?) AND fecha < ? AND estado='jugado'
           ORDER BY fecha DESC LIMIT 1""", (equipo, equipo, hasta))
    if not r:
        return {"equipo": equipo, "dias": None, "corto": False}
    d = (datetime.fromisoformat(hasta[:10]).date()
         - datetime.fromisoformat(r["fecha"][:10]).date()).days
    return {"equipo": equipo, "dias": d, "corto": d < 4}


def _h2h(local, visitante, hasta, n=5):
    filas = almacen.consultar(
        """SELECT * FROM partidos
           WHERE ((local = ? AND visitante = ?) OR (local = ? AND visitante = ?))
                 AND fecha < ? AND estado = 'jugado'
           ORDER BY fecha DESC LIMIT ?""",
        (local, visitante, visitante, local, hasta, n))

    out = []
    for f in filas:
        gl, gv = int(f["goles_local"]), int(f["goles_visitante"])
        det = []
        if f["tarjetas_local"] is not None:
            det.append(f"{int(f['tarjetas_local']) + int(f['tarjetas_visitante'])} tarjetas")
        if f["corners_local"] is not None:
            det.append(f"{int(f['corners_local']) + int(f['corners_visitante'])} córners")
        out.append({
            "fecha": config.mes_corto(datetime.fromisoformat(f["fecha"][:10])),
            "marcador": f"{gl} — {gv}",
            "total_goles": gl + gv,
            "detalle": " · ".join(det) or "—",
        })
    return out


def _forma(equipo, hasta, n=5):
    """Los últimos cinco: G, E o P. Del más viejo al más reciente."""
    filas = almacen.consultar(
        """SELECT local, visitante, goles_local, goles_visitante
           FROM partidos
           WHERE (local = ? OR visitante = ?) AND fecha < ? AND estado='jugado'
           ORDER BY fecha DESC LIMIT ?""", (equipo, equipo, hasta, n))

    letras = []
    for f in reversed(filas):
        gl, gv = int(f["goles_local"]), int(f["goles_visitante"])
        propio, rival = (gl, gv) if f["local"] == equipo else (gv, gl)
        letras.append("G" if propio > rival else "P" if propio < rival else "E")
    return {"equipo": equipo, "ultimos": letras}


# --- En vivo ---------------------------------------------------------------
@publico.route("/vivo")
def vivo():
    filas = almacen.consultar(
        "SELECT * FROM partidos WHERE estado = 'vivo' ORDER BY liga_id")
    out = []
    for p in filas:
        gl = int(p["goles_local"] or 0)
        gv = int(p["goles_visitante"] or 0)
        out.append({
            "id": p["id"],
            "minuto": p.get("minuto", ""),
            "liga": _liga(p["liga_id"])["nombre"],
            "local": p["local"],
            "visitante": p["visitante"],
            "marcador": f"{gl} — {gv}",
        })
    return jsonify(out)


CAMPOS_VIVO = [("Goles", "goles"), ("Tiros al arco", "tiros"),
               ("Tarjetas", "tarjetas"), ("Córners", "corners"),
               ("Faltas", "faltas")]


@publico.route("/vivo/<pid>")
def vivo_detalle(pid):
    """Real contra lo proyectado A ESE MINUTO, no al final."""
    p = almacen.uno("SELECT * FROM partidos WHERE id = ?", (pid,))
    if not p:
        return jsonify(fmt.pendiente("No encontré ese partido.")), 404

    minuto = int(request.args.get("minuto", p.get("minuto") or 45))
    fraccion = min(1.0, max(0.05, minuto / 90.0))
    m = mod.mercados(p["local"], p["visitante"])

    filas = []
    for nombre, campo in CAMPOS_VIVO:
        if campo == "goles":
            real = int(p["goles_local"] or 0) + int(p["goles_visitante"] or 0)
            total = m["goles_esperados"] if m else None
        else:
            a, b = p[f"{campo}_local"], p[f"{campo}_visitante"]
            real = int(a or 0) + int(b or 0)
            c = mod.conteo_esperado(p["local"], p["visitante"], campo,
                                    p["arbitro"])
            total = c["total"] if c else None
        if total is None:
            continue
        esp = fmt.umbral_bajo(total * fraccion)
        filas.append({"nombre": nombre, "real": real, "esperado": esp,
                      "estado": fmt.estado_vivo(real, esp)})

    return jsonify({
        "veredicto": fmt.veredicto_vivo(filas),
        "filas": filas,
        "predicho": _predicho(p, m, minuto),
    })


def _predicho(p, m, minuto):
    """Lo que el modelo había dicho antes, y cómo va."""
    if not m:
        return []
    goles = int(p["goles_local"] or 0) + int(p["goles_visitante"] or 0)
    dos = (p["goles_local"] or 0) > 0 and (p["goles_visitante"] or 0) > 0
    quedan = max(0, 90 - minuto)

    return [
        {"tema": "Menos de 2.5 goles", "prob": fmt.pct(m["prob_menos_2.5"]),
         "estado": ("perdiendo" if goles >= 3 else
                    "acertando" if quedan < 15 else "en juego")},
        {"tema": "Ambos marcan", "prob": fmt.pct(m["prob_btts"]),
         "estado": ("acertando" if dos else
                    "perdiendo" if quedan < 10 else "en juego")},
    ]


# --- Predicciones guardadas ------------------------------------------------
@publico.route("/predicciones", methods=["GET", "POST"])
def predicciones():
    u = _usuario()

    if request.method == "POST":
        if u == "invitado":
            return jsonify({"error": "Entrá con tu cuenta para guardar "
                                     "predicciones."}), 403
        d = request.get_json(force=True)
        p = almacen.uno("SELECT * FROM partidos WHERE id = ?",
                        (d["partido_id"],))
        if not p:
            return jsonify({"error": "partido inexistente"}), 400

        almacen.ejecutar(
            """INSERT INTO predicciones
               (usuario, creada, partido_id, fecha, liga_id, local,
                visitante, tema, linea, prob, confianza)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (u, datetime.now().isoformat(timespec="seconds"), p["id"],
             p["fecha"], p["liga_id"], p["local"], p["visitante"],
             d["tema"], d["linea"], int(d["prob"]), d.get("confianza")))
        return jsonify({"ok": True}), 201

    filas = almacen.consultar(
        "SELECT * FROM predicciones WHERE usuario = ? ORDER BY id DESC", (u,))
    return jsonify([{
        "id": f["id"],
        "tema": f["tema"],
        "linea": f["linea"],
        "prob": f["prob"],
        "partido": f"{f['local']} — {f['visitante']}",
        "ok": None if not f["resuelta"] else bool(f["acierto"]),
    } for f in filas])


@publico.route("/predicciones/<int:pid>", methods=["DELETE"])
def borrar_prediccion(pid):
    almacen.ejecutar("DELETE FROM predicciones WHERE id = ? AND usuario = ?",
                     (pid, _usuario()))
    return "", 204


@publico.route("/predicciones/resumen")
def resumen_predicciones():
    from modelo.calibracion import por_confianza, por_tema
    u = _usuario()
    return jsonify({
        "por_tema": por_tema(usuario=u, dias=365),
        "por_confianza": por_confianza(usuario=u),
    })


# --- Favoritos -------------------------------------------------------------
@publico.route("/favoritos", methods=["GET", "POST"])
def favoritos():
    clave = f"favoritos:{_usuario()}"
    actual = almacen.leer_ajuste(clave) or []

    if request.method == "POST":
        eq = request.get_json(force=True)["equipo"]
        if eq in actual:
            actual.remove(eq)
        else:
            actual.append(eq)
        almacen.escribir_ajuste(clave, actual)

    return jsonify(actual)


# --- Combinada -------------------------------------------------------------
@publico.route("/combinada", methods=["POST"])
def combinada():
    """Probabilidad conjunta de varias líneas, y si se contradicen.

    Dos líneas del mismo partido no son independientes: multiplicar sin
    más miente. Acá al menos se avisa.
    """
    d = request.get_json(force=True)
    lineas = d.get("lineas", [])
    if not lineas:
        return jsonify({"prob": None, "aviso": None})

    conjunta = 1.0
    for l in lineas:
        conjunta *= int(l["prob"]) / 100.0

    return jsonify({
        "prob": int(round(conjunta * 100)),
        "aviso": _aviso_combinada(lineas),
        "nota": ("Cuantas más líneas sumás, más baja la probabilidad de "
                 "que salgan todas juntas."),
    })


CONTRARIAS = [("menos de 2.5 goles", "ambos marcan"),
              ("menos de 1.5 goles", "ambos marcan"),
              ("menos de 2.5 goles", "más de 2.5 goles")]


def _aviso_combinada(lineas):
    por_partido = {}
    for l in lineas:
        por_partido.setdefault(l.get("partido", ""), []).append(
            l["texto"].lower())

    for partido, textos in por_partido.items():
        for a, b in CONTRARIAS:
            if any(a in t for t in textos) and any(b in t for t in textos):
                return (f"En {partido} elegiste dos líneas que se pelean "
                        "entre sí: es difícil que salgan las dos.")
        if len(textos) > 1:
            return (f"Las líneas de {partido} son del mismo partido: "
                    "suelen pasar juntas, así que la probabilidad real es "
                    "más alta que la que se muestra.")
    return None
