/* Instrumento — vistas2.js
 * En vivo, combinar, registro, ajustes y panel.
 */

/* --- En vivo --- */
async function verVivo() {
  cargando();
  const d = await pedir('/api/vivo');
  vista().innerHTML = `
    <div class="titulo"><h2>En vivo</h2>
      <p class="chico apagado">Partidos jugándose ahora. El modelo se
        actualiza con lo que va pasando.</p></div>
    ${d.length ? `<div class="lista">${d.map(v => `
      <button class="tarjeta" style="text-align:left;cursor:pointer;font:inherit;color:inherit"
              data-vivo="${esc(v.id)}">
        <div class="fila" style="margin-bottom:13px">
          <div class="punto mal"></div>
          <div class="mono chico apagado">${esc(v.minuto)} · ${esc(v.liga)}</div>
        </div>
        <div class="fila" style="justify-content:space-between">
          <div style="font-weight:600">${esc(v.local)}</div>
          <div class="num" style="font-size:20px;font-weight:600">${esc(v.marcador)}</div>
          <div style="font-weight:600;text-align:right">${esc(v.visitante)}</div>
        </div>
      </button>`).join('')}</div>`
      : vacio('No hay partidos en vivo',
              'Volvé cuando haya alguno en juego.')}`;
}

async function verVivoDetalle() {
  cargando();
  const d = await pedir(`/api/vivo/${estado.vivo}`);
  if (d.pendiente) { vista().innerHTML = volver('En vivo') + pendiente(d); return; }

  vista().innerHTML = volver('En vivo') + `
    <div style="padding:18px 18px 0">
      <div class="tarjeta">
        <div class="sobretitulo" style="margin-bottom:11px">¿Va como dijo el modelo?</div>
        <p style="margin:0;font-size:16px">${esc(d.veredicto)}</p>
      </div>
    </div>
    <div class="lista">
      ${d.filas.map(f => `<div class="tarjeta">
        <div class="fila">
          <div class="crece" style="font-weight:600">${esc(f.nombre)}</div>
          <div class="chip ${f.estado === 'por encima' ? 'ojo'
            : f.estado === 'por debajo' ? '' : 'bien'}">${esc(f.estado)}</div>
        </div>
        <div class="fila" style="gap:18px;align-items:flex-end;margin-top:13px">
          <div><div class="num" style="font-size:21px;font-weight:600">${f.real}</div>
            <div class="chico apagado">ahora</div></div>
          <div><div class="num apagado" style="font-size:21px;font-weight:600">${f.esperado}</div>
            <div class="chico apagado">esperado a este minuto</div></div>
        </div>
      </div>`).join('')}
    </div>
    ${d.predicho.length ? `<div style="padding:14px 18px 0"><div class="tarjeta">
      <div class="sobretitulo" style="margin-bottom:13px">Lo que había dicho el modelo</div>
      ${d.predicho.map(p => `<div class="fila" style="margin-bottom:12px">
        <div class="crece">${esc(p.tema)}</div>
        <div class="num" style="font-weight:600">${p.prob}%</div>
        <div class="chip ${p.estado === 'acertando' ? 'bien'
          : p.estado === 'perdiendo' ? 'mal' : ''}">${esc(p.estado)}</div>
      </div>`).join('')}
    </div></div>` : ''}`;
}

