// Full TUI layout — 220 cols × 50 rows.
// Centerpiece deliverable: every component rendered in one screen.

// Column geometry:
// pos 0=║  1..24=sidebar(24)  25=║  26..159=feed(134)  160=║  161..218=inspector(58)  219=║

// Render arbitrary fragments inline. Strings & numbers pass through; objects {text,color,bg,bold} become spans.
function R(frags) {
  return frags.map((f, i) => {
    if (f == null) return null;
    if (typeof f === 'string' || typeof f === 'number') return <React.Fragment key={i}>{f}</React.Fragment>;
    if (React.isValidElement(f)) return React.cloneElement(f, { key: i });
    return (
      <span key={i} style={{
        color: f.color || undefined,
        background: f.bg || undefined,
        fontWeight: f.bold ? 600 : undefined,
        fontStyle: f.italic ? 'italic' : undefined,
        textDecoration: f.underline ? 'underline' : undefined,
      }}>{f.text}</span>
    );
  });
}

// === ROW BUILDERS ===

// All cells are pre-padded to exact width by the caller.
// V = vertical border between columns (single char).
const V = () => ({ text: '║', color: TC.border });

// 3-col row
function row3(sidebar, feed, inspector) {
  return [V(), ...sidebar, V(), ...feed, V(), ...inspector, V(), '\n'];
}
// 2-col row (sidebar + send), after killing inspector col
function row2(sidebar, sendArea) {
  return [V(), ...sidebar, V(), ...sendArea, V(), '\n'];
}
// 1-col row (status bar)
function row1(content) {
  return [V(), ...content, V(), '\n'];
}

// ===== Sidebar cells (24 chars each) =====

const SB_W = 24;
// pad sidebar fragments to SB_W. fragments must NOT include border chars.
// We don't compute lengths automatically; each helper pre-pads itself.

const sbBlank = () => [sp(SB_W)];

const sbPanelHeader = () => [
  '  ',
  { text: 'CHANNELS', color: TC.text, bold: true },
  sp(SB_W - 2 - 8 - 4),
  { text: '5', color: TC.textMid },
  '  ',
];

const sbMeta = (str) => [
  '  ',
  { text: str, color: TC.textDim },
  sp(SB_W - 2 - str.length),
];

const sbHR = () => [
  '  ',
  { text: rep('─', SB_W - 4), color: TC.border },
  '  ',
];

const sbGroup = (label, total) => [
  ' ',
  { text: '▼', color: TC.textMid },
  ' ',
  { text: label + ':', color: TC.text, bold: true },
  sp(SB_W - 3 - (label.length + 1) - 1 - String(total).length - 2),
  { text: String(total), color: TC.textDim },
  '  ',
];

// Channel row. active=highlighted with bg + gutter mark.
const sbChannel = (name, count, { active = false, hot = false } = {}) => {
  // Format aim: "│▶ name(15) count(3) dot(2)  "
  const gutter = active ? { text: '█', color: TC.borderHi } : ' ';
  const chevron = active ? { text: '▶', color: TC.borderHi } : ' ';
  const namePart = name.slice(0, 15);
  const countStr = String(count).padStart(3, ' ');
  const dot = hot ? { text: '●', color: TC.online } : ' ';
  // 1(gutter)+1(chev)+1(sp)+15(name)+1(sp)+3(count)+1(sp)+1(dot) = 24
  const cell = [
    gutter, chevron, ' ',
    { text: namePart.padEnd(15), color: active ? TC.text : TC.textMid, bold: active },
    ' ',
    { text: countStr, color: active ? TC.text : TC.textDim },
    ' ',
    dot,
  ];
  if (active) {
    // wrap as a single bg span
    return [{ text: '', }, // placeholder; we'll wrap externally
    ];
  }
  return cell;
};

// Build an active channel row with bg highlight wrapping the cell
function sbChannelActive(name, count) {
  const namePart = name.slice(0, 15);
  const countStr = String(count).padStart(3, ' ');
  return [
    <span key="ch" style={{ background: TC.activeBg, color: TC.text }}>
      {R([
        { text: '█', color: TC.borderHi },
        { text: '▶', color: TC.borderHi },
        ' ',
        { text: namePart.padEnd(15), color: TC.text, bold: true },
        ' ',
        { text: countStr, color: TC.text },
        ' ',
        { text: '●', color: TC.online },
      ])}
    </span>,
  ];
}

