// Compact 120×35 and narrow 80×24 layouts.

// ==================== COMPACT 120×35 ====================
// Geometry: 1(║) + 14(sidebar) + 1(║) + 102(feed) + 1(║) = 119? Need 120.
// Use: 1 + 14 + 1 + 103 + 1 = 120. Sidebar=14, feed=103.

const CSB = 14;
const CFD = 103;
const CINNER = 118;

function cTopBorder() { return [{ text: '╔' + rep('═', CINNER) + '╗', color: TC.border }, '\n']; }
function cBottomBorder() { return [{ text: '╚' + rep('═', CINNER) + '╝', color: TC.border }, '\n']; }
function cDiv2Start() { return [{ text: '╠' + rep('═', CSB) + '╦' + rep('═', CFD) + '╣', color: TC.border }, '\n']; }
function cDiv2End()   { return [{ text: '╠' + rep('═', CSB) + '╩' + rep('═', CFD) + '╣', color: TC.border }, '\n']; }
function cRow2(s, f)  { return [V(), ...s, V(), ...f, V(), '\n']; }
function cRow1(c)     { return [V(), ...c, V(), '\n']; }

function cHeader() {
  return [
    '  ',
    { text: 'CLAUDE BRIDGE', color: TC.text, bold: true },
    '  ',
    { text: '●', color: TC.online },
    '  ',
    { text: ':8765', color: TC.textDim },
    '  ',
    { text: '5ch', color: TC.text }, '  ',
    { text: '565msg', color: TC.text }, '  ',
    { text: '00:14:32', color: TC.text },
    sp(CINNER - (2 + 13 + 2 + 1 + 2 + 5 + 2 + 3 + 2 + 6 + 2 + 8 + 9 + 2)),
    { text: '[?] help', color: TC.borderHi },
    '  ',
  ];
}

function cSbBlank() { return [sp(CSB)]; }

function cSbChannel(label, count, opts = {}) {
  const lbl = label.padEnd(7);
  const cnt = String(count).padStart(3);
  // 1 gut + 1 chev + 1 sp + 7 lbl + 1 sp + 3 cnt = 14
  if (opts.active) {
    return [
      <span key="a" style={{ background: TC.activeBg }}>
        {R([
          { text: '█', color: TC.borderHi },
          { text: '▶', color: TC.borderHi },
          ' ',
          { text: lbl, color: TC.text, bold: true },
          ' ',
          { text: cnt, color: TC.text },
        ])}
      </span>,
    ];
  }
  return [
    ' ', ' ', ' ',
    { text: lbl, color: TC.textMid },
    ' ',
    { text: cnt, color: TC.textDim },
  ];
}

function cFdBlank() { return [sp(CFD)]; }

function cFdHeader() {
  const right = '[I] toggle inspector';
  return [
    '  ',
    { text: 'FEED  ', color: TC.text, bold: true },
    { text: 'pawprint:orchestrator', color: TC.channel, bold: true },
    '   ',
    { text: '89 msg · last 14:32:19', color: TC.textDim },
    sp(CFD - (2 + 6 + 21 + 3 + 22 + right.length + 2)),
    { text: right, color: TC.borderHi },
    '  ',
  ];
}

function cFdHR() { return ['  ', { text: rep('─', CFD - 4), color: TC.border }, '  ']; }

function cFdMessage(m, { selected = false } = {}) {
  const seq = `[${String(m.seq).padStart(2, ' ')}]`;
  const sender = m.sender.padEnd(7);
  const senderColor = SENDER_COLORS_TUI[m.sender] || TC.textMid;
  const typeColor = TYPE_COLORS[m.type] || TC.textDim;
  const contentBudget = 67;
  let content = m.text;
  if (content.length > contentBudget) content = content.slice(0, contentBudget - 1) + '…';
  else content = content.padEnd(contentBudget);
  const typeStr = m.type.padStart(6);
  // 2 + 1 + 4 + 2 + 7 + 2 + 8 + 2 + 67 + 2 + 6 = 103
  const inner = [
    '  ',
    selected ? { text: '▶', color: TC.borderHi, bold: true } : ' ',
    { text: seq, color: TC.textDim },
    '  ',
    { text: sender, color: senderColor, bold: true },
    '  ',
    { text: m.ts, color: TC.textDim },
    '  ',
    { text: content, color: selected ? TC.text : TC.textMid },
    '  ',
    { text: typeStr, color: typeColor, bold: true },
  ];
  if (selected) {
    return [<span key="s" style={{ background: TC.activeBg }}>{R(inner)}</span>];
  }
  return inner;
}

