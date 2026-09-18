/* Instrumento — panel.js
 * Ajustes del usuario y panel de administrador.
 */

const AJUSTES_USUARIO = [
  ['llano', 'Lenguaje llano', 'Reemplaza los términos técnicos por explicaciones cortas'],
  ['ayudas', 'Ayuda al toque', 'Muestra el botón «cómo se calcula» en cada tema'],
  ['ocultar', 'Ocultar temas sin señal', 'Esconde los temas donde el modelo no ve nada'],
];

function verAjustes() {
  const f = JSON.parse(localStorage.getItem('instrumento:flags') || '{}');

  vista().innerHTML = `
    <div class="titulo"><h2>Ajustes</h2></div>
    <div class="lista">
      ${AJUSTES_USUARIO.map(([id, nombre, detalle]) => `
        <button class="tarjeta" style="text-align:left;cursor:pointer;font:inherit;color:inherit"
                data-flag="${id}">
          <div class="fila">
            <div class="crece">
              <div style="font-weight:500">${esc(nombre)}</div>
              <div class="chico apagado" style="margin-top:4px">${esc(detalle)}</div>
            </div>
            <div class="chip ${f[id] ? 'bien' : ''}">${f[id] ? 'sí' : 'no'}</div>
          </div>
        </button>`).join('')}

      <button class="tarjeta" style="text-align:left;cursor:pointer;font:inherit;color:inherit"
              data-pedir-admin>
        <div class="fila">
          <div class="crece">
            <div style="font-weight:500">Modo administrador</div>
            <div class="chico apagado" style="margin-top:4px">Estado de los
              datos, parámetros del modelo y calibración</div>
          </div>
          <div class="chip ${estado.admin ? 'bien' : ''}">${estado.admin ? 'activo' : 'clave'}</div>
        </div>
      </button>
    </div>

    <div id="caja-admin" class="oculto" style="padding:14px 18px 0">
      <div class="tarjeta">
        <div style="font-weight:600">Acceso de administrador</div>
        <p class="chico apagado" style="margin:7px 0 14px">Se valida contra
          el servidor. La clave no está en el navegador.</p>
        <input type="password" id="token-admin" placeholder="Clave">
        <p class="error oculto" id="admin-error">Clave incorrecta.</p>
        <button class="btn primario" data-entrar-admin>Entrar al panel</button>
      </div>
    </div>

    <div style="padding:20px 18px 0">
      <button class="btn" data-salir>Cerrar sesión</button>
    </div>`;
}

/* --- Panel --- */
const SECCIONES = [['datos', 'Datos'], ['modelo', 'Modelo'], ['ligas', 'Ligas'],
                   ['errores', 'Errores'], ['cambios', 'Cambios'], ['uso', 'Uso']];

async function verPanel() {
  cargando();
  const cuerpo = await {
    datos: panelDatos, modelo: panelModelo, ligas: panelLigas,
    errores: panelErrores, cambios: panelCambios, uso: panelUso,
  }[estado.sec]();

  vista().innerHTML = `
    <div class="titulo"><h2>Panel</h2></div>
    <div class="tira">
      ${SECCIONES.map(([id, n]) => `<button class="pildora" data-sec="${id}"
        aria-pressed="${estado.sec === id}">${n}</button>`).join('')}
    </div>
    ${cuerpo}`;
}

const NOMBRE_INGESTA = {
  inicial: 'Histórico inicial', dia: 'Resultados de ayer', agenda: 'Agenda',
};
let ingestaReloj = null;

