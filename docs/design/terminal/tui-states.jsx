// State variants — 4 mini TUI panels showing different modes.

// Width for the state crops
const SW = 158; // inner content width — wide enough to show meaningful feed
const STOTAL = SW + 2;

function sTop() { return [{text: '╔' + rep('═', SW) + '╗', color: TC.border}, '\n']; }
function sBot() { return [{text: '╚' + rep('═', SW) + '╝', color: TC.border}, '\n']; }
function sDiv() { return [{text: '╠' + rep('═', SW) + '╣', color: TC.border}, '\n']; }
function sRow(c) { return [V(), ...c, V(), '\n']; }
function sBlank() { return [sp(SW)]; }

function sHeader(state) {
  const isOffline = state === 'offline';
  const right = `MODE  ${state.toUpperCase()}`;
  const rightColor = state === 'normal' ? TC.online :
                     state === 'filter' ? TC.warn :
                     state === 'send'   ? TC.borderHi :
                     state === 'offline' ? TC.offline : TC.textMid;
  return [
    '  ',
    { text: 'CLAUDE BRIDGE', color: TC.text, bold: true }, '   ',
    isOffline
      ? <span key="o">{R([{text:'○', color: TC.offline}, {text:'OFFLINE', color: TC.offline, bold:true}])}</span>
      : <span key="n">{R([{text:'●', color: TC.online}, {text:'ONLINE', color: TC.online, bold:true}])}</span>,
    '   ',
    { text: ':8765', color: TC.textDim }, '   ',
    { text: 'uptime: ', color: TC.textDim },
    { text: isOffline ? '00:14:32 (frozen)' : '00:14:32', color: isOffline ? TC.textDim : TC.text },
    '   ',
    { text: 'channels: 5', color: TC.textMid }, '   ',
    { text: 'messages: 565', color: TC.textMid },
    sp(SW - (2 + 13 + 3 + 1 + 7 + 3 + 5 + 3 + 8 + (isOffline ? 17 : 8) + 3 + 11 + 3 + 13 + 6 + rightColor ? 0 : 0 + right.length + 2)),
    { text: 'MODE  ', color: TC.textDim },
    { text: state.toUpperCase(), color: rightColor, bold: true },
    '  ',
  ];
}

// Reusable mini message row, width 154 chars (SW - 4)
const SF_W = SW;
function sMsg(m, { selected = false, dim = false, highlight = null } = {}) {
  const senderColor = SENDER_COLORS_TUI[m.sender] || TC.textMid;
  const typeColor = TYPE_COLORS[m.type] || TC.textDim;
  const sender = m.sender.padEnd(7);
  const seq = `[${String(m.seq).padStart(2, ' ')}]`;
  const contentBudget = SF_W - (2 + 1 + 4 + 2 + 7 + 2 + 8 + 2 + 2 + 6 + 2);
  let content = m.text;
  if (content.length > contentBudget) content = content.slice(0, contentBudget - 1) + '…';
  else content = content.padEnd(contentBudget);

  // For highlight (filter match): wrap matching substring
  let contentNode = content;
  if (highlight && content.toLowerCase().includes(highlight.toLowerCase())) {
    const idx = content.toLowerCase().indexOf(highlight.toLowerCase());
    const before = content.slice(0, idx);
    const match = content.slice(idx, idx + highlight.length);
    const after = content.slice(idx + highlight.length);
    contentNode = (
      <>
        <span style={{ color: dim ? TC.textDim : TC.textMid }}>{before}</span>
        <span style={{ background: TC.warn, color: '#000', fontWeight: 600 }}>{match}</span>
        <span style={{ color: dim ? TC.textDim : TC.textMid }}>{after}</span>
      </>
    );
  }

  const inner = [
    '  ',
    selected ? { text: '▶', color: TC.borderHi, bold: true } : ' ',
    { text: seq, color: dim ? TC.textDim : TC.textDim },
    '  ',
    { text: sender, color: dim ? TC.textDim : senderColor, bold: !dim },
    '  ',
    { text: m.ts, color: TC.textDim },
    '  ',
    typeof contentNode === 'string'
      ? { text: contentNode, color: dim ? TC.textDim : (selected ? TC.text : TC.textMid) }
      : contentNode,
    '  ',
    { text: m.type.padStart(6), color: dim ? TC.textDim : typeColor, bold: !dim },
    '  ',
  ];
  if (selected) return [<span key="s" style={{background: TC.activeBg}}>{R(inner)}</span>];
  return inner;
}

