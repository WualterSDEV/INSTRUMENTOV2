"""
datos/almacen.py
================
Una sola forma de hablar con la base, funcione en SQLite (tu máquina) o
Postgres/Neon (producción). El resto del código no sabe cuál es.

Neon corta las conexiones ociosas: por eso cada operación abre y cierra
la suya en vez de mantener un pool abierto. Con el tráfico de esta app
el costo es despreciable y evita el clásico "server closed the
connection unexpectedly" después de unos minutos sin uso.
"""

import json
import sqlite3
from contextlib import contextmanager

import config

ES_POSTGRES = str(config.BASE_DATOS).startswith(("postgres://",
                                                 "postgresql://"))

# Lo único que cambia entre dialectos.
SERIAL = "SERIAL PRIMARY KEY" if ES_POSTGRES else \
         "INTEGER PRIMARY KEY AUTOINCREMENT"

ESQUEMA = f"""
CREATE TABLE IF NOT EXISTS partidos (
    id            TEXT PRIMARY KEY,
    fecha         TEXT NOT NULL,
    hora          TEXT,
    liga_id       INTEGER NOT NULL,
    local         TEXT NOT NULL,
    visitante     TEXT NOT NULL,
    goles_local       INTEGER,
    goles_visitante   INTEGER,
    tarjetas_local    INTEGER,
    tarjetas_visitante INTEGER,
    tiros_local       INTEGER,
    tiros_visitante   INTEGER,
    corners_local     INTEGER,
    corners_visitante INTEGER,
    faltas_local      INTEGER,
    faltas_visitante  INTEGER,
    minuto        INTEGER,
    arbitro       TEXT,
    fixture_id    INTEGER,
    estado        TEXT DEFAULT 'jugado'
);
CREATE INDEX IF NOT EXISTS idx_partido_fecha ON partidos(fecha);
CREATE INDEX IF NOT EXISTS idx_partido_liga  ON partidos(liga_id);
CREATE INDEX IF NOT EXISTS idx_partido_estado ON partidos(estado);

CREATE TABLE IF NOT EXISTS fuerzas (
    equipo     TEXT PRIMARY KEY,
    liga_id    INTEGER,
    ataque     REAL NOT NULL,
    defensa    REAL NOT NULL,
    n_partidos INTEGER NOT NULL,
    ajustado   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasas (
    equipo     TEXT NOT NULL,
    campo      TEXT NOT NULL,
    por_90     REAL NOT NULL,
    concede    REAL,
    n_partidos INTEGER NOT NULL,
    PRIMARY KEY (equipo, campo)
);

CREATE TABLE IF NOT EXISTS arbitros (
    nombre       TEXT PRIMARY KEY,
    tarjetas_p90 REAL NOT NULL,
    faltas_p90   REAL,
    n_partidos   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS predicciones (
    id         {SERIAL},
    usuario    TEXT NOT NULL,
    creada     TEXT NOT NULL,
    partido_id TEXT NOT NULL,
    fecha      TEXT NOT NULL,
    liga_id    INTEGER,
    local      TEXT NOT NULL,
    visitante  TEXT NOT NULL,
    tema       TEXT NOT NULL,
    linea      TEXT NOT NULL,
    prob       INTEGER NOT NULL,
    confianza  INTEGER,
    resuelta   INTEGER DEFAULT 0,
    acierto    INTEGER
);
CREATE INDEX IF NOT EXISTS idx_pred_usuario ON predicciones(usuario);

CREATE TABLE IF NOT EXISTS ajustes (
    clave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bitacora (
    id       {SERIAL},
    cuando   TEXT NOT NULL,
    tipo     TEXT NOT NULL,
    que      TEXT,
    antes    TEXT,
    despues  TEXT,
    quien    TEXT,
    deshecho INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS errores (
    id       {SERIAL},
    cuando   TEXT NOT NULL,
    tipo     TEXT NOT NULL,
    gravedad TEXT DEFAULT 'Baja',
    detalle  TEXT,
    liga_id  INTEGER,
    resuelto INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_error_tipo ON errores(tipo);
"""


def _url_neon(url):
    """Neon exige SSL y conviene usar el endpoint con pooler.

    Si pegaste la 'Direct connection' en vez de la 'Pooled', esto no la
    cambia: solo agrega el sslmode que falta. Para producción usá la
    pooled, que termina en `-pooler` antes del dominio.
    """
    if "sslmode=" not in url:
        url += ("&" if "?" in url else "?") + "sslmode=require"
    return url


