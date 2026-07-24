#!/usr/bin/env node
/* Test F6 ad-hoc: renderGlobalPending clicable + changeSource(keepTab).
 * Extrae los bloques REALES de client_script.js (mismo emparejamiento de
 * llaves que extract_bundle.py) y los ejecuta con DOM mínimo stubbed. */
'use strict';
const fs = require('fs');
const vm = require('node:vm');
const lines = fs.readFileSync('client_script.js', 'utf8').split('\r\n');

function findLine(s) { for (let i = 0; i < lines.length; i++) if (lines[i].trim().startsWith(s)) return i; throw new Error('no encontrado: ' + s); }
function extractBlock(i0) {
  let depth = 0, started = false, out = [];
  for (let i = i0; i < lines.length; i++) {
    out.push(lines[i]);
    for (const ch of lines[i]) { if (ch === '{') { depth++; started = true; } else if (ch === '}') depth--; }
    if (started && depth === 0) return out.join('\n');
  }
  throw new Error('bloque sin cerrar');
}
const code = [
  extractBlock(findLine('function renderGlobalPending(')),
  extractBlock(findLine('async function changeSource(')),
].join('\n\n');

// ── DOM mínimo ──
function makeEl() {
  return {
    children: [], listeners: {}, style: { cssText: '' }, dataset: {}, _innerHTML: '',
    set innerHTML(v) { this._innerHTML = v; if (v === '') this.children = []; },
    get innerHTML() { return this._innerHTML; },
    appendChild(c) { this.children.push(c); },
    addEventListener(ev, fn) { (this.listeners[ev] = this.listeners[ev] || []).push(fn); },
    click() { (this.listeners.click || []).forEach(f => f()); },
    set textContent(v) { this._tc = String(v); }, get textContent() { return this._tc || ''; },
  };
}
const container = makeEl();
const sourceSel = makeEl();
sourceSel.options = [{ value: 'tsumego_hero' }, { value: 'cho_chikun' }];
sourceSel.value = 'tsumego_hero';
const runProgress = makeEl();

const calls = { switchTab: [], loadCollections: 0, showSessionEnd: 0 };
const ctx = {
  console,
  document: {
    getElementById: id => ({ 'rv-global-pending': container, 'source-sel': sourceSel, 'run-progress': runProgress }[id] || makeEl()),
    createElement: () => makeEl(),
  },
  dbQuery: () => [{ source: 'tsumego_hero' }, { source: 'cho_chikun' }, { source: 'huerfano' }],
  localCountReviewPending: s => (s === 'cho_chikun' ? 72 : 0),
  esc: s => s,
  currentSource: 'tsumego_hero',
  activeRunId: 7, runMode: true, runItems: [1], allProblems: [1], chaptersCache: { x: 1 },
  switchTab: n => calls.switchTab.push(n),
  loadCollections: async () => { calls.loadCollections++; },
  showSessionEnd: () => { calls.showSessionEnd++; },
  Array,
};
vm.createContext(ctx);
vm.runInContext(code, ctx);

const fails = [];
const check = (name, cond) => { console.log((cond ? 'PASS ' : 'FAIL ') + name); if (!cond) fails.push(name); };

(async () => {
  // 1) render: una fila por source, nombre con listener salvo el actual
  ctx.renderGlobalPending();
  check('render: 3 filas', container.children.length === 3);
  const rows = container.children;
  const nameOf = r => r.children[0], cntOf = r => r.children[1];
  check('render: source actual sin listener de click', !(nameOf(rows[0]).listeners.click || []).length);
  check('render: otros sources con listener de click', (nameOf(rows[1]).listeners.click || []).length === 1 && (nameOf(rows[2]).listeners.click || []).length === 1);
  check('render: contador 72 pending', cntOf(rows[1]).textContent === '72 pending');
  check('render: done para 0 pendientes', cntOf(rows[0]).textContent.includes('done'));

  // 2) click en cho_chikun → changeSource keepTab: sin switchTab, resets, dropdown sincronizado
  await nameOf(rows[1]).click();
  await new Promise(r => setTimeout(r, 10));
  check('click: currentSource cambiado', ctx.currentSource === 'cho_chikun');
  check('click: NO cambia de pestana (keepTab)', calls.switchTab.length === 0);
  check('click: loadCollections llamado', calls.loadCollections === 1);
  check('click: showSessionEnd llamado', calls.showSessionEnd === 1);
  check('click: dropdown sincronizado', sourceSel.value === 'cho_chikun');
  check('click: resets de estado', ctx.activeRunId === null && ctx.runMode === false && ctx.runItems.length === 0 && ctx.allProblems.length === 0 && Object.keys(ctx.chaptersCache).length === 0);

  // 3) source huérfano (en sm2_state, no en dropdown): cambia igualmente, dropdown intacto
  await ctx.changeSource('huerfano', { keepTab: true });
  check('huerfano: currentSource cambiado', ctx.currentSource === 'huerfano');
  check('huerfano: dropdown NO tocado', sourceSel.value === 'cho_chikun');

  // 4) flujo del dropdown (sin keepTab): conserva el salto a collections
  await ctx.changeSource('tsumego_hero');
  check('dropdown: switchTab(collections) conservado', calls.switchTab.length === 1 && calls.switchTab[0] === 'collections');

  console.log(fails.length ? `\nRESULTADO F6: ${fails.length} FALLOS` : '\nRESULTADO F6: TODO OK');
  process.exit(fails.length ? 1 : 0);
})();
