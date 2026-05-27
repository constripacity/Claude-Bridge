// Logo / wordmark sheet — 1200×900

// The icon mark — two nodes connected by an arc bridge.
const Mark = ({ size = 80, color = '#58a6ff', detail = true, bg }) => (
  <svg width={size} height={size} viewBox="0 0 80 80" style={{ display: 'block' }}>
    {bg && <rect width="80" height="80" rx="12" fill={bg} />}
    {/* Arc */}
    <path d="M14 52 Q40 12 66 52" stroke={color} strokeWidth="3"
          fill="none" strokeLinecap="round" />
    {/* Dashed line under */}
    {detail && (
      <path d="M14 52 H66" stroke={color} strokeWidth="1.5"
            strokeDasharray="2 4" opacity="0.35" />
    )}
    {/* Nodes */}
    <circle cx="14" cy="52" r="6" fill={color} />
    <circle cx="66" cy="52" r="6" fill={color} />
    {/* Center pulse */}
    {detail && <circle cx="40" cy="22" r="2.5" fill={color} opacity="0.7" />}
  </svg>
);

// Wordmark, locks the M and the type together
const Wordmark = ({ size = 36, color = 'var(--text)', mark = 'var(--blue)', dense = false }) => (
  <div style={{ display: 'inline-flex', alignItems: 'center', gap: size * 0.42 }}>
    <Mark size={size * 1.05} color={mark} detail={!dense} />
    <span style={{
      fontFamily: 'var(--mono)', fontSize: size, fontWeight: 700,
      letterSpacing: '0.08em', color, lineHeight: 1,
    }}>
      CLAUDE&nbsp;<span style={{ color: mark }}>BRIDGE</span>
    </span>
  </div>
);