/* --- Combinar --- */
async function verCombinar() {
  let conjunta = null;
  if (estado.combi.length) {
    conjunta = await pedir('/api/combinada', {
      method: 'POST',
      body: JSON.stringify({ lineas: estado.combi }),
    });
  }

  vista().innerHTML = `
    <div class="titulo"><h2>Combinar</h2>
      <p class="chico apagado">Sumá líneas desde cualquier tema del análisis
        y mirá la probabilidad conjunta.</p></div>
    <div style="padding:18px 18px 0"><div class="tarjeta">
      <div class="fila" style="margin-bottom:13px">
        <div class="sobretitulo crece">Mi combinada</div>
        <div class="num" style="font-size:18px;font-weight:600;color:var(--acc)">
          ${conjunta?.prob != null ? conjunta.prob + '%' : '—'}</div>
      </div>
      ${estado.combi.length ? estado.combi.map((m, i) => `
        <div class="fila" style="margin-bottom:10px">
          <div class="crece">${esc(m.texto)}</div>
          <div class="num chico apagado">${m.prob}%</div>
          <button class="pildora" data-quitar-combi="${i}"
            style="width:26px;height:26px;padding:0;border-radius:50%">×</button>
        </div>`).join('')
        : '<p class="chico apagado" style="margin:0">Todavía no agregaste ninguna línea.</p>'}
      ${conjunta?.aviso ? `<div class="pie" style="color:var(--alerta)">
        ${esc(conjunta.aviso)}</div>` : ''}
      ${conjunta?.nota ? `<div class="pie">${esc(conjunta.nota)}</div>` : ''}
    </div></div>`;
}

/* --- Registro --- */
async function verRegistro() {
  cargando();
  const [preds, resumen] = await Promise.all([
    pedir('/api/predicciones'),
    pedir('/api/predicciones/resumen'),
  ]);

  vista().innerHTML = `
    <div class="titulo"><h2>Mi registro</h2>
      <p class="chico apagado">Las predicciones que guardaste y si el modelo
        acertó.</p></div>

    <div style="padding:18px 18px 0"><div class="tarjeta">
      <div class="sobretitulo" style="margin-bottom:13px">Mis equipos</div>
      ${estado.favoritos.length ? estado.favoritos.map(e => `
        <div class="fila" style="margin-bottom:11px">
          <div class="escudo"></div>
          <div class="crece" style="font-weight:600">${esc(e)}</div>
          <button class="pildora" data-favorito="${esc(e)}"
            style="width:26px;height:26px;padding:0;border-radius:50%">×</button>
        </div>`).join('')
        : `<p class="chico apagado" style="margin:0">Todavía no marcaste
           ninguno. Tocá la estrella de un partido.</p>`}
    </div></div>

    ${resumen.por_tema.length ? bloqueBarras('Acierto por tema',
      resumen.por_tema.map(t => ({ nombre: t.tema, pct: t.acierto,
                                   extra: `${t.n} guardadas` }))) : ''}

    ${resumen.por_confianza.length ? bloqueBarras('Acierto por confianza',
      resumen.por_confianza.map(c => ({ nombre: estrellas(c.estrellas),
                                        pct: c.acierto, extra: `${c.n}` })),
      'Cuando el modelo avisa que confía poco, conviene hacerle caso.') : ''}

    ${preds.length ? `<div class="lista">${preds.map(p => `
      <div class="tarjeta" style="padding:14px 16px">
        <div class="fila">
          <div class="punto ${p.ok === true ? 'bien' : p.ok === false ? 'mal' : ''}"></div>
          <div class="crece">
            <div style="font-weight:500">${esc(p.linea)}</div>
            <div class="chico apagado" style="margin-top:3px">${esc(p.partido)}</div>
          </div>
          <div class="num chico apagado">${p.prob}%</div>
          <button class="pildora" data-borrar="${p.id}"
            style="width:26px;height:26px;padding:0;border-radius:50%">×</button>
        </div>
      </div>`).join('')}</div>`
      : vacio('Sin predicciones guardadas',
              'Abrí un partido, elegí un tema y guardalo.')}`;
}

function bloqueBarras(titulo, filas, nota) {
  return `<div style="padding:10px 18px 0"><div class="tarjeta">
    <div class="sobretitulo" style="margin-bottom:14px">${esc(titulo)}</div>
    ${filas.map(f => `<div style="margin-bottom:13px">
      <div class="fila">
        <div class="crece">${f.nombre}</div>
        <div class="num" style="font-weight:600">${f.pct}%</div>
        ${f.extra ? `<div class="chico apagado">${esc(f.extra)}</div>` : ''}
      </div>
      ${barra(f.pct)}
    </div>`).join('')}
    ${nota ? `<div class="pie">${esc(nota)}</div>` : ''}
  </div></div>`;
}
