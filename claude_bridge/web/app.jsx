// Top-level dashboard orchestrator. API requests authenticate with a short-lived,
// HttpOnly session cookie; the bearer token is only held for the duration of the
// POST /api/session request and is never written to browser storage or a URL.

import React, { useCallback, useEffect, useRef, useState } from 'react';

import DashboardDesktop from './dashboard-desktop.jsx';
import DashboardMobile from './dashboard-mobile.jsx';

const POLL_MS = 2000;
const MOBILE_MAX = 640;

class AuthError extends Error {
  constructor(message) {
    super(message);
    this.name = 'AuthError';
  }
}

const authListeners = new Set();
let authenticationPromise = null;
let authenticationBlocked = false;

function publishAuthState(active, required = !active) {
  for (const listener of authListeners) listener({ active, required });
}

function promptForToken() {
  const entered = window.prompt(
    'This bridge requires authentication.\n\n' +
    'Paste the CLAUDE_BRIDGE_AUTH_TOKEN value (or the --auth-token CLI value). ' +
    'It will be exchanged for an HttpOnly browser session and will not be stored:',
    '',
  );
  return entered?.trim() || null;
}

async function createBrowserSession(token) {
  const response = await fetch('/api/session', {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      'Accept': 'application/json',
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: '{}',
  });

  if (response.status === 401) throw new AuthError('Bridge rejected that token');
  if (!response.ok) {
    const body = await response.text().catch(() => '');
    throw new Error(`${response.status} ${response.statusText}: ${body}`);
  }
}

async function restoreBrowserSession() {
  // GET is deliberately sent without a bearer header. A valid HttpOnly cookie
  // authenticates it; a 401 simply means the normal sign-in flow must run.
  // The response also distinguishes an auth-disabled local bridge.
  const response = await fetch('/api/session', {
    credentials: 'same-origin',
    headers: { 'Accept': 'application/json' },
  });
  if (response.status === 401) {
    publishAuthState(false, true);
    return false;
  }
  if (!response.ok) return false;
  const result = await response.json().catch(() => ({}));
  const authRequired = Boolean(result.auth_required);
  const active = authRequired && Boolean(result.authenticated);
  publishAuthState(active, authRequired && !active);
  return Boolean(result.authenticated);
}

async function authenticate({ force = false } = {}) {
  if (authenticationPromise) return authenticationPromise;
  if (authenticationBlocked && !force) {
    throw new AuthError('Authentication required');
  }

  authenticationPromise = (async () => {
    const token = promptForToken();
    if (!token) {
      authenticationBlocked = true;
      publishAuthState(false, true);
      throw new AuthError('Authentication cancelled');
    }

    try {
      await createBrowserSession(token);
      authenticationBlocked = false;
      publishAuthState(true, false);
    } catch (error) {
      authenticationBlocked = true;
      publishAuthState(false, true);
      throw error;
    }
  })();

  try {
    return await authenticationPromise;
  } finally {
    authenticationPromise = null;
  }
}

async function fetchJson(url, options = {}, { retryOn401 = true } = {}) {
  const headers = {
    'Accept': 'application/json',
    ...(options.headers || {}),
  };
  const response = await fetch(url, {
    ...options,
    credentials: 'same-origin',
    headers,
  });

  if (response.status === 401) {
    if (retryOn401) {
      await authenticate();
      return fetchJson(url, options, { retryOn401: false });
    }
    publishAuthState(false, true);
    throw new AuthError('Browser session was rejected');
  }
  if (!response.ok) {
    const body = await response.text().catch(() => '');
    throw new Error(`${response.status} ${response.statusText}: ${body}`);
  }
  if (response.status === 204) return null;
  return response.json();
}

