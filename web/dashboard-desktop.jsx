// Desktop dashboard — 1280×800, dark, three-column. Live-data props version.
// Receives { state, channels, activeChannel, channelMeta, messages,
//           selectedId, detail, onSelectChannel, onSelectMessage,
//           onSend, onClear, defaultSender }

const { useState } = React;

function HeaderBar({ state }) {
  const totals = {
    channels: state?.channels?.length ?? 0,
    messages: state?.total_messages ?? 0,
    uptime:   state?.uptime_human ?? '00:00:00',
    version:  state?.version ?? '—',
  };
  return (
    <div style={{
      height: 48, background: 'var(--bg-deep)',
      borderBottom: '1px solid var(--hairline)',
      display: 'flex', alignItems: 'center', padding: '0 20px',
      position: 'relative',
    }}>
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
        }}>v{totals.version}</span>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 18, marginLeft: 32 }}>
        <Stat label="STATUS" value={
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <LiveDot color="var(--green)" />
            <span style={{ color: 'var(--green)' }}>online</span>
          </span>
        } />
        <Stat label="PORT"     value=":8765" mono />
        <Stat label="UPTIME"   value={totals.uptime} mono />
        <Stat label="CHANNELS" value={totals.channels} mono />
        <Stat label="MESSAGES" value={totals.messages} mono />
      </div>

      <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6 }}>
        <HeaderBtn><Icon name="search" size={14} color="var(--text-mid)" /></HeaderBtn>
        <HeaderBtn><Icon name="book"   size={14} color="var(--text-mid)" /></HeaderBtn>
        <HeaderBtn><Icon name="gear"   size={14} color="var(--text-mid)" /></HeaderBtn>
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

function Sidebar({ channels, activeId, onSelect }) {
  const grouped = {};
  (channels || []).forEach(c => {
    grouped[c.group || ''] = grouped[c.group || ''] || [];
    grouped[c.group || ''].push(c);
  });
  return (
    <div style={{
      width: 252, background: 'var(--bg-base)',
      borderRight: '1px solid var(--hairline)',
      display: 'flex', flexDirection: 'column',
    }}>
      <ChromeLabel count={channels?.length ?? 0}>Channels</ChromeLabel>
      <div style={{ flex: 1, overflowY: 'auto', padding: '0 8px' }}>
        {Object.entries(grouped).map(([group, chs]) => (
          <div key={group} style={{ marginBottom: 14 }}>
            <div style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '4px 8px 6px', color: 'var(--text-faint)',
              fontFamily: 'var(--mono)', fontSize: 10, fontWeight: 500,
              letterSpacing: '0.12em',
            }}>
              <Icon name="chev" size={10} color="var(--text-faint)" />
              <span>{group || 'ungrouped'}:</span>
              <span style={{ color: 'var(--text-faint)', opacity: 0.7 }}>{chs.length}</span>
            </div>
            {chs.map(c => (
              <ChannelRow key={c.id} c={c} active={c.id === activeId} onSelect={onSelect} />
            ))}
          </div>
        ))}
        {(!channels || channels.length === 0) && (
          <div style={{
            padding: '24px 12px', fontFamily: 'var(--mono)', fontSize: 11,
            color: 'var(--text-faint)', lineHeight: 1.6, textAlign: 'center',
          }}>
            No channels yet.<br />
            Send a message from any<br />
            connected Claude Code.
          </div>
        )}
      </div>
    </div>
  );
}

