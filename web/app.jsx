// Top-level orchestrator: polls /api/state + /api/messages, renders
// DashboardDesktop or DashboardMobile depending on viewport.

const { useState, useEffect, useRef, useCallback } = React;

const POLL_MS = 2000;
const MOBILE_MAX = 640;

async function fetchJson(url, opts = {}) {
  const res = await fetch(url, opts);
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

  // ── Poll /api/state ──────────────────────────────────────────────────────
  const refreshState = useCallback(async () => {
    try {
      const s = await fetchJson('/api/state');
      setState(s);
      setErr(null);
    } catch (e) {
      setErr(String(e));
    }
  }, []);
  useEffect(() => { refreshState(); }, [refreshState]);
  useInterval(refreshState, POLL_MS);

  // ── Poll /api/messages for the active channel ───────────────────────────
  const refreshMessages = useCallback(async () => {
    if (!activeChannel) { setMessages([]); return; }
    try {
      const data = await fetchJson(
        `/api/messages?channel=${encodeURIComponent(activeChannel)}&limit=100`
      );
      setMessages(data.messages || []);
    } catch (e) {
      setErr(String(e));
    }
  }, [activeChannel]);
  useEffect(() => { refreshMessages(); }, [refreshMessages]);
  useInterval(refreshMessages, POLL_MS);

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
    // Refresh immediately so user sees their message land
    await refreshState();
    await refreshMessages();
  }, [refreshState, refreshMessages]);

  const handleClear = useCallback(async (channel) => {
    if (!confirm(`Clear ALL messages from "${channel}"? This cannot be undone.`)) return;
    await fetchJson('/api/clear', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ channel }),
    });
    setSelectedMsg(null);
    setDetail(null);
    await refreshState();
    await refreshMessages();
  }, [refreshState, refreshMessages]);

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
    </div>
  );
}

window.App = App;
