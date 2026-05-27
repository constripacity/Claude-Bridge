// Mobile dashboard — 390×844 (iPhone 15 Pro). Horizontal channel tabs,
// stacked message feed, bottom-sheet inspector peeking up.

function MobileHeader() {
  return (
    <div style={{
      background: 'var(--bg-deep)',
      borderBottom: '1px solid var(--hairline)',
      paddingTop: 50, /* status bar gutter */
    }}>
      {/* iOS-ish status bar */}
      <div style={{
        position: 'absolute', top: 14, left: 0, right: 0,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '0 28px', color: 'var(--text)',
        fontFamily: 'var(--sans)', fontSize: 15, fontWeight: 600,
      }}>
        <span>14:32</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <svg width="18" height="11" viewBox="0 0 18 11" fill="currentColor"><rect x="0" y="6" width="3" height="5"/><rect x="5" y="4" width="3" height="7"/><rect x="10" y="2" width="3" height="9"/><rect x="15" y="0" width="3" height="11"/></svg>
          <Icon name="wifi" size={14} color="var(--text)" stroke={2} />
          <svg width="25" height="11" viewBox="0 0 25 11" fill="none" stroke="currentColor" strokeWidth="1"><rect x="0.5" y="0.5" width="22" height="10" rx="2"/><rect x="23.5" y="3.5" width="1" height="4" fill="currentColor"/><rect x="2" y="2" width="14" height="7" fill="currentColor"/></svg>
        </div>
      </div>

      {/* App bar */}
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
            <span>online · :8765 · 00:34:12</span>
          </div>
        </div>
        <button style={{
          width: 32, height: 32, padding: 0,
          border: '1px solid var(--hairline-strong)', background: 'transparent',
          borderRadius: 6, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <Icon name="gear" size={14} color="var(--text-mid)" />
        </button>
      </div>

      {/* Channel tab row */}
      <div style={{
        display: 'flex', gap: 6, padding: '0 16px 10px',
        overflowX: 'auto',
      }}>
        {DASHBOARD_DATA.channels.map(c => (
          <div key={c.id} style={{
            flexShrink: 0, padding: '6px 10px',
            background: c.active ? 'var(--bg-elev)' : 'transparent',
            border: `1px solid ${c.active ? 'var(--blue-dim)' : 'var(--hairline-strong)'}`,
            borderRadius: 4,
            display: 'flex', alignItems: 'center', gap: 6,
          }}>
            <Icon name="hash" size={10} color={c.active ? 'var(--blue)' : 'var(--text-dim)'} />
            <span style={{
              fontFamily: 'var(--mono)', fontSize: 11,
              color: c.active ? 'var(--text)' : 'var(--text-mid)',
              fontWeight: c.active ? 500 : 400,
            }}>{c.group}:{c.name}</span>
            <span style={{
              fontFamily: 'var(--mono)', fontSize: 9,
              color: 'var(--text-faint)',
              fontVariantNumeric: 'tabular-nums',
            }}>{c.count}</span>
            {c.unread && (
              <span style={{
                width: 5, height: 5, borderRadius: '50%',
                background: 'var(--blue)',
              }} />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function MobileMessageRow({ m }) {
  return (
    <div style={{
      padding: '12px 16px',
      borderBottom: '1px solid var(--hairline)',
      background: m.selected ? 'rgba(88, 166, 255, 0.05)' : 'transparent',
      borderLeft: m.selected ? '2px solid var(--blue)' : '2px solid transparent',
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
        {m.isJson && (
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
        color: m.selected ? 'var(--text)' : 'var(--text-mid)',
        lineHeight: 1.45,
        display: '-webkit-box', WebkitBoxOrient: 'vertical', WebkitLineClamp: 2,
        overflow: 'hidden',
      }}>{m.preview}</div>
    </div>
  );
}

function DashboardMobile() {
  return (
    <div style={{
      width: '100%', height: '100%',
      background: 'var(--bg-base)',
      color: 'var(--text)',
      fontFamily: 'var(--sans)',
      display: 'flex', flexDirection: 'column',
      overflow: 'hidden', position: 'relative',
    }}>
      <MobileHeader />

      {/* Channel breadcrumb / state bar */}
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
        }}>demo:orchestrator</span>
        <span style={{
          marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6,
          fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--text-faint)',
        }}>
          <Icon name="lock" size={10} color="var(--green)" />
          FOLLOW
        </span>
      </div>

      {/* Feed */}
      <div style={{
        flex: 1, overflow: 'hidden',
      }}>
        {DASHBOARD_DATA.messages.slice(2).map(m => (
          <MobileMessageRow key={m.seq} m={m} />
        ))}
      </div>

      {/* Bottom sheet — inspector peek */}
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

        <div style={{
          display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8,
        }}>
          <Eyebrow>Inspector · seq 45</Eyebrow>
          <SenderPill name="windows" size="sm" />
          <span style={{
            marginLeft: 'auto', fontFamily: 'var(--mono)', fontSize: 10,
            color: 'var(--text-faint)',
          }}>+45ms</span>
        </div>

        <div style={{
          background: 'var(--bg-deep)', borderRadius: 4,
          border: '1px solid var(--hairline)',
          padding: 10, fontFamily: 'var(--mono)', fontSize: 10.5,
          maxHeight: 110, overflow: 'hidden',
        }}>
          <HighlightedJson value={DASHBOARD_DATA.selectedMsg.content} />
        </div>

        {/* Mini compose */}
        <div style={{
          marginTop: 10,
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '8px 10px',
          background: 'var(--bg-base)',
          border: '1px solid var(--hairline-strong)',
          borderRadius: 6,
        }}>
          <SenderPill name="mac" size="sm" />
          <span style={{
            fontFamily: 'var(--mono)', fontSize: 11,
            color: 'var(--text-dim)', flex: 1,
            whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          }}>send to demo:orchestrator…</span>
          <button style={{
            width: 28, height: 28, padding: 0,
            background: 'var(--blue)', border: 'none', borderRadius: 4,
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Icon name="send" size={13} color="#0d1117" stroke={2} />
          </button>
        </div>
      </div>

      {/* Home indicator */}
      <div style={{
        position: 'absolute', bottom: 8, left: '50%', transform: 'translateX(-50%)',
        width: 134, height: 5, borderRadius: 3, background: 'var(--text)',
      }} />
    </div>
  );
}

window.DashboardMobile = DashboardMobile;
