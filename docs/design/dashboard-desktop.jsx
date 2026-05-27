// Desktop dashboard — 1280×800, dark, three-column

const DASHBOARD_DATA = {
  uptime: '00:34:12',
  port: 8765,
  totalMessages: 247,
  channels: [
    {
      id: 'demo:orchestrator',
      group: 'demo',
      name: 'orchestrator',
      count: 89,
      lastTs: '14:32:07',
      senders: ['windows', 'mac'],
      unread: false,
      active: true,
    },
    {
      id: 'demo:worker',
      group: 'demo',
      name: 'worker',
      count: 112,
      lastTs: '14:32:04',
      senders: ['mac'],
      unread: true,
    },
    {
      id: 'demo:events',
      group: 'demo',
      name: 'events',
      count: 41,
      lastTs: '14:31:58',
      senders: ['windows', 'mac', 'watcher'],
      unread: false,
    },
    {
      id: 'general:sync',
      group: 'general',
      name: 'sync',
      count: 5,
      lastTs: '14:18:22',
      senders: ['windows'],
      unread: false,
    },
  ],
  messages: [
    { seq: 40, ts: '14:31:42', sender: 'mac',     isJson: true,  preview: '{ "task": "test", "target": "claude-bridge", "depth": "full" }' },
    { seq: 41, ts: '14:31:44', sender: 'windows', isJson: false, preview: 'acknowledged — spinning up 4 workers, ETA 18 minutes for full suite' },
    { seq: 42, ts: '14:31:47', sender: 'windows', isJson: true,  preview: '{ "workers": 4, "started_at": "2026-05-27T14:31:47Z", "queue_depth": 0 }' },
    { seq: 43, ts: '14:31:51', sender: 'mac',     isJson: false, preview: 'good. ping me on demo:events when you hit the integration tests' },
    { seq: 44, ts: '14:31:55', sender: 'windows', isJson: true,  preview: '{ "progress": 0.12, "tests_run": 28, "failures": 0, "elapsed_ms": 2103 }' },
    { seq: 45, ts: '14:32:01', sender: 'windows', isJson: true,  preview: '{ "progress": 0.27, "tests_run": 61, "failures": 3, "elapsed_ms": 7411 }', selected: true },
    { seq: 46, ts: '14:32:04', sender: 'mac',     isJson: false, preview: 'three failures already? show me the first one when the suite finishes' },
    { seq: 47, ts: '14:32:07', sender: 'windows', isJson: true,  preview: '{ "progress": 0.31, "current_suite": "tests/test_persistence.py", "tests_run": 70 }' },
  ],
  selectedMsg: {
    id: 'msg_01HX2K9PQ4R7VBN8MFGD3Y6XCA',
    seq: 45,
    channel: 'demo:orchestrator',
    sender: 'windows',
    ts: '14:32:01.847',
    received_at: '14:32:01.892',
    content: {
      progress: 0.27,
      tests_run: 61,
      failures: 3,
      elapsed_ms: 7411,
      current_suite: 'tests/test_persistence.py',
      worker_id: 'w-2',
      mem_mb: 412,
    },
  },
};

