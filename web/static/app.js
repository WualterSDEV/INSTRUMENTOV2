/* Instrumento — app.js
 *
 * Regla del archivo: no calcula ni redacta nada. Pide al backend y
 * pinta lo que vuelve. Si un texto se lee mal, se arregla en
 * api/formato.py, no acá.
 */

const estado = {
  tab: 'partidos',
  dia: hoyISO(),
  partido: null,
  vivo: null,
  equipo: null,
  jugador: null,
  tema: null,
  calculo: null,
  liga: 'todas',
  busqueda: '',
  soloSenal: false,
  soloFav: false,
  favoritos: [],
  combi: [],
  admin: false,
  sec: 'datos',
  token: null,
};

/* --- utilidades --- */
const $ = (s, raiz = document) => raiz.querySelector(s);
const vista = () => $('#vista');

function hoyISO() { return new Date().toISOString().slice(0, 10); }

function esc(s) {
  return String(s ?? '').replace(/[&<>"]/g,
    c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

function estrellas(n) {
  if (!n) return '';
  return '★★★★★'.slice(0, n) + '☆☆☆☆☆'.slice(0, 5 - n);
}

function barra(prob) {
  return `<div class="barra"><i class="${prob >= 55 ? 'fuerte' : ''}"
          style="width:${prob}%"></i></div>`;
}

async function pedir(ruta, opciones = {}) {
  const cab = { 'Content-Type': 'application/json' };
  if (estado.token) cab['X-Admin-Token'] = estado.token;
  const r = await fetch(ruta, { ...opciones, headers: { ...cab, ...opciones.headers } });
  if (!r.ok && r.status !== 403) throw new Error(`${r.status}`);
  return r.status === 204 ? null : r.json();
}

function cargando() {
  vista().innerHTML = $('#t-cargando').innerHTML;
}

function vacio(titulo, texto, boton) {
  return `<div class="vacio">
    <div style="font-weight:600">${esc(titulo)}</div>
    <p class="chico apagado" style="margin:8px 0 0">${esc(texto)}</p>
    ${boton ? `<button class="pildora" style="margin-top:16px"
                data-accion="${boton.accion}">${esc(boton.texto)}</button>` : ''}
  </div>`;
}

function pendiente(d) {
  return `<div class="vacio">
    <div style="font-weight:600">Todavía no hay datos</div>
    <p class="chico apagado" style="margin:8px 0 0">${esc(d.mensaje)}</p>
  </div>`;
}

/* --- arranque --- */
async function iniciar() {
  const guardado = localStorage.getItem('instrumento:sesion');
  if (guardado) {
    Object.assign(estado, JSON.parse(guardado));
    entrar();
  }

  const tema = localStorage.getItem('instrumento:tema');
  if (tema) document.body.dataset.tema = tema;
  sincronizarTema();

  $('#f-login').addEventListener('submit', e => {
    e.preventDefault();
    const c = $('#correo').value.trim();
    const p = $('#clave').value.trim();
    if (!c || !p) {
      $('#login-error').textContent = 'Completá el correo y la contraseña.';
      $('#login-error').classList.remove('oculto');
      return;
    }
    estado.usuario = c;
    entrar();
  });

  $('#b-invitado').addEventListener('click', () => {
    estado.usuario = 'invitado';
    entrar();
  });

  $('#b-tema').addEventListener('click', () => {
    const nuevo = document.body.dataset.tema === 'oscuro' ? 'claro' : 'oscuro';
    document.body.dataset.tema = nuevo;
    localStorage.setItem('instrumento:tema', nuevo);
    sincronizarTema();
  });

  $('#tabs').addEventListener('click', e => {
    const b = e.target.closest('button');
    if (!b) return;
    estado.tab = b.dataset.tab;
    estado.partido = estado.vivo = null;
    pintar();
  });

  vista().addEventListener('click', alClic);
  vista().addEventListener('input', alEscribir);
}

function sincronizarTema() {
  $('#b-tema').textContent =
    document.body.dataset.tema === 'oscuro' ? 'claro' : 'oscuro';
}

function entrar() {
  localStorage.setItem('instrumento:sesion',
    JSON.stringify({ usuario: estado.usuario, favoritos: estado.favoritos }));
  $('#p-login').classList.add('oculto');
  $('#principal').classList.remove('oculto');
  cargarFavoritos();
  pintar();
}

async function cargarFavoritos() {
  try { estado.favoritos = await pedir('/api/favoritos'); } catch {}
}

/* --- enrutado --- */
function pintar() {
  document.querySelectorAll('#tabs button').forEach(b =>
    b.setAttribute('aria-current', String(b.dataset.tab === estado.tab)));

  if (estado.tab === 'partidos' && estado.partido) return verAnalisis();
  if (estado.tab === 'vivo' && estado.vivo) return verVivoDetalle();

  ({
    partidos: verPartidos, vivo: verVivo, combinar: verCombinar,
    registro: verRegistro, ajustes: verAjustes, panel: verPanel,
  }[estado.tab] || verPartidos)();
}

document.addEventListener('DOMContentLoaded', iniciar);