async function panelDatos() {
  const [d, ing] = await Promise.all([
    pedir('/api/admin/estado'),
    pedir('/api/admin/ingesta'),
  ]);

  clearTimeout(ingestaReloj);
  if (ing.corriendo) {
    ingestaReloj = setTimeout(() => {
      if (estado.tab === 'panel' && estado.sec === 'datos') pintar();
    }, 5000);
  }

  return `<div style="padding:16px 18px 0"><div class="tarjeta">
      <div class="sobretitulo" style="margin-bottom:12px">Cargar datos</div>
      ${ing.corriendo ? `
        <div class="fila">
          <div class="punto ojo"></div>
          <div class="crece">Corriendo: ${esc(NOMBRE_INGESTA[ing.que] || ing.que)}</div>
        </div>
        <p class="chico apagado" style="margin:8px 0 0">Empezó a las
          ${esc((ing.empezo || '').slice(11, 16))}. Podés seguir usando el
          panel, esto corre en el servidor.</p>`
      : `
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <button class="btn" data-ingesta="inicial">Histórico inicial</button>
          <button class="btn" data-ingesta="dia">Resultados de ayer</button>
          <button class="btn" data-ingesta="agenda">Agenda</button>
        </div>
        ${ing.termino ? `<p class="chico apagado" style="margin:10px 0 0">
          Última corrida (${esc(NOMBRE_INGESTA[ing.que] || ing.que)}): ${
            ing.error ? `error — ${esc(ing.error)}`
                      : `${ing.resultado ?? 0} partidos, ${esc((ing.termino || '').slice(0, 16))}`
          }</p>` : ''}
        <p class="chico apagado" style="margin:10px 0 0">El histórico inicial
          tarda unos 20 minutos y usa ~3.000 llamadas de la API. Si se corta,
          volvé a correrlo: retoma donde quedó.</p>`}
    </div></div>

    <div style="padding:10px 18px 0" class="lista">${d.map(e => `
    <div class="tarjeta" style="padding:14px 16px">
      <div class="fila">
        <div class="punto ${e.ok ? 'bien' : 'ojo'}"></div>
        <div class="crece">
          <div style="font-weight:600">${esc(e.nombre)}</div>
          <div class="chico apagado" style="margin-top:3px">${esc(e.detalle)}</div>
        </div>
        <div class="mono chico apagado">${esc(e.valor)}</div>
      </div>
    </div>`).join('')}</div>`;
}

async function panelModelo() {
  const [params, cal, ver] = await Promise.all([
    pedir('/api/admin/parametros'),
    pedir(`/api/admin/calibracion?liga=${estado.calibLiga || 'todas'}&periodo=${encodeURIComponent(estado.periodo || '90 días')}`),
    pedir('/api/admin/versiones'),
  ]);

  return `<div style="padding:16px 18px 0"><div class="tarjeta">
      <div class="sobretitulo" style="margin-bottom:16px">Parámetros</div>
      ${params.map(p => `<div style="margin-bottom:18px">
        <div class="fila" style="margin-bottom:8px">
          <div class="crece">${esc(p.nombre)}</div>
          <div class="num" style="font-weight:600">${p.valor}</div>
        </div>
        <input type="range" data-param="${esc(p.id)}" value="${p.valor}"
               min="${rangoDe(p.id)[0]}" max="${rangoDe(p.id)[1]}"
               step="${rangoDe(p.id)[2]}">
      </div>`).join('')}
      <p class="chico apagado" style="margin:0">Cada cambio queda registrado
        en Cambios y se puede deshacer.</p>
    </div></div>

    <div style="padding:10px 18px 0"><div class="tarjeta">
      <div class="sobretitulo" style="margin-bottom:12px">Calibración por tema</div>
      ${cal.por_tema.length ? cal.por_tema.map(t => `
        <div style="margin-bottom:14px">
          <div class="fila">
            <div class="crece">${esc(t.tema)}</div>
            <div class="num" style="font-weight:600">${t.acierto}%</div>
            <div class="chico apagado">${t.n}</div>
          </div>
          ${barra(t.acierto)}
          <div class="chico apagado" style="margin-top:6px">${esc(t.nota)}</div>
        </div>`).join('')
        : '<p class="chico apagado" style="margin:0">Sin predicciones resueltas todavía.</p>'}
    </div></div>

    <div style="padding:10px 18px 0"><div class="tarjeta">
      <div class="sobretitulo" style="margin-bottom:12px">Versión del modelo</div>
      <p style="margin:0">En producción: <b>${esc(ver.publicada)}</b></p>
      <button class="btn" data-publicar="${ver.publicada === 'v1' ? 'v2' : 'v1'}">
        ${ver.publicada === 'v1' ? 'Publicar v2' : 'Volver a v1'}</button>
    </div></div>`;
}

