import { useEffect, useRef, useState, useCallback } from 'react';
import Lenis from 'lenis';
import './Landing.css';

const go = (path) => {
  window.history.pushState({}, '', path);
  window.dispatchEvent(new PopStateEvent('popstate'));
};

/* ── Text scramble ──────────────────────────────────────── */
function useScramble(finalText, started, delay = 0) {
  const [display, setDisplay] = useState(finalText);
  const frame = useRef(null);
  useEffect(() => {
    if (!started) return;
    const CHARS = '!<>-_\\/[]{}—=+*^?#';
    setDisplay(finalText.split('').map(ch => ch === ' ' ? ' ' : CHARS[Math.floor(Math.random() * CHARS.length)]).join(''));
    const tid = setTimeout(() => {
      if (frame.current) clearInterval(frame.current);
      let iter = 0;
      frame.current = setInterval(() => {
        setDisplay(finalText.split('').map((ch, i) => {
          if (ch === ' ') return ' ';
          if (i < Math.floor(iter)) return ch;
          return CHARS[Math.floor(Math.random() * CHARS.length)];
        }).join(''));
        iter += 0.35;
        if (iter > finalText.length) { clearInterval(frame.current); setDisplay(finalText); }
      }, 32);
    }, delay);
    return () => { clearTimeout(tid); clearInterval(frame.current); };
  }, [started, finalText, delay]);
  return display;
}

/* ── Animated counter ───────────────────────────────────── */
function useCounter(end, started, duration = 1800) {
  const [val, setVal] = useState(0);
  useEffect(() => {
    if (!started) return;
    let t0 = null;
    const ease = t => 1 - Math.pow(1 - t, 4);
    const raf = requestAnimationFrame(function tick(now) {
      if (!t0) t0 = now;
      const p = Math.min((now - t0) / duration, 1);
      setVal(Math.round(end * ease(p)));
      if (p < 1) requestAnimationFrame(tick); else setVal(end);
    });
    return () => cancelAnimationFrame(raf);
  }, [started, end, duration]);
  return val;
}

/* ── IntersectionObserver hook ──────────────────────────── */
function useInView(threshold = 0.15) {
  const ref = useRef(null);
  const [inView, setInView] = useState(false);
  useEffect(() => {
    const el = ref.current; if (!el) return;
    const obs = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setInView(true); obs.disconnect(); } }, { threshold });
    obs.observe(el);
    return () => obs.disconnect();
  }, [threshold]);
  return [ref, inView];
}

/* ── Magnetic button ────────────────────────────────────── */
function useMagnetic(strength = 0.3) {
  const ref = useRef(null);
  const [off, setOff] = useState({ x: 0, y: 0 });
  useEffect(() => {
    const el = ref.current; if (!el) return;
    const onMove = e => {
      const r = el.getBoundingClientRect();
      const dx = e.clientX - (r.left + r.width / 2), dy = e.clientY - (r.top + r.height / 2);
      const d = Math.hypot(dx, dy);
      if (d < 90) { const pull = 1 - d / 90; setOff({ x: dx * pull * strength, y: dy * pull * strength }); }
      else setOff({ x: 0, y: 0 });
    };
    const onLeave = () => setOff({ x: 0, y: 0 });
    window.addEventListener('mousemove', onMove);
    el.addEventListener('mouseleave', onLeave);
    return () => { window.removeEventListener('mousemove', onMove); el.removeEventListener('mouseleave', onLeave); };
  }, [strength]);
  return { ref, style: { transform: `translate(${off.x}px, ${off.y}px)`, transition: off.x === 0 ? 'transform 0.5s cubic-bezier(0.16,1,0.3,1)' : 'transform 0.08s linear' } };
}

/* ── Stat counter component ─────────────────────────────── */
function StatNum({ end, prefix = '', suffix = '' }) {
  const [ref, inView] = useInView(0.5);
  const val = useCounter(end, inView);
  return <span ref={ref}>{prefix}{val}{suffix}</span>;
}

/* ── Letter-by-letter reveal ────────────────────────────── */
function LetterReveal({ text, baseDelay = 0, stagger = 0.05 }) {
  const [ref, inView] = useInView(0.3);
  return (
    <span ref={ref} aria-label={text}>
      {text.split('').map((ch, i) =>
        ch === ' '
          ? <span key={i} style={{ display: 'inline-block', width: '0.28em' }} aria-hidden="true" />
          : <span key={i} aria-hidden="true" className={`lp-letter ${inView ? 'visible' : ''}`}
              style={{ transitionDelay: `${baseDelay + i * stagger}s` }}>{ch}</span>
      )}
    </span>
  );
}

/* ── BentoCard with 3D tilt + spotlight (outerRef forwarded) */
function BentoCard({ children, outerRef, span2 = false, beam = false }) {
  const cardRef = useRef(null);
  const spotRef = useRef(null);
  const glareRef = useRef(null);

  const setRefs = useCallback(el => {
    cardRef.current = el;
    if (typeof outerRef === 'function') outerRef(el);
  }, [outerRef]);

  const onMouseMove = useCallback(e => {
    const el = cardRef.current; if (!el) return;
    const r = el.getBoundingClientRect();
    const x = e.clientX - r.left;
    const y = e.clientY - r.top;
    const rx = ((y - r.height/2) / r.height) * 8;
    const ry = -((x - r.width/2) / r.width) * 8;
    el.style.transform = `perspective(900px) rotateX(${rx}deg) rotateY(${ry}deg) scale(1.015)`;
    if (spotRef.current) {
      spotRef.current.style.setProperty('--mx', x + 'px');
      spotRef.current.style.setProperty('--my', y + 'px');
    }
    const gx = (x / r.width) * 100;
    const gy = (y / r.height) * 100;
    if (glareRef.current) {
      glareRef.current.style.background = `radial-gradient(circle at ${gx}% ${gy}%, rgba(255, 255, 255, 0.055) 0%, transparent 65%)`;
    }
  }, []);

  const onMouseLeave = useCallback(() => {
    const el = cardRef.current; if (!el) return;
    el.style.transform = 'perspective(900px) rotateX(0deg) rotateY(0deg) scale(1)';
  }, []);

  return (
    <div
      ref={setRefs}
      className={`lp-bento-card ${span2 ? 'span2' : ''} ${beam ? 'beam-card' : ''}`}
      onMouseMove={onMouseMove}
      onMouseLeave={onMouseLeave}
    >
      <div ref={spotRef} className="lp-card-spotlight" />
      <div ref={glareRef} className="lp-card-glare" />
      {children}
    </div>
  );
}

