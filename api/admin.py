"""
api/admin.py
============
Panel de administrador. La clave sale de ADMIN_TOKEN, nunca del código.

Todo cambio de parámetro queda en la bitácora con quién y cuándo, y se
puede deshacer. Un panel que no registra lo que tocás es un panel que
no sirve cuando algo se rompe.
"""

import threading
from datetime import datetime
from functools import wraps

from flask import Blueprint, jsonify, request

import config
from datos import almacen

MODOS_INGESTA = ("inicial", "dia", "agenda")

admin = Blueprint("admin", __name__, url_prefix="/api/admin")

NOMBRES = {
    "localia": "Ventaja de localía",
    "ventana": "Partidos que mira atrás",
    "forma": "Peso de la forma reciente",
    "arbitro": "Peso del árbitro en tarjetas",
    "descanso": "Ajuste por descanso",
    "umbral": "Umbral de señal alta",
    "vida_media": "Vida media del decaimiento",
}


def solo_admin(f):
    @wraps(f)
    def envoltorio(*a, **kw):
        if not config.ADMIN_TOKEN:
            return jsonify({"error": "ADMIN_TOKEN no configurado en el "
                                     "servidor"}), 503
        if request.headers.get("X-Admin-Token") != config.ADMIN_TOKEN:
            return jsonify({"error": "no autorizado"}), 401
        return f(*a, **kw)
    return envoltorio


def _quien():
    return request.headers.get("X-Admin-Usuario", "admin")


def _anotar(tipo, que, antes, despues):
    almacen.ejecutar(
        """INSERT INTO bitacora (cuando, tipo, que, antes, despues, quien)
           VALUES (?,?,?,?,?,?)""",
        (datetime.now().isoformat(timespec="seconds"), tipo, que,
         str(antes), str(despues), _quien()))


# --- Estado de los datos ---------------------------------------------------
@admin.route("/estado")
@solo_admin
def estado():
    ultimo = almacen.uno(
        "SELECT MAX(fecha) AS f FROM partidos WHERE estado = 'jugado'")
    ajustado = almacen.leer_ajuste("ajustado")
    n = almacen.uno("SELECT COUNT(*) AS n FROM partidos")
    sin_stats = almacen.uno(
        """SELECT COUNT(*) AS n FROM partidos
           WHERE estado = 'jugado' AND tarjetas_local IS NULL""")

    apagadas = set(almacen.leer_ajuste("ligas_apagadas") or [])
    activas = len(config.LIGAS) - len(apagadas)

    return jsonify([
        {"nombre": "Resultados cargados",
         "detalle": f"{n['n']} partidos en la base",
         "valor": ultimo["f"] or "—",
         "ok": bool(ultimo["f"])},
        {"nombre": "Último reajuste del modelo",
         "detalle": "Se recalcula con cada ingesta diaria",
         "valor": (ajustado or "nunca")[:16],
         "ok": bool(ajustado)},
        {"nombre": "Ligas activas",
         "detalle": ", ".join(v["nombre"] for k, v in config.LIGAS.items()
                              if str(k) not in apagadas),
         "valor": f"{activas} / {len(config.LIGAS)}",
         "ok": activas == len(config.LIGAS)},
        {"nombre": "Partidos sin estadísticas",
         "detalle": "Se bajan aparte del resultado; si son muchos, revisar",
         "valor": str(sin_stats["n"]),
         "ok": sin_stats["n"] < 20},
    ])


# --- Ingesta de datos -------------------------------------------------------
# Corre en un hilo aparte: la carga inicial tarda ~20 minutos y gunicorn
# corta la request a los 120s. El estado se guarda en la base (tabla
# ajustes) y no en memoria, porque Render puede repartir las requests
# entre varios workers y cada uno tiene la suya.
def _estado_ingesta():
    return almacen.leer_ajuste("ingesta_estado", {"corriendo": False})