function HeaderBar() {
  return (
    <div style={{
      height: 48, background: 'var(--bg-deep)',
      borderBottom: '1px solid var(--hairline)',
      display: 'flex', alignItems: 'center', padding: '0 20px',
      position: 'relative',
    }}>
      {/* The heartbeat line */}
      <div style={{
        position: 'absolute', top: 0, left: 0, right: 0, height: 2,
        background: 'linear-gradient(90deg, transparent, var(--blue) 30%, var(--blue) 70%, transparent)',
        opacity: 0.5, filter: 'blur(0.5px)',
      }} />
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <BridgeMark size={18} color="var(--blue)" />
        <span style={{
          fontFamily: 'var(--mono)', fontSize: 12, fontWeight: 600,
          letterSpacing: '0.22em', color: 'var(--text)',
        }}>CLAUDE&nbsp;BRIDGE</span>
        <span style={{
          fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text-faint)',
          marginLeft: 4,
        }}>v0.3.1</span>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 18, marginLeft: 32 }}>
        <Stat label="STATUS" value={
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <LiveDot color="var(--green)" />
            <span style={{ color: 'var(--green)' }}>online</span>
          </span>
        } />
        <Stat label="PORT"     value=":8765" mono />
        <Stat label="UPTIME"   value={DASHBOARD_DATA.uptime} mono />
        <Stat label="CHANNELS" value={DASHBOARD_DATA.channels.length} mono />
        <Stat label="MESSAGES" value={DASHBOARD_DATA.totalMessages} mono />
      </div>

      <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6 }}>
        <HeaderBtn><Icon name="search" size={14} color="var(--text-mid)" /></HeaderBtn>
        <HeaderBtn><Icon name="book" size={14} color="var(--text-mid)" /></HeaderBtn>
        <HeaderBtn><Icon name="gear" size={14} color="var(--text-mid)" /></HeaderBtn>
      </div>
    </div>
  );
}

function Stat({ label, value, mono }) {
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
      <span style={{
        fontFamily: 'var(--mono)', fontSize: 9, fontWeight: 500,
        letterSpacing: '0.16em', color: 'var(--text-faint)',
      }}>{label}</span>
      <span style={{
        fontFamily: mono ? 'var(--mono)' : 'var(--sans)',
        fontSize: 12, color: 'var(--text)', fontWeight: 500,
        fontVariantNumeric: 'tabular-nums',
      }}>{value}</span>
    </div>
  );
}

const HeaderBtn = ({ children }) => (
  <button style={{
    width: 28, height: 28, padding: 0, border: '1px solid transparent',
    background: 'transparent', borderRadius: 4, cursor: 'pointer',
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
  }}>{children}</button>
);

function Sidebar() {
  const grouped = {};
  DASHBOARD_DATA.channels.forEach(c => {
    grouped[c.group] = grouped[c.group] || [];
    grouped[c.group].push(c);
  });
  return (
    <div style={{
      width: 252, background: 'var(--bg-base)',
      borderRight: '1px solid var(--hairline)',
      display: 'flex', flexDirection: 'column',
    }}>
      <ChromeLabel count={DASHBOARD_DATA.channels.length}>Channels</ChromeLabel>
      <div style={{ flex: 1, overflow: 'hidden', padding: '0 8px' }}>
        {Object.entries(grouped).map(([group, chs]) => (
          <div key={group} style={{ marginBottom: 14 }}>
            <div style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '4px 8px 6px', color: 'var(--text-faint)',
              fontFamily: 'var(--mono)', fontSize: 10, fontWeight: 500,
              letterSpacing: '0.12em',
            }}>
              <Icon name="chev" size={10} color="var(--text-faint)" />
              <span>{group}:</span>
              <span style={{ color: 'var(--text-faint)', opacity: 0.7 }}>{chs.length}</span>
            </div>
            {chs.map(c => <ChannelRow key={c.id} c={c} />)}
          </div>
        ))}
      </div>

      <div style={{ padding: '10px 8px', borderTop: '1px solid var(--hairline)' }}>
        <button style={{
          width: '100%', padding: '8px 10px',
          background: 'transparent',
          border: '1px dashed var(--hairline-strong)',
          borderRadius: 4, color: 'var(--text-mid)',
          fontFamily: 'var(--mono)', fontSize: 11,
          display: 'flex', alignItems: 'center', gap: 8,
          cursor: 'pointer', justifyContent: 'center',
        }}>
          <Icon name="plus" size={12} color="var(--text-mid)" />
          <span>new channel</span>
        </button>
      </div>
    </div>
  );
}