function cStatusBar() {
  const keys = [
    ['↑↓', 'nav'], ['Tab', 'panel'], ['Enter', 'inspect'],
    ['S', 'send'], ['F', 'filter'], ['I', 'inspector'], ['Q', 'quit'],
  ];
  const out = ['  '];
  let used = 2;
  keys.forEach(([k, a]) => {
    const pre = `[${k}]`;
    const after = ` ${a}   `;
    out.push({ text: pre, color: TC.borderHi, bold: true });
    out.push({ text: after, color: TC.textMid });
    used += pre.length + after.length;
  });
  out.push(sp(CINNER - used - 8));
  out.push({ text: 'NORMAL', color: TC.online, bold: true });
  out.push('  ');
  return out;
}

function cSendLabel() {
  return [[
    '  ', { text: 'SEND', color: TC.text, bold: true }, sp(CSB - 6),
  ], [
    '  ', { text: 'ch: ', color: TC.textDim },
    { text: 'pawprint:orchestrator', color: TC.channel, bold: true },
    '  ', { text: 'from: ', color: TC.textDim },
    { text: 'shadow', color: TC.shadow, bold: true },
    sp(CFD - (2 + 4 + 21 + 2 + 6 + 6 + 13)),
    { text: '✓ json', color: TC.online }, '  ',
  ]];
}
function cSendInput() {
  return [[sp(CSB)], [
    '  ',
    { text: '> ', color: TC.borderHi, bold: true },
    { text: '{ "type": "task", "phase": 2, "action": "extract", "match": "m-001" }', color: TC.text },
    { text: '█', color: TC.borderHi },
    sp(CFD - (2 + 2 + 67 + 1 + 5)),
    { text: '⌘↵', color: TC.textDim }, '  ',
  ]];
}

function TUICompactContent() {
  const sb = [];
  sb.push(['  ', { text: 'CHAN', color: TC.text, bold: true }, sp(CSB - 6)]);
  sb.push(cSbBlank());
  sb.push(['  ', { text: 'pawprint', color: TC.textDim }, sp(CSB - 10)]);
  sb.push(cSbChannel('orch', 89, { active: true }));
  sb.push(cSbChannel('worker', 112));
  sb.push(cSbChannel('events', 41));
  sb.push(cSbBlank());
  sb.push(['  ', { text: 'general', color: TC.textDim }, sp(CSB - 9)]);
  sb.push(cSbChannel('sync', 5));
  sb.push(cSbBlank());
  sb.push(['  ', { text: 'system', color: TC.textDim }, sp(CSB - 8)]);
  sb.push(cSbChannel('hb', 318));
  sb.push(cSbBlank());
  sb.push(cSbBlank());

  // activity dots
  sb.push(['  ', { text: '●', color: TC.shadow }, ' ', { text: 'shdw', color: TC.shadow }, ' ', { text: '267', color: TC.textDim }, sp(CSB - 13)]);
  sb.push(['  ', { text: '●', color: TC.mac }, ' ', { text: 'mac ', color: TC.mac }, ' ', { text: '291', color: TC.textDim }, sp(CSB - 13)]);
  sb.push(cSbBlank());
  sb.push(['  ', { text: rep('─', CSB - 4), color: TC.border }, '  ']);
  sb.push(['  ', { text: '[N]', color: TC.borderHi, bold: true }, ' ', { text: 'new', color: TC.textMid }, sp(CSB - 10)]);

  // Feed
  const fd = [];
  fd.push(cFdHeader());
  fd.push(cFdHR());
  fd.push(cFdBlank());
  MSGS.slice(2).forEach((m) => {
    if (m.seq === 52) fd.push(cFdMessage(m, { selected: true }));
    else fd.push(cFdMessage(m));
  });
  fd.push(cFdBlank());
  fd.push([
    '  ', { text: '⏺ ', color: TC.online }, { text: 'live  ', color: TC.online, bold: true },
    { text: 'tail -f  ·  [Space] pause  ·  [/] search', color: TC.textDim },
    sp(CFD - (2 + 2 + 6 + 40 + 14)),
    { text: '↓ at bottom', color: TC.textDim }, '  ',
  ]);

  // pad
  while (sb.length < 25) sb.push(cSbBlank());
  while (fd.length < 25) fd.push(cFdBlank());

  // Assemble - 35 rows total
  // Row 0: top
  // Row 1: header
  // Row 2: divider
  // Rows 3..27: 2-col (25 rows)
  // Row 28: divider
  // Row 29: send label
  // Row 30: send input
  // Row 31: divider
  // Row 32: status
  // Row 33: bottom
  // = 34. Need 35. Add blank.

  const out = [];
  out.push(...cTopBorder());
  out.push(...cRow1(cHeader()));
  out.push(...cDiv2Start());
  for (let i = 0; i < 25; i++) {
    out.push(...cRow2(sb[i] || cSbBlank(), fd[i] || cFdBlank()));
  }
  // Add one more blank content row to hit 35
  out.push(...cRow2(cSbBlank(), cFdBlank()));

  // Transition: kill nothing, just header divider for send
  out.push({ text: '╠' + rep('═', CSB) + '╬' + rep('═', CFD) + '╣', color: TC.border }, '\n');
  const [sL, fL] = cSendLabel();
  out.push(...cRow2(sL, fL));
  const [sI, fI] = cSendInput();
  out.push(...cRow2(sI, fI));
  out.push(...cDiv2End());
  out.push(...cRow1(cStatusBar()));
  out.push(...cBottomBorder());

  return out;
}

