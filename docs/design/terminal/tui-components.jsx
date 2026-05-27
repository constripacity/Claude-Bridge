// TUI component sheet — characters, colors, spacing for each piece.

const CompCard = ({ title, sub, children, span = 1 }) => (
  <div style={{
    gridColumn: `span ${span}`,
    background: '#0e1218', border: `1px solid ${TC.border}`,
    borderRadius: 4, padding: '18px 20px',
  }}>
    <div style={{
      display: 'flex', alignItems: 'baseline', justifyContent: 'space-between',
      marginBottom: 14, paddingBottom: 10,
      borderBottom: `1px solid ${TC.border}`,
    }}>
      <Eyebrow color={TC.text} size={11} style={{ fontWeight: 600 }}>{title}</Eyebrow>
      {sub && <span style={{
        fontFamily: "'IBM Plex Mono', monospace", fontSize: 10, color: TC.textDim,
      }}>{sub}</span>}
    </div>
    {children}
  </div>
);

const Mono = ({ children, color = TC.text, size = 12, bg, bold }) => (
  <span style={{
    fontFamily: "'IBM Plex Mono', monospace", fontSize: size, color, background: bg,
    fontWeight: bold ? 600 : 400, whiteSpace: 'pre',
  }}>{children}</span>
);

const Block = ({ children, height }) => (
  <pre style={{
    margin: 0, fontFamily: "'IBM Plex Mono', monospace", fontSize: 12,
    lineHeight: 1.32, color: TC.text, background: TC.bg,
    padding: '8px 10px', borderRadius: 3, border: `1px solid ${TC.border}`,
    whiteSpace: 'pre', height,
  }}>{children}</pre>
);

const Label = ({ children, c = TC.textDim }) => (
  <div style={{
    fontFamily: "'IBM Plex Mono', monospace", fontSize: 10, color: c,
    letterSpacing: '0.12em', textTransform: 'uppercase', marginBottom: 6,
  }}>{children}</div>
);

function ChannelRowStates() {
  return (
    <Block>
{R([
  { text: '  default state', color: TC.textDim }, '\n',
  ' ', '  ', { text: 'orchestrator   ', color: TC.textMid }, { text: ' 89', color: TC.textDim }, ' ', '\n',
  '\n',
  { text: '  hover (cursor on row)', color: TC.textDim }, '\n',
  <span key="h" style={{ background: '#161b22' }}>{R([
    ' ', '  ', { text: 'orchestrator   ', color: TC.text }, { text: ' 89', color: TC.textDim }, ' ',
  ])}</span>, '\n',
  '\n',
  { text: '  active (selected channel)', color: TC.textDim }, '\n',
  <span key="a" style={{ background: TC.activeBg }}>{R([
    { text: '█', color: TC.borderHi },
    { text: '▶', color: TC.borderHi },
    ' ',
    { text: 'orchestrator   ', color: TC.text, bold: true },
    { text: ' 89', color: TC.text },
    ' ',
    { text: '●', color: TC.online },
  ])}</span>, '\n',
  '\n',
  { text: '  new-message flash (~500 ms)', color: TC.textDim }, '\n',
  <span key="f" style={{ background: TC.flashBg }}>{R([
    ' ', '  ', { text: 'events         ', color: TC.text }, { text: ' 41', color: TC.text }, ' ',
    { text: '●', color: TC.online },
  ])}</span>, '\n',
  '\n',
  { text: '  with activity sparkline (last 8s)', color: TC.textDim }, '\n',
  ' ', '  ', { text: 'worker         ', color: TC.textMid }, { text: '112', color: TC.textDim }, ' ',
  { text: '▃▄▆██▇▆▅', color: TC.online }, '\n',
])}
    </Block>
  );
}

