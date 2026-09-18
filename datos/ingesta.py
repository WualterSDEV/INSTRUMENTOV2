"""
datos/ingesta.py
================
Trae partidos y estadísticas de API-Football a la base.

    python -m datos.ingesta --inicial      histórico de tres temporadas
    python -m datos.ingesta --dia          resultados de ayer
    python -m datos.ingesta --agenda       próximos partidos

Cada fallo queda registrado en la tabla `errores`: el panel de admin los
agrupa por tipo. Un error silencioso es peor que uno ruidoso.
"""

import time
from datetime import date, datetime, timedelta

import requests

import config
from datos import almacen
from datos.equipos import canonico, id_partido

# Cómo se llama cada estadística en la API y cómo la guardamos.
CAMPOS = {
    "Yellow Cards": "tarjetas",
    "Shots on Goal": "tiros",
    "Corner Kicks": "corners",
    "Fouls": "faltas",
}


class Cliente:
    """Cliente de API-Football que cuenta lo que gasta.

    Con el plan Pro son 7.500 llamadas por día. La carga inicial de tres
    temporadas y cinco ligas usa alrededor de 3.000 si pedís las
    estadísticas partido por partido, así que entra holgada en un día.
    El presupuesto corta antes de llegar al límite para no dejar la
    cuenta seca.
    """

    def __init__(self, clave=None, pausa=None, presupuesto=None):
        self.clave = clave or config.API_KEY
        self.pausa = pausa if pausa is not None else config.PAUSA_API
        self.presupuesto = presupuesto or config.PRESUPUESTO_DIARIO
        self.usados = 0
        if not self.clave:
            raise RuntimeError("Falta API_FOOTBALL_KEY")

    def pedir(self, ruta, **params):
        if self.usados >= self.presupuesto:
            raise PresupuestoAgotado(
                f"Corté en {self.usados} llamadas para no agotar la cuota.")

        time.sleep(self.pausa)
        r = requests.get(f"{config.API_BASE}/{ruta}",
                         headers={"x-apisports-key": self.clave},
                         params=params, timeout=30)
        self.usados += 1

        if r.status_code == 429:
            raise PresupuestoAgotado("cuota de la API agotada")
        r.raise_for_status()

        j = r.json()
        if j.get("errors"):
            raise RuntimeError(str(j["errors"])[:200])
        return j

    def cuota(self):
        """Lo que dice la API, no lo que contamos nosotros."""
        try:
            j = self.pedir("status")
            req = (j.get("response") or {}).get("requests") or {}
            return {"usadas": req.get("current", 0),
                    "limite": req.get("limit_day", 0)}
        except Exception:
            return {"usadas": self.usados, "limite": self.presupuesto}


class PresupuestoAgotado(RuntimeError):
    """Se acabaron las llamadas del día. No es un error de programación:
    la carga se retoma mañana desde donde quedó."""


def _temporada(f=None):
    """La temporada europea arranca en julio."""
    f = f or date.today()
    return f.year if f.month >= 7 else f.year - 1


def _equipos_conocidos():
    filas = almacen.consultar("SELECT DISTINCT local AS e FROM partidos")
    return [f["e"] for f in filas]


def bajar_liga(cli, liga_id, temporada, desde=None, hasta=None):
    """Partidos de una liga y temporada. Devuelve cuántos guardó."""
    params = {"league": liga_id, "season": temporada}
    if desde:
        params["from"] = desde.isoformat()
    if hasta:
        params["to"] = hasta.isoformat()

    try:
        j = cli.pedir("fixtures", **params)
    except Exception as e:
        almacen.registrar_error("Fallo al bajar liga", e, "Media", liga_id)
        return 0

    conocidos = _equipos_conocidos()
    slug = config.LIGAS.get(liga_id, {}).get("slug", "xx")
    filas = []

    for fx in j.get("response", []):
        f, tt, gg = fx["fixture"], fx["teams"], fx["goals"]
        estado = (f.get("status") or {}).get("short")
        cuando = datetime.fromisoformat(f["date"].replace("Z", "+00:00"))

        local = canonico(tt["home"]["name"], conocidos) or tt["home"]["name"]
        visita = canonico(tt["away"]["name"], conocidos) or tt["away"]["name"]

        filas.append({
            "id": id_partido(cuando.date(), local, visita, slug),
            "fecha": cuando.date().isoformat(),
            "liga_id": liga_id,
            "local": local,
            "visitante": visita,
            "goles_local": gg.get("home"),
            "goles_visitante": gg.get("away"),
            "tarjetas_local": None, "tarjetas_visitante": None,
            "tiros_local": None, "tiros_visitante": None,
            "corners_local": None, "corners_visitante": None,
            "faltas_local": None, "faltas_visitante": None,
            "arbitro": f.get("referee"),
            "estado": "jugado" if estado == "FT" else
                      "vivo" if estado in ("1H", "HT", "2H", "ET", "P") else
                      "programado",
            "_fixture": f["id"],
        })

    fixtures = [(x.pop("_fixture"), x["id"]) for x in filas]
    almacen.guardar_muchos("partidos", filas)
    return fixtures