function rangoDe(id) {
  return {
    localia: [0, 0.6, 0.05], ventana: [10, 60, 2], forma: [0, 100, 5],
    arbitro: [0, 100, 5], descanso: [0, 100, 5], umbral: [1, 5, 1],
    vida_media: [60, 400, 10],
  }[id] || [0, 100, 1];
}

async function panelLigas() {
  const d = await pedir('/api/admin/ligas');
  return `<div class="lista">${d.map(l => `
    <div class="tarjeta" style="padding:15px 16px">
      <div class="fila">
        <div class="crece">
          <div style="font-weight:600">${esc(l.nombre)}</div>
          <div class="chico apagado" style="margin-top:3px">${esc(l.detalle)}</div>
        </div>
        <button class="pildora" data-liga="${esc(l.id)}"
                aria-pressed="${l.activa}">${l.activa ? 'activa' : 'apagada'}</button>
      </div>
      <div class="fila" style="margin-top:13px">
        <div class="chico apagado crece">Calidad de los datos</div>
        <div class="num chico" style="font-weight:600">${l.calidad}%</div>
      </div>
      ${barra(l.calidad)}
    </div>`).join('')}</div>`;
}

async function panelErrores() {
  const d = await pedir('/api/admin/errores');
  if (!d.length) return vacio('Sin errores registrados',
    'Cuando la ingesta falle, vas a verlo acá agrupado por tipo.');
  return `<div class="lista">${d.map(e => `
    <div class="tarjeta" style="padding:15px 16px">
      <div class="fila">
        <div class="punto ${e.gravedad === 'Alta' ? 'mal'
          : e.gravedad === 'Media' ? 'ojo' : ''}"></div>
        <div class="crece" style="font-weight:600">${esc(e.tipo)}</div>
        <div class="num" style="font-size:16px;font-weight:600">${e.veces}</div>
        <button class="pildora" data-resolver="${esc(e.tipo)}"
                aria-pressed="${e.resuelto}">${e.resuelto ? 'resuelto' : 'marcar'}</button>
      </div>
      <div class="chico apagado" style="margin-top:9px;padding-left:20px">
        ${esc(e.detalle || '')}</div>
      <div class="chico apagado" style="margin-top:7px;padding-left:20px">
        Último: ${esc(e.ultimo || '—')} · ${esc(e.gravedad)}</div>
    </div>`).join('')}</div>`;
}

async function panelCambios() {
  const d = await pedir('/api/admin/bitacora');
  if (!d.length) return vacio('Sin cambios registrados',
    'Cuando muevas un parámetro, queda acá con quién y cuándo.');
  return `<div class="lista">${d.map(c => `
    <div class="tarjeta" style="padding:14px 16px">
      <div class="fila">
        <div class="crece" style="font-weight:600">${esc(c.que)}</div>
        <div class="mono chico apagado">${esc((c.cuando || '').slice(0, 16))}</div>
      </div>
      <div class="fila" style="margin-top:9px;gap:9px">
        <div class="num chico apagado" style="text-decoration:line-through">${esc(c.antes)}</div>
        <div class="chico apagado">→</div>
        <div class="num" style="font-weight:600">${esc(c.despues)}</div>
      </div>
      <div class="fila" style="margin-top:9px">
        <div class="chico apagado crece">${esc(c.quien)}</div>
        ${c.deshecho ? '<div class="chip">deshecho</div>'
          : `<button class="pildora" data-deshacer="${c.id}">Deshacer</button>`}
      </div>
    </div>`).join('')}</div>`;
}

async function panelUso() {
  const d = await pedir('/api/admin/uso');
  return `<div style="display:grid;grid-template-columns:1fr 1fr;gap:9px;padding:16px 18px 0">
      ${d.resumen.map(r => `<div class="tarjeta" style="padding:15px 14px">
        <div class="num" style="font-size:21px;font-weight:600">${esc(r.valor)}</div>
        <div class="chico apagado" style="margin-top:5px">${esc(r.etiqueta)}</div>
      </div>`).join('')}
    </div>
    ${d.temas.length ? bloqueBarras('Temas más guardados',
      d.temas.map(t => ({ nombre: esc(t.nombre), pct: t.pct }))) : ''}`;
}