function TUICompact() {
  return (
    <div style={{
      width: '100%', height: '100%', background: '#0a0b0e',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: 16, boxSizing: 'border-box',
    }}>
      <TerminalChrome
        title="claude-bridge-tui"
        subtitle="13″ laptop · iTerm2"
        cols={120} rows={35}
      >
        {R(TUICompactContent())}
      </TerminalChrome>
    </div>
  );
}


// ==================== NARROW 80×24 ====================
// Single column. Tab strip at top, feed, mini send, status.

const NW = 78; // inner

function nTop()    { return [{ text: '╔' + rep('═', NW) + '╗', color: TC.border }, '\n']; }
function nBot()    { return [{ text: '╚' + rep('═', NW) + '╝', color: TC.border }, '\n']; }
function nDiv()    { return [{ text: '╠' + rep('═', NW) + '╣', color: TC.border }, '\n']; }
function nRow(c)   { return [V(), ...c, V(), '\n']; }
function nBlank()  { return [sp(NW)]; }

function nHeader() {
  return [
    ' ',
    { text: 'CLAUDE BRIDGE', color: TC.text, bold: true },
    ' ',
    { text: '●', color: TC.online },
    ' ',
    { text: ':8765', color: TC.textDim },
    ' ',
    { text: '5ch', color: TC.text }, ' ',
    { text: '565msg', color: TC.text },
    sp(NW - (1 + 13 + 1 + 1 + 1 + 5 + 1 + 3 + 1 + 6 + 8 + 1)),
    { text: '[?]help', color: TC.borderHi },
    ' ',
  ];
}

// Tab strip: shows channel names abbreviated
function nTabs() {
  const tabs = [
    { label: 'p:orch', count: 89,  active: true,  hot: true },
    { label: 'p:work', count: 112, active: false, hot: true },
    { label: 'p:evnt', count: 41,  active: false, hot: true },
    { label: 'g:sync', count: 5,   active: false, hot: false },
    { label: 's:hb',   count: 318, active: false, hot: false },
  ];
  const out = [' '];
  let used = 1;
  tabs.forEach((t_, i) => {
    if (t_.active) {
      const text = `▶ ${t_.label} ${t_.count} `;
      out.push(<span key={i} style={{background: TC.activeBg}}>{R([
        { text: '▶ ', color: TC.borderHi, bold: true },
        { text: t_.label, color: TC.text, bold: true },
        ' ',
        { text: String(t_.count), color: TC.text },
        ' ',
      ])}</span>);
      used += text.length;
    } else {
      const text = ` ${t_.label} ${t_.count}`;
      out.push({ text: t_.label, color: TC.textMid });
      out.push({ text: ` ${t_.count}`, color: TC.textDim });
      used += text.length;
      if (t_.hot) {
        out.push({ text: '●', color: TC.online });
        used += 1;
      }
      out.push(' ');
      used += 1;
    }
  });
  out.push(sp(NW - used));
  return out;
}