function MessageRowStates() {
  const msg = MSGS[10]; // selected
  const row = (m, opts = {}) => {
    const senderColor = SENDER_COLORS_TUI[m.sender] || TC.textMid;
    const typeColor = TYPE_COLORS[m.type] || TC.textDim;
    const inner = [
      opts.selected ? { text: '▶', color: TC.borderHi, bold: true } : ' ',
      { text: `[${String(m.seq).padStart(2)}]`, color: opts.dim ? TC.textDim : TC.textDim },
      '  ',
      { text: m.sender.padEnd(7), color: opts.dim ? TC.textDim : senderColor, bold: !opts.dim },
      '  ',
      { text: m.ts, color: TC.textDim },
      '  ',
      { text: (m.text.slice(0, 50) + (m.text.length > 50 ? '…' : '')).padEnd(50), color: opts.dim ? TC.textDim : (opts.selected ? TC.text : TC.textMid) },
      '  ',
      { text: m.type.padStart(6), color: opts.dim ? TC.textDim : typeColor, bold: !opts.dim },
    ];
    if (opts.selected) return <span style={{background: TC.activeBg}}>{R(inner)}</span>;
    if (opts.flash) return <span style={{background: TC.flashBg}}>{R(inner)}</span>;
    return R(inner);
  };
  return (
    <Block>
{R([
  { text: '  ' }, { text: 'normal', color: TC.textDim }, '\n',
  row(MSGS[4]), '\n',
  '\n',
  { text: '  ' }, { text: 'hover', color: TC.textDim }, '\n',
  <span key="h" style={{background:'#161b22'}}>{row(MSGS[4])}</span>, '\n',
  '\n',
  { text: '  ' }, { text: 'selected (with gutter + bg)', color: TC.textDim }, '\n',
  row(MSGS[10], { selected: true }), '\n',
  '\n',
  { text: '  ' }, { text: 'new arrival (200ms flash)', color: TC.textDim }, '\n',
  row(MSGS[7], { flash: true }), '\n',
  '\n',
  { text: '  ' }, { text: 'filtered out (dimmed)', color: TC.textDim }, '\n',
  row(MSGS[3], { dim: true }), '\n',
])}
    </Block>
  );
}

function MessageTypes() {
  const samples = [
    { type: 'TASK',   text: '{ "type": "task", "phase": 2, "action": "scan" }' },
    { type: 'RESULT', text: '{ "type": "result", "phase": 1, "count": 14 }' },
    { type: 'ACK',    text: '{ "type": "ack", "phase": 2, "status": "ok" }' },
    { type: 'ERR',    text: '{ "type": "error", "code": 503, "msg": "timeout" }' },
    { type: 'HB',     text: '{ "type": "heartbeat", "progress": 0.27 }' },
    { type: 'TXT',    text: 'show me the first match once you hit imap_export' },
  ];
  return (
    <Block>
{R(samples.flatMap(s => [
  ' ',
  { text: s.type.padStart(6), color: TYPE_COLORS[s.type], bold: true },
  '   ',
  { text: s.text.slice(0, 60).padEnd(60), color: TC.textMid },
  '\n',
]))}
    </Block>
  );
}

function SparklineRow() {
  return (
    <Block>
{R([
  { text: '  spark blocks   ', color: TC.textDim },
  { text: '▁▂▃▄▅▆▇█', color: TC.online }, '\n',
  '\n',
  { text: '  msg-rate over last 60s', color: TC.textDim }, '\n',
  ' ', { text: '▁▂▂▃▃▂▄▆▇█▇▆▄▃▂▂▂▃▅▅▆▇█▇▆▄▃▂▁▁', color: TC.online }, '\n',
  '\n',
  { text: '  progress bar', color: TC.textDim }, '\n',
  ' ', { text: '████████████████░░░░░░░░░░', color: TC.borderHi },
  '  ', { text: '62%', color: TC.text }, '\n',
  '\n',
  { text: '  loading bar', color: TC.textDim }, '\n',
  ' ', { text: '▒▒▓███████▓▒░         ', color: TC.warn }, '\n',
])}
    </Block>
  );
}

function BorderSet() {
  return (
    <Block>
{R([
  { text: '  primary panel (double)', color: TC.textDim }, '\n',
  '  ', { text: '╔══════════════════╗', color: TC.border }, '\n',
  '  ', { text: '║', color: TC.border }, '   header / chrome  ', { text: '║', color: TC.border }, '\n',
  '  ', { text: '╠══════════════════╣', color: TC.border }, '\n',
  '  ', { text: '║', color: TC.border }, '   content          ', { text: '║', color: TC.border }, '\n',
  '  ', { text: '╚══════════════════╝', color: TC.border }, '\n',
  '\n',
  { text: '  secondary box (single)', color: TC.textDim }, '\n',
  '  ', { text: '┌──────────────────┐', color: TC.border }, '\n',
  '  ', { text: '│', color: TC.border }, '   inspector json   ', { text: '│', color: TC.border }, '\n',
  '  ', { text: '└──────────────────┘', color: TC.border }, '\n',
  '\n',
  { text: '  focused send (heavy)', color: TC.textDim }, '\n',
  '  ', { text: '┏━━━━━━━━━━━━━━━━━━┓', color: TC.borderHi }, '\n',
  '  ', { text: '┃', color: TC.borderHi }, '  ', { text: '> _', color: TC.text }, '              ', { text: '┃', color: TC.borderHi }, '\n',
  '  ', { text: '┗━━━━━━━━━━━━━━━━━━┛', color: TC.borderHi }, '\n',
  '\n',
  { text: '  T-junctions  ', color: TC.textDim },
  { text: '╠ ╣ ╦ ╩ ╬   ├ ┤ ┬ ┴ ┼', color: TC.border }, '\n',
])}
    </Block>
  );
}

