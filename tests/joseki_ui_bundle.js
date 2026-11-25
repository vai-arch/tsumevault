    // ══ J3: JOSEKIS — pestaña y modo aprender (REQUISITOS_JOSEKI.md J-30..J-43) ══
    // El contenido llega compilado por import_joseki.py (joseki/<fichero>.json +
    // manifest.json). Bloque 1: funciones PURAS (sin DOM ni estado global),
    // extraídas y probadas en Node por extract_joseki.py + test_joseki.js.
    // Bloque 2: UI al estilo del visor de partidas (gm*).

    // J3: simetrías del tablero 19x19 (J-40). t en 0..7: bit 4 = transponer,
    // bit 1 = espejo horizontal, bit 2 = espejo vertical. Los pases no cambian.
    function jsXform(m, t) {
      if (m === 'pass') return m;
      let x = m.charCodeAt(0) - 97, y = m.charCodeAt(1) - 97;
      if (t & 4) { const s = x; x = y; y = s; }
      if (t & 1) x = 18 - x;
      if (t & 2) y = 18 - y;
      return String.fromCharCode(97 + x) + String.fromCharCode(97 + y);
    }
    function jsXformInv(m, t) {
      if (m === 'pass') return m;
      let x = m.charCodeAt(0) - 97, y = m.charCodeAt(1) - 97;
      if (t & 2) y = 18 - y;
      if (t & 1) x = 18 - x;
      if (t & 4) { const s = x; x = y; y = s; }
      return String.fromCharCode(97 + x) + String.fromCharCode(97 + y);
    }
    // J3: símbolo + color de un fantasma (J-31: color Y forma, no solo tono).
    function jsMarkInfo(n) {
      if (n.ctx) return { sym: '◆', color: '#a07cd8', kind: 'context' };   // J3.2: nodo de contexto (piedras añadidas)
      if (n.it && !n.implicit) return { sym: '?', color: '#4a8fe7', kind: 'whatif' };
      if (n.q === 'bad') return { sym: '✕', color: '#d45030', kind: 'bad' };
      if (n.q === 'doubtful') return { sym: '▲', color: '#e0a030', kind: 'doubtful' };
      if (n.te) return { sym: '★', color: '#5cb868', kind: 'tesuji' };
      return { sym: '●', color: '#5cb868', kind: 'good' };
    }
    // J3: opciones visibles en un nodo. El pase implícito (rama ¿y si? del mismo
    // color, J-75) no se muestra como opción: se aplanan sus hijos IT y se
    // recuerda en "via" para que el sistema lo juegue antes de la piedra.
    // J3.2: un nodo de contexto es una opción con ctx=true (chip, nunca fantasma).
    function jsOptions(node, showWhatif) {
      const out = [];
      for (const k of (node.ch || [])) {
        if (k.it && !showWhatif) continue;
        if (k.implicit) {
          for (const g of (k.ch || [])) out.push(Object.assign({ m: g.m, c: g.c, pass: g.m === 'pass', node: g, via: k }, jsMarkInfo(g)));
        } else {
          out.push(Object.assign({ m: k.m, c: k.c, pass: k.m === 'pass', ctx: !!k.ctx, node: k, via: null }, jsMarkInfo(k)));
        }
      }
      return out;
    }
    // J3: final de línea = sin hijos que no sean ramas ¿y si? (J-71). Mismo
    // criterio que is_endpoint() de joseki_lib.py; un pase implícito nunca lo es.
    function jsIsEndpoint(node) {
      if (node.implicit) return false;
      return !(node.ch || []).some(k => !k.it);
    }
    // J3: señal tras jugar un nodo (J-34): mala -> rojo; final de línea -> verde.
    function jsSignal(node) {
      return { bad: node.q === 'bad', end: jsIsEndpoint(node) };
    }
    // J3: ruta de nombres de variante recorrida (para #board-hint).
    function jsNamePath(stack) {
      return stack.filter(n => n.name).map(n => n.name).join(' · ');
    }
    // J3.1: ¿se dibujan los fantasmas? Siempre con "all ghosts"; si no, solo
    // cuando hay 2+ opciones visibles (pases incluidos, what-if ya filtrado).
    // J3.2: los contextos no cuentan: son escenarios, no alternativas que adivinar.
    function jsGhostsVisible(opts, showAll) {
      return !!showAll || opts.filter(o => !o.ctx).length >= 2;
    }

    // ── J3: UI ──
    let jsActive = false;       // true con la pestaña Josekis activa (análogo a gmActive)
    let jsManifest = null;      // { format, files: [{ file, json, hash, lines }] }
    let jsEntry = null;         // entrada del manifiesto abierta
    let jsData = null;          // JSON compilado del fichero abierto
    let jsStack = [];           // nodos recorridos desde la raíz (la raíz no entra)
    let jsSym = 0;              // orientación actual (0 = la del fichero)
    let jsShowWhatif = true;    // mostrar ramas ¿y si?
    let jsShowAll = true;       // J3.1: fantasmas también con una sola continuación
    let jsNotice = '';          // aviso de un solo render (p. ej. tenuki implícito)

    function jsNode() { return jsStack.length ? jsStack[jsStack.length - 1] : jsData.root; }
    // J3.1: preferencias de los checks, por navegador (localStorage protegido)
    function jsPrefGet(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : v === '1'; } catch (e) { return d; } }
    function jsPrefSet(k, v) { try { localStorage.setItem(k, v ? '1' : '0'); } catch (e) { } }
    function jsXy(m) { return { x: m.charCodeAt(0) - 97, y: m.charCodeAt(1) - 97 }; }

    async function jsLoadManifest() {
      const list = document.getElementById('js-list');
      const msg = t => { list.innerHTML = ''; const d = document.createElement('div'); d.style.cssText = 'padding:24px 14px;font-family:var(--mono);font-size:9px;color:var(--dim2);text-align:center'; d.textContent = t; list.appendChild(d); };
      try {
        const r = await fetch(SGF_BASE + 'joseki/manifest.json', { cache: 'no-store' });
        if (!r.ok) throw new Error('HTTP ' + r.status);
        const man = await r.json();
        if (!man || man.format !== 1 || !Array.isArray(man.files)) throw new Error('manifest format');
        jsManifest = man;
      } catch (e) {
        console.warn('jsLoadManifest', e);
        if (!jsManifest) { msg('No joseki files available (offline or not published yet)'); return; }
      }
      if (!jsManifest.files.length) { msg('No joseki files'); return; }
      list.innerHTML = '';
      for (const f of jsManifest.files) {
        const div = document.createElement('div');
        div.style.cssText = 'padding:7px 14px;font-family:var(--mono);font-size:9px;color:var(--text);cursor:pointer;border-bottom:1px solid var(--border);transition:background .1s;';
        div.textContent = f.file;
        const sub = document.createElement('div');
        sub.style.cssText = 'font-size:8px;color:var(--dim2);margin-top:2px;';
        sub.textContent = f.lines != null ? f.lines + ' lines' : '';   // manifiesto anterior (sin lines): nada
        div.appendChild(sub);
        div.addEventListener('mouseenter', () => div.style.background = 'var(--hover)');
        div.addEventListener('mouseleave', () => div.style.background = '');
        div.addEventListener('click', () => jsOpenFile(f));
        list.appendChild(div);
      }
    }

    async function jsOpenFile(entry) {
      try {
        const url = SGF_BASE + 'joseki/' + encodeURIComponent(entry.json) + '?h=' + encodeURIComponent(entry.hash);
        const r = await fetch(url);
        if (!r.ok) throw new Error('HTTP ' + r.status);
        const data = await r.json();
        if (!data || data.format !== 1 || !data.root) throw new Error('joseki format');
        jsEntry = entry; jsData = data; jsStack = []; jsSym = 0; jsNotice = '';
        if (!wgoBoard || boardSize !== 19) initBoard(19);
        jsRender(null);
        switchToBoard();
      } catch (e) { console.warn('jsOpenFile', e); alert('Error loading joseki file: ' + e.message); }
    }

    function jsRender(signal) {
      if (!jsData || !wgoBoard) return;
      const node = jsNode();
      clearBoard();
      // Posición: WGo.Game aplica capturas; la legalidad ya la validó el importador.
      const game = new WGo.Game(19, 'NONE', true, false);
      const ctxPts = [];   // J3.2: piedras de contexto de la pila (para el cuadrado)
      for (const n of jsStack) {
        if (n.ctx) {         // J3.2: el contexto añade piedras, sin capturas ni cambio de turno
          for (const c of ['B', 'W']) for (const m of (n.ctx[c] || [])) {
            const p = jsXy(jsXform(m, jsSym));
            game.setStone(p.x, p.y, c === 'B' ? WGo.B : WGo.W);
            ctxPts.push(p);
          }
          continue;
        }
        if (n.m === 'pass') continue;
        const p = jsXy(jsXform(n.m, jsSym));
        game.play(p.x, p.y, n.c === 'B' ? WGo.B : WGo.W);
      }
      const pos = game.getPosition();
      for (let x = 0; x < 19; x++) for (let y = 0; y < 19; y++) {
        const v = pos.get(x, y);
        if (v === WGo.B) wgoBoard.addObject({ x, y, c: 1 });
        else if (v === WGo.W) wgoBoard.addObject({ x, y, c: -1 });
      }
      const stoneAt = (x, y) => { const v = pos.get(x, y); return v === WGo.B ? 1 : v === WGo.W ? -1 : 0; };
      // Último movimiento (como en Games)
      if (jsStack.length && node.m !== 'pass' && !node.ctx) { const p = jsXy(jsXform(node.m, jsSym)); wgoBoard.addObject({ x: p.x, y: p.y, type: 'CR' }); }
      // Marcas del nodo (J-76), rotadas con el tablero. J3.2: LB = [[coord, texto], ...]
      const labelled = new Set();
      for (const [t, list] of Object.entries(node.marks || {})) {
        const h = WGo.Board.drawHandlers[t];
        if (!h) continue;
        for (const m of list) {
          const isLb = t === 'LB';
          const p = jsXy(jsXform(isLb ? m[0] : m, jsSym)), sc = stoneAt(p.x, p.y);
          const obj = { x: p.x, y: p.y, type: h, c: sc === 1 ? 'white' : sc === -1 ? 'black' : '#333' };
          if (isLb) { obj.text = m[1]; labelled.add(p.x + ',' + p.y); }
          wgoBoard.addObject(obj);
        }
      }
      // J3.2: cuadrado en las piedras de contexto que siguen en el tablero, salvo si llevan letra
      for (const p of ctxPts) {
        const sc = stoneAt(p.x, p.y);
        if (!sc || labelled.has(p.x + ',' + p.y)) continue;
        wgoBoard.addObject({ x: p.x, y: p.y, type: WGo.Board.drawHandlers['SQ'], c: sc === 1 ? 'white' : 'black' });
      }
      // Opciones: fantasmas en el tablero; pases como chips (J-31, J-74)
      const opts = jsOptions(node, jsShowWhatif);
      const drawGhosts = jsGhostsVisible(opts, jsShowAll);   // J3.1
      jsClosePop();
      const seen = new Set();
      for (const o of opts) {
        if (o.pass || o.ctx || !drawGhosts) continue;
        const p = jsXy(jsXform(o.m, jsSym)), key = p.x + ',' + p.y;
        if (seen.has(key)) continue;   // varias opciones en el mismo punto: se elige al pulsar
        seen.add(key);
        wgoBoard.addObject({ x: p.x, y: p.y, c: o.c === 'B' ? 1 : -1, type: 'outline' });
        wgoBoard.addObject({ x: p.x, y: p.y, type: WGo.Board.drawHandlers['LB'], text: o.sym, c: o.color });
      }
      const ctxOpts = opts.filter(o => o.ctx);   // J3.2: los contextos, siempre visibles
      if (drawGhosts) jsRenderChoices(opts.filter(o => o.pass).concat(ctxOpts));
      else jsRenderNeutralPass(opts.filter(o => o.pass), ctxOpts);   // J3.1: sin pistas, pero se puede pasar
      // Comentario (J-35: siempre visible en modo aprender)
      const cb = document.getElementById('comment-box');
      cb.textContent = jsStack.length ? (node.comment || '') : (jsData.description || '');
      // Señal (J-34)
      const bw = document.getElementById('board-wrap');
      bw.classList.remove('board-ok', 'board-bad');
      if (signal && signal.bad) { bw.classList.add('board-bad'); playSound('wrong'); }
      else if (signal && signal.end) { bw.classList.add('board-ok'); playSound('right'); }
      else if (signal && signal.moved) playSound('stone');
      // Cabecera: fichero + ruta de nombres + estado
      const parts = [jsData.file];
      const names = jsNamePath(jsStack);
      if (names) parts.push(names);
      if (jsStack.length && jsIsEndpoint(node)) parts.push('End of line');
      if (jsNotice) parts.push(jsNotice);
      const hint = document.getElementById('board-hint');
      hint.textContent = parts.join(' · ');
      hint.className = '';
      jsNotice = '';
      jsSetupBoardClick();
      jsUpdateControls();
    }

    // J3: chips bajo el tablero (pases, o la elección cuando varias opciones
    // comparten punto). Cada chip lleva el mismo símbolo/color que los fantasmas.
    function jsChoiceButton(o) {
      const b = document.createElement('button');
      b.className = 'ctrl-btn';
      const s = document.createElement('span');
      s.style.color = o.color; s.textContent = o.sym + ' ';
      b.appendChild(s);
      b.appendChild(document.createTextNode(o.ctx ? 'Context · ' + (o.node.name || '?')   // J3.2
        : (o.pass ? 'Pass' : o.m.toUpperCase()) + ' (' + o.c + ')' + (o.node.name ? ' · ' + o.node.name : '')));
      b.addEventListener('click', () => jsPlay(o));
      return b;
    }
    function jsRenderChoices(opts) {
      const zone = document.getElementById('js-choices');
      zone.innerHTML = '';
      for (const o of opts) zone.appendChild(jsChoiceButton(o));
    }
    // J3.1: con los fantasmas ocultos, un botón Pass sin símbolo (no desvela si
    // pasar es una opción); si el nodo no tiene pase, no hace nada.
    // J3.2: los chips de contexto se añaden detrás (siempre visibles).
    function jsRenderNeutralPass(passOpts, ctxOpts) {
      const zone = document.getElementById('js-choices');
      zone.innerHTML = '';
      const b = document.createElement('button');
      b.className = 'ctrl-btn';
      b.textContent = 'Pass';
      b.addEventListener('click', () => { if (passOpts.length === 1) jsPlay(passOpts[0]); });
      zone.appendChild(b);
      for (const o of (ctxOpts || [])) zone.appendChild(jsChoiceButton(o));
    }
    // J3.1: menú flotante anclado a la intersección (varias opciones en el
    // mismo punto). Se cierra al elegir, al pulsar fuera, con Escape o al repintar.
    function jsShowPop(hits, x, y) {
      let pop = document.getElementById('js-pop');
      if (!pop) {
        pop = document.createElement('div');
        pop.id = 'js-pop';
        pop.style.cssText = 'position:fixed;z-index:1200;display:none;flex-direction:column;gap:4px;padding:6px;background:var(--panel);border:1px solid var(--border2);border-radius:3px;box-shadow:0 8px 24px rgba(0,0,0,.6);';
        document.body.appendChild(pop);
      }
      pop.innerHTML = '';
      for (const o of hits) pop.appendChild(jsChoiceButton(o));
      const rect = wgoBoard.element.getBoundingClientRect();
      const px = rect.left + (wgoBoard.left + x * wgoBoard.fieldWidth) / wgoBoard.pixelRatio;
      const py = rect.top + (wgoBoard.top + y * wgoBoard.fieldHeight) / wgoBoard.pixelRatio;
      pop.style.display = 'flex';
      const w = pop.offsetWidth || 160, h = pop.offsetHeight || 60;
      const vw = window.innerWidth || 1024, vh = window.innerHeight || 768;
      let left = px + 10, top = py + 10;
      if (left + w > vw - 4) left = Math.max(4, px - w - 10);
      if (top + h > vh - 4) top = Math.max(4, py - h - 10);
      pop.style.left = left + 'px'; pop.style.top = top + 'px';
    }
    function jsClosePop() {
      const pop = document.getElementById('js-pop');
      if (pop) pop.style.display = 'none';
    }

    function jsPlay(opt) {
      if (opt.via) { jsStack.push(opt.via); jsNotice = 'tenuki by ' + opt.via.c; }
      jsStack.push(opt.node);
      const sig = jsSignal(opt.node);
      sig.moved = !opt.pass && !opt.ctx;   // J3.2: el contexto no suena a piedra
      jsRender(sig);
    }

    function jsSetupBoardClick() {
      window._boardClickHandler = (x, y) => {
        if (!jsActive || !jsData) return;
        const m = jsXformInv(String.fromCharCode(97 + x) + String.fromCharCode(97 + y), jsSym);
        const hits = jsOptions(jsNode(), jsShowWhatif).filter(o => !o.pass && !o.ctx && o.m === m);
        if (hits.length === 1) jsPlay(hits[0]);
        else if (hits.length > 1) jsShowPop(hits, x, y);   // J3.1: menú junto al punto
      };
    }

    function jsBack() {
      if (!jsStack.length) return;
      jsStack.pop();
      if (jsStack.length && jsStack[jsStack.length - 1].implicit) jsStack.pop();   // el pase implícito no es una parada
      jsRender(null);
    }
    function jsRestart() { if (!jsData) return; jsStack = []; jsRender(null); }
    function jsRotate() { if (!jsData) return; jsSym = (jsSym + 1) % 8; jsRender(null); }

    function jsUpdateControls() {
      document.getElementById('js-btn-back').disabled = !jsStack.length;
    }

    function jsInitControls() {
      document.getElementById('js-btn-back').addEventListener('click', jsBack);
      document.getElementById('js-btn-restart').addEventListener('click', jsRestart);
      document.getElementById('js-btn-rotate').addEventListener('click', jsRotate);
      document.getElementById('js-whatif').addEventListener('change', e => { jsShowWhatif = e.target.checked; jsPrefSet('joseki_show_whatif', jsShowWhatif); if (jsData) jsRender(null); });
      // J3.1: check 'all ghosts' y preferencias recordadas
      jsShowWhatif = jsPrefGet('joseki_show_whatif', true);
      jsShowAll = jsPrefGet('joseki_show_all', true);
      document.getElementById('js-whatif').checked = jsShowWhatif;
      document.getElementById('js-allghosts').checked = jsShowAll;
      document.getElementById('js-allghosts').addEventListener('change', e => { jsShowAll = e.target.checked; jsPrefSet('joseki_show_all', jsShowAll); if (jsData) jsRender(null); });
      // Cierre del menú flotante: pulsar fuera (pointerdown: el clic que lo abre ya pasó) o Escape
      document.addEventListener('pointerdown', e => { const pop = document.getElementById('js-pop'); if (pop && pop.style.display !== 'none' && !pop.contains(e.target)) jsClosePop(); });
      document.addEventListener('keydown', e => { if (e.code === 'Escape') jsClosePop(); });
    }

    // J3: entrada en la pestaña: refresca la lista y, si había un joseki
    // abierto, lo vuelve a pintar (el tablero es compartido con otros modos).
    function jsEnterTab() {
      jsLoadManifest();
      if (jsData) { if (!wgoBoard || boardSize !== 19) initBoard(19); jsRender(null); }
    }