function ChannelRow({ c }) {
  return (
    <div style={{
      position: 'relative',
      padding: '8px 10px 8px 12px',
      borderRadius: 4,
      background: c.active ? 'var(--bg-elev)' : 'transparent',
      marginBottom: 1, cursor: 'pointer',
    }}>
      {c.active && (
        <div style={{
          position: 'absolute', left: 0, top: 4, bottom: 4, width: 2,
          background: 'var(--blue)', borderRadius: 1,
        }} />
      )}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4,
      }}>
        <Icon name="hash" size={11} color={c.active ? 'var(--blue)' : 'var(--text-dim)'} />
        <span style={{
          fontFamily: 'var(--mono)', fontSize: 12,
          color: c.active ? 'var(--text)' : 'var(--text-mid)',
          fontWeight: c.active ? 500 : 400, flex: 1,
          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
        }}>{c.name}</span>
        {c.unread && (
          <span style={{
            width: 5, height: 5, borderRadius: '50%',
            background: 'var(--blue)',
          }} />
        )}
        <span style={{
          fontFamily: 'var(--mono)', fontSize: 10,
          color: 'var(--text-faint)', fontVariantNumeric: 'tabular-nums',
        }}>{c.count}</span>
      </div>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, paddingLeft: 19,
      }}>
        <div style={{ display: 'flex', gap: 3 }}>
          {c.senders.map(s => (
            <span key={s} style={{
              width: 5, height: 5, borderRadius: '50%',
              background: SENDER_COLORS[s]?.fg || SENDER_COLORS.default.fg,
            }} />
          ))}
        </div>
        <span style={{
          fontFamily: 'var(--mono)', fontSize: 10,
          color: 'var(--text-faint)',
        }}>{c.lastTs}</span>
      </div>
    </div>
  );
}

function MessageFeed() {
  return (
    <div style={{
      flex: 1, background: 'var(--bg-base)',
      display: 'flex', flexDirection: 'column',
      borderRight: '1px solid var(--hairline)',
      minWidth: 0,
    }}>
      {/* Feed header with channel breadcrumb */}
      <div style={{
        padding: '14px 20px', borderBottom: '1px solid var(--hairline)',
        display: 'flex', alignItems: 'center', gap: 12,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <Icon name="hash" size={13} color="var(--blue)" />
          <span style={{
            fontFamily: 'var(--mono)', fontSize: 13,
            color: 'var(--text)', fontWeight: 500,
          }}>demo:orchestrator</span>
        </div>
        <span style={{
          fontFamily: 'var(--mono)', fontSize: 10,
          color: 'var(--text-faint)', letterSpacing: '0.06em',
        }}>89 MESSAGES · 2 SENDERS · LAST 14:32:07</span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 4, alignItems: 'center' }}>
          <button style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '4px 8px', background: 'transparent',
            border: '1px solid var(--hairline-strong)', borderRadius: 4,
            color: 'var(--text-mid)', fontFamily: 'var(--mono)', fontSize: 10,
            cursor: 'pointer', letterSpacing: '0.04em',
          }}>
            <Icon name="lock" size={11} color="var(--green)" />
            <span>FOLLOW</span>
          </button>
        </div>
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflow: 'hidden', padding: '8px 0' }}>
        {DASHBOARD_DATA.messages.map(m => <MessageRow key={m.seq} m={m} />)}
      </div>

      {/* Send bar */}
      <SendBar />
    </div>
  );
}

function MessageRow({ m }) {
  return (
    <div style={{
      position: 'relative',
      padding: '8px 20px 8px 56px',
      background: m.selected ? 'rgba(88, 166, 255, 0.05)' : 'transparent',
      borderLeft: m.selected ? '2px solid var(--blue)' : '2px solid transparent',
      display: 'grid',
      gridTemplateColumns: 'auto auto 1fr auto',
      gap: 10, alignItems: 'baseline',
      cursor: 'pointer',
    }}>
      {/* seq margin */}
      <span style={{
        position: 'absolute', left: 16, top: 9,
        fontFamily: 'var(--mono)', fontSize: 10,
        color: 'var(--text-faint)', fontVariantNumeric: 'tabular-nums',
        width: 30, textAlign: 'right',
      }}>{m.seq}</span>

      {/* timestamp */}
      <span style={{
        fontFamily: 'var(--mono)', fontSize: 11,
        color: 'var(--text-dim)', fontVariantNumeric: 'tabular-nums',
      }}>{m.ts}</span>

      <SenderPill name={m.sender} size="sm" />

      <span style={{
        fontFamily: 'var(--mono)', fontSize: 12,
        color: m.selected ? 'var(--text)' : 'var(--text-mid)',
        whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
        minWidth: 0,
      }}>{m.preview}</span>

      {m.isJson && (
        <span style={{
          fontFamily: 'var(--mono)', fontSize: 9,
          color: 'var(--magenta)', opacity: 0.7,
          letterSpacing: '0.06em',
          padding: '1px 5px', border: '1px solid rgba(188, 140, 255, 0.25)',
          borderRadius: 3,
        }}>JSON</span>
      )}
    </div>
  );
}

