/* Instrumento — acciones.js
 * Un solo manejador para todos los clics. Cada botón declara qué hace
 * con un atributo data-*; acá se resuelve.
 */

async function alClic(e) {
  const b = e.target.closest('[data-dia],[data-partido],[data-tema],[data-calculo],' +
    '[data-favorito],[data-combi],[data-quitar-combi],[data-guardar],[data-borrar],' +
    '[data-volver],[data-contexto],[data-vivo],[data-senal],[data-fav],[data-accion],' +
    '[data-sec],[data-liga],[data-resolver],[data-deshacer],[data-publicar],' +
    '[data-flag],[data-pedir-admin],[data-entrar-admin],[data-salir],[data-jugador]');
  if (!b) return;
  const d = b.dataset;

  /* navegación */
  if (d.dia) { estado.dia = d.dia; return pintar(); }
  if (d.partido) {
    estado.partido = d.partido;
    estado.tema = estado.calculo = estado.equipo = estado.jugador = null;
    return pintar();
  }
  if (d.vivo) { estado.vivo = d.vivo; return pintar(); }
  if ('volver' in d) {
    if (estado.contexto) { estado.contexto = false; return pintar(); }
    estado.partido = estado.vivo = null;
    return pintar();
  }
  if ('contexto' in d) { estado.contexto = true; return verContexto(); }
  if (d.tema) {
    estado.tema = estado.tema === d.tema ? null : d.tema;
    estado.calculo = null;
    return pintar();
  }
  if (d.calculo) {
    estado.calculo = estado.calculo === d.calculo ? null : d.calculo;
    return pintar();
  }

  /* filtros */
  if ('senal' in d) { estado.soloSenal = !estado.soloSenal; return pintar(); }
  if ('fav' in d) { estado.soloFav = !estado.soloFav; return pintar(); }
  if (d.accion === 'limpiar') {
    Object.assign(estado, { busqueda: '', soloSenal: false, soloFav: false,
                            liga: 'todas' });
    return pintar();
  }
  if (d.accion === 'hoy') { estado.dia = hoyISO(); return pintar(); }
  if (d.accion === 'recargar') return pintar();

  /* favoritos */
  if (d.favorito) {
    estado.favoritos = await pedir('/api/favoritos', {
      method: 'POST', body: JSON.stringify({ equipo: d.favorito }) });
    return pintar();
  }

  /* combinada */
  if (d.combi) {
    const l = JSON.parse(d.combi);
    const i = estado.combi.findIndex(x => x.texto === l.texto);
    if (i >= 0) estado.combi.splice(i, 1); else estado.combi.push(l);
    return pintar();
  }
  if (d.quitarCombi) {
    estado.combi.splice(Number(d.quitarCombi), 1);
    return pintar();
  }

  /* predicciones */
  if (d.guardar) {
    const g = JSON.parse(d.guardar);
    const r = await fetch('/api/predicciones', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...g, partido_id: estado.partido }) });
    if (r.status === 403) {
      const j = await r.json();
      b.textContent = j.error;
      return;
    }
    b.textContent = '✓ Guardado en mi registro';
    return;
  }
  if (d.borrar) {
    await pedir(`/api/predicciones/${d.borrar}`, { method: 'DELETE' });
    return pintar();
  }

  /* ajustes */
  if (d.flag) {
    const f = JSON.parse(localStorage.getItem('instrumento:flags') || '{}');
    f[d.flag] = !f[d.flag];
    localStorage.setItem('instrumento:flags', JSON.stringify(f));
    return pintar();
  }
  if ('pedirAdmin' in d) {
    if (estado.admin) {
      estado.admin = false;
      estado.token = null;
      $('[data-tab="panel"]').classList.add('oculto');
      if (estado.tab === 'panel') estado.tab = 'ajustes';
      return pintar();
    }
    return $('#caja-admin').classList.toggle('oculto');
  }
  if ('entrarAdmin' in d) {
    estado.token = $('#token-admin').value.trim();
    try {
      await pedir('/api/admin/estado');
      estado.admin = true;
      $('[data-tab="panel"]').classList.remove('oculto');
      estado.tab = 'panel';
      return pintar();
    } catch {
      estado.token = null;
      return $('#admin-error').classList.remove('oculto');
    }
  }
  if ('salir' in d) {
    localStorage.removeItem('instrumento:sesion');
    location.reload();
    return;
  }

  /* panel */
  if (d.sec) { estado.sec = d.sec; return pintar(); }
  if (d.liga) {
    await pedir('/api/admin/ligas', { method: 'PUT',
      body: JSON.stringify({ id: d.liga,
                             activa: b.getAttribute('aria-pressed') !== 'true' }) });
    return pintar();
  }
  if (d.resolver) {
    await pedir('/api/admin/errores/resolver', { method: 'POST',
      body: JSON.stringify({ tipo: d.resolver }) });
    return pintar();
  }
  if (d.deshacer) {
    await pedir(`/api/admin/bitacora/${d.deshacer}/deshacer`, { method: 'POST' });
    return pintar();
  }
  if (d.publicar) {
    await pedir(`/api/admin/versiones/${d.publicar}/publicar`, { method: 'POST' });
    return pintar();
  }
}

