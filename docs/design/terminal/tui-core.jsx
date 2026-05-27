// TUI core — palette, helpers, base Screen, terminal chrome.

const TC = {
  // Terminal canvas
  bg:        '#0d1117',
  border:    '#30363d',
  borderHi:  '#58a6ff',
  // Text
  text:      '#e6edf3',
  textMid:   '#8b949e',
  textDim:   '#484f58',
  // Senders
  shadow:    '#d97706',
  mac:       '#58a6ff',
  watcher:   '#3fb950',
  // Message types
  task:      '#a371f7',
  result:    '#3fb950',
  ack:       '#7dd3fc',
  err:       '#f85149',
  hb:        '#8b949e',
  txt:       '#e6edf3',
  // Channel
  channel:   '#7dd3fc',
  // JSON
  jKey:      '#7dd3fc',
  jStr:      '#a5d6ff',
  jNum:      '#79c0ff',
  jBool:     '#d97706',
  jNull:     '#f85149',
  jPunct:    '#8b949e',
  // Status
  online:    '#3fb950',
  offline:   '#f85149',
  warn:      '#d97706',
  // Active
  activeBg:  '#1c2333',
  flashBg:   '#1f3a5f',
};

// Segment helper — returns a span or plain text
const t = (text, color, opts = {}) => {
  if (!color && !opts.bg && !opts.bold) return text;
  return (
    <span style={{
      color: color || undefined,
      background: opts.bg || undefined,
      fontWeight: opts.bold ? 600 : undefined,
    }}>{text}</span>
  );
};

const sp = (n) => ' '.repeat(Math.max(0, n));
const rep = (ch, n) => ch.repeat(Math.max(0, n));

// Inline border-colored chars
const B  = (s) => t(s, TC.border);
const BH = (s) => t(s, TC.borderHi);

// One-cell separator line: ── (single line)
const hr = (n) => rep('─', n);
// Heavy: ═══
const HR = (n) => rep('═', n);

// Screen — a <pre> at fixed monospace size, wrapped in a terminal window chrome.
function TerminalChrome({ title = 'claude-bridge-tui', subtitle, cols, rows, children, accent = TC.borderHi, scale = 1 }) {
  return (
    <div style={{
      display: 'inline-flex', flexDirection: 'column',
      borderRadius: 8, overflow: 'hidden',
      background: '#000', boxShadow: '0 4px 24px rgba(0,0,0,0.5)',
      border: `1px solid ${TC.border}`,
      transform: `scale(${scale})`, transformOrigin: 'top left',
    }}>
      {/* Title bar */}
      <div style={{
        background: '#1a1a1a', borderBottom: `1px solid ${TC.border}`,
        display: 'flex', alignItems: 'center',
        padding: '8px 12px', gap: 8,
      }}>
        <div style={{ display: 'flex', gap: 6 }}>
          <span style={{ width: 11, height: 11, borderRadius: '50%', background: '#ff5f56' }} />
          <span style={{ width: 11, height: 11, borderRadius: '50%', background: '#ffbd2e' }} />
          <span style={{ width: 11, height: 11, borderRadius: '50%', background: '#27c93f' }} />
        </div>
        <span style={{ flex: 1, textAlign: 'center', color: '#9ca3af', fontFamily: "'IBM Plex Mono', monospace", fontSize: 11 }}>
          {title}
          {subtitle && <span style={{ color: '#525a63' }}>{' · '}{subtitle}</span>}
        </span>
        <span style={{
          fontFamily: "'IBM Plex Mono', monospace", fontSize: 10,
          color: '#525a63', minWidth: 70, textAlign: 'right',
        }}>{cols && rows ? `${cols}×${rows}` : ''}</span>
      </div>

      {/* Terminal canvas */}
      <pre style={{
        margin: 0, padding: '10px 14px',
        fontFamily: "'IBM Plex Mono', ui-monospace, monospace",
        fontSize: 12, lineHeight: 1.32,
        background: TC.bg, color: TC.text,
        whiteSpace: 'pre',
        fontVariantLigatures: 'none',
        // crisp text
        WebkitFontSmoothing: 'antialiased',
      }}>
        {children}
      </pre>
    </div>
  );
}

// Section header inside a panel ("CHANNELS", "FEED  channel-name")
const SectionHead = ({ children }) => t(children, TC.text, { bold: true });

// Channel data
const CHANNELS = [
  { group: 'pawprint', name: 'orchestrator', count:  89, spark: '▂▃▅▇█▆▅▄', active: true,  hot: true  },
  { group: 'pawprint', name: 'worker',       count: 112, spark: '▃▄▆██▇▆▅', active: false, hot: true  },
  { group: 'pawprint', name: 'events',       count:  41, spark: '▁▂▂▃▃▄▅▆', active: false, hot: true  },
  { group: 'general',  name: 'sync',         count:   5, spark: '▁▁▁▂▁▁▁▁', active: false, hot: false },
  { group: 'system',   name: 'heartbeat',    count: 318, spark: '▄▄▄▄▄▄▄▄', active: false, hot: false },
];