function ChannelRow({ c, active, onSelect }) {
  return (
    <div onClick={() => onSelect && onSelect(c.id)} style={{
      position: 'relative',
      padding: '8px 10px 8px 12px',
      borderRadius: 4,
      background: active ? 'var(--bg-elev)' : 'transparent',
      marginBottom: 1, cursor: 'pointer',
    }}>
      {active && (
        <div style={{
          position: 'absolute', left: 0, top: 4, bottom: 4, width: 2,
          background: 'var(--blue)', borderRadius: 1,
        }} />
      )}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
        <Icon name="hash" size={11} color={active ? 'var(--blue)' : 'var(--text-dim)'} />
        <span style={{
          fontFamily: 'var(--mono)', fontSize: 12,
          color: active ? 'var(--text)' : 'var(--text-mid)',
          fontWeight: active ? 500 : 400, flex: 1,
          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
        }}>{c.name}</span>
        <span style={{
          fontFamily: 'var(--mono)', fontSize: 10,
          color: 'var(--text-faint)', fontVariantNumeric: 'tabular-nums',
        }}>{c.count}</span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, paddingLeft: 19 }}>
        <div style={{ display: 'flex', gap: 3 }}>
          {(c.senders || []).map(s => (
            <span key={s} style={{
              width: 5, height: 5, borderRadius: '50%',
              background: SENDER_COLORS[s]?.fg || SENDER_COLORS.default.fg,
            }} />
          ))}
        </div>
        <span style={{
          fontFamily: 'var(--mono)', fontSize: 10,
          color: 'var(--text-faint)',
        }}>{c.last_ts || '—'}</span>
      </div>
    </div>
  );
}

function MessageFeed({ channel, channelMeta, messages, selectedId, onSelect, onSend, onClear, defaultSender }) {
  const lastTs = channelMeta?.last_ts || '—';
  const senderCount = channelMeta?.senders?.length ?? 0;
  return (
    <div style={{
      flex: 1, background: 'var(--bg-base)',
      display: 'flex', flexDirection: 'column',
      borderRight: '1px solid var(--hairline)',
      minWidth: 0,
    }}>
      <div style={{
        padding: '14px 20px', borderBottom: '1px solid var(--hairline)',
        display: 'flex', alignItems: 'center', gap: 12,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <Icon name="hash" size={13} color="var(--blue)" />
          <span style={{
            fontFamily: 'var(--mono)', fontSize: 13,
            color: 'var(--text)', fontWeight: 500,
          }}>{channel || '— no channel —'}</span>
        </div>
        <span style={{
          fontFamily: 'var(--mono)', fontSize: 10,
          color: 'var(--text-faint)', letterSpacing: '0.06em',
        }}>{(channelMeta?.count ?? 0)} MESSAGES · {senderCount} SENDERS · LAST {lastTs}</span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 6, alignItems: 'center' }}>
          {channel && (
            <button onClick={() => onClear && onClear(channel)} title="Clear this channel" style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '4px 8px', background: 'transparent',
              border: '1px solid var(--hairline-strong)', borderRadius: 4,
              color: 'var(--text-mid)', fontFamily: 'var(--mono)', fontSize: 10,
              cursor: 'pointer', letterSpacing: '0.04em',
            }}>
              <Icon name="close" size={11} color="var(--text-mid)" />
              <span>CLEAR</span>
            </button>
          )}
        </div>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
        {(messages || []).map(m => (
          <MessageRow
            key={m.id}
            m={m}
            selected={m.id === selectedId}
            onSelect={() => onSelect && onSelect(m)}
          />
        ))}
        {messages && messages.length === 0 && (
          <div style={{
            padding: '40px 20px', textAlign: 'center',
            fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text-faint)',
          }}>
            No messages on this channel yet.
          </div>
        )}
      </div>

      {channel && <SendBar channel={channel} defaultSender={defaultSender} onSend={onSend} />}
    </div>
  );
}

