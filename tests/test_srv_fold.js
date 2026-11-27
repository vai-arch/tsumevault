// SP1: estado del servidor en ⚙ como desplegable cerrado por defecto. Cerrado, solo el punto
// de color (nivel y avisos en su tooltip) y ↻; abierto, el detalle. Se recuerda abierto/cerrado.
// Comprueba el HTML y el código real de renderServerStatus con un DOM mínimo simulado.
//
//     node tests/test_srv_fold.js
const vm = require('vm');
const { pageSource } = require('./page_source.js');
let FAILS = 0, N = 0;
function check(name, cond, extra) { N++; console.log((cond ? 'PASS ' : 'FAIL ') + name + (!cond && extra ? '  ' + extra : '')); if (!cond) FAILS++; }

const html = pageSource();
const src = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]).sort((a, b) => b.length - a.length)[0];
function fnSource(name) {
  const a = src.indexOf('function ' + name + '(');
  if (a < 0) return null;
  let i = src.indexOf(') {', a) + 2, depth = 0;
  for (; i < src.length; i++) { if (src[i] === '{') depth++; else if (src[i] === '}' && --depth === 0) break; }
  const pre = src.slice(a - 6, a) === 'async ' ? 6 : 0;   // conserva «async»
  return src.slice(a - pre, i + 1);
}

// 1. HTML
const det = html.match(/<details class="cfg-section" id="cfg-srv"[^>]*>[\s\S]*?<\/details>/);
check('el estado del servidor es un <details>', !!det);
check('cerrado por defecto (sin atributo open)', !!det && !/<details[^>]*\bopen\b/.test(det[0].split('\n')[0]));
const summ = det && det[0].match(/<summary[\s\S]*?<\/summary>/);
check('el summary lleva el punto y el ↻', !!summ && summ[0].includes('id="cfg-srv-dot"') && summ[0].includes('id="cfg-srv-refresh"'));
check('el detalle va fuera del summary', !!det && !!summ && !summ[0].includes('cfg-srv-status') && det[0].includes('id="cfg-srv-status"'));
check('se recuerda abierto/cerrado', /srvBox\.open = lsGet\(SRV_STATUS_OPEN_KEY\) === '1';/.test(src) && /addEventListener\('toggle', \(\) => lsSet\(SRV_STATUS_OPEN_KEY/.test(src));
check('↻ no pliega el desplegable', /srvBtn\.addEventListener\('click', e => \{ e\.preventDefault\(\); renderServerStatus\(\); \}\)/.test(src));

// 2. renderServerStatus (código real) con DOM simulado
const code = ['paintSrvDot', 'renderServerStatus'].map(fnSource);
check('funciones encontradas', code.every(Boolean));
function el() {
  return { style: {}, title: '', children: [], _t: '',
    set textContent(v) { this._t = v; this.children = []; }, get textContent() { return this._t + this.children.map(c => c.textContent).join(''); },
    appendChild(c) { this.children.push(c); return c; } };
}
async function run(resp) {
  const els = { 'cfg-srv-status': el(), 'cfg-srv-dot': el() };
  const ctx = {
    document: { getElementById: id => els[id] || null, createElement: () => el() },
    syncFetch: async () => { if (!resp) throw new Error('down'); return resp; },
    srvStatusSummary: (data) => data ? { level: data.level, warn: data.warn || [], lines: [['Versión', '1']] } : { level: 'bad', warn: ['El servidor no responde'], lines: [] },
    AbortSignal: { timeout: () => null }, Date,
  };
  vm.createContext(ctx);
  vm.runInContext(code.join('\n'), ctx);
  await ctx.renderServerStatus();
  return els;
}
(async () => {
  let e = await run({ ok: true, status: 200, json: async () => ({ level: 'ok' }) });
  check('ok: punto verde, tooltip «Todo en orden»', e['cfg-srv-dot'].style.color === 'var(--ok-bright)' && e['cfg-srv-dot'].title === 'Todo en orden', JSON.stringify(e['cfg-srv-dot']));
  check('ok: el detalle ya no repite la cabecera', !e['cfg-srv-status'].textContent.includes('Todo en orden') && e['cfg-srv-status'].textContent.includes('Versión'));
  e = await run({ ok: true, status: 200, json: async () => ({ level: 'warn', warn: ['Disco al 91%'] }) });
  check('warn: punto dorado y el aviso en el tooltip', e['cfg-srv-dot'].style.color === 'var(--gold)' && e['cfg-srv-dot'].title === 'Hay algo que mirar\nDisco al 91%', JSON.stringify(e['cfg-srv-dot'].title));
  e = await run(null);
  check('sin respuesta: punto rojo', e['cfg-srv-dot'].style.color === 'var(--accent)' && e['cfg-srv-dot'].title.startsWith('Sin conexión'));
  e = await run({ ok: false, status: 401 });
  check('401: punto dorado con el motivo', e['cfg-srv-dot'].style.color === 'var(--gold)' && /Token/.test(e['cfg-srv-dot'].title));
  console.log(`\n${N - FAILS}/${N} PASS`);
  process.exit(FAILS ? 1 : 0);
})();