// Message data
const MSGS = [
  { seq: 42, ts: '14:31:47', sender: 'shadow', type: 'RESULT', text: '{ "workers": 4, "started_at": "2026-05-27T14:31:47Z", "queue_depth": 0 }' },
  { seq: 43, ts: '14:31:51', sender: 'mac',    type: 'TXT',    text: 'good. ping me on pawprint:events when you hit the artifact directory' },
  { seq: 44, ts: '14:31:55', sender: 'shadow', type: 'HB',     text: '{ "progress": 0.12, "files_scanned": 2847, "matches": 0, "elapsed_ms": 2103 }' },
  { seq: 45, ts: '14:31:58', sender: 'shadow', type: 'HB',     text: '{ "progress": 0.18, "files_scanned": 4011, "matches": 1, "elapsed_ms": 4220 }' },
  { seq: 46, ts: '14:32:01', sender: 'shadow', type: 'TASK',   text: '{ "type": "task", "phase": 2, "action": "deep_scan", "target": "imap_export" }' },
  { seq: 47, ts: '14:32:04', sender: 'mac',    type: 'ACK',    text: '{ "type": "ack", "phase": 2, "status": "accepted", "worker_id": "w-2" }' },
  { seq: 48, ts: '14:32:07', sender: 'shadow', type: 'HB',     text: '{ "progress": 0.27, "files_scanned": 6122, "matches": 3, "elapsed_ms": 7411 }' },
  { seq: 49, ts: '14:32:09', sender: 'mac',    type: 'TXT',    text: 'three matches already? show me the first one when the scan finishes that directory' },
  { seq: 50, ts: '14:32:11', sender: 'shadow', type: 'HB',     text: '{ "progress": 0.31, "files_scanned": 7019, "matches": 3 }' },
  { seq: 51, ts: '14:32:14', sender: 'shadow', type: 'TASK',   text: '{ "type": "task", "phase": 2, "action": "extract", "match_id": "m-001" }' },
  { seq: 52, ts: '14:32:19', sender: 'mac',    type: 'RESULT', text: '{ "type": "result", "phase": 1, "status": "complete", "count": 14, "artifacts": [ "com.apple.finder", "com.apple.security" ] }' },
];

const TYPE_COLORS = {
  TASK:   TC.task,
  RESULT: TC.result,
  ACK:    TC.ack,
  ERR:    TC.err,
  HB:     TC.hb,
  TXT:    TC.txt,
};
const SENDER_COLORS_TUI = {
  shadow:  TC.shadow,
  mac:     TC.mac,
  watcher: TC.watcher,
};

// Render JSON with simple syntax color, given a JS value.
function jsonRender(value, indent = 2, depth = 0) {
  const pad = sp(indent * depth);
  const padIn = sp(indent * (depth + 1));
  if (value === null) return [t('null', TC.jNull)];
  if (typeof value === 'boolean') return [t(String(value), TC.jBool)];
  if (typeof value === 'number') return [t(String(value), TC.jNum)];
  if (typeof value === 'string') return [t(`"${value}"`, TC.jStr)];
  if (Array.isArray(value)) {
    if (value.length === 0) return [t('[]', TC.jPunct)];
    const out = [t('[', TC.jPunct), '\n'];
    value.forEach((v, i) => {
      out.push(padIn);
      out.push(...jsonRender(v, indent, depth + 1));
      if (i < value.length - 1) out.push(t(',', TC.jPunct));
      out.push('\n');
    });
    out.push(pad, t(']', TC.jPunct));
    return out;
  }
  const keys = Object.keys(value);
  if (keys.length === 0) return [t('{}', TC.jPunct)];
  const out = [t('{', TC.jPunct), '\n'];
  keys.forEach((k, i) => {
    out.push(padIn);
    out.push(t(`"${k}"`, TC.jKey));
    out.push(t(': ', TC.jPunct));
    out.push(...jsonRender(value[k], indent, depth + 1));
    if (i < keys.length - 1) out.push(t(',', TC.jPunct));
    out.push('\n');
  });
  out.push(pad, t('}', TC.jPunct));
  return out;
}

Object.assign(window, {
  TC, t, sp, rep, B, BH, hr, HR, TerminalChrome, SectionHead,
  CHANNELS, MSGS, TYPE_COLORS, SENDER_COLORS_TUI, jsonRender,
});
