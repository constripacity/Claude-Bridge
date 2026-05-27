// Shared atoms used across artboards: icons, dots, pills, code formatter.

const Icon = ({ name, size = 16, stroke = 1.5, color = 'currentColor' }) => {
  const paths = {
    plus:    <path d="M8 3v10M3 8h10" />,
    hash:    <path d="M5 3l-1 10M11 3l-1 10M3 6h10M3 11h10" />,
    arrow:   <path d="M3 8h10M9 4l4 4-4 4" />,
    chev:    <path d="M5 6l3 3 3-3" />,
    chevR:   <path d="M6 5l3 3-3 3" />,
    chevL:   <path d="M10 5l-3 3 3 3" />,
    close:   <path d="M4 4l8 8M12 4l-8 8" />,
    lock:    <path d="M4.5 7V5.5a2.5 2.5 0 015 0V7M3.5 7h8v5h-8z" />,
    unlock:  <path d="M4.5 7V5.5a2.5 2.5 0 014.9-.5M3.5 7h8v5h-8z" />,
    copy:    <path d="M5 5h6v6H5zM3 3h6v2M3 3v6h2" />,
    send:    <path d="M14 2L2 8l5 1.5L8.5 14 14 2zM7 9l4-5" />,
    gear:    <path d="M8 5.5a2.5 2.5 0 100 5 2.5 2.5 0 000-5zM8 2v1.5M8 12.5V14M2 8h1.5M12.5 8H14M3.7 3.7l1 1M11.3 11.3l1 1M3.7 12.3l1-1M11.3 4.7l1-1" />,
    json:    <path d="M5 3.5c-1 0-1.5.5-1.5 1.5v2c0 .5-.3 1-1 1 .7 0 1 .5 1 1v2c0 1 .5 1.5 1.5 1.5M11 3.5c1 0 1.5.5 1.5 1.5v2c0 .5.3 1 1 1-.7 0-1 .5-1 1v2c0 1-.5 1.5-1.5 1.5" />,
    search:  <path d="M11 11l3 3M7 12.5a5.5 5.5 0 100-11 5.5 5.5 0 000 11z" />,
    bolt:    <path d="M9 2L4 9h3l-1 5 5-7H8l1-5z" />,
    node:    <path d="M8 2v3M8 11v3M2 8h3M11 8h3M8 8m-2 0a2 2 0 104 0 2 2 0 10-4 0" />,
    dot:     <circle cx="8" cy="8" r="3" />,
    wifi:    <path d="M2 6a8 8 0 0112 0M4 8.5a5 5 0 018 0M6 11a2.5 2.5 0 014 0M8 13.5h.01" />,
    book:    <path d="M3 2.5h10v11H3z M3 2.5v11 M8 2.5v11" />,
    star:    <path d="M8 2l1.8 3.7 4 .6-2.9 2.8.7 4L8 11.2 4.4 13.1l.7-4L2.2 6.3l4-.6L8 2z" />,
    terminal:<path d="M2 3.5h12v9H2z M4.5 6.5L6.5 8 4.5 9.5 M7.5 10h4" />,
    grip:    <path d="M5 4h.01M5 8h.01M5 12h.01M11 4h.01M11 8h.01M11 12h.01" />,
  };
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none"
         stroke={color} strokeWidth={stroke} strokeLinecap="round" strokeLinejoin="round"
         style={{ flexShrink: 0, display: 'block' }}>
      {paths[name] || null}
    </svg>
  );
};

// Pulsing live dot
const LiveDot = ({ color = 'var(--green)', size = 6 }) => (
  <span style={{ position: 'relative', display: 'inline-block', width: size, height: size }}>
    <span style={{
      position: 'absolute', inset: 0, borderRadius: '50%', background: color,
      boxShadow: `0 0 0 0 ${color}66`,
      animation: 'lb-pulse 1.6s ease-out infinite',
    }} />
    <style>{`@keyframes lb-pulse{
      0%   { box-shadow: 0 0 0 0 ${color}88; }
      70%  { box-shadow: 0 0 0 ${size * 1.5}px ${color}00; }
      100% { box-shadow: 0 0 0 0 ${color}00; }
    }`}</style>
  </span>
);

// Tracked-out caps mini-label
const Eyebrow = ({ children, color = 'var(--text-dim)', size = 10, style }) => (
  <span style={{
    fontFamily: 'var(--mono)', fontSize: size, fontWeight: 500,
    letterSpacing: '0.14em', textTransform: 'uppercase', color, ...(style || {}),
  }}>{children}</span>
);

