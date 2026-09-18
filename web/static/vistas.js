/* Instrumento — vistas.js
 * Cada función pinta una pantalla. El HTML sale de lo que devuelve la
 * API; acá solo se acomoda.
 */

/* --- Partidos --- */
function tiraDias() {
  const dias = [];
  for (let i = -2; i <= 4; i++) {
    const d = new Date();
    d.setDate(d.getDate() + i);
    const iso = d.toISOString().slice(0, 10);
    dias.push(`<button class="pildora" data-dia="${iso}"
      aria-pressed="${iso === estado.dia}"
      style="min-width:52px;text-align:center;border-radius:var(--rad2)">
      <div style="font-size:11px">${i === 0 ? 'Hoy'
        : ['Dom','Lun','Mar','Mié','Jue','Vie','Sáb'][d.getDay()]}</div>
      <div class="num" style="font-size:15px;font-weight:600">${d.getDate()}</div>
    </button>`);
  }
  return `<div class="tira">${dias.join('')}</div>`;
}

async function verPartidos() {
  cargando();
  let d;
  try {
    d = await pedir(`/api/partidos?fecha=${estado.dia}`);
  } catch {
    vista().innerHTML = vacio('No se pudo cargar',
      'Revisá tu conexión y volvé a intentar.',
      { accion: 'recargar', texto: 'Reintentar' });
    return;
  }

  let lista = d.partidos;
  const q = estado.busqueda.trim().toLowerCase();
  if (q) lista = lista.filter(p =>
    `${p.local} ${p.visitante} ${p.liga}`.toLowerCase().includes(q));
  if (estado.liga !== 'todas') lista = lista.filter(p => p.liga_id === estado.liga);
  if (estado.soloSenal) lista = lista.filter(p => (p.confianza || 0) >= 4);
  if (estado.soloFav) lista = lista.filter(p =>
    estado.favoritos.includes(p.local) || estado.favoritos.includes(p.visitante));

  lista.sort((a, b) => esFav(b) - esFav(a));

  vista().innerHTML = `
    <div class="titulo">
      <div class="sobretitulo">${esc(d.etiqueta)}</div>
      <h2>${d.jugados ? 'Ya jugados' : estado.dia === hoyISO()
            ? 'Partidos de hoy' : 'Próximos partidos'}</h2>
    </div>
    ${tiraDias()}
    <div style="padding:10px 18px 0">
      <input type="text" id="buscar" placeholder="Buscar equipo o liga"
             value="${esc(estado.busqueda)}">
    </div>
    <div class="tira" style="padding-top:12px">
      <button class="pildora" data-senal aria-pressed="${estado.soloSenal}">Solo señal alta</button>
      <button class="pildora" data-fav aria-pressed="${estado.soloFav}">Mis equipos</button>
    </div>
    ${lista.length ? `<div class="lista">${lista.map(tarjetaPartido).join('')}</div>`
      : d.partidos.length
        ? vacio('Ningún partido coincide',
                'Probá con otro equipo o quitá los filtros que tenés activos.',
                { accion: 'limpiar', texto: 'Quitar filtros' })
        : vacio('No hay partidos ese día',
                'Elegí otro día en la tira de fechas.',
                { accion: 'hoy', texto: 'Volver a hoy' })}`;
}

function esFav(p) {
  return estado.favoritos.includes(p.local) ||
         estado.favoritos.includes(p.visitante) ? 1 : 0;
}

function tarjetaPartido(p) {
  return `<div class="tarjeta">
    <div class="fila" style="margin-bottom:12px">
      <div class="mono chico apagado crece">${esc(p.liga)}${p.hora ? ' · ' + esc(p.hora) : ''}</div>
      ${p.confianza ? `<div class="estrellas">${estrellas(p.confianza)}</div>` : ''}
      <button class="pildora" data-favorito="${esc(p.local)}"
        style="width:30px;height:30px;padding:0;border-radius:50%"
        ${esFav(p) ? 'aria-pressed="true"' : ''}>${esFav(p) ? '★' : '☆'}</button>
    </div>
    <button style="all:unset;cursor:pointer;display:block;width:100%"
            data-partido="${esc(p.id)}">
      ${p.marcador ? `
        <div class="fila" style="justify-content:space-between">
          <div style="font-weight:600">${esc(p.local)}</div>
          <div class="num" style="font-size:20px;font-weight:600">${esc(p.marcador)}</div>
          <div style="font-weight:600;text-align:right">${esc(p.visitante)}</div>
        </div>` : `
        <div class="fila"><div class="escudo"></div>
          <div class="crece" style="font-weight:600">${esc(p.local)}</div>
          <div class="num apagado">${p.prob_local ?? '—'}%</div></div>
        <div class="fila" style="margin-top:9px"><div class="escudo"></div>
          <div class="crece" style="font-weight:600">${esc(p.visitante)}</div>
          <div class="num apagado">${p.prob_visitante ?? '—'}%</div></div>`}
      <div class="pie">${esc(p.titular)}</div>
    </button>
  </div>`;
}