// ===== Feed cells (134 chars wide) =====
const FD_W = 134;

const fdBlank = () => [sp(FD_W)];

// Header showing channel name + meta
const fdHeader = () => {
  const left = '  ';
  const label = 'FEED  ';
  const ch = 'pawprint:orchestrator';
  const meta = '  ·  89 messages  ·  2 senders  ·  last 14:32:19';
  const right = '[FOLLOWING]';
  const used = left.length + label.length + ch.length + meta.length + right.length;
  return [
    left,
    { text: label, color: TC.text, bold: true },
    { text: ch, color: TC.channel, bold: true },
    { text: meta, color: TC.textDim },
    sp(FD_W - used - 2),
    { text: right, color: TC.online },
    '  ',
  ];
};

// Column legend
const fdLegend = () => {
  const text = '   SEQ   SENDER    TIME       CONTENT';
  const right = 'TYPE';
  return [
    '  ',
    { text: text, color: TC.textDim },
    sp(FD_W - 2 - text.length - right.length - 4),
    { text: right, color: TC.textDim },
    '    ',
  ];
};

const fdHR = () => [
  '  ',
  { text: rep('─', FD_W - 4), color: TC.border },
  '  ',
];

// Message row in the feed.
// Layout (134 wide):
//   2 pad | 1 gutter | 4 seq "[XX]" | 2 sp | 7 sender pad | 2 sp | 8 ts | 2 sp | content 94 | 2 sp | 7 type | 3 pad
//   = 2+1+4+2+7+2+8+2+94+2+7+3 = 134
const fdMessage = (m, { selected = false } = {}) => {
  const seq = `[${String(m.seq).padStart(2, ' ')}]`;
  const sender = m.sender.padEnd(7);
  const senderColor = SENDER_COLORS_TUI[m.sender] || TC.textMid;
  const typeColor = TYPE_COLORS[m.type] || TC.textDim;

  const contentBudget = 94;
  let content = m.text;
  if (content.length > contentBudget) content = content.slice(0, contentBudget - 1) + '…';
  else content = content.padEnd(contentBudget);

  const typeStr = m.type.padStart(6).padEnd(7);

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
    '   ',
  ];

  if (selected) {
    return [
      <span key="sel" style={{ background: TC.activeBg }}>
        {R(inner)}
      </span>,
    ];
  }
  return inner;
};

// ===== Inspector cells (58 chars wide) =====
const IN_W = 58;

const inBlank = () => [sp(IN_W)];

const inHeader = () => [
  '  ',
  { text: 'INSPECTOR', color: TC.text, bold: true },
  sp(IN_W - 2 - 9 - 10 - 2),
  { text: 'msg 52/247', color: TC.textDim },
  '  ',
];

const inHR = () => [
  '  ',
  { text: rep('─', IN_W - 4), color: TC.border },
  '  ',
];

// kv row: label (10 chars) + value
const inKV = (k, v, vColor = TC.text) => {
  const used = 2 + 10 + 2 + v.length;
  return [
    '  ',
    { text: k.padEnd(10), color: TC.textDim },
    '  ',
    { text: v, color: vColor },
    sp(IN_W - used),
  ];
};

const inContentLabel = () => {
  const right = '156 B  ·  JSON';
  return [
    '  ',
    { text: 'CONTENT', color: TC.text, bold: true },
    sp(IN_W - 2 - 7 - right.length - 2),
    { text: right, color: TC.textDim },
    '  ',
  ];
};

// JSON box (50 chars wide: ┌+48+┐). Content area = 48 chars inside box, but each content line: "│ " + 46 + " │"
// Total cell: 2 indent + 50 box + 6 trailing = 58
const inBoxTop = () => [
  '  ',
  { text: '┌' + rep('─', 48) + '┐', color: TC.border },
  '      ',
];
const inBoxBottom = () => [
  '  ',
  { text: '└' + rep('─', 48) + '┘', color: TC.border },
  '      ',
];
const inBoxRow = (frags, len) => [
  '  ',
  { text: '│ ', color: TC.border },
  ...frags,
  sp(46 - len),
  { text: ' │', color: TC.border },
  '      ',
];
const inBoxRowText = (text, color = TC.text) => inBoxRow([{ text, color }], text.length);

