# Instrumento

Análisis de partidos de fútbol. Ocho temas por partido, en lenguaje
llano, sin catálogo de mercados.

## Qué hace

Toma resultados históricos de varias ligas, estima con un modelo de
Poisson bivariado (Dixon-Coles) cuántos goles, tarjetas, tiros y córners
se esperan en un partido, y lo presenta como líneas con umbral `.5`:

```
Menos de 2.5 goles      58%
Más de 4.5 tarjetas     52%
Saka: más de 0.5 tiros  68%
```

No muestra cuotas ni pide cargarlas. Dice qué tan probable es cada cosa
y cuánta información tiene el modelo para decirlo.

## Estructura

```
instrumento/
  app.py                 arranque de Flask
  config.py              claves y constantes
  requirements.txt

  datos/
    almacen.py           SQLite/Postgres, una sola interfaz
    ingesta.py           API-Football -> base
    equipos.py           normalización de nombres

  modelo/
    ajuste.py            Dixon-Coles: fuerzas de ataque y defensa
    partido.py           probabilidades de un partido
    conteo.py            tarjetas, tiros, córners, faltas
    jugadores.py         líneas por jugador según minutos
    calibracion.py       qué tan bien viene acertando

  api/
    formato.py           traduce el modelo a lo que pinta la pantalla
    publico.py           rutas del usuario
    admin.py             rutas del panel

  web/
    index.html           la interfaz
```

## Instalación

```bash
git clone <tu-repo> && cd instrumento
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export DATABASE_URL="postgresql://…-pooler….neon.tech/neondb?sslmode=require"
export API_FOOTBALL_KEY=tu-clave
export ADMIN_TOKEN=algo-largo

python -m datos.ingesta --inicial     # ~3.000 llamadas, unos 20 min
python -m modelo.ajuste --reajustar
python -m datos.ingesta --agenda
python app.py
```

Abre en `http://localhost:5000`. Sin `DATABASE_URL` usa SQLite local.

Paso a paso completo, incluido Render: ver `INSTALAR.md`.

## Actualizar los datos

```bash
python -m datos.ingesta --dia         # resultados de ayer
python -m modelo.ajuste --reajustar   # recalcula las fuerzas
```

Conviene dejarlo en un cron diario.

## Las reglas del proyecto

**Las líneas van en umbral `.5`.** Si el modelo estima 4.8 tarjetas, la
app muestra "Más de 4.5 tarjetas" con su probabilidad. El 4.8 nunca sale
del backend.

**El front no calcula ni redacta.** Los textos de resumen, explicación y
veredicto se arman en `api/formato.py`. Si algo se lee mal, se arregla
ahí.

**Cuando falta un dato, se dice.** Nada de rellenar con promedios de
liga disfrazados de estimación. Devuelve `pendiente` y la pantalla
muestra su estado vacío.

**La confianza no es la probabilidad.** Las estrellas dicen cuántos
partidos parecidos tiene el modelo, no qué tan seguro es el resultado.
