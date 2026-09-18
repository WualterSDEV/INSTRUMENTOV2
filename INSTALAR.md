# Instalar Instrumento

Paso a paso, desde cero hasta la app andando. Toma unos 20 minutos, más
lo que tarde la primera carga de datos.

---

## Antes de empezar

Necesitás tres cosas:

1. **Python 3.11 o más nuevo.** Comprobá con `python --version`.
2. **Tu clave de API-Football** (plan Pro, 7.500 llamadas por día).
3. **Tu base de Neon** y **tu cuenta de Render**.

---

## 1. La base en Neon

En el panel de Neon, entrá a tu proyecto → **Connection Details**.

Vas a ver dos cadenas. Copiá la **Pooled connection**, la que tiene
`-pooler` antes del dominio:

```
postgresql://usuario:clave@ep-algo-pooler.region.aws.neon.tech/neondb?sslmode=require
```

Usá la pooled, no la directa. Render levanta varios procesos y Neon
cierra las conexiones ociosas; con la directa vas a ver caídas
intermitentes que cuesta diagnosticar.

No hace falta crear tablas a mano: la app las crea sola al arrancar.

---

## 2. Correr en tu computadora

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Claves:

```bash
export DATABASE_URL="la-cadena-pooled-de-neon"
export API_FOOTBALL_KEY=tu-clave
export ADMIN_TOKEN=inventá-algo-largo
export SECRET_KEY=otra-cosa-larga
```

En Windows con PowerShell:

```powershell
$env:DATABASE_URL="la-cadena-pooled"
$env:API_FOOTBALL_KEY="tu-clave"
$env:ADMIN_TOKEN="algo-largo"
$env:SECRET_KEY="otra-cosa"
```

Si no ponés `DATABASE_URL`, usa un archivo SQLite local. Sirve para
probar sin tocar Neon.

---

## 3. Cargar los datos

```bash
python -m datos.ingesta --inicial
```

Tres temporadas de las cinco ligas, con estadísticas partido por
partido. Usa alrededor de **3.000 llamadas** de tus 7.500, así que entra
en un día. Tarda unos 20 minutos por la pausa entre llamadas.

El proceso corta solo al llegar a 7.000 para dejarte margen. Si se
corta, volvé a correr el mismo comando: saltea lo que ya bajó.

Después, ajustá el modelo:

```bash
python -m modelo.ajuste --reajustar
```

Calcula fuerzas de ataque y defensa, tasas de tarjetas y córners, y el
perfil de cada árbitro. Un par de minutos, sin usar la API.

Por último, la agenda:

```bash
python -m datos.ingesta --agenda
```

---

## 4. Levantar la app

```bash
python app.py
```

Abrí `http://localhost:5000`. Entrá con cualquier correo y contraseña, o
como invitado.

Para ver el panel: Ajustes → Modo administrador → escribí el valor de
`ADMIN_TOKEN`.

---

## 5. Mantener los datos al día

Todos los días hay que traer los resultados nuevos y reajustar:

```bash
python -m datos.ingesta --dia
python -m modelo.ajuste --reajustar
```

El primer comando también resuelve solo las predicciones guardadas: si
guardaste "menos de 2.5 goles" y el partido terminó 1-0, queda marcada
como acertada.

Para tener la agenda de los próximos días:

```bash
python -m datos.ingesta --agenda
```

---

## 6. Publicar en Render

Subí el repo a GitHub primero:

```bash
cd instrumento
git init && git add . && git commit -m "Primera versión"
git branch -M main
git remote add origin https://github.com/TU-USUARIO/instrumento.git
git push -u origin main
```

En Render: **New → Blueprint**, apuntá a ese repo. El archivo
`render.yaml` define tres servicios:

- **instrumento** — el sitio.
- **instrumento-diario** — 6:00 UTC: resultados de ayer y reajuste.
- **instrumento-agenda** — 6:30 UTC: próximos partidos.

Render te va a pedir tres variables, las mismas para los tres servicios:

| Variable | Valor |
|---|---|
| `DATABASE_URL` | la cadena **pooled** de Neon |
| `API_FOOTBALL_KEY` | tu clave |
| `ADMIN_TOKEN` | la clave del panel |

`SECRET_KEY` se genera sola.

Después del primer despliegue, abrí **Shell** en el servicio web y
cargá los datos una vez:

```bash
python -m datos.ingesta --inicial && python -m modelo.ajuste --reajustar
python -m datos.ingesta --agenda
```

Si tu plan de Render es Free, el servicio se duerme tras 15 minutos sin
tráfico y la primera visita tarda medio minuto en despertar. Los cron
jobs andan igual.

### Cuánta cuota gastan los cron

Con cinco ligas: el diario usa unas 40 llamadas, la agenda unas 5. Te
quedan más de 7.400 libres para el uso normal y para volver a cargar
histórico si hace falta.

---

## Problemas frecuentes

**"server closed the connection unexpectedly"**
Estás usando la cadena directa de Neon en vez de la pooled. Cambiá
`DATABASE_URL` por la que tiene `-pooler` en el dominio.

**"SSL connection has been closed unexpectedly"**
Lo mismo, o a la cadena le falta `?sslmode=require`. El código lo agrega
solo, pero si tu cadena trae otros parámetros raros, ponelo a mano.

**"password authentication failed"**
Neon rota la contraseña si regenerás las credenciales. Copiá la cadena
de nuevo desde Connection Details.

**La primera consulta del día tarda mucho**
Neon suspende la base cuando no se usa. El primer pedido la despierta en
unos segundos. Es del plan gratuito de Neon, no de la app.

**"Corté en 7000 llamadas para no agotar la cuota"**
No es un error. Volvé a correr el comando: retoma donde quedó. Si querés
cambiar el tope, poné `PRESUPUESTO_API` en las variables de entorno.

**"cuota de la API agotada"**
Esta sí viene de API-Football: pasaste las 7.500. Espera a mañana. Los
fallos quedan registrados en el panel, sección Errores.

**La app abre pero no hay partidos**
Faltó `python -m datos.ingesta --agenda`. Tenés el histórico pero no los
partidos que vienen.

**Los temas dicen "el modelo todavía no tiene datos"**
Faltó `python -m modelo.ajuste --reajustar`, o hay menos de 30 partidos
de esos equipos en la base.

**El panel devuelve 503**
No configuraste `ADMIN_TOKEN` en Render.

**Un equipo aparece dos veces con nombres parecidos**
La normalización no lo resolvió. Agregalo al diccionario `ALIAS` de
`datos/equipos.py` y volvé a ajustar.

---

## Cómo está armado

```
app.py            arranca Flask, registra las rutas, no tiene lógica
config.py         ligas, parámetros por defecto, claves

datos/
  almacen.py      única forma de hablar con la base
  ingesta.py      trae datos de la API
  equipos.py      normaliza nombres de equipo

modelo/
  ajuste.py       Dixon-Coles: fuerzas de ataque y defensa
  partido.py      probabilidades de un partido concreto
  jugadores.py    líneas por jugador según minutos esperados
  calibracion.py  si el modelo acierta lo que promete

api/
  formato.py      único lugar donde se escribe texto y se arman líneas .5
  publico.py      rutas de la app
  admin.py        rutas del panel

web/
  index.html      la pantalla
  static/         estilos y JavaScript
```

Las cuatro reglas del proyecto, para cuando lo modifiques:

**Las líneas van en umbral `.5`.** Si el modelo estima 4.8 tarjetas, la
app muestra "Más de 4.5 tarjetas". El 4.8 nunca sale del backend.

**El front no calcula ni redacta.** Todos los textos se escriben en
`api/formato.py`. Si algo se lee mal, se arregla ahí.

**Cuando falta un dato, se dice.** Nada de rellenar con promedios de
liga disfrazados de estimación.

**La confianza no es la probabilidad.** Las estrellas dicen cuántos
partidos parecidos tiene el modelo, no qué tan seguro está.
