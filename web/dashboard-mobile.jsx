// Mobile dashboard — 390×844-ish. Live-data props version.
// Same prop bag as DashboardDesktop.

function MobileHeader({ state, channels, activeId, onSelect, onNewChannel }) {
  return (
    <div style={{
      background: 'var(--bg-deep)',
      borderBottom: '1px solid var(--hairline)',
      paddingTop: 16,
    }}>
      <div style={{
        padding: '10px 16px',
        display: 'flex', alignItems: 'center', gap: 10,
      }}>
        <BridgeMark size={20} color="var(--blue)" />
        <div style={{ flex: 1 }}>
          <div style={{
            fontFamily: 'var(--mono)', fontSize: 11, fontWeight: 600,
            letterSpacing: '0.22em', color: 'var(--text)',
          }}>CLAUDE&nbsp;BRIDGE</div>
          <div style={{
            fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--text-dim)',
            marginTop: 2, display: 'flex', alignItems: 'center', gap: 6,
          }}>
            <LiveDot color="var(--green)" size={5} />
            <span>online · :8765 · {state?.uptime_human || '00:00:00'}</span>
          </div>
        </div>
      </div>

      <div style={{
        display: 'flex', gap: 6, padding: '0 16px 10px',
        overflowX: 'auto',
      }}>
        {(channels || []).map(c => {
          const active = c.id === activeId;
          return (
            <div key={c.id} onClick={() => onSelect && onSelect(c.id)} style={{
              flexShrink: 0, padding: '6px 10px',
              background: active ? 'var(--bg-elev)' : 'transparent',
              border: `1px solid ${active ? 'var(--blue-dim)' : 'var(--hairline-strong)'}`,
              borderRadius: 4,
              display: 'flex', alignItems: 'center', gap: 6,
              cursor: 'pointer',
            }}>
              <Icon name="hash" size={10} color={active ? 'var(--blue)' : 'var(--text-dim)'} />
              <span style={{
                fontFamily: 'var(--mono)', fontSize: 11,
                color: active ? 'var(--text)' : 'var(--text-mid)',
                fontWeight: active ? 500 : 400,
              }}>{c.id}</span>
              <span style={{
                fontFamily: 'var(--mono)', fontSize: 9,
                color: 'var(--text-faint)', fontVariantNumeric: 'tabular-nums',
              }}>{c.count}</span>
            </div>
          );
        })}
        {(!channels || channels.length === 0) && (
          <span style={{
            fontFamily: 'var(--mono)', fontSize: 10,
            color: 'var(--text-faint)', padding: '4px 0',
          }}>No channels yet</span>
        )}
        <button
          onClick={() => onNewChannel && onNewChannel()}
          title="New channel"
          style={{
            flexShrink: 0, padding: '6px 10px',
            background: 'transparent',
            border: '1px dashed var(--hairline-strong)',
            borderRadius: 4, color: 'var(--blue)',
            fontFamily: 'var(--mono)', fontSize: 11, cursor: 'pointer',
            display: 'inline-flex', alignItems: 'center', gap: 4,
          }}
        >
          <span>+</span>
          <span>NEW</span>
        </button>
      </div>
    </div>
  );
}

function MobileMessageRow({ m, selected, onSelect }) {
  return (
    <div onClick={onSelect} style={{
      padding: '12px 16px',
      borderBottom: '1px solid var(--hairline)',
      background: selected ? 'rgba(88, 166, 255, 0.05)' : 'transparent',
      borderLeft: selected ? '2px solid var(--blue)' : '2px solid transparent',
      cursor: 'pointer',
    }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6,
      }}>
        <SenderPill name={m.sender} size="sm" />
        <span style={{
          fontFamily: 'var(--mono)', fontSize: 10,
          color: 'var(--text-faint)', fontVariantNumeric: 'tabular-nums',
        }}>seq {m.seq}</span>
        <span style={{
          marginLeft: 'auto',
          fontFamily: 'var(--mono)', fontSize: 10,
          color: 'var(--text-dim)', fontVariantNumeric: 'tabular-nums',
        }}>{m.ts}</span>
        {m.is_json && (
          <span style={{
            fontFamily: 'var(--mono)', fontSize: 8.5,
            color: 'var(--magenta)', opacity: 0.7,
            padding: '1px 4px', border: '1px solid rgba(188, 140, 255, 0.25)',
            borderRadius: 2,
          }}>JSON</span>
        )}
      </div>
      <div style={{
        fontFamily: 'var(--mono)', fontSize: 11,
        color: selected ? 'var(--text)' : 'var(--text-mid)',
        lineHeight: 1.45,
        display: '-webkit-box', WebkitBoxOrient: 'vertical', WebkitLineClamp: 3,
        overflow: 'hidden',
      }}>{m.preview}</div>
    </div>
  );
}

