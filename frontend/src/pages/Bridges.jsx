import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { 
  UserPlus, Key, Eye, Trash, ArrowLeft, ChartBar, SealCheck, Lock, ClockCounterClockwise
} from '@phosphor-icons/react';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls, Html, Line } from '@react-three/drei';
// Stubs to bypass R3F version reconciler crashes
const EffectComposer = ({ children }) => <group>{children}</group>;
const Bloom = () => null;
import * as THREE from 'three';
import gsap from 'gsap';
import AudioEngine from '../utils/AudioEngine';

/* ── Custom SVGs ────────────────────────────────────────────────────────── */
const GitCompare = ({ size = 20, color = 'currentColor' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="18" cy="18" r="3" />
    <circle cx="6" cy="6" r="3" />
    <path d="M13 6h3a2 2 0 0 1 2 2v7" />
    <path d="M11 18H8a2 2 0 0 1-2-2V9" />
  </svg>
);

const Sparkles = ({ size = 20, color = 'currentColor', className = "" }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <path d="M12 3v3m0 12v3M5.6 5.6l2.1 2.1m8.6 8.6l2.1 2.1M3 12h3m12 0h3M5.6 18.4l2.1-2.1m8.6-8.6l2.1-2.1" />
  </svg>
);

/* Palette Colors */
const COLOR_GOLD = '#d4af37';
const COLOR_CERAMIC_WARM = '#d8cca3'; // Glazed Ochre
const COLOR_CERAMIC_WHITE = '#3e3a36'; // Dark Basalt/Slate
const COLOR_GLOW_AMBER = '#a68c5b';
const COLOR_BARK = '#a39785'; // Travertine/Alabaster Limestone
const COLOR_CHARCOAL = '#070709';

export default function Bridges() {
  const [unlocked, setUnlocked] = useState(false);
  const [itemCount, setItemCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [bridges, setBridges] = useState([]);
  const [selectedBridgeId, setSelectedBridgeId] = useState(null);
  const [bridgeDetails, setBridgeDetails] = useState(null);
  const [detailsLoading, setDetailsLoading] = useState(false);
  
  // Connection states
  const [inviteCode, setInviteCode] = useState('');
  const [generatedCode, setGeneratedCode] = useState('');
  const [connecting, setConnecting] = useState(false);
  const [connectionSuccess, setConnectionSuccess] = useState(false);
  
  // Active selected matched card inside 3D Canvas
  const [activeSynapseIdx, setActiveSynapseIdx] = useState(null);

  // Ceremony / Cairn States
  const [ceremonyStarted, setCeremonyStarted] = useState(false);
  const [activeNode, setActiveNode] = useState(null);
  const [animationDone, setAnimationDone] = useState(false);
  const [skipTriggered, setSkipTriggered] = useState(false);
  const [overlayText, setOverlayText] = useState('');
  const [subOverlayText, setSubOverlayText] = useState('');

  // Audio helper
  const playSound = (type) => {
    try {
      if (type === 'click') AudioEngine.playClick();
      else if (type === 'transition') AudioEngine.playTransition();
    } catch (e) {
      console.warn('Audio play failed:', e);
    }
  };

  /* ── Load initial details ───────────────────────────────────────────────── */
  const fetchData = useCallback(async () => {
    try {
      const meRes = await fetch('/api/me');
      if (meRes.ok) {
        const meData = await meRes.json();
        const savesCount = meData.total_saves || 0;
        setItemCount(savesCount);
        if (savesCount >= 50) setUnlocked(true);
      }

      const bridgesRes = await fetch('/api/bridges');
      if (bridgesRes.ok) {
        const list = await bridgesRes.json();
        setBridges(list);
      }
    } catch (err) {
      console.error('Failed to load bridges:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  /* ── Create invite code ─────────────────────────────────────────────────── */
  const generateCode = async () => {
    playSound('click');
    try {
      const res = await fetch('/api/bridges/invite', { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        setGeneratedCode(data.invite_code);
      }
    } catch (e) {
      console.error('Failed to generate invite code:', e);
    }
  };

  /* ── Connect code ───────────────────────────────────────────────────────── */
  const connectLink = async (e) => {
    e.preventDefault();
    if (!inviteCode.trim()) return;
    playSound('click');
    setConnecting(true);
    
    try {
      const res = await fetch('/api/bridges/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ invite_code: inviteCode.trim() })
      });
      
      if (res.ok) {
        setConnectionSuccess(true);
        playSound('transition');
        setTimeout(() => {
          setConnectionSuccess(false);
          setInviteCode('');
          fetchData();
        }, 3200);
      } else {
        const err = await res.json();
        alert(err.detail || 'Connection failed.');
      }
    } catch (e) {
      console.error('Connection failed:', e);
    } finally {
      setConnecting(false);
    }
  };

  /* ── Get bridge details ─────────────────────────────────────────────────── */
  const selectBridge = async (bridgeId) => {
    playSound('click');
    setSelectedBridgeId(bridgeId);
    setDetailsLoading(true);
    
    try {
      const res = await fetch(`/api/bridges/${bridgeId}`);
      if (res.ok) {
        const data = await res.json();
        setBridgeDetails(data);
        setActiveSynapseIdx(null);
        setAnimationDone(false);
        setSkipTriggered(false);
        setCeremonyStarted(true);
      }
    } catch (err) {
      console.error('Failed to load bridge details:', err);
    } finally {
      setDetailsLoading(false);
    }
  };

  const skipAnimation = () => {
    playSound('click');
    setSkipTriggered(true);
    setAnimationDone(true);
    if (selectedBridgeId) {
      fetch(`/api/bridges/${selectedBridgeId}/ceremony`, { method: 'POST' })
        .catch(err => console.warn("Failed to update ceremony timestamp on skip:", err));
    }
  };

  /* ── Dissolve connection ────────────────────────────────────────────────── */
  const deleteBridge = async (bridgeId) => {
    if (!confirm('Dissolve this cognitive bridge?')) return;
    playSound('click');
    try {
      const res = await fetch(`/api/bridges/${bridgeId}`, { method: 'DELETE' });
      if (res.ok) {
        setSelectedBridgeId(null);
        setBridgeDetails(null);
        fetchData();
      }
    } catch (e) {
      console.error('Failed to dissolve bridge:', e);
    }
  };

  /* Loading State */
  if (loading) {
    return (
      <div className="br-obsidian-loader">
        <ClockCounterClockwise size={32} className="spin-loader" />
        <div className="loader-lbl">CONNECTING TO OBSERVED MIND...</div>
      </div>
    );
  }

  /* Locked Milestone Screen */
  if (!unlocked) {
    const progress = Math.min(100, (itemCount / 50) * 100);
    return (
      <div className="br-locked-viewport">
        <style>{stylesCss}</style>
        <div className="starfield-bg" />
        <div className="br-locked-card">
          <div className="lock-avatar">
            <Lock size={32} color="var(--accent-gold)" />
          </div>
          <h1 className="locked-card-title">COGNITIVE COMPATIBILITY</h1>
          <p className="locked-card-desc">
            Unlock neural sharing links to blend mental maps, compare specialties, and calculate overlap indices. 
          </p>
          <div className="progress-meter">
            <div className="progress-meter-hdr">
              <span>Saves mapped</span>
              <span>{itemCount} / 50</span>
            </div>
            <div className="progress-meter-track">
              <div className="progress-meter-fill" style={{ width: `${progress}%` }} />
            </div>
          </div>
          <div className="locked-footer-alert">
            <span className="alert-dot" />
            COMPATIBILITY CHANNEL SHIELD ACTIVE
          </div>
        </div>
      </div>
    );
  }

  /* ── Observatory View: Dual Mycelium Root Network ──────────────────────── */
  if (selectedBridgeId) {
    const activeSynapse = activeSynapseIdx !== null ? bridgeDetails?.synapses?.[activeSynapseIdx] : null;

    const isResting = ceremonyStarted && animationDone;

    return (
      <div className="br-observatory-view-fullscreen" style={{ background: '#0D0B09' }}>
        <style>{stylesCss}</style>
        
        {/* Navigation control rail */}
        {isResting && (
          <div className="obs-header" style={{
          height: '64px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0 2rem',
          borderBottom: '1px solid #1E1810',
          background: '#0D0B09',
          boxSizing: 'border-box',
          zIndex: 100
        }}>
          <button className="obs-back-btn" onClick={() => { playSound('click'); setSelectedBridgeId(null); setBridgeDetails(null); setActiveSynapseIdx(null); }} style={{
            background: 'none',
            border: 'none',
            outline: 'none',
            color: '#5A4A32',
            fontFamily: 'var(--font-mono)',
            fontSize: '7px',
            letterSpacing: '0.15em',
            display: 'flex',
            alignItems: 'center',
            gap: '8px'
          }}>
            <ArrowLeft size={10} style={{ color: '#C8841A' }} />
            <span>DISMISS OBSERVATION</span>
          </button>
          
          <div className="obs-title-wrap" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.1rem' }}>
            <div className="obs-badge" style={{ fontFamily: 'var(--font-mono)', fontSize: '7px', letterSpacing: '0.15em', color: '#4A3A22' }}>INTERFERENCE PATTERN</div>
            <h1 className="obs-title" style={{ fontFamily: '"Cormorant Garamond", serif', fontSize: '20px', fontWeight: 'normal', color: '#E8DEC8', margin: 0 }}>
              {bridgeDetails ? bridgeDetails.friend_name.toUpperCase() : '...' } <span style={{ color: '#C8841A', fontSize: '22px', margin: '0 4px', verticalAlign: 'middle' }}>&times;</span> COGNITIVE BLEND
            </h1>
          </div>

          <button className="obs-dissolve-btn" onClick={() => deleteBridge(selectedBridgeId)} style={{
            background: 'none',
            border: 'none',
            outline: 'none',
            color: '#5A4A32',
            fontFamily: 'var(--font-mono)',
            fontSize: '7px',
            letterSpacing: '0.15em',
            display: 'flex',
            alignItems: 'center',
            gap: '8px'
          }}>
            <Trash size={10} style={{ color: '#C8841A' }} />
            <span>DISSOLVE</span>
          </button>
        </div>
        )}

        {detailsLoading || !bridgeDetails ? (
          <div className="obs-details-loader" style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '1rem', background: '#0D0B09' }}>
            <ClockCounterClockwise size={32} className="spin-loader" />
            <div className="loader-lbl">INTERWEAVING NEURAL PATHWAYS...</div>
          </div>
        ) : (
          <div className="obs-editorial-layout slide-in-view" style={{
            display: 'flex',
            flex: 1,
            width: '100%',
            height: isResting ? 'calc(100vh - 64px)' : '100vh',
            position: 'relative'
          }}>
            
            {/* LEFT STRIP (64px wide, vertical) */}
            {isResting && (
              <div style={{
              width: '64px',
              height: '100%',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              paddingTop: '2rem',
              background: '#0D0B09',
              borderRight: '1px solid #1E1810',
              boxSizing: 'border-box',
              zIndex: 10
            }}>
              {/* Matte ceramic disc monogram */}
              <div style={{
                width: '32px',
                height: '32px',
                borderRadius: '50%',
                background: '#E8E0D4',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#0D0B09',
                fontSize: '10px',
                fontWeight: 'bold',
                fontFamily: 'var(--font-mono)',
                marginBottom: '2.5rem'
              }}>
                {bridgeDetails ? bridgeDetails.user_mind_type?.slice(0, 2).toUpperCase() || 'ME' : 'ME'}
              </div>
              
              {/* Rotated label "YOUR ARCHIVE" */}
              <div style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '7px',
                letterSpacing: '0.15em',
                color: '#5A4A32',
                textTransform: 'uppercase',
                writingMode: 'vertical-lr',
                transform: 'rotate(180deg)',
                whiteSpace: 'nowrap'
              }}>
                YOUR ARCHIVE
              </div>
            </div>
            )}

            {/* CENTER CANVAS (fills remaining left ~65% of screen) */}
            <div style={{
              flex: isResting ? '1 1 65%' : '1 1 100%',
              height: '100%',
              position: 'relative',
              overflow: 'hidden',
              background: '#0D0B09'
            }}>
              {ceremonyStarted && (
                <Canvas
                  shadows
                  camera={{ position: [0, 2, 8], fov: 40 }}
                  style={{ width: '100%', height: '100%', display: 'block', background: '#0D0B09' }}
                  gl={{ preserveDrawingBuffer: true }}
                >
                  <color attach="background" args={["#0D0B09"]} />
                  <fogExp2 attach="fog" color="#0D0B09" density={0.035} />
                  
                  <CairnScene 
                    bridgeDetails={bridgeDetails}
                    animationDone={animationDone}
                    setAnimationDone={setAnimationDone}
                    activeNode={activeNode}
                    setActiveNode={setActiveNode}
                    setActiveSynapseIdx={setActiveSynapseIdx}
                    skipTriggered={skipTriggered}
                    setSkipTriggered={setSkipTriggered}
                    playSound={playSound}
                    selectedBridgeId={selectedBridgeId}
                    setOverlayText={setOverlayText}
                    setSubOverlayText={setSubOverlayText}
                  />
                </Canvas>
              )}

              {/* SKIP REPLAY BUTTON */}
              {ceremonyStarted && !animationDone && (
                <button 
                  onClick={skipAnimation}
                  style={{
                    position: 'absolute',
                    top: '24px',
                    right: '24px',
                    zIndex: 250,
                    background: 'rgba(13, 11, 9, 0.75)',
                    border: '1px solid rgba(200, 132, 26, 0.4)',
                    padding: '8px 16px',
                    fontFamily: 'var(--font-mono)',
                    fontSize: '8px',
                    letterSpacing: '0.15em',
                    color: '#E8DEC8',
                    cursor: 'pointer',
                    borderRadius: '2px',
                    pointerEvents: 'auto',
                    transition: 'all 0.2s'
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.borderColor = '#C8841A'; }}
                  onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'rgba(200, 132, 26, 0.4)'; }}
                >
                  SKIP REPLAY
                </button>
              )}

              {/* BOTTOM LEFT PERSISTENT WEAKENED INDICATOR */}
              {isResting && bridgeDetails?.synapses?.filter(s => s.decay_stage !== 'STABLE').length > 0 && (
                <button
                  onClick={() => {
                    playSound('click');
                    const damaged = bridgeDetails.synapses.filter(s => s.decay_stage !== 'STABLE');
                    const currentIdx = window.lastDamageCycleIdx || 0;
                    const nextIdx = currentIdx + 1;
                    window.lastDamageCycleIdx = nextIdx;
                    
                    const targetSyn = damaged[currentIdx % damaged.length];
                    const globalIdx = bridgeDetails.synapses.indexOf(targetSyn);
                    
                    setActiveNode({
                      id: `A-shared-${globalIdx}`,
                      title: targetSyn.item_a.title,
                      summary: targetSyn.item_a.summary,
                      side: 'A',
                      type: 'shared',
                      synapseIdx: globalIdx
                    });
                    setActiveSynapseIdx(globalIdx);
                    AudioEngine.playDissonantTone();
                  }}
                  style={{
                    position: 'absolute',
                    bottom: '24px',
                    left: '24px',
                    zIndex: 250,
                    background: 'rgba(13, 11, 9, 0.75)',
                    border: '1px solid #A65b5b',
                    padding: '6px 12px',
                    fontFamily: 'var(--font-mono)',
                    fontSize: '7px',
                    letterSpacing: '0.1em',
                    color: '#A65b5b',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    borderRadius: '1px',
                    pointerEvents: 'auto',
                    transition: 'all 0.2s'
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(166, 91, 91, 0.1)'; }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = 'rgba(13, 11, 9, 0.75)'; }}
                >
                  <span style={{ 
                    display: 'inline-block', 
                    width: '4px', 
                    height: '4px', 
                    borderRadius: '50%', 
                    background: '#A65b5b',
                    boxShadow: '0 0 4px #A65b5b'
                  }} />
                  {bridgeDetails.synapses.filter(s => s.decay_stage !== 'STABLE').length} STONES CRACKED / WEAKENED
                </button>
              )}

              {/* BOTTOM CENTER DYNAMIC TEXT OVERLAYS */}
              {overlayText && (
                <div style={{
                  position: 'absolute',
                  bottom: '12%',
                  left: 0,
                  right: 0,
                  textAlign: 'center',
                  pointerEvents: 'none',
                  zIndex: 200,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '6px'
                }}>
                  <div style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: '8px',
                    letterSpacing: '0.2em',
                    color: '#C8841A',
                    textTransform: 'uppercase'
                  }}>
                    {overlayText}
                  </div>
                  {subOverlayText && (
                    <div style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: '7px',
                      letterSpacing: '0.15em',
                      color: '#4A3A22',
                      textTransform: 'uppercase'
                    }}>
                      {subOverlayText}
                    </div>
                  )}
                </div>
              )}
            </div>
            
            {/* RIGHT PANEL (35% width, full height, border-left 1px solid #1E1810) */}
            {isResting && (
              <div className="obs-editorial-sidebar" style={{
                width: '35%',
              minWidth: '320px',
              height: '100%',
              borderLeft: '1px solid #1E1810',
              background: '#100E0B',
              overflow: 'hidden',
              position: 'relative',
              boxSizing: 'border-box'
            }}>
              {/* Slide Container */}
              <div style={{
                display: 'flex',
                width: '200%',
                height: '100%',
                transform: activeSynapseIdx !== null ? 'translateX(-50%)' : 'translateX(0)',
                transition: 'transform 240ms cubic-bezier(0.16, 1, 0.3, 1)'
              }}>
                {/* PANEL A: DEFAULT STATE */}
                <div style={{
                  width: '50%',
                  height: '100%',
                  display: 'flex',
                  flexDirection: 'column',
                  padding: '2.5rem 2rem',
                  boxSizing: 'border-box',
                  overflowY: 'auto'
                }}>
                  {/* Top section: MUTUAL OVERLAP INDEX */}
                  <div style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: '7px',
                    letterSpacing: '0.15em',
                    color: '#4A3A22',
                    textTransform: 'uppercase',
                    marginBottom: '0.5rem'
                  }}>
                    MUTUAL OVERLAP INDEX
                  </div>

                  {/* Overlap Percentage Large treated numeral */}
                  <div style={{
                    display: 'flex',
                    alignItems: 'baseline',
                    fontFamily: '"Cormorant Garamond", serif',
                    color: '#C8841A',
                    marginBottom: '1rem',
                    lineHeight: 1
                  }}>
                    <span style={{ fontSize: '72px', fontWeight: '300' }}>
                      {Math.floor(bridgeDetails.compatibility_score || 0)}
                    </span>
                    <span style={{ fontSize: '32px', fontWeight: '300' }}>
                      .{Math.round(((bridgeDetails.compatibility_score || 0) % 1) * 10)}
                    </span>
                    <span style={{ fontSize: '48px', fontWeight: '300', marginLeft: '2px' }}>
                      %
                    </span>
                  </div>

                  {/* Restrained horizontal amber line */}
                  <div style={{
                    width: '32px',
                    height: '1px',
                    background: '#C8841A',
                    marginBottom: '0.75rem'
                  }} />

                  {/* Explanatory metric sub-label to resolve data score mismatch */}
                  <div style={{
                    fontFamily: 'var(--font-sans)',
                    fontSize: '10px',
                    color: '#6E5D4B',
                    lineHeight: '1.45',
                    marginBottom: '1.25rem',
                    maxWidth: '280px'
                  }}>
                    * Overall overlap represents the average similarity across your top 15 shared cognitive facets. Individual matched facets are listed below.
                  </div>

                  {/* Interpretive text */}
                  <p style={{
                    fontFamily: '"Cormorant Garamond", serif',
                    fontStyle: 'italic',
                    fontSize: '13px',
                    color: '#8A7560',
                    lineHeight: '1.4',
                    margin: '0 0 2rem 0'
                  }}>
                    {getInterpretiveText(bridgeDetails.compatibility_score)}
                  </p>

                  {/* 1px divider */}
                  <div style={{
                    width: '100%',
                    height: '1px',
                    background: '#1E1810',
                    marginBottom: '1.5rem'
                  }} />

                  {/* FACET LIST */}
                  <div style={{
                    display: 'flex',
                    flexDirection: 'column',
                    flex: 1
                  }}>
                    {bridgeDetails.synapses.map((syn, idx) => (
                      <div 
                        key={idx}
                        className="facet-row-item"
                        onClick={() => {
                          playSound('click');
                          setActiveSynapseIdx(idx);
                        }}
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          padding: '1rem 0.5rem',
                          borderBottom: '1px solid #1E1810',
                          cursor: 'pointer',
                          position: 'relative',
                          transition: 'background-color 0.2s'
                        }}
                      >
                        {/* 1px Left Accent Bar */}
                        <div className="hover-accent-bar" style={{
                          position: 'absolute',
                          left: 0,
                          top: 0,
                          bottom: 0,
                          width: '1px',
                          background: '#C8841A',
                          opacity: 0,
                          transition: 'opacity 0.2s'
                        }} />

                        <span style={{
                          fontFamily: 'var(--font-mono)',
                          fontSize: '7px',
                          letterSpacing: '0.15em',
                          color: '#4A3A22'
                        }}>
                          FACET 0{idx + 1}
                        </span>
                        
                        <span style={{
                          fontFamily: 'var(--font-mono)',
                          fontSize: '7px',
                          letterSpacing: '0.15em',
                          color: '#4A3A22'
                        }}>
                          {Math.round(syn.similarity * 100)}% MATCH
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* PANEL B: SELECTED STATE */}
                <div style={{
                  width: '50%',
                  height: '100%',
                  display: 'flex',
                  flexDirection: 'column',
                  padding: '2.5rem 2rem',
                  boxSizing: 'border-box',
                  overflowY: 'auto'
                }}>
                  {activeSynapse && (
                    <>
                      {/* YOUR MAP SOURCE */}
                      <div style={{ marginBottom: '1.5rem' }}>
                        <div style={{
                          fontFamily: 'var(--font-mono)',
                          fontSize: '7px',
                          letterSpacing: '0.15em',
                          color: '#C8841A',
                          textTransform: 'uppercase',
                          marginBottom: '0.5rem'
                        }}>
                          YOUR MAP SOURCE
                        </div>
                        <h3 style={{
                          fontFamily: '"Cormorant Garamond", serif',
                          fontSize: '18px',
                          fontWeight: 'normal',
                          color: '#E8DEC8',
                          lineHeight: '1.3',
                          margin: '0 0 0.5rem 0'
                        }}>
                          {activeSynapse.item_a?.title || "Untitled Link"}
                        </h3>
                        <p style={{
                          fontFamily: '"DM Sans", sans-serif',
                          fontSize: '11px',
                          color: '#7A6A52',
                          lineHeight: '1.45',
                          margin: 0,
                          display: '-webkit-box',
                          WebkitLineClamp: 4,
                          WebkitBoxOrient: 'vertical',
                          overflow: 'hidden'
                        }}>
                          {activeSynapse.item_a?.summary || "Concept nodes saved in the observatory cortex."}
                        </p>
                      </div>

                      {/* 1px divider */}
                      <div style={{
                        width: '100%',
                        height: '1px',
                        background: '#1E1810',
                        marginBottom: '1.5rem'
                      }} />

                      {/* AETHER LINK'S SOURCE */}
                      <div style={{ marginBottom: '1.5rem' }}>
                        <div style={{
                          fontFamily: 'var(--font-mono)',
                          fontSize: '7px',
                          letterSpacing: '0.15em',
                          color: '#C8841A',
                          textTransform: 'uppercase',
                          marginBottom: '0.5rem'
                        }}>
                          AETHER LINK'S SOURCE
                        </div>
                        <h3 style={{
                          fontFamily: '"Cormorant Garamond", serif',
                          fontSize: '18px',
                          fontWeight: 'normal',
                          color: '#E8DEC8',
                          lineHeight: '1.3',
                          margin: '0 0 0.5rem 0'
                        }}>
                          {activeSynapse.item_b?.title || "Untitled Link"}
                        </h3>
                        <p style={{
                          fontFamily: '"DM Sans", sans-serif',
                          fontSize: '11px',
                          color: '#7A6A52',
                          lineHeight: '1.45',
                          margin: 0,
                          display: '-webkit-box',
                          WebkitLineClamp: 4,
                          WebkitBoxOrient: 'vertical',
                          overflow: 'hidden'
                        }}>
                          {activeSynapse.item_b?.summary || "Concept nodes matched from friend's memory indices."}
                        </p>
                      </div>

                      {/* 1px divider */}
                      <div style={{
                        width: '100%',
                        height: '1px',
                        background: '#1E1810',
                        marginBottom: '1.5rem'
                      }} />

                      {/* COGNITIVE SYNERGY */}
                      <div style={{ marginBottom: '2rem' }}>
                        <div style={{
                          fontFamily: 'var(--font-mono)',
                          fontSize: '7px',
                          letterSpacing: '0.15em',
                          color: '#C8841A',
                          textTransform: 'uppercase',
                          marginBottom: '0.5rem'
                        }}>
                          COGNITIVE SYNERGY
                        </div>
                        <p style={{
                          fontFamily: '"DM Sans", sans-serif',
                          fontSize: '11px',
                          color: '#7A6A52',
                          lineHeight: '1.45',
                          margin: 0
                        }}>
                          This node pair exhibits a similarity score of {Math.round(activeSynapse.similarity * 100)}%. It represents a shared node of thought, linking concept models across both repositories.
                        </p>
                      </div>

                      {/* Back to pool link */}
                      <button 
                        onClick={() => {
                          playSound('click');
                          setActiveSynapseIdx(null);
                        }}
                        style={{
                          alignSelf: 'flex-start',
                          background: 'none',
                          border: 'none',
                          outline: 'none',
                          padding: 0,
                          cursor: 'pointer',
                          fontFamily: 'var(--font-mono)',
                          fontSize: '7px',
                          letterSpacing: '0.15em',
                          color: '#C8841A',
                          textTransform: 'uppercase',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '4px',
                          marginTop: 'auto'
                        }}
                      >
                        ← BACK TO POOL
                      </button>
                    </>
                  )}
                </div>
              </div>
            </div>
            )}
          </div>
        )}
      </div>
    );
  }

  /* ── Master List View ──────────────────────────────────────────────────── */
  return (
    <div className="br-observatory-view">
      <style>{stylesCss}</style>
      <div className="obs-main-deck slide-in-view">
        
        {/* Holographic Console Panel */}
        <div className="obs-console-sidebar">
          <div className="obs-glass-box console-box">
            <h2 className="console-title">NEURAL LINK GATEWAY</h2>
            <p className="console-desc">
              Establish a secure bridge overlay by generating an invite code or claiming a friend's connection code.
            </p>
            
            <div className="console-divider" />
            
            {/* Generate box */}
            <div className="console-action-block">
              <button className="console-primary-btn" onClick={generateCode}>
                <UserPlus size={14} />
                <span>Generate Invite Code</span>
              </button>
              {generatedCode && (
                <div className="console-code-output">
                  <span className="code-text">{generatedCode}</span>
                  <button 
                    className="code-copy-btn" 
                    onClick={() => { 
                      navigator.clipboard.writeText(generatedCode); 
                      playSound('click'); 
                    }}
                  >
                    COPY
                  </button>
                </div>
              )}
            </div>

            <div className="console-divider" />

            {/* Connect code */}
            <form onSubmit={connectLink} className="console-connect-form">
              <div className="console-input-label">CLAIM TUNNEL TOKEN</div>
              <div className="console-input-wrapper">
                <input 
                  type="text" 
                  value={inviteCode} 
                  onChange={(e) => setInviteCode(e.target.value.toUpperCase())}
                  placeholder="MIND-XXXX-XXXX" 
                  className="console-token-input"
                />
                <button type="submit" className="console-submit-btn" disabled={connecting}>
                  {connecting ? 'LINKING...' : 'CONNECT'}
                </button>
              </div>
            </form>
          </div>

          <div className="obs-privacy-shield">
            <Lock size={12} style={{ color: 'rgba(255,255,255,0.3)', marginRight: 6 }} />
            <span>Strict Zero-Knowledge Analytics. Raw saved files are never shared or readable.</span>
          </div>
        </div>

        {/* Mapped bridges deck */}
        <div className="obs-bridges-deck">
          <h2 className="obs-section-title">ACTIVE NEURAL OVERLAYS</h2>
          {bridges.length === 0 ? (
            <div className="obs-empty-deck">
              <div className="obs-empty-orb" />
              <div className="obs-empty-title">NO ACTIVE OVERLAYS</div>
              <p className="obs-empty-desc">Blends of your mapped concept indices with friends will appear here.</p>
            </div>
          ) : (
            <div className="obs-cards-layout-grid">
              {bridges.map(br => {
                const colors = getArchetypeGradient(br.friend_mind_type);
                return (
                  <div 
                    key={br.id}
                    className="obs-deck-card"
                    onClick={() => selectBridge(br.id)}
                  >
                    <div className="card-glow-back" style={{ background: colors.bg }} />
                    <div className="card-obs-glass">
                      <div className="card-obs-top">
                        <div className="avatar-shield" style={{ background: colors.bg, color: colors.text }}>
                          {br.friend_initials}
                        </div>
                        <div className="avatar-meta">
                          <div className="meta-name">{br.friend_name}</div>
                          <div className="meta-type">Archetype: {br.friend_mind_type || 'UNKNOWN'}</div>
                        </div>
                        <div className="meta-readout">
                          <span className="readout-val">{Math.round(br.compatibility_score)}%</span>
                          <span className="readout-lbl">OVERLAP</span>
                        </div>
                      </div>
                      <div className="card-obs-footer">
                        <span>DECODE NEURAL OVERLAP</span>
                        <GitCompare size={12} color="var(--accent-gold)" />
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Success quantum gateway animation loop */}
      {connectionSuccess && (
        <div className="obs-success-modal">
          <div className="obs-success-card">
            <SealCheck size={64} color="#00f0ff" className="br-success-zoom-icon" />
            <h2 className="obs-success-title">COGNITIVE TUNNEL SYNCHRONIZED</h2>
            <p className="obs-success-desc">Neural index coordinates aligned. Syncing semantic horizons...</p>
          </div>
        </div>
      )}
    </div>
  );
}

/* Archetypes color helper */
function getArchetypeGradient(type) {
  if (!type) return { bg: 'rgba(255,255,255,0.06)', text: '#ffffff' };
  const first = type.charAt(0);
  switch (first) {
    case 'F':
      return { bg: 'linear-gradient(135deg, #00f0ff 0%, #0072ff 100%)', text: '#020204' };
    case 'I':
      return { bg: 'linear-gradient(135deg, #ff00ff 0%, #81007f 100%)', text: '#ffffff' };
    case 'V':
      return { bg: 'linear-gradient(135deg, #ffaa00 0%, #993300 100%)', text: '#020204' };
    default:
      return { bg: 'linear-gradient(135deg, #f4f1ea 0%, #8fa382 100%)', text: '#020204' };
  }
}


/* ── GROUND EARTH DISC ─────────────────────────────────────────── */

function GroundPlane() {
  
  const groundGeometry = useMemo(() => {
    const geo = new THREE.CircleGeometry(3, 64);
    const posAttr = geo.attributes.position;
    const v = new THREE.Vector3();
    for (let i = 0; i < posAttr.count; i++) {
      v.fromBufferAttribute(posAttr, i);
      const distFromCenter = Math.sqrt(v.x * v.x + v.y * v.y);
      if (distFromCenter > 0.1) {
        const edgeFactor = Math.max(0, 1 - distFromCenter / 3);
        const noise = (seededRandom(v.x * 15 + v.y * 23) - 0.5) * 0.04 * edgeFactor;
        v.z += noise;
      }
      posAttr.setXYZ(i, v.x, v.y, v.z);
    }
    geo.computeVertexNormals();
    return geo;
  }, []);

  return (
    <mesh geometry={groundGeometry} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
      <meshStandardMaterial color="#1A1510" roughness={0.95} metalness={0.02} />
    </mesh>
  );
}

/* ── CAIRN INSTANCED BASE FOR SCALING STACK ────────────────────── */

function CairnInstancedBase({ stones }) {
  const instancedRef = useRef();
  
  const baseGeometry = useMemo(() => {
    const geo = new THREE.IcosahedronGeometry(1, 1);
    const pos = geo.attributes.position;
    const v = new THREE.Vector3();
    for (let i = 0; i < pos.count; i++) {
      v.fromBufferAttribute(pos, i);
      const nx = seededRandom(v.x * 15.3 + v.y * 9.2 + v.z * 11.4);
      const norm = v.clone().normalize();
      const disp = (nx - 0.5) * 0.15;
      v.addScaledVector(norm, disp);
      pos.setXYZ(i, v.x, v.y, v.z);
    }
    geo.computeVertexNormals();
    return geo;
  }, []);
  

  
  useEffect(() => {
    if (!instancedRef.current || stones.length === 0) return;
    const tempObject = new THREE.Object3D();
    const tempColor = new THREE.Color();
    
    stones.forEach((stone, idx) => {
      tempObject.position.set(stone.x, stone.y, stone.z);
      tempObject.scale.set(stone.radius * 0.5, stone.radius * stone.scaleY, stone.radius);
      tempObject.rotation.set(stone.rotX, stone.rotY, stone.rotZ);
      tempObject.updateMatrix();
      instancedRef.current.setMatrixAt(idx, tempObject.matrix);
      
      const colorStr = stone.category === 'analytical' ? '#4A4640' : '#8A5A3E';
      tempColor.set(colorStr);
      instancedRef.current.setColorAt(idx, tempColor);
    });
    
    instancedRef.current.instanceMatrix.needsUpdate = true;
    if (instancedRef.current.instanceColor) {
      instancedRef.current.instanceColor.needsUpdate = true;
    }
  }, [stones, baseGeometry]);
  
  if (stones.length === 0) return null;
  
  return (
    <instancedMesh ref={instancedRef} args={[baseGeometry, null, stones.length]} castShadow receiveShadow>
      <meshStandardMaterial roughness={0.82} metalness={0.02} />
    </instancedMesh>
  );
}

/* ── INDIVIDUAL CAIRN STONE ────────────────────────────────────── */

function CairnStone({ 
  stone, 
  index, 
  isNew, 
  isRepairing, 
  localTime, 
  activeNode, 
  setActiveNode, 
  setActiveSynapseIdx, 
  hoveredIdx, 
  setHoveredIdx,
  playSound
}) {
  const meshRef = useRef();
  const leftRef = useRef();
  const rightRef = useRef();
  const fragRef = useRef();
  
  const isHovered = hoveredIdx === index;
  
  let yOffset = 0;
  let opacity = 1;
  let gap = 0;
  let scaleMultiplier = isHovered ? 1.08 : 1.0;
  
  if (isNew) {
    const fallDuration = stone.type === 'foundation' ? 1.4 : 0.9;
    if (localTime < 0) {
      return null;
    } else if (localTime < fallDuration) {
      const progress = localTime / fallDuration;
      const easeInQuad = progress * progress;
      yOffset = 2.0 * (1 - easeInQuad);
      opacity = Math.min(localTime / 0.15, 1);
    } else {
      const bounceTime = localTime - fallDuration;
      if (bounceTime < 0.35) {
        const bounceProgress = bounceTime / 0.35;
        const overshoot = Math.sin(bounceProgress * Math.PI) * 0.06 * Math.exp(-bounceProgress * 4);
        yOffset = -overshoot;
      } else {
        yOffset = 0;
      }
      opacity = 1;
    }
  }

  let baseGap = 0;
  if (stone.decayStage === 'WIDE_CRACK') {
    baseGap = 0.025;
  } else if (stone.decayStage === 'BROKEN') {
    baseGap = 0.05;
  }
  
  if (isRepairing && localTime >= 0 && localTime < 1.8) {
    const progress = localTime / 1.8;
    const prevGap = stone.decayStage === 'STABLE' ? 0.015 : (stone.decayStage === 'WEAKENED' ? 0.015 : (stone.decayStage === 'SMALL_CRACK' ? 0.025 : 0.05));
    gap = prevGap * (1 - progress) + baseGap * progress;
  } else {
    gap = baseGap;
  }

  const isQuartz = stone.isQuartz;
  const category = stone.category;
  
  let baseColor = '#8A5A3E'; 
  let baseRoughness = 0.85;
  let emissiveColor = '#000000';
  let emissiveIntensity = 0.0;
  let metalness = 0.02;
  
  if (isQuartz) {
    baseColor = '#D8CFC0';
    baseRoughness = 0.55;
    emissiveColor = '#C8A97E';
    emissiveIntensity = isHovered ? 0.25 : 0.08;
  } else if (category === 'analytical') {
    baseColor = '#4A4640'; 
    baseRoughness = 0.8;
  }
  
  if (stone.decayStage === 'WEAKENED') {
    const c = new THREE.Color(baseColor);
    const grey = new THREE.Color('#666666');
    c.lerp(grey, 0.15);
    baseColor = '#' + c.getHexString();
    baseRoughness += 0.1;
  }

  useFrame((state) => {
    const t = state.clock.getElapsedTime();
    if (stone.decayStage === 'WIDE_CRACK' && leftRef.current && rightRef.current) {
      const jitterVal = Math.sin(t * 4.5 + index) * 0.004;
      leftRef.current.rotation.y = jitterVal;
      rightRef.current.rotation.y = -jitterVal;
    } else if (stone.decayStage === 'BROKEN' && leftRef.current && rightRef.current) {
      const jitterVal = Math.sin(t * 7.5 + index) * 0.009;
      leftRef.current.rotation.y = jitterVal;
      rightRef.current.rotation.y = -jitterVal;
      if (fragRef.current) {
        fragRef.current.rotation.z = Math.cos(t * 6.5 + index) * 0.012;
      }
    } else {
      if (leftRef.current) leftRef.current.rotation.y = 0;
      if (rightRef.current) rightRef.current.rotation.y = 0;
    }
  });
  
  const radius = stone.radius || 0.4;
  const scaleY = stone.scaleY || 0.6;
  const seed = index * 100 + (category === 'analytical' ? 17 : 43);
  

  
  const leftGeometry = useMemo(() => {
    const geo = new THREE.IcosahedronGeometry(radius, 1);
    const pos = geo.attributes.position;
    const v = new THREE.Vector3();
    for (let i = 0; i < pos.count; i++) {
      v.fromBufferAttribute(pos, i);
      const nx = seededRandom(v.x * 12.1 + v.y * 7.4 + v.z * 18.9 + seed);
      const ny = seededRandom(v.y * 14.3 + v.z * 9.1 + v.x * 11.7 + seed + 1);
      const nz = seededRandom(v.z * 10.9 + v.x * 13.3 + v.y * 6.7 + seed + 2);
      const norm = v.clone().normalize();
      const disp = (nx - 0.5) * 0.15 * radius;
      v.addScaledVector(norm, disp);
      pos.setXYZ(i, v.x, v.y, v.z);
    }
    geo.computeVertexNormals();
    return geo;
  }, [radius, index, category]);

  const handlePointerDown = (e) => {
    e.stopPropagation();
    if (stone.type === 'synapse') {
      setActiveNode({
        id: `A-shared-${stone.synapseIdx}`,
        title: stone.title_a,
        summary: stone.synapse.item_a.summary,
        side: 'A',
        type: 'shared',
        synapseIdx: stone.synapseIdx
      });
      setActiveSynapseIdx(stone.synapseIdx);
    }
  };

  const showDarkSeam = stone.decayStage === 'SMALL_CRACK';
  const showGoldSeam = stone.decayStage === 'STABLE' && stone.hasGoldSeam;
  
  let goldEmissiveIntensity = 0.1;
  if (showGoldSeam && isRepairing && localTime >= 1.8 && localTime <= 2.4) {
    const flareTime = localTime - 1.8;
    const progress = flareTime / 0.6;
    goldEmissiveIntensity = 0.1 + 0.35 * Math.sin(progress * Math.PI);
  }

  const stoneMaterialProps = {
    color: baseColor,
    roughness: baseRoughness,
    metalness: metalness,
    emissive: new THREE.Color(emissiveColor),
    emissiveIntensity: emissiveIntensity
  };

  return (
    <group 
      position={[stone.x, stone.y + yOffset, stone.z]} 
      rotation={[stone.rotX, stone.rotY, stone.rotZ]}
      scale={[scaleMultiplier, scaleMultiplier * scaleY, scaleMultiplier]}
    >
      {/* LEFT HALF */}
      <mesh 
        ref={leftRef}
        geometry={leftGeometry}
        position={[-gap * 0.5, 0, 0]}
        scale={[0.5, 1, 1]}
        castShadow
        receiveShadow
        onPointerOver={(e) => { e.stopPropagation(); setHoveredIdx(index); }}
        onPointerOut={(e) => { e.stopPropagation(); setHoveredIdx(null); }}
        onClick={handlePointerDown}
      >
        <meshStandardMaterial {...stoneMaterialProps} transparent opacity={opacity} />
      </mesh>
      
      {/* RIGHT HALF */}
      <mesh 
        ref={rightRef}
        geometry={leftGeometry}
        position={[gap * 0.5, 0, 0]}
        scale={[0.5, 1, 1]}
        rotation={[0, Math.PI, 0]}
        castShadow
        receiveShadow
        onPointerOver={(e) => { e.stopPropagation(); setHoveredIdx(index); }}
        onPointerOut={(e) => { e.stopPropagation(); setHoveredIdx(null); }}
        onClick={handlePointerDown}
      >
        <meshStandardMaterial {...stoneMaterialProps} transparent opacity={opacity} />
      </mesh>

      {/* THIRD FRAGMENT FOR BROKEN STAGE */}
      {stone.decayStage === 'BROKEN' && (
        <mesh
          ref={fragRef}
          geometry={leftGeometry}
          position={[0, -0.05, radius * 0.45 + gap * 0.7]}
          scale={[0.28, 0.28, 0.28]}
          castShadow
          receiveShadow
          onPointerOver={(e) => { e.stopPropagation(); setHoveredIdx(index); }}
          onPointerOut={(e) => { e.stopPropagation(); setHoveredIdx(null); }}
          onClick={handlePointerDown}
        >
          <meshStandardMaterial {...stoneMaterialProps} transparent opacity={opacity} />
        </mesh>
      )}

      {/* CENTRAL SEAM DECAL */}
      {showDarkSeam && (
        <mesh position={[0, 0, 0]} scale={[0.005, 1.01, 1.01]}>
          <boxGeometry args={[radius * 0.2, radius, radius]} />
          <meshStandardMaterial color="#0A0806" roughness={0.95} metalness={0.02} transparent opacity={opacity} />
        </mesh>
      )}

      {showGoldSeam && (
        <mesh position={[0, 0, 0]} scale={[0.012, 1.03, 1.03]}>
          <boxGeometry args={[radius * 0.15, radius, radius]} />
          <meshStandardMaterial 
            color="#D4AF37" 
            roughness={0.3} 
            metalness={0.65} 
            emissive={new THREE.Color("#C8841A")}
            emissiveIntensity={goldEmissiveIntensity}
            transparent 
            opacity={opacity} 
          />
        </mesh>
      )}

      {/* HOVER TOOLTIP HTML */}
      {isHovered && stone.type === 'synapse' && (
        <Html distanceFactor={3.5} position={[0, radius * 0.7, 0]} style={{ pointerEvents: 'none', zIndex: 100 }}>
          <div style={{
            background: 'rgba(13, 11, 9, 0.96)',
            border: '1px solid #C8841A',
            padding: '6px 12px',
            borderRadius: '1px',
            color: '#E8DEC8',
            fontFamily: 'var(--font-mono)',
            fontSize: '8px',
            lineHeight: '1.4',
            whiteSpace: 'nowrap',
            pointerEvents: 'none',
            boxShadow: '0 4px 20px rgba(0,0,0,0.6)'
          }}>
            {stone.decayStage === 'STABLE' && stone.hasGoldSeam && (
              <div style={{ color: '#C8841A', fontWeight: 'bold', marginBottom: '2px' }}>REPAIRED — Quiet stretch weathered</div>
            )}
            {stone.decayStage === 'WEAKENED' && (
              <div style={{ color: '#7A6A52', fontWeight: 'bold', marginBottom: '2px' }}>Weakened — no shared thoughts in 1 cycle</div>
            )}
            {stone.decayStage === 'SMALL_CRACK' && (
              <div style={{ color: '#8A7550', fontWeight: 'bold', marginBottom: '2px' }}>Cracking — no shared thoughts in 2 cycles</div>
            )}
            {stone.decayStage === 'WIDE_CRACK' && (
              <div style={{ color: '#C8841A', fontWeight: 'bold', marginBottom: '2px' }}>Wide crack — no shared thoughts in 3-4 cycles</div>
            )}
            {stone.decayStage === 'BROKEN' && (
              <div style={{ color: '#A65b5b', fontWeight: 'bold', marginBottom: '2px' }}>Broken — no shared thoughts in 5+ cycles</div>
            )}
            <div style={{ fontWeight: 'bold' }}>{stone.title_a} <span style={{ color: '#C8841A' }}>&times;</span> {stone.title_b}</div>
            <div style={{ fontSize: '7px', color: '#7A6A52', marginTop: '2px' }}>
              Similarity: {Math.round(stone.synapse.similarity * 100)}%
            </div>
          </div>
        </Html>
      )}
    </group>
  );
}

const seededRandom = (s) => {
  const x = Math.sin(s) * 10000;
  return x - Math.floor(x);
};

const getStageSeverity = (stage) => {
  const order = ['STABLE', 'WEAKENED', 'SMALL_CRACK', 'WIDE_CRACK', 'BROKEN'];
  return order.indexOf(stage);
};
const isRepairedStage = (prev, curr) => {
  return getStageSeverity(prev) > getStageSeverity(curr);
};

/* ── CAIRN COORDINATOR SCENE ───────────────────────────────────── */

function CairnScene({
  bridgeDetails,
  animationDone,
  setAnimationDone,
  activeNode,
  setActiveNode,
  setActiveSynapseIdx,
  skipTriggered,
  setSkipTriggered,
  playSound,
  selectedBridgeId,
  setOverlayText,
  setSubOverlayText
}) {
  const controlsRef = useRef();
  const shakeRef = useRef({ amplitude: 0 });
  const particlesRef = useRef([]);
  const [dustParticles, setDustParticles] = useState([]);
  const phaseStartTimeRef = useRef(0);
  const sequenceTimeRef = useRef(0);
  const ceremonyUpdatedRef = useRef(false);
  
  const { calculatedStones, totalHeight, cameraDistance, cameraY } = useMemo(() => {
    if (!bridgeDetails) return { calculatedStones: [], totalHeight: 0, cameraDistance: 5, cameraY: 2 };
    

    
    const stones = [];
    
    const fStones = [
      {
        type: 'foundation',
        x: -0.22,
        y: -0.05,
        z: -0.12,
        radius: 0.45,
        scaleY: 0.6,
        rotX: -0.05,
        rotY: 0.2,
        rotZ: 0.05,
        decayStage: 'STABLE',
        hasGoldSeam: false
      },
      {
        type: 'foundation',
        x: 0.22,
        y: -0.05,
        z: -0.12,
        radius: 0.42,
        scaleY: 0.62,
        rotX: 0.08,
        rotY: -0.4,
        rotZ: -0.06,
        decayStage: 'STABLE',
        hasGoldSeam: false
      },
      {
        type: 'foundation',
        x: 0.0,
        y: -0.02,
        z: 0.20,
        radius: 0.40,
        scaleY: 0.58,
        rotX: -0.06,
        rotY: 0.8,
        rotZ: 0.02,
        decayStage: 'STABLE',
        hasGoldSeam: false
      }
    ];
    
    stones.push(...fStones);
    
    let prevY = 0.24; 
    let prevX = 0.0;
    let prevZ = 0.0;
    
    const sortedSynapses = [...bridgeDetails.synapses].sort((a, b) => {
      const da = Math.max(a.item_a.created_at ? new Date(a.item_a.created_at).getTime() : 0, a.item_b.created_at ? new Date(a.item_b.created_at).getTime() : 0);
      const db = Math.max(b.item_a.created_at ? new Date(b.item_a.created_at).getTime() : 0, b.item_b.created_at ? new Date(b.item_b.created_at).getTime() : 0);
      return da - db;
    });
    
    const similarities = sortedSynapses.map(s => s.similarity).sort((a, b) => b - a);
    const top10PercentIdx = Math.max(0, Math.floor(similarities.length * 0.1) - 1);
    const quartzThreshold = similarities.length > 0 ? similarities[top10PercentIdx] : 0.88;
    
    sortedSynapses.forEach((syn, i) => {
      const seed = syn.item_a.id + syn.item_b.id + i;
      // Increased base size (0.6) and larger minimum clamp floor (0.3) for bold visual layout
      const radius = Math.max(0.3, 0.6 * Math.pow(0.96, i));
      const scaleY = 0.55 + 0.15 * seededRandom(seed * 17);
      const halfHeight = radius * scaleY * 0.5; // Spacing matches oblate squashed Y
      
      const y = prevY + halfHeight;
      prevY = y + halfHeight + 0.01; // Spacing contact gap
      
      const jitterX = (seededRandom(seed * 31) * 2 - 1) * 0.08;
      const jitterZ = (seededRandom(seed * 47) * 2 - 1) * 0.08;
      let x = prevX + jitterX;
      let z = prevZ + jitterZ;
      
      const dist = Math.sqrt(x * x + z * z);
      const maxLean = 0.35;
      if (dist > maxLean) {
        x = (x / dist) * maxLean;
        z = (z / dist) * maxLean;
      }
      
      prevX = x;
      prevZ = z;
      
      const rotX = (seededRandom(seed * 13) * 2 - 1) * 0.15;
      const rotY = seededRandom(seed * 29) * Math.PI * 2;
      const rotZ = (seededRandom(seed * 43) * 2 - 1) * 0.15;
      
      const techKeywords = ['tech', 'code', 'python', 'software', 'develop', 'program', 'data', 'algorithm', 'model', 'ai', 'neural', 'vector', 'search', 'fastapi', 'react', 'sql', 'db', 'git', 'engineering', 'math', 'science', 'analytic', 'system', 'web', 'comput'];
      const titleLower = ((syn.item_a.title || '') + ' ' + (syn.item_b.title || '')).toLowerCase();
      const summaryLower = ((syn.item_a.summary || '') + ' ' + (syn.item_b.summary || '')).toLowerCase();
      const isAnalytical = techKeywords.some(kw => titleLower.includes(kw) || summaryLower.includes(kw));
      const category = isAnalytical ? 'analytical' : 'reflective';
      
      const isQuartz = syn.similarity >= quartzThreshold || syn.similarity >= 0.88;
      
      stones.push({
        type: 'synapse',
        synapseIdx: i,
        synapse: syn,
        x,
        y,
        z,
        radius,
        scaleY,
        rotX,
        rotY,
        rotZ,
        category,
        isQuartz,
        decayStage: syn.decay_stage || 'STABLE',
        hasGoldSeam: syn.has_gold_seam || false,
        title_a: syn.item_a.title,
        title_b: syn.item_b.title
      });
    });
    
    const totalHeight = prevY;
    const cameraDistance = 6.0; // Fixed camera distance to render cairn big and centered
    const cameraY = 1.8; // Fixed camera height for eye-level view
    
    return { calculatedStones: stones, totalHeight, cameraDistance, cameraY };
  }, [bridgeDetails]);

  const lastCeremonyTime = useMemo(() => {
    if (!bridgeDetails?.last_ceremony_at) return 0;
    return new Date(bridgeDetails.last_ceremony_at).getTime();
  }, [bridgeDetails]);

  const { oldStones, newStones, repairingSynapseIdx, firstEver } = useMemo(() => {
    if (calculatedStones.length === 0) return { oldStones: [], newStones: [], repairingSynapseIdx: null, firstEver: false };
    
    const foundations = calculatedStones.filter(s => s.type === 'foundation');
    const synapses = calculatedStones.filter(s => s.type === 'synapse');
    
    if (synapses.length === 0) {
      return {
        oldStones: [],
        newStones: foundations.map((s, idx) => ({ ...s, isNew: true, localIdx: idx })),
        repairingSynapseIdx: null,
        firstEver: true
      };
    }
    
    if (lastCeremonyTime === 0) {
      return {
        oldStones: calculatedStones,
        newStones: [],
        repairingSynapseIdx: null,
        firstEver: false
      };
    }
    
    const oldS = [...foundations];
    const newS = [];
    
    const localCacheKey = `recall_bridge_${selectedBridgeId}_decay_stages`;
    const cachedStages = JSON.parse(localStorage.getItem(localCacheKey) || '{}');
    
    let repIdx = null;
    
    synapses.forEach((s, idx) => {
      const synDate = Math.max(
        s.synapse.item_a.created_at ? new Date(s.synapse.item_a.created_at).getTime() : 0,
        s.synapse.item_b.created_at ? new Date(s.synapse.item_b.created_at).getTime() : 0
      );
      
      const isNewStone = synDate > lastCeremonyTime;
      
      const prevStage = cachedStages[s.synapse.item_a.id + '_' + s.synapse.item_b.id] || 'STABLE';
      const isRep = isRepairedStage(prevStage, s.decayStage);
      if (isRep && repIdx === null) {
        repIdx = idx;
      }
      
      if (isNewStone) {
        newS.push({ ...s, isNew: true, localIdx: newS.length });
      } else {
        oldS.push(s);
      }
    });
    
    return {
      oldStones: oldS,
      newStones: newS,
      repairingSynapseIdx: repIdx,
      firstEver: false
    };
  }, [calculatedStones, lastCeremonyTime, selectedBridgeId]);



  const [phase, setPhase] = useState('idle');
  const [hoveredIdx, setHoveredIdx] = useState(null);
  
  const cairnTiltRef = useRef(0);
  
  const triggerImpactEffects = (x, y, z) => {
    shakeRef.current.amplitude = 0.035;
    
    const particleCount = 6 + Math.floor(Math.random() * 3);
    const newParticles = [];
    for (let i = 0; i < particleCount; i++) {
      const angle = Math.random() * Math.PI * 2;
      const speed = 0.35 + Math.random() * 0.45;
      newParticles.push({
        id: Math.random().toString(),
        pos: [x, y, z],
        vel: [Math.cos(angle) * speed, 0.15 + Math.random() * 0.25, Math.sin(angle) * speed],
        age: 0,
        maxAge: 0.3 + Math.random() * 0.1,
        size: 0.04 + Math.random() * 0.02
      });
    }
    particlesRef.current.push(...newParticles);
    setDustParticles([...particlesRef.current]);
  };

  const triggerCeremonyUpdate = useCallback(() => {
    if (ceremonyUpdatedRef.current) return;
    ceremonyUpdatedRef.current = true;
    
    const localCacheKey = `recall_bridge_${selectedBridgeId}_decay_stages`;
    const nextCache = {};
    bridgeDetails?.synapses?.forEach(s => {
      nextCache[s.item_a.id + '_' + s.item_b.id] = s.decay_stage;
    });
    localStorage.setItem(localCacheKey, JSON.stringify(nextCache));
    
    fetch(`/api/bridges/${selectedBridgeId}/ceremony`, { method: 'POST' })
      .catch(err => console.warn("Failed to update ceremony timestamp:", err));
  }, [selectedBridgeId, bridgeDetails]);

  useEffect(() => {
    if (newStones.length === 0 && repairingSynapseIdx === null) {
      setPhase('resting');
      setAnimationDone(true);
      triggerCeremonyUpdate();
    } else {
      setPhase(repairingSynapseIdx !== null ? 'repair' : 'growth');
      phaseStartTimeRef.current = 0;
      sequenceTimeRef.current = 0;
      ceremonyUpdatedRef.current = false;
    }
  }, [newStones.length, repairingSynapseIdx, triggerCeremonyUpdate, setAnimationDone]);

  useEffect(() => {
    if (phase === 'repair') {
      setOverlayText('WEATHERING SILENT CYCLES');
      setSubOverlayText('Restoring connection health...');
    } else if (phase === 'growth') {
      if (firstEver) {
        setOverlayText('THE ORIGIN MOMENT');
        setSubOverlayText('Placing the foundation stones...');
      } else {
        setOverlayText('PLACING SHARED MEMORY');
        setSubOverlayText('Consolidating new thoughts...');
      }
    } else if (phase === 'lean') {
      if (firstEver) {
        setOverlayText('FOUNDATION SECURED');
        setSubOverlayText('Connection alignment complete');
      } else {
        setOverlayText(`${newStones.length} STONES ADDED THIS CYCLE`);
        setSubOverlayText(`${bridgeDetails?.synapses?.length || 0} TOTAL STONES FORGED`);
      }
    } else if (phase === 'resting') {
      if (newStones.length > 0) {
        setOverlayText('CAIRN STABILIZED');
        setSubOverlayText('Connection alignment complete');
        const timer = setTimeout(() => {
          setOverlayText('');
          setSubOverlayText('');
        }, 4000);
        return () => clearTimeout(timer);
      } else {
        setOverlayText('THE CAIRN HOLDS STEADY');
        setSubOverlayText('No new thoughts this cycle');
        const timer = setTimeout(() => {
          setOverlayText('');
          setSubOverlayText('');
        }, 4000);
        return () => clearTimeout(timer);
      }
    }
  }, [phase, newStones.length, bridgeDetails, firstEver, setOverlayText, setSubOverlayText]);

  const repairTriggeredRef = useRef(false);
  const activeSwayOffsetRef = useRef(0);
  
  useFrame((state) => {
    const dt = Math.min(state.clock.getDelta(), 0.05); 
    const t = state.clock.getElapsedTime();
    
    if (!animationDone) {
      if (skipTriggered) {
        setPhase('resting');
        setAnimationDone(true);
        cairnTiltRef.current = 0;
        triggerCeremonyUpdate();
      } else {
        sequenceTimeRef.current += dt;
        const seqTime = sequenceTimeRef.current;
        const phaseTime = seqTime - phaseStartTimeRef.current;
        
        if (phase === 'repair') {
          if (phaseTime >= 1.8 && !repairTriggeredRef.current) {
            repairTriggeredRef.current = true;
            AudioEngine.playChime();
          }
          if (phaseTime >= 2.2) {
            setPhase('growth');
            phaseStartTimeRef.current = seqTime;
          }
        } else if (phase === 'growth') {
          let allLanded = true;
          newStones.forEach((s) => {
            const fallStart = s.localIdx * 0.6;
            const fallDuration = s.type === 'foundation' ? 1.4 : 0.9;
            const landingTime = fallStart + fallDuration;
            
            if (phaseTime >= fallStart && !s.started) {
              s.started = true;
            }
            if (phaseTime >= landingTime && !s.landed) {
              s.landed = true;
              AudioEngine.playThud();
              triggerImpactEffects(s.x, s.y, s.z);
              activeSwayOffsetRef.current = 0.015 * (Math.random() > 0.5 ? 1 : -1);
            }
            if (!s.landed) {
              allLanded = false;
            }
          });
          
          activeSwayOffsetRef.current *= Math.exp(-dt * 6);
          cairnTiltRef.current = activeSwayOffsetRef.current * Math.sin(t * 12);
          
          if (allLanded && phaseTime >= (newStones.length - 1) * 0.6 + 1.6) {
            setPhase('lean');
            phaseStartTimeRef.current = seqTime;
          }
        } else if (phase === 'lean') {
          const targetLeanAngle = 0.07 * (selectedBridgeId % 2 === 0 ? 1 : -1);
          if (phaseTime < 0.6) {
            cairnTiltRef.current = (phaseTime / 0.6) * targetLeanAngle;
          } else if (phaseTime < 1.0) {
            cairnTiltRef.current = targetLeanAngle;
          } else if (phaseTime < 2.2) {
            const progress = (phaseTime - 1.0) / 1.2;
            cairnTiltRef.current = targetLeanAngle * (1 - progress);
          } else {
            cairnTiltRef.current = 0;
          }
          
          if (phaseTime >= 4.0) {
            setPhase('resting');
            setAnimationDone(true);
            triggerCeremonyUpdate();
          }
        }
      }
    } else {
      cairnTiltRef.current = Math.sin(t * 0.5) * 0.006;
    }

    if (activeNode) {
      const idx = activeNode.synapseIdx;
      const stone = calculatedStones.find(s => s.type === 'synapse' && s.synapseIdx === idx);
      if (stone) {
        const targetPos = new THREE.Vector3(
          stone.x,
          stone.y + 0.1,
          stone.z + stone.radius * 3.5
        );
        const targetLook = new THREE.Vector3(stone.x, stone.y, stone.z);
        state.camera.position.lerp(targetPos, 0.08);
        if (controlsRef.current) {
          controlsRef.current.target.lerp(targetLook, 0.08);
        }
      }
    } else {
      const targetPos = new THREE.Vector3(0, cameraY, cameraDistance);
      const targetLook = new THREE.Vector3(0, 1.2, 0); // Fixed look target at center of base stack
      
      state.camera.position.lerp(targetPos, 0.05);
      if (controlsRef.current) {
        controlsRef.current.target.lerp(targetLook, 0.05);
      }
    }
    
    if (controlsRef.current) {
      controlsRef.current.update();
    }
  });

  const { individualStones, instancedStones } = useMemo(() => {
    const synapses = calculatedStones.filter(s => s.type === 'synapse');
    const foundations = calculatedStones.filter(s => s.type === 'foundation');
    
    if (synapses.length <= 50) {
      return { individualStones: calculatedStones, instancedStones: [] };
    }
    
    const individuals = [...foundations];
    const instanced = [];
    
    synapses.forEach((s) => {
      const isNewStone = newStones.some(ns => ns.synapseIdx === s.synapseIdx);
      const isRep = repairingSynapseIdx === s.synapseIdx;
      const isRecent = s.synapseIdx >= synapses.length - 20;
      
      if (s.isQuartz || isNewStone || isRep || isRecent) {
        individuals.push(s);
      } else {
        instanced.push(s);
      }
    });
    
    return { individualStones: individuals, instancedStones: instanced };
  }, [calculatedStones, newStones, repairingSynapseIdx]);

  return (
    <group>
      <ambientLight intensity={0.25} />
      <directionalLight
        position={[-4, 8, 4]}
        intensity={1.4}
        color="#C8841A"
        castShadow
        shadow-mapSize-width={1024}
        shadow-mapSize-height={1024}
        shadow-bias={-0.001}
        shadow-camera-far={25}
        shadow-camera-left={-4}
        shadow-camera-right={4}
        shadow-camera-top={4}
        shadow-camera-bottom={-4}
      />
      <directionalLight
        position={[4, 4, -4]}
        intensity={0.25}
        color="#3A2A18"
      />
      
      <GroundPlane />

      <group rotation={[0, 0, cairnTiltRef.current]}>
        <CairnInstancedBase stones={instancedStones} />

        {individualStones.map((stone, idx) => {
          const isNewStone = newStones.find(ns => ns.synapseIdx === stone.synapseIdx && stone.type === 'synapse');
          const isFoundationNew = firstEver && stone.type === 'foundation';
          
          let localTime = -1;
          let isNew = false;
          if (isNewStone) {
            localTime = (sequenceTimeRef.current - phaseStartTimeRef.current) - isNewStone.localIdx * 0.6;
            isNew = true;
          } else if (isFoundationNew) {
            const fIdx = stone.radius > 0.44 ? 0 : (stone.radius > 0.41 ? 1 : 2);
            localTime = (sequenceTimeRef.current - phaseStartTimeRef.current) - fIdx * 0.6;
            isNew = true;
          }
          
          const isRepairing = repairingSynapseIdx === stone.synapseIdx && stone.type === 'synapse';
          const repairLocalTime = isRepairing ? (sequenceTimeRef.current - phaseStartTimeRef.current) : -1;

          return (
            <CairnStone
              key={stone.type === 'foundation' ? `f-${idx}` : `syn-${stone.synapseIdx}`}
              stone={stone}
              index={idx}
              isNew={isNew}
              isRepairing={isRepairing}
              localTime={isNew ? localTime : (isRepairing ? repairLocalTime : -1)}
              activeNode={activeNode}
              setActiveNode={setActiveNode}
              setActiveSynapseIdx={setActiveSynapseIdx}
              hoveredIdx={hoveredIdx}
              setHoveredIdx={setHoveredIdx}
              playSound={playSound}
            />
          );
        })}
      </group>

      {dustParticles.map((p) => (
        <mesh key={p.id} position={p.pos}>
          <sphereGeometry args={[p.size * (1 - p.age / p.maxAge), 8, 8]} />
          <meshBasicMaterial color="#1A1510" transparent opacity={0.55 * (1 - p.age / p.maxAge)} />
        </mesh>
      ))}

      {animationDone && (
        <OrbitControls 
          ref={controlsRef}
          enableZoom={true} 
          enablePan={true} // Allow panning to inspect tall stacks
          minDistance={2.5}
          maxDistance={15.0}
          target={[0, 1.2, 0]}
        />
      )}
      
      <EffectComposer>
        <Bloom 
          luminanceThreshold={0.75} 
          intensity={0.3} 
          radius={0.5} 
        />
      </EffectComposer>
    </group>
  );
}

export function getInterpretiveText(score) {
  const s = score || 0;
  if (s < 15) {
    return "Parallel thinkers. Rare overlap, distinct lenses.";
  } else if (s < 35) {
    return "Intersecting pathways. Emerging alignment, diverse backgrounds.";
  } else if (s < 55) {
    return "Resonant minds. Shared frequencies, complementary insights.";
  } else if (s < 75) {
    return "Deep cognitive synergy. High coherence, shared intellectual foundation.";
  } else {
    return "Consonant consciousness. Identical wavelengths, unified conceptual map.";
  }
}


/* ── STYLE RULES SHEET ──────────────────────────────────────────────────── */
const stylesCss = `
  @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,600;1,300;1,400&family=DM+Sans:wght@400;500;700&family=JetBrains+Mono:wght@400;500&display=swap');

  /* Fullscreen Revamp Styles */
  .br-observatory-view-fullscreen {
    display: flex;
    flex-direction: column;
    width: 100vw;
    height: 100vh;
    background-color: #0D0B09;
    color: #E8DEC8;
    overflow: hidden;
    position: fixed;
    inset: 0;
    z-index: 9999;
    font-family: "DM Sans", sans-serif;
  }

  .br-observatory-view-fullscreen button {
    cursor: pointer;
    transition: opacity 0.2s;
  }

  .br-observatory-view-fullscreen button:hover {
    opacity: 0.8;
  }

  .facet-row-item:hover {
    background-color: #1A1510;
  }

  .facet-row-item:hover .hover-accent-bar {
    opacity: 1 !important;
  }

  @keyframes spinLoader {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }
  @keyframes successZoom {
    0% { transform: scale(0.95); opacity: 0.8; }
    100% { transform: scale(1.0); opacity: 1; }
  }

  /* Drei Text labels style */
  .mycelium-drei-label {
    font-family: "Cormorant Garamond", "DM Serif Display", serif;
    font-size: 10px;
    font-style: italic;
    color: rgba(235, 220, 195, 0.42);
    white-space: nowrap;
    text-shadow: 0 2px 4px rgba(0,0,0,0.85);
    background: rgba(6, 6, 8, 0.7);
    border: 1px solid rgba(255,255,255,0.03);
    padding: 0.15rem 0.5rem;
    border-radius: 4px;
    transition: all 0.25s ease;
    opacity: 0.85;
    pointer-events: none;
  }
  .mycelium-drei-label.active {
    color: var(--accent-gold);
    border-color: rgba(212, 175, 55, 0.25);
    background: rgba(10, 8, 14, 0.85);
    opacity: 1;
  }

  /* Loaders */
  .br-obsidian-loader {
    display: flex;
    flex-direction: column;
    align-items: center;
    justifyContent: center;
    height: 100%;
    width: 100%;
    background: ${COLOR_CHARCOAL};
    color: #eae9f0;
    gap: 1.25rem;
  }
  .spin-loader {
    animation: spinLoader 4.5s linear infinite;
    color: var(--accent-gold);
  }
  .loader-lbl {
    font-family: var(--font-mono);
    font-size: 10px;
    color: var(--text-muted);
    letter-spacing: 0.22em;
  }

  /* Locked progress state viewports */
  .br-locked-viewport {
    position: relative;
    height: 100%;
    width: 100%;
    display: flex;
    align-items: center;
    justifyContent: center;
    background: ${COLOR_CHARCOAL};
    overflow: hidden;
  }
  .starfield-bg {
    position: absolute;
    inset: 0;
    background: radial-gradient(circle at center, rgba(207, 163, 101, 0.04) 0%, transparent 70%);
  }
  .br-locked-card {
    position: relative;
    z-index: 10;
    max-width: 440px;
    width: 90%;
    background: rgba(255, 255, 255, 0.012);
    backdrop-filter: blur(24px);
    border: 1px solid rgba(207, 163, 101, 0.12);
    border-radius: 16px;
    padding: 3rem 2.5rem;
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    box-shadow: 0 35px 90px rgba(0,0,0,0.85);
  }
  .lock-avatar {
    width: 64px;
    height: 64px;
    border-radius: 50%;
    background: rgba(207, 163, 101, 0.03);
    border: 1px solid rgba(207, 163, 101, 0.15);
    display: flex;
    align-items: center;
    justifyContent: center;
    margin-bottom: 1.5rem;
  }
  .locked-card-title {
    font-family: var(--font-display);
    font-size: 18px;
    font-weight: 600;
    color: var(--accent-gold);
    letter-spacing: 0.15em;
    margin-bottom: 1rem;
  }
  .locked-card-desc {
    font-size: 12px;
    line-height: 1.6;
    color: var(--text-muted);
    margin-bottom: 2rem;
  }
  .progress-meter {
    width: 100%;
    margin-bottom: 2.25rem;
  }
  .progress-meter-hdr {
    display: flex;
    justify-content: space-between;
    font-size: 10.5px;
    font-family: var(--font-mono);
    color: var(--text-muted);
    margin-bottom: 0.5rem;
  }
  .progress-meter-track {
    width: 100%;
    height: 4px;
    background: rgba(255,255,255,0.02);
    border-radius: 2px;
    overflow: hidden;
  }
  .progress-meter-fill {
    height: 100%;
    background: linear-gradient(90deg, #8fa382 0%, var(--accent-gold) 100%);
    border-radius: 2px;
    transition: width 0.8s cubic-bezier(0.16, 1, 0.3, 1);
  }
  .locked-footer-alert {
    display: flex;
    align-items: center;
    font-family: var(--font-mono);
    font-size: 9px;
    color: rgba(255, 60, 60, 0.75);
    letter-spacing: 0.1em;
  }
  .alert-dot {
    width: 4px;
    height: 4px;
    border-radius: 50%;
    background-color: #ff3c3c;
    margin-right: 6px;
    box-shadow: 0 0 6px #ff3c3c;
  }

  /* Master layout container */
  .br-observatory-view {
    padding: 2.5rem;
    height: 100%;
    overflow-y: auto;
    background-color: ${COLOR_CHARCOAL};
    color: #eae9f0;
    font-family: system-ui, -apple-system, sans-serif;
  }

  /* Observatory back rail */
  .obs-header {
    display: flex;
    align-items: center;
    justifyContent: space-between;
    margin-bottom: 2rem;
    border-bottom: 1px solid rgba(255,255,255,0.04);
    padding-bottom: 1.25rem;
  }
  .obs-back-btn {
    background: rgba(255,255,255,0.015);
    border: 1px solid rgba(255,255,255,0.08);
    color: var(--text-signal);
    border-radius: 6px;
    padding: 0.5rem 0.85rem;
    cursor: pointer;
    font-size: 11px;
    font-family: var(--font-mono);
    display: flex;
    align-items: center;
    gap: 0.5rem;
    transition: all 0.2s ease;
  }
  .obs-back-btn:hover {
    background: rgba(255,255,255,0.04);
    color: #ffffff;
  }
  .obs-title-wrap {
    text-align: center;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  .obs-badge {
    font-size: 9px;
    font-family: var(--font-mono);
    color: var(--accent-gold);
    letter-spacing: 0.12em;
  }
  .obs-title {
    font-family: var(--font-display);
    font-size: 16px;
    font-weight: 600;
    color: #ffffff;
    letter-spacing: 0.08em;
  }
  .obs-dissolve-btn {
    background: rgba(255, 60, 60, 0.04);
    border: 1px solid rgba(255, 60, 60, 0.18);
    color: #ff3c3c;
    border-radius: 6px;
    padding: 0.5rem 0.85rem;
    cursor: pointer;
    font-size: 11px;
    font-family: var(--font-mono);
    display: flex;
    align-items: center;
    gap: 0.4rem;
  }
  .obs-dissolve-btn:hover {
    background: rgba(255, 60, 60, 0.08);
  }
  .obs-details-loader {
    display: flex;
    flex-direction: column;
    align-items: center;
    justifyContent: center;
    padding: 8rem 0;
    gap: 1.25rem;
  }

  /* Editorial Grid Layout */
  .obs-editorial-layout {
    display: grid;
    grid-template-columns: 1fr 380px;
    gap: 2.5rem;
    max-width: 1200px;
    margin: 0 auto;
    align-items: stretch;
    height: calc(100vh - 160px);
    min-height: 580px;
  }
  
  .obs-canvas-column {
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
    height: 100%;
  }

  .obs-canvas-box {
    flex: 1;
    border-radius: 12px;
    border: 1px solid rgba(255, 255, 255, 0.035);
    box-shadow: 0 15px 35px rgba(0,0,0,0.35);
    position: relative;
    overflow: hidden;
  }

  .canvas-instruction-label {
    position: absolute;
    bottom: 1.25rem;
    left: 50%;
    transform: translateX(-50%);
    background: rgba(8, 8, 10, 0.85);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 20px;
    padding: 0.45rem 1rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 9px;
    font-family: var(--font-mono);
    color: rgba(255,255,255,0.45);
    letter-spacing: 0.08em;
    pointer-events: none;
  }

  .facets-selector-row {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 0.75rem;
  }
  .facet-tab {
    background: rgba(255, 255, 255, 0.015);
    border: 1px solid rgba(255, 255, 255, 0.03);
    border-radius: 6px;
    padding: 0.75rem 0.5rem;
    cursor: pointer;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.2rem;
    transition: all 0.2s ease;
  }
  .facet-tab span {
    font-size: 10px;
    font-family: var(--font-mono);
    color: var(--text-muted);
  }
  .facet-tab-pct {
    font-size: 11.5px;
    font-weight: 600;
  }
  .facet-tab:hover {
    background: rgba(255,255,255,0.03);
    border-color: rgba(255,255,255,0.08);
  }
  .facet-tab.active {
    background: rgba(207, 163, 101, 0.03);
    border-color: rgba(207, 163, 101, 0.25);
  }
  .facet-tab.active span {
    color: var(--accent-gold);
  }
  .facet-tab.active .facet-tab-pct {
    color: #ffffff;
  }

  /* Editorial Sidebar */
  .obs-editorial-sidebar {
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
    height: 100%;
    overflow-y: auto;
  }

  .editorial-score-box {
    background: rgba(255, 255, 255, 0.012);
    border: 1px solid rgba(255, 255, 255, 0.03);
    border-radius: 12px;
    padding: 1.5rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  .score-hdr {
    font-size: 9px;
    font-family: var(--font-mono);
    color: var(--text-muted);
    letter-spacing: 0.05em;
  }
  .score-num-row {
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
  }
  .score-large {
    font-size: 32px;
    font-weight: 700;
    font-family: var(--font-mono);
    color: #ffffff;
  }
  .score-label {
    font-size: 9.5px;
    font-family: var(--font-mono);
    color: var(--accent-gold);
  }
  .compatibility-indicator-track {
    width: 100%;
    height: 3px;
    background: rgba(255,255,255,0.02);
    border-radius: 1.5px;
    overflow: hidden;
  }
  .compatibility-indicator-fill {
    height: 100%;
    background-color: var(--accent-gold);
  }

  /* Active Synapse Card detailed split view */
  .editorial-active-synapse-card {
    background: rgba(255, 255, 255, 0.015);
    backdrop-filter: blur(20px);
    border: 1px solid rgba(255, 255, 255, 0.035);
    border-radius: 12px;
    padding: 1.5rem;
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
    box-shadow: 0 10px 30px rgba(0,0,0,0.25);
  }
  .synapse-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .synapse-index-pill {
    font-size: 9px;
    font-family: var(--font-mono);
    color: var(--accent-gold);
    background: rgba(207,163,101,0.05);
    padding: 0.15rem 0.45rem;
    border-radius: 4px;
    border: 1px solid rgba(207,163,101,0.15);
  }
  .synapse-sim-badge {
    font-size: 9.5px;
    font-family: var(--font-mono);
    color: rgba(255,255,255,0.45);
  }
  .synapse-split-column {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }
  .source-label {
    font-size: 8px;
    font-family: var(--font-mono);
    margin-bottom: 0.15rem;
  }
  .source-label.yours { color: #00f0ff; }
  .source-label.theirs { color: #ff00ff; }
  .source-title {
    font-size: 13.5px;
    font-weight: 600;
    color: #ffffff;
    line-height: 1.4;
    margin: 0;
  }
  .source-summary {
    font-size: 11px;
    line-height: 1.5;
    color: var(--text-muted);
    margin: 0;
  }
  .synapse-divider-dash {
    height: 1px;
    border-top: 1px dashed rgba(255,255,255,0.06);
    width: 100%;
  }

  .editorial-profile-box {
    background: rgba(255, 255, 255, 0.012);
    border: 1px solid rgba(255, 255, 255, 0.03);
    border-radius: 12px;
    padding: 1.5rem;
    display: flex;
    flex-direction: column;
    gap: 0.85rem;
  }
  .profile-hdr {
    font-size: 9px;
    font-family: var(--font-mono);
    color: var(--text-muted);
    letter-spacing: 0.05em;
  }
  .profile-desc {
    font-size: 11.5px;
    line-height: 1.55;
    color: var(--text-signal);
    opacity: 0.85;
    margin: 0;
  }
  .archetype-pair-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.75rem;
    border-top: 1px solid rgba(255,255,255,0.03);
    padding-top: 0.85rem;
  }
  .archetype-pill {
    background: rgba(255,255,255,0.01);
    border: 1px solid rgba(255,255,255,0.03);
    border-radius: 6px;
    padding: 0.5rem;
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
  }
  .archetype-pill .label {
    font-size: 8px;
    font-family: var(--font-mono);
    color: rgba(255,255,255,0.3);
  }
  .archetype-pill .value {
    font-size: 11.5px;
    font-family: var(--font-mono);
    font-weight: 600;
    color: var(--accent-gold);
  }

  /* Master list deck layout */
  .obs-main-deck {
    display: grid;
    grid-template-columns: 350px 1fr;
    gap: 2.5rem;
    max-width: 1200px;
    margin: 0 auto;
    padding-bottom: 4rem;
  }
  .obs-console-sidebar {
    display: flex;
    flex-direction: column;
    gap: 2rem;
  }
  .console-box {
    padding: 1.75rem;
    gap: 1.5rem;
    background: rgba(10, 8, 16, 0.35);
  }
  .console-title {
    font-family: var(--font-display);
    font-size: 15px;
    color: var(--accent-gold);
    letter-spacing: 0.05em;
    margin: 0;
  }
  .console-desc {
    font-size: 12px;
    line-height: 1.55;
    color: var(--text-muted);
    margin: 0;
  }
  .console-action-block {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  .console-primary-btn {
    background: rgba(207,163,101,0.03);
    border: 1px solid rgba(207,163,101,0.15);
    color: var(--accent-gold);
    padding: 0.75rem;
    border-radius: 6px;
    cursor: pointer;
    font-size: 11.5px;
    font-weight: 600;
    display: flex;
    align-items: center;
    justifyContent: center;
    gap: 0.5rem;
    transition: all 0.2s ease;
  }
  .console-primary-btn:hover {
    background: rgba(207,163,101,0.08);
    border-color: var(--accent-gold);
  }
  .console-code-output {
    display: flex;
    align-items: center;
    justifyContent: space-between;
    background: rgba(0,0,0,0.3);
    border: 1px solid rgba(255,255,255,0.05);
    padding: 0.5rem 0.75rem;
    border-radius: 6px;
    font-family: var(--font-mono);
  }
  .code-text {
    font-size: 12px;
    color: #ffffff;
    letter-spacing: 0.05em;
  }
  .code-copy-btn {
    background: transparent;
    border: none;
    color: var(--accent-gold);
    font-size: 9.5px;
    font-weight: 600;
    cursor: pointer;
  }
  .console-connect-form {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  .console-input-label {
    font-size: 9px;
    font-family: var(--font-mono);
    color: rgba(255,255,255,0.35);
    letter-spacing: 0.05em;
  }
  .console-input-wrapper {
    display: flex;
    gap: 0.5rem;
  }
  .console-token-input {
    flex: 1;
    background: rgba(0,0,0,0.25);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 6px;
    color: #ffffff;
    padding: 0.65rem 0.75rem;
    font-size: 12px;
    font-family: var(--font-mono);
    outline: none;
  }
  .console-submit-btn {
    background: var(--accent-gold);
    color: #020204;
    border: none;
    border-radius: 6px;
    padding: 0 1rem;
    font-size: 11px;
    font-weight: 600;
    cursor: pointer;
  }
  .console-divider {
    height: 1px;
    background: rgba(255,255,255,0.03);
    width: 100%;
  }
  .obs-privacy-shield {
    display: flex;
    align-items: flex-start;
    font-size: 10px;
    color: rgba(255,255,255,0.3);
    line-height: 1.45;
  }

  /* Connected bridges lists */
  .obs-bridges-deck {
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
  }
  .obs-section-title {
    font-family: var(--font-display);
    font-size: 14px;
    color: var(--text-muted);
    letter-spacing: 0.05em;
    margin: 0;
  }
  .obs-cards-layout-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 1.5rem;
  }
  .obs-deck-card {
    position: relative;
    border-radius: 12px;
    padding: 1px;
    cursor: pointer;
    overflow: hidden;
    transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1);
  }
  .obs-deck-card:hover {
    transform: translateY(-4px);
  }
  .card-glow-back {
    position: absolute;
    inset: 0;
    filter: blur(15px);
    opacity: 0;
    transition: opacity 0.3s ease;
  }
  .obs-deck-card:hover .card-glow-back {
    opacity: 0.15;
  }
  .card-obs-glass {
    background: rgba(20, 18, 28, 0.45);
    border: 1px solid rgba(255,255,255,0.04);
    border-radius: 12px;
    padding: 1.5rem;
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
  }
  .card-obs-top {
    display: flex;
    align-items: center;
    gap: 0.85rem;
  }
  .avatar-shield {
    width: 38px;
    height: 38px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justifyContent: center;
    font-size: 12px;
    font-weight: 700;
    font-family: var(--font-mono);
  }
  .avatar-meta {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
  }
  .meta-name {
    font-size: 13.5px;
    font-weight: 600;
    color: #ffffff;
  }
  .meta-type {
    font-size: 10px;
    font-family: var(--font-mono);
    color: var(--text-muted);
  }
  .meta-readout {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
  }
  .readout-val {
    font-size: 18px;
    font-family: var(--font-mono);
    color: var(--accent-gold);
    font-weight: 700;
  }
  .readout-lbl {
    font-size: 8px;
    font-family: var(--font-mono);
    color: rgba(255,255,255,0.25);
  }
  .card-obs-footer {
    border-top: 1px solid rgba(255,255,255,0.03);
    padding-top: 0.75rem;
    display: flex;
    align-items: center;
    justifyContent: space-between;
    font-size: 10.5px;
    font-family: var(--font-mono);
    color: var(--accent-gold);
    opacity: 0.85;
  }

  /* Empty state */
  .obs-empty-deck {
    background: rgba(255,255,255,0.015);
    border: 1px dashed rgba(255,255,255,0.04);
    border-radius: 12px;
    padding: 5rem 2rem;
    display: flex;
    flex-direction: column;
    alignItems: center;
    justifyContent: center;
    text-align: center;
  }
  .obs-empty-orb {
    width: 48px;
    height: 48px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(207,163,101,0.08) 0%, transparent 70%);
    border: 1px solid rgba(207,163,101,0.15);
    margin-bottom: 1.5rem;
  }
  .obs-empty-title {
    font-size: 12px;
    font-family: var(--font-mono);
    color: var(--accent-gold);
    margin-bottom: 0.5rem;
    letter-spacing: 0.05em;
  }
  .obs-empty-desc {
    font-size: 11px;
    color: var(--text-muted);
    max-width: 260px;
    line-height: 1.45;
  }

  /* Success tunnel modal overlay */
  .obs-success-modal {
    position: fixed;
    inset: 0;
    z-index: 9999;
    background: rgba(8, 8, 10, 0.96);
    display: flex;
    align-items: center;
    justifyContent: center;
  }
  .obs-success-card {
    text-align: center;
    max-width: 420px;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1.5rem;
    z-index: 10;
  }
  .br-success-zoom-icon {
    animation: successZoom 1.2s ease-in-out infinite alternate;
  }
  .obs-success-title {
    font-family: var(--font-display);
    font-size: 18px;
    font-weight: 600;
    color: #00f0ff;
    letter-spacing: 0.1em;
    margin: 0;
  }
  .obs-success-desc {
    font-size: 13px;
    color: var(--text-muted);
    line-height: 1.5;
    margin: 0;
  }

  /* Fade transitions */
  .fade-in-panel {
    animation: successZoom 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards;
  }
  .slide-in-view {
    animation: successZoom 0.45s cubic-bezier(0.16, 1, 0.3, 1) forwards;
  }
`;