// ========= STATE 1: FILTER MODE =========
function StateFilter() {
  // 16 rows: top, header, div, "FEED", filter bar, div, 8 messages (some dimmed), status, bottom
  const out = [];
  out.push(...sTop());
  out.push(...sRow(sHeader('filter')));
  out.push(...sDiv());
  out.push(...sRow([
    '  ', { text: 'FEED  ', color: TC.text, bold: true },
    { text: 'pawprint:orchestrator', color: TC.channel, bold: true },
    sp(SW - (2 + 6 + 21 + 12 + 2)),
    { text: '[PAUSED]', color: TC.warn, bold: true },
    '  ',
  ]));
  // Filter bar
  out.push(...sRow([
    '  ', { text: '/', color: TC.warn, bold: true },
    { text: 'result', color: TC.text }, { text: '█', color: TC.borderHi },
    sp(20),
    { text: 'matching: ', color: TC.textDim },
    { text: '2 of 8', color: TC.text },
    '   ',
    { text: 'sender:', color: TC.textDim }, { text: '*', color: TC.textMid },
    '  ', { text: 'type:', color: TC.textDim }, { text: '*', color: TC.textMid },
    sp(SW - (2 + 1 + 6 + 1 + 20 + 10 + 6 + 3 + 7 + 1 + 2 + 5 + 1 + 14)),
    { text: '[Enter] apply  [Esc] cancel', color: TC.textDim },
    '  ',
  ]));
  out.push(...sRow(['  ', { text: rep('─', SW - 4), color: TC.border }, '  ']));

  // Dim non-matching messages, highlight matches
  const filterMsgs = MSGS.slice(2);
  filterMsgs.forEach((m) => {
    const matches = m.text.toLowerCase().includes('result') || m.type === 'RESULT';
    out.push(...sRow(sMsg(m, { dim: !matches, highlight: matches ? 'result' : null, selected: m.seq === 52 })));
  });
  out.push(...sBot());
  return out;
}

// ========= STATE 2: SEND MODE =========
function StateSend() {
  const out = [];
  out.push(...sTop());
  out.push(...sRow(sHeader('send')));
  out.push(...sDiv());
  out.push(...sRow([
    '  ', { text: 'FEED  ', color: TC.text, bold: true },
    { text: 'pawprint:orchestrator', color: TC.channel, bold: true },
    sp(SW - (2 + 6 + 21 + 30 + 2)),
    { text: '⏺ live  ·  auto-scroll on', color: TC.online },
    '  ',
  ]));
  out.push(...sRow(['  ', { text: rep('─', SW - 4), color: TC.border }, '  ']));

  // Show recent messages
  MSGS.slice(-6).forEach((m) => {
    out.push(...sRow(sMsg(m, { selected: m.seq === 52 })));
  });
  out.push(...sRow(sBlank()));

  // Send bar with focus border (heavy ─━ doubled chars to indicate focus)
  out.push(...sRow([
    '  ', { text: '┏' + rep('━', SW - 6) + '┓', color: TC.borderHi },
    '  ',
  ]));
  out.push(...sRow([
    '  ',
    { text: '┃ ', color: TC.borderHi },
    { text: 'channel: ', color: TC.textDim },
    { text: 'pawprint:orchestrator', color: TC.channel, bold: true },
    '   ',
    { text: 'from: ', color: TC.textDim },
    { text: 'mac', color: TC.mac, bold: true },
    '   ',
    { text: 'type: ', color: TC.textDim },
    { text: 'TASK', color: TC.task, bold: true },
    sp(SW - (2 + 2 + 9 + 21 + 3 + 6 + 3 + 3 + 6 + 4 + 14 + 2 + 2)),
    { text: '✓ valid json', color: TC.online },
    { text: ' ┃', color: TC.borderHi },
    '  ',
  ]));
  out.push(...sRow([
    '  ',
    { text: '┃ ', color: TC.borderHi },
    { text: '> ', color: TC.borderHi, bold: true },
    { text: '{ "type": "task", "phase": 3, "action": "extract_all", "matches": ["m-001"]', color: TC.text },
    { text: '█', color: TC.borderHi },
    sp(SW - (2 + 2 + 2 + 76 + 1 + 2 + 2)),
    { text: ' ┃', color: TC.borderHi },
    '  ',
  ]));
  out.push(...sRow([
    '  ', { text: '┗' + rep('━', SW - 6) + '┛', color: TC.borderHi },
    '  ',
  ]));
  // Mode status bar
  out.push(...sRow([
    '  ',
    { text: '[↵]', color: TC.borderHi, bold: true }, ' ',
    { text: 'send  ', color: TC.textMid },
    { text: '[Esc]', color: TC.borderHi, bold: true }, ' ',
    { text: 'cancel  ', color: TC.textMid },
    { text: '[Tab]', color: TC.borderHi, bold: true }, ' ',
    { text: 'channel  ', color: TC.textMid },
    { text: '[↑]', color: TC.borderHi, bold: true }, ' ',
    { text: 'history  ', color: TC.textMid },
    { text: '[Ctrl+W]', color: TC.borderHi, bold: true }, ' ',
    { text: 'clear word', color: TC.textMid },
    sp(SW - (2 + 3 + 1 + 6 + 5 + 1 + 8 + 5 + 1 + 9 + 3 + 1 + 9 + 8 + 1 + 10 + 14)),
    { text: 'SEND MODE', color: TC.borderHi, bold: true },
    '  ',
  ]));
  out.push(...sBot());
  return out;
}

