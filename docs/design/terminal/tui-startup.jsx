// Startup sequence — 4 frames showing the launch animation progression.

// Centered startup box, ~46 chars wide, ~14 rows tall.
// Each frame shows the box on a "blank terminal" backdrop.

function StartupFrame({ frame }) {
  const BW = 46;
  const TOP = '┌' + rep('─', BW - 2) + '┐';
  const BOT = '└' + rep('─', BW - 2) + '┘';
  const HR  = '├' + rep('─', BW - 2) + '┤';

  // Inner content width = BW - 4 (with 1px padding inside)
  const IW = BW - 4;

  const center = (str, w = IW) => {
    const pad = w - str.length;
    const l = Math.floor(pad / 2);
    return sp(l) + str + sp(pad - l);
  };

  const line = (fragments, len) => [
    { text: '│ ', color: TC.border },
    ...fragments,
    sp(IW - len),
    { text: ' │', color: TC.border },
    '\n',
  ];
  const blank = () => [
    { text: '│', color: TC.border },
    sp(BW - 2),
    { text: '│', color: TC.border },
    '\n',
  ];

  // Frame-specific data
  // Frame 1: connecting (10%)
  // Frame 2: server online ✓, loading channels (60%)
  // Frame 3: channels loaded ✓, syncing messages (90%)
  // Frame 4: success — about to transition
  const data = {
    1: { pct: 10, msg: 'connecting to :8765...',
         steps: [
           { state: 'pending', text: 'server online' },
           { state: 'pending', text: 'channels loaded' },
           { state: 'pending', text: 'messages synced' },
         ] },
    2: { pct: 45, msg: 'loading channels...',
         steps: [
           { state: 'ok', text: 'server online' },
           { state: 'loading', text: 'loading channels  (3/5)' },
           { state: 'pending', text: 'messages synced' },
         ] },
    3: { pct: 85, msg: 'syncing message log...',
         steps: [
           { state: 'ok', text: 'server online' },
           { state: 'ok', text: '5 channels loaded' },
           { state: 'loading', text: '481 / 565 messages synced' },
         ] },
    4: { pct: 100, msg: 'ready  ·  transitioning...',
         steps: [
           { state: 'ok', text: 'server online' },
           { state: 'ok', text: '5 channels loaded' },
           { state: 'ok', text: '565 messages synced' },
         ] },
  }[frame];

  const barFilled = Math.floor((IW - 6) * data.pct / 100);
  const barEmpty = (IW - 6) - barFilled;
  const pctStr = `${data.pct}%`.padStart(4);

  const STEP_ICON = {
    ok:      { ch: '✓', color: TC.online },
    loading: { ch: '◐', color: TC.warn },
    pending: { ch: '·', color: TC.textDim },
  };
  const STEP_TEXT = {
    ok:      TC.text,
    loading: TC.text,
    pending: TC.textDim,
  };

  const out = [];
  // Top border
  out.push({ text: TOP, color: TC.border }, '\n');
  // Title row
  out.push(...line([
    { text: center('CLAUDE BRIDGE'), color: TC.text, bold: true },
  ], IW));
  // Subtitle
  out.push(...line([
    { text: center('v0.3.1  ·  starting'), color: TC.textDim },
  ], IW));
  out.push({ text: HR, color: TC.border }, '\n');
  out.push(...blank());
  // Status message
  out.push(...line([
    { text: '  ', },
    { text: data.msg, color: TC.text },
    sp(IW - 2 - data.msg.length),
  ], IW));
  out.push(...blank());
  // Progress bar: "  " + "█████░░░░░  45%"
  out.push(...line([
    '  ',
    { text: rep('█', barFilled), color: frame === 4 ? TC.online : TC.borderHi },
    { text: rep('░', barEmpty), color: TC.textDim },
    '  ',
    { text: pctStr, color: TC.text },
  ], 2 + (IW - 6) + 2 + pctStr.length));
  out.push(...blank());
  // Steps
  data.steps.forEach((s) => {
    const icon = STEP_ICON[s.state];
    out.push(...line([
      '  ',
      { text: icon.ch, color: icon.color, bold: s.state !== 'pending' },
      ' ',
      { text: s.text, color: STEP_TEXT[s.state] },
    ], 2 + 1 + 1 + s.text.length));
  });
  out.push(...blank());
  // Last line: hint
  if (frame === 4) {
    out.push(...line([
      { text: center('press [Enter] to skip', IW), color: TC.textDim, italic: true },
    ], IW));
  } else {
    out.push(...line([
      { text: center('press [Ctrl+C] to cancel', IW), color: TC.textDim },
    ], IW));
  }
  out.push(...blank());
  // Bottom border
  out.push({ text: BOT, color: TC.border }, '\n');

  return out;
}

