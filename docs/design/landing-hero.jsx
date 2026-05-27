// Landing / README hero — 1440×1100. Hero (animated diagram) + "What is it".

function LandingNav() {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 12,
      padding: '20px 64px', borderBottom: '1px solid var(--hairline)',
      background: 'var(--bg-deep)',
    }}>
      <BridgeMark size={22} color="var(--blue)" />
      <span style={{
        fontFamily: 'var(--mono)', fontSize: 13, fontWeight: 600,
        letterSpacing: '0.22em', color: 'var(--text)',
      }}>CLAUDE&nbsp;BRIDGE</span>

      <div style={{ display: 'flex', gap: 22, marginLeft: 48 }}>
        {['Overview', 'Quickstart', 'Tools', 'Docs', 'GitHub'].map(s => (
          <a key={s} style={{
            fontFamily: 'var(--sans)', fontSize: 13, fontWeight: 500,
            color: s === 'Overview' ? 'var(--text)' : 'var(--text-mid)',
            cursor: 'pointer',
          }}>{s}</a>
        ))}
      </div>

      <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 12 }}>
        <span style={{
          fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text-dim)',
          display: 'inline-flex', alignItems: 'center', gap: 6,
        }}>
          <Icon name="star" size={12} color="var(--amber)" />
          1,247
        </span>
        <button style={{
          padding: '7px 14px',
          background: 'var(--bg-card)',
          border: '1px solid var(--hairline-strong)',
          borderRadius: 4, color: 'var(--text)',
          fontFamily: 'var(--mono)', fontSize: 11, fontWeight: 500,
          letterSpacing: '0.04em', cursor: 'pointer',
        }}>★ STAR</button>
      </div>
    </div>
  );
}

// Animated bridge diagram — two nodes, particles drifting across
function BridgeDiagram() {
  // Static-rendered React, but animations are pure CSS so it loops without state.
  const W = 880, H = 280;
  const macX = 140, winX = W - 140, midY = H / 2;
  return (
    <div style={{ position: 'relative', width: W, height: H, margin: '0 auto' }}>
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}
           style={{ position: 'absolute', inset: 0 }}>
        <defs>
          <linearGradient id="wire" x1="0" x2="1" y1="0" y2="0">
            <stop offset="0%"  stopColor="#58a6ff" stopOpacity="0"/>
            <stop offset="20%" stopColor="#58a6ff" stopOpacity="0.5"/>
            <stop offset="80%" stopColor="#58a6ff" stopOpacity="0.5"/>
            <stop offset="100%" stopColor="#58a6ff" stopOpacity="0"/>
          </linearGradient>
          <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="3" />
          </filter>
        </defs>

        {/* Grid backdrop */}
        <g opacity="0.15">
          {Array.from({ length: 10 }, (_, i) => (
            <line key={'h'+i} x1="0" x2={W} y1={28 * (i+1)} y2={28 * (i+1)}
                  stroke="#30363d" strokeWidth="0.5" strokeDasharray="2 6" />
          ))}
        </g>

        {/* Wire */}
        <line x1={macX + 60} x2={winX - 60} y1={midY} y2={midY}
              stroke="url(#wire)" strokeWidth="2" />
        {/* Faint dashes along the wire */}
        <line x1={macX + 60} x2={winX - 60} y1={midY} y2={midY}
              stroke="#58a6ff" strokeWidth="1" strokeDasharray="3 8" opacity="0.3" />

        {/* Particles — packets moving across the bridge */}
        {[0, 1.2, 2.4, 3.6, 4.8].map((delay, i) => (
          <circle key={i} cx={macX + 60} cy={midY} r="3" fill="#58a6ff"
                  filter="url(#glow)" opacity="0.9">
            <animate attributeName="cx"
                     from={macX + 60} to={winX - 60} dur="3s"
                     begin={`${delay}s`} repeatCount="indefinite" />
            <animate attributeName="opacity"
                     values="0;1;1;0" keyTimes="0;0.1;0.9;1" dur="3s"
                     begin={`${delay}s`} repeatCount="indefinite" />
          </circle>
        ))}

        {/* Mac node (blue) */}
        <g transform={`translate(${macX} ${midY})`}>
          <rect x="-60" y="-46" width="120" height="92" rx="6"
                fill="#0d1117" stroke="#58a6ff" strokeWidth="1.5" />
          <rect x="-60" y="-46" width="120" height="20" rx="6"
                fill="rgba(88, 166, 255, 0.12)" />
          <circle cx="-50" cy="-36" r="2" fill="#58a6ff" />
          <text x="-40" y="-32" fill="#79b8ff" fontFamily="var(--mono)" fontSize="10" fontWeight="500" letterSpacing="1">MACBOOK · macOS</text>
          <text x="0" y="0" fill="#e6edf3" fontFamily="var(--mono)" fontSize="14" fontWeight="600" textAnchor="middle">mac</text>
          <text x="0" y="20" fill="#8b949e" fontFamily="var(--mono)" fontSize="10" textAnchor="middle">claude-code</text>
          <text x="0" y="36" fill="#6e7681" fontFamily="var(--mono)" fontSize="9" textAnchor="middle">70 tests · 3 failures</text>
        </g>

        {/* Windows node (amber) */}
        <g transform={`translate(${winX} ${midY})`}>
          <rect x="-60" y="-46" width="120" height="92" rx="6"
                fill="#0d1117" stroke="#d97706" strokeWidth="1.5" />
          <rect x="-60" y="-46" width="120" height="20" rx="6"
                fill="rgba(217, 119, 6, 0.12)" />
          <circle cx="-50" cy="-36" r="2" fill="#fbbf24" />
          <text x="-40" y="-32" fill="#fbbf24" fontFamily="var(--mono)" fontSize="10" fontWeight="500" letterSpacing="1">WINDOWS · 11</text>
          <text x="0" y="0" fill="#e6edf3" fontFamily="var(--mono)" fontSize="14" fontWeight="600" textAnchor="middle">windows</text>
          <text x="0" y="20" fill="#8b949e" fontFamily="var(--mono)" fontSize="10" textAnchor="middle">claude-code</text>
          <text x="0" y="36" fill="#6e7681" fontFamily="var(--mono)" fontSize="9" textAnchor="middle">4 workers · 412mb</text>
        </g>

        {/* Bridge label in centre */}
        <g transform={`translate(${W/2} ${midY - 50})`}>
          <rect x="-72" y="-14" width="144" height="28" rx="14"
                fill="#0d1117" stroke="#21262d" strokeWidth="1" />
          <text x="0" y="-1" fill="#8b949e" fontFamily="var(--mono)" fontSize="9"
                textAnchor="middle" letterSpacing="2">SSE BRIDGE :8765</text>
          <text x="0" y="9" fill="#58a6ff" fontFamily="var(--mono)" fontSize="9"
                textAnchor="middle">demo:orchestrator</text>
        </g>

        {/* Latency tag */}
        <g transform={`translate(${W/2} ${midY + 50})`}>
          <text x="0" y="4" fill="#3fb950" fontFamily="var(--mono)" fontSize="10"
                textAnchor="middle">~45ms p95 · 247 msgs · 00:34:12</text>
        </g>
      </svg>
    </div>
  );
}

