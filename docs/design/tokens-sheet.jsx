// Tokens & component sheet — 1200×1700

const PALETTE = {
  Background: [
    { name: '--bg-deep', value: '#08090d', use: 'Header bar · code blocks' },
    { name: '--bg-base', value: '#0d1117', use: 'App background' },
    { name: '--bg-card', value: '#161b22', use: 'Cards · compose · 2nd surface' },
    { name: '--bg-elev', value: '#1c2333', use: 'Active row · 3rd surface' },
  ],
  Signal: [
    { name: '--blue',    value: '#58a6ff', use: 'Active · live · data · CTAs' },
    { name: '--green',   value: '#3fb950', use: 'Online · success · received' },
    { name: '--amber',   value: '#d97706', use: 'Warn · Claude identity' },
    { name: '--red',     value: '#f85149', use: 'Error · destructive · invalid' },
    { name: '--magenta', value: '#bc8cff', use: 'JSON · meta · keywords' },
  ],
  Text: [
    { name: '--text',       value: '#e6edf3', use: 'Primary' },
    { name: '--text-mid',   value: '#8b949e', use: 'Body · labels' },
    { name: '--text-dim',   value: '#6e7681', use: 'Tertiary · meta' },
    { name: '--text-faint', value: '#484f58', use: 'Disabled · seq numbers' },
  ],
  Structure: [
    { name: '--hairline',          value: '#21262d', use: 'Most borders' },
    { name: '--hairline-strong',   value: '#30363d', use: 'Focused / hover' },
  ],
};

function SwatchRow({ group, items }) {
  return (
    <div style={{ marginBottom: 18 }}>
      <Eyebrow color="var(--text-dim)">{group}</Eyebrow>
      <div style={{ marginTop: 8, display: 'grid', gap: 1, background: 'var(--hairline)' }}>
        {items.map(s => (
          <div key={s.name} style={{
            display: 'grid', gridTemplateColumns: '52px 1fr 1fr 1.4fr',
            gap: 0, alignItems: 'center',
            background: 'var(--bg-base)', padding: '9px 12px',
          }}>
            <div style={{
              width: 32, height: 32, borderRadius: 3, background: s.value,
              border: '1px solid var(--hairline-strong)',
            }} />
            <span style={{
              fontFamily: 'var(--mono)', fontSize: 11.5, color: 'var(--text)',
            }}>{s.name}</span>
            <span style={{
              fontFamily: 'var(--mono)', fontSize: 11.5, color: 'var(--text-mid)',
            }}>{s.value}</span>
            <span style={{
              fontFamily: 'var(--sans)', fontSize: 11.5, color: 'var(--text-dim)',
            }}>{s.use}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function TypeRow({ label, sample, props }) {
  return (
    <div style={{
      display: 'grid', gridTemplateColumns: '180px 1fr 280px',
      gap: 24, padding: '14px 0',
      borderBottom: '1px solid var(--hairline)',
      alignItems: 'baseline',
    }}>
      <Eyebrow color="var(--text-dim)">{label}</Eyebrow>
      <div style={props.style}>{sample}</div>
      <div style={{
        fontFamily: 'var(--mono)', fontSize: 10.5, color: 'var(--text-faint)',
      }}>{props.spec}</div>
    </div>
  );
}

function ComponentState({ label, children }) {
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', gap: 10,
      padding: 18, background: 'var(--bg-base)',
      border: '1px solid var(--hairline)', borderRadius: 4,
    }}>
      <Eyebrow color="var(--text-dim)">{label}</Eyebrow>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {children}
      </div>
    </div>
  );
}

// Mini channel-row sample
const MiniChannel = ({ state, name = 'demo:orchestrator', count = 89 }) => {
  const isActive = state === 'active';
  const isHover = state === 'hover';
  const isDisabled = state === 'disabled';
  return (
    <div style={{
      position: 'relative', padding: '7px 10px 7px 12px', borderRadius: 4,
      background: isActive ? 'var(--bg-elev)' : isHover ? 'var(--bg-card)' : 'transparent',
      opacity: isDisabled ? 0.4 : 1,
      display: 'flex', alignItems: 'center', gap: 8,
    }}>
      {isActive && <div style={{
        position: 'absolute', left: 0, top: 4, bottom: 4, width: 2,
        background: 'var(--blue)', borderRadius: 1,
      }} />}
      <Icon name="hash" size={11} color={isActive ? 'var(--blue)' : 'var(--text-dim)'} />
      <span style={{
        fontFamily: 'var(--mono)', fontSize: 12,
        color: isActive ? 'var(--text)' : 'var(--text-mid)',
        flex: 1,
      }}>{name}</span>
      <span style={{
        fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--text-faint)',
      }}>{count}</span>
    </div>
  );
};

// Mini message row sample
const MiniMessage = ({ state }) => {
  const selected = state === 'selected';
  const hover = state === 'hover';
  return (
    <div style={{
      padding: '7px 10px',
      background: selected ? 'rgba(88, 166, 255, 0.05)' : hover ? 'var(--bg-card)' : 'transparent',
      borderLeft: selected ? '2px solid var(--blue)' : '2px solid transparent',
      display: 'grid',
      gridTemplateColumns: 'auto auto 1fr auto', gap: 8, alignItems: 'baseline',
    }}>
      <span style={{
        fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--text-faint)',
        fontVariantNumeric: 'tabular-nums', width: 22, textAlign: 'right',
      }}>45</span>
      <span style={{
        fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--text-dim)',
      }}>14:32:01</span>
      <SenderPill name="windows" size="sm" />
      <span style={{
        fontFamily: 'var(--mono)', fontSize: 10,
        color: selected ? 'var(--text)' : 'var(--text-mid)',
        whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
      }}>{ '{ "progress": 0.27 }' }</span>
    </div>
  );
};