function SendBar() {
  return (
    <div style={{
      borderTop: '1px solid var(--hairline)',
      padding: 12, background: 'var(--bg-base)',
    }}>
      <div style={{
        background: 'var(--bg-card)', borderRadius: 6,
        border: '1px solid var(--hairline-strong)',
        padding: 8,
      }}>
        {/* Top row: channel / sender */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 8, alignItems: 'center' }}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '3px 8px', background: 'var(--bg-elev)',
            borderRadius: 3, border: '1px solid var(--hairline-strong)',
          }}>
            <Icon name="hash" size={10} color="var(--blue)" />
            <span style={{
              fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text)',
            }}>demo:orchestrator</span>
            <Icon name="chev" size={9} color="var(--text-dim)" />
          </div>

          <span style={{
            fontFamily: 'var(--mono)', fontSize: 10,
            color: 'var(--text-faint)', letterSpacing: '0.06em',
          }}>FROM</span>

          <div style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '3px 8px', background: 'var(--bg-elev)',
            borderRadius: 3, border: '1px solid var(--hairline-strong)',
          }}>
            <SenderPill name="mac" size="sm" />
          </div>

          <span style={{
            marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 5,
            fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--text-faint)',
            letterSpacing: '0.06em',
          }}>
            <span style={{ width: 5, height: 5, borderRadius: '50%', background: 'var(--green)' }} />
            JSON&nbsp;OK
          </span>
        </div>

        {/* Content area with caret */}
        <div style={{
          fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--text)',
          padding: '6px 4px 14px', minHeight: 38, lineHeight: 1.5,
          display: 'flex', alignItems: 'flex-start',
        }}>
          <span style={{ color: 'var(--text-mid)' }}>{`{ "action": "pause_workers", "worker_ids": ["w-1", "w-3"] }`}</span>
          <span style={{
            display: 'inline-block', width: 7, height: 14, background: 'var(--blue)',
            marginLeft: 1, marginTop: 2, animation: 'caret 1s steps(2) infinite',
          }} />
          <style>{`@keyframes caret { 50% { opacity: 0; } }`}</style>
        </div>

        {/* Bottom row: hint + send */}
        <div style={{
          display: 'flex', alignItems: 'center',
          paddingTop: 8, borderTop: '1px solid var(--hairline)',
        }}>
          <span style={{
            fontFamily: 'var(--mono)', fontSize: 10,
            color: 'var(--text-faint)',
          }}>
            <span style={{ color: 'var(--text-dim)' }}>⌘↵</span> to send · <span style={{ color: 'var(--text-dim)' }}>⇧↵</span> for newline
          </span>
          <button style={{
            marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6,
            padding: '5px 12px',
            background: 'var(--blue)', color: '#0d1117', border: 'none',
            borderRadius: 4, fontFamily: 'var(--mono)', fontSize: 11,
            fontWeight: 600, cursor: 'pointer', letterSpacing: '0.04em',
          }}>
            <Icon name="send" size={11} color="#0d1117" stroke={2} />
            <span>SEND</span>
          </button>
        </div>
      </div>
    </div>
  );
}

