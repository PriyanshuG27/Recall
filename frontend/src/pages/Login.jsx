import React, { useEffect, useState, useRef, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';

/* ══════════════════════════════════════════════════════════════════════════
   ATRIUM — Login v3 — "Your Memory, Mapped."
   
   Layout: full-bleed split-screen
   • Left  60%: Live animated demo knowledge graph (pure canvas, no deps)
   • Right 40%: Login form — wordmark, tagline, Telegram widget, dev bypass
   ══════════════════════════════════════════════════════════════════════════ */

/* ── Demo graph data ────────────────────────────────────────────────────── */
const DEMO_NODES = [
  { id: 0,  label: 'Research',      color: '#CFA365', r: 22, type: 'hub'  },
  { id: 1,  label: 'Machine Learning', color: '#7C6FD4', r: 8,  type: 'item' },
  { id: 2,  label: 'Voice Note',    color: '#3DAA8A', r: 7,  type: 'item' },
  { id: 3,  label: 'FastAPI docs',  color: '#C9893C', r: 8,  type: 'item' },
  { id: 4,  label: 'Screenshot',    color: '#3D8AAA', r: 7,  type: 'item' },
  { id: 5,  label: 'Meeting Notes', color: '#8A8582', r: 7,  type: 'item' },
  { id: 6,  label: 'Ideas',         color: '#CFA365', r: 18, type: 'hub'  },
  { id: 7,  label: 'Quick thought', color: '#3DAA8A', r: 7,  type: 'item' },
  { id: 8,  label: 'Article link',  color: '#7C6FD4', r: 7,  type: 'item' },
  { id: 9,  label: 'Design ref',    color: '#3D8AAA', r: 7,  type: 'item' },
  { id: 10, label: 'Projects',      color: '#CFA365', r: 16, type: 'hub'  },
  { id: 11, label: 'System design', color: '#C9893C', r: 8,  type: 'item' },
  { id: 12, label: 'Stack trace',   color: '#8A8582', r: 7,  type: 'item' },
];

const DEMO_EDGES = [
  [0,1],[0,2],[0,3],[0,4],[0,5],
  [6,7],[6,8],[6,9],[1,8],
  [10,11],[10,12],[10,3],[5,11],
];

function useDemoGraph(canvasRef) {
  const stateRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // 1. Set canvas resolution to container size immediately before placing nodes
    canvas.width  = canvas.offsetWidth || 800;
    canvas.height = canvas.offsetHeight || 600;

    let W = canvas.width;
    let H = canvas.height;
    let cx = W / 2;
    let cy = H / 2;

    const resize = () => {
      canvas.width  = canvas.offsetWidth;
      canvas.height = canvas.offsetHeight;
      W = canvas.width;
      H = canvas.height;
      cx = W / 2;
      cy = H / 2;
    };
    window.addEventListener('resize', resize);

    // Hub positions (dynamic based on current center)
    const getHubPositions = () => [
      { x: cx - 130, y: cy - 60 },  // 0 Research
      { x: cx + 140, y: cy + 50 },  // 6 Ideas
      { x: cx - 20,  y: cy + 150 }, // 10 Projects
    ];

    const nodes = DEMO_NODES.map((n, i) => {
      let x, y;
      if (n.type === 'hub') {
        const hubPositions = getHubPositions();
        const hi = [0,6,10].indexOf(n.id);
        x = hubPositions[hi]?.x ?? cx;
        y = hubPositions[hi]?.y ?? cy;
      } else {
        // Orbit around connected hub
        x = cx + (Math.random() - 0.5) * W * 0.7;
        y = cy + (Math.random() - 0.5) * H * 0.65;
      }
      return { ...n, x, y, vx: 0, vy: 0, phase: Math.random() * Math.PI * 2 };
    });

    // Simple D3-style force simulation
    function tick() {
      const t = performance.now() * 0.001;
      nodes.forEach(n => {
        // Gentle float
        n.vx += (Math.sin(t * 0.3 + n.phase) * 0.12 - n.vx) * 0.03;
        n.vy += (Math.cos(t * 0.22 + n.phase) * 0.09 - n.vy) * 0.03;
        // Repulsion
        nodes.forEach(m => {
          if (m.id === n.id) return;
          const dx = n.x - m.x;
          const dy = n.y - m.y;
          const d2 = dx*dx + dy*dy + 0.1;
          const f = Math.min(4000 / d2, 2.5);
          n.vx += dx * f * 0.01;
          n.vy += dy * f * 0.01;
        });
        // Center gravity
        n.vx += (cx - n.x) * 0.0008;
        n.vy += (cy - n.y) * 0.0006;
        // Damping
        n.vx *= 0.85;
        n.vy *= 0.85;
        n.x += n.vx;
        n.y += n.vy;
        // Bounds
        n.x = Math.max(n.r + 10, Math.min(W - n.r - 10, n.x));
        n.y = Math.max(n.r + 10, Math.min(H - n.r - 10, n.y));
      });
    }

    let rafId;
    function draw() {
      rafId = requestAnimationFrame(draw);
      tick();

      ctx.fillStyle = '#09080C';
      ctx.fillRect(0, 0, W, H);

      // ── Edges ──
      DEMO_EDGES.forEach(([si, ti]) => {
        const s = nodes[si];
        const t = nodes[ti];
        const isHub = s.type === 'hub' || t.type === 'hub';
        ctx.beginPath();
        ctx.moveTo(s.x, s.y);
        ctx.lineTo(t.x, t.y);
        ctx.strokeStyle = isHub ? 'rgba(207,163,101,0.22)' : 'rgba(138,133,130,0.1)';
        ctx.lineWidth = isHub ? 1.2 : 0.6;
        ctx.stroke();
      });

      // ── Nodes ──
      nodes.forEach(n => {
        const isHubNode = n.type === 'hub';

        if (isHubNode) {
          // Outer glow
          const grd = ctx.createRadialGradient(n.x, n.y, n.r * 0.5, n.x, n.y, n.r * 3);
          grd.addColorStop(0, `${n.color}30`);
          grd.addColorStop(1, `${n.color}00`);
          ctx.beginPath();
          ctx.arc(n.x, n.y, n.r * 3, 0, Math.PI * 2);
          ctx.fillStyle = grd;
          ctx.fill();

          // Rings
          ctx.beginPath();
          ctx.arc(n.x, n.y, n.r + 5, 0, Math.PI * 2);
          ctx.strokeStyle = `${n.color}55`;
          ctx.lineWidth = 1;
          ctx.stroke();
        }

        // Core
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
        ctx.fillStyle = n.color;
        ctx.globalAlpha = isHubNode ? 0.9 : 0.75;
        ctx.fill();
        ctx.globalAlpha = 1;

        // Label
        if (isHubNode) {
          ctx.font = 'bold 10px "JetBrains Mono", monospace';
          ctx.fillStyle = '#F4EFEB';
          ctx.textAlign = 'center';
          ctx.fillText(n.label, n.x, n.y - n.r - 6);
        }
      });
    }

    stateRef.current = { rafId: null };
    draw();
    stateRef.current.rafId = rafId;

    return () => {
      cancelAnimationFrame(rafId);
      window.removeEventListener('resize', resize);
    };
  }, [canvasRef]);
}