function MessageRow({ m, selected, onSelect }) {
  return (
    <div onClick={onSelect} style={{
      position: 'relative',
      padding: '8px 20px 8px 56px',
      background: selected ? 'rgba(88, 166, 255, 0.05)' : 'transparent',
      borderLeft: selected ? '2px solid var(--blue)' : '2px solid transparent',
      display: 'grid',
      gridTemplateColumns: 'auto auto 1fr auto',
      gap: 10, alignItems: 'baseline',
      cursor: 'pointer',
    }}>
      <span style={{
        position: 'absolute', left: 16, top: 9,
        fontFamily: 'var(--mono)', fontSize: 10,
        color: 'var(--text-faint)', fontVariantNumeric: 'tabular-nums',
        width: 30, textAlign: 'right',
      }}>{m.seq}</span>

      <span style={{
        fontFamily: 'var(--mono)', fontSize: 11,
        color: 'var(--text-dim)', fontVariantNumeric: 'tabular-nums',
      }}>{m.ts}</span>

      <SenderPill name={m.sender} size="sm" />

      <span style={{
        fontFamily: 'var(--mono)', fontSize: 12,
        color: selected ? 'var(--text)' : 'var(--text-mid)',
        whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
        minWidth: 0,
      }}>{m.preview}</span>

      {m.is_json && (
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

function SendBar({ channel, defaultSender, onSend }) {
  const [sender, setSender] = useState(defaultSender || 'dashboard');
  const [content, setContent] = useState('');
  const [sending, setSending] = useState(false);

  const handleSend = async () => {
    if (!content.trim() || sending) return;
    setSending(true);
    try {
      await onSend({ channel, sender, content });
      setContent('');
    } finally {
      setSending(false);
    }
  };

  const handleKey = (e) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleSend();
    }
  };

  const senderOptions = ['windows', 'mac', 'linux', 'watcher', 'dashboard'];
  const senderValid = content.trim().length > 0;

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
        <div style={{ display: 'flex', gap: 8, marginBottom: 8, alignItems: 'center' }}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '3px 8px', background: 'var(--bg-elev)',
            borderRadius: 3, border: '1px solid var(--hairline-strong)',
          }}>
            <Icon name="hash" size={10} color="var(--blue)" />
            <span style={{
              fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text)',
            }}>{channel}</span>
          </div>

          <span style={{
            fontFamily: 'var(--mono)', fontSize: 10,
            color: 'var(--text-faint)', letterSpacing: '0.06em',
          }}>FROM</span>

          <select value={sender} onChange={e => setSender(e.target.value)} style={{
            padding: '3px 6px', background: 'var(--bg-elev)',
            border: '1px solid var(--hairline-strong)', borderRadius: 3,
            color: 'var(--text)', fontFamily: 'var(--mono)', fontSize: 11,
            cursor: 'pointer',
          }}>
            {senderOptions.map(s => <option key={s} value={s}>{s}</option>)}
          </select>

          <span style={{
            marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 5,
            fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--text-faint)',
            letterSpacing: '0.06em',
          }}>
            <span style={{
              width: 5, height: 5, borderRadius: '50%',
              background: senderValid ? 'var(--green)' : 'var(--text-faint)',
            }} />
            {senderValid ? 'READY' : 'EMPTY'}
          </span>
        </div>

        <textarea
          value={content}
          onChange={e => setContent(e.target.value)}
          onKeyDown={handleKey}
          placeholder='Type a message or paste JSON…'
          style={{
            width: '100%', boxSizing: 'border-box',
            fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--text)',
            padding: '6px 4px 6px 4px', minHeight: 42, lineHeight: 1.5,
            background: 'transparent', border: 'none', outline: 'none',
            resize: 'vertical',
          }}
        />

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
          <button
            onClick={handleSend}
            disabled={!senderValid || sending}
            style={{
              marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6,
              padding: '5px 12px',
              background: senderValid ? 'var(--blue)' : 'var(--bg-elev)',
              color: senderValid ? '#0d1117' : 'var(--text-faint)',
              border: 'none', borderRadius: 4,
              fontFamily: 'var(--mono)', fontSize: 11, fontWeight: 600,
              cursor: senderValid && !sending ? 'pointer' : 'not-allowed',
              letterSpacing: '0.04em', opacity: sending ? 0.6 : 1,
            }}>
            <Icon name="send" size={11} color={senderValid ? '#0d1117' : 'var(--text-faint)'} stroke={2} />
            <span>{sending ? 'SENDING…' : 'SEND'}</span>
          </button>
        </div>
      </div>
    </div>
  );
}