function Inspector() {
  const m = DASHBOARD_DATA.selectedMsg;
  return (
    <div style={{
      width: 360, background: 'var(--bg-base)',
      display: 'flex', flexDirection: 'column',
    }}>
      <ChromeLabel>Inspector</ChromeLabel>

      <div style={{ padding: '4px 16px 0' }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12,
        }}>
          <SenderPill name={m.sender} />
          <span style={{
            fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text-mid)',
          }}>seq <span style={{ color: 'var(--text)' }}>{m.seq}</span></span>
          <span style={{
            marginLeft: 'auto', display: 'inline-flex', gap: 4,
          }}>
            <IconBtn><Icon name="copy" size={12} color="var(--text-mid)" /></IconBtn>
            <IconBtn><Icon name="bolt" size={12} color="var(--text-mid)" /></IconBtn>
          </span>
        </div>

        <div style={{ display: 'grid', gap: 1, marginBottom: 16 }}>
          <KV k="id"          v={m.id} mono />
          <KV k="channel"     v={m.channel} mono color="var(--blue)" />
          <KV k="sender"      v={m.sender} mono />
          <KV k="timestamp"   v={m.ts} mono />
          <KV k="received_at" v={m.received_at} mono />
          <KV k="latency"     v="+45ms" mono color="var(--green)" />
        </div>

        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          marginBottom: 8,
        }}>
          <Eyebrow>Content · JSON</Eyebrow>
          <span style={{
            fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--text-faint)',
          }}>156 bytes</span>
        </div>

        <div style={{
          background: 'var(--bg-deep)', borderRadius: 4,
          border: '1px solid var(--hairline)',
          padding: '10px 12px', maxHeight: 280, overflow: 'hidden',
        }}>
          <HighlightedJson value={m.content} />
        </div>

        <div style={{
          display: 'flex', gap: 6, marginTop: 10,
        }}>
          <ActionBtn icon="copy" label="Copy ID" />
          <ActionBtn icon="copy" label="Copy JSON" />
          <ActionBtn icon="arrow" label="Reply" primary />
        </div>
      </div>
    </div>
  );
}

const KV = ({ k, v, mono, color }) => (
  <div style={{
    display: 'grid', gridTemplateColumns: '90px 1fr',
    fontSize: 11, padding: '4px 0',
    borderBottom: '1px solid var(--hairline)',
  }}>
    <span style={{
      fontFamily: 'var(--mono)', color: 'var(--text-faint)',
      letterSpacing: '0.04em',
    }}>{k}</span>
    <span style={{
      fontFamily: mono ? 'var(--mono)' : 'var(--sans)',
      color: color || 'var(--text)',
      whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
    }}>{v}</span>
  </div>
);

const IconBtn = ({ children }) => (
  <button style={{
    width: 24, height: 24, padding: 0, background: 'transparent',
    border: '1px solid var(--hairline)', borderRadius: 4,
    cursor: 'pointer', display: 'inline-flex',
    alignItems: 'center', justifyContent: 'center',
  }}>{children}</button>
);

const ActionBtn = ({ icon, label, primary }) => (
  <button style={{
    display: 'inline-flex', alignItems: 'center', gap: 6,
    padding: '6px 10px',
    background: primary ? 'rgba(88, 166, 255, 0.1)' : 'var(--bg-card)',
    border: `1px solid ${primary ? 'var(--blue-dim)' : 'var(--hairline-strong)'}`,
    borderRadius: 4, color: primary ? 'var(--blue)' : 'var(--text-mid)',
    fontFamily: 'var(--mono)', fontSize: 10, cursor: 'pointer',
    letterSpacing: '0.04em', flex: 1, justifyContent: 'center',
  }}>
    <Icon name={icon} size={11} color={primary ? 'var(--blue)' : 'var(--text-mid)'} />
    <span>{label}</span>
  </button>
);

function DashboardDesktop() {
  return (
    <div style={{
      width: '100%', height: '100%',
      background: 'var(--bg-base)',
      color: 'var(--text)',
      fontFamily: 'var(--sans)',
      display: 'flex', flexDirection: 'column',
      overflow: 'hidden',
    }}>
      <HeaderBar />
      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        <Sidebar />
        <MessageFeed />
        <Inspector />
      </div>
    </div>
  );
}

window.DashboardDesktop = DashboardDesktop;