const inActions = () => [
  '  ',
  { text: '[C]', color: TC.borderHi, bold: true }, ' ',
  { text: 'copy id', color: TC.textMid }, '   ',
  { text: '[Y]', color: TC.borderHi, bold: true }, ' ',
  { text: 'copy content', color: TC.textMid }, '   ',
  { text: '[R]', color: TC.borderHi, bold: true }, ' ',
  { text: 'reply', color: TC.textMid },
  sp(IN_W - (2 + 3 + 1 + 7 + 3 + 3 + 1 + 12 + 3 + 3 + 1 + 5)),
];

// ===== Send area (134 + 58 = 192 chars + 1 border = 193 total inner) =====
// After killing inspector column at row "div2", the send area is 193 chars wide.
// Actually after the 3→2 divider, sidebar col stays. Send area = 134 + 1 + 58 = 193.

const SEND_W = 134 + 1 + 58; // 193

const sendLabelRow = () => {
  // Send label cell (sidebar 24) shows "SEND"
  const sidebar = [
    '  ',
    { text: 'SEND', color: TC.text, bold: true },
    sp(SB_W - 2 - 4),
  ];
  // Send area shows: channel + sender
  const sendLine = [
    '  ',
    { text: 'channel: ', color: TC.textDim },
    { text: 'pawprint:orchestrator', color: TC.channel, bold: true },
    '      ',
    { text: 'from: ', color: TC.textDim },
    { text: 'mac', color: TC.mac, bold: true },
    '      ',
    { text: 'type: ', color: TC.textDim },
    { text: 'TASK', color: TC.task, bold: true },
    sp(SEND_W - (2 + 9 + 21 + 6 + 6 + 3 + 6 + 6 + 4 + 1)),
    { text: '✓ valid json', color: TC.online },
    '  ',
  ];
  return [sidebar, sendLine];
};

const sendInputRow = () => {
  const sidebar = [sp(SB_W)];
  const sendLine = [
    '  ',
    { text: '> ', color: TC.borderHi, bold: true },
    { text: '{ "type": "task", "phase": 3, "action": "extract_all", "matches": ["m-001", "m-002", "m-003"] }', color: TC.text },
    { text: '█', color: TC.borderHi }, // cursor block
    sp(SEND_W - (2 + 2 + 90 + 1) - 5),
    { text: '⌘↵', color: TC.textDim },
    '  ',
  ];
  return [sidebar, sendLine];
};

// ===== Status bar (218 cols inner) =====
const STATUS_W = 1 + 24 + 1 + 134 + 1 + 58; // 219 total inner of 220 row? No, inner = 218.
const STATUS_W_INNER = 218;
const statusBar = () => {
  const keys = [
    { k: '↑↓', a: 'navigate' },
    { k: 'Tab', a: 'panel' },
    { k: 'Enter', a: 'select' },
    { k: 'S', a: 'send' },
    { k: 'F', a: 'filter' },
    { k: 'C', a: 'clear' },
    { k: 'N', a: 'new channel' },
    { k: '/', a: 'search' },
    { k: '?', a: 'help' },
    { k: 'Q', a: 'quit' },
  ];
  const frags = ['  '];
  let used = 2;
  keys.forEach(({ k, a }) => {
    const pre = `[${k}]`;
    const after = ` ${a}   `;
    frags.push({ text: pre, color: TC.borderHi, bold: true });
    frags.push({ text: after, color: TC.textMid });
    used += pre.length + after.length;
  });
  // right side: NORMAL mode indicator
  const modeStr = 'MODE  NORMAL';
  used += modeStr.length + 2;
  frags.push(sp(STATUS_W_INNER - used));
  frags.push({ text: 'MODE  ', color: TC.textDim });
  frags.push({ text: 'NORMAL', color: TC.online, bold: true });
  frags.push('  ');
  return frags;
};