// ========= STATE 3: BRIDGE OFFLINE =========
function StateOffline() {
  const out = [];
  out.push(...sTop());
  out.push(...sRow(sHeader('offline')));
  // Pulsing offline banner
  out.push([{text: '╠' + rep('═', SW) + '╣', color: TC.offline}, '\n']);
  const bannerText = '  ◢◤  BRIDGE OFFLINE — reconnecting...  attempt 3 / 10  ·  last seen 14:32:19  ·  retry in 4s  ·  ';
  out.push(...sRow([
    <span key="b" style={{ background: 'rgba(248,81,73,0.12)' }}>
      {R([
        { text: bannerText, color: TC.offline, bold: true },
        sp(SW - bannerText.length - 13),
        { text: '[R] retry now', color: TC.offline, bold: true },
      ])}
    </span>,
  ]));
  out.push([{text: '╠' + rep('═', SW) + '╣', color: TC.offline}, '\n']);

  // Greyed-out feed
  out.push(...sRow([
    '  ', { text: 'FEED  ', color: TC.textDim, bold: true },
    { text: 'pawprint:orchestrator', color: TC.textDim },
    sp(SW - (2 + 6 + 21 + 16 + 2)),
    { text: '[disconnected]', color: TC.offline },
    '  ',
  ]));
  out.push(...sRow(['  ', { text: rep('─', SW - 4), color: TC.border }, '  ']));

  // Last received messages dimmed
  MSGS.slice(-5).forEach((m) => {
    out.push(...sRow(sMsg(m, { dim: true })));
  });
  // SYSTEM message
  out.push(...sRow([
    '  ',
    { text: '[SYSTEM] ', color: TC.warn, bold: true },
    { text: 'connection lost at 14:32:19 — feed paused, send disabled', color: TC.warn },
    sp(SW - (2 + 9 + 58 + 2)),
    '  ',
  ]));

  out.push(...sRow(sBlank()));
  // Disabled send bar
  out.push(...sRow([
    '  ', { text: '┌' + rep('─', SW - 6) + '┐', color: TC.textDim },
    '  ',
  ]));
  out.push(...sRow([
    '  ', { text: '│ ', color: TC.textDim },
    { text: '> ', color: TC.textDim },
    { text: '[bridge offline — cannot send]', color: TC.offline },
    sp(SW - (2 + 2 + 2 + 30 + 2 + 2)),
    { text: ' │', color: TC.textDim },
    '  ',
  ]));
  out.push(...sRow([
    '  ', { text: '└' + rep('─', SW - 6) + '┘', color: TC.textDim },
    '  ',
  ]));
  out.push(...sBot());
  return out;
}