// Sender pill — amber for shadow, blue for mac, slate for others
const SENDER_COLORS = {
  shadow: { fg: '#fbbf24', bg: 'rgba(217, 119, 6, 0.14)', border: 'rgba(217, 119, 6, 0.4)' },
  mac:    { fg: '#79b8ff', bg: 'rgba(88, 166, 255, 0.12)', border: 'rgba(88, 166, 255, 0.4)' },
  linux:  { fg: '#a371f7', bg: 'rgba(188, 140, 255, 0.12)', border: 'rgba(188, 140, 255, 0.4)' },
  watcher:{ fg: '#3fb950', bg: 'rgba(63, 185, 80, 0.12)',  border: 'rgba(63, 185, 80, 0.4)' },
  default:{ fg: '#8b949e', bg: 'rgba(139, 148, 158, 0.1)', border: 'rgba(139, 148, 158, 0.3)' },
};
const SenderPill = ({ name, size = 'md' }) => {
  const c = SENDER_COLORS[name] || SENDER_COLORS.default;
  const sz = size === 'sm'
    ? { fontSize: 10, padding: '1px 6px' }
    : { fontSize: 11, padding: '2px 7px' };
  return (
    <span style={{
      ...sz,
      fontFamily: 'var(--mono)', fontWeight: 500,
      color: c.fg, background: c.bg,
      border: `1px solid ${c.border}`,
      borderRadius: 3, display: 'inline-flex', alignItems: 'center',
      lineHeight: 1.4, letterSpacing: 0,
    }}>{name}</span>
  );
};

// JSON syntax highlighter — for the inspector
function HighlightedJson({ value, indent = 2 }) {
  const text = typeof value === 'string' ? value : JSON.stringify(value, null, indent);
  // Tokenise: strings, numbers, booleans/null, keys
  const tokens = [];
  let i = 0;
  const push = (color, str) => tokens.push({ color, str });
  while (i < text.length) {
    const ch = text[i];
    if (ch === '"') {
      let j = i + 1;
      while (j < text.length && text[j] !== '"') {
        if (text[j] === '\\') j++;
        j++;
      }
      const lit = text.slice(i, j + 1);
      // peek next non-space for ':'
      let k = j + 1;
      while (k < text.length && /\s/.test(text[k])) k++;
      if (text[k] === ':') push('#79b8ff', lit);     // key
      else push('#a5d6ff', lit);                     // string value
      i = j + 1;
    } else if (/[\d-]/.test(ch) && /[\d.\-+eE]/.test(text[i+1] || '')) {
      let j = i;
      while (j < text.length && /[\d.\-+eE]/.test(text[j])) j++;
      push('#f0883e', text.slice(i, j));
      i = j;
    } else if (text.startsWith('true', i) || text.startsWith('false', i)) {
      const len = text.startsWith('true', i) ? 4 : 5;
      push('#bc8cff', text.substr(i, len));
      i += len;
    } else if (text.startsWith('null', i)) {
      push('#bc8cff', 'null'); i += 4;
    } else {
      push('#8b949e', ch); i++;
    }
  }
  return (
    <pre style={{
      margin: 0, fontFamily: 'var(--mono)', fontSize: 12, lineHeight: 1.65,
      color: '#8b949e', whiteSpace: 'pre-wrap', wordBreak: 'break-word',
    }}>
      {tokens.map((t, idx) => <span key={idx} style={{ color: t.color }}>{t.str}</span>)}
    </pre>
  );
}

// Section labels in the dashboard chrome
const ChromeLabel = ({ children, count }) => (
  <div style={{
    display: 'flex', alignItems: 'center', gap: 8,
    padding: '12px 14px 8px',
    fontFamily: 'var(--mono)', fontSize: 10, fontWeight: 500,
    letterSpacing: '0.18em', textTransform: 'uppercase',
    color: 'var(--text-dim)',
  }}>
    <span>{children}</span>
    {count != null && (
      <span style={{
        marginLeft: 'auto', color: 'var(--text-faint)', fontSize: 10,
        fontVariantNumeric: 'tabular-nums',
      }}>{count}</span>
    )}
  </div>
);

// Brand mark — small bridge glyph (two nodes joined by an arc)
const BridgeMark = ({ size = 24, color = 'var(--blue)' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
    <path d="M4 16c0-4.5 3.5-8 8-8s8 3.5 8 8" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
    <circle cx="4" cy="16" r="2.5" fill={color} />
    <circle cx="20" cy="16" r="2.5" fill={color} />
    <path d="M4 16h16" stroke={color} strokeWidth="1" strokeDasharray="1.5 2.5" opacity="0.4" />
  </svg>
);

Object.assign(window, {
  Icon, LiveDot, Eyebrow, SenderPill, HighlightedJson, ChromeLabel,
  BridgeMark, SENDER_COLORS,
});
