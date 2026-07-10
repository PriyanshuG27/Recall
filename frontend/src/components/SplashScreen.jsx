import React, { useEffect, useState } from 'react';

/* ============================================================
   SplashScreen — Cybernetic signal booting splash screen.

   Dot scale -> SVG orbital ring draw -> Title fade-in ->
   Typed verification status string.
   ============================================================ */
export default function SplashScreen() {
  const [typedText, setTypedText] = useState('');

  useEffect(() => {
    const text = 'VERIFYING SIGNAL...';
    let idx = 0;
    
    // Start typing after initial SVG animations begin (600ms delay)
    const delayTimeout = setTimeout(() => {
      const typeInterval = setInterval(() => {
        if (idx < text.length) {
          setTypedText(text.slice(0, idx + 1));
          idx++;
        } else {
          clearInterval(typeInterval);
        }
      }, 50);
      return () => clearInterval(typeInterval);
    }, 600);

    return () => clearTimeout(delayTimeout);
  }, []);

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      height: '100dvh',
      width: '100vw',
      background: '#08070a', // var(--bg-void) fallback
      gap: '1.25rem',
      userSelect: 'none',
      position: 'fixed',
      inset: 0,
      zIndex: 9999,
    }}>
      {/* ── SVG Signal Chamber Animat ── */}
      <svg width="60" height="60" viewBox="0 0 60 60" style={{ overflow: 'visible' }}>
        {/* Core Amber Dot */}
        <circle 
          cx="30" 
          cy="30" 
          r="3" 
          fill="var(--accent-gold, #CFA365)" 
          style={{
            transformOrigin: '30px 30px',
            animation: 'scaleDot 0.4s cubic-bezier(0.34, 1.56, 0.64, 1) forwards',
          }} 
        />
        {/* Outer Orbital Ring */}
        <circle 
          cx="30" 
          cy="30" 
          r="20" 
          fill="none" 
          stroke="var(--accent-gold, #CFA365)" 
          strokeWidth="1" 
          strokeDasharray="126" 
          strokeDashoffset="126" 
          style={{
            transformOrigin: '30px 30px',
            animation: 'drawOrbital 0.8s ease-in-out 0.3s forwards',
            opacity: 0.4,
          }} 
        />
      </svg>

      {/* ── Title & Status Info ── */}
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: '0.35rem',
        animation: 'fadeInText 0.5s ease-out 0.5s forwards',
        opacity: 0,
      }}>
        <h2 style={{
          fontFamily: "'DM Serif Display', Georgia, serif",
          fontSize: '2.5rem',
          fontWeight: 400,
          color: 'var(--accent-gold, #CFA365)',
          margin: 0,
          letterSpacing: '-0.02em',
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
        }}>
          <svg viewBox="0 0 100 100" style={{ width: '32px', height: '32px', fill: 'var(--accent-gold)' }} aria-hidden="true">
            <path d="M 25 85 V 50 A 25 25 0 0 1 75 50 V 85 H 63 V 50 A 13 13 0 0 0 37 50 V 85 Z" />
            <circle cx="50" cy="48" r="3.5" />
            <circle cx="43" cy="62" r="2.2" />
            <circle cx="57" cy="67" r="2.2" />
            <circle cx="47" cy="76" r="1.3" />
          </svg>
          Atrium
        </h2>
        <p style={{
          fontFamily: 'var(--font-mono, monospace)',
          fontSize: 10,
          color: 'var(--text-muted, rgba(255,255,255,0.4))',
          letterSpacing: '0.12em',
          margin: 0,
          minHeight: '14px',
        }}>
          {typedText}
        </p>
      </div>

      <style dangerouslySetInnerHTML={{__html: `
        @keyframes scaleDot {
          from { transform: scale(0); }
          to { transform: scale(1); }
        }
        @keyframes drawOrbital {
          to { stroke-dashoffset: 0; }
        }
        @keyframes fadeInText {
          from {
            opacity: 0;
            transform: translateY(4px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
      `}} />
    </div>
  );
}