/* ══════════════════════════════════════════════════════════════════════════
   Main Component
   ══════════════════════════════════════════════════════════════════════════ */
export default function Login() {
  const { login } = useAuth();
  const [error, setError]             = useState('');
  const [customChatId, setCustomChatId] = useState('');
  const [displayText, setDisplayText] = useState('');
  const [twaDebug, setTwaDebug]       = useState(null); // debug info inside Telegram
  const canvasRef = useRef(null);

  // Animate demo graph
  useDemoGraph(canvasRef);

  // TWA auto-login: runs when Login page mounts inside Telegram
  useEffect(() => {
    const initData = window.Telegram?.WebApp?.initData;
    if (!initData) {
      // Not in Telegram or initData empty
      if (window.Telegram?.WebApp) {
        setTwaDebug({ step: 'initData empty', detail: 'Telegram detected but initData is empty string' });
      }
      return;
    }
    setTwaDebug({ step: 'attempting login', detail: `initData length: ${initData.length}` });
    fetch('/auth/me')
      .then(async res => {
        const body = await res.json().catch(() => ({}));
        if (res.ok) {
          login({ id: body.id, chat_id: body.chat_id, drive_connected: body.drive_connected, google_last_sync: body.google_last_sync });
          setTwaDebug({ step: 'success', detail: `Logged in as user ${body.id}` });
        } else {
          setTwaDebug({ step: 'backend rejected', detail: `${res.status}: ${body.detail || JSON.stringify(body)}` });
        }
      })
      .catch(err => {
        setTwaDebug({ step: 'network error', detail: err.message });
      });
  }, [login]);

  // Typewriter tagline
  const fullText = 'Your second brain, finally visible.';
  useEffect(() => {
    let i = 0;
    const iv = setInterval(() => {
      setDisplayText(fullText.slice(0, i + 1));
      i++;
      if (i >= fullText.length) clearInterval(iv);
    }, 42);
    return () => clearInterval(iv);
  }, []);

  // Telegram widget
  useEffect(() => {
    const script = document.createElement('script');
    script.src = 'https://telegram.org/js/telegram-widget.js';
    script.setAttribute('data-telegram-login', import.meta.env.VITE_BOT_USERNAME || '');
    script.setAttribute('data-size', 'large');
    script.setAttribute('data-radius', '4');
    script.setAttribute('data-auth-url', `${window.location.origin}/auth/telegram`);
    script.async = true;
    const container = document.getElementById('tg-widget');
    if (container) container.appendChild(script);
    return () => { if (container) container.innerHTML = ''; };
  }, []);

  const handleDeveloperBypass = async () => {
    try {
      const targetId = customChatId.trim() || '12345';
      const res = await fetch(`/auth/telegram?id=${targetId}&mock=true`);
      if (res.ok) {
        const check = await fetch('/auth/me');
        if (check.ok) {
          const profile = await check.json();
          login({ id: profile.id, chat_id: profile.chat_id });
        }
      } else {
        setError('Bypass login failed.');
      }
    } catch (err) {
      setError('Connection error.');
    }
  };

  return (
    <div style={{
      width: '100%',
      height: '100dvh',
      display: 'flex',
      background: '#09080C',
      overflow: 'hidden',
      fontFamily: '"Inter", sans-serif',
    }}>
      <style>{`
        @keyframes login-fade-up {
          from { opacity: 0; transform: translateY(16px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        @keyframes pulse-border {
          0%,100% { border-color: rgba(207,163,101,0.12); }
          50%     { border-color: rgba(207,163,101,0.32); }
        }
        .login-step { opacity: 0; animation: login-fade-up 0.6s cubic-bezier(0.16,1,0.3,1) forwards; }
        .bypass-input:focus { border-color: rgba(207,163,101,0.4) !important; outline: none; }
        .bypass-btn:hover { opacity: 0.8; }
        .back-link {
          background: none;
          border: none;
          color: rgba(244,239,235,0.45);
          cursor: pointer;
          font-family: "JetBrains Mono", monospace;
          font-size: 11px;
          display: inline-flex;
          align-items: center;
          gap: 6px;
          padding: 0;
          transition: color 0.2s;
        }
        .back-link:hover {
          color: #CFA365 !important;
        }
      `}</style>

      {/* ── LEFT: Animated knowledge graph ── */}
      <div style={{ flex: '1 1 60%', position: 'relative', overflow: 'hidden' }}>
        {/* Dark gradient overlay on right edge to blend into form */}
        <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(to right, transparent 70%, #09080C 100%)', zIndex: 2, pointerEvents: 'none' }} />
        <div style={{ position: 'absolute', inset: 0, background: 'radial-gradient(ellipse 70% 60% at 40% 50%, rgba(207,163,101,0.04) 0%, transparent 70%)', zIndex: 1, pointerEvents: 'none' }} />
        
        <canvas ref={canvasRef} style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }} />

        {/* Floating label in top-left */}
        <div style={{ position: 'absolute', top: 32, left: 36, zIndex: 5 }}>
          <div style={{ fontFamily: '"JetBrains Mono", monospace', fontSize: 10, color: 'rgba(207,163,101,0.5)', letterSpacing: '0.14em', textTransform: 'uppercase', marginBottom: 6 }}>
            ATRIUM
          </div>
          <div style={{ fontFamily: '"Outfit", sans-serif', fontWeight: 700, fontSize: '1.5rem', color: '#F0EDE8', letterSpacing: '-0.03em' }}>
            Your knowledge,<br />connected.
          </div>
        </div>

        {/* Step indicators bottom-left */}
        <div style={{ position: 'absolute', bottom: 36, left: 36, zIndex: 5, display: 'flex', flexDirection: 'column', gap: '0.625rem' }}>
          {[
            ['01', 'SEND', 'Message your Telegram bot'],
            ['02', 'SAVE', 'Atrium indexes it instantly'],
            ['03', 'MAP',  'Your knowledge graph grows'],
          ].map(([num, title, desc], i) => (
            <div key={num} style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', opacity: 0.7 }}>
              <span style={{ fontFamily: '"JetBrains Mono", monospace', fontSize: 9, color: 'var(--accent-gold)', letterSpacing: '0.1em' }}>{num}</span>
              <span style={{ fontFamily: '"JetBrains Mono", monospace', fontSize: 9, color: '#F0EDE8', letterSpacing: '0.1em' }}>{title}</span>
              <span style={{ fontFamily: '"Inter", sans-serif', fontSize: 11, color: 'rgba(244,239,235,0.4)' }}>{desc}</span>
            </div>
          ))}
        </div>
      </div>

      {/* ── RIGHT: Login form ── */}
      <div style={{
        flex: '0 0 400px',
        minWidth: 340,
        maxWidth: 440,
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        padding: '2rem 3rem 2rem 2.5rem',
        position: 'relative',
        zIndex: 10,
        borderLeft: '1px solid rgba(244,239,235,0.05)',
        background: 'rgba(10,9,14,0.96)',
        backdropFilter: 'blur(20px)',
        overflowY: 'auto',
      }}>

        {/* Back Button */}
        <div className="login-step" style={{ animationDelay: '0.02s', marginBottom: '1.5rem' }}>
          <button 
            className="back-link"
            onClick={() => {
              window.history.pushState({}, '', '/');
              window.dispatchEvent(new PopStateEvent('popstate'));
            }}
          >
            ← Back to Atrium
          </button>
        </div>

        {/* TWA Debug overlay — only visible inside Telegram */}
        {twaDebug && (
          <div style={{ marginBottom: '1rem', padding: '0.6rem 0.75rem', borderRadius: 4, background: 'rgba(41,171,226,0.08)', border: '1px solid rgba(41,171,226,0.2)', fontFamily: '"JetBrains Mono", monospace', fontSize: 10 }}>
            <div style={{ color: '#29ABE2', marginBottom: 2, letterSpacing: '0.08em' }}>TWA · {twaDebug.step}</div>
            <div style={{ color: 'rgba(244,239,235,0.5)' }}>{twaDebug.detail}</div>
          </div>
        )}

        {/* Wordmark */}
        <div className="login-step" style={{ animationDelay: '0.05s', marginBottom: '2.5rem' }}>
          <div style={{ fontFamily: '"JetBrains Mono", monospace', fontSize: 10, color: 'rgba(207,163,101,0.5)', letterSpacing: '0.14em', textTransform: 'uppercase', marginBottom: 10 }}>
            Personal knowledge OS
          </div>
          <h1 style={{ fontFamily: '"Outfit", sans-serif', fontWeight: 800, fontSize: '2.5rem', lineHeight: 1.05, letterSpacing: '-0.05em', color: '#F0EDE8', margin: '0 0 0.5rem 0' }}>
            Atrium.
          </h1>
          <p style={{ fontFamily: '"Inter", sans-serif', fontSize: '0.9375rem', color: 'rgba(244,239,235,0.45)', lineHeight: 1.5, margin: 0, minHeight: '1.5em' }}>
            {displayText}
            <span style={{ opacity: displayText.length < fullText.length ? 1 : 0, borderRight: '1.5px solid rgba(207,163,101,0.7)', marginLeft: 1, animation: 'pulse-border 0.8s steps(1) infinite' }}>&nbsp;</span>
          </p>
        </div>

        {/* Source type capabilities */}
        <div className="login-step" style={{ animationDelay: '0.15s', display: 'flex', flexWrap: 'wrap', gap: '0.4rem', marginBottom: '2.5rem' }}>
          {[
            ['🔗', 'Links',  '#7C6FD4'],
            ['🎙', 'Voice',  '#3DAA8A'],
            ['📄', 'PDFs',   '#C9893C'],
            ['🖼', 'Images', '#3D8AAA'],
            ['📝', 'Text',   '#8A8582'],
          ].map(([icon, label, col]) => (
            <span key={label} style={{
              display: 'inline-flex', alignItems: 'center', gap: '0.3rem',
              padding: '0.3rem 0.65rem', borderRadius: 4,
              border: `1px solid ${col}30`, background: `${col}10`,
              fontSize: '0.75rem', color: col,
              fontFamily: '"JetBrains Mono", monospace', letterSpacing: '0.04em',
            }}>
              {icon} {label}
            </span>
          ))}
        </div>

        {/* Telegram CTA */}
        <div className="login-step" style={{ animationDelay: '0.25s', marginBottom: '1.5rem' }}>
          <div style={{ fontFamily: '"JetBrains Mono", monospace', fontSize: 9, letterSpacing: '0.14em', color: 'rgba(207,163,101,0.5)', textTransform: 'uppercase', marginBottom: 10 }}>
            Continue with
          </div>
          <div style={{ border: '1px solid rgba(207,163,101,0.15)', borderRadius: 8, padding: '1.25rem', animation: 'pulse-border 4s ease-in-out infinite' }}>
            <div id="tg-widget" style={{ minHeight: 48, display: 'flex', alignItems: 'center', justifyContent: 'center' }} />
          </div>

          {/* TWA login hint */}
          <div style={{ marginTop: '0.875rem', padding: '0.75rem', background: 'rgba(41,171,226,0.05)', border: '1px solid rgba(41,171,226,0.12)', borderRadius: 6 }}>
            <div style={{ fontFamily: '"JetBrains Mono", monospace', fontSize: 9, color: '#29ABE2', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: '0.4rem' }}>
              Already using the bot?
            </div>
            <div style={{ fontFamily: '"Inter", sans-serif', fontSize: 11, color: 'rgba(244,239,235,0.45)', lineHeight: 1.5 }}>
              Open <span style={{ color: '#F0EDE8', fontFamily: '"JetBrains Mono", monospace' }}>@AtriumHub_bot</span> in Telegram
              and tap the <span style={{ color: '#F0EDE8' }}>Open Atrium 🧠</span> button to log in instantly — no phone number needed.
            </div>
          </div>

        </div>


        {/* Error */}
        {error && (
          <div style={{ marginBottom: '1rem', padding: '0.5rem 0.75rem', borderRadius: 4, background: 'rgba(180,60,60,0.1)', border: '1px solid rgba(180,60,60,0.25)', color: '#D4756A', fontSize: '0.8rem', fontFamily: '"JetBrains Mono", monospace' }}>
            {error}
          </div>
        )}

        {/* Footnote */}
        <div className="login-step" style={{ animationDelay: '0.3s' }}>
          <p style={{ fontFamily: '"JetBrains Mono", monospace', fontSize: 10, color: 'rgba(244,239,235,0.2)', letterSpacing: '0.1em', textTransform: 'uppercase', margin: '0 0 1.5rem 0' }}>
            no account · no form · 5 seconds
          </p>
        </div>

        {/* Dev bypass */}
        <div className="login-step" style={{ animationDelay: '0.4s', paddingTop: '1.25rem', borderTop: '1px solid rgba(244,239,235,0.05)' }}>
          <label style={{ fontFamily: '"JetBrains Mono", monospace', fontSize: 9, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'rgba(244,239,235,0.2)', display: 'block', marginBottom: 6 }}>
            Dev bypass · Telegram Chat ID
          </label>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <input
              className="bypass-input"
              type="text"
              value={customChatId}
              onChange={e => setCustomChatId(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleDeveloperBypass()}
              placeholder="e.g. 123456789"
              style={{
                flex: 1,
                background: 'rgba(244,239,235,0.03)',
                border: '1px solid rgba(244,239,235,0.08)',
                color: '#F0EDE8',
                padding: '0.45rem 0.7rem',
                borderRadius: 4,
                fontSize: '0.8rem',
                fontFamily: '"JetBrains Mono", monospace',
                transition: 'border-color 0.15s',
              }}
            />
            <button
              className="bypass-btn"
              onClick={handleDeveloperBypass}
              style={{
                padding: '0 1rem',
                background: 'rgba(124,111,212,0.15)',
                border: '1px solid rgba(124,111,212,0.3)',
                borderRadius: 4,
                color: '#9B90D9',
                fontSize: '0.75rem',
                fontFamily: '"JetBrains Mono", monospace',
                cursor: 'pointer',
                whiteSpace: 'nowrap',
                transition: 'opacity 0.15s',
              }}
            >
              ⚡ Go
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
