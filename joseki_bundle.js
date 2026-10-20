// ── function jsXform( ──
    function jsXform(m, t) {
      if (m === 'pass') return m;
      let x = m.charCodeAt(0) - 97, y = m.charCodeAt(1) - 97;
      if (t & 4) { const s = x; x = y; y = s; }
      if (t & 1) x = 18 - x;
      if (t & 2) y = 18 - y;
      return String.fromCharCode(97 + x) + String.fromCharCode(97 + y);
    }

// ── function jsXformInv( ──
    function jsXformInv(m, t) {
      if (m === 'pass') return m;
      let x = m.charCodeAt(0) - 97, y = m.charCodeAt(1) - 97;
      if (t & 2) y = 18 - y;
      if (t & 1) x = 18 - x;
      if (t & 4) { const s = x; x = y; y = s; }
      return String.fromCharCode(97 + x) + String.fromCharCode(97 + y);
    }

// ── function jsMarkInfo( ──
    function jsMarkInfo(n) {
      if (n.ctx) return { sym: '◆', color: '#a07cd8', kind: 'context' };   // J3.2: nodo de contexto (piedras añadidas)
      if (n.it && !n.implicit) return { sym: '?', color: '#4a8fe7', kind: 'whatif' };
      if (n.q === 'bad') return { sym: '✕', color: '#d45030', kind: 'bad' };
      if (n.q === 'doubtful') return { sym: '▲', color: '#e0a030', kind: 'doubtful' };
      if (n.te) return { sym: '★', color: '#5cb868', kind: 'tesuji' };
      return { sym: '●', color: '#5cb868', kind: 'good' };
    }

// ── function jsOptions( ──
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

// ── function jsIsEndpoint( ──
    function jsIsEndpoint(node) {
      if (node.implicit) return false;
      return !(node.ch || []).some(k => !k.it);
    }

// ── function jsSignal( ──
    function jsSignal(node) {
      return { bad: node.q === 'bad', end: jsIsEndpoint(node) };
    }

// ── function jsNamePath( ──
    function jsNamePath(stack) {
      return stack.filter(n => n.name).map(n => n.name).join(' · ');
    }

// ── function jsGhostsVisible( ──
    function jsGhostsVisible(opts, showAll) {
      return !!showAll || opts.filter(o => !o.ctx).length >= 2;
    }