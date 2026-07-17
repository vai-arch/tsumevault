#!/usr/bin/env node
/* T10/R11: verifica que en las funciones de render citadas no queda ninguna
 * interpolación de los campos de datos sin envolver en esc(. Analiza el texto
 * del script extraído del cliente. */
'use strict';
const fs = require('fs');
const src = fs.readFileSync('client_script.js', 'utf8');

function fnBody(name) {
  const i = src.indexOf(`function ${name}(`);
  if (i < 0) throw new Error('no encontrada: ' + name);
  let d = 0, started = false, j = i;
  for (; j < src.length; j++) {
    if (src[j] === '{') { d++; started = true; }
    else if (src[j] === '}') { d--; if (started && d === 0) break; }
  }
  return src.slice(i, j + 1);
}

// campos de datos que DEBEN ir escapados en cada función
const RULES = {
  renderCollectionsList: ['col.name', 'diffStr', 'e.message'],
  renderChapterList: ['chap.name', 'diffStr'],
  loadRuns: ['run.label', 'run.status'],
  renderStatsTable: ['r.source', 'r.collection_name'],
  renderByLevel: ['source'],
  renderGlobalPending: ['source'],
};

let fails = 0;
for (const [fn, fields] of Object.entries(RULES)) {
  const body = fnBody(fn);
  for (const f of fields) {
    // interpolación cruda del campo: ${campo...} sin esc( inmediatamente dentro
    const re = new RegExp('\\$\\{\\s*' + f.replace(/[.$]/g, '\\$&') + '[^}]*\\}', 'g');
    const raw = (body.match(re) || []).filter(m => !m.startsWith('${esc('));
    const ok = raw.length === 0;
    console.log((ok ? 'PASS ' : 'FAIL ') + `${fn}: ${f}` + (ok ? '' : `  → ${raw.join(' | ')}`));
    if (!ok) fails++;
  }
}
console.log(fails ? `\n${fails} FALLOS` : '\nESC OK: todos los campos de datos escapados');
process.exit(fails ? 1 : 0);