def bajar_estadisticas(cli, fixture_id, partido_id):
    """Tarjetas, tiros, córners y faltas de un partido ya jugado."""
    try:
        j = cli.pedir("fixtures/statistics", fixture=fixture_id)
    except Exception as e:
        almacen.registrar_error("Estadística faltante", e, "Baja")
        return False

    vals = {}
    for i, equipo in enumerate(j.get("response", [])):
        lado = "local" if i == 0 else "visitante"
        for s in equipo.get("statistics", []):
            campo = CAMPOS.get(s.get("type"))
            if not campo:
                continue
            v = s.get("value")
            if isinstance(v, str):
                v = v.replace("%", "")
            try:
                vals[f"{campo}_{lado}"] = int(float(v))
            except (TypeError, ValueError):
                pass

    if not vals:
        return False

    sets = ", ".join(f"{k} = ?" for k in vals)
    almacen.ejecutar(f"UPDATE partidos SET {sets} WHERE id = ?",
                     tuple(vals.values()) + (partido_id,))
    return True


def inicial(temporadas=3, con_estadisticas=True):
    """Carga el histórico. Es la corrida cara: se hace una vez.

    Con el plan Pro (7.500/día) entra completa. Si igual se corta,
    volvé a correrla: saltea los partidos que ya tienen estadísticas.
    """
    almacen.crear_tablas()
    cli = Cliente()
    actual = _temporada()
    total = 0

    try:
        for liga_id in config.LIGAS:
            nombre = config.LIGAS[liga_id]["nombre"]
            for t in range(actual - temporadas + 1, actual + 1):
                fx = bajar_liga(cli, liga_id, t)
                print(f"  {nombre} {t}: {len(fx)} partidos")
                total += len(fx)

                if con_estadisticas:
                    for fixture_id, pid in fx:
                        if _ya_tiene_estadisticas(pid):
                            continue
                        bajar_estadisticas(cli, fixture_id, pid)

    except PresupuestoAgotado as e:
        print(f"\n{e}")
        print("Volvé a correr el mismo comando mañana: retoma donde quedó.")

    print(f"\n{total} partidos guardados ({cli.usados} llamadas)")
    return total


def _ya_tiene_estadisticas(pid):
    r = almacen.uno("SELECT tarjetas_local FROM partidos WHERE id = ?", (pid,))
    return bool(r and r["tarjetas_local"] is not None)


def dia(cuando=None):
    """Resultados de un día. Para el cron diario."""
    cuando = cuando or (date.today() - timedelta(days=1))
    cli = Cliente()
    t = _temporada(cuando)
    n = 0

    for liga_id in config.LIGAS:
        fx = bajar_liga(cli, liga_id, t, desde=cuando, hasta=cuando)
        for fixture_id, pid in fx:
            if bajar_estadisticas(cli, fixture_id, pid):
                n += 1

    print(f"{n} partidos actualizados ({cli.usados} requests)")
    resolver_predicciones()
    return n


def agenda(dias=8):
    """Próximos partidos. Sin estadísticas, todavía no existen."""
    cli = Cliente()
    hoy = date.today()
    n = 0
    for liga_id in config.LIGAS:
        fx = bajar_liga(cli, liga_id, _temporada(),
                        desde=hoy, hasta=hoy + timedelta(days=dias))
        n += len(fx)
    print(f"{n} partidos en agenda ({cli.usados} requests)")
    return n


def resolver_predicciones():
    """Marca las predicciones guardadas contra lo que pasó.

    Se corre sola después de cada ingesta diaria. Sin esto, el registro
    del usuario queda lleno de predicciones eternamente pendientes.
    """
    from modelo.calibracion import evaluar_linea

    pend = almacen.consultar(
        "SELECT * FROM predicciones WHERE resuelta = 0")
    if not pend:
        return 0

    n = 0
    for p in pend:
        j = almacen.uno("SELECT * FROM partidos WHERE id = ? AND estado = ?",
                        (p["partido_id"], "jugado"))
        if not j or j["goles_local"] is None:
            continue
        ok = evaluar_linea(p["tema"], p["linea"], j)
        if ok is None:
            continue
        almacen.ejecutar(
            "UPDATE predicciones SET resuelta = 1, acierto = ? WHERE id = ?",
            (1 if ok else 0, p["id"]))
        n += 1

    if n:
        print(f"{n} predicciones resueltas")
    return n


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Ingesta de datos")
    ap.add_argument("--inicial", action="store_true",
                    help="histórico completo, tarda")
    ap.add_argument("--dia", action="store_true", help="resultados de ayer")
    ap.add_argument("--agenda", action="store_true", help="próximos partidos")
    ap.add_argument("--temporadas", type=int, default=3)
    a = ap.parse_args()

    if a.inicial:
        inicial(a.temporadas)
    elif a.dia:
        dia()
    elif a.agenda:
        agenda()
    else:
        ap.print_help()