function LandingHero() {
  return (
    <div style={{
      width: '100%', height: '100%', overflow: 'hidden',
      background: 'var(--bg-base)',
      color: 'var(--text)',
      fontFamily: 'var(--sans)',
      position: 'relative',
    }}>
      {/* Ambient gradient */}
      <div style={{
        position: 'absolute', top: -200, left: '50%', transform: 'translateX(-50%)',
        width: 1200, height: 600, pointerEvents: 'none',
        background: 'radial-gradient(ellipse at center, rgba(88, 166, 255, 0.08) 0%, transparent 60%)',
      }} />

      <LandingNav />

      <div style={{ position: 'relative', padding: '48px 64px 0' }}>
        {/* Hero text */}
        <div style={{ maxWidth: 880, margin: '0 auto 24px', textAlign: 'center' }}>
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: 8,
            padding: '5px 12px',
            border: '1px solid var(--hairline-strong)',
            borderRadius: 100, marginBottom: 22,
            fontFamily: 'var(--mono)', fontSize: 10.5,
            letterSpacing: '0.14em',
          }}>
            <LiveDot color="var(--green)" size={5} />
            <span style={{ color: 'var(--text-mid)' }}>v0.3.1 · MIT · 1,247 STARS</span>
            <span style={{
              color: 'var(--text-faint)', paddingLeft: 8, marginLeft: 4,
              borderLeft: '1px solid var(--hairline)',
            }}>
              <Icon name="arrow" size={10} color="var(--text-faint)" stroke={1.5} style={{ display: 'inline-block', verticalAlign: 'middle', marginRight: 4 }} />
              CHANGELOG
            </span>
          </div>

          <h1 style={{
            margin: '0 0 14px',
            fontFamily: 'var(--mono)', fontSize: 78, fontWeight: 700,
            letterSpacing: '-0.02em', lineHeight: 0.95,
            color: 'var(--text)',
          }}>
            CLAUDE&nbsp;<span style={{ color: 'var(--blue)' }}>BRIDGE</span>
          </h1>
          <p style={{
            margin: '0 auto', maxWidth: 620,
            fontFamily: 'var(--sans)', fontSize: 19,
            color: 'var(--text-mid)', lineHeight: 1.45,
          }}>
            Real-time cross-machine communication for Claude Code agents.
            One MCP server, two config lines, six tools — done.
          </p>

          <div style={{
            display: 'inline-flex', gap: 10, marginTop: 24,
          }}>
            <button style={{
              padding: '11px 20px', background: 'var(--blue)',
              color: '#0d1117', border: 'none', borderRadius: 5,
              fontFamily: 'var(--mono)', fontSize: 12, fontWeight: 600,
              letterSpacing: '0.06em', cursor: 'pointer',
              display: 'inline-flex', alignItems: 'center', gap: 8,
            }}>
              GITHUB
              <Icon name="arrow" size={13} color="#0d1117" stroke={2} />
            </button>
            <button style={{
              padding: '11px 20px', background: 'transparent',
              color: 'var(--text)',
              border: '1px solid var(--hairline-strong)', borderRadius: 5,
              fontFamily: 'var(--mono)', fontSize: 12, fontWeight: 500,
              letterSpacing: '0.06em', cursor: 'pointer',
              display: 'inline-flex', alignItems: 'center', gap: 8,
            }}>
              <Icon name="book" size={13} color="var(--text)" />
              READ THE DOCS
            </button>
            <button style={{
              padding: '11px 16px', background: 'transparent',
              color: 'var(--text-mid)',
              border: '1px solid var(--hairline)', borderRadius: 5,
              fontFamily: 'var(--mono)', fontSize: 12, fontWeight: 500,
              cursor: 'pointer',
              display: 'inline-flex', alignItems: 'center', gap: 8,
            }}>
              <Icon name="copy" size={12} color="var(--text-mid)" />
              <span style={{ color: 'var(--text)' }}>$</span>
              <span>pip install claude-bridge</span>
            </button>
          </div>
        </div>

        {/* Diagram */}
        <div style={{ margin: '8px 0 0' }}>
          <BridgeDiagram />
        </div>
      </div>

      {/* What is it — 3 columns */}
      <div style={{
        padding: '24px 64px 0', borderTop: '1px solid var(--hairline)',
        marginTop: 24,
      }}>
        <div style={{
          maxWidth: 1200, margin: '0 auto',
          display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 24,
        }}>
          <WhatCol
            tag="01 / THE PROBLEM"
            tagColor="var(--red)"
            title="Agents on different machines can't see each other."
            body="Agent Teams coordinates Claude Code sessions on the same box. But your build server is a Linux box at the office and your dev machine is a Mac at home. They have to coordinate through a human — copy-paste, screenshots, Slack."
            sample={['multi-box  →  no shared state', 'windows.local  ⇎  mac.local', '— forced human relay —']}
          />
          <WhatCol
            tag="02 / THE SOLUTION"
            tagColor="var(--amber)"
            title="An MCP relay that any Claude Code can speak."
            body="One Python file. Speaks SSE on :8765. Both machines add it to their MCP config. Six tools (send, receive, channels, ping, clear, status) become available inside each Claude Code session. Zero schema, channel-namespaced."
            sample={['$ python server.py', '○ bind 0.0.0.0:8765', '✓ ready · SSE /sse']}
          />
          <WhatCol
            tag="03 / THE RESULT"
            tagColor="var(--green)"
            title="Two sessions, any machines, real-time conversation."
            body="The agents subscribe to a shared channel and start trading JSON. You watch it happen in this dashboard. They divide tasks, request artifacts, hand off context — without you in the loop. Open it on a second monitor and let them work."
            sample={['mac      → "tests passed, 0 failures"', 'windows  → { handoff: build-42 }', '~45ms p95']}
          />
        </div>
      </div>
    </div>
  );
}