// ===== Header bar (218 cols inner) =====
const headerBar = () => {
  const frags = [];
  frags.push('  ');
  frags.push({ text: 'CLAUDE BRIDGE', color: TC.text, bold: true });
  frags.push('   ');
  frags.push({ text: '●', color: TC.online });
  frags.push({ text: 'ONLINE', color: TC.online, bold: true });
  frags.push('   ');
  frags.push({ text: ':8765', color: TC.textDim });
  frags.push('   ');
  frags.push({ text: 'uptime: ', color: TC.textDim });
  frags.push({ text: '00:14:32', color: TC.text });
  frags.push('   ');
  frags.push({ text: 'channels: ', color: TC.textDim });
  frags.push({ text: '5', color: TC.text });
  frags.push('   ');
  frags.push({ text: 'messages: ', color: TC.textDim });
  frags.push({ text: '565', color: TC.text });
  frags.push('   ');
  frags.push({ text: '↑/s p95: ', color: TC.textDim });
  frags.push({ text: '45ms', color: TC.online });
  // compute used
  let used = 2 + 13 + 3 + 1 + 6 + 3 + 5 + 3 + 8 + 8 + 3 + 10 + 1 + 3 + 10 + 3 + 3 + 9 + 4;
  const right = '[?] help';
  frags.push(sp(STATUS_W_INNER - used - right.length - 2));
  frags.push({ text: right, color: TC.borderHi });
  frags.push('  ');
  return frags;
};

// ===== Border rows =====
const topBorder = () => [
  { text: '╔' + rep('═', 218) + '╗', color: TC.border },
  '\n',
];
const div3Start = () => [
  { text: '╠' + rep('═', SB_W) + '╦' + rep('═', FD_W) + '╦' + rep('═', IN_W) + '╣', color: TC.border },
  '\n',
];
const div32 = () => [
  { text: '╠' + rep('═', SB_W) + '╬' + rep('═', FD_W) + '╩' + rep('═', IN_W) + '╣', color: TC.border },
  '\n',
];
const div21 = () => [
  { text: '╠' + rep('═', SB_W) + '╩' + rep('═', FD_W + 1 + IN_W) + '╣', color: TC.border },
  '\n',
];
const bottomBorder = () => [
  { text: '╚' + rep('═', 218) + '╝', color: TC.border },
  '\n',
];
const hRule3 = () => [
  V(), ...sbHR(), V(), ...fdHR(), V(), ...inHR(), V(), '\n',
];

// ===== ASSEMBLE FULL SCREEN =====

