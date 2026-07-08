import React, { useState, useEffect, useCallback } from 'react';
import AudioEngine from '../utils/AudioEngine';

// Circular Progress Gauge for Metrics (Redesigned as HUD Ring)
function CircularProgress({ value, threshold, max }) {
  const radius = 18;
  const circumference = 2 * Math.PI * radius;
  const percentage = Math.min(100, Math.max(5, (value / max) * 100));
  const strokeDashoffset = circumference - (percentage / 100) * circumference;
  const isHigh = value >= threshold;
  const strokeColor = isHigh ? 'var(--accent-gold)' : 'rgba(255, 255, 255, 0.25)';

  return (
    <div style={{ position: 'relative', width: '56px', height: '56px', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
      {/* Background ticks and indicators */}
      <svg width="56" height="56" viewBox="0 0 48 48" style={{ position: 'absolute', transform: 'rotate(-90deg)' }}>
        <circle cx="24" cy="24" r="22" fill="none" stroke="rgba(255, 255, 255, 0.01)" strokeWidth="3" />
        <circle cx="24" cy="24" r={radius} fill="none" stroke="rgba(255, 255, 255, 0.05)" strokeWidth="1.5" strokeDasharray="3, 3" />
        {/* Active arc */}
        <circle 
          cx="24" 
          cy="24" 
          r={radius} 
          fill="none" 
          stroke={strokeColor} 
          strokeWidth="2.5" 
          strokeDasharray={circumference}
          strokeDashoffset={strokeDashoffset}
          strokeLinecap="round"
          style={{ 
            transition: 'stroke-dashoffset 1.5s cubic-bezier(0.16, 1, 0.3, 1)', 
            filter: isHigh ? 'drop-shadow(0 0 4px rgba(207,163,101,0.4))' : 'none' 
          }}
        />
      </svg>
      {/* Center numerical reading */}
      <span style={{ fontSize: '0.72rem', fontFamily: 'var(--font-mono)', fontWeight: 600, color: isHigh ? '#ffffff' : 'var(--text-muted)' }}>
        {value.toFixed(1)}
      </span>
    </div>
  );
}

// Interactive HUD Cognitive Avatar Constellation
// Interactive Cyber-HUD Cognitive Avatar
// Interactive Cyber-HUD Cognitive Avatar
// Interactive Cybernetic Character Face Generator
function CognitiveAvatar({ signature, size = 120 }) {
  const [tilt, setTilt] = useState({ x: 0, y: 0 });
  const containerRef = React.useRef(null);

  const handleMouseMove = (e) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left - rect.width / 2;
    const y = e.clientY - rect.top - rect.height / 2;
    setTilt({
      x: Math.max(-15, Math.min(15, -y * 0.2)),
      y: Math.max(-15, Math.min(15, x * 0.2))
    });
  };

  const handleMouseLeave = () => {
    setTilt({ x: 0, y: 0 });
  };

  const sig = signature || 'BLVN';
  const isB = sig[0] === 'B';
  const isL = sig[1] === 'L';
  const isV = sig[2] === 'V';
  const isN = sig[3] === 'N';

  // Theme colors
  const primaryGlow = isN ? '#ffb95e' : '#06b6d4';
  const accentColor = isN ? '#d946ef' : '#10b981';
  const baseColor = '#1f1a24';
  const faceColor = '#120f17';

  return (
    <div
      ref={containerRef}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      style={{
        width: `${size}px`,
        height: `${size}px`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        cursor: 'crosshair',
        perspective: '500px',
        transformStyle: 'preserve-3d',
        transition: 'all 0.3s ease'
      }}
    >
      <div
        style={{
          width: '100%',
          height: '100%',
          transform: `rotateX(${tilt.x}deg) rotateY(${tilt.y}deg)`,
          transition: tilt.x === 0 ? 'transform 0.6s cubic-bezier(0.16, 1, 0.3, 1)' : 'transform 0.1s ease-out',
          transformStyle: 'preserve-3d',
          position: 'relative'
        }}
      >
        <svg
          width="100%"
          height="100%"
          viewBox="0 0 120 120"
          style={{ overflow: 'visible', position: 'absolute', top: 0, left: 0 }}
        >
          <defs>
            {/* Gradients */}
            <linearGradient id="glowGrad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor={primaryGlow} stopOpacity="0.3" />
              <stop offset="100%" stopColor={accentColor} stopOpacity="0" />
            </linearGradient>
            <linearGradient id="visorGrad" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor={primaryGlow} />
              <stop offset="50%" stopColor={accentColor} />
              <stop offset="100%" stopColor={primaryGlow} />
            </linearGradient>
            <linearGradient id="faceGrad" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="#1e1826" />
              <stop offset="100%" stopColor="#0a070d" />
            </linearGradient>
            <filter id="neonGlow" x="-20%" y="-20%" width="140%" height="140%">
              <feGaussianBlur stdDeviation="3.5" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>

          {/* Ambient Background Aura */}
          <circle cx="60" cy="60" r="54" fill="url(#glowGrad)" style={{ transform: 'translateZ(-15px)' }} />

          {/* HUD Tech Frame (Gyroscope Ticks) */}
          <g stroke="rgba(255, 255, 255, 0.03)" strokeWidth="0.5" style={{ transform: 'translateZ(-10px)' }}>
            <circle cx="60" cy="60" r="50" fill="none" />
            <circle cx="60" cy="60" r="53" fill="none" strokeDasharray="2, 8" />
            <line x1="60" y1="2" x2="60" y2="118" />
            <line x1="2" y1="60" x2="118" y2="60" />
          </g>

          {/* THE CHARACTER BUST */}
          <g style={{ transform: 'translateZ(10px)' }}>
            {/* Cybernetic Collar / Shoulders */}
            <path
              d="M 35 110 C 35 98, 42 90, 60 90 C 78 90, 85 98, 85 110 Z"
              fill="#181320"
              stroke={primaryGlow}
              strokeWidth="0.5"
              strokeOpacity="0.2"
            />
            {/* Collar Inner Light */}
            <path
              d="M 42 98 C 48 93, 72 93, 78 98"
              fill="none"
              stroke={accentColor}
              strokeWidth="1.5"
              filter="url(#neonGlow)"
              opacity="0.75"
            />

            {/* Neck */}
            <path
              d="M 52 82 L 52 92 L 68 92 L 68 82 Z"
              fill="#0e0a14"
            />

            {/* Head Base Silhouette */}
            <path
              d="M 40 46 C 40 32, 50 22, 60 22 C 70 22, 80 32, 80 46 C 80 62, 75 78, 60 84 C 45 78, 40 62, 40 46 Z"
              fill="url(#faceGrad)"
              stroke="rgba(255, 255, 255, 0.08)"
              strokeWidth="0.75"
            />

            {/* Neck Cyber-Decals / Spine (Linker vs Independent) */}
            {isL ? (
              // Linker: Glowing cybernetic nodes on neck
              <g stroke={accentColor} strokeWidth="1" filter="url(#neonGlow)" opacity="0.8">
                <line x1="60" y1="84" x2="60" y2="94" />
                <circle cx="60" cy="89" r="1.5" fill={accentColor} />
              </g>
            ) : (
              // Independent: Solid mechanical neck bracket
              <path
                d="M 55 86 L 65 86"
                stroke="rgba(255, 255, 255, 0.2)"
                strokeWidth="2"
              />
            )}

            {/* Face Cybernetic Lines (Linker vs Independent) */}
            {isL && (
              <g stroke={accentColor} strokeWidth="0.75" fill="none" opacity="0.6" filter="url(#neonGlow)">
                {/* Cheek and chin connector lines */}
                <path d="M 45 60 L 52 72 L 60 76" />
                <path d="M 75 60 L 68 72 L 60 76" />
                <circle cx="52" cy="72" r="1" fill={accentColor} />
                <circle cx="68" cy="72" r="1" fill={accentColor} />
              </g>
            )}

            {/* EYEWEAR / ACCESSORY (Breadth vs Focus) */}
            {isB ? (
              // Broad: Wrap-around Visor (Scanning/Wide)
              <g style={{ transform: 'translateZ(18px)' }}>
                <path
                  d="M 38 42 C 45 39, 75 39, 82 42 L 82 49 C 75 52, 45 52, 38 49 Z"
                  fill="url(#visorGrad)"
                  filter="url(#neonGlow)"
                  style={{ animation: 'avatarPulse 3s ease-in-out infinite' }}
                />
                {/* Visor Glare line */}
                <path
                  d="M 40 45 L 80 45"
                  stroke="#ffffff"
                  strokeWidth="0.75"
                  strokeOpacity="0.8"
                />
              </g>
            ) : (
              // Focus: Precision monocle
              <g style={{ transform: 'translateZ(18px)' }}>
                <circle
                  cx="50"
                  cy="45"
                  r="7"
                  fill="none"
                  stroke={primaryGlow}
                  strokeWidth="1.5"
                  filter="url(#neonGlow)"
                />
                <circle cx="50" cy="45" r="2.5" fill="#ffffff" />
                <line x1="50" y1="35" x2="50" y2="38" stroke={primaryGlow} strokeWidth="1" />
                <line x1="40" y1="45" x2="43" y2="45" stroke={primaryGlow} strokeWidth="1" />
                <line x1="66" y1="45" x2="72" y2="45" stroke="rgba(255, 255, 255, 0.2)" strokeWidth="1.5" />
              </g>
            )}

            {/* HAIR / ENERGY ELEMENTS (Velocity vs Stability) */}
            {isV ? (
              // Velocity: Floating particles & light filaments
              <g opacity="0.8">
                <circle cx="50" cy="14" r="1.5" fill={primaryGlow} style={{ animation: 'avatarPulse 1.5s infinite' }} />
                <circle cx="70" cy="10" r="1" fill={accentColor} style={{ animation: 'avatarPulse 2s infinite' }} />
                <circle cx="60" cy="8" r="2" fill={primaryGlow} style={{ animation: 'avatarPulse 1.2s infinite' }} />
                <path d="M 45 22 L 40 10" stroke={primaryGlow} strokeWidth="0.75" />
                <path d="M 60 22 L 60 5" stroke={accentColor} strokeWidth="0.75" />
                <path d="M 75 22 L 80 10" stroke={primaryGlow} strokeWidth="0.75" />
              </g>
            ) : (
              // Stability: Shroud/hood contour
              <path
                d="M 36 46 C 36 28, 44 16, 60 16 C 76 16, 84 28, 84 46 C 84 56, 82 72, 82 72 L 78 72 L 78 46 C 78 34, 70 26, 60 26 C 50 26, 42 34, 42 46 L 42 72 L 38 72 Z"
                fill="none"
                stroke="rgba(255, 255, 255, 0.12)"
                strokeWidth="1.5"
                strokeDasharray="4, 4"
              />
            )}

            {/* Novelty vs Routine detailing */}
            {isN ? (
              // Novelty: Organic element on head
              <g stroke={accentColor} strokeWidth="0.5" fill="none" opacity="0.6">
                <circle cx="60" cy="30" r="3" />
                <circle cx="55" cy="30" r="2" />
                <circle cx="65" cy="30" r="2" />
              </g>
            ) : (
              // Routine: Hexagonal print
              <polygon
                points="57,28 63,28 66,31 63,34 57,34 54,31"
                fill="none"
                stroke="rgba(255, 255, 255, 0.2)"
                strokeWidth="0.75"
              />
            )}
          </g>

          {/* Foreground HUD scanner line */}
          <line
            x1="10"
            y1="60"
            x2="110"
            y2="60"
            stroke={primaryGlow}
            strokeWidth="0.5"
            strokeOpacity="0.4"
            style={{
              animation: isV ? 'avatarScan 1.8s linear infinite' : 'avatarScan 4.5s linear infinite'
            }}
          />
        </svg>

        {/* Parallax coordinate label overlay */}
        <div style={{
          position: 'absolute',
          bottom: -15,
          left: '50%',
          transform: 'translateX(-50%) translateZ(30px)',
          fontFamily: 'var(--font-mono)',
          fontSize: '0.45rem',
          color: primaryGlow,
          letterSpacing: '0.2em',
          opacity: tilt.x === 0 ? 0.25 : 0.8,
          transition: 'opacity 0.3s ease',
          pointerEvents: 'none'
        }}>
          [{tilt.x.toFixed(0)}, {tilt.y.toFixed(0)}]
        </div>
      </div>
    </div>
  );
}


// Custom Vector SVGs for Stepper Milestones
const MILESTONE_ICONS = {
  pattern_report: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
    </svg>
  ),
  mind_type: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="12" r="10" />
      <path d="M8 12h8M12 8v8" />
    </svg>
  ),
  predictions: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="12" r="10" />
      <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
      <path d="M2 12h20" />
    </svg>
  ),
  hearth: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  ),
  ranked_pulse: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
    </svg>
  ),
  public_graph: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="12" r="10" />
      <path d="M12 2v20M2 12h20" />
    </svg>
  )
};