const Btn = ({ variant = 'primary', state, children = 'SEND' }) => {
  const styles = {
    primary: {
      bg: state === 'hover' ? '#79b8ff' : state === 'active' ? '#1f6feb' : 'var(--blue)',
      fg: '#0d1117', border: 'transparent',
    },
    ghost: {
      bg: state === 'hover' ? 'var(--bg-card)' : 'transparent',
      fg: 'var(--text)', border: 'var(--hairline-strong)',
    },
    danger: {
      bg: state === 'hover' ? 'rgba(248, 81, 73, 0.12)' : 'transparent',
      fg: 'var(--red)', border: 'rgba(248, 81, 73, 0.4)',
    },
  };
  const s = styles[variant];
  return (
    <button disabled={state === 'disabled'} style={{
      padding: '6px 12px', background: s.bg, color: s.fg,
      border: `1px solid ${s.border}`, borderRadius: 4,
      fontFamily: 'var(--mono)', fontSize: 11, fontWeight: 600,
      letterSpacing: '0.06em', cursor: 'pointer',
      opacity: state === 'disabled' ? 0.4 : 1,
      display: 'inline-flex', alignItems: 'center', gap: 6,
    }}>
      <Icon name="send" size={11} color={s.fg} stroke={2} />
      {children}
    </button>
  );
};