function WhatCol({ tag, tagColor, title, body, sample }) {
  return (
    <div style={{
      padding: 28,
      background: 'var(--bg-card)',
      border: '1px solid var(--hairline)',
      borderRadius: 4,
      position: 'relative',
    }}>
      <div style={{
        position: 'absolute', top: 0, left: 28, height: 2, width: 32,
        background: tagColor,
      }} />
      <Eyebrow color={tagColor} size={10}>{tag}</Eyebrow>
      <h3 style={{
        margin: '14px 0 12px',
        fontFamily: 'var(--sans)', fontSize: 19, fontWeight: 600,
        letterSpacing: '-0.01em', color: 'var(--text)',
        textWrap: 'pretty', lineHeight: 1.25,
      }}>{title}</h3>
      <p style={{
        margin: '0 0 18px',
        fontFamily: 'var(--sans)', fontSize: 13, color: 'var(--text-mid)',
        lineHeight: 1.55, textWrap: 'pretty',
      }}>{body}</p>
      <div style={{
        background: 'var(--bg-deep)',
        border: '1px solid var(--hairline)',
        borderRadius: 3, padding: '10px 12px',
        fontFamily: 'var(--mono)', fontSize: 11, lineHeight: 1.7,
        color: 'var(--text-mid)',
      }}>
        {sample.map((l, i) => (
          <div key={i} style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            <span style={{ color: 'var(--text-faint)' }}>{String(i + 1).padStart(2, '0')} </span>
            {l}
          </div>
        ))}
      </div>
    </div>
  );
}

window.LandingHero = LandingHero;