function FramePanel({ n, label, ms, children }) {
  return (
    <div style={{ flex: 1, minWidth: 0 }}>
      <div style={{
        display: 'flex', alignItems: 'baseline', justifyContent: 'space-between',
        marginBottom: 8,
      }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'baseline' }}>
          <Eyebrow color={TC.borderHi} size={11}>FRAME {n}</Eyebrow>
          <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: TC.textMid }}>{label}</span>
        </div>
        <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: TC.textDim }}>{ms}</span>
      </div>
      <TerminalChrome title="claude-bridge-tui" subtitle={`startup · t=${ms}`} cols={48} rows={16}>
        {children}
      </TerminalChrome>
    </div>
  );
}

function TUIStartup() {
  return (
    <div style={{
      width: '100%', height: '100%',
      background: '#0a0b0e', padding: '36px 40px',
      boxSizing: 'border-box', overflow: 'hidden',
    }}>
      <div style={{ marginBottom: 24 }}>
        <Eyebrow color={TC.borderHi} size={11}>TUI · STARTUP SEQUENCE</Eyebrow>
        <h2 style={{
          margin: '6px 0 4px',
          fontFamily: "'IBM Plex Mono', monospace", fontSize: 26, fontWeight: 700,
          color: TC.text, letterSpacing: '-0.01em',
        }}>From <span style={{color: TC.borderHi}}>python tui.py</span> to full screen</h2>
        <p style={{ margin: 0, color: TC.textMid, fontSize: 13, fontFamily: 'var(--sans)' }}>
          Each step fades in 150ms apart. On success, the box expands to fill the terminal and the main layout fades up underneath.
          On any failure, the box collapses to a one-line error and the process exits.
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
        <FramePanel n="1" label="connect" ms="0 ms">
          {R(StartupFrame({ frame: 1 }))}
        </FramePanel>
        <FramePanel n="2" label="server up" ms="+220 ms">
          {R(StartupFrame({ frame: 2 }))}
        </FramePanel>
        <FramePanel n="3" label="syncing log" ms="+420 ms">
          {R(StartupFrame({ frame: 3 }))}
        </FramePanel>
        <FramePanel n="4" label="ready" ms="+620 ms">
          {R(StartupFrame({ frame: 4 }))}
        </FramePanel>
      </div>

      {/* Error variant strip */}
      <div style={{
        marginTop: 28, padding: '14px 18px',
        background: 'var(--bg-card)', border: '1px solid var(--hairline)',
        borderRadius: 4,
      }}>
        <Eyebrow color={TC.offline} size={10}>ERROR PATH · COULDN'T REACH :8765</Eyebrow>
        <pre style={{
          margin: '10px 0 0', fontFamily: "'IBM Plex Mono', monospace", fontSize: 12,
          color: TC.text, background: TC.bg, padding: '12px 16px',
          borderRadius: 4, border: '1px solid var(--hairline)',
          whiteSpace: 'pre',
        }}>
{R([
  '  ',
  { text: '✗', color: TC.offline, bold: true },
  ' ',
  { text: 'connection refused', color: TC.offline, bold: true },
  '  ',
  { text: '— bridge server not running on :8765', color: TC.textMid },
  '\n  ',
  { text: '  hint: ', color: TC.textDim },
  { text: 'start the bridge with ', color: TC.textMid },
  { text: '`python server.py`', color: TC.warn, bold: true },
  { text: ' on this machine, or check that port 8765 is reachable.', color: TC.textMid },
  '\n  ',
  { text: '  retry:', color: TC.textDim },
  '  ',
  { text: '[R]', color: TC.borderHi, bold: true },
  { text: ' reconnect    ', color: TC.textMid },
  { text: '[Q]', color: TC.borderHi, bold: true },
  { text: ' quit', color: TC.textMid },
])}
        </pre>
      </div>
    </div>
  );
}

window.TUIStartup = TUIStartup;
