"""
datos/equipos.py
================
Los nombres de equipo llegan distintos según la fuente: "Man City",
"Manchester City", "Man. City". Si no se normalizan, el modelo cree que
son tres equipos distintos y cada uno con un tercio de los partidos.
"""

import re
import unicodedata
from difflib import SequenceMatcher

# Casos que el emparejamiento automático no resuelve bien.
ALIAS = {
    "man city": "Manchester City",
    "man utd": "Manchester United",
    "man united": "Manchester United",
    "spurs": "Tottenham",
    "wolves": "Wolverhampton",
    "nottm forest": "Nottingham Forest",
    "sheffield weds": "Sheffield Wednesday",
    "atletico madrid": "Atlético Madrid",
    "ath madrid": "Atlético Madrid",
    "ath bilbao": "Athletic Club",
    "athletic bilbao": "Athletic Club",
    "real sociedad": "Real Sociedad",
    "betis": "Real Betis",
    "celta": "Celta de Vigo",
    "inter": "Inter",
    "internazionale": "Inter",
    "ac milan": "Milan",
    "bayern munich": "Bayern München",
    "bayern": "Bayern München",
    "dortmund": "Borussia Dortmund",
    "m'gladbach": "Borussia Mönchengladbach",
    "leverkusen": "Bayer Leverkusen",
    "psg": "Paris Saint-Germain",
    "paris sg": "Paris Saint-Germain",
}


def limpiar(nombre):
    """'Atlético Madrid' -> 'atletico madrid'. Para comparar, no mostrar."""
    if not nombre:
        return ""
    s = unicodedata.normalize("NFKD", str(nombre))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().strip()
    s = re.sub(r"\b(fc|cf|afc|sc|ac|ss|as|rc|cd|ud|club|de|the)\b", " ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def canonico(nombre, conocidos=None, umbral=0.86):
    """El nombre oficial de un equipo.

    Si `conocidos` está, busca el más parecido entre los que ya hay en
    la base. Devuelve None si no se parece a ninguno: mejor no emparejar
    que emparejar mal.
    """
    clave = limpiar(nombre)
    if not clave:
        return None

    if clave in ALIAS:
        return ALIAS[clave]

    if not conocidos:
        return str(nombre).strip()

    mapa = {limpiar(e): e for e in conocidos}
    if clave in mapa:
        return mapa[clave]

    mejor, punta = None, 0.0
    for k, v in mapa.items():
        s = SequenceMatcher(None, clave, k).ratio()
        if s > punta:
            mejor, punta = v, s
    return mejor if punta >= umbral else None


def nombre_corto(nombre):
    """'Virgil van Dijk' -> 'Van Dijk'. Lo que entra en el círculo."""
    partes = str(nombre).split()
    if len(partes) <= 1:
        return nombre
    particula = partes[-2].lower()
    if particula in ("van", "de", "del", "da", "di", "dos", "mac", "mc"):
        return f"{partes[-2].capitalize()} {partes[-1]}"
    return partes[-1]


def id_partido(fecha, local, visitante, liga_slug="xx"):
    """Identificador estable y legible: pl-arsenal-liverpo-20260919."""
    def corto(s):
        return re.sub(r"[^a-z0-9]", "", limpiar(s))[:8]
    f = str(fecha)[:10].replace("-", "")
    return f"{liga_slug}-{corto(local)}-{corto(visitante)}-{f}"
