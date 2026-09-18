"""
config.py
=========
Todo lo que cambia entre entornos, en un solo lugar.
Nada de claves escritas en el código.
"""

import os
from pathlib import Path

RAIZ = Path(__file__).parent
BASE_DATOS = os.environ.get("DATABASE_URL") or str(RAIZ / "instrumento.db")

API_KEY = os.environ.get("API_FOOTBALL_KEY", "")
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")

API_BASE = "https://v3.football.api-sports.io"

# Plan Pro: 7.500 llamadas por día. Se corta antes del límite real para
# dejar margen a las actualizaciones en vivo del final del día.
PRESUPUESTO_DIARIO = int(os.environ.get("PRESUPUESTO_API", 7000))

# El plan Pro tolera 300 llamadas por minuto. 0.25 s entre llamadas deja
# 240/min: cómodo, sin arriesgar un 429.
PAUSA_API = float(os.environ.get("PAUSA_API", 0.25))


# Ligas que sigue la app. El id es el de API-Football.
LIGAS = {
    39:  {"nombre": "Premier League", "slug": "pl",  "pais": "Inglaterra"},
    140: {"nombre": "LaLiga",         "slug": "ll",  "pais": "España"},
    135: {"nombre": "Serie A",        "slug": "sa",  "pais": "Italia"},
    78:  {"nombre": "Bundesliga",     "slug": "bl",  "pais": "Alemania"},
    2:   {"nombre": "Champions League", "slug": "ch", "pais": "Europa"},
}

SLUG_A_ID = {v["slug"]: k for k, v in LIGAS.items()}


# --- Parámetros del modelo -------------------------------------------------
# Son los valores por defecto. El panel de admin los puede mover y el
# cambio se guarda en la base; ver modelo/ajuste.py.
PARAMETROS = {
    # Goles de más que se le acreditan al equipo de casa.
    "localia": 0.25,
    # Cuántos partidos hacia atrás mira el ajuste. Más partidos da
    # estimaciones más estables pero reacciona más lento.
    "ventana": 38,
    # Cuánto pesan los últimos cinco partidos sobre el promedio de
    # temporada, en porcentaje.
    "forma": 35,
    # Cuánto pesa el árbitro designado en la estimación de tarjetas.
    "arbitro": 40,
    # Penalización a los equipos con menos de tres días de descanso.
    "descanso": 15,
    # Estrellas mínimas para que un partido pase el filtro "señal alta".
    "umbral": 4,
    # Vida media en días del decaimiento temporal de Dixon-Coles.
    # Un partido de hace 180 días pesa la mitad que uno de hoy.
    "vida_media": 180,
}


# --- Textos ---------------------------------------------------------------
DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado",
        "Domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def etiqueta_fecha(d):
    """date -> 'Sábado 19 de septiembre'."""
    return f"{DIAS[d.weekday()]} {d.day} de {MESES[d.month - 1]}"


def mes_corto(d):
    """date -> 'Sep 2026'."""
    return f"{MESES[d.month - 1][:3].capitalize()} {d.year}"