function StatusIndicators() {
  return (
    <Block>
{R([
  ' ',
  { text: '●', color: TC.online },
  { text: 'ONLINE', color: TC.online, bold: true },
  '         ', { text: 'server reachable, SSE attached', color: TC.textDim }, '\n',
  ' ',
  { text: '◑', color: TC.warn },
  { text: 'CONNECTING', color: TC.warn, bold: true },
  '     ', { text: 'mid-handshake, < 2s', color: TC.textDim }, '\n',
  ' ',
  { text: '○', color: TC.offline },
  { text: 'OFFLINE', color: TC.offline, bold: true },
  '        ', { text: 'no response, auto-retry on', color: TC.textDim }, '\n',
  ' ',
  { text: '◢◤', color: TC.offline, bold: true },
  { text: 'RECONNECTING', color: TC.offline, bold: true },
  '   ', { text: 'banner pulses 600 ms', color: TC.textDim }, '\n',
  '\n',
  ' ', { text: '⏺', color: TC.online }, ' ', { text: 'live', color: TC.online, bold: true },
  '             ', { text: 'feed auto-scrolls, [Space] pauses', color: TC.textDim }, '\n',
  ' ', { text: '⏸', color: TC.warn }, ' ', { text: '[PAUSED]', color: TC.warn, bold: true },
  '         ', { text: 'user scrolled up, manual mode', color: TC.textDim }, '\n',
  ' ', { text: '🔒', color: TC.online }, ' ', { text: 'FOLLOWING', color: TC.online },
  '         ', { text: 'pinned to bottom even on switch', color: TC.textDim }, '\n',
])}
    </Block>
  );
}

function JsonSyntax() {
  return (
    <Block>
{R([
  '  ', { text: '{', color: TC.jPunct }, '\n',
  '    ', { text: '"type"', color: TC.jKey },
  { text: ': ', color: TC.jPunct },
  { text: '"result"', color: TC.jStr },
  { text: ',', color: TC.jPunct }, '\n',
  '    ', { text: '"phase"', color: TC.jKey },
  { text: ': ', color: TC.jPunct },
  { text: '1', color: TC.jNum },
  { text: ',', color: TC.jPunct }, '\n',
  '    ', { text: '"complete"', color: TC.jKey },
  { text: ': ', color: TC.jPunct },
  { text: 'true', color: TC.jBool },
  { text: ',', color: TC.jPunct }, '\n',
  '    ', { text: '"error"', color: TC.jKey },
  { text: ': ', color: TC.jPunct },
  { text: 'null', color: TC.jNull },
  { text: ',', color: TC.jPunct }, '\n',
  '    ', { text: '"count"', color: TC.jKey },
  { text: ': ', color: TC.jPunct },
  { text: '14.5e3', color: TC.jNum }, '\n',
  '  ', { text: '}', color: TC.jPunct }, '\n',
  '\n',
  { text: '  collapsed key:', color: TC.textDim }, '\n',
  '  ', { text: '▶ ', color: TC.borderHi },
  { text: '"artifacts"', color: TC.jKey },
  { text: ': ', color: TC.jPunct },
  { text: '[...]', color: TC.jPunct },
  '   ', { text: '(2 items)', color: TC.textDim }, '\n',
])}
    </Block>
  );
}

function ColorTable() {
  const rows = [
    ['--bg',           TC.bg,        'terminal canvas'],
    ['--border',       TC.border,    'panel borders'],
    ['--border-hi',    TC.borderHi,  'active / focused panel'],
    ['--text',         TC.text,      'primary'],
    ['--text-mid',     TC.textMid,   'body, labels'],
    ['--text-dim',     TC.textDim,   'seq, timestamps'],
    ['--shadow',       TC.shadow,    'sender · shadow'],
    ['--mac',          TC.mac,       'sender · mac'],
    ['--channel',      TC.channel,   'channel names'],
    ['--task',         TC.task,      'type · TASK'],
    ['--result',       TC.result,    'type · RESULT'],
    ['--ack',          TC.ack,       'type · ACK'],
    ['--err',          TC.err,       'type · ERR'],
    ['--hb',           TC.hb,        'type · HB'],
    ['--online',       TC.online,    'status · online'],
    ['--offline',      TC.offline,   'status · offline'],
    ['--warn',         TC.warn,      'warn / claude'],
    ['--active-bg',    TC.activeBg,  'selected row bg'],
    ['--flash-bg',     TC.flashBg,   'new-msg flash bg'],
  ];
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 0 }}>
      {rows.map(([name, val, use]) => (
        <div key={name} style={{
          display: 'grid', gridTemplateColumns: '20px 1fr 1fr',
          gap: 8, alignItems: 'center', padding: '5px 0',
          borderBottom: `1px solid ${TC.border}`,
        }}>
          <span style={{
            width: 16, height: 16, background: val, display: 'inline-block',
            border: '1px solid #30363d',
          }} />
          <Mono color={TC.text} size={11}>{name}</Mono>
          <Mono color={TC.textDim} size={11}>{use}</Mono>
        </div>
      ))}
    </div>
  );
}

