// VC1: modo editar visibilidad en Collections (botón ✎). El control nunca cambia la
// visibilidad de los capítulos: activo, se ven todos con su casilla show; inactivo, solo
// los visibles. Comprueba el HTML de la página y prueba el código real de localInsertRun
// (extraído de tsumevault.html) con una BD simulada.
//
//     node tests/test_edit_mostrar.js
const fs = require('fs'), path = require('path'), vm = require('vm');
const { pageSource } = require('./page_source.js');
let FAILS = 0, N = 0;
function check(name, cond, extra) { N++; console.log((cond ? 'PASS ' : 'FAIL ') + name + (!cond && extra ? '  ' + extra : '')); if (!cond) FAILS++; }

const html = pageSource();
const src = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]).sort((a, b) => b.length - a.length)[0];

// Extrae una función de nivel superior por su nombre (llaves equilibradas).
function fnSource(name) {
  const a = src.indexOf('function ' + name + '(');
  if (a < 0) return null;
  let i = src.indexOf(') {', a) + 2, depth = 0;   // la llave del cuerpo, no la de los parámetros
  for (; i < src.length; i++) { if (src[i] === '{') depth++; else if (src[i] === '}' && --depth === 0) break; }
  return src.slice(a, i + 1);
}

// 1. HTML: el control sale de ⚙ y entra en Collections
const cfg = html.slice(html.indexOf('<div id="cfg-modal">'), html.indexOf('<!-- STATS MODAL -->'));
check('⚙ ya no tiene la casilla de visibilidad', cfg.length > 1000 && !cfg.includes('cfg-filter-mostrar') && !/lecciones marcadas/i.test(cfg));
check('no quedan restos de filterMostrar / filter_mostrar', !/filterMostrar|FILTER_MOSTRAR|filter_mostrar/.test(html));
const colTab = html.slice(html.indexOf('id="tab-collections"'), html.indexOf('id="tab-focus"'));
const btn = colTab.match(/<button id="btn-edit-mostrar"[^>]*>/);
check('Collections tiene el botón ✎ con tooltip', !!btn && /title="[^"]*visibilidad[^"]*"/i.test(btn[0]), btn && btn[0]);
check('✎ está junto a ⊞ All', !!btn && colTab.indexOf('btn-edit-mostrar') < colTab.indexOf('btn-expand-all'));
check('la clave nueva arranca en «no editar»', /let editMostrar = localStorage\.getItem\(EDIT_MOSTRAR_KEY\) === 'true';/.test(src));
check('las casillas show solo se pintan en modo editar', src.includes('${editMostrar ? `<label') && src.includes('class="chap-mostrar-chk"'));

// 2. localInsertRun (código real): el run de colección respeta la visibilidad salvo en modo editar
const code = fnSource('localInsertRun');
check('localInsertRun encontrada y usa editMostrar', !!code && code.includes('editMostrar'));
const PROBS = [
  { source: 'tsumego_hero', problem_id: 'a', set_id: 7, mostrar: 1 },
  { source: 'tsumego_hero', problem_id: 'b', set_id: 7, mostrar: 0 },
  { source: 'tsumego_hero', problem_id: 'c', set_id: 7, mostrar: 1 },
  { source: 'tsumego_hero', problem_id: 'd', set_id: 7, mostrar: 0 },
];
function runCollection(editMostrar) {
  const items = [], stat = { queries: 0 };
  const ctx = {
    editMostrar, items, stat,
    dbQuery(sql) { stat.queries++; return PROBS.filter(p => !/ch\.mostrar=1/.test(sql) || p.mostrar).map(p => ({ source: p.source, problem_id: p.problem_id })); },
    dbQueryOne() { return { id: 1, set_id: 7 }; },
    dbExec(sql, params) { if (/INSERT INTO run_items/.test(sql)) items.push(params[2]); },
    makeUUID: () => 'u', alert: () => { }, Math, Date,
  };
  vm.createContext(ctx);
  vm.runInContext(code + '\n__r = localInsertRun("tsumego_hero", "collection", { set_id: 7 });', ctx);
  return ctx;
}
const off = runCollection(false), on = runCollection(true);
check('sin editar: el run de colección consultó la BD', off.stat.queries === 1 && off.__r && off.__r.total === off.items.length);
check('sin editar: el run de colección solo lleva capítulos visibles', off.__r.total === 2 && off.items.sort().join() === 'a,c', JSON.stringify(off.items));
check('editando: el run de colección lleva todos los capítulos', on.__r.total === 4, JSON.stringify(on.items));

console.log(`\n${N - FAILS}/${N} PASS`);
process.exit(FAILS ? 1 : 0);