function useViewport() {
  const [width, setWidth] = useState(window.innerWidth);
  useEffect(() => {
    const onResize = () => setWidth(window.innerWidth);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);
  return width;
}

function useInterval(callback, milliseconds) {
  const savedRef = useRef(callback);
  useEffect(() => { savedRef.current = callback; }, [callback]);
  useEffect(() => {
    if (milliseconds == null) return undefined;
    const id = window.setInterval(() => savedRef.current(), milliseconds);
    return () => window.clearInterval(id);
  }, [milliseconds]);
}

function defaultSender() {
  const userAgent = (navigator.userAgent || '').toLowerCase();
  if (userAgent.includes('mac')) return 'mac';
  if (userAgent.includes('linux')) return 'linux';
  if (userAgent.includes('windows')) return 'windows';
  return 'dashboard';
}

function normalizeFeedMessage(message) {
  const content = typeof message.content === 'string' ? message.content : '';
  const timestamp = message.ts_full || message.timestamp || '';
  const preview = message.preview ?? (
    content.length <= 200 ? content : `${content.slice(0, 200)}…`
  );
  const trimmed = content.trim();
  let isJson = message.is_json ?? false;
  if (message.is_json == null && (trimmed.startsWith('{') || trimmed.startsWith('['))) {
    try {
      JSON.parse(trimmed);
      isJson = true;
    } catch (_) {
      isJson = false;
    }
  }
  return {
    ...message,
    ts: message.ts || (timestamp ? timestamp.slice(11, 19) : ''),
    ts_full: timestamp,
    preview,
    is_json: isJson,
  };
}

function mergeMessages(...collections) {
  const byId = new Map();
  for (const collection of collections) {
    for (const raw of collection || []) {
      const message = normalizeFeedMessage(raw);
      if (message.id) byId.set(message.id, message);
    }
  }
  return [...byId.values()].sort((left, right) => left.seq - right.seq);
}

function readActiveChannel() {
  try {
    return localStorage.getItem('bridge.activeChannel') || null;
  } catch (_) {
    return null;
  }
}

function storeActiveChannel(channel) {
  try {
    localStorage.setItem('bridge.activeChannel', channel);
  } catch (_) {}
}

function App() {
  const [state, setState] = useState(null);
  const [activeChannel, setActiveChannel] = useState(readActiveChannel);
  const [messages, setMessages] = useState([]);
  const [selectedMsg, setSelectedMsg] = useState(null);
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState(null);
  const [authState, setAuthState] = useState({ active: false, required: false });

  const width = useViewport();
  const sender = defaultSender();
  const eventSourceRef = useRef(null);

  useEffect(() => {
    authListeners.add(setAuthState);
    return () => authListeners.delete(setAuthState);
  }, []);

  useEffect(() => {
    if (!activeChannel && state?.channels?.length) {
      const first = state.channels[0].id;
      setActiveChannel(first);
      storeActiveChannel(first);
    }
  }, [state, activeChannel]);

  const refreshState = useCallback(async () => {
    try {
      const nextState = await fetchJson('/api/state');
      setState(nextState);
      setError(null);
    } catch (caught) {
      setError(String(caught));
    }
  }, []);

  useEffect(() => {
    restoreBrowserSession()
      .catch(() => false)
      .finally(refreshState);
  }, [refreshState]);
  useInterval(
    refreshState,
    authState.required && !authState.active ? null : POLL_MS,
  );

  const handleSignIn = useCallback(async () => {
    try {
      await authenticate({ force: true });
      await refreshState();
      setError(null);
    } catch (caught) {
      setError(String(caught));
    }
  }, [refreshState]);

  const handleSignOut = useCallback(async () => {
    if (!window.confirm('End this dashboard session?')) return;
    try {
      const response = await fetch('/api/session', {
        method: 'DELETE',
        credentials: 'same-origin',
        headers: { 'Accept': 'application/json' },
      });
      if (!response.ok && response.status !== 401) {
        throw new Error(`${response.status} ${response.statusText}`);
      }
    } catch (caught) {
      setError(String(caught));
      return;
    }

    authenticationBlocked = true;
    publishAuthState(false, true);
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
    setState(null);
    setMessages([]);
    setSelectedMsg(null);
    setDetail(null);
  }, []);

  // Fetch a stable backlog, then resume the stream from its newest cursor.
  // Anything written between those two operations is replayed by the server,
  // and duplicate ids are collapsed client-side.
  useEffect(() => {
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
    setSelectedMsg(null);
    setDetail(null);

    if (!activeChannel) {
      setMessages([]);
      return undefined;
    }
    if (authState.required && !authState.active) {
      setMessages([]);
      return undefined;
    }

    let cancelled = false;
    let eventSource = null;

    const fetchBacklog = async () => {
      const data = await fetchJson(
        `/api/messages?channel=${encodeURIComponent(activeChannel)}&limit=100`,
      );
      const backlog = (data.messages || []).map(normalizeFeedMessage);
      if (!cancelled) {
        setMessages(backlog);
      }
      return {
        backlog,
        cursor: data.next_cursor || data.cursor || backlog[backlog.length - 1]?.id || null,
      };
    };

    const connect = async () => {
      try {
        const { cursor } = await fetchBacklog();
        if (cancelled) return;

        const parameters = cursor ? `?since_id=${encodeURIComponent(cursor)}` : '';
        const url = `/events/channel/${encodeURIComponent(activeChannel)}${parameters}`;
        eventSource = new EventSource(url, { withCredentials: true });
        eventSourceRef.current = eventSource;

        eventSource.addEventListener('open', () => {
          if (!cancelled) setError(null);
        });
        eventSource.addEventListener('message', event => {
          try {
            const message = normalizeFeedMessage(JSON.parse(event.data));
            if (!cancelled) setMessages(previous => mergeMessages(previous, [message]));
          } catch (_) {}
        });
        eventSource.addEventListener('clear', () => {
          if (cancelled) return;
          setMessages([]);
          setSelectedMsg(null);
          setDetail(null);
        });
        eventSource.addEventListener('cursor_stale', () => {
          fetchBacklog().catch(caught => setError(String(caught)));
        });
        eventSource.addEventListener('replay_truncated', () => {
          fetchBacklog().catch(caught => setError(String(caught)));
        });
        eventSource.addEventListener('error', () => {
          if (!cancelled) setError('Event stream interrupted — reconnecting…');
        });
      } catch (caught) {
        if (!cancelled) setError(String(caught));
      }
    };

    connect();
    return () => {
      cancelled = true;
      eventSource?.close();
      if (eventSourceRef.current === eventSource) eventSourceRef.current = null;
    };
  }, [activeChannel, authState.active, authState.required]);

  const handleSelectMessage = useCallback(async message => {
    setSelectedMsg(message);
    if (!message) {
      setDetail(null);
      return;
    }
    try {
      const nextDetail = await fetchJson(`/api/messages/${message.id}`);
      setDetail(nextDetail);
    } catch (caught) {
      setError(String(caught));
    }
  }, []);

  useEffect(() => {
    if (!selectedMsg && messages.length) {
      handleSelectMessage(messages[messages.length - 1]);
    } else if (selectedMsg && !messages.some(message => message.id === selectedMsg.id)) {
      setSelectedMsg(null);
      setDetail(null);
    }
  }, [messages, selectedMsg, handleSelectMessage]);

  const handleSelectChannel = useCallback(channel => {
    setActiveChannel(channel);
    storeActiveChannel(channel);
  }, []);

  const handleSend = useCallback(async ({ channel, sender: from, content }) => {
    await fetchJson('/api/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ channel, sender: from, content }),
    });
    await refreshState();
  }, [refreshState]);

  const handleNewChannel = useCallback(async () => {
    const raw = window.prompt(
      'New channel name (convention: project:role — e.g. demo:orchestrator):',
      'demo:orchestrator',
    );
    const name = raw?.trim();
    if (!name) return;

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
    storeActiveChannel(name);
    await refreshState();
  }, [sender, refreshState]);

  const handleClear = useCallback(async channel => {
    if (!window.confirm(`Clear ALL messages from "${channel}"? This cannot be undone.`)) return;
    await fetchJson('/api/clear', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ channel }),
    });
    await refreshState();
  }, [refreshState]);

  const channelMeta = (state?.channels || []).find(
    channel => channel.id === activeChannel,
  ) || null;
  const Dashboard = width <= MOBILE_MAX ? DashboardMobile : DashboardDesktop;

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

      {error && (
        <div style={{
          position: 'fixed', bottom: 12, right: 12, maxWidth: 360,
          background: 'rgba(248, 81, 73, 0.12)',
          border: '1px solid rgba(248, 81, 73, 0.4)',
          borderRadius: 6, padding: '8px 12px',
          fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--red)',
          zIndex: 100,
        }}>
          {error}
        </div>
      )}

      {authState.required && !authState.active && (
        <button
          onClick={handleSignIn}
          style={{
            position: 'fixed', top: 12, right: 12,
            background: 'rgba(88, 166, 255, 0.14)',
            border: '1px solid rgba(88, 166, 255, 0.5)',
            borderRadius: 6, padding: '5px 10px',
            fontFamily: 'var(--mono)', fontSize: 11,
            color: 'var(--blue)', cursor: 'pointer', zIndex: 100,
          }}
        >Sign in</button>
      )}

      {authState.active && (
        <div style={{
          position: 'fixed', top: 12, right: 12,
          background: 'rgba(63, 185, 80, 0.12)',
          border: '1px solid rgba(63, 185, 80, 0.4)',
          borderRadius: 6, padding: '4px 10px',
          fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--green)',
          display: 'flex', alignItems: 'center', gap: 8, zIndex: 100,
        }}>
          <span>Session ✓</span>
          <button
            onClick={handleSignOut}
            style={{
              background: 'transparent',
              border: '1px solid rgba(63, 185, 80, 0.4)',
              borderRadius: 4, padding: '1px 6px', color: 'var(--green)',
              fontFamily: 'var(--mono)', fontSize: 10, cursor: 'pointer',
            }}
            title="End dashboard session"
          >logout</button>
        </div>
      )}
    </div>
  );
}

export default App;