function CharsetReference() {
  return (
    <Block>
{R([
  { text: '  box (double)  ', color: TC.textDim },
  { text: '╔═╗ ║ ╠═╬═╣ ╚═╝', color: TC.text },
  { text: '   U+2550..2569', color: TC.textDim }, '\n',
  { text: '  box (single)  ', color: TC.textDim },
  { text: '┌─┐ │ ├─┼─┤ └─┘', color: TC.text },
  { text: '   U+2500..253C', color: TC.textDim }, '\n',
  { text: '  box (heavy)   ', color: TC.textDim },
  { text: '┏━┓ ┃ ┣━╋━┫ ┗━┛', color: TC.text },
  { text: '   U+2501..254B', color: TC.textDim }, '\n',
  { text: '  blocks        ', color: TC.textDim },
  { text: '█▓▒░ ▁▂▃▄▅▆▇█', color: TC.text },
  { text: '   U+2580..259F', color: TC.textDim }, '\n',
  { text: '  arrows        ', color: TC.textDim },
  { text: '▶ ◀ ▲ ▼ ▷ ◁ → ←', color: TC.text },
  { text: '   U+25B0..25BD', color: TC.textDim }, '\n',
  { text: '  status        ', color: TC.textDim },
  { text: '● ○ ◐ ◑ ◢◤ ⏺ ⏸', color: TC.text },
  { text: '   U+25CF / 23FA', color: TC.textDim }, '\n',
])}
    </Block>
  );
}

function TUIComponents() {
  return (
    <div style={{
      width: '100%', height: '100%',
      background: '#0a0b0e', padding: '36px 40px',
      boxSizing: 'border-box', overflow: 'hidden',
      color: TC.text, fontFamily: 'var(--sans)',
    }}>
      <div style={{
        marginBottom: 24, paddingBottom: 18,
        borderBottom: `1px solid ${TC.border}`,
        display: 'flex', alignItems: 'baseline', justifyContent: 'space-between',
      }}>
        <div>
          <Eyebrow color={TC.borderHi} size={11}>TUI · COMPONENT SHEET</Eyebrow>
          <h2 style={{
            margin: '6px 0 4px',
            fontFamily: "'IBM Plex Mono', monospace", fontSize: 28, fontWeight: 700,
            color: TC.text, letterSpacing: '-0.01em',
          }}>Every character. Every color.</h2>
          <p style={{ margin: 0, color: TC.textMid, fontSize: 13, fontFamily: 'var(--sans)' }}>
            All states for every component, plus the Unicode set we draw with.
            Match these and the rendering will match any reference frame.
          </p>
        </div>
        <div style={{
          fontFamily: "'IBM Plex Mono', monospace", fontSize: 11, color: TC.textDim,
          textAlign: 'right',
        }}>
          <div>textual.css  +  rich.theme</div>
          <div style={{ color: '#5a6470', marginTop: 4 }}>19 tokens · 6 type colors · 4 status icons</div>
        </div>
      </div>

      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16,
      }}>
        <CompCard title="CHANNEL ROW" sub="5 states">
          <ChannelRowStates />
        </CompCard>
        <CompCard title="MESSAGE ROW" sub="normal · hover · selected · flash · dim">
          <MessageRowStates />
        </CompCard>
        <CompCard title="MESSAGE TYPES" sub="6 type tags + their colors">
          <MessageTypes />
        </CompCard>

        <CompCard title="SPARKLINES & BARS" sub="▁▂▃▄▅▆▇█  ░▒▓█">
          <SparklineRow />
        </CompCard>
        <CompCard title="BORDER STYLES" sub="double · single · heavy">
          <BorderSet />
        </CompCard>
        <CompCard title="STATUS INDICATORS" sub="connection · feed · follow">
          <StatusIndicators />
        </CompCard>

        <CompCard title="JSON SYNTAX" sub="inspector content rendering">
          <JsonSyntax />
        </CompCard>
        <CompCard title="UNICODE SET" sub="exact characters used">
          <CharsetReference />
        </CompCard>
        <CompCard title="COLOR TOKENS" sub="ANSI true-color · CSS-named">
          <ColorTable />
        </CompCard>
      </div>
    </div>
  );
}

window.TUIComponents = TUIComponents;