// ========= STATE 4: HELP OVERLAY =========
function StateHelp() {
  const out = [];
  out.push(...sTop());
  out.push(...sRow(sHeader('help')));
  out.push(...sDiv());

  // Background dimmed pattern
  const dimRow = () => [
    '  ',
    { text: '░'.repeat(SW - 4), color: TC.textDim },
    '  ',
  ];

  // Overlay box: ~80 chars wide, centered
  const BOX_W = 96;
  const sidePad = Math.floor((SW - BOX_W) / 2);
  const padL = sp(sidePad);
  const padR = sp(SW - sidePad - BOX_W);

  const boxRow = (content, contentWidth) => [
    padL,
    { text: '║', color: TC.borderHi },
    ...content,
    sp(BOX_W - 2 - contentWidth),
    { text: '║', color: TC.borderHi },
    padR,
  ];

  out.push(...sRow([
    padL, { text: '╔' + rep('═', BOX_W - 2) + '╗', color: TC.borderHi }, padR,
  ]));
  out.push(...sRow(boxRow([
    sp(28),
    { text: 'CLAUDE BRIDGE  ·  HELP', color: TC.text, bold: true },
    sp(28),
  ], 28 + 22 + 28)));
  out.push(...sRow([
    padL, { text: '╠' + rep('═', BOX_W - 2) + '╣', color: TC.borderHi }, padR,
  ]));
  // Two columns inside box: 44 + 4 + 44 = 92 + 2 borders = 94, plus padding 1 each side = 96 ✓
  const helpRow = (l, r) => sRow(boxRow([
    ' ',
    ...renderHelpCol(l, 44),
    '  ',
    ...renderHelpCol(r, 44),
    ' ',
  ], 1 + 44 + 2 + 44 + 1));

  // Section header row
  const sectionRow = (lTitle, rTitle) => sRow(boxRow([
    ' ',
    { text: lTitle, color: TC.warn, bold: true },
    sp(44 - lTitle.length),
    '  ',
    { text: rTitle, color: TC.warn, bold: true },
    sp(44 - rTitle.length),
    ' ',
  ], 1 + 44 + 2 + 44 + 1));

  out.push(...sectionRow('NAVIGATION', 'ACTIONS'));
  out.push(...helpRow(['↑↓', 'move'], ['S', 'send message']));
  out.push(...helpRow(['Tab', 'next panel'], ['C', 'clear channel']));
  out.push(...helpRow(['Enter', 'select'], ['F', 'filter feed']));
  out.push(...helpRow(['Esc', 'back'], ['N', 'new channel']));
  out.push(...helpRow([' ', ' '], ['R', 'reply to channel']));
  out.push(...sRow(boxRow([sp(BOX_W - 2)], BOX_W - 2)));
  out.push(...sectionRow('FEED', 'INSPECTOR'));
  out.push(...helpRow(['Space', 'pause scroll'], ['Space', 'expand JSON']));
  out.push(...helpRow(['/', 'search'], ['C', 'copy id']));
  out.push(...helpRow(['Ctrl+C', 'quit'], ['Y', 'copy content']));
  out.push(...sRow(boxRow([sp(BOX_W - 2)], BOX_W - 2)));
  out.push(...sRow(boxRow([
    sp(20),
    { text: 'press ', color: TC.textDim },
    { text: '[Esc]', color: TC.borderHi, bold: true },
    { text: ' or ', color: TC.textDim },
    { text: '[?]', color: TC.borderHi, bold: true },
    { text: ' to close', color: TC.textDim },
    sp(BOX_W - 2 - 20 - 6 - 5 - 4 - 3 - 9),
  ], BOX_W - 2)));
  out.push(...sRow([
    padL, { text: '╚' + rep('═', BOX_W - 2) + '╝', color: TC.borderHi }, padR,
  ]));
  out.push(...sBot());
  return out;
}

function renderHelpCol([k, label], width) {
  const padded = `[${k}]`.padEnd(8);
  return [
    { text: padded, color: TC.borderHi, bold: true },
    { text: label, color: TC.text },
    sp(width - 8 - label.length),
  ];
}

// ========= ASSEMBLE STATE PANEL =========

function StatePanel({ title, subtitle, children }) {
  return (
    <div style={{ flex: 1, minWidth: 0 }}>
      <div style={{
        display: 'flex', alignItems: 'baseline', gap: 12,
        marginBottom: 10,
      }}>
        <Eyebrow color={TC.borderHi} size={11}>{title}</Eyebrow>
        <span style={{
          fontFamily: 'var(--mono)', fontSize: 11, color: TC.textMid,
        }}>{subtitle}</span>
      </div>
      <TerminalChrome title="claude-bridge-tui" subtitle={title.toLowerCase()} cols={160} rows={20}>
        {children}
      </TerminalChrome>
    </div>
  );
}

function TUIStates() {
  return (
    <div style={{
      width: '100%', height: '100%',
      background: '#0a0b0e', padding: '32px 36px',
      boxSizing: 'border-box', overflow: 'hidden',
    }}>
      <div style={{ marginBottom: 24 }}>
        <Eyebrow color={TC.borderHi} size={11}>TUI · STATE VARIANTS</Eyebrow>
        <h2 style={{
          margin: '6px 0 4px',
          fontFamily: "'IBM Plex Mono', monospace", fontSize: 26, fontWeight: 700,
          color: TC.text, letterSpacing: '-0.01em',
        }}>Four modes, one layout</h2>
        <p style={{ margin: 0, color: TC.textMid, fontSize: 13, fontFamily: 'var(--sans)' }}>
          The same panels respond to mode. Filter dims non-matching rows; send shifts focus to the input;
          offline freezes the feed and paints a banner; help draws an overlay.
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        <StatePanel title="FILTER MODE" subtitle="/result — matching 2 of 8">
          {R(StateFilter())}
        </StatePanel>
        <StatePanel title="SEND MODE" subtitle="focus on input, history & tab-complete">
          {R(StateSend())}
        </StatePanel>
        <StatePanel title="BRIDGE OFFLINE" subtitle="auto-retry 3/10, feed frozen, send disabled">
          {R(StateOffline())}
        </StatePanel>
        <StatePanel title="HELP OVERLAY" subtitle="press [?] anywhere, [Esc] to dismiss">
          {R(StateHelp())}
        </StatePanel>
      </div>
    </div>
  );
}

window.TUIStates = TUIStates;