function FullTuiContent() {
  // Build sidebar 41 rows
  const sb = [];
  sb.push(sbPanelHeader());
  sb.push(sbMeta('5 active  ·  565 msgs'));
  sb.push(sbBlank());
  sb.push(sbHR());
  sb.push(sbBlank());

  sb.push(sbGroup('pawprint', 242));
  sb.push(sbChannelActive('orchestrator', 89));
  sb.push(sbChannel('worker', 112, { hot: true }));
  sb.push(sbChannel('events', 41, { hot: true }));
  sb.push(sbBlank());

  sb.push(sbGroup('general', 5));
  sb.push(sbChannel('sync', 5));
  sb.push(sbBlank());

  sb.push(sbGroup('system', 318));
  sb.push(sbChannel('heartbeat', 318));
  sb.push(sbBlank());

  sb.push(sbBlank());
  // ACTIVITY mini-sparkline section
  sb.push([
    '  ',
    { text: 'ACTIVITY', color: TC.text, bold: true },
    sp(SB_W - 2 - 8 - 6 - 2),
    { text: '60 sec', color: TC.textDim },
    '  ',
  ]);
  sb.push([
    '  ',
    { text: '▁▂▂▃▃▂▄▆▇█▇▆▄▃▂▂▂▃', color: TC.online },
    sp(SB_W - 2 - 18 - 2),
    '  ',
  ]);
  sb.push([
    '  ',
    { text: 'msg/s ', color: TC.textDim },
    { text: '12.4', color: TC.text },
    { text: '  peak ', color: TC.textDim },
    { text: '28', color: TC.text },
    sp(SB_W - 2 - 6 - 4 - 7 - 2 - 2),
    '  ',
  ]);
  sb.push(sbBlank());

  // recent senders
  sb.push([
    '  ',
    { text: 'SENDERS', color: TC.text, bold: true },
    sp(SB_W - 2 - 7 - 2),
    '  ',
  ]);
  sb.push([
    '  ',
    { text: '●', color: TC.shadow }, ' ',
    { text: 'shadow', color: TC.shadow }, '  ',
    { text: '267', color: TC.textDim },
    sp(SB_W - (2 + 1 + 1 + 6 + 2 + 3)),
  ]);
  sb.push([
    '  ',
    { text: '●', color: TC.mac }, ' ',
    { text: 'mac', color: TC.mac }, '     ',
    { text: '291', color: TC.textDim },
    sp(SB_W - (2 + 1 + 1 + 3 + 5 + 3)),
  ]);
  sb.push([
    '  ',
    { text: '●', color: TC.watcher }, ' ',
    { text: 'watcher', color: TC.watcher }, ' ',
    { text:  '7', color: TC.textDim },
    sp(SB_W - (2 + 1 + 1 + 7 + 1 + 2)),
  ]);
  sb.push(sbBlank());
  sb.push(sbBlank());

  // pad to 41
  while (sb.length < 41 - 3) sb.push(sbBlank());

  sb.push(sbHR());
  sb.push([
    '  ',
    { text: '[N]', color: TC.borderHi, bold: true }, ' ',
    { text: 'new channel', color: TC.textMid },
    sp(SB_W - (2 + 3 + 1 + 11)),
  ]);
  sb.push(sbBlank());

  // Build feed 41 rows
  const fd = [];
  fd.push(fdHeader());
  fd.push(fdHR());
  fd.push(fdLegend());
  fd.push(fdBlank());

  MSGS.forEach((m, idx) => {
    if (m.seq === 52) {
      fd.push(fdMessage(m, { selected: true }));
    } else {
      fd.push(fdMessage(m));
    }
  });

  fd.push(fdBlank());
  // selected message expanded preview within feed
  fd.push([
    '  ',
    { text: '└─', color: TC.borderHi },
    ' ',
    { text: 'expanded view in inspector  →', color: TC.textDim },
    sp(FD_W - (2 + 2 + 1 + 29)),
  ]);
  fd.push(fdBlank());

  // Activity rate row
  fd.push([
    '  ',
    { text: 'msg rate (last 60s) ', color: TC.textDim },
    { text: '▁▂▂▃▃▂▄▆▇█▇▆▄▃▂▂▂▃▅▅▆▇█▇▆▄▃▂▁▁', color: TC.online },
    '  ',
    { text: 'peak 28/s', color: TC.textMid },
    sp(FD_W - (2 + 20 + 30 + 2 + 9)),
  ]);

  // pad
  while (fd.length < 41 - 4) fd.push(fdBlank());

  // Final feed lines: separator + auto-scroll status
  fd.push(fdHR());
  fd.push([
    '  ',
    { text: '⏺ ', color: TC.online },
    { text: 'live  ', color: TC.online, bold: true },
    { text: 'auto-scroll on  ·  press [Space] to pause  ·  [/] to search', color: TC.textDim },
    sp(FD_W - (2 + 2 + 6 + 58 + 2)),
    { text: 'tail -f', color: TC.textDim },
    '  ',
  ]);
  fd.push(fdBlank());
  fd.push(fdBlank());

  // Build inspector 41 rows
  const ins = [];
  ins.push(inHeader());
  ins.push(inHR());
  ins.push(inBlank());
  ins.push(inKV('id', '01HX2K9PQ4R7VBN8MFGD3Y6XCA'));
  ins.push(inKV('seq', '52'));
  ins.push(inKV('sender', 'mac', TC.mac));
  ins.push(inKV('channel', 'pawprint:orchestrator', TC.channel));
  ins.push(inKV('time', '2026-05-27 14:32:19.847Z'));
  ins.push(inKV('latency', '+45ms', TC.online));
  ins.push(inKV('size', '156 B', TC.textMid));
  ins.push(inBlank());
  ins.push(inContentLabel());
  ins.push(inBoxTop());
  // JSON content lines inside box
  ins.push(inBoxRow([
    { text: '{', color: TC.jPunct },
  ], 1));
  ins.push(inBoxRow([
    { text: '  "type"', color: TC.jKey },
    { text: ': ', color: TC.jPunct },
    { text: '"result"', color: TC.jStr },
    { text: ',', color: TC.jPunct },
  ], 19));
  ins.push(inBoxRow([
    { text: '  "phase"', color: TC.jKey },
    { text: ': ', color: TC.jPunct },
    { text: '1', color: TC.jNum },
    { text: ',', color: TC.jPunct },
  ], 13));
  ins.push(inBoxRow([
    { text: '  "status"', color: TC.jKey },
    { text: ': ', color: TC.jPunct },
    { text: '"complete"', color: TC.jStr },
    { text: ',', color: TC.jPunct },
  ], 23));
  ins.push(inBoxRow([
    { text: '  "count"', color: TC.jKey },
    { text: ': ', color: TC.jPunct },
    { text: '14', color: TC.jNum },
    { text: ',', color: TC.jPunct },
  ], 14));
  ins.push(inBoxRow([
    { text: '  "artifacts"', color: TC.jKey },
    { text: ': ', color: TC.jPunct },
    { text: '[', color: TC.jPunct },
  ], 17));
  ins.push(inBoxRow([
    { text: '    "com.apple.finder"', color: TC.jStr },
    { text: ',', color: TC.jPunct },
  ], 23));
  ins.push(inBoxRow([
    { text: '    "com.apple.security"', color: TC.jStr },
  ], 24));
  ins.push(inBoxRow([
    { text: '  ]', color: TC.jPunct },
  ], 3));
  ins.push(inBoxRow([
    { text: '}', color: TC.jPunct },
  ], 1));
  ins.push(inBoxBottom());
  ins.push(inBlank());
  ins.push(inActions());
  ins.push(inBlank());
  ins.push(inHR());
  // PARSE breakdown
  ins.push([
    '  ',
    { text: 'SCHEMA', color: TC.text, bold: true },
    sp(IN_W - 2 - 6 - 2),
    '  ',
  ]);
  ins.push(inBlank());
  ins.push([
    '  ',
    { text: 'type    ', color: TC.textDim },
    { text: 'result.complete', color: TC.result },
    sp(IN_W - 2 - 8 - 15),
  ]);
  ins.push([
    '  ',
    { text: 'origin  ', color: TC.textDim },
    { text: 'mac.local', color: TC.mac },
    '  →  ',
    { text: 'shadow.pc', color: TC.shadow },
    sp(IN_W - 2 - 8 - 9 - 5 - 9),
  ]);
  ins.push([
    '  ',
    { text: 'recv    ', color: TC.textDim },
    { text: '23 subscribers', color: TC.text },
    sp(IN_W - 2 - 8 - 14),
  ]);
  // pad
  while (ins.length < 41) ins.push(inBlank());

  // Now assemble all rows
  const out = [];
  out.push(...topBorder());
  out.push(...row1(headerBar()));
  out.push(...div3Start());

  for (let i = 0; i < 41; i++) {
    out.push(...row3(sb[i] || sbBlank(), fd[i] || fdBlank(), ins[i] || inBlank()));
  }

  out.push(...div32());
  const [sbLbl, sndLbl] = sendLabelRow();
  out.push(...row2(sbLbl, sndLbl));
  const [sbInp, sndInp] = sendInputRow();
  out.push(...row2(sbInp, sndInp));
  out.push(...div21());
  out.push(...row1(statusBar()));
  out.push(...bottomBorder());

  return out;
}

function TUIFull() {
  return (
    <div style={{
      width: '100%', height: '100%', background: '#0a0b0e',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: 20, boxSizing: 'border-box',
    }}>
      <TerminalChrome
        title="claude-bridge-tui · python tui.py"
        subtitle="ssh://mac.local"
        cols={220} rows={50}
      >
        {R(FullTuiContent())}
      </TerminalChrome>
    </div>
  );
}

Object.assign(window, { TUIFull, R, V, row1, row2, row3,
  topBorder, bottomBorder, div3Start, div32, div21,
  SB_W, FD_W, IN_W, STATUS_W_INNER,
  sbBlank, sbPanelHeader, sbMeta, sbHR, sbGroup, sbChannel, sbChannelActive,
  fdBlank, fdHeader, fdHR, fdLegend, fdMessage,
  inBlank, inHeader, inHR, inKV, inContentLabel, inBoxTop, inBoxBottom, inBoxRow, inBoxRowText, inActions,
  headerBar, statusBar, sendLabelRow, sendInputRow,
});