function Inspector({ detail }) {
  if (!detail) {
    return (
      <div style={{
        width: 360, background: 'var(--bg-base)',
        display: 'flex', flexDirection: 'column',
      }}>
        <ChromeLabel>Inspector</ChromeLabel>
        <div style={{
          padding: '24px 16px', fontFamily: 'var(--mono)', fontSize: 11,
          color: 'var(--text-faint)', lineHeight: 1.6,
        }}>
          Select a message to inspect.
        </div>
      </div>
    );
  }
  const ts = (detail.ts || '').replace('T', ' ').replace('Z', '');
  return (
    <div style={{
      width: 360, background: 'var(--bg-base)',
      display: 'flex', flexDirection: 'column',
    }}>
      <ChromeLabel>Inspector</ChromeLabel>

      <div style={{ padding: '4px 16px 0', overflowY: 'auto' }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12,
        }}>
          <SenderPill name={detail.sender} />
          <span style={{
            fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text-mid)',
          }}>seq <span style={{ color: 'var(--text)' }}>{detail.seq}</span></span>
          <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 4 }}>
            <IconBtn onClick={() => navigator.clipboard?.writeText(detail.id)} title="Copy ID">
              <Icon name="copy" size={12} color="var(--text-mid)" />
            </IconBtn>
            <IconBtn onClick={() => navigator.clipboard?.writeText(detail.content)} title="Copy content">
              <Icon name="bolt" size={12} color="var(--text-mid)" />
            </IconBtn>
          </span>
        </div>

        <div style={{ display: 'grid', gap: 1, marginBottom: 16 }}>
          <KV k="id"        v={detail.id} mono />
          <KV k="channel"   v={detail.channel} mono color="var(--blue)" />
          <KV k="sender"    v={detail.sender} mono />
          <KV k="timestamp" v={ts} mono />
          <KV k="bytes"     v={String(detail.bytes)} mono color="var(--text-mid)" />
        </div>

        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          marginBottom: 8,
        }}>
          <Eyebrow>{detail.is_json ? 'Content · JSON' : 'Content · TEXT'}</Eyebrow>
          <span style={{
            fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--text-faint)',
          }}>{detail.bytes} bytes</span>
        </div>

        <div style={{
          background: 'var(--bg-deep)', borderRadius: 4,
          border: '1px solid var(--hairline)',
          padding: '10px 12px', maxHeight: 360, overflow: 'auto',
        }}>
          {detail.is_json && detail.content_parsed != null
            ? <HighlightedJson value={detail.content_parsed} />
            : <pre style={{
                margin: 0, fontFamily: 'var(--mono)', fontSize: 12,
                color: 'var(--text-mid)', whiteSpace: 'pre-wrap', wordBreak: 'break-word',
              }}>{detail.content}</pre>
          }
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

const IconBtn = ({ children, onClick, title }) => (
  <button onClick={onClick} title={title} style={{
    width: 24, height: 24, padding: 0, background: 'transparent',
    border: '1px solid var(--hairline)', borderRadius: 4,
    cursor: 'pointer', display: 'inline-flex',
    alignItems: 'center', justifyContent: 'center',
  }}>{children}</button>
);

function DashboardDesktop(props) {
  return (
    <div style={{
      width: '100%', height: '100%',
      background: 'var(--bg-base)',
      color: 'var(--text)',
      fontFamily: 'var(--sans)',
      display: 'flex', flexDirection: 'column',
      overflow: 'hidden',
    }}>
      <HeaderBar state={props.state} />
      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        <Sidebar
          channels={props.state?.channels}
          activeId={props.activeChannel}
          onSelect={props.onSelectChannel}
        />
        <MessageFeed
          channel={props.activeChannel}
          channelMeta={props.channelMeta}
          messages={props.messages}
          selectedId={props.selectedId}
          onSelect={props.onSelectMessage}
          onSend={props.onSend}
          onClear={props.onClear}
          defaultSender={props.defaultSender}
        />
        <Inspector detail={props.detail} />
      </div>
    </div>
  );
}

window.DashboardDesktop = DashboardDesktop;