function LogoSheet() {
  return (
    <div style={{
      width: '100%', height: '100%',
      background: 'var(--bg-base)', color: 'var(--text)',
      fontFamily: 'var(--sans)', padding: '48px 56px',
      boxSizing: 'border-box', overflow: 'hidden',
    }}>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'baseline', justifyContent: 'space-between',
        marginBottom: 28, paddingBottom: 18,
        borderBottom: '1px solid var(--hairline)',
      }}>
        <div>
          <Eyebrow color="var(--blue)">BRAND · v0.3</Eyebrow>
          <h2 style={{
            margin: '6px 0 4px', fontFamily: 'var(--mono)', fontSize: 28,
            fontWeight: 700, letterSpacing: '-0.01em', color: 'var(--text)',
          }}>Logo & Wordmark</h2>
          <p style={{ margin: 0, color: 'var(--text-mid)', fontSize: 13 }}>
            One mark, two surfaces, three sizes. Two nodes bridged by an arc.
          </p>
        </div>
        <div style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text-faint)', textAlign: 'right' }}>
          <div>FILES · SVG / PNG / FAVICON</div>
          <div style={{ marginTop: 4 }}>WORDMARK / MARK / LOCKUP</div>
        </div>
      </div>

      {/* Primary lockup — dark */}
      <div style={{
        display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16,
        marginBottom: 28,
      }}>
        <div style={{
          background: 'var(--bg-deep)', border: '1px solid var(--hairline)',
          borderRadius: 4, padding: 36, position: 'relative', minHeight: 200,
          display: 'flex', flexDirection: 'column', justifyContent: 'space-between',
        }}>
          <Eyebrow color="var(--text-dim)">PRIMARY · DARK</Eyebrow>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', flex: 1, padding: '24px 0' }}>
            <Wordmark size={36} color="#e6edf3" mark="#58a6ff" />
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--text-faint)' }}>
            <span>BG #0D1117 / TEXT #E6EDF3 / MARK #58A6FF</span>
            <span>SVG · 32 KB</span>
          </div>
        </div>

        <div style={{
          background: '#f0eee9', border: '1px solid var(--hairline)',
          borderRadius: 4, padding: 36, position: 'relative', minHeight: 200,
          display: 'flex', flexDirection: 'column', justifyContent: 'space-between',
        }}>
          <span style={{
            fontFamily: 'var(--mono)', fontSize: 10, fontWeight: 500,
            letterSpacing: '0.14em', textTransform: 'uppercase',
            color: 'rgba(60,50,40,0.6)',
          }}>PRIMARY · LIGHT</span>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', flex: 1, padding: '24px 0' }}>
            <Wordmark size={36} color="#1a1a1a" mark="#1f4d8a" />
          </div>
          <div style={{
            display: 'flex', justifyContent: 'space-between',
            fontFamily: 'var(--mono)', fontSize: 10,
            color: 'rgba(60,50,40,0.5)',
          }}>
            <span>BG #F0EEE9 / TEXT #1A1A1A / MARK #1F4D8A</span>
            <span>SVG · 32 KB</span>
          </div>
        </div>
      </div>

      {/* Construction & favicons */}
      <div style={{
        display: 'grid', gridTemplateColumns: '1.1fr 1fr', gap: 16,
      }}>
        {/* Construction grid */}
        <div style={{
          background: 'var(--bg-card)', border: '1px solid var(--hairline)',
          borderRadius: 4, padding: 24,
        }}>
          <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 16 }}>
            <Eyebrow color="var(--text-dim)">CONSTRUCTION</Eyebrow>
            <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--text-faint)' }}>80×80 GRID</span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 36 }}>
            {/* Construction view */}
            <div style={{ position: 'relative' }}>
              <svg width="220" height="220" viewBox="0 0 80 80" style={{ display: 'block' }}>
                {/* grid */}
                <g opacity="0.25">
                  {Array.from({ length: 9 }).map((_, i) => (
                    <line key={'h' + i} x1="0" x2="80" y1={i*10} y2={i*10}
                          stroke="#30363d" strokeWidth="0.3" />
                  ))}
                  {Array.from({ length: 9 }).map((_, i) => (
                    <line key={'v' + i} x1={i*10} x2={i*10} y1="0" y2="80"
                          stroke="#30363d" strokeWidth="0.3" />
                  ))}
                </g>
                {/* guide circles */}
                <circle cx="14" cy="52" r="6" stroke="#58a6ff" strokeWidth="0.3" fill="none" opacity="0.4" />
                <circle cx="66" cy="52" r="6" stroke="#58a6ff" strokeWidth="0.3" fill="none" opacity="0.4" />
                <path d="M14 52 Q40 12 66 52" stroke="#58a6ff" strokeWidth="0.3" fill="none" opacity="0.4" />
                {/* the mark */}
                <path d="M14 52 Q40 12 66 52" stroke="#58a6ff" strokeWidth="3"
                      fill="none" strokeLinecap="round" />
                <path d="M14 52 H66" stroke="#58a6ff" strokeWidth="1.5"
                      strokeDasharray="2 4" opacity="0.35" />
                <circle cx="14" cy="52" r="6" fill="#58a6ff" />
                <circle cx="66" cy="52" r="6" fill="#58a6ff" />
                <circle cx="40" cy="22" r="2.5" fill="#58a6ff" opacity="0.7" />

                {/* annotations */}
                <text x="14" y="68" textAnchor="middle" fill="#6e7681" fontFamily="var(--mono)" fontSize="3">mac</text>
                <text x="66" y="68" textAnchor="middle" fill="#6e7681" fontFamily="var(--mono)" fontSize="3">windows</text>
                <text x="40" y="9" textAnchor="middle" fill="#6e7681" fontFamily="var(--mono)" fontSize="3">peak +30</text>
              </svg>
            </div>

            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                <ConstructRow label="Node radius" v="6 u" />
                <ConstructRow label="Stroke" v="3 u · round" />
                <ConstructRow label="Arc peak" v="y = 12 (control)" />
                <ConstructRow label="Baseline" v="y = 52" />
                <ConstructRow label="Clear space" v="≥ 1× node diameter" />
                <ConstructRow label="Min size" v="16 px (no detail)" />
              </div>
            </div>
          </div>
        </div>

        {/* Mark variations */}
        <div style={{
          background: 'var(--bg-card)', border: '1px solid var(--hairline)',
          borderRadius: 4, padding: 24,
        }}>
          <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 16 }}>
            <Eyebrow color="var(--text-dim)">FAVICON · AVATAR · BADGE</Eyebrow>
            <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--text-faint)' }}>6 SIZES</span>
          </div>

          <div style={{ display: 'flex', gap: 14, alignItems: 'flex-end', justifyContent: 'space-around', flexWrap: 'wrap' }}>
            <FaviconTile size={64} label="64" bg="#0d1117" fg="#58a6ff" />
            <FaviconTile size={48} label="48" bg="#0d1117" fg="#58a6ff" />
            <FaviconTile size={32} label="32" bg="#0d1117" fg="#58a6ff" />
            <FaviconTile size={24} label="24" bg="#0d1117" fg="#58a6ff" dense />
            <FaviconTile size={16} label="16" bg="#0d1117" fg="#58a6ff" dense />
          </div>

          <div style={{
            marginTop: 18, paddingTop: 14, borderTop: '1px solid var(--hairline)',
            display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap',
          }}>
            <Eyebrow color="var(--text-dim)">INVERTED</Eyebrow>
            <FaviconTile size={32} bg="#e6edf3" fg="#1f4d8a" />
            <FaviconTile size={32} bg="#3fb950" fg="#0d1117" />
            <FaviconTile size={32} bg="#d97706" fg="#0d1117" />

            <span style={{ flex: 1 }} />

            <div style={{
              display: 'inline-flex', alignItems: 'center', gap: 0,
              border: '1px solid var(--hairline-strong)', borderRadius: 3,
              overflow: 'hidden', fontFamily: 'var(--mono)', fontSize: 10,
            }}>
              <span style={{ padding: '4px 8px', background: '#21262d', color: 'var(--text-mid)' }}>BRIDGE</span>
              <span style={{ padding: '4px 8px', background: 'var(--blue)', color: '#0d1117', fontWeight: 600 }}>v0.3.1</span>
            </div>
          </div>
        </div>
      </div>

      {/* DON'Ts */}
      <div style={{
        marginTop: 22, background: 'var(--bg-deep)',
        border: '1px solid var(--hairline)', borderRadius: 4,
        padding: 24,
      }}>
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 16 }}>
          <Eyebrow color="var(--text-dim)">USAGE — DON'T</Eyebrow>
          <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--text-faint)' }}>4 RULES</span>
        </div>
        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12,
        }}>
          <DontTile label="rotate or skew" bad>
            <div style={{ transform: 'rotate(-12deg)' }}>
              <Mark size={48} color="#58a6ff" />
            </div>
          </DontTile>
          <DontTile label="recolor outside palette" bad>
            <Mark size={48} color="#ff4ae0" />
          </DontTile>
          <DontTile label="crowd the clear-space" bad>
            <div style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <Mark size={48} color="#58a6ff" />
              <span style={{ fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--text-mid)', maxWidth: 60 }}>by team</span>
            </div>
          </DontTile>
          <DontTile label="drop the arc, keep dots" bad>
            <svg width="48" height="48" viewBox="0 0 80 80">
              <circle cx="14" cy="52" r="6" fill="#58a6ff" />
              <circle cx="66" cy="52" r="6" fill="#58a6ff" />
              <line x1="14" y1="52" x2="66" y2="52" stroke="#58a6ff" strokeWidth="3" />
            </svg>
          </DontTile>
        </div>
      </div>
    </div>
  );
}