function TokensSheet() {
  const SP = [4, 8, 12, 16, 20, 24, 32, 48, 64];
  return (
    <div style={{
      width: '100%', height: '100%', background: 'var(--bg-base)',
      color: 'var(--text)', fontFamily: 'var(--sans)',
      padding: '48px 56px', boxSizing: 'border-box',
      overflow: 'hidden',
    }}>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'baseline', justifyContent: 'space-between',
        marginBottom: 32, paddingBottom: 22,
        borderBottom: '1px solid var(--hairline)',
      }}>
        <div>
          <Eyebrow color="var(--blue)">DESIGN SYSTEM · v0.3</Eyebrow>
          <h2 style={{
            margin: '6px 0 4px',
            fontFamily: 'var(--mono)', fontSize: 32, fontWeight: 700,
            letterSpacing: '-0.01em', color: 'var(--text)',
          }}>Tokens & Components</h2>
          <p style={{ margin: 0, color: 'var(--text-mid)', fontSize: 13 }}>
            Variables, type scale, spacing, and component states.
          </p>
        </div>
        <div style={{
          fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text-dim)',
          textAlign: 'right',
        }}>
          <div>{'/* tokens.css */'}</div>
          <div style={{ color: 'var(--text-faint)' }}>17 colors · 6 type sizes · 9 spacing steps</div>
        </div>
      </div>

      {/* TOP BAND: palette + type */}
      <div style={{
        display: 'grid', gridTemplateColumns: '1.1fr 1fr', gap: 40,
        marginBottom: 36,
      }}>
        {/* Palette */}
        <div>
          <SectionHeader num="01" title="Color Tokens" />
          <SwatchRow group="Background" items={PALETTE.Background} />
          <SwatchRow group="Signal" items={PALETTE.Signal} />
          <SwatchRow group="Text" items={PALETTE.Text} />
          <SwatchRow group="Structure" items={PALETTE.Structure} />
        </div>

        {/* Type */}
        <div>
          <SectionHeader num="02" title="Typography" />
          <div style={{
            padding: '0 0 8px', borderBottom: '1px solid var(--hairline)',
            display: 'flex', gap: 24, marginBottom: 14,
          }}>
            <div>
              <Eyebrow color="var(--text-dim)">DISPLAY / DATA</Eyebrow>
              <div style={{
                fontFamily: 'var(--mono)', fontSize: 22, fontWeight: 600,
                color: 'var(--text)', marginTop: 4,
              }}>IBM Plex Mono</div>
              <div style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--text-faint)', marginTop: 2 }}>
                300 · 400 · 500 · 600 · 700
              </div>
            </div>
            <div>
              <Eyebrow color="var(--text-dim)">UI / BODY</Eyebrow>
              <div style={{
                fontFamily: 'var(--sans)', fontSize: 22, fontWeight: 600,
                color: 'var(--text)', marginTop: 4,
              }}>Geist</div>
              <div style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--text-faint)', marginTop: 2 }}>
                400 · 500 · 600 · 700
              </div>
            </div>
          </div>

          <TypeRow label="DISPLAY" sample={<span>CLAUDE BRIDGE</span>}
            props={{
              style: { fontFamily: 'var(--mono)', fontSize: 40, fontWeight: 700, letterSpacing: '-0.02em', color: 'var(--text)' },
              spec: 'mono / 40 / 700 / -0.02em',
            }} />
          <TypeRow label="H2" sample={<span>Bridge offline</span>}
            props={{
              style: { fontFamily: 'var(--sans)', fontSize: 24, fontWeight: 600, color: 'var(--text)' },
              spec: 'sans / 24 / 600 / -0.01em',
            }} />
          <TypeRow label="DATA·MD" sample={<span style={{color:'var(--blue)'}}>demo:orchestrator</span>}
            props={{
              style: { fontFamily: 'var(--mono)', fontSize: 13, fontWeight: 500 },
              spec: 'mono / 13 / 500 / 0',
            }} />
          <TypeRow label="BODY" sample={<span>One MCP server, two config lines, six tools.</span>}
            props={{
              style: { fontFamily: 'var(--sans)', fontSize: 13, color: 'var(--text-mid)' },
              spec: 'sans / 13 / 400 / 1.55',
            }} />
          <TypeRow label="LABEL·CAPS" sample={<Eyebrow>SENDER · SEQ · TIMESTAMP</Eyebrow>}
            props={{
              style: {},
              spec: 'mono / 10 / 500 / 0.14em / UPPER',
            }} />
          <TypeRow label="CODE" sample={<span style={{fontFamily:'var(--mono)',fontSize:11,color:'var(--text-mid)'}}>
            {'{ "seq": 45, "ts": "14:32:01" }'}
          </span>}
            props={{ style: {}, spec: 'mono / 11 / 400 / 1.65' }} />
        </div>
      </div>

      {/* Spacing & radius */}
      <div style={{ marginBottom: 36 }}>
        <SectionHeader num="03" title="Spacing · Radius · Border" />
        <div style={{
          display: 'grid', gridTemplateColumns: '1.8fr 1fr 1fr', gap: 32,
        }}>
          {/* Spacing */}
          <div>
            <Eyebrow color="var(--text-dim)">SPACING — 4PX BASE</Eyebrow>
            <div style={{
              display: 'flex', gap: 8, marginTop: 12, alignItems: 'flex-end',
            }}>
              {SP.map(n => (
                <div key={n} style={{ textAlign: 'center' }}>
                  <div style={{
                    width: n, height: 48, background: 'var(--blue)',
                    opacity: 0.4 + (n / 200),
                  }} />
                  <div style={{
                    fontFamily: 'var(--mono)', fontSize: 10,
                    color: 'var(--text-dim)', marginTop: 6,
                  }}>{n}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Radius */}
          <div>
            <Eyebrow color="var(--text-dim)">RADIUS</Eyebrow>
            <div style={{
              display: 'flex', gap: 12, marginTop: 12, alignItems: 'flex-end',
            }}>
              {[3, 4, 6, 12].map(r => (
                <div key={r} style={{ textAlign: 'center' }}>
                  <div style={{
                    width: 50, height: 50, background: 'var(--bg-card)',
                    border: '1px solid var(--hairline-strong)', borderRadius: r,
                  }} />
                  <div style={{
                    fontFamily: 'var(--mono)', fontSize: 10,
                    color: 'var(--text-dim)', marginTop: 6,
                  }}>{r}px</div>
                </div>
              ))}
            </div>
          </div>

          {/* Borders */}
          <div>
            <Eyebrow color="var(--text-dim)">HAIRLINES</Eyebrow>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 12 }}>
              <div style={{
                height: 26, background: 'var(--bg-card)',
                border: '1px solid var(--hairline)', borderRadius: 3,
                display: 'flex', alignItems: 'center', padding: '0 10px',
                fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--text-mid)',
              }}>--hairline · default</div>
              <div style={{
                height: 26, background: 'var(--bg-card)',
                border: '1px solid var(--hairline-strong)', borderRadius: 3,
                display: 'flex', alignItems: 'center', padding: '0 10px',
                fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--text-mid)',
              }}>--hairline-strong · hover</div>
              <div style={{
                height: 26, background: 'var(--bg-card)',
                border: '1px solid var(--blue)', borderRadius: 3,
                display: 'flex', alignItems: 'center', padding: '0 10px',
                fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--blue)',
              }}>--blue · focus ring</div>
            </div>
          </div>
        </div>
      </div>

      {/* Components — channel row · message row · button · pill */}
      <div>
        <SectionHeader num="04" title="Component States" />
        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14,
        }}>
          <ComponentState label="CHANNEL ROW">
            <MiniChannel state="default" />
            <MiniChannel state="hover" />
            <MiniChannel state="active" />
            <MiniChannel state="disabled" />
          </ComponentState>

          <ComponentState label="MESSAGE ROW">
            <MiniMessage state="default" />
            <MiniMessage state="hover" />
            <MiniMessage state="selected" />
            <div style={{
              padding: '7px 10px', borderRadius: 3,
              border: '1px dashed var(--hairline-strong)',
              fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--text-faint)',
              textAlign: 'center',
            }}>— empty —</div>
          </ComponentState>

          <ComponentState label="SEND BUTTON">
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              <Btn state="default" />
              <Btn state="hover" />
            </div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              <Btn state="active" />
              <Btn state="disabled" />
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              <Btn variant="ghost" state="default">DOCS</Btn>
              <Btn variant="danger" state="default">DELETE</Btn>
            </div>
          </ComponentState>

          <ComponentState label="SENDER PILLS">
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              <SenderPill name="windows" />
              <SenderPill name="mac" />
            </div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              <SenderPill name="linux" />
              <SenderPill name="watcher" />
            </div>
            <div style={{
              display: 'flex', alignItems: 'center', gap: 6, paddingTop: 4,
              borderTop: '1px solid var(--hairline)',
            }}>
              <Eyebrow size={9}>STATUS DOTS</Eyebrow>
              <LiveDot color="var(--green)" />
              <LiveDot color="var(--amber)" />
              <LiveDot color="var(--blue)" />
              <LiveDot color="var(--red)" />
            </div>
          </ComponentState>
        </div>
      </div>

      {/* Footer note */}
      <div style={{
        marginTop: 32, padding: '14px 18px',
        background: 'var(--bg-deep)',
        border: '1px solid var(--hairline)', borderRadius: 4,
        display: 'flex', alignItems: 'center', gap: 12,
        fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text-dim)',
      }}>
        <Icon name="terminal" size={14} color="var(--green)" />
        <span style={{ color: 'var(--text-mid)' }}>$</span>
        <span>cat tokens.css | head -n 20</span>
        <span style={{ marginLeft: 'auto', color: 'var(--text-faint)' }}>
          all variables exported · CSS · JSON · TS
        </span>
      </div>
    </div>
  );
}

const SectionHeader = ({ num, title }) => (
  <div style={{
    display: 'flex', alignItems: 'baseline', gap: 14,
    paddingBottom: 14, marginBottom: 18,
    borderBottom: '1px solid var(--hairline)',
  }}>
    <span style={{
      fontFamily: 'var(--mono)', fontSize: 11,
      color: 'var(--text-faint)', letterSpacing: '0.14em',
    }}>{num}</span>
    <h3 style={{
      margin: 0, fontFamily: 'var(--sans)', fontSize: 18, fontWeight: 600,
      color: 'var(--text)', letterSpacing: '-0.01em',
    }}>{title}</h3>
    <div style={{ flex: 1, borderTop: '1px dashed var(--hairline)', alignSelf: 'center' }} />
  </div>
);

window.TokensSheet = TokensSheet;