function MobileSheet({ detail, channel, defaultSender, onSend }) {
  const [content, setContent] = React.useState('');
  const [sending, setSending] = React.useState(false);
  const handleSend = async () => {
    if (!content.trim() || sending || !channel) return;
    setSending(true);
    try {
      await onSend({ channel, sender: defaultSender || 'dashboard', content });
      setContent('');
    } finally {
      setSending(false);
    }
  };
  return (
    <div style={{
      background: 'var(--bg-card)',
      borderTop: '1px solid var(--hairline-strong)',
      borderTopLeftRadius: 12, borderTopRightRadius: 12,
      padding: '6px 16px 18px',
      boxShadow: '0 -8px 32px rgba(0,0,0,0.5)',
    }}>
      <div style={{
        width: 40, height: 4, borderRadius: 2,
        background: 'var(--hairline-strong)',
        margin: '4px auto 10px',
      }} />

      {detail && (
        <>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8,
          }}>
            <Eyebrow>Inspector · seq {detail.seq}</Eyebrow>
            <SenderPill name={detail.sender} size="sm" />
          </div>

          <div style={{
            background: 'var(--bg-deep)', borderRadius: 4,
            border: '1px solid var(--hairline)',
            padding: 10, fontFamily: 'var(--mono)', fontSize: 10.5,
            maxHeight: 140, overflow: 'auto',
          }}>
            {detail.is_json && detail.content_parsed != null
              ? <HighlightedJson value={detail.content_parsed} />
              : <pre style={{
                  margin: 0, fontFamily: 'var(--mono)', fontSize: 10.5,
                  color: 'var(--text-mid)', whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                }}>{detail.content}</pre>
            }
          </div>
        </>
      )}

      <div style={{
        marginTop: 10,
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '6px 10px',
        background: 'var(--bg-base)',
        border: '1px solid var(--hairline-strong)',
        borderRadius: 6,
      }}>
        <SenderPill name={defaultSender || 'dashboard'} size="sm" />
        <input
          value={content}
          onChange={e => setContent(e.target.value)}
          placeholder={channel ? `send to ${channel}…` : 'pick a channel first'}
          disabled={!channel}
          onKeyDown={e => { if (e.key === 'Enter') handleSend(); }}
          style={{
            fontFamily: 'var(--mono)', fontSize: 11,
            color: 'var(--text)', background: 'transparent',
            border: 'none', outline: 'none', flex: 1, minWidth: 0,
          }}
        />
        <button onClick={handleSend} disabled={!content.trim() || sending || !channel} style={{
          width: 28, height: 28, padding: 0,
          background: content.trim() && channel ? 'var(--blue)' : 'var(--bg-elev)',
          border: 'none', borderRadius: 4,
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          cursor: content.trim() && channel ? 'pointer' : 'not-allowed',
          opacity: sending ? 0.6 : 1,
        }}>
          <Icon name="send" size={13} color={content.trim() && channel ? '#0d1117' : 'var(--text-faint)'} stroke={2} />
        </button>
      </div>
    </div>
  );
}

function DashboardMobile(props) {
  const channelMeta = props.channelMeta;
  return (
    <div style={{
      width: '100%', height: '100%',
      background: 'var(--bg-base)',
      color: 'var(--text)',
      fontFamily: 'var(--sans)',
      display: 'flex', flexDirection: 'column',
      overflow: 'hidden', position: 'relative',
    }}>
      <MobileHeader
        state={props.state}
        channels={props.state?.channels}
        onNewChannel={props.onNewChannel}
        activeId={props.activeChannel}
        onSelect={props.onSelectChannel}
      />

      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '10px 16px',
        background: 'var(--bg-card)',
        borderBottom: '1px solid var(--hairline)',
      }}>
        <Icon name="hash" size={12} color="var(--blue)" />
        <span style={{
          fontFamily: 'var(--mono)', fontSize: 12,
          color: 'var(--text)', fontWeight: 500,
        }}>{props.activeChannel || '— no channel —'}</span>
        <span style={{
          marginLeft: 'auto',
          fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--text-faint)',
        }}>{channelMeta?.count ?? 0} msgs</span>
      </div>

      <div style={{ flex: 1, overflowY: 'auto' }}>
        {(props.messages || []).map(m => (
          <MobileMessageRow
            key={m.id} m={m}
            selected={m.id === props.selectedId}
            onSelect={() => props.onSelectMessage && props.onSelectMessage(m)}
          />
        ))}
        {props.messages && props.messages.length === 0 && (
          <div style={{
            padding: '40px 20px', textAlign: 'center',
            fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text-faint)',
          }}>
            No messages on this channel.
          </div>
        )}
      </div>

      <MobileSheet
        detail={props.detail}
        channel={props.activeChannel}
        defaultSender={props.defaultSender}
        onSend={props.onSend}
      />
    </div>
  );
}

window.DashboardMobile = DashboardMobile;