/* ── Step visuals ────────────────────────────────────────── */
function StepVisual({ index }) {
  if (index === 0) return <ChipsVisual />;
  if (index === 1) return <MiniMapCanvas />;
  return <TerminalVisual />;
}

function ChipsVisual() {
  const chips = [
    ['🎙', 'voice note', '#3DAA8A', 0],
    ['📄', 'pdf',        '#C9893C', 0.4],
    ['📷', 'screenshot', '#3D8AAA', 0.2],
    ['🔗', 'link',       '#7C6FD4', 0.6],
    ['📹', 'reel',       '#3DAA8A', 0.1],
    ['📝', 'text note',  '#8A8582', 0.5],
  ];
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, padding: 32, width: '100%' }}>
      {chips.map(([icon, label, color, delay]) => (
        <div key={label} style={{
          display: 'flex', alignItems: 'center', gap: 10,
          background: 'rgba(255,255,255,0.03)',
          border: '1px solid rgba(255,255,255,0.07)',
          borderRadius: 10, padding: '12px 16px',
          fontFamily: '"JetBrains Mono", monospace', fontSize: 12,
          color: 'rgba(240,237,232,0.6)',
          animation: `chipFloat 4s ease-in-out infinite`,
          animationDelay: `${delay}s`,
        }}>
          <div style={{ width: 7, height: 7, borderRadius: '50%', background: color, flexShrink: 0 }} />
          {icon} {label}
        </div>
      ))}
    </div>
  );
}