function nMessage(m, { selected = false } = {}) {
  // Narrow: drop seq, use shorter format
  // 1 gut + 1 chev + 7 sender + 1sp + 8 ts + 1sp + content
  const sender = m.sender.padEnd(7);
  const senderColor = SENDER_COLORS_TUI[m.sender] || TC.textMid;
  const typeColor = TYPE_COLORS[m.type] || TC.textDim;
  const contentBudget = NW - (1 + 1 + 7 + 1 + 8 + 1 + 1 + 6 + 1); // ~51
  let content = m.text;
  if (content.length > contentBudget) content = content.slice(0, contentBudget - 1) + '…';
  else content = content.padEnd(contentBudget);
  const inner = [
    ' ',
    selected ? { text: '▶', color: TC.borderHi, bold: true } : ' ',
    { text: sender, color: senderColor, bold: true },
    ' ',
    { text: m.ts, color: TC.textDim },
    ' ',
    { text: content, color: selected ? TC.text : TC.textMid },
    ' ',
    { text: m.type.padStart(6), color: typeColor, bold: true },
    ' ',
  ];
  if (selected) return [<span key="s" style={{background: TC.activeBg}}>{R(inner)}</span>];
  return inner;
}

function nSend() {
  const inner = [
    ' ', { text: '> ', color: TC.borderHi, bold: true },
    { text: '{"type":"task","phase":2}', color: TC.text },
    { text: '█', color: TC.borderHi },
    sp(NW - (1 + 2 + 25 + 1 + 1 + 8 + 1)),
    { text: '[mac→p:o]', color: TC.textDim }, ' ',
  ];
  return inner;
}

function nStatus() {
  const out = [' '];
  let used = 1;
  const keys = [['↑↓','nav'], ['Tab','tab'], ['S','send'], ['I','inspect'], ['Q','quit']];
  keys.forEach(([k,a]) => {
    out.push({ text: `[${k}]`, color: TC.borderHi, bold: true });
    out.push({ text: ` ${a}  `, color: TC.textMid });
    used += k.length + 2 + 1 + a.length + 2;
  });
  out.push(sp(NW - used - 7));
  out.push({ text: 'NORMAL', color: TC.online, bold: true });
  out.push(' ');
  return out;
}

function TUINarrowContent() {
  const out = [];
  out.push(...nTop());
  out.push(...nRow(nHeader()));
  out.push(...nDiv());
  out.push(...nRow(nTabs()));
  out.push(...nDiv());

  const msgs = MSGS.slice(-13);
  msgs.forEach(m => {
    out.push(...nRow(nMessage(m, { selected: m.seq === 52 })));
  });
  // we have 1+1+1+1+1+13 = 18 rows. Need 24 total. Add: send divider(1) + send(1) + status divider(1) + status(1) + bottom(1) = 5 rows. Plus padding 1.
  // Currently used: 1(top)+1(hdr)+1(div)+1(tabs)+1(div)+13(msgs) = 18. Need send block: 1 div + 1 send = 2. Then 1 div + 1 status + 1 bottom = 3. Total = 23. Need 1 more.
  out.push(...nRow(nBlank()));

  out.push(...nDiv());
  out.push(...nRow(nSend()));
  out.push(...nDiv());
  out.push(...nRow(nStatus()));
  out.push(...nBot());
  return out;
}

function TUINarrow() {
  return (
    <div style={{
      width: '100%', height: '100%', background: '#0a0b0e',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: 12, boxSizing: 'border-box',
    }}>
      <TerminalChrome title="bridge" subtitle="tmux pane" cols={80} rows={24}>
        {R(TUINarrowContent())}
      </TerminalChrome>
    </div>
  );
}

window.TUICompact = TUICompact;
window.TUINarrow = TUINarrow;
