"""
app.py
======
Arranque. Nada de lógica acá: solo registra las rutas y sirve la
interfaz.

    python app.py                  desarrollo
    gunicorn app:app               producción
"""

import os

from flask import Flask, render_template, send_from_directory

import config
from api.admin import admin
from api.publico import publico
from datos import almacen

app = Flask(__name__, template_folder="web", static_folder="web/static")
app.secret_key = os.environ.get("SECRET_KEY", "cambiar-en-produccion")

app.register_blueprint(publico)
app.register_blueprint(admin)


@app.route("/")
def inicio():
    return render_template("index.html")


@app.route("/salud")
def salud():
    """Para el health check de Render y para ver si Neon responde."""
    s = almacen.salud()
    return (s, 200) if s["ok"] else (s, 503)


@app.errorhandler(404)
def no_encontrado(_):
    return {"error": "no existe esa ruta"}, 404


@app.errorhandler(500)
def error_interno(e):
    almacen.registrar_error("Error del servidor", e, "Alta")
    return {"error": "algo se rompió; quedó registrado"}, 500


def preparar():
    """Crea las tablas si no están. Idempotente."""
    try:
        almacen.crear_tablas()
    except Exception as e:
        print(f"No pude preparar la base: {e}")
        print("Revisá DATABASE_URL: en Neon usá la cadena *pooled*.")
        return
    if not config.API_KEY:
        print("Aviso: falta API_FOOTBALL_KEY, la ingesta no va a funcionar.")
    if not config.ADMIN_TOKEN:
        print("Aviso: falta ADMIN_TOKEN, el panel va a devolver 503.")


preparar()


if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