/* --- entradas de texto y sliders --- */
let reloj = null;

function alEscribir(e) {
  const t = e.target;

  if (t.id === 'buscar') {
    clearTimeout(reloj);
    estado.busqueda = t.value;
    reloj = setTimeout(pintar, 250);
    return;
  }

  if (t.dataset.param) {
    clearTimeout(reloj);
    const id = t.dataset.param;
    const v = Number(t.value);
    reloj = setTimeout(async () => {
      await pedir('/api/admin/parametros', { method: 'PUT',
        body: JSON.stringify({ [id]: v }) });
      pintar();
    }, 400);
  }
}

/* --- Contexto del partido --- */
async function verContexto() {
  cargando();
  const d = await pedir(`/api/partidos/${estado.partido}/contexto`);
  if (d.pendiente) { vista().innerHTML = volver('Análisis') + pendiente(d); return; }

  vista().innerHTML = volver('Análisis') + `
    <div class="titulo"><h2 style="font-size:27px">Contexto</h2></div>

    <div style="padding:18px 18px 0"><div class="tarjeta">
      <div class="sobretitulo" style="margin-bottom:13px">Árbitro</div>
      <div style="font-weight:600">${esc(d.arbitro.nombre)}</div>
      <p class="chico apagado" style="margin:6px 0 0">${esc(d.arbitro.nota)}</p>
    </div></div>

    <div style="padding:10px 18px 0"><div class="tarjeta">
      <div class="sobretitulo" style="margin-bottom:13px">Forma reciente</div>
      ${d.forma.map(f => `<div class="fila" style="margin-bottom:12px">
        <div class="crece" style="font-weight:600">${esc(f.equipo)}</div>
        <div style="display:flex;gap:5px">${f.ultimos.map(l => `
          <span class="chip ${l === 'G' ? 'bien' : l === 'P' ? 'mal' : ''}"
                style="width:22px;text-align:center;padding:4px 0">${l}</span>`).join('')}</div>
      </div>`).join('')}
      <div class="pie">Últimos cinco partidos, del más viejo al más reciente.</div>
    </div></div>

    <div style="padding:10px 18px 0"><div class="tarjeta">
      <div class="sobretitulo" style="margin-bottom:13px">Descanso</div>
      ${d.descanso.map(x => `<div class="fila" style="margin-bottom:11px">
        <div class="crece">${esc(x.equipo)}</div>
        <div class="num" style="font-weight:600">${x.dias != null ? x.dias + ' días' : '—'}</div>
        <div class="chip ${x.corto ? 'ojo' : ''}">${x.corto ? 'poco descanso' : 'normal'}</div>
      </div>`).join('')}
    </div></div>

    <div style="padding:10px 18px 0"><div class="tarjeta">
      <div class="sobretitulo" style="margin-bottom:13px">Historial entre los dos</div>
      ${d.h2h.length ? d.h2h.map(h => `<div class="fila" style="margin-bottom:12px">
        <div class="mono chico apagado" style="width:62px;flex:none">${esc(h.fecha)}</div>
        <div class="num" style="font-weight:600">${esc(h.marcador)}</div>
        <div class="chico apagado crece" style="text-align:right">${esc(h.detalle)}</div>
      </div>`).join('') : '<p class="chico apagado" style="margin:0">Sin cruces recientes.</p>'}
      <div class="pie">${esc(d.h2h_nota)}</div>
    </div></div>`;
}