@admin.route("/ingesta", methods=["GET", "POST"])
@solo_admin
def ingesta():
    if request.method == "GET":
        return jsonify(_estado_ingesta())

    modo = (request.get_json(force=True) or {}).get("modo")
    if modo not in MODOS_INGESTA:
        return jsonify({"error": "modo inválido: usar inicial, dia o agenda"}), 400
    if _estado_ingesta().get("corriendo"):
        return jsonify({"error": "ya hay una ingesta corriendo"}), 409

    ahora = datetime.now().isoformat(timespec="seconds")
    almacen.escribir_ajuste("ingesta_estado", {
        "corriendo": True, "que": modo, "empezo": ahora,
        "termino": None, "resultado": None, "error": None})

    def _correr():
        from datos import ingesta as mod_ingesta
        from modelo.ajuste import reajustar_todo

        try:
            if modo == "inicial":
                n = mod_ingesta.inicial()
                reajustar_todo(verbose=False)
            elif modo == "dia":
                n = mod_ingesta.dia()
                reajustar_todo(verbose=False)
            else:
                n = mod_ingesta.agenda()
            error = None
        except Exception as e:
            n, error = None, str(e)[:300]
            almacen.registrar_error("Ingesta manual falló", e, "Alta")

        almacen.escribir_ajuste("ingesta_estado", {
            "corriendo": False, "que": modo, "empezo": ahora,
            "termino": datetime.now().isoformat(timespec="seconds"),
            "resultado": n, "error": error})

    threading.Thread(target=_correr, daemon=True).start()
    return jsonify({"ok": True, "corriendo": True, "que": modo})


# --- Calibración -----------------------------------------------------------
PERIODOS = {"30 días": 30, "90 días": 90, "Temporada": 365}


@admin.route("/calibracion")
@solo_admin
def calibracion():
    from modelo.calibracion import calibracion as cal, por_tema

    dias = PERIODOS.get(request.args.get("periodo", "90 días"), 90)
    slug = request.args.get("liga")
    liga_id = config.SLUG_A_ID.get(slug) if slug and slug != "todas" else None

    return jsonify({
        "por_tema": por_tema(liga_id=liga_id, dias=dias),
        "bandas": cal(liga_id=liga_id, dias=dias),
    })


# --- Parámetros del modelo -------------------------------------------------
@admin.route("/parametros", methods=["GET", "PUT"])
@solo_admin
def parametros():
    actual = almacen.parametros()

    if request.method == "GET":
        return jsonify([
            {"id": k, "nombre": NOMBRES.get(k, k), "valor": v,
             "defecto": config.PARAMETROS[k]}
            for k, v in actual.items()])

    nuevos = request.get_json(force=True)
    guardados = dict(almacen.leer_ajuste("parametros") or {})

    for k, v in nuevos.items():
        if k not in config.PARAMETROS or actual[k] == v:
            continue
        _anotar("parametro", NOMBRES.get(k, k), actual[k], v)
        guardados[k] = v

    almacen.escribir_ajuste("parametros", guardados)
    return jsonify(almacen.parametros())


@admin.route("/bitacora")
@solo_admin
def bitacora():
    filas = almacen.consultar(
        "SELECT * FROM bitacora ORDER BY id DESC LIMIT 60")
    return jsonify([{
        "id": f["id"], "que": f["que"], "antes": f["antes"],
        "despues": f["despues"], "quien": f["quien"],
        "cuando": f["cuando"], "deshecho": bool(f["deshecho"]),
        "tipo": f["tipo"],
    } for f in filas])


@admin.route("/bitacora/<int:bid>/deshacer", methods=["POST"])
@solo_admin
def deshacer(bid):
    b = almacen.uno("SELECT * FROM bitacora WHERE id = ? AND deshecho = 0",
                    (bid,))
    if not b:
        return jsonify({"error": "no existe o ya se deshizo"}), 404

    if b["tipo"] == "parametro":
        clave = next((k for k, n in NOMBRES.items() if n == b["que"]), None)
        if clave:
            g = dict(almacen.leer_ajuste("parametros") or {})
            g[clave] = float(b["antes"]) if "." in b["antes"] else int(b["antes"])
            almacen.escribir_ajuste("parametros", g)
    elif b["tipo"] == "version":
        almacen.escribir_ajuste("version_modelo", b["antes"])
    elif b["tipo"] == "liga":
        apagadas = set(almacen.leer_ajuste("ligas_apagadas") or [])
        if b["antes"] == "activa":
            apagadas.discard(b["que"])
        else:
            apagadas.add(b["que"])
        almacen.escribir_ajuste("ligas_apagadas", sorted(apagadas))

    almacen.ejecutar("UPDATE bitacora SET deshecho = 1 WHERE id = ?", (bid,))
    return jsonify({"ok": True})


# --- Ligas -----------------------------------------------------------------
@admin.route("/ligas", methods=["GET", "PUT"])
@solo_admin
def ligas():
    apagadas = set(almacen.leer_ajuste("ligas_apagadas") or [])

    if request.method == "PUT":
        d = request.get_json(force=True)
        lid = str(d["id"])
        antes = "apagada" if lid in apagadas else "activa"
        if d.get("activa"):
            apagadas.discard(lid)
        else:
            apagadas.add(lid)
        almacen.escribir_ajuste("ligas_apagadas", sorted(apagadas))
        _anotar("liga", lid, antes,
                "activa" if d.get("activa") else "apagada")

    return jsonify([{
        "id": str(lid),
        "nombre": v["nombre"],
        "activa": str(lid) not in apagadas,
        "calidad": _calidad(lid),
        "detalle": _detalle(lid),
    } for lid, v in config.LIGAS.items()])