function TerminalVisual() {
  return (
    <div style={{ padding: '28px 24px', width: '100%', display: 'flex', flexDirection: 'column', gap: 14 }}>
      {[
        { q: 'what did I save about sleep?', a: '3 results ✦ research.pdf, voice-note Jul 4, article Jun 28' },
        { q: 'notes from my system design phase', a: '5 results ✦ concurrency, architecture, api patterns' },
        { q: 'what was that fastapi thing', a: '2 results ✦ voice-note Jun 29, link bookmark Jul 2' },
      ].map(({ q, a }) => (
        <div key={q} style={{ background: 'rgba(255,255,255,0.025)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 10, padding: '12px 16px' }}>
          <div style={{ fontFamily: '"JetBrains Mono",monospace', fontSize: 11, color: 'rgba(240,237,232,0.4)', marginBottom: 7 }}>› {q}</div>
          <div style={{ fontFamily: '"JetBrains Mono",monospace', fontSize: 11, color: '#CFA365' }}>✓ {a}</div>
        </div>
      ))}
    </div>
  );
}

function MiniMapCanvas() {
  const canvasRef = useRef(null);
  useEffect(() => {
    const canvas = canvasRef.current; if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    let raf, t = 0, stars = null;
    const hubs = [
      { x: 0.5, y: 0.35, label: 'focus',   color: '#CFA365' },
      { x: 0.22, y: 0.6, label: 'memory',  color: '#CFA365' },
      { x: 0.76, y: 0.55, label: 'systems', color: '#CFA365' },
      { x: 0.5, y: 0.72, label: 'reading', color: '#CFA365' },
    ];
    const items = [
      { x: 0.36, y: 0.22, hub: 0, color: '#3DAA8A' },
      { x: 0.63, y: 0.2, hub: 0, color: '#7C6FD4' },
      { x: 0.12, y: 0.46, hub: 1, color: '#C9893C' },
      { x: 0.27, y: 0.77, hub: 1, color: '#3D8AAA' },
      { x: 0.69, y: 0.7, hub: 2, color: '#7C6FD4' },
      { x: 0.89, y: 0.42, hub: 2, color: '#3DAA8A' },
      { x: 0.4, y: 0.87, hub: 3, color: '#8A8582' },
      { x: 0.62, y: 0.89, hub: 3, color: '#C9893C' },
    ];
    function draw() {
      raf = requestAnimationFrame(draw); t += 0.015;
      const W = canvas.offsetWidth, H = canvas.offsetHeight;
      if (canvas.width !== W || canvas.height !== H) {
        canvas.width = W; canvas.height = H;
      }
      ctx.clearRect(0, 0, W, H);
      if (!stars) {
        stars = Array.from({ length: 40 }, () => ({
          x: Math.random(), y: Math.random(),
          r: 0.3 + Math.random() * 0.5,
          a: 0.02 + Math.random() * 0.04,
          ph: Math.random() * Math.PI * 2,
          sp: 0.3 + Math.random() * 0.3
        }));
      }
      stars.forEach(s => {
        const a = s.a * (0.5 + 0.5 * Math.sin(t * s.sp + s.ph));
        ctx.beginPath(); ctx.arc(s.x * W, s.y * H, s.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(255,245,220,${a})`; ctx.fill();
      });
      items.forEach(item => {
        const hub = hubs[item.hub];
        const x1 = hub.x * W, y1 = hub.y * H, x2 = item.x * W, y2 = item.y * H;
        const g = ctx.createLinearGradient(x1, y1, x2, y2);
        g.addColorStop(0, 'rgba(207,163,101,0.28)'); g.addColorStop(1, item.color + '25');
        ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2);
        ctx.strokeStyle = g; ctx.lineWidth = 0.8; ctx.stroke();
        const tf = (t * 0.12 + item.x * 3.7) % 1;
        const px = x1 + (x2 - x1) * tf, py = y1 + (y2 - y1) * tf;
        ctx.beginPath(); ctx.arc(px, py, 1.3, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(207,163,101,0.65)'; ctx.fill();
      });
      hubs.forEach((hub, i) => {
        const x = hub.x * W, y = hub.y * H;
        const pulse = 0.5 + 0.5 * Math.sin(t * 0.6 + i * 1.3);
        const haloR = 24 + pulse * 7;
        const g2 = ctx.createRadialGradient(x, y, 0, x, y, haloR);
        g2.addColorStop(0, `rgba(207,163,101,${0.08 + pulse * 0.03})`); g2.addColorStop(1, 'rgba(207,163,101,0)');
        ctx.beginPath(); ctx.arc(x, y, haloR, 0, Math.PI * 2); ctx.fillStyle = g2; ctx.fill();
        ctx.beginPath(); ctx.arc(x, y, 19, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(207,163,101,0.07)'; ctx.lineWidth = 0.7; ctx.setLineDash([3, 5]); ctx.stroke(); ctx.setLineDash([]);
        const r = 8 + pulse * 1.5;
        const g3 = ctx.createRadialGradient(x, y, 0, x, y, r);
        g3.addColorStop(0, '#CFA365EE'); g3.addColorStop(1, '#CFA36566');
        ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fillStyle = g3; ctx.fill();
        ctx.font = '9px "JetBrains Mono",monospace'; ctx.fillStyle = 'rgba(207,163,101,0.6)';
        ctx.textAlign = 'center'; ctx.fillText(hub.label, x, y - r - 5);
      });
      items.forEach(item => {
        ctx.beginPath(); ctx.arc(item.x * W, item.y * H, 4, 0, Math.PI * 2);
        ctx.fillStyle = item.color + 'AA'; ctx.fill();
      });
    }
    draw();
    return () => cancelAnimationFrame(raf);
  }, []);
  return <canvas ref={canvasRef} style={{ width: '100%', height: '100%', borderRadius: 12 }} aria-hidden="true" />;
}

/* ── Bento Card Interactive graphics ────────────────────── */
function BentoCardPrivateGraphic() {
  const [locked, setLocked] = useState(true);
  const [particles, setParticles] = useState([]);
  const timerRef = useRef(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const trigger = (e) => {
    if (!locked) return;
    setLocked(false);
    
    const list = Array.from({ length: 14 }, () => ({
      id: Math.random(),
      val: Math.random() > 0.5 ? '1' : '0',
      x: 0, y: 0,
      vx: (Math.random() - 0.5) * 140,
      vy: (Math.random() - 0.5) * 80 - 20,
      opacity: 1,
    }));
    setParticles(list);

    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      setLocked(true);
      setParticles([]);
    }, 1100);
  };

  useEffect(() => {
    if (particles.length === 0) return;
    let raf, start = performance.now();
    function update(time) {
      const elapsed = (time - start) / 1000;
      setParticles(prev =>
        prev.map(p => ({
          ...p,
          x: p.vx * elapsed,
          y: p.vy * elapsed + 50 * elapsed * elapsed,
          opacity: Math.max(0, 1 - elapsed / 0.9)
        }))
      );
      if (elapsed < 0.9) {
        raf = requestAnimationFrame(update);
      }
    }
    raf = requestAnimationFrame(update);
    return () => cancelAnimationFrame(raf);
  }, [particles.length]);

  return (
    <div 
      onClick={trigger}
      style={{
        position: 'relative',
        width: '100%',
        height: 80,
        marginTop: 16,
        background: 'rgba(0,0,0,0.15)',
        border: '1px solid rgba(255,255,255,0.03)',
        borderRadius: 12,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        cursor: 'pointer',
        overflow: 'hidden'
      }}
    >
      <div style={{
        fontSize: 22,
        transition: 'transform 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275)',
        transform: locked ? 'scale(1)' : 'scale(1.25) rotate(15deg)'
      }}>
        {locked ? '🔒' : '🔓'}
      </div>
      
      <div style={{
        position: 'absolute',
        bottom: 8,
        fontFamily: '"JetBrains Mono", monospace',
        fontSize: 8,
        letterSpacing: '0.08em',
        color: locked ? 'rgba(207,163,101,0.4)' : '#CFA365',
        textTransform: 'uppercase'
      }}>
        {locked ? 'System Secure' : 'Decrypting...'}
      </div>

      {particles.map(p => (
        <span key={p.id} style={{
          position: 'absolute',
          left: `calc(50% + ${p.x}px)`,
          top: `calc(50% + ${p.y}px)`,
          fontFamily: '"JetBrains Mono", monospace',
          fontSize: 10,
          fontWeight: 'bold',
          color: '#CFA365',
          opacity: p.opacity,
          transform: 'translate(-50%, -50%)',
          pointerEvents: 'none'
        }}>
          {p.val}
        </span>
      ))}
    </div>
  );
}

function BentoCardExportGraphic() {
  const [progress, setProgress] = useState(-1);
  const [success, setSuccess] = useState(false);
  const intervalRef = useRef(null);
  const timeoutRef = useRef(null);
  const successTimeoutRef = useRef(null);

  const cleanup = () => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    if (successTimeoutRef.current) clearTimeout(successTimeoutRef.current);
  };

  useEffect(() => {
    return cleanup;
  }, []);

  const startExport = () => {
    if (progress !== -1 || success) return;
    cleanup();
    setProgress(0);
    setSuccess(false);

    let val = 0;
    intervalRef.current = setInterval(() => {
      val += Math.floor(Math.random() * 15) + 8;
      if (val >= 100) {
        val = 100;
        clearInterval(intervalRef.current);
        setProgress(100);
        timeoutRef.current = setTimeout(() => {
          setProgress(-1);
          setSuccess(true);
          successTimeoutRef.current = setTimeout(() => setSuccess(false), 3500);
        }, 300);
      } else {
        setProgress(val);
      }
    }, 120);
  };

  return (
    <div 
      onClick={startExport}
      style={{
        width: '100%',
        marginTop: 16,
        cursor: 'pointer',
        minHeight: 80,
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center'
      }}
    >
      {progress === -1 && !success && (
        <div style={{
          background: 'rgba(255,255,255,0.02)',
          border: '1px solid rgba(255,255,255,0.05)',
          borderRadius: 10,
          padding: '10px',
          textAlign: 'center',
          fontFamily: '"JetBrains Mono", monospace',
          fontSize: 10,
          color: 'rgba(240,237,232,0.45)',
          transition: 'all 0.2s'
        }} className="export-trigger-btn">
          ⚡ Click to backup archive
        </div>
      )}

      {progress !== -1 && (
        <div style={{ background: 'rgba(0,0,0,0.22)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: 10, padding: '10px', animation: 'fadeUp 0.3s ease' }}>
          <div style={{ fontFamily: '"JetBrains Mono", monospace', fontSize: 10, color: '#CFA365', marginBottom: 6 }}>
            $ atrium --export-zip
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ flex: 1, height: 4, background: 'rgba(255,255,255,0.05)', borderRadius: 2, overflow: 'hidden' }}>
              <div style={{ width: `${progress}%`, height: '100%', background: '#CFA365', transition: 'width 0.1s linear' }} />
            </div>
            <span style={{ fontFamily: '"JetBrains Mono", monospace', fontSize: 10, color: 'rgba(240,237,232,0.6)' }}>
              {progress}%
            </span>
          </div>
        </div>
      )}

      {success && (
        <div style={{ background: 'rgba(207,163,101,0.08)', border: '1px solid rgba(207,163,101,0.2)', borderRadius: 10, padding: '10px', color: '#F0EDE8', fontSize: 10, fontFamily: '"JetBrains Mono", monospace', animation: 'fadeUp 0.35s cubic-bezier(0.16,1,0.3,1) both' }}>
          ✓ atrium-backup.zip ready (37 KB)
        </div>
      )}
    </div>
  );
}

function BentoCardAskGraphic() {
  const prompts = [
    { q: 'what did I save about sleep?', a: '✓ Mapped to 3 files. Connected to focus.' },
    { q: 'concurrency rules on windows', a: '✓ Enforce WindowsSelectorEventLoopPolicy.' },
    { q: 'voice notes about neural networks', a: '✓ Found 2 voice notes. Connected to AI.' }
  ];
  const [idx, setIdx] = useState(0);
  const [response, setResponse] = useState(prompts[0].a);
  const [typing, setTyping] = useState(false);
  const timeoutRef = useRef(null);
  const intervalRef = useRef(null);

  const cleanup = () => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    if (intervalRef.current) clearInterval(intervalRef.current);
  };

  useEffect(() => {
    return cleanup;
  }, []);

  const rotatePrompt = () => {
    if (typing) return;
    cleanup();
    setTyping(true);
    const nextIdx = (idx + 1) % prompts.length;
    setIdx(nextIdx);
    setResponse('');
    
    timeoutRef.current = setTimeout(() => {
      const fullText = prompts[nextIdx].a;
      let curr = '';
      let charIdx = 0;
      intervalRef.current = setInterval(() => {
        curr += fullText[charIdx];
        setResponse(curr);
        charIdx++;
        if (charIdx >= fullText.length) {
          clearInterval(intervalRef.current);
          setTyping(false);
        }
      }, 30);
    }, 450);
  };

  return (
    <div style={{ width: '100%', marginTop: 16, cursor: 'pointer' }} onClick={rotatePrompt}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div style={{ display: 'flex', background: 'rgba(0,0,0,0.18)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 8, padding: '6px 10px', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: 10, color: 'rgba(240,237,232,0.7)', fontFamily: '"JetBrains Mono", monospace' }}>
            {prompts[idx].q}
          </span>
          <span style={{ fontSize: 8, color: 'rgba(207,163,101,0.5)', fontFamily: '"JetBrains Mono", monospace', marginLeft: 'auto' }}>
            [Cycle]
          </span>
        </div>
        <div style={{ minHeight: 38, background: 'rgba(255,255,255,0.015)', border: '1px solid rgba(255,255,255,0.03)', borderRadius: 8, padding: '8px 12px', fontFamily: '"JetBrains Mono", monospace', fontSize: 10, color: '#CFA365', display: 'flex', alignItems: 'center' }}>
          {response}
          {typing && <span style={{ background: '#CFA365', width: 2, height: 12, marginLeft: 2, display: 'inline-block', animation: 'blink 0.8s infinite' }} />}
        </div>
      </div>
    </div>
  );
}

function SecurityShowcase() {
  const [activeTab, setTab] = useState(0);

  const tabs = [
    {
      id: 'fernet',
      title: 'Zero-Trust Storage',
      tag: 'Cryptographic Privacy',
      desc: 'All ingested user texts and external tokens are encrypted at rest using Fernet symmetric keys. Your data is ciphered before hitting serverless cloud storage, meaning database hosts see only raw ciphertext.',
      code: `# Client-side encryption key is separate
plaintext = "Highly sensitive memory..."
ciphertext = security.encrypt(plaintext)
# Database receives:
# 'gAAAAABm...'`,
      diagram: (
        <div className="sec-diag">
          <div className="sec-node note">Thought</div>
          <span className="sec-arrow">──►</span>
          <div className="sec-node cipher pulse">Cipher</div>
          <span className="sec-arrow">──►</span>
          <div className="sec-node db">Neon DB (Cipher)</div>
        </div>
      )
    },
    {
      id: 'pii',
      title: 'PII & Secret Scrubbing',
      tag: 'Telemetry Redaction',
      desc: 'System logs, error streams, and telemetry traces are automatically sanitized. Built-in pattern maskers intercept and redact API tokens, passwords, cookies, and personal identifiers (emails, phone numbers) before they hit loggers or Sentry.',
      code: `# Log stream processor matches patterns
raw_log = "failed: user=admin key=sk-live-281a"
clean_log = mask_secrets(raw_log)
# Console output:
# "failed: user=admin key=[REDACTED_SECRET]"`,
      diagram: (
        <div className="sec-diag">
          <div className="sec-node raw">Log Payload</div>
          <span className="sec-arrow">──►</span>
          <div className="sec-node mask pulse">PII Filter</div>
          <span className="sec-arrow">──►</span>
          <div className="sec-node clean">Safe Console</div>
        </div>
      )
    },
    {
      id: 'ssrf',
      title: 'SSRF & DNS-Pinning',
      tag: 'Network Sanitization',
      desc: 'Web scraping links is a major SSRF risk. Atrium pre-resolves domain addresses to verify they point to public, non-private A/AAAA records, and locks the TCP socket directly to the IP to prevent DNS-rebinding exploits.',
      code: `# Block private ranges (127.0.0.1, 10.0.0.0/8, etc.)
addr = dns_resolve("target.com")
if addr.is_private:
    raise SSRFAttackException("Access Denied")
# TCP socket bound directly to validated IP`,
      diagram: (
        <div className="sec-diag">
          <div className="sec-node url">Scraped URL</div>
          <span className="sec-arrow">──►</span>
          <div className="sec-node check pulse">DNS Pinning</div>
          <span className="sec-arrow">──►</span>
          <div className="sec-node target">Safe Host Only</div>
        </div>
      )
    }
  ];

  return (
    <div className="sec-showcase">
      <div className="sec-tabs">
        {tabs.map((tab, i) => (
          <button
            key={tab.id}
            className={`sec-tab-btn ${activeTab === i ? 'active' : ''}`}
            onClick={() => setTab(i)}
          >
            <span className="sec-tab-tag">{tab.tag}</span>
            <span className="sec-tab-title">{tab.title}</span>
          </button>
        ))}
      </div>
      <div className="sec-content">
        <div className="sec-info">
          <h3>{tabs[activeTab].title}</h3>
          <p>{tabs[activeTab].desc}</p>
          {tabs[activeTab].diagram}
        </div>
        <div className="sec-code-box">
          <div className="sec-code-header">
            <span className="sec-dot" />
            <span className="sec-dot" />
            <span className="sec-dot" />
            <span className="sec-lang">python</span>
          </div>
          <pre><code>{tabs[activeTab].code}</code></pre>
        </div>
      </div>
    </div>
  );
}

/* ── Scroll-Driven Text Reveal Component ─────────────────── */
function ScrollRevealText({ text }) {
  const containerRef = useRef(null);
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    const handleScroll = () => {
      const el = containerRef.current; if (!el) return;
      const rect = el.getBoundingClientRect();
      const viewHeight = window.innerHeight;
      
      const start = viewHeight * 0.85;
      const end = viewHeight * 0.25;
      const current = rect.top;
      const ratio = (start - current) / (start - end);
      setProgress(Math.min(1, Math.max(0, ratio)));
    };

    window.addEventListener('scroll', handleScroll, { passive: true });
    handleScroll();
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  const words = text.split(' ');
  return (
    <p ref={containerRef} style={{
      fontSize: 'clamp(18px, 2.5vw, 28px)',
      lineHeight: 1.5,
      color: '#F0EDE8',
      fontFamily: '"DM Serif Display", serif',
      maxWidth: 750,
      margin: '40px auto 0',
      textAlign: 'center',
    }}>
      {words.map((word, i) => {
        const threshold = i / words.length;
        const opacity = progress > threshold ? 1 : Math.max(0.12, (progress - threshold + 0.1) * 10);
        return (
          <span key={i} style={{
            opacity,
            transition: 'opacity 0.25s cubic-bezier(0.16,1,0.3,1)',
            marginRight: '0.28em',
            display: 'inline-block'
          }}>
            {word}
          </span>
        );
      })}
    </p>
  );
}

/* ── Faint Constellation Background Canvas ───────────────── */
function ConstellationBg() {
  const canvasRef = useRef(null);
  useEffect(() => {
    const canvas = canvasRef.current; if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    let raf, width, height;
    
    const particles = Array.from({ length: 45 }, () => ({
      x: Math.random(),
      y: Math.random(),
      vx: (Math.random() - 0.5) * 0.0006,
      vy: (Math.random() - 0.5) * 0.0006,
      r: 0.5 + Math.random() * 1.0,
    }));

    let mx = -1000, my = -1000;
    const onMove = e => {
      const r = canvas.getBoundingClientRect();
      mx = e.clientX - r.left;
      my = e.clientY - r.top;
    };
    const onLeave = () => { mx = -1000; my = -1000; };
    
    window.addEventListener('mousemove', onMove);
    canvas.addEventListener('mouseleave', onLeave);

    function draw() {
      raf = requestAnimationFrame(draw);
      width = canvas.offsetWidth;
      height = canvas.offsetHeight;
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width; canvas.height = height;
      }
      ctx.clearRect(0, 0, width, height);

      particles.forEach(p => {
        p.x += p.vx; p.y += p.vy;
        if (p.x < 0 || p.x > 1) p.vx *= -1;
        if (p.y < 0 || p.y > 1) p.vy *= -1;
        const px = p.x * width, py = p.y * height;
        ctx.beginPath(); ctx.arc(px, py, p.r, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(207, 163, 101, 0.28)'; ctx.fill();
      });

      for (let i = 0; i < particles.length; i++) {
        const p1 = particles[i];
        const x1 = p1.x * width, y1 = p1.y * height;
        for (let j = i + 1; j < particles.length; j++) {
          const p2 = particles[j];
          const x2 = p2.x * width, y2 = p2.y * height;
          const dist = Math.hypot(x2 - x1, y2 - y1);
          if (dist < 100) {
            const alpha = (1 - dist / 100) * 0.12;
            ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2);
            ctx.strokeStyle = `rgba(207, 163, 101, ${alpha})`;
            ctx.lineWidth = 0.6; ctx.stroke();
          }
        }
        if (mx > 0) {
          const dist = Math.hypot(mx - x1, my - y1);
          if (dist < 140) {
            const alpha = (1 - dist / 140) * 0.15;
            ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(mx, my);
            ctx.strokeStyle = `rgba(207, 163, 101, ${alpha})`;
            ctx.lineWidth = 0.7; ctx.stroke();
          }
        }
      }
    }
    draw();
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('mousemove', onMove);
    };
  }, []);

  return <canvas ref={canvasRef} style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none', zIndex: 0 }} aria-hidden="true" />;
}

/* ══════════════════════════════════════════════════════════
   MAIN PAGE
══════════════════════════════════════════════════════════ */
export default function Landing() {
  const [navSolid, setNavSolid] = useState(false);
  useEffect(() => {
    const fn = () => setNavSolid(window.scrollY > 40);
    window.addEventListener('scroll', fn, { passive: true });

    const lenis = new Lenis({
      duration: 1.15,
      easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
      smoothWheel: true,
    });

    let rafId;
    function raf(time) {
      lenis.raf(time);
      rafId = requestAnimationFrame(raf);
    }
    rafId = requestAnimationFrame(raf);

    return () => {
      window.removeEventListener('scroll', fn);
      lenis.destroy();
      cancelAnimationFrame(rafId);
    };
  }, []);

  const heroRef = useRef(null);



  /* Scramble headline (just "Atrium" decodes first) */
  const scrambled = useScramble('Atrium', true, 200);

  /* Pinned scroll step tracker (robust window-center proximity logic) */
  const [activeStep, setActiveStep] = useState(0);
  const [mobileStep, setMobileStep] = useState(0);
  const pinBlockRefs = useRef([]);
  useEffect(() => {
    const handleScroll = () => {
      const centerY = window.innerHeight / 2;
      let minDistance = Infinity;
      let activeIdx = 0;
      
      pinBlockRefs.current.forEach((el, i) => {
        if (!el) return;
        const rect = el.getBoundingClientRect();
        const blockCenter = rect.top + rect.height / 2;
        const dist = Math.abs(blockCenter - centerY);
        if (dist < minDistance) {
          minDistance = dist;
          activeIdx = i;
        }
      });
      
      setActiveStep(activeIdx);
      
      // Toggle active class on copy block
      pinBlockRefs.current.forEach((el, i) => {
        if (!el) return;
        if (i === activeIdx) el.classList.add('active');
        else el.classList.remove('active');
      });
    };

    window.addEventListener('scroll', handleScroll, { passive: true });
    // Run once on load
    const tid = setTimeout(handleScroll, 120);
    return () => {
      window.removeEventListener('scroll', handleScroll);
      clearTimeout(tid);
    };
  }, []);

  /* Bento grid cards stagger reveal */
  const bentoCardRefs = useRef([]);
  useEffect(() => {
    const tid = setTimeout(() => {
      bentoCardRefs.current.forEach((el, i) => {
        if (!el) return;
        const obs = new IntersectionObserver(([entry]) => {
          if (entry.isIntersecting) {
            setTimeout(() => {
              el.classList.add('visible');
              el.style.transition = `opacity 0.6s ease ${i * 0.1}s, transform 0.65s cubic-bezier(0.16,1,0.3,1) ${i * 0.1}s, border-color 0.3s`;
            }, 50);
            obs.disconnect();
          }
        }, { threshold: 0.05, rootMargin: '0px 0px -30px 0px' });
        obs.observe(el);
      });
    }, 300);
    return () => clearTimeout(tid);
  }, []);

  /* Trust items reveal */
  const trustRefs = useRef([]);
  useEffect(() => {
    const obs = trustRefs.current.map((el, i) => {
      if (!el) return null;
      const o = new IntersectionObserver(([entry]) => {
        if (entry.isIntersecting) { setTimeout(() => el.classList.add('visible'), i * 130); o.disconnect(); }
      }, { threshold: 0.2 });
      o.observe(el);
      return o;
    });
    return () => obs.forEach(o => o?.disconnect());
  }, []);

  const [ulRef, ulVis] = useInView(0.4);
  const magNav = useMagnetic(0.28);
  const magHeroPrimary = useMagnetic(0.28);
  const magHeroSecondary = useMagnetic(0.28);
  const magFinal = useMagnetic(0.28);

  const FEATURES = [
    {
      num: '01 — Send',
      title: <>Forward it.<br /><em>That's all.</em></>,
      desc: 'Send anything to Atrium through Telegram. Voice memos from your commute. PDFs you meant to read. Screenshots, reels, links, notes — anything.',
    },
    {
      num: '02 — Connect',
      title: <>Ideas find<br /><em>each other.</em></>,
      desc: 'Atrium reads everything you save and silently builds connections. The voice note from Tuesday links to the article from last month. Without you doing anything.',
    },
    {
      num: '03 — Ask',
      title: <>Ask anything.<br /><em>It remembers.</em></>,
      desc: 'Search across everything you\'ve ever saved. Ask in plain language — "what did I save about sleep?" — and get exactly what you meant.',
    },
  ];

  const BENTO = [
    { icon: '🗺', title: 'Zero friction capture', desc: 'No new apps to install. No friction. Forward files, voice notes, screenshots, and links directly to Atrium on Telegram. Mapped instantly.', span2: true, beam: true },
    { icon: '🔐', title: 'Private by design',    desc: 'Fernet-encrypted at rest. Your data is never readable by anyone but you.' },
    { icon: '⚡', title: 'Export anytime',        desc: 'Open format. No lock-in. Export your entire knowledge archive as Markdown or JSON anytime.' },
    { icon: '🎙', title: 'Voice → knowledge',    desc: 'Send a voice note. Get back a transcription, summary, and connected ideas.' },
    { icon: '🤖', title: 'Ask your archive',     desc: 'AI that knows your context. Ask in plain English. Get exactly what you saved.' },
  ];

  return (
    <div className="lp">
      <div id="lp-progress" aria-hidden="true" />

      {/* NAV */}
      <nav className={`lp-nav ${navSolid ? 'solid' : ''}`}>
        <div className="lp-logo" style={{ display: 'flex', alignItems: 'center', gap: '8px', fontFamily: "'DM Serif Display', Georgia, serif", fontSize: '1.25rem', fontWeight: 400, color: 'var(--text-signal, #F4EFEB)' }}>
          <svg viewBox="0 0 100 100" style={{ width: '20px', height: '20px', fill: 'var(--accent-gold, #CFA365)' }} aria-hidden="true">
            <path d="M 25 85 V 50 A 25 25 0 0 1 75 50 V 85 H 63 V 50 A 13 13 0 0 0 37 50 V 85 Z" />
            <circle cx="50" cy="48" r="3.5" />
            <circle cx="43" cy="62" r="2.2" />
            <circle cx="57" cy="67" r="2.2" />
            <circle cx="47" cy="76" r="1.3" />
          </svg>
          Atrium
        </div>
        <div className="lp-nav-r">
          <button className="lp-nav-link" onClick={() => go('/login')}>Sign in</button>
          <div ref={magNav.ref} style={magNav.style}>
            <button className="lp-nav-cta" onClick={() => go('/login')}>Get started</button>
          </div>
        </div>
      </nav>

      {/* HERO */}
      <section className="lp-hero" ref={heroRef}>
        <div className="lp-hero-mesh" aria-hidden="true" />
        <ConstellationBg />

        <div className="lp-hero-content">
          <div className="lp-badge">
            <div className="lp-badge-dot" />
            Now in private beta
          </div>

          {/* Headline Scramble */}
          <h1 className="lp-h1" aria-label="Atrium">
            <em>{scrambled}</em>
          </h1>

          {/* Subtitle word-by-word reveal */}
          <div className="lp-hero-sub" aria-label="Your second brain. Finally alive.">
            {'Your second brain.'.split(' ').map((word, i) => (
              <span key={i} className="lp-word-wrap">
                <span className="lp-word-inner" style={{ animationDelay: `${1.0 + i * 0.15}s` }}>{word}</span>
              </span>
            ))}
            <span style={{ display: 'inline-block', width: '0.28em' }} />
            {'Finally alive.'.split(' ').map((word, i) => (
              <span key={i} className="lp-word-wrap">
                <span className="lp-word-inner" style={{ animationDelay: `${2.0 + i * 0.15}s`, color: '#CFA365', fontStyle: 'italic' }}>{word}</span>
              </span>
            ))}
          </div>

          <p className="lp-subhead">
            Send anything to Telegram. Atrium reads it, extracts the meaning,
            and quietly connects it to everything you've ever saved.
          </p>

          <div className="lp-cta-row">
            <div ref={magHeroPrimary.ref} style={magHeroPrimary.style}>
              <button className="lp-btn-primary" onClick={() => go('/login')}>
                <span>Enter Atrium →</span>
                <div className="lp-btn-blobs">
                  <div className="lp-btn-blob" />
                  <div className="lp-btn-blob" />
                  <div className="lp-btn-blob" />
                </div>
              </button>
            </div>
            <div ref={magHeroSecondary.ref} style={magHeroSecondary.style}>
              <button className="lp-btn-ghost" onClick={() => go('/login')}>Sign in</button>
            </div>
          </div>
        </div>

        {/* Hero image — clip-path reveal */}
        <div className="lp-hero-img-wrap">
          <img src="/atrium_map_hero.webp" alt="Atrium Knowledge Constellation" className="lp-hero-img" loading="eager" />
        </div>
      </section>

      {/* STATS */}
      <div className="lp-stats">
        <div className="lp-stats-label">By the numbers</div>
        <div className="lp-stats-row">
          <div className="lp-stat">
            <div className="lp-stat-num"><StatNum end={158} /></div>
            <div className="lp-stat-lbl">signals saved</div>
          </div>
          <div className="lp-stat-div" />
          <div className="lp-stat">
            <div className="lp-stat-num">{'< 2s'}</div>
            <div className="lp-stat-lbl">to process any file</div>
          </div>
          <div className="lp-stat-div" />
          <div className="lp-stat">
            <div className="lp-stat-num"><StatNum end={100} suffix="%" /></div>
            <div className="lp-stat-lbl">encrypted at rest</div>
          </div>
          <div className="lp-stat-div" />
          <div className="lp-stat">
            <div className="lp-stat-num"><StatNum end={0} /></div>
            <div className="lp-stat-lbl">manual tags needed</div>
          </div>
        </div>
      </div>

      {/* MARQUEE */}
      <div className="lp-marquee" aria-hidden="true">
        <div className="lp-marquee-track">
          {[...Array(2)].flatMap((_, j) =>
            ['Voice notes','PDFs','Screenshots','Links','Reels','Ideas','Articles','Research','Bookmarks','Thoughts'].map((w, i) => (
              <div className="lp-marquee-item" key={`${w}-${j}-${i}`}>{w} <span>✦</span></div>
            ))
          )}
        </div>
      </div>

      {/* HOW IT WORKS */}
      <section style={{ background: 'linear-gradient(to bottom, #080B14, #06080F)' }}>
        {/* Desktop version */}
        <div className="lp-steps-container lp-desktop-steps">
          <div className="lp-section-label" style={{ marginBottom: 20 }}>How it works</div>
          {FEATURES.map((f, i) => (
            <div key={i} className="lp-step-row" ref={el => pinBlockRefs.current[i] = el}>
              <div className="lp-step-visual-col">
                <div className="lp-step-visual-box">
                  <StepVisual index={i} />
                </div>
              </div>
              <div className="lp-step-text-col">
                <div className="lp-pin-num">{f.num}</div>
                <h2 className="lp-pin-title">{f.title}</h2>
                <p className="lp-pin-desc">{f.desc}</p>
              </div>
            </div>
          ))}
        </div>

        {/* Mobile version */}
        <div className="lp-steps-container lp-mobile-steps">
          <div className="lp-section-label" style={{ marginBottom: 10 }}>How it works</div>
          
          <div className="lp-mobile-tabs">
            {FEATURES.map((f, i) => (
              <button
                key={i}
                className={`lp-mobile-tab-btn ${mobileStep === i ? 'active' : ''}`}
                onClick={() => setMobileStep(i)}
              >
                {f.num.split(' — ')[1]}
              </button>
            ))}
          </div>

          <div className="lp-mobile-step-card">
            <div className="lp-step-visual-box">
              <StepVisual index={mobileStep} />
            </div>
            <div className="lp-mobile-step-text">
              <div className="lp-pin-num">{FEATURES[mobileStep].num}</div>
              <h2 className="lp-pin-title">{FEATURES[mobileStep].title}</h2>
              <p className="lp-pin-desc">{FEATURES[mobileStep].desc}</p>
            </div>
          </div>
        </div>
      </section>

      {/* BENTO */}
      <section className="lp-bento">
        <div className="lp-section-label">Everything included</div>
        <div className="lp-bento-grid">
          {BENTO.map((card, i) => (
            <BentoCard key={i} outerRef={el => { bentoCardRefs.current[i] = el; }} span2={card.span2} beam={card.beam}>
              <div className="lp-card-icon">{card.icon}</div>
              <div className="lp-card-title">{card.title}</div>
              <div className="lp-card-desc">{card.desc}</div>
              
              {card.beam && (
                <div className="lp-bento-chat-box">
                  <div className="lp-chat-msg sent">🎙 voice-note.mp3</div>
                  <div className="lp-chat-msg reply">✓ Transcribed. Connected to <strong>focus</strong> and <strong>sleep</strong></div>
                  <div className="lp-chat-msg sent">🔗 neuro.org/dopamine</div>
                  <div className="lp-chat-msg reply">✓ Saved. Connected to <strong>motivation</strong></div>
                </div>
              )}

              {i === 1 && <BentoCardPrivateGraphic />}
              {i === 2 && <BentoCardExportGraphic />}
              {i === 4 && <BentoCardAskGraphic />}
            </BentoCard>
          ))}
        </div>
      </section>

      {/* TRUST */}
      <section className="lp-trust">
        <h2 className="lp-trust-h">
          Built for people who think{' '}
          <span ref={ulRef} className={`lp-underline-anim ${ulVis ? 'visible' : ''}`}>in private.</span>
        </h2>
        <ScrollRevealText text="Your knowledge should belong to you. Atrium encrypts every signal with Fernet at rest, ensures your data is never used for third-party training, and gives you full control to export everything at any moment. Quiet, safe, and open." />
      </section>

      {/* SECURITY SHOWCASE */}
      <section className="lp-security">
        <div className="lp-section-label">Security Architecture</div>
        <SecurityShowcase />
      </section>

      {/* FINAL CTA */}
      <section className="lp-final">
        <div className="lp-final-bg" aria-hidden="true" />
        <h2 className="lp-final-h">
          <LetterReveal text="Enter Atrium" baseDelay={0.1} stagger={0.055} />
        </h2>
        <p className="lp-final-sub">Your thinking deserves a home.</p>
        <div className="lp-final-cta">
          <div ref={magFinal.ref} style={magFinal.style}>
            <button className="lp-btn-primary" onClick={() => go('/login')} style={{ fontSize: 15, padding: '15px 36px' }}>
              <span>Get started — it's free →</span>
              <div className="lp-btn-blobs">
                <div className="lp-btn-blob" />
                <div className="lp-btn-blob" />
                <div className="lp-btn-blob" />
              </div>
            </button>
          </div>
          <button className="lp-btn-ghost" onClick={() => go('/login')}>Already have an account? Sign in</button>
        </div>
      </section>

      {/* FOOTER */}
      <footer className="lp-footer">
        <span>✦ ATRIUM</span>
        <span>© 2026</span>
        <span>Built with intent.</span>
      </footer>

      {/* Liquid Gooey SVG filter definition */}
      <svg style={{ position: 'absolute', width: 0, height: 0 }} aria-hidden="true">
        <defs>
          <filter id="lp-goo">
            <feGaussianBlur in="SourceGraphic" stdDeviation="6" result="blur" />
            <feColorMatrix in="blur" mode="matrix" values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 19 -9" result="goo" />
            <feComposite in="SourceGraphic" in2="goo" operator="atop" />
          </filter>
        </defs>
      </svg>
    </div>
  );
}
