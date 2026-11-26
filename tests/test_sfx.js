// Tests de la elección aleatoria de sonidos de piedra/captura (sfxPickIndex).
// Uso: python tests/extract_sfx.py && node tests/test_sfx.js
const fs = require('fs');
const path = require('path');
const vm = require('node:vm');
const ctx = {};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(__dirname, 'sfx_bundle.js'), 'utf8') + '\nthis.sfxPickIndex = sfxPickIndex;', ctx);
const pick = ctx.sfxPickIndex;

let fails = 0, n = 0;
function check(name, cond) { n++; if (cond) console.log('PASS ' + name); else { fails++; console.log('FAIL ' + name); } }
const rnds = []; for (let k = 0; k <= 100; k++) rnds.push(Math.min(k / 100, 0.999999));   // barrido de [0,1)

// Con 5 sonidos: nunca repite el anterior, siempre en rango, y salen los otros 4
for (let last = 0; last < 5; last++) {
  const got = new Set(rnds.map(r => pick(5, last, r)));
  check(`n=5 last=${last}: nunca repite`, !got.has(last));
  check(`n=5 last=${last}: en rango`, [...got].every(i => Number.isInteger(i) && i >= 0 && i < 5));
  check(`n=5 last=${last}: salen los otros 4`, got.size === 4);
}
// Al empezar (last=-1) puede salir cualquiera de los 5
check('n=5 last=-1: salen los 5', new Set(rnds.map(r => pick(5, -1, r))).size === 5);
check('n=5 last=undefined: salen los 5', new Set(rnds.map(r => pick(5, undefined, r))).size === 5);
check('n=5 last=7 (fuera de rango): en rango', rnds.every(r => { const i = pick(5, 7, r); return i >= 0 && i < 5; }));
// Con 2 sonidos alterna; con 1 (o 0) siempre 0
check('n=2: alterna', rnds.every(r => pick(2, 0, r) === 1 && pick(2, 1, r) === 0));
check('n=1: siempre 0', rnds.every(r => pick(1, 0, r) === 0 && pick(1, -1, r) === 0));
check('n=0: 0 sin romper', pick(0, -1, 0.5) === 0);
// Secuencia larga con Math.random: nunca dos iguales seguidos (guarda anti-vacío: hubo cambios)
let last = -1, repeats = 0, changes = 0;
for (let k = 0; k < 5000; k++) { const i = pick(5, last, Math.random()); if (i === last) repeats++; else changes++; last = i; }
check('5000 jugadas seguidas: 0 repeticiones', repeats === 0);
check('guarda: la secuencia sí recorrió jugadas', changes === 5000);

console.log(`\n${n - fails}/${n} PASS`);
console.log(fails ? 'RESULTADO SFX: FALLOS' : 'RESULTADO SFX: TODO OK');
process.exit(fails ? 1 : 0);