def _conectar():
    if ES_POSTGRES:
        import psycopg2
        import psycopg2.extras
        return psycopg2.connect(_url_neon(config.BASE_DATOS),
                                connect_timeout=10,
                                cursor_factory=psycopg2.extras.DictCursor)
    con = sqlite3.connect(config.BASE_DATOS, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


@contextmanager
def conexion():
    con = _conectar()
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def _sql(q):
    """SQLite usa ?, Postgres usa %s."""
    return q.replace("?", "%s") if ES_POSTGRES else q


def _cursor(con):
    return con.cursor() if ES_POSTGRES else con


def crear_tablas():
    with conexion() as con:
        cur = _cursor(con)
        for sentencia in ESQUEMA.split(";"):
            if sentencia.strip():
                cur.execute(sentencia)


def ejecutar(q, params=()):
    with conexion() as con:
        cur = _cursor(con)
        cur.execute(_sql(q), params)
        return cur.rowcount


def consultar(q, params=()):
    """Lista de dicts. Nunca None."""
    with conexion() as con:
        cur = _cursor(con)
        cur.execute(_sql(q), params)
        filas = cur.fetchall()
        if not filas:
            return []
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, f)) for f in filas]


def uno(q, params=()):
    r = consultar(q, params)
    return r[0] if r else None


def guardar_muchos(tabla, filas, clave=None):
    """Inserta o actualiza. `filas` es una lista de dicts homogéneos.

    En una sola conexión y una sola transacción: con Neon, abrir una
    conexión por fila haría que la carga inicial tardara horas.
    """
    if not filas:
        return 0

    cols = list(filas[0])
    clave = clave or cols[0]
    hueco = ", ".join(["?"] * len(cols))

    if ES_POSTGRES:
        resto = [c for c in cols if c != clave]
        q = (f"INSERT INTO {tabla} ({', '.join(cols)}) VALUES ({hueco}) "
             f"ON CONFLICT ({clave}) DO UPDATE SET "
             + ", ".join(f"{c} = EXCLUDED.{c}" for c in resto))
    else:
        q = f"INSERT OR REPLACE INTO {tabla} ({', '.join(cols)}) VALUES ({hueco})"

    datos = [tuple(f[c] for c in cols) for f in filas]

    with conexion() as con:
        cur = _cursor(con)
        if ES_POSTGRES:
            from psycopg2.extras import execute_batch
            execute_batch(cur, _sql(q), datos, page_size=200)
        else:
            cur.executemany(q, datos)

    return len(filas)


# --- Ajustes clave-valor ---------------------------------------------------
def leer_ajuste(clave, defecto=None):
    r = uno("SELECT valor FROM ajustes WHERE clave = ?", (clave,))
    if not r:
        return defecto
    try:
        return json.loads(r["valor"])
    except (ValueError, TypeError):
        return r["valor"]


def escribir_ajuste(clave, valor):
    v = json.dumps(valor)
    if ES_POSTGRES:
        ejecutar("""INSERT INTO ajustes (clave, valor) VALUES (?, ?)
                    ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor""",
                 (clave, v))
    else:
        ejecutar("INSERT OR REPLACE INTO ajustes (clave, valor) VALUES (?, ?)",
                 (clave, v))


def parametros():
    """Los del config, pisados por lo que haya cambiado el admin."""
    return {**config.PARAMETROS, **(leer_ajuste("parametros") or {})}


# --- Errores ---------------------------------------------------------------
def registrar_error(tipo, detalle="", gravedad="Baja", liga_id=None):
    """Todo fallo pasa por acá. El panel los agrupa por tipo.

    Nunca lanza: un error al registrar un error no puede tumbar la
    ingesta.
    """
    from datetime import datetime
    try:
        ejecutar("""INSERT INTO errores (cuando, tipo, gravedad, detalle, liga_id)
                    VALUES (?, ?, ?, ?, ?)""",
                 (datetime.now().isoformat(timespec="seconds"), tipo,
                  gravedad, str(detalle)[:400], liga_id))
    except Exception as e:
        print(f"  [no pude registrar el error] {e}")


def salud():
    """Para /salud y el panel: ¿responde la base y qué tiene?"""
    try:
        n = uno("SELECT COUNT(*) AS n FROM partidos")
        ultimo = uno("SELECT MAX(fecha) AS f FROM partidos "
                     "WHERE estado = 'jugado'")
        return {"ok": True,
                "motor": "postgres" if ES_POSTGRES else "sqlite",
                "partidos": n["n"] if n else 0,
                "ultimo_resultado": ultimo["f"] if ultimo else None}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}
