// Top-level orchestrator: polls /api/state + /api/messages, renders
// DashboardDesktop or DashboardMobile depending on viewport.

const { useState, useEffect, useRef, useCallback } = React;

const POLL_MS = 2000;
const MOBILE_MAX = 640;

const TOKEN_KEY = 'claude-bridge:auth-token';

function getToken() {
  try { return localStorage.getItem(TOKEN_KEY) || null; } catch (_) { return null; }
}

function setToken(t) {
  try {
    if (t) localStorage.setItem(TOKEN_KEY, t);
    else   localStorage.removeItem(TOKEN_KEY);
  } catch (_) {}
}

function promptForToken() {
  const entered = window.prompt(
    'This bridge requires an auth token.\n\n' +
    'Paste the CLAUDE_BRIDGE_AUTH_TOKEN value (or the --auth-token CLI value) ' +
    'used when the bridge was started:',
    '',
  );
  if (entered && entered.trim()) {
    setToken(entered.trim());
    return entered.trim();
  }
  return null;
}

class AuthError extends Error {
  constructor(msg) { super(msg); this.name = 'AuthError'; }
}

async function fetchJson(url, opts = {}, { retryOn401 = true } = {}) {
  const token = getToken();
  const headers = { ...(opts.headers || {}) };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const res = await fetch(url, { ...opts, headers });
  if (res.status === 401) {
    if (retryOn401) {
      setToken(null);
      const next = promptForToken();
      if (next) return fetchJson(url, opts, { retryOn401: false });
    }
    throw new AuthError('Bridge rejected token');
  }
  if (!res.ok) {
    let body = '';
    try { body = await res.text(); } catch (_) {}
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return res.json();
}

function useViewport() {
  const [w, setW] = useState(typeof window !== 'undefined' ? window.innerWidth : 1280);
  useEffect(() => {
    const onResize = () => setW(window.innerWidth);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);
  return w;
}

function useInterval(fn, ms) {
  const savedRef = useRef(fn);
  useEffect(() => { savedRef.current = fn; }, [fn]);
  useEffect(() => {
    if (ms == null) return;
    const id = setInterval(() => savedRef.current(), ms);
    return () => clearInterval(id);
  }, [ms]);
}

function defaultSender() {
  const ua = (navigator.userAgent || '').toLowerCase();
  if (ua.includes('mac'))     return 'mac';
  if (ua.includes('linux'))   return 'linux';
  if (ua.includes('windows')) return 'windows';
  return 'dashboard';
}

function App() {
  const [state, setState]               = useState(null);
  const [activeChannel, setActiveChannel] = useState(
    () => localStorage.getItem('bridge.activeChannel') || null
  );
  const [messages, setMessages]         = useState([]);
  const [selectedMsg, setSelectedMsg]   = useState(null);
  const [detail, setDetail]             = useState(null);
  const [err, setErr]                   = useState(null);
  const [hasToken, setHasToken]         = useState(() => !!getToken());

  const clearToken = useCallback(() => {
    if (!confirm('Clear stored bridge token? You will be re-prompted on the next request.')) return;
    setToken(null);
    setHasToken(false);
  }, []);

  const width = useViewport();
  const sender = defaultSender();

  // ── Auto-select first channel once we know about any ────────────────────
  useEffect(() => {
    if (!activeChannel && state?.channels?.length) {
      const first = state.channels[0].id;
      setActiveChannel(first);
      localStorage.setItem('bridge.activeChannel', first);
    }
  }, [state, activeChannel]);

  // ── Poll /api/state (keep polling — channel list, counts, uptime) ────────
  const refreshState = useCallback(async () => {
    try {
      const s = await fetchJson('/api/state');
      setState(s);
      setErr(null);
    } catch (e) {
      setErr(String(e));
    } finally {
      // Keep auth badge in sync with whatever fetchJson stored after prompts
      setHasToken(!!getToken());
    }
  }, []);
  useEffect(() => { refreshState(); }, [refreshState]);
  useInterval(refreshState, POLL_MS);

  // ── Live event stream for the active channel (replaces messages poll) ────
  // One-shot /api/messages for initial backlog, then EventSource for live
  // updates. /api/state poll is unchanged — it covers channel list + counts.
  const esRef = useRef(null);

  const fetchBacklog = useCallback((channel) => {
    fetchJson(`/api/messages?channel=${encodeURIComponent(channel)}&limit=100`)
      .then(data => setMessages(data.messages || []))
      .catch(e => setErr(String(e)));
  }, []);

  useEffect(() => {
    if (esRef.current) { esRef.current.close(); esRef.current = null; }
    if (!activeChannel) { setMessages([]); return; }

    fetchBacklog(activeChannel);

    const token = getToken();
    const url = `/events/channel/${encodeURIComponent(activeChannel)}` +
      (token ? `?token=${encodeURIComponent(token)}` : '');
    const es = new EventSource(url);
    esRef.current = es;

    es.addEventListener('message', (e) => {
      try {
        const msg = JSON.parse(e.data);
        setMessages(prev => prev.some(m => m.id === msg.id) ? prev : [...prev, msg]);
      } catch (_) {}
    });

    es.addEventListener('clear', () => {
      setMessages([]);
      setSelectedMsg(null);
      setDetail(null);
    });

    // cursor_stale or replay_truncated: our resume point is gone or overflow —
    // re-sync from /api/messages without a cursor.
    es.addEventListener('cursor_stale',      () => fetchBacklog(activeChannel));
    es.addEventListener('replay_truncated',  () => fetchBacklog(activeChannel));

    es.addEventListener('error', () => {
      setErr('Event stream error — reconnecting…');
    });

    return () => { es.close(); esRef.current = null; };
  }, [activeChannel, fetchBacklog]);

  // ── Auto-select latest message on channel switch / first load ───────────
  useEffect(() => {
    if (!selectedMsg && messages.length) {
      const latest = messages[messages.length - 1];
      handleSelectMessage(latest);
    }
    // If selected msg no longer in feed (channel switch), clear it
    if (selectedMsg && !messages.some(m => m.id === selectedMsg.id)) {
      setSelectedMsg(null);
      setDetail(null);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages]);

  // ── Fetch detail for selected message ───────────────────────────────────
  const handleSelectMessage = useCallback(async (m) => {
    setSelectedMsg(m);
    if (!m) { setDetail(null); return; }
    try {
      const d = await fetchJson(`/api/messages/${m.id}`);
      setDetail(d);
    } catch (e) {
      setErr(String(e));
    }
  }, []);

  const handleSelectChannel = useCallback((id) => {
    setActiveChannel(id);
    localStorage.setItem('bridge.activeChannel', id);
    setSelectedMsg(null);
    setDetail(null);
  }, []);

  const handleSend = useCallback(async ({ channel, sender, content }) => {
    await fetchJson('/api/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ channel, sender, content }),
    });
    // Message arrives via EventSource; refresh state for channel count update.
    await refreshState();
  }, [refreshState]);

  const handleNewChannel = useCallback(async () => {
    const raw = window.prompt(
      'New channel name (convention: project:role — e.g. demo:orchestrator):',
      'demo:orchestrator',
    );
    if (!raw) return;
    const name = raw.trim();
    if (!name) return;
    // Channels come into existence on first write — drop a hello marker.
    const hello = JSON.stringify({
      type: 'hello',
      from: sender,
      ts: new Date().toISOString(),
    });
    await fetchJson('/api/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ channel: name, sender, content: hello }),
    });
    setActiveChannel(name);
    localStorage.setItem('bridge.activeChannel', name);
    setSelectedMsg(null);
    setDetail(null);
    await refreshState();
  }, [sender, refreshState]);

  const handleClear = useCallback(async (channel) => {
    if (!confirm(`Clear ALL messages from "${channel}"? This cannot be undone.`)) return;
    await fetchJson('/api/clear', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ channel }),
    });
    // `clear` SSE event handles setMessages([])/setSelectedMsg/setDetail;
    // refresh state for the channel count.
    await refreshState();
  }, [refreshState]);

  const channelMeta = (state?.channels || []).find(c => c.id === activeChannel) || null;

  const Dashboard = width <= MOBILE_MAX ? window.DashboardMobile : window.DashboardDesktop;

  return (
    <div style={{ width: '100vw', height: '100vh', background: 'var(--bg-base)' }}>
      <Dashboard
        state={state}
        activeChannel={activeChannel}
        channelMeta={channelMeta}
        messages={messages}
        selectedId={selectedMsg?.id}
        detail={detail}
        onSelectChannel={handleSelectChannel}
        onSelectMessage={handleSelectMessage}
        onSend={handleSend}
        onClear={handleClear}
        onNewChannel={handleNewChannel}
        defaultSender={sender}
      />
      {err && (
        <div style={{
          position: 'fixed', bottom: 12, right: 12, maxWidth: 360,
          background: 'rgba(248, 81, 73, 0.12)',
          border: '1px solid rgba(248, 81, 73, 0.4)',
          borderRadius: 6, padding: '8px 12px',
          fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--red)',
          zIndex: 100,
        }}>
          {err}
        </div>
      )}
      {hasToken && (
        <div style={{
          position: 'fixed', top: 12, right: 12,
          background: 'rgba(63, 185, 80, 0.12)',
          border: '1px solid rgba(63, 185, 80, 0.4)',
          borderRadius: 6, padding: '4px 10px',
          fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--green)',
          display: 'flex', alignItems: 'center', gap: 8, zIndex: 100,
        }}>
          <span>Auth ✓</span>
          <button
            onClick={clearToken}
            style={{
              background: 'transparent', border: '1px solid rgba(63, 185, 80, 0.4)',
              borderRadius: 4, padding: '1px 6px', color: 'var(--green)',
              fontFamily: 'var(--mono)', fontSize: 10, cursor: 'pointer',
            }}
            title="Clear stored bridge token"
          >clear</button>
        </div>
      )}
    </div>
  );
}

window.App = App;