const ConstructRow = ({ label, v }) => (
  <div style={{
    display: 'flex', justifyContent: 'space-between',
    padding: '5px 0', borderBottom: '1px solid var(--hairline)',
    fontFamily: 'var(--mono)', fontSize: 11,
  }}>
    <span style={{ color: 'var(--text-dim)' }}>{label}</span>
    <span style={{ color: 'var(--text)' }}>{v}</span>
  </div>
);

const FaviconTile = ({ size, label, bg, fg, dense }) => (
  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
    <div style={{
      width: size, height: size, background: bg,
      border: '1px solid var(--hairline-strong)',
      borderRadius: Math.max(3, size * 0.08),
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <Mark size={size * 0.74} color={fg} detail={!dense} />
    </div>
    {label && <div style={{
      fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--text-faint)',
    }}>{label}px</div>}
  </div>
);

const DontTile = ({ label, bad, children }) => (
  <div style={{
    background: 'var(--bg-base)', border: '1px solid var(--hairline)',
    borderRadius: 3, padding: 14,
    display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10,
    position: 'relative',
  }}>
    <div style={{
      position: 'absolute', top: 8, right: 8, width: 16, height: 16, borderRadius: '50%',
      background: 'rgba(248,81,73,0.12)', border: '1px solid rgba(248,81,73,0.4)',
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <Icon name="close" size={9} color="var(--red)" stroke={2} />
    </div>
    <div style={{ height: 56, display: 'flex', alignItems: 'center' }}>{children}</div>
    <div style={{
      fontFamily: 'var(--mono)', fontSize: 10.5, color: 'var(--text-mid)',
      textAlign: 'center',
    }}>{label}</div>
  </div>
);

window.LogoSheet = LogoSheet;