/* --- Análisis --- */
async function verAnalisis() {
  cargando();
  const d = await pedir(`/api/partidos/${estado.partido}/analisis`);
  if (d.pendiente) { vista().innerHTML = volver() + pendiente(d); return; }

  vista().innerHTML = volver() + `
    <div class="titulo">
      <h2 style="font-size:27px">${esc(d.local)}<br>${esc(d.visitante)}</h2>
    </div>
    <div style="padding:18px 18px 0">
      <div class="tarjeta">
        <div class="fila" style="margin-bottom:11px">
          <div class="sobretitulo crece">Lo más destacable</div>
          <div class="estrellas">${estrellas(d.confianza)}</div>
        </div>
        <p style="margin:0;font-size:16px">${esc(d.titular)}</p>
        <div class="pie">Confianza del modelo: cuántos partidos parecidos
          tiene para estimar este.</div>
      </div>
    </div>
    <div style="padding:14px 18px 0">
      <button class="btn" data-contexto style="text-align:left;margin:0">
        <b>Contexto del partido</b>
        <div class="chico apagado" style="margin-top:4px">Árbitro, descanso,
          forma e historial entre los dos</div>
      </button>
    </div>
    <div class="lista">${d.temas.map(tema).join('')}</div>`;
}

function tema(t) {
  const abierto = estado.tema === t.id;
  return `<div class="tarjeta" style="padding:0;overflow:hidden">
    <button style="all:unset;cursor:pointer;display:block;width:100%;padding:16px"
            data-tema="${esc(t.id)}">
      <div class="fila">
        <div class="crece">
          <div style="font-weight:600">${esc(t.nombre)}</div>
          <div class="chico apagado" style="margin-top:4px">${esc(t.resumen)}</div>
        </div>
        <div class="mono chico apagado">${esc(t.signo)}</div>
      </div>
    </button>
    ${abierto ? `<div style="padding:0 16px 16px">
      ${t.por_jugador ? '<div data-jugadores></div>'
        : t.lineas.map(l => `
        <div style="margin-bottom:11px">
          <div class="fila">
            <div class="crece">${esc(l.etiqueta)}</div>
            <div class="num" style="font-weight:600">${l.prob}%</div>
            <button class="pildora" data-combi='${esc(JSON.stringify(
              { texto: l.etiqueta, prob: l.prob, partido: estado.partido }))}'
              style="width:26px;height:26px;padding:0;border-radius:50%">+</button>
          </div>
          ${barra(l.prob)}
        </div>`).join('')}
      <div class="pie">${esc(t.porque)}</div>
      <button class="pildora" data-calculo="${esc(t.id)}"
              style="margin-top:12px">${estado.calculo === t.id
                ? 'Ocultar el cálculo' : 'Cómo se calcula'}</button>
      ${estado.calculo === t.id ? `<p class="chico apagado"
        style="background:var(--suave);border-radius:11px;padding:13px;margin-top:11px">
        ${esc(t.calculo)}</p>` : ''}
      ${!t.por_jugador ? `<button class="btn" data-guardar='${esc(JSON.stringify(
        { tema: t.id, linea: t.lineas[0]?.etiqueta, prob: t.lineas[0]?.prob }))}'
        >Guardar esta predicción</button>` : ''}
    </div>` : ''}
  </div>`;
}

function volver(texto = 'Partidos') {
  return `<div style="padding:16px 18px 0">
    <button class="pildora" data-volver>‹ ${esc(texto)}</button></div>`;
}