export default function Profile() {
  const [profile, setProfile] = useState(null);
  const [milestones, setMilestones] = useState(null);
  const [detailed, setDetailed] = useState(null);
  const [loadingDetailed, setLoadingDetailed] = useState(false);
  const [showDetailed, setShowDetailed] = useState(false);
  const [editingSelfDesc, setEditingSelfDesc] = useState(false);
  const [newSelfDesc, setNewSelfDesc] = useState('');
  const [updating, setUpdating] = useState(false);
  const [showGuide, setShowGuide] = useState(false);
  const [selectedSig, setSelectedSig] = useState('BLVN');

  const fetchProfileAndMilestones = useCallback(async () => {
    try {
      const pRes = await fetch('/api/user/profile');
      if (pRes.ok) {
        const pData = await pRes.json();
        setProfile(pData);
        setNewSelfDesc(pData.self_description || '');
      }

      const mRes = await fetch('/api/user/milestones');
      if (mRes.ok) {
        const mData = await mRes.json();
        setMilestones(mData);
      }
    } catch (err) {
      console.error('Failed to load profile data:', err);
    }
  }, []);

  useEffect(() => {
    fetchProfileAndMilestones();
  }, [fetchProfileAndMilestones]);

  const handleFetchDetailed = async () => {
    if (showDetailed) {
      setShowDetailed(false);
      return;
    }
    AudioEngine.playClick();
    setLoadingDetailed(true);
    try {
      const res = await fetch('/api/user/profile/detailed', { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        setDetailed(data);
        setShowDetailed(true);
      } else {
        console.error('Failed to fetch detailed metrics');
      }
    } catch (err) {
      console.error('Error fetching detailed metrics:', err);
    } finally {
      setLoadingDetailed(false);
    }
  };

  const handleSaveSelfDesc = async (e) => {
    e.preventDefault();
    if (!newSelfDesc.trim()) return;
    AudioEngine.playClick();
    setUpdating(true);
    try {
      const res = await fetch('/api/user/self-description', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ self_description: newSelfDesc.trim() })
      });
      if (res.ok) {
        setProfile(prev => prev ? { ...prev, self_description: newSelfDesc.trim() } : null);
        setEditingSelfDesc(false);
      }
    } catch (err) {
      console.error('Failed to update self description:', err);
    } finally {
      setUpdating(false);
    }
  };

  if (!profile || !milestones) {
    return (
      <div className="room-container" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
        <div style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', fontSize: 11, letterSpacing: '0.15em' }}>CONNECTING OBSERVATORY SIGNAL…</div>
      </div>
    );
  }

  const { node_count, unlocked = [] } = milestones;
  const isMindTypeUnlocked = unlocked.includes('mind_type') || node_count >= 15;

  const milestoneThresholds = [
    { key: 'pattern_report', threshold: 5, label: 'Pattern Report', desc: 'Identifies early cognitive clusters' },
    { key: 'mind_type', threshold: 15, label: 'Mind Type Trajectory', desc: 'MBTI-style graph classification' },
    { key: 'predictions', threshold: 30, label: 'Monthly Predictions', desc: 'Topic extrapolation engine' },
    { key: 'hearth', threshold: 50, label: 'Hearth Space', desc: 'Enables pairing with a friend and growing a shared Hearth space' },
    { key: 'ranked_pulse', threshold: 100, label: 'Ranked Pulse', desc: 'High-frequency hub analysis' },
    { key: 'public_graph', threshold: 200, label: 'Public Graph Observatory', desc: 'Declassified shared map' }
  ];

  const ARCHETYPES = {
    "BLVN": "Warp Navigator",
    "FLVN": "Quantum Catalyst",
    "BLSN": "Nebula Weaver",
    "FLSN": "Alchemy Core",
    "BLVR": "Ingestion Matrix",
    "FLVR": "Laser Synthesizer",
    "BLSR": "Codex Cartographer",
    "FLSR": "Monolith Architect",
    "BIVN": "Void Collector",
    "FIVN": "Recon Scout",
    "BISN": "Archival Explorer",
    "FISN": "Deep Diver",
    "BIVR": "Cyclone Curator",
    "FIVR": "Sentinel Core",
    "BISR": "Silent Librarian",
    "FISR": "Singular Vault"
  };

  return (
    <div className="observatory-wrapper">
      <style>{`
        .observatory-wrapper {
          overflow-y: auto;
          padding: 4rem 3.5rem;
          height: 100%;
          box-sizing: border-box;
          font-family: var(--font-body);
          color: var(--text-signal);
          background: #060507;
          background-size: 50px 50px;
          background-image: 
            linear-gradient(to right, rgba(255, 255, 255, 0.015) 1px, transparent 1px),
            linear-gradient(to bottom, rgba(255, 255, 255, 0.015) 1px, transparent 1px);
          position: relative;
        }
        
        .observatory-wrapper::before {
          content: '';
          position: absolute;
          top: 0;
          left: 50%;
          transform: translateX(-50%);
          width: 60%;
          height: 300px;
          background: radial-gradient(circle, rgba(207, 163, 101, 0.06) 0%, transparent 70%);
          pointer-events: none;
          z-index: 0;
        }
        
        .observatory-header {
          margin-bottom: 4.5rem;
          position: relative;
          z-index: 1;
        }
        
        .observatory-header h1 {
          font-family: var(--font-display);
          font-size: 3rem;
          font-weight: 700;
          color: #ffffff;
          margin: 0;
          letter-spacing: -0.04em;
        }
        
        .observatory-header p {
          font-family: var(--font-mono);
          font-size: 0.65rem;
          text-transform: uppercase;
          color: var(--accent-gold);
          margin: 0.6rem 0 0 0;
          letter-spacing: 0.35em;
        }
        
        .grid-two-cols {
          display: grid;
          grid-template-columns: 1.15fr 0.85fr;
          gap: 3rem;
          margin-bottom: 3rem;
          position: relative;
          z-index: 1;
        }
        
        @media (max-width: 1024px) {
          .grid-two-cols {
            grid-template-columns: 1fr;
            gap: 2.5rem;
          }
        }
        
        .profile-card {
          background: rgba(12, 10, 15, 0.65);
          backdrop-filter: blur(20px);
          -webkit-backdrop-filter: blur(20px);
          border: 1px solid rgba(255, 255, 255, 0.04);
          border-radius: 16px;
          padding: 2.5rem;
          box-shadow: 0 30px 60px rgba(0, 0, 0, 0.45), inset 0 1px 0 rgba(255, 255, 255, 0.02);
          position: relative;
          transition: all 0.3s ease;
        }
        
        .profile-card:hover {
          border-color: rgba(207, 163, 101, 0.15);
        }
        
        .card-corner-label {
          position: absolute;
          top: 1.25rem;
          right: 1.5rem;
          font-family: var(--font-mono);
          font-size: 0.6rem;
          letter-spacing: 0.2em;
          color: rgba(207, 163, 101, 0.4);
          text-transform: uppercase;
        }
        
        .card-title {
          font-family: var(--font-display);
          font-size: 1.5rem;
          font-weight: 700;
          color: #ffffff;
          margin: 0 0 0.5rem 0;
          letter-spacing: -0.02em;
        }
        
        .card-subtitle {
          font-size: 0.85rem;
          color: var(--text-muted);
          margin: 0 0 2.5rem 0;
          line-height: 1.5;
        }
        
        /* Constellation Stepper */
        .stepper-container {
          position: relative;
          display: flex;
          flex-direction: column;
          gap: 1.75rem;
        }
        
        .stepper-line {
          position: absolute;
          left: 24px;
          top: 24px;
          bottom: 24px;
          width: 1px;
          background: rgba(255, 255, 255, 0.05);
          z-index: 1;
        }
        
        .stepper-progress {
          position: absolute;
          left: 24px;
          top: 24px;
          width: 1px;
          background: var(--accent-gold);
          box-shadow: 0 0 8px var(--accent-gold);
          z-index: 2;
          transition: height 0.6s cubic-bezier(0.16, 1, 0.3, 1);
        }
        
        .stepper-item {
          position: relative;
          display: flex;
          align-items: center;
          gap: 1.75rem;
          z-index: 3;
        }
        
        .stepper-dot {
          position: relative;
          z-index: 3;
          width: 48px;
          height: 48px;
          border-radius: 50%;
          background: #060507;
          border: 1px solid rgba(255, 255, 255, 0.05);
          display: flex;
          align-items: center;
          justify-content: center;
          color: var(--text-muted);
          transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1);
        }
        
        .stepper-item.unlocked .stepper-dot {
          border-color: var(--accent-gold);
          color: var(--accent-gold);
          background: radial-gradient(circle, #231c19 0%, #0c0a0f 100%);
          box-shadow: 0 0 16px rgba(207, 163, 101, 0.12);
        }
        
        .stepper-content {
          flex: 1;
        }
        
        .stepper-label {
          font-family: var(--font-display);
          font-size: 1rem;
          font-weight: 600;
          color: var(--text-muted);
          transition: color 0.3s ease;
        }
        
        .stepper-requirement-badge {
          font-family: var(--font-mono);
          font-size: 0.65rem;
          color: var(--accent-gold);
          border: 1px solid rgba(207, 163, 101, 0.18);
          border-radius: 4px;
          padding: 1px 6px;
          letter-spacing: 0.05em;
          background: rgba(207, 163, 101, 0.03);
          text-transform: uppercase;
        }
        
        .stepper-item:not(.unlocked) .stepper-requirement-badge {
          color: var(--text-muted);
          border-color: rgba(255, 255, 255, 0.08);
          background: rgba(255, 255, 255, 0.01);
        }
        
        .stepper-item.unlocked .stepper-label {
          color: #ffffff;
        }
        
        .stepper-desc {
          font-size: 0.78rem;
          color: var(--text-muted);
          margin-top: 0.15rem;
          opacity: 0.85;
        }
        
        /* Monospace direction quote block */
        .direction-quote-box {
          background: rgba(0, 0, 0, 0.25);
          border: 1px solid rgba(255, 255, 255, 0.03);
          padding: 1.75rem 2rem;
          border-radius: 8px;
          color: #e2e1e6;
          line-height: 1.6;
          font-size: 0.95rem;
          position: relative;
          min-height: 120px;
          box-shadow: inset 0 2px 10px rgba(0, 0, 0, 0.4);
        }
        
        .direction-quote-box::after {
          content: ' _';
          color: var(--accent-gold);
          animation: blink 1s step-end infinite;
          font-weight: 700;
        }
        
        /* Locked Trajectory Overlay */
        .locked-trajectory {
          position: relative;
          min-height: 480px; /* Elevated min-height to guarantee orbit HUD has space */
          z-index: 1;
        }
        
        .locked-trajectory-overlay {
          position: absolute;
          inset: 0;
          background: rgba(6, 5, 8, 0.82);
          backdrop-filter: blur(12px);
          -webkit-backdrop-filter: blur(12px);
          z-index: 10;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 1.25rem;
          text-align: center;
          padding: 3rem 2.5rem;
          border-radius: 16px;
          box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.02);
        }
        
        .blurred-content {
          filter: blur(14px) saturate(35%);
          opacity: 0.25;
          pointer-events: none;
          user-select: none;
          transition: filter 0.5s ease;
        }
        
        .observatory-lock-hud {
          position: relative;
          width: 160px;
          height: 160px;
          margin-bottom: 0.5rem;
          display: flex;
          align-items: center;
          justify-content: center;
        }
        
        .hud-svg {
          width: 100%;
          height: 100%;
          transform-origin: center;
        }
        
        .hud-circle {
          fill: none;
          transform-origin: center;
        }
        
        .hud-circle.tech {
          stroke: rgba(207, 163, 101, 0.05);
          stroke-width: 1;
        }
        
        .hud-circle.dash {
          stroke: rgba(207, 163, 101, 0.15);
          stroke-width: 1;
          stroke-dasharray: 4 12;
          animation: spin-clockwise 25s linear infinite;
        }
        
        .hud-circle.solid {
          stroke: rgba(207, 163, 101, 0.08);
          stroke-width: 1;
        }
        
        .hud-axis {
          stroke: rgba(207, 163, 101, 0.3);
          stroke-width: 1.5;
        }
        
        .hud-dot-path {
          fill: none;
          stroke: transparent;
        }
        
        .hud-dot {
          fill: var(--accent-gold);
          transform-origin: center;
          animation: orbit 8s linear infinite;
        }
        
        .hud-lock {
          filter: drop-shadow(0 0 4px rgba(207, 163, 101, 0.3));
          animation: pulse-lock 2s infinite ease-in-out;
        }
        
        @keyframes spin-clockwise {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        
        @keyframes orbit {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        
        @keyframes pulse-lock {
          0%, 100% { transform: scale(1); opacity: 0.95; }
          50% { transform: scale(1.05); opacity: 0.7; }
        }
        
        .locked-badge {
          font-family: var(--font-mono);
          font-size: 0.65rem;
          color: var(--accent-gold);
          border: 1px solid rgba(207, 163, 101, 0.25);
          border-radius: 4px;
          padding: 2px 10px;
          letter-spacing: 0.15em;
          background: rgba(207, 163, 101, 0.05);
          text-transform: uppercase;
        }
        
        .locked-title {
          font-family: var(--font-display);
          font-size: 1.5rem;
          font-weight: 700;
          color: #ffffff;
          margin: 0;
          letter-spacing: -0.01em;
        }
        
        .locked-text {
          font-size: 0.85rem;
          color: var(--text-muted);
          max-width: 400px;
          margin: 0;
          line-height: 1.6;
        }
        
        /* Timeline */
        .trajectory-timeline-strip {
          display: flex;
          align-items: center;
          gap: 1rem;
          overflow-x: auto;
          padding: 1.5rem 0.5rem;
          border-top: 1px solid rgba(255, 255, 255, 0.03);
          border-bottom: 1px solid rgba(255, 255, 255, 0.03);
        }
        
        .timeline-badge {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 0.35rem;
          background: rgba(255, 255, 255, 0.015);
          border: 1px solid rgba(255, 255, 255, 0.05);
          padding: 0.85rem 1.15rem;
          border-radius: 12px;
          min-width: 125px;
          position: relative;
          transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
          cursor: default;
          box-sizing: border-box;
        }
        .timeline-badge:hover {
          background: rgba(255, 255, 255, 0.03);
          border-color: rgba(255, 255, 255, 0.12);
          transform: translateY(-4px);
        }
        .timeline-badge.current {
          background: rgba(207, 163, 101, 0.03);
          border-color: var(--accent-gold);
          box-shadow: inset 0 0 10px rgba(207, 163, 101, 0.05), 0 4px 20px rgba(0, 0, 0, 0.4);
        }
        
        .timeline-label {
          font-family: var(--font-mono);
          font-size: 0.78rem;
          font-weight: 700;
          color: rgba(255, 255, 255, 0.85);
          letter-spacing: 0.05em;
        }
        .timeline-badge.current .timeline-label {
          color: var(--accent-gold);
          text-shadow: 0 0 8px rgba(207, 163, 101, 0.45);
        }
        
        .timeline-date {
          font-family: var(--font-mono);
          font-size: 0.58rem;
          color: var(--text-muted);
          background: rgba(255, 255, 255, 0.03);
          padding: 2px 8px;
          border-radius: 4px;
        }
        .timeline-badge.current .timeline-date {
          background: rgba(207, 163, 101, 0.12);
          color: var(--accent-gold);
        }
        .timeline-connector {
          height: 1px;
          width: 32px;
          background: linear-gradient(90deg, rgba(255, 255, 255, 0.03), rgba(207, 163, 101, 0.3), rgba(255, 255, 255, 0.03));
          box-shadow: 0 0 6px rgba(207, 163, 101, 0.15);
          flex-shrink: 0;
        }
        
        .btn-inspect {
          background: rgba(255, 255, 255, 0.02);
          border: 1px solid rgba(255, 255, 255, 0.06);
          color: #ffffff;
          font-family: var(--font-mono);
          font-size: 0.75rem;
          letter-spacing: 0.05em;
          padding: 0.85rem 1.75rem;
          border-radius: 8px;
          cursor: pointer;
          transition: all 0.3s ease;
          display: flex;
          align-items: center;
          gap: 0.75rem;
        }
        
        .btn-inspect:hover {
          background: rgba(207, 163, 101, 0.05);
          border-color: rgba(207, 163, 101, 0.3);
          color: var(--accent-gold);
          box-shadow: 0 0 12px rgba(207, 163, 101, 0.05);
        }
        
        /* Metric cards */
        .metric-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
          gap: 1.5rem;
          animation: fadeIn 0.4s ease-out;
        }
        
        .metric-panel {
          background: rgba(5, 4, 7, 0.3);
          border: 1px solid rgba(255, 255, 255, 0.03);
          border-radius: 12px;
          padding: 1.5rem;
          display: flex;
          align-items: center;
          gap: 1.25rem;
          position: relative;
        }
        
        .metric-content {
          flex: 1;
          display: flex;
          flex-direction: column;
          gap: 0.4rem;
        }
        
        .metric-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
        }
        
        .metric-title {
          font-family: var(--font-display);
          font-size: 0.95rem;
          font-weight: 600;
          color: #ffffff;
        }
        
        .metric-status {
          font-family: var(--font-mono);
          font-size: 0.65rem;
          border-radius: 4px;
          padding: 2px 8px;
        }
        
        .metric-status.high {
          color: var(--accent-gold);
          background: rgba(207, 163, 101, 0.05);
          border: 1px solid rgba(207, 163, 101, 0.2);
        }
        
        .metric-status.low {
          color: var(--text-muted);
          background: rgba(255, 255, 255, 0.02);
          border: 1px solid rgba(255, 255, 255, 0.05);
        }
        
        .metric-value-row {
          display: flex;
          align-items: baseline;
          gap: 0.5rem;
        }
        
        .metric-value {
          font-family: var(--font-mono);
          font-size: 1.6rem;
          font-weight: 700;
          color: #ffffff;
        }
        
        .metric-threshold {
          font-family: var(--font-mono);
          font-size: 0.7rem;
          color: var(--text-muted);
        }
        
        .metric-desc {
          font-size: 0.8rem;
          color: var(--text-muted);
          line-height: 1.45;
          margin: 0;
        }
        
        @keyframes blink {
          50% { opacity: 0; }
        }
        
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(10px); }
          to { opacity: 1; transform: translateY(0); }
        }

        /* Modal Styles */
        .modal-overlay {
          position: fixed;
          inset: 0;
          background: rgba(0, 0, 0, 0.75);
          backdrop-filter: blur(8px);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 1000;
          animation: fadeIn 0.25s ease-out;
        }
        .modal-box {
          background: linear-gradient(135deg, #120e18 0%, #08060a 100%);
          border: 1px solid rgba(207, 163, 101, 0.25);
          border-radius: 16px;
          width: 90%;
          max-width: 680px;
          max-height: 85vh;
          overflow-y: auto;
          padding: 2.5rem;
          box-shadow: 0 24px 60px rgba(0,0,0,0.8), 0 0 30px rgba(207,163,101,0.05);
          position: relative;
        }
        .modal-close {
          position: absolute;
          top: 1.25rem;
          right: 1.5rem;
          background: transparent;
          border: none;
          color: var(--text-muted);
          font-size: 1.5rem;
          cursor: pointer;
          transition: color 0.2s;
        }
        .modal-close:hover {
          color: #ffffff;
        }
        .modal-section {
          margin-bottom: 2rem;
        }
        /* Wider Modal for Codex */
        .modal-box.wide {
          max-width: 900px;
        }
        
        /* Codex Grid Layout */
        .codex-grid {
          display: grid;
          grid-template-columns: 320px 1fr;
          gap: 2rem;
          margin-top: 1.5rem;
          min-height: 480px;
        }
        @media (max-width: 768px) {
          .codex-grid {
            grid-template-columns: 1fr;
            gap: 1.5rem;
          }
        }
        
        .codex-sidebar {
          display: flex;
          flex-direction: column;
          gap: 0.5rem;
          max-height: 480px;
          overflow-y: auto;
          padding-right: 0.5rem;
          border-right: 1px solid rgba(255, 255, 255, 0.05);
        }
        @media (max-width: 768px) {
          .codex-sidebar {
            border-right: none;
            max-height: 240px;
          }
        }
        
        /* Custom scrollbar for sidebar */
        .codex-sidebar::-webkit-scrollbar {
          width: 4px;
        }
        .codex-sidebar::-webkit-scrollbar-track {
          background: rgba(255, 255, 255, 0.01);
        }
        .codex-sidebar::-webkit-scrollbar-thumb {
          background: rgba(207, 163, 101, 0.15);
          border-radius: 4px;
        }
        
        .codex-item {
          background: rgba(255, 255, 255, 0.01);
          border: 1px solid rgba(255, 255, 255, 0.03);
          padding: 0.75rem 1rem;
          border-radius: 8px;
          cursor: pointer;
          transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
          display: flex;
          align-items: center;
          justify-content: space-between;
        }
        .codex-item:hover {
          background: rgba(255, 255, 255, 0.03);
          border-color: rgba(207, 163, 101, 0.15);
        }
        .codex-item.active {
          background: rgba(207, 163, 101, 0.05);
          border-color: var(--accent-gold);
          box-shadow: inset 0 0 10px rgba(207, 163, 101, 0.05);
        }
        
        .codex-item-name {
          font-family: var(--font-display);
          font-size: 0.82rem;
          font-weight: 600;
          color: rgba(255, 255, 255, 0.75);
          transition: color 0.2s;
        }
        .codex-item.active .codex-item-name {
          color: #ffffff;
        }
        .codex-item-code {
          font-family: var(--font-mono);
          font-size: 0.68rem;
          color: var(--text-muted);
          transition: color 0.2s;
        }
        .codex-item.active .codex-item-code {
          color: var(--accent-gold);
        }
        
        .codex-viewer {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          background: rgba(5, 4, 7, 0.2);
          border: 1px solid rgba(255, 255, 255, 0.02);
          border-radius: 12px;
          padding: 2.5rem;
          position: relative;
          overflow: hidden;
          text-align: center;
          animation: fadeIn 0.4s ease-out;
        }
        
        /* Tactical corner borders */
        .codex-viewer::before, .codex-viewer::after {
          content: '';
          position: absolute;
          width: 10px;
          height: 10px;
          border: 1px solid var(--accent-gold);
          opacity: 0.35;
        }
        .codex-viewer::before {
          top: 12px;
          left: 12px;
          border-right: none;
          border-bottom: none;
        }
        .codex-viewer::after {
          bottom: 12px;
          right: 12px;
          border-left: none;
          border-top: none;
        }
        
        /* HUD scanline animation */
        .hud-scanline {
          position: absolute;
          top: 0;
          left: 0;
          width: 100%;
          height: 1px;
          background: linear-gradient(90deg, transparent, rgba(207, 163, 101, 0.12), transparent);
          animation: hudScan 4.5s linear infinite;
          pointer-events: none;
        }
        @keyframes hudScan {
          0% { top: 0%; }
          100% { top: 100%; }
        }
        
        /* Tactical HUD borders on cards */
        .metric-panel {
          overflow: hidden;
          transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
        }
        .metric-panel:hover {
          border-color: rgba(207, 163, 101, 0.2);
          background: rgba(207, 163, 101, 0.015);
          box-shadow: 0 8px 30px rgba(0, 0, 0, 0.4), 0 0 15px rgba(207, 163, 101, 0.02);
          transform: translateY(-2px);
        }
        .metric-panel::before {
          content: '';
          position: absolute;
          top: 0;
          left: -100%;
          width: 100%;
          height: 1px;
          background: linear-gradient(90deg, transparent, rgba(207, 163, 101, 0.4), transparent);
          transition: left 0.5s ease;
        }
        .metric-panel:hover::before {
          left: 100%;
        }
        
        .metric-panel-tag {
          position: absolute;
          top: 6px;
          right: 8px;
          font-family: var(--font-mono);
          font-size: 0.55rem;
          color: rgba(255, 255, 255, 0.15);
          letter-spacing: 0.1em;
        }

        /* SVG Constellation & Avatar animations */
        @keyframes avatarSpin {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
        @keyframes avatarPulse {
          0%, 100% { transform: scale(1); opacity: 0.8; }
          50% { transform: scale(1.05); opacity: 1; }
        }
        @keyframes avatarGlowPulse {
          0%, 100% { opacity: 0.45; }
          50% { opacity: 0.85; }
        }
        @keyframes avatarScan {
          0% { transform: translateY(-35px); opacity: 0; }
          10% { opacity: 0.8; }
          90% { opacity: 0.8; }
          100% { transform: translateY(35px); opacity: 0; }
        }
      `}</style>

      {/* Title Header */}
      <header className="observatory-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h1>Cognitive Observatory</h1>
          <p>identity · trajectories · structures</p>
        </div>
        {profile && profile.pulse_score !== undefined && (
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            background: 'rgba(207,163,101,0.02)',
            border: '1px solid rgba(207,163,101,0.12)',
            borderRadius: '12px',
            padding: '8px 16px',
            boxShadow: '0 0 15px rgba(207,163,101,0.03)',
            animation: 'fadeIn 0.5s ease',
          }}>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.55rem', color: 'var(--accent-gold)', letterSpacing: '0.12em', textTransform: 'uppercase' }}>
                Cognitive Pulse
              </span>
              <span style={{ fontSize: '0.88rem', fontWeight: 700, color: '#ffffff' }}>
                {profile.pulse_score}%
              </span>
            </div>
            {/* Minimal Pulse Indicator */}
            <div style={{
              width: '10px',
              height: '10px',
              borderRadius: '50%',
              background: '#CFA365',
              boxShadow: '0 0 8px #CFA365',
              animation: 'pulseGlow 1.6s infinite ease-in-out',
            }} />
            <style>{`
              @keyframes pulseGlow {
                0%, 100% { transform: scale(1); opacity: 0.65; box-shadow: 0 0 4px #CFA365; }
                50% { transform: scale(1.2); opacity: 1; box-shadow: 0 0 10px #CFA365; }
              }
            `}</style>
          </div>
        )}
      </header>

      {/* Row 1: Stepper Milestones & Direction */}
      <div className="grid-two-cols">
        
        {/* Stepper Milestones Panel */}
        <section className="profile-card">
          <div className="card-corner-label">OBSERVATION_STEPPERS</div>
          <h2 className="card-title">Observed Nodes: {node_count}</h2>
          <p className="card-subtitle">Unlock thresholds of your cognitive capabilities.</p>

          <div className="stepper-container">
            <div className="stepper-line" />
            {unlocked.length > 1 && (
              <div 
                className="stepper-progress" 
                style={{
                  height: `${((unlocked.length - 1) / (milestoneThresholds.length - 1)) * 100}%`
                }} 
              />
            )}
            
            {milestoneThresholds.map((m) => {
              const isUnlocked = node_count >= m.threshold;
              return (
                <div key={m.key} className={`stepper-item ${isUnlocked ? 'unlocked' : ''}`}>
                  <div className="stepper-dot">
                    {isUnlocked ? '✓' : MILESTONE_ICONS[m.key]}
                  </div>
                  <div className="stepper-content">
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                      <span className="stepper-label">{m.label}</span>
                      <span className="stepper-requirement-badge">
                        {m.threshold} saves
                      </span>
                    </div>
                    <div className="stepper-desc">{m.desc}</div>
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        {/* Direction Card */}
        <section className="profile-card" style={{ display: 'flex', flexDirection: 'column' }}>
          <div className="card-corner-label">STATED_INTEREST</div>
          <h2 className="card-title">Stated Direction</h2>
          <p className="card-subtitle">Your claimed search statement. Used in discrepancy scans.</p>

          {editingSelfDesc ? (
            <form onSubmit={handleSaveSelfDesc} style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', flex: 1 }}>
              <textarea
                value={newSelfDesc}
                onChange={(e) => setNewSelfDesc(e.target.value)}
                style={{
                  width: '100%',
                  background: 'rgba(0, 0, 0, 0.4)',
                  border: '1px solid rgba(255, 255, 255, 0.08)',
                  borderRadius: '8px',
                  color: '#ffffff',
                  padding: '1.25rem',
                  fontSize: '0.9rem',
                  fontFamily: 'var(--font-body)',
                  resize: 'none',
                  flex: 1,
                  minHeight: '140px',
                  outline: 'none',
                  boxSizing: 'border-box',
                  boxShadow: 'inset 0 2px 8px rgba(0,0,0,0.5)',
                  transition: 'border-color 0.2s',
                }}
                maxLength={200}
                placeholder="What topics are you mostly interested in right now?"
              />
              <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
                <button
                  type="button"
                  onClick={() => setEditingSelfDesc(false)}
                  style={{
                    background: 'transparent',
                    border: '1px solid rgba(255, 255, 255, 0.12)',
                    color: 'var(--text-muted)',
                    borderRadius: '6px',
                    padding: '8px 18px',
                    fontSize: '0.8rem',
                    cursor: 'pointer',
                  }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={updating}
                  style={{
                    background: 'var(--accent-gold)',
                    border: 'none',
                    color: '#000000',
                    borderRadius: '6px',
                    padding: '8px 18px',
                    fontSize: '0.8rem',
                    fontWeight: 700,
                    cursor: 'pointer',
                  }}
                >
                  {updating ? 'Saving...' : 'Save'}
                </button>
              </div>
            </form>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', flex: 1, justifyContent: 'space-between' }}>
              <div className="direction-quote-box">
                {profile.self_description ? (
                  profile.self_description
                ) : (
                  "No statement recorded yet. Write one now to help filter monthly discrepancies."
                )}
              </div>
              <button
                onClick={() => { AudioEngine.playClick(); setEditingSelfDesc(true); }}
                style={{
                  alignSelf: 'flex-end',
                  background: 'transparent',
                  border: '1px solid rgba(207, 163, 101, 0.35)',
                  color: 'var(--accent-gold)',
                  borderRadius: '6px',
                  padding: '8px 18px',
                  fontSize: '0.8rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                }}
              >
                Edit Direction
              </button>
            </div>
          )}
        </section>
      </div>

      {/* Row 2: Cognitive Trajectory */}
      <section className="profile-card locked-trajectory">
        
        {/* Real content rendered underneath the overlay, blurred out */}
        <div className={!isMindTypeUnlocked ? 'blurred-content' : ''}>
          <h2 className="card-title">Cognitive Trajectory</h2>
          <p className="card-subtitle">Weekly shifts in your graph geometry and conceptual connections.</p>
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
            <div style={{ 
              display: 'grid', 
              gridTemplateColumns: '1fr auto', 
              gap: '2rem', 
              padding: '2rem', 
              background: 'rgba(5, 4, 7, 0.4)', 
              border: '1px solid rgba(255, 255, 255, 0.03)', 
              borderRadius: '16px',
              position: 'relative',
              overflow: 'hidden'
            }}>
              {/* Tactical background scanline */}
              <div className="hud-scanline" />
              
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', justifyContent: 'center' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.62rem', color: 'var(--accent-gold)', letterSpacing: '0.15em', textTransform: 'uppercase' }}>
                    Active Mind Classification
                  </span>
                  <h1 style={{ fontFamily: 'var(--font-display)', fontSize: '2rem', fontWeight: 800, color: '#ffffff', letterSpacing: '-0.02em', margin: 0 }}>
                    {isMindTypeUnlocked ? (ARCHETYPES[profile.mind_type] || profile.mind_type || 'Cognitive Explorer') : 'Polymath Explorer'}
                  </h1>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                    Signature Reference: {isMindTypeUnlocked ? (profile.mind_type || 'BLVN') : 'BLVN'}
                  </span>
                </div>
                
                <div style={{ 
                  background: 'rgba(255, 255, 255, 0.01)', 
                  borderLeft: '2px solid var(--accent-gold)', 
                  padding: '1rem 1.5rem', 
                  borderRadius: '0 8px 8px 0',
                  marginTop: '0.5rem'
                }}>
                  <p style={{ fontSize: '0.92rem', color: '#e2e2e2', margin: 0, lineHeight: 1.6, fontStyle: 'italic' }}>
                    {isMindTypeUnlocked ? (profile.mind_type_summary ? `“${profile.mind_type_summary}”` : 'Calculating weekly summary...') : '“Your mind is heavily classified under broad conceptual integration...”'}
                  </p>
                </div>
              </div>
              
              {/* Avatar Frame on the Right */}
              <div style={{ 
                display: 'flex', 
                alignItems: 'center', 
                justifyContent: 'center',
                background: 'rgba(255, 255, 255, 0.01)',
                border: '1px solid rgba(255, 255, 255, 0.04)',
                borderRadius: '12px',
                height: '140px',
                width: '140px',
                position: 'relative'
              }}>
                <div style={{ position: 'absolute', top: 6, left: 8, fontSize: '0.5rem', fontFamily: 'var(--font-mono)', color: 'rgba(255,255,255,0.15)', letterSpacing: '0.05em' }}>
                  SCAN.V4
                </div>
                <CognitiveAvatar signature={isMindTypeUnlocked ? (profile.mind_type || 'BLVN') : 'BLVN'} size={110} />
              </div>
            </div>
            
             <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%', flexWrap: 'wrap', gap: '0.5rem' }}>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--text-muted)', letterSpacing: '0.12em' }}>
                  HISTORICAL WEEKLY STRIP
                </span>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.58rem', color: 'var(--accent-gold)', opacity: 0.85, letterSpacing: '0.08em' }}>
                  [ RECALCULATES WEEKLY ON SUNDAY ]
                </span>
              </div>
              <div className="trajectory-timeline-strip">
                {isMindTypeUnlocked && profile.mind_type_trajectory && profile.mind_type_trajectory.length > 0 ? (
                  profile.mind_type_trajectory.map((item, idx) => {
                    const isLast = idx === profile.mind_type_trajectory.length - 1;
                    return (
                      <React.Fragment key={idx}>
                        <div className={`timeline-badge ${isLast ? 'current' : ''}`}>
                          <span className="timeline-label">
                            {item.mind_type}
                          </span>
                          <span style={{ fontSize: '0.52rem', color: isLast ? 'var(--accent-gold)' : 'var(--text-muted)', fontFamily: 'var(--font-mono)', textAlign: 'center', opacity: 0.85 }}>
                            {ARCHETYPES[item.mind_type] || 'Explorer'}
                          </span>
                          <span className="timeline-date">
                            {item.date ? item.date.slice(5) : ''}
                          </span>
                        </div>
                        {!isLast && (
                          <div className="timeline-connector" />
                        )}
                      </React.Fragment>
                    );
                  })
                ) : (
                  <div className="timeline-badge current">
                    <span className="timeline-label">BLVN</span>
                    <span style={{ fontSize: '0.52rem', color: 'var(--accent-gold)', fontFamily: 'var(--font-mono)', textAlign: 'center' }}>
                      Warp Navigator
                    </span>
                    <span className="timeline-date">06-29</span>
                  </div>
                )}
              </div>
            </div>

            {/* Expand Detailed Metrics */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
              <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
                <button 
                  onClick={handleFetchDetailed} 
                  disabled={loadingDetailed || !isMindTypeUnlocked} 
                  className="btn-inspect"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M3 3v18h18" />
                    <path d="M18.7 8l-5.1 5.2-2.8-2.7L7 14.3" />
                  </svg>
                  <span>{loadingDetailed ? 'CALCULATING COGNITIVE GRAPH…' : showDetailed ? 'COLLAPSE METRICS' : 'INSPECT GRAPH METRICS'}</span>
                </button>
                <button 
                  onClick={() => setShowGuide(true)} 
                  disabled={!isMindTypeUnlocked}
                  className="btn-inspect"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="12" cy="12" r="10" />
                    <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
                    <line x1="12" y1="17" x2="12.01" y2="17" />
                  </svg>
                  <span>DIRECTORY GUIDE</span>
                </button>
              </div>

              {showDetailed && detailed && (
                <div className="metric-grid">
                  {[
                    { key: 'breadth', title: 'Breadth (B/F)', score: detailed.breadth.score, threshold: detailed.breadth.threshold, max: 2.0, desc: detailed.breadth.explanation },
                    { key: 'linkage', title: 'Linkage (L/I)', score: detailed.linkage.score, threshold: detailed.linkage.threshold, max: 1.0, desc: detailed.linkage.explanation },
                    { key: 'velocity', title: 'Velocity (V/S)', score: detailed.velocity.score, threshold: detailed.velocity.threshold, max: 15.0, desc: detailed.velocity.explanation },
                    { key: 'novelty', title: 'Novelty (N/R)', score: detailed.novelty.score, threshold: detailed.novelty.threshold, max: 0.5, desc: detailed.novelty.explanation }
                  ].map((dim) => {
                    const pass = dim.score >= dim.threshold;
                    
                    return (
                      <div key={dim.key} className="metric-panel">
                        <span className="metric-panel-tag">[ {dim.key.toUpperCase()} ]</span>
                        <CircularProgress value={dim.score} threshold={dim.threshold} max={dim.max} />
                        
                        <div className="metric-content">
                          <div className="metric-header">
                            <span className="metric-title">{dim.title}</span>
                            <span className={`metric-status ${pass ? 'high' : 'low'}`}>
                              {pass ? 'HIGH' : 'LOW'}
                            </span>
                          </div>
                          <div className="metric-value-row">
                            <span className="metric-value">{dim.score.toFixed(2)}</span>
                            <span className="metric-threshold">Threshold: {dim.threshold.toFixed(2)}</span>
                          </div>
                          <p className="metric-desc">{dim.desc}</p>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

          </div>
        </div>

        {/* Locking Overlay */}
        {!isMindTypeUnlocked && (
          <div className="locked-trajectory-overlay">
            <div className="observatory-lock-hud">
              <svg width="160" height="160" viewBox="0 0 160 160" className="hud-svg">
                <circle cx="80" cy="80" r="70" className="hud-circle tech" />
                <circle cx="80" cy="80" r="60" className="hud-circle dash" />
                <circle cx="80" cy="80" r="48" className="hud-circle solid" />
                <line x1="80" y1="10" x2="80" y2="20" className="hud-axis" />
                <line x1="80" y1="140" x2="80" y2="150" className="hud-axis" />
                <line x1="10" y1="80" x2="20" y2="80" className="hud-axis" />
                <line x1="140" y1="80" x2="150" y2="80" className="hud-axis" />
                <circle cx="80" cy="80" r="60" className="hud-dot-path" />
                <circle cx="140" cy="80" r="3.5" className="hud-dot" />
                <g transform="translate(68, 68)">
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--accent-gold)" strokeWidth="1.5" className="hud-lock">
                    <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                    <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                  </svg>
                </g>
              </svg>
            </div>
            <div className="locked-badge">[ CLASSIFIED SYSTEM ]</div>
            <h3 className="locked-title">Trajectory Insights</h3>
            <p className="locked-text">
              Analysis requires 15 active nodes. Save {15 - node_count} more items to decode your weekly cognitive classifications.
            </p>
          </div>
        )}
      </section>

      {showGuide && (
        <div className="modal-overlay" onClick={() => setShowGuide(false)}>
          <div className="modal-box wide" onClick={(e) => e.stopPropagation()}>
            <button className="modal-close" onClick={() => setShowGuide(false)}>&times;</button>
            
            <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
              <span className="locked-badge" style={{ color: 'var(--accent-gold)' }}>[ COGNITIVE SYSTEM DIRECTORY ]</span>
              <h2 style={{ fontFamily: 'var(--font-display)', color: '#ffffff', fontSize: '1.75rem', marginTop: '0.5rem', marginBottom: '0.25rem' }}>
                Cognitive Codex Directory
              </h2>
              <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                Interactive diagnostic signatures mapping all 16 memory network topologies.
              </p>
            </div>

            {(() => {
              const DIRECTORY_ARCHETYPES = [
                { code: 'BLVN', name: 'Warp Navigator', desc: 'Saves widely, synthesizes concepts globally, ingests at high velocity, and explores high novelty.' },
                { code: 'FLVN', name: 'Quantum Catalyst', desc: 'Deeply focused domain expert, synthesizes concepts globally, ingests at high velocity, and explores high novelty.' },
                { code: 'BLSN', name: 'Nebula Weaver', desc: 'Saves widely, synthesizes concepts globally, ingests at a steady pace, and explores high novelty.' },
                { code: 'FLSN', name: 'Alchemy Core', desc: 'Deeply focused domain expert, synthesizes concepts globally, ingests at a steady pace, and explores high novelty.' },
                { code: 'BLVR', name: 'Ingestion Matrix', desc: 'Saves widely, synthesizes concepts globally, ingests at high velocity, and reinforces routine expertise.' },
                { code: 'FLVR', name: 'Laser Synthesizer', desc: 'Deeply focused domain expert, synthesizes concepts globally, ingests at high velocity, and reinforces routine expertise.' },
                { code: 'BLSR', name: 'Codex Cartographer', desc: 'Saves widely, synthesizes concepts globally, ingests at a steady pace, and reinforces routine expertise.' },
                { code: 'FLSR', name: 'Monolith Architect', desc: 'Deeply focused domain expert, synthesizes concepts globally, ingests at a steady pace, and reinforces routine expertise.' },
                { code: 'BIVN', name: 'Void Collector', desc: 'Saves widely, maintains isolated independent silos, ingests at high velocity, and explores high novelty.' },
                { code: 'FIVN', name: 'Recon Scout', desc: 'Deeply focused domain expert, maintains isolated independent silos, ingests at high velocity, and explores high novelty.' },
                { code: 'BISN', name: 'Archival Explorer', desc: 'Saves widely, maintains isolated independent silos, ingests at a steady pace, and explores high novelty.' },
                { code: 'FISN', name: 'Deep Diver', desc: 'Deeply focused domain expert, maintains isolated independent silos, ingests at a steady pace, and explores high novelty.' },
                { code: 'BIVR', name: 'Cyclone Curator', desc: 'Saves widely, maintains isolated independent silos, ingests at high velocity, and reinforces routine expertise.' },
                { code: 'FIVR', name: 'Sentinel Core', desc: 'Deeply focused domain expert, maintains isolated independent silos, ingests at high velocity, and reinforces routine expertise.' },
                { code: 'BISR', name: 'Silent Librarian', desc: 'Saves widely, maintains isolated independent silos, ingests at a steady pace, and reinforces routine expertise.' },
                { code: 'FISR', name: 'Singular Vault', desc: 'Deeply focused domain expert, maintains isolated independent silos, ingests at a steady pace, and reinforces routine expertise.' }
              ];
              const selectedArch = DIRECTORY_ARCHETYPES.find(a => a.code === selectedSig) || DIRECTORY_ARCHETYPES[0];

              return (
                <div className="codex-grid">
                  {/* Left Pane: Selection Menu */}
                  <div className="codex-sidebar">
                    {DIRECTORY_ARCHETYPES.map((arch) => {
                      const isActive = selectedSig === arch.code;
                      return (
                        <div 
                          key={arch.code} 
                          className={`codex-item ${isActive ? 'active' : ''}`}
                          onClick={() => setSelectedSig(arch.code)}
                        >
                          <span className="codex-item-name">{arch.name}</span>
                          <span className="codex-item-code">{arch.code}</span>
                        </div>
                      );
                    })}
                  </div>

                  {/* Right Pane: Codex Viewer */}
                  <div className="codex-viewer">
                    <div className="hud-scanline" />
                    
                    {/* Real-time Constellation Representation */}
                    <div style={{ marginBottom: '1.5rem', display: 'flex', justifyContent: 'center' }}>
                      <CognitiveAvatar signature={selectedSig} size={150} />
                    </div>
                    
                    <h3 style={{ fontFamily: 'var(--font-display)', color: '#ffffff', fontSize: '1.4rem', fontWeight: 700, margin: '0 0 0.5rem 0' }}>
                      {selectedArch.name}
                    </h3>
                    
                    <span style={{ 
                      fontFamily: 'var(--font-mono)', 
                      fontSize: '0.72rem', 
                      color: 'var(--accent-gold)', 
                      background: 'rgba(207, 163, 101, 0.1)', 
                      padding: '4px 10px', 
                      borderRadius: '12px',
                      letterSpacing: '0.05em',
                      marginBottom: '1rem',
                      display: 'inline-block'
                    }}>
                      FORMULA: {selectedSig.split('').join(' · ')}
                    </span>
                    
                    <p style={{ 
                      fontSize: '0.85rem', 
                      color: 'var(--text-muted)', 
                      lineHeight: 1.6, 
                      margin: '0 0 1.5rem 0',
                      maxWidth: '420px'
                    }}>
                      {selectedArch.desc}
                    </p>


                {/* Cognitive breakdown list */}
                <div style={{ 
                  display: 'grid', 
                  gridTemplateColumns: 'repeat(2, 1fr)', 
                  gap: '0.75rem', 
                  width: '100%',
                  maxWidth: '420px',
                  textAlign: 'left',
                  borderTop: '1px solid rgba(255, 255, 255, 0.05)',
                  paddingTop: '1.25rem'
                }}>
                  <div style={{ fontSize: '0.75rem' }}>
                    <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '0.65rem', fontFamily: 'var(--font-mono)' }}>BREADTH</span>
                    <strong style={{ color: '#ffffff' }}>{selectedSig[0] === 'B' ? 'Domain Spreader (B)' : 'Deep Focus (F)'}</strong>
                  </div>
                  <div style={{ fontSize: '0.75rem' }}>
                    <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '0.65rem', fontFamily: 'var(--font-mono)' }}>SYNTHESIS</span>
                    <strong style={{ color: '#ffffff' }}>{selectedSig[1] === 'L' ? 'Active Linker (L)' : 'Silo Specialist (I)'}</strong>
                  </div>
                  <div style={{ fontSize: '0.75rem' }}>
                    <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '0.65rem', fontFamily: 'var(--font-mono)' }}>VELOCITY</span>
                    <strong style={{ color: '#ffffff' }}>{selectedSig[2] === 'V' ? 'High Ingestor (V)' : 'Steady Curator (S)'}</strong>
                  </div>
                  <div style={{ fontSize: '0.75rem' }}>
                    <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '0.65rem', fontFamily: 'var(--font-mono)' }}>EXPLORATION</span>
                    <strong style={{ color: '#ffffff' }}>{selectedSig[3] === 'N' ? 'Novelty Seeker (N)' : 'Routine Builder (R)'}</strong>
                  </div>
                </div>
                  </div>
                </div>
              );
            })()}
            
            <div style={{ 
              marginTop: '2rem', 
              borderTop: '1px solid rgba(207, 163, 101, 0.15)', 
              paddingTop: '1.25rem',
              display: 'flex',
              flexDirection: 'column',
              gap: '1rem'
            }}>
              <h4 style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--accent-gold)', margin: 0, textTransform: 'uppercase', letterSpacing: '0.1em' }}>
                The 4 Cognitive Dimensions Reference
              </h4>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '1rem', fontSize: '0.78rem', color: 'var(--text-muted)', lineHeight: 1.45 }}>
                <div>
                  <strong style={{ color: '#ffffff' }}>Breadth (B/F):</strong> Entropy threshold is 1.20. High score indicates broad multi-domain exploration, low indicates high-density focal clusters.
                </div>
                <div>
                  <strong style={{ color: '#ffffff' }}>Linkage (L/I):</strong> Cross-hub ratio threshold is 0.20. High score indicates inter-topic conceptual bridges, low indicates modular compartmentalization.
                </div>
                <div>
                  <strong style={{ color: '#ffffff' }}>Velocity (V/S):</strong> Weekly saves target is 10. High score indicates swift ingestion rate, low indicates highly stable curation.
                </div>
                <div>
                  <strong style={{ color: '#ffffff' }}>Novelty (N/R):</strong> New-concept distance threshold is 0.35. High score indicates active exploration of foreign domains, low indicates routine reinforcement.
                </div>
              </div>
            </div>

          </div>
        </div>
      )}
    </div>
  );
}