CAMPOS = ["tarjetas_local", "tiros_local", "corners_local", "faltas_local"]


def _calidad(liga_id):
    """Porcentaje de partidos con las estadísticas completas."""
    r = almacen.uno(
        f"""SELECT COUNT(*) AS total,
                   SUM(CASE WHEN {' IS NOT NULL AND '.join(CAMPOS)} IS NOT NULL
                       THEN 1 ELSE 0 END) AS completos
            FROM partidos WHERE liga_id = ? AND estado = 'jugado'""",
        (liga_id,))
    if not r or not r["total"]:
        return 0
    return int(round(100 * (r["completos"] or 0) / r["total"]))


def _detalle(liga_id):
    q = _calidad(liga_id)
    arb = almacen.uno(
        """SELECT COUNT(*) AS n FROM partidos
           WHERE liga_id = ? AND arbitro IS NOT NULL""", (liga_id,))
    if q >= 95:
        return "Datos completos"
    if q >= 85:
        return "Faltan campos sueltos"
    if not arb or arb["n"] == 0:
        return "Sin historial de árbitros"
    return "Datos incompletos: el modelo estima con poco"


# --- Errores ---------------------------------------------------------------
@admin.route("/errores")
@solo_admin
def errores():
    """Agrupados por tipo, con cuántas veces pasó cada uno."""
    filas = almacen.consultar(
        """SELECT tipo, gravedad, COUNT(*) AS veces, MAX(cuando) AS ultimo,
                  MAX(detalle) AS detalle, MAX(resuelto) AS resuelto
           FROM errores GROUP BY tipo, gravedad""")
    orden = {"Alta": 0, "Media": 1, "Baja": 2}
    return jsonify(sorted([{
        "tipo": f["tipo"], "gravedad": f["gravedad"], "veces": f["veces"],
        "ultimo": f["ultimo"], "detalle": f["detalle"],
        "resuelto": bool(f["resuelto"]),
    } for f in filas], key=lambda x: (orden.get(x["gravedad"], 3),
                                      -x["veces"])))


@admin.route("/errores/resolver", methods=["POST"])
@solo_admin
def resolver_error():
    tipo = request.get_json(force=True)["tipo"]
    r = almacen.uno("SELECT MAX(resuelto) AS r FROM errores WHERE tipo = ?",
                    (tipo,))
    nuevo = 0 if (r and r["r"]) else 1
    almacen.ejecutar("UPDATE errores SET resuelto = ? WHERE tipo = ?",
                     (nuevo, tipo))
    return jsonify({"resuelto": bool(nuevo)})


# --- Versiones del modelo --------------------------------------------------
@admin.route("/versiones", methods=["GET"])
@solo_admin
def versiones():
    return jsonify({
        "publicada": almacen.leer_ajuste("version_modelo", "v1"),
        "comparacion": almacen.leer_ajuste("comparacion_versiones") or [],
    })


@admin.route("/versiones/<v>/publicar", methods=["POST"])
@solo_admin
def publicar(v):
    if v not in ("v1", "v2"):
        return jsonify({"error": "versión inválida"}), 400
    antes = almacen.leer_ajuste("version_modelo", "v1")
    almacen.escribir_ajuste("version_modelo", v)
    _anotar("version", "Versión del modelo", antes, v)
    return jsonify({"publicada": v})


# --- Uso -------------------------------------------------------------------
@admin.route("/uso")
@solo_admin
def uso():
    guardadas = almacen.consultar(
        """SELECT tema, COUNT(*) AS n FROM predicciones
           GROUP BY tema ORDER BY n DESC""")
    total = sum(g["n"] for g in guardadas) or 1
    usuarios = almacen.uno(
        "SELECT COUNT(DISTINCT usuario) AS n FROM predicciones")

    return jsonify({
        "resumen": [
            {"valor": str(usuarios["n"] if usuarios else 0),
             "etiqueta": "usuarios con predicciones"},
            {"valor": str(total), "etiqueta": "predicciones guardadas"},
        ],
        "temas": [{"nombre": g["tema"],
                   "pct": int(round(100 * g["n"] / total))}
                  for g in guardadas[:6]],
    })
