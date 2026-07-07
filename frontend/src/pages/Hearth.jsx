/**
 * frontend/src/pages/Hearth.jsx
 * ==============================
 * Hearth — shared home progression for two paired users.
 *
 * State 1 (unpaired): Landing page with CSS isometric hut, invite flow,
 *                     and connection animation.
 * State 2 (paired):   Full-screen 3D BranchingPOC with minimal HUD overlay,
 *                     flip clock counter, and milestone celebration.
 */

import { useState, useEffect, useRef, useCallback, lazy, Suspense } from 'react';

const BranchingPOC = lazy(() => import('./BranchingPOC'));

/* ═══════════════════════════════════════════════════════════════════════════
   SCORE / STAGE HELPERS (mirrors backend/routes/hearth.py)
   ═══════════════════════════════════════════════════════════════════════════ */

function sharedDaysToScore(days) {
  if (days <= 20)  return days * 0.80;
  if (days <= 40)  return 16 + (days - 20) * 0.85;
  if (days <= 65)  return 33 + (days - 40) * 0.76;
  if (days <= 120) return 52 + (days - 65) * 0.38;
  return Math.min(96, 73 + (days - 120) * 0.30);
}

const STAGE_NAMES   = ['Hut', 'Cottage', 'House', 'Manor', 'Villa', 'Castle'];
const STAGE_EMOJIS  = { Hut:'🪵', Cottage:'🏡', House:'🏠', Manor:'🏛', Villa:'🏰', Castle:'🔒' };
const STAGE_DAYS    = { Hut:0, Cottage:20, House:40, Manor:65, Villa:120, Castle:200 };

function nextStage(stage) {
  const idx = STAGE_NAMES.indexOf(stage);
  return idx < STAGE_NAMES.length - 1 ? STAGE_NAMES[idx + 1] : null;
}
function daysToNext(stage, sharedDays) {
  const next = nextStage(stage);
  if (!next || stage === 'Castle') return null;
  return Math.max(0, STAGE_DAYS[next] - sharedDays);
}

/* ═══════════════════════════════════════════════════════════════════════════
   CSS STYLES (injected once)
   ═══════════════════════════════════════════════════════════════════════════ */

/* ═══════════════════════════════════════════════════════════════════════════
   DEV TEST PRESETS  (only active on localhost)
   ═══════════════════════════════════════════════════════════════════════════ */

const SAMPLE_JOURNEYS = [
  { pair_id:'dev-1', is_paired:true, shared_days:18,  score:14.4, stage:'Hut',     partner_name:'Alex',   partner_active_today:true,  self_active_today:true  },
  { pair_id:'dev-2', is_paired:true, shared_days:38,  score:29.3, stage:'Cottage', partner_name:'Maya',   partner_active_today:true,  self_active_today:true  },
  { pair_id:'dev-3', is_paired:true, shared_days:62,  score:49.7, stage:'House',   partner_name:'Jordan', partner_active_today:false, self_active_today:true  },
  { pair_id:'dev-4', is_paired:true, shared_days:115, score:70.7, stage:'Manor',   partner_name:'Riley',  partner_active_today:false, self_active_today:false },
  { pair_id:'dev-5', is_paired:true, shared_days:175, score:88.0, stage:'Villa',   partner_name:'Sam',    partner_active_today:true,  self_active_today:false },
];

const DEV_PRESETS = [
  { label: '🪵 Unpaired',            state: 'unpaired' },
  { label: '✨ Connecting',          state: 'connecting' },
  { label: '▶ Simulate growth',      state: 'simulate' },
  { label: '🏠 Two journeys hub',    journeys: SAMPLE_JOURNEYS.slice(0, 2) },
  { label: '🏰 Five journeys hub',   journeys: SAMPLE_JOURNEYS },
  { label: '🪵 Hut  · Day 18',       journey: SAMPLE_JOURNEYS[0] },
  { label: '🏡 Cottage · Day 38',    journey: SAMPLE_JOURNEYS[1] },
  { label: '🏠 House   · Day 62',    journey: SAMPLE_JOURNEYS[2] },
  { label: '🏛 Manor   · Day 115',   journey: SAMPLE_JOURNEYS[3] },
  { label: '🏰 Villa   · Day 175',   journey: SAMPLE_JOURNEYS[4] },
  { label: '🎉 Milestone popup',     milestone: 'House', journey: SAMPLE_JOURNEYS[2] },
  { label: '🏗 Block toast',         toast: true, journey: SAMPLE_JOURNEYS[0] },
];

const IS_DEV = typeof window !== 'undefined' &&
  (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1');

const HEARTH_CSS = `
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@200;300;400;600&family=JetBrains+Mono:wght@400;500&display=swap');

.hearth-root {
  width: 100vw; height: 100vh;
  background: #0C0B0F;
  position: relative; overflow: hidden;
  font-family: 'Outfit', sans-serif;
  color: #F0EDE8;
}

/* ── Film grain ──────────────────────────────────────────────────────────── */
.hearth-root::after {
  content: '';
  position: fixed; inset: 0; pointer-events: none; z-index: 999;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
  opacity: 0.035;
}

/* ── Fog layers ──────────────────────────────────────────────────────────── */
.hearth-fog { position: absolute; inset: 0; pointer-events: none; }
.hearth-fog-1 { background: radial-gradient(ellipse 70% 50% at 50% 65%, transparent 30%, #0C0B0F 100%); }
.hearth-fog-2 { background: radial-gradient(ellipse 90% 65% at 50% 80%, transparent 40%, #0C0B0F 90%); opacity: 0.7; }
.hearth-fog-3 { background: radial-gradient(ellipse 110% 80% at 50% 100%, transparent 50%, #0C0B0F 85%); opacity: 0.5; }

/* ── Landing page ────────────────────────────────────────────────────────── */
.hearth-landing {
  position: absolute; inset: 0;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: 0;
}

.hearth-title {
  font-size: clamp(42px, 7vw, 80px);
  font-weight: 200;
  letter-spacing: 0.55em;
  color: #F0EDE8;
  text-transform: uppercase;
  margin: 0 0 10px 0;
  opacity: 0;
  transform: translateY(18px);
  animation: hearth-fadein 0.9s cubic-bezier(0.16,1,0.3,1) 0.3s forwards;
}
.hearth-subtitle {
  font-size: 13px;
  letter-spacing: 0.22em;
  color: #8A8582;
  text-transform: lowercase;
  margin: 0 0 48px 0;
  opacity: 0;
  animation: hearth-fadein 0.7s cubic-bezier(0.16,1,0.3,1) 0.55s forwards;
}

/* ── CSS Isometric hut ───────────────────────────────────────────────────── */
.hearth-hut-wrap {
  position: relative;
  width: 180px; height: 160px;
  margin-bottom: 48px;
  opacity: 0;
  animation: hearth-fadein 0.7s cubic-bezier(0.16,1,0.3,1) 0.4s forwards;
}
.hearth-iso {
  position: absolute; top: 20px; left: 10px;
  transform: rotateX(52deg) rotateZ(-45deg);
  transform-style: preserve-3d;
}
.iso-block {
  position: absolute;
  background: #4A5880;
  border-top: 1px solid rgba(255,255,255,0.12);
  border-right: 1px solid rgba(0,0,0,0.25);
  box-shadow: inset 0 0 0 1px rgba(255,255,255,0.04);
  opacity: 0;
  transform: translateY(-80px);
  animation: iso-drop 0.45s cubic-bezier(0.34,1.56,0.64,1) both;
}
.iso-roof {
  position: absolute;
  background: #7A4A3A;
  clip-path: polygon(50% 0%, 0% 100%, 100% 100%);
  opacity: 0;
  animation: hearth-fadein 0.4s ease both;
}
.iso-window {
  position: absolute;
  background: rgba(201,137,60,0.6);
  border-radius: 1px;
  box-shadow: 0 0 6px rgba(201,137,60,0.4);
}
@keyframes iso-drop {
  to { opacity: 1; transform: translateY(0); }
}

/* ── Amber firelight ─────────────────────────────────────────────────────── */
.hearth-glow {
  position: absolute;
  bottom: -28px; left: 50%; transform: translateX(-50%);
  width: 200px; height: 60px;
  background: radial-gradient(ellipse, rgba(201,137,60,0.22) 0%, transparent 70%);
  animation: glow-breathe 3.2s ease-in-out infinite;
  pointer-events: none;
}
@keyframes glow-breathe {
  0%,100% { opacity: 0.55; transform: translateX(-50%) scaleX(1); }
  50%      { opacity: 1.0;  transform: translateX(-50%) scaleX(1.12); }
}

/* ── Pairing card ────────────────────────────────────────────────────────── */
.hearth-card {
  background: rgba(20,18,24,0.88);
  border: 1px solid rgba(240,237,232,0.08);
  border-radius: 12px;
  padding: 24px 28px;
  width: min(400px, 90vw);
  display: flex; flex-direction: column; align-items: center; gap: 20px;
  opacity: 0;
  transform: translateY(24px);
  animation: hearth-spring 0.6s cubic-bezier(0.34,1.56,0.64,1) 1.0s forwards;
  backdrop-filter: blur(12px);
}
@keyframes hearth-fadein { to { opacity: 1; transform: translateY(0); } }
@keyframes hearth-spring  { to { opacity: 1; transform: translateY(0); } }

/* ── Avatar connector ────────────────────────────────────────────────────── */
.hearth-avatars {
  display: flex; align-items: center; gap: 0; width: 100%;
}
.hearth-avatar-slot {
  display: flex; flex-direction: column; align-items: center; gap: 6px;
  flex: 0 0 72px;
}
.hearth-avatar-circle {
  width: 52px; height: 52px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 22px; font-weight: 600;
  position: relative;
}
.hearth-avatar-circle.self-avatar {
  background: rgba(124,111,212,0.15);
  border: 1.5px solid rgba(124,111,212,0.45);
  color: #7C6FD4;
}
.hearth-avatar-circle.partner-empty {
  background: rgba(240,237,232,0.04);
  border: 1.5px dashed rgba(240,237,232,0.2);
  color: #4A4845;
  animation: pulse-ring 2s ease-in-out infinite;
}
.hearth-avatar-circle.partner-filled {
  background: rgba(61,170,138,0.15);
  border: 1.5px solid rgba(61,170,138,0.45);
  color: #3DAA8A;
  animation: partner-pop 0.5s cubic-bezier(0.34,1.56,0.64,1) both;
}
@keyframes pulse-ring {
  0%,100% { box-shadow: 0 0 0 0 rgba(240,237,232,0.06); }
  50%      { box-shadow: 0 0 0 6px rgba(240,237,232,0); }
}
@keyframes partner-pop {
  from { transform: scale(0); opacity: 0; }
  to   { transform: scale(1); opacity: 1; }
}
.hearth-avatar-label {
  font-size: 10px; letter-spacing: 0.1em; color: #4A4845; text-transform: uppercase;
}
.hearth-connector {
  flex: 1; height: 1px;
  background: linear-gradient(90deg, rgba(124,111,212,0.3), rgba(240,237,232,0.06), rgba(61,170,138,0.2));
  position: relative; overflow: hidden;
}
.hearth-connector-light {
  position: absolute; top: 0; left: -100%; width: 100%; height: 100%;
  background: linear-gradient(90deg, transparent, rgba(240,237,232,0.6), transparent);
  animation: connector-travel 2s ease-in-out infinite 1.2s;
}
@keyframes connector-travel {
  0%   { left: -100%; }
  100% { left: 100%; }
}

/* ── Invite code ─────────────────────────────────────────────────────────── */
.hearth-code-wrap {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 14px;
  background: rgba(240,237,232,0.04);
  border: 1px solid rgba(240,237,232,0.07);
  border-radius: 6px; width: 100%;
}
.hearth-code-text {
  font-family: 'JetBrains Mono', monospace;
  font-size: 15px; letter-spacing: 0.12em;
  color: #C9893C; flex: 1;
}
.hearth-code-btn {
  background: none; border: none; cursor: pointer; padding: 4px;
  color: #8A8582; font-size: 11px; letter-spacing: 0.1em;
  font-family: 'JetBrains Mono', monospace;
  transition: color 0.2s;
}
.hearth-code-btn:hover { color: #F0EDE8; }

.hearth-cta-btn {
  width: 100%; padding: 12px;
  background: rgba(201,137,60,0.1);
  border: 1px solid rgba(201,137,60,0.25);
  border-radius: 6px; cursor: pointer;
  font-family: 'Outfit', sans-serif;
  font-size: 13px; letter-spacing: 0.18em; text-transform: uppercase;
  color: #C9893C;
  transition: background 0.2s, border-color 0.2s;
}
.hearth-cta-btn:hover {
  background: rgba(201,137,60,0.18);
  border-color: rgba(201,137,60,0.4);
}
.hearth-accept-input {
  width: 100%; padding: 10px 12px;
  background: rgba(240,237,232,0.04);
  border: 1px solid rgba(240,237,232,0.1);
  border-radius: 6px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 14px; color: #F0EDE8;
  outline: none; letter-spacing: 0.1em;
  transition: border-color 0.2s;
}
.hearth-accept-input:focus { border-color: rgba(124,111,212,0.4); }
.hearth-accept-input::placeholder { color: #4A4845; }

/* ── Connection animation overlay ────────────────────────────────────────── */
.hearth-connect-overlay {
  position: fixed; inset: 0; z-index: 100;
  display: flex; align-items: center; justify-content: center;
  background: rgba(12,11,15,0);
  animation: connect-darken 0.4s ease 2s forwards;
  pointer-events: none;
}
@keyframes connect-darken { to { background: rgba(12,11,15,0.92); } }
.hearth-first-flame {
  font-size: 28px; font-weight: 200;
  letter-spacing: 0.35em; color: #F0EDE8;
  text-transform: uppercase;
  opacity: 0;
  animation: flame-text 2s ease 2.6s forwards;
}
@keyframes flame-text {
  0%   { opacity: 0; transform: translateY(8px); }
  20%  { opacity: 1; transform: translateY(0); }
  80%  { opacity: 1; }
  100% { opacity: 0; }
}

/* ── Active HUD — fixed overlay, above canvas stacking context ─────── */
.hearth-hud {
  position: fixed; inset: 0; pointer-events: none; z-index: 101;
}

/* TOP-RIGHT: partner chip — fixed, above everything, always clickable */
.hearth-hud-top {
  position: fixed; top: 0; right: 0;
  padding: 16px 20px;
  display: flex; align-items: center; gap: 8px;
  pointer-events: auto;
  z-index: 101;
}
.hearth-partner-chip {
  display: flex; align-items: center; gap: 9px;
  padding: 7px 12px 7px 8px;
  background: rgba(20,18,24,0.7);
  border: 1px solid rgba(240,237,232,0.07);
  border-radius: 20px;
  backdrop-filter: blur(8px);
}
.hearth-partner-avatar {
  width: 28px; height: 28px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 600;
  background: rgba(61,170,138,0.15);
  border: 1.5px solid rgba(61,170,138,0.3);
  color: #3DAA8A; position: relative; flex-shrink: 0;
}
.hearth-partner-dot {
  position: absolute; bottom: -1px; right: -1px;
  width: 8px; height: 8px; border-radius: 50%;
  border: 1.5px solid #0C0B0F;
}
.hearth-partner-dot.active-today  { background: #3DAA8A; box-shadow: 0 0 4px #3DAA8A88; }
.hearth-partner-dot.active-recent { background: #C9893C; }
.hearth-partner-dot.inactive      { background: #4A4845; }
.hearth-partner-name { font-size: 12px; font-weight: 400; color: #F0EDE8; }
.hearth-partner-status {
  font-size: 9px; letter-spacing: 0.1em;
  font-family: 'JetBrains Mono', monospace; color: #4A4845;
}
.hearth-hud-settings {
  background: none; border: none; cursor: pointer;
  color: #4A4845; font-size: 16px; padding: 4px;
  pointer-events: auto; transition: color 0.2s;
}
.hearth-hud-settings:hover { color: #8A8582; }
.hearth-hud-settings.active { color: #C9893C; transform: rotate(60deg); }
.hearth-hud-settings { transition: color 0.2s, transform 0.35s; }

/* Settings dropdown */
.hearth-settings-dropdown {
  position: absolute; top: calc(100% + 8px); right: 0;
  min-width: 210px;
  background: rgba(14,12,18,0.92);
  border: 1px solid rgba(240,237,232,0.08);
  border-radius: 12px;
  padding: 6px;
  backdrop-filter: blur(16px);
  box-shadow: 0 8px 32px rgba(0,0,0,0.5);
  animation: hsd-in 0.15s ease-out forwards;
}
@keyframes hsd-in {
  from { opacity:0; transform: translateY(-6px) scale(0.97); }
  to   { opacity:1; transform: translateY(0)   scale(1); }
}
.hsd-item {
  display: flex; align-items: center; gap: 10px;
  width: 100%; padding: 9px 12px;
  background: none; border: none; cursor: pointer;
  color: #C8C4BE; font-size: 12px; font-family: 'Outfit', sans-serif;
  border-radius: 8px; text-align: left;
  transition: background 0.15s, color 0.15s;
}
.hsd-item:hover { background: rgba(240,237,232,0.06); color: #F0EDE8; }
.hsd-item.hsd-danger { color: #9A5A5A; }
.hsd-item.hsd-danger:hover { background: rgba(180,60,60,0.1); color: #E07070; }
.hsd-icon { font-size: 13px; width: 18px; text-align: center; flex-shrink: 0; }
.hsd-divider { height: 1px; background: rgba(240,237,232,0.06); margin: 4px 6px; }
.hearth-replay-btn {
  background: none; border: none; cursor: pointer;
  color: #4A4845; font-size: 15px; padding: 4px 6px;
  pointer-events: auto; transition: color 0.2s, transform 0.3s;
  font-family: 'JetBrains Mono', monospace;
  position: relative;
}
.hearth-replay-btn:hover { color: #C9893C; transform: rotate(-30deg); }
.hearth-replay-btn::after {
  content: 'replay';
  position: absolute; bottom: -14px; right: 0;
  font-size: 8px; letter-spacing: 0.1em; color: #4A4845;
  opacity: 0; transition: opacity 0.2s; white-space: nowrap;
  font-family: 'JetBrains Mono', monospace;
}
.hearth-replay-btn:hover::after { opacity: 1; }

/* BOTTOM: fixed two-column layout, never clipped */
.hearth-hud-bottom {
  position: fixed; bottom: 0; left: 0; right: 0;
  padding: 0 44px 28px;
  background: linear-gradient(to top, rgba(12,11,15,0.85) 0%, transparent 100%);
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  pointer-events: none;
  z-index: 101;
}

/* Stage + progress — left column */
.hearth-progress-card {
  display: flex; flex-direction: column; gap: 6px;
  max-width: 280px;
}
.hearth-stage-label {
  font-size: 9px; letter-spacing: 0.22em; text-transform: uppercase;
  color: #4A4845; font-family: 'JetBrains Mono', monospace;
}
.hearth-stage-name {
  font-size: 22px; font-weight: 300; color: #F0EDE8;
  letter-spacing: 0.04em; line-height: 1;
}
.hearth-progress-track {
  height: 2px; background: rgba(240,237,232,0.08); border-radius: 1px; overflow: hidden;
  margin-top: 2px;
}
.hearth-progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #7C6FD4, #C9893C);
  border-radius: 1px;
  transition: width 1.4s cubic-bezier(0.16,1,0.3,1);
  position: relative; overflow: hidden;
}
.hearth-progress-fill::after {
  content: '';
  position: absolute; inset: 0;
  background: linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.35) 50%, transparent 100%);
  background-size: 200% 100%;
  animation: shimmer 2.5s ease-in-out infinite;
}
@keyframes shimmer {
  0%,100% { background-position: -100% 0; }
  50%      { background-position: 200% 0; }
}
.hearth-next-label {
  font-size: 9px; color: #4A4845;
  font-family: 'JetBrains Mono', monospace;
}

/* Days counter — right column */
.hearth-days-card {
  display: flex; flex-direction: column; align-items: flex-end; gap: 3px;
  flex-shrink: 0;
}
.hearth-flip-counter {
  display: flex; align-items: baseline; gap: 2px;
}
.flip-digit-wrap {
  display: inline-block; perspective: 60px;
}
.flip-digit {
  font-family: 'JetBrains Mono', monospace;
  font-size: 26px; font-weight: 500;
  color: #C9893C; display: block;
  transition: transform 0.3s ease, opacity 0.2s;
}
.flip-digit.flipping {
  transform: rotateX(90deg); opacity: 0;
}
.hearth-days-label {
  font-size: 9px; letter-spacing: 0.2em; text-transform: uppercase;
  color: #4A4845; font-family: 'JetBrains Mono', monospace;
}


/* ── Milestone overlay ───────────────────────────────────────────────────── */
.hearth-milestone {
  position: fixed; inset: 0; z-index: 200;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 20px;
  background: rgba(12,11,15,0.93);
  animation: hearth-fadein 0.35s ease both;
}
.hearth-milestone-emoji {
  font-size: 80px; line-height: 1;
  animation: emoji-spring 0.65s cubic-bezier(0.34,1.56,0.64,1) both;
}
@keyframes emoji-spring {
  from { transform: scale(0); opacity: 0; }
  to   { transform: scale(1); opacity: 1; }
}
.hearth-milestone-stage {
  font-size: clamp(28px, 5vw, 52px);
  font-weight: 200; letter-spacing: 0.45em;
  text-transform: uppercase; color: #F0EDE8;
}
.hearth-milestone-sub {
  font-size: 14px; color: #8A8582; max-width: 340px; text-align: center; line-height: 1.6;
}
.hearth-milestone-path {
  display: flex; align-items: center; gap: 8px;
  font-size: 11px; letter-spacing: 0.14em; font-family: 'JetBrains Mono', monospace;
  color: #4A4845;
}
.hearth-milestone-path .active-stage { color: #7C6FD4; }
.hearth-milestone-actions {
  display: flex; gap: 12px; margin-top: 8px;
}
.btn-milestone-primary {
  padding: 11px 24px;
  background: linear-gradient(135deg, rgba(201,137,60,0.2), rgba(201,137,60,0.1));
  border: 1px solid rgba(201,137,60,0.35);
  border-radius: 6px; cursor: pointer;
  font-family: 'Outfit', sans-serif;
  font-size: 12px; letter-spacing: 0.18em; text-transform: uppercase;
  color: #C9893C; transition: background 0.2s;
}
.btn-milestone-primary:hover { background: rgba(201,137,60,0.25); }
.btn-milestone-secondary {
  padding: 11px 24px;
  background: none; border: 1px solid rgba(240,237,232,0.1);
  border-radius: 6px; cursor: pointer;
  font-family: 'Outfit', sans-serif;
  font-size: 12px; letter-spacing: 0.18em; text-transform: uppercase;
  color: #8A8582; transition: border-color 0.2s, color 0.2s;
}
.btn-milestone-secondary:hover { border-color: rgba(240,237,232,0.22); color: #F0EDE8; }

/* ── Block toast ─────────────────────────────────────────────────────────── */
.hearth-toast {
  position: fixed; top: 24px; right: 24px; z-index: 150;
  display: flex; align-items: center; gap: 12px;
  padding: 12px 16px;
  background: rgba(20,18,24,0.92);
  border: 1px solid rgba(240,237,232,0.1);
  border-radius: 8px; backdrop-filter: blur(8px);
  animation: toast-in 0.4s cubic-bezier(0.34,1.56,0.64,1) both;
}
.hearth-toast.hiding { animation: toast-out 0.3s cubic-bezier(0.4,0,1,1) both; }
@keyframes toast-in  { from { transform: translateX(120%); opacity:0; } to { transform:translateX(0); opacity:1; } }
@keyframes toast-out { to   { transform: translateX(120%); opacity:0; } }
.toast-icon { font-size: 18px; }
.toast-title { font-size: 13px; font-weight: 500; color: #F0EDE8; }
.toast-sub   { font-size: 11px; color: #8A8582; font-family: 'JetBrains Mono', monospace; margin-top: 1px; }

/* ── Partner glow on canvas ─────────────────────────────────────────────── */
.hearth-canvas-wrap { position: absolute; inset: 0; }
.hearth-canvas-wrap.partner-active-today {
  animation: partner-glow 3s ease-in-out infinite;
}
@keyframes partner-glow {
  0%,100% { box-shadow: 0 0 0 0 rgba(61,170,138,0); }
  50%      { box-shadow: inset 0 0 60px rgba(61,170,138,0.06); }
}

/* ── Journey hub ─────────────────────────────────────────────────────────── */
.hearth-hub {
  position: absolute; inset: 0;
  display: flex; flex-direction: column; align-items: center;
  padding: 60px 40px 100px; overflow-y: auto;
}
.hearth-hub-title {
  font-size: 13px; letter-spacing: 0.28em; text-transform: uppercase;
  color: #8A8582; margin: 0 0 36px;
  animation: hearth-fadein 0.6s ease both;
}
.hearth-hub-grid {
  display: flex; flex-wrap: wrap; gap: 16px;
  justify-content: center; width: 100%; max-width: 860px;
}
.hearth-journey-card {
  position: relative;
  width: clamp(200px, 28vw, 260px);
  background: rgba(20,18,24,0.7);
  border: 1px solid rgba(240,237,232,0.07);
  border-radius: 16px; padding: 22px 20px 18px;
  cursor: pointer;
  transition: transform 0.22s cubic-bezier(0.34,1.56,0.64,1), border-color 0.2s, box-shadow 0.2s;
  backdrop-filter: blur(10px);
  animation: hearth-fadein 0.5s ease both;
}
.hearth-journey-card:hover {
  transform: translateY(-4px) scale(1.02);
  border-color: rgba(201,137,60,0.3);
  box-shadow: 0 12px 40px rgba(0,0,0,0.4), 0 0 0 1px rgba(201,137,60,0.15);
}
.hearth-journey-card.partner-online::before {
  content: ''; position: absolute; top: 14px; right: 14px;
  width: 7px; height: 7px; border-radius: 50%;
  background: #3DAA8A; box-shadow: 0 0 8px #3DAA8A;
}
.hjc-avatar {
  width: 44px; height: 44px; border-radius: 50%;
  background: linear-gradient(135deg,rgba(201,137,60,0.3),rgba(201,137,60,0.1));
  border: 1px solid rgba(201,137,60,0.25);
  display: flex; align-items: center; justify-content: center;
  font-size: 18px; font-weight: 600; color: #C9893C; margin-bottom: 14px;
}
.hjc-name { font-size: 16px; font-weight: 500; color: #F0EDE8; margin-bottom: 4px; }
.hjc-stage { font-size: 12px; color: #8A8582; margin-bottom: 14px; }
.hjc-days { font-family:'JetBrains Mono',monospace; font-size:26px; font-weight:500; color:#C9893C; }
.hjc-days-label { font-size:9px; letter-spacing:0.18em; color:#4A4845; text-transform:uppercase; margin-top:2px; }
.hjc-bar { margin-top:14px; height:2px; background:rgba(240,237,232,0.06); border-radius:2px; overflow:hidden; }
.hjc-bar-fill { height:100%; background:linear-gradient(90deg,#7B5C2A,#C9893C); border-radius:2px; transition:width 0.6s cubic-bezier(0.16,1,0.3,1); }

.hearth-hub-actions { margin-top: 32px; display: flex; gap: 12px; }
.btn-new-journey {
  padding: 10px 22px;
  background: rgba(201,137,60,0.12); border: 1px solid rgba(201,137,60,0.3);
  border-radius: 24px; cursor: pointer;
  font-family: 'Outfit', sans-serif; font-size: 13px; letter-spacing: 0.1em; color: #C9893C;
  transition: background 0.2s, transform 0.2s;
}
.btn-new-journey:hover { background: rgba(201,137,60,0.22); transform: translateY(-1px); }

/* Back button inside 3D view */
.hearth-back-btn {
  position: fixed; top: 18px; left: 20px; z-index: 101;
  background: rgba(14,12,18,0.75); border: 1px solid rgba(240,237,232,0.08);
  border-radius: 20px; padding: 7px 14px 7px 10px;
  display: flex; align-items: center; gap: 6px;
  cursor: pointer; color: #8A8582;
  font-family: 'Outfit', sans-serif; font-size: 13px;
  transition: color 0.2s, border-color 0.2s; backdrop-filter: blur(8px);
  pointer-events: auto;
}
.hearth-back-btn:hover { color: #F0EDE8; border-color: rgba(240,237,232,0.18); }

/* Leave warning modal */
.hearth-leave-overlay {
  position: fixed; inset: 0; z-index: 500;
  background: rgba(8,7,12,0.8); backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center;
  animation: hearth-fadein 0.2s ease both;
}
.hearth-leave-modal {
  background: rgba(20,18,24,0.96); border: 1px solid rgba(240,237,232,0.09);
  border-radius: 18px; padding: 32px 28px; max-width: 360px; width: 90%;
  box-shadow: 0 24px 64px rgba(0,0,0,0.6); text-align: center;
}
.hlm-avatar {
  width: 56px; height: 56px; border-radius: 50%;
  background: rgba(180,60,60,0.15); border: 1px solid rgba(180,60,60,0.25);
  display: flex; align-items: center; justify-content: center;
  font-size: 22px; font-weight: 600; color: #E07070; margin: 0 auto 16px;
}
.hlm-title { font-size: 17px; font-weight: 500; color: #F0EDE8; margin-bottom: 8px; }
.hlm-sub   { font-size: 13px; color: #8A8582; line-height: 1.55; margin-bottom: 8px; }
.hlm-warning {
  font-size: 12px; color: #9A5A5A;
  background: rgba(180,60,60,0.08); border: 1px solid rgba(180,60,60,0.15);
  border-radius: 8px; padding: 10px 14px; margin: 16px 0 24px; line-height: 1.5;
}
.hlm-actions { display: flex; gap: 10px; }
.hlm-cancel {
  flex:1; padding:11px; background:none; border:1px solid rgba(240,237,232,0.1);
  border-radius:8px; cursor:pointer; font-family:'Outfit',sans-serif; font-size:13px;
  color:#8A8582; transition:border-color 0.2s,color 0.2s;
}
.hlm-cancel:hover { border-color:rgba(240,237,232,0.22); color:#F0EDE8; }
.hlm-confirm {
  flex:1; padding:11px; background:rgba(180,60,60,0.15); border:1px solid rgba(180,60,60,0.3);
  border-radius:8px; cursor:pointer; font-family:'Outfit',sans-serif; font-size:13px;
  color:#E07070; transition:background 0.2s;
}
.hlm-confirm:hover { background:rgba(180,60,60,0.25); }

/* ── Dev Panel ───────────────────────────────────────────────────────────── */
.hearth-dev-panel {
  position: fixed;
  bottom: 20px; left: 50%; transform: translateX(-50%);
  z-index: 9999;
  display: flex; flex-direction: column; align-items: center; gap: 8px;
}
.hearth-dev-toggle {
  padding: 6px 14px;
  background: rgba(124,111,212,0.18);
  border: 1px solid rgba(124,111,212,0.35);
  border-radius: 20px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px; letter-spacing: 0.12em;
  color: #7C6FD4; cursor: pointer;
  transition: background 0.2s;
  pointer-events: auto;
}
.hearth-dev-toggle:hover { background: rgba(124,111,212,0.28); }
.hearth-dev-menu {
  display: flex; flex-wrap: wrap; justify-content: center; gap: 6px;
  max-width: 520px;
  background: rgba(12,11,15,0.92);
  border: 1px solid rgba(124,111,212,0.2);
  border-radius: 10px;
  padding: 10px 12px;
  backdrop-filter: blur(12px);
  animation: hearth-fadein 0.2s ease both;
}
.hearth-dev-btn {
  padding: 5px 11px;
  background: rgba(240,237,232,0.04);
  border: 1px solid rgba(240,237,232,0.1);
  border-radius: 6px; cursor: pointer;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px; color: #8A8582;
  white-space: nowrap;
  transition: background 0.15s, color 0.15s;
}
.hearth-dev-btn:hover {
  background: rgba(124,111,212,0.15);
  border-color: rgba(124,111,212,0.35);
  color: #F0EDE8;
}
`;

/* ═══════════════════════════════════════════════════════════════════════════
   SUB-COMPONENTS
   ═══════════════════════════════════════════════════════════════════════════ */

/** SVG campfire on landing — warm and recognizable */
function CSSHut() {
  return (
    <div className="hearth-hut-wrap">
      <svg width="160" height="160" viewBox="0 0 160 160" fill="none" xmlns="http://www.w3.org/2000/svg"
        style={{ filter: 'drop-shadow(0 8px 32px rgba(201,137,60,0.35))' }}>
        {/* Ground shadow */}
        <ellipse cx="80" cy="138" rx="48" ry="8" fill="rgba(201,137,60,0.10)" />
        {/* Log base left */}
        <rect x="36" y="118" width="50" height="12" rx="6" fill="#7A4A28" transform="rotate(-18 36 118)" />
        {/* Log base right */}
        <rect x="74" y="118" width="50" height="12" rx="6" fill="#5A3018" transform="rotate(18 124 118)" />
        {/* Log center */}
        <rect x="54" y="122" width="52" height="10" rx="5" fill="#6A3C20" />
        {/* Ember glow */}
        <ellipse cx="80" cy="126" rx="22" ry="7" fill="rgba(220,100,30,0.55)" style={{ filter:'blur(4px)' }} />
        {/* Flame 1 — back */}
        <path d="M80 118 C72 108 68 90 78 76 C74 88 80 96 80 96 C80 96 86 88 82 76 C92 90 88 108 80 118Z"
          fill="url(#flame-grad-1)" opacity="0.7"
          style={{ transformOrigin:'80px 118px', animation:'flame-sway-1 2.1s ease-in-out infinite' }} />
        {/* Flame 2 — front */}
        <path d="M80 116 C75 107 73 94 80 82 C77 93 82 100 82 100 C82 100 87 92 84 82 C90 94 87 108 80 116Z"
          fill="url(#flame-grad-2)"
          style={{ transformOrigin:'80px 116px', animation:'flame-sway-2 1.7s ease-in-out infinite' }} />
        {/* Spark particles */}
        <circle cx="68" cy="88" r="1.5" fill="#FFC870" opacity="0.8"
          style={{ animation:'spark-1 2.4s ease-in-out infinite' }} />
        <circle cx="92" cy="80" r="1.2" fill="#FFA040" opacity="0.6"
          style={{ animation:'spark-2 1.9s ease-in-out 0.5s infinite' }} />
        <circle cx="76" cy="72" r="1" fill="#FFD080" opacity="0.5"
          style={{ animation:'spark-1 2.8s ease-in-out 1s infinite' }} />
        <defs>
          <linearGradient id="flame-grad-1" x1="80" y1="76" x2="80" y2="118" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#FFE8A0" />
            <stop offset="40%" stopColor="#FF9020" />
            <stop offset="100%" stopColor="#CC4400" stopOpacity="0.3" />
          </linearGradient>
          <linearGradient id="flame-grad-2" x1="80" y1="82" x2="80" y2="116" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#FFFFFF" stopOpacity="0.9" />
            <stop offset="30%" stopColor="#FFB030" />
            <stop offset="100%" stopColor="#FF5500" stopOpacity="0.2" />
          </linearGradient>
        </defs>
      </svg>
      <div className="hearth-glow" />
    </div>
  );
}



/** Flip clock digit — value is always a single char '0'–'9' */
function FlipDigit({ value }) {
  const [display, setDisplay] = useState(String(value));
  const [flipping, setFlipping] = useState(false);

  useEffect(() => {
    const next = String(value);
    if (next === display) return;
    setFlipping(true);
    const t = setTimeout(() => { setDisplay(next); setFlipping(false); }, 300);
    return () => clearTimeout(t);
  }, [value]);

  return (
    <div className="flip-digit-wrap">
      <span className={`flip-digit ${flipping ? 'flipping' : ''}`}>{display}</span>
    </div>
  );
}

function FlipClock({ days }) {
  const n = Math.floor(Number(days) || 0);   // always a clean integer
  const d = String(Math.min(n, 999)).padStart(3, '0');
  return (
    <div className="hearth-flip-counter">
      {d.split('').map((ch, i) => <FlipDigit key={i} value={ch} />)}
    </div>
  );
}

/** Stage milestone overlay */
function MilestoneOverlay({ stage, partnerName, sharedDays, onDismiss }) {
  const prev = STAGE_NAMES[STAGE_NAMES.indexOf(stage) - 1] || 'Hut';
  return (
    <div className="hearth-milestone">
      <div className="hearth-milestone-emoji">{STAGE_EMOJIS[stage]}</div>
      <div className="hearth-milestone-stage">{stage}</div>
      <div className="hearth-milestone-sub">
        You and {partnerName} have been building together for {sharedDays} days
      </div>
      <div className="hearth-milestone-path">
        {STAGE_NAMES.filter(s => s !== 'Castle').map((s, i) => (
          <span key={s}>
            <span className={s === stage ? 'active-stage' : ''}>{s.toUpperCase()}</span>
            {i < STAGE_NAMES.length - 2 && <span> ——— </span>}
          </span>
        ))}
      </div>
      <div className="hearth-milestone-actions">
        <button className="btn-milestone-primary" onClick={() => {
          if (navigator.share) {
            navigator.share({ title: `${stage} unlocked!`, text: `${sharedDays} days together on Recall Hearth 🔥` });
          }
        }}>Share this moment</button>
        <button className="btn-milestone-secondary" onClick={onDismiss}>Continue building</button>
      </div>
    </div>
  );
}

/** Block drop toast */
function BlockToast({ days, onHide }) {
  const [hiding, setHiding] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => { setHiding(true); setTimeout(onHide, 350); }, 3000);
    return () => clearTimeout(t);
  }, []);
  return (
    <div className={`hearth-toast ${hiding ? 'hiding' : ''}`}>
      <span className="toast-icon">🏗</span>
      <div>
        <div className="toast-title">Block placed</div>
        <div className="toast-sub">{days} days together</div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   MAIN COMPONENT
   ═══════════════════════════════════════════════════════════════════════════ */

/* ── Dev test panel ──────────────────────────────────────────────────────── */
function DevPanel({ onSelect }) {
  const [open, setOpen] = useState(false);
  if (!IS_DEV) return null;
  return (
    <div className="hearth-dev-panel">
      {open && (
        <div className="hearth-dev-menu">
          {DEV_PRESETS.map((p) => (
            <button
              key={p.label}
              className="hearth-dev-btn"
              onClick={() => { onSelect(p); setOpen(false); }}
            >
              {p.label}
            </button>
          ))}
        </div>
      )}
      <button className="hearth-dev-toggle" onClick={() => setOpen(o => !o)}>
        {open ? '✕ close' : '⚗ dev preview'}
      </button>
    </div>
  );
}

export default function Hearth() {
  const [journeys,      setJourneys]      = useState([]);     // all active journeys from API
  const [loading,       setLoading]       = useState(true);
  const [activeJourney, setActiveJourney] = useState(null);   // null = hub/landing
  const [inviteCode,    setInviteCode]    = useState('');
  const [acceptInput,   setAcceptInput]   = useState('');
  const [acceptErr,     setAcceptErr]     = useState('');
  const [connecting,    setConnecting]    = useState(false);
  const [milestone,     setMilestone]     = useState(null);
  const [toast,         setToast]         = useState(false);
  const [copied,        setCopied]        = useState(false);
  const [settingsOpen,  setSettingsOpen]  = useState(false);
  const [leaveTarget,   setLeaveTarget]   = useState(null);   // journey to confirm-leave
  const [leaving,       setLeaving]       = useState(false);  // loading state for leave
  const [showInviteForm, setShowInviteForm] = useState(false); // new-journey invite panel in hub

  const prevStageRef  = useRef(null);
  const replayFnRef   = useRef(null);
  const devModeActive = useRef(false);

  /* ── Dev preset handler ──────────────────────────────────────────────── */
  const handleDevSelect = useCallback((preset) => {
    devModeActive.current = true;
    setMilestone(null);
    setToast(false);
    setConnecting(false);
    setLoading(false);
    setActiveJourney(null);
    setLeaveTarget(null);

    if (preset.state === 'unpaired') {
      devModeActive.current = false;
      setJourneys([]);
    } else if (preset.state === 'connecting') {
      setJourneys([]);
      setConnecting(true);
      setTimeout(() => {
        setConnecting(false);
        const newJourney = { pair_id:'dev-new', is_paired:true, shared_days:1, score:0.8,
          stage:'Hut', partner_name:'Alex', partner_active_today:true, self_active_today:true };
        setJourneys([newJourney]);
        setActiveJourney(newJourney);
      }, 4500);
    } else if (preset.state === 'simulate') {
      localStorage.removeItem('hearth_last_seen_score');
      const j = { pair_id:'dev-sim', is_paired:true, shared_days:80, score:51.4,
        stage:'Manor', partner_name:'Alex', partner_active_today:true, self_active_today:true };
      setJourneys([j]);
      setActiveJourney(j);
    } else if (preset.journeys) {
      // hub view with multiple journeys
      setJourneys(preset.journeys);
    } else if (preset.journey) {
      // enter directly into a single journey's 3D view
      setJourneys([preset.journey]);
      if (preset.milestone) setMilestone(preset.milestone);
      if (preset.toast)     setToast(true);
      setActiveJourney(preset.journey);
    }
  }, []);

  /* ── Fetch hearth state ─────────────────────────────────────────────── */
  const fetchHearth = useCallback(async () => {
    if (devModeActive.current) return;
    try {
      const r = await fetch('/api/hearth', { credentials: 'include' });
      if (!r.ok) return;
      const data = await r.json();
      const newJourneys = data.journeys || [];
      setJourneys(prev => {
        // Detect new journey added (pairing just completed)
        if (newJourneys.length > prev.length && newJourneys.length === 1) {
          setActiveJourney(newJourneys[0]);
        }
        // Detect stage change or score increase on active journey
        if (activeJourney) {
          const updated = newJourneys.find(j => j.pair_id === activeJourney.pair_id);
          if (updated) {
            if (updated.stage !== activeJourney.stage && updated.stage !== 'Hut') {
              setMilestone(updated.stage);
            }
            if (updated.score > activeJourney.score) setToast(true);
            setActiveJourney(updated);
          }
        }
        return newJourneys;
      });
    } catch { /* silently fail */ }
    finally { setLoading(false); }
  }, [activeJourney]);

  useEffect(() => {
    if (!devModeActive.current) fetchHearth();
    const interval = setInterval(fetchHearth, 30_000);
    return () => clearInterval(interval);
  }, [fetchHearth]);

  /* ── Generate invite ────────────────────────────────────────────────── */
  const generateInvite = async () => {
    try {
      const r = await fetch('/api/hearth/invite', { method: 'POST', credentials: 'include' });
      const d = await r.json();
      if (d.invite_code) setInviteCode(d.invite_code);
    } catch { /* ignore */ }
  };

  /* ── Accept invite ──────────────────────────────────────────────────── */
  const acceptInvite = async () => {
    setAcceptErr('');
    try {
      const r = await fetch('/api/hearth/accept', {
        method: 'POST', credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ invite_code: acceptInput.trim() }),
      });
      const d = await r.json();
      if (d.success) {
        setConnecting(true);
        setTimeout(() => { setConnecting(false); fetchHearth(); }, 4500);
      } else {
        setAcceptErr(d.detail || 'Invalid code');
      }
    } catch { setAcceptErr('Something went wrong'); }
  };

  /* ── Leave journey (hard delete) ────────────────────────────────────── */
  const confirmLeave = async () => {
    if (!leaveTarget) return;
    setLeaving(true);
    try {
      await fetch(`/api/hearth/leave/${leaveTarget.pair_id}`, {
        method: 'DELETE', credentials: 'include',
      });
      const remaining = journeys.filter(j => j.pair_id !== leaveTarget.pair_id);
      setJourneys(remaining);
      setActiveJourney(null);
      setLeaveTarget(null);
    } catch { /* silently fail — user stays on screen */ }
    finally { setLeaving(false); }
  };

  /* ── Copy code ──────────────────────────────────────────────────────── */
  const copyCode = () => {
    navigator.clipboard.writeText(inviteCode).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  /* ═══════════════════════════════════════════════════════════════════════
     RENDER: LOADING
  ═══════════════════════════════════════════════════════════════════════ */
  if (loading) {
    return (
      <div className="hearth-root">
        <style>{HEARTH_CSS}</style>
        <div style={{ position:'absolute', inset:0, display:'flex', alignItems:'center', justifyContent:'center' }}>
          <span style={{ fontFamily:'JetBrains Mono,monospace', fontSize:11, letterSpacing:'0.2em', color:'#4A4845' }}>
            LIGHTING...
          </span>
        </div>
        <DevPanel onSelect={handleDevSelect} />
      </div>
    );
  }

  /* ═══════════════════════════════════════════════════════════════════════
     RENDER: INSIDE A JOURNEY (3D full-screen view)
  ═══════════════════════════════════════════════════════════════════════ */
  if (activeJourney) {
    const { score, shared_days, stage, partner_name, partner_active_today, pair_id } = activeJourney;
    const progressPct = Math.min(100, (score / 96) * 100);
    const toNext      = daysToNext(stage, shared_days);
    const dotClass    = partner_active_today ? 'active-today' : (shared_days > 0 ? 'active-recent' : 'inactive');

    return (
      <div className="hearth-root">
        <style>{HEARTH_CSS}</style>

        {/* 3D building full screen */}
        <div className={`hearth-canvas-wrap ${partner_active_today ? 'partner-active-today' : ''}`}>
          <Suspense fallback={<div style={{ background:'#0C0B0F', inset:0, position:'absolute' }} />}>
            <BranchingPOC
              key={pair_id}
              externalScore={score}
              hearthMode
              pairId={pair_id}
              onReplayReady={(fn) => { replayFnRef.current = fn; }}
            />
          </Suspense>
        </div>

        {/* Back button — returns to journey hub */}
        <button className="hearth-back-btn" onClick={() => { setActiveJourney(null); setSettingsOpen(false); }}>
          ← Journeys
        </button>

        {/* HUD */}
        <div className="hearth-hud">
          {/* Top-right: partner chip + settings */}
          <div className="hearth-hud-top">
            <div className="hearth-partner-chip">
              <div className="hearth-partner-avatar">
                {partner_name?.[0]?.toUpperCase() || '?'}
                <div className={`hearth-partner-dot ${dotClass}`} />
              </div>
              <div>
                <div className="hearth-partner-name">{partner_name}</div>
                <div className="hearth-partner-status">
                  {partner_active_today ? '● active today' : '● last seen recently'}
                </div>
              </div>
            </div>
            <div style={{ position: 'relative', display: 'flex', gap: '4px' }}>
              <button
                className={`hearth-hud-settings ${settingsOpen ? 'active' : ''}`}
                title="Settings"
                onClick={() => setSettingsOpen(o => !o)}
              >⚙</button>
              <button
                className="hearth-replay-btn"
                title="Watch your journey from the beginning"
                onClick={() => { replayFnRef.current?.(); setSettingsOpen(false); }}
              >↺</button>

              {settingsOpen && (
                <div className="hearth-settings-dropdown">
                  <button className="hsd-item" onClick={() => { replayFnRef.current?.(); setSettingsOpen(false); }}>
                    <span className="hsd-icon">↺</span>
                    <span>Watch journey from start</span>
                  </button>
                  <div className="hsd-divider" />
                  <button className="hsd-item" onClick={() => setSettingsOpen(false)}>
                    <span className="hsd-icon">🔗</span>
                    <span>Share invite code</span>
                  </button>
                  <button className="hsd-item hsd-danger" onClick={() => {
                    setLeaveTarget(activeJourney);
                    setSettingsOpen(false);
                  }}>
                    <span className="hsd-icon">✕</span>
                    <span>Leave journey</span>
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Bottom: stage + days */}
          <div className="hearth-hud-bottom">
            <div className="hearth-progress-card">
              <span className="hearth-stage-label">Current Stage</span>
              <span className="hearth-stage-name">{stage} {STAGE_EMOJIS[stage]}</span>
              <div className="hearth-progress-track">
                <div className="hearth-progress-fill" style={{ width: `${progressPct}%` }} />
              </div>
              <span className="hearth-next-label">
                {toNext !== null ? `${toNext} more days to ${nextStage(stage)}` : 'Maximum stage reached'}
              </span>
            </div>
            <div className="hearth-days-card">
              <FlipClock days={Math.floor(shared_days || 0)} />
              <span className="hearth-days-label">Days Together</span>
            </div>
          </div>
        </div>

        {toast && <BlockToast days={shared_days} onHide={() => setToast(false)} />}
        {milestone && (
          <MilestoneOverlay
            stage={milestone} partnerName={partner_name}
            sharedDays={shared_days} onDismiss={() => setMilestone(null)}
          />
        )}

        {/* Leave warning modal */}
        {leaveTarget && (
          <div className="hearth-leave-overlay" onClick={() => setLeaveTarget(null)}>
            <div className="hearth-leave-modal" onClick={e => e.stopPropagation()}>
              <div className="hlm-avatar">{partner_name?.[0]?.toUpperCase() || '?'}</div>
              <div className="hlm-title">Leave journey with {partner_name}?</div>
              <div className="hlm-sub">{stage} · {Math.floor(shared_days)} days together</div>
              <div className="hlm-warning">
                This journey will be permanently deleted. If you reconnect with {partner_name}, you'll start from Hut again.
              </div>
              <div className="hlm-actions">
                <button className="hlm-cancel" onClick={() => setLeaveTarget(null)}>Cancel</button>
                <button className="hlm-confirm" onClick={confirmLeave} disabled={leaving}>
                  {leaving ? 'Leaving…' : 'Delete Journey'}
                </button>
              </div>
            </div>
          </div>
        )}

        <DevPanel onSelect={handleDevSelect} />
      </div>
    );
  }

  /* ═══════════════════════════════════════════════════════════════════════
     RENDER: JOURNEY HUB (has journeys, no active selection)
  ═══════════════════════════════════════════════════════════════════════ */
  if (journeys.length > 0) {
    return (
      <div className="hearth-root">
        <style>{HEARTH_CSS}</style>
        <div className="hearth-fog hearth-fog-1" />
        <div className="hearth-fog hearth-fog-2" />

        <div className="hearth-hub">
          <p className="hearth-hub-title">Your Journeys</p>

          <div className="hearth-hub-grid">
            {journeys.map((j, idx) => {
              const pct = Math.min(100, (j.score / 96) * 100);
              return (
                <div
                  key={j.pair_id}
                  className={`hearth-journey-card${j.partner_active_today ? ' partner-online' : ''}`}
                  style={{ animationDelay: `${idx * 0.07}s` }}
                  onClick={() => setActiveJourney(j)}
                >
                  <div className="hjc-avatar">{j.partner_name?.[0]?.toUpperCase() || '?'}</div>
                  <div className="hjc-name">{j.partner_name}</div>
                  <div className="hjc-stage">{STAGE_EMOJIS[j.stage]} {j.stage}</div>
                  <div className="hjc-days">{Math.floor(j.shared_days)}</div>
                  <div className="hjc-days-label">Days Together</div>
                  <div className="hjc-bar">
                    <div className="hjc-bar-fill" style={{ width: `${pct}%` }} />
                  </div>
                </div>
              );
            })}
          </div>

          <div className="hearth-hub-actions">
            <button className="btn-new-journey" onClick={() => { setShowInviteForm(true); setInviteCode(''); setAcceptInput(''); setAcceptErr(''); }}>
              ＋ New Journey
            </button>
          </div>
        </div>

        {/* New Journey invite panel — slides up over the hub */}
        {showInviteForm && (
          <div className="hearth-leave-overlay" onClick={() => setShowInviteForm(false)}>
            <div className="hearth-leave-modal" style={{ maxWidth: 420, textAlign: 'left' }} onClick={e => e.stopPropagation()}>
              <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:20 }}>
                <button onClick={() => setShowInviteForm(false)}
                  style={{ background:'none', border:'none', color:'#8A8582', fontSize:18, cursor:'pointer', padding:'0 4px' }}>←</button>
                <span style={{ fontSize:15, fontWeight:500, color:'#F0EDE8', fontFamily:'Outfit,sans-serif' }}>Start a New Journey</span>
              </div>

              {inviteCode ? (
                <div className="hearth-code-wrap">
                  <span className="hearth-code-text">{inviteCode}</span>
                  <button className="hearth-code-btn" onClick={copyCode}>{copied ? 'COPIED' : 'COPY'}</button>
                  <button className="hearth-code-btn" onClick={() => {
                    if (navigator.share) navigator.share({
                      title: 'Light my Hearth',
                      text: `Join me on Recall Hearth: ${inviteCode}`,
                      url: `https://t.me/recall_bot?start=hearth_${inviteCode}`,
                    });
                  }}>SHARE</button>
                </div>
              ) : (
                <button className="hearth-cta-btn" style={{ marginBottom: 16 }} onClick={generateInvite}>
                  Generate Invite Code
                </button>
              )}

              <div style={{ width:'100%', display:'flex', flexDirection:'column', gap:8 }}>
                <input
                  className="hearth-accept-input"
                  placeholder="Have a code? Enter it here — RCL-XXXX-XXXX"
                  value={acceptInput}
                  onChange={e => setAcceptInput(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && acceptInvite()}
                />
                {acceptInput.length > 3 && (
                  <button className="hearth-cta-btn" style={{ marginTop:0 }} onClick={acceptInvite}>
                    Join Journey
                  </button>
                )}
                {acceptErr && (
                  <span style={{ fontSize:11, color:'#8A5A3A', letterSpacing:'0.08em', fontFamily:'JetBrains Mono,monospace' }}>
                    {acceptErr}
                  </span>
                )}
              </div>
            </div>
          </div>
        )}

        <DevPanel onSelect={handleDevSelect} />
      </div>
    );
  }

  /* ═══════════════════════════════════════════════════════════════════════
     RENDER: LANDING (no journeys — invite flow)
  ═══════════════════════════════════════════════════════════════════════ */
  return (
    <div className="hearth-root">
      <style>{HEARTH_CSS}</style>

      <div className="hearth-fog hearth-fog-1" />
      <div className="hearth-fog hearth-fog-2" />
      <div className="hearth-fog hearth-fog-3" />

      {connecting && (
        <div className="hearth-connect-overlay">
          <span className="hearth-first-flame">Your first flame</span>
        </div>
      )}

      <div className="hearth-landing">
        <h1 className="hearth-title">Hearth</h1>
        <p className="hearth-subtitle">A home grows where curiosity lives</p>

        <CSSHut />

        <div className="hearth-card">
          <div className="hearth-avatars">
            <div className="hearth-avatar-slot">
              <div className="hearth-avatar-circle self-avatar">✦</div>
              <span className="hearth-avatar-label">You</span>
            </div>
            <div className="hearth-connector">
              <div className="hearth-connector-light" />
            </div>
            <div className="hearth-avatar-slot">
              <div className="hearth-avatar-circle partner-empty">
                {inviteCode ? '···' : '+'}
              </div>
              <span className="hearth-avatar-label">Waiting…</span>
            </div>
          </div>

          {inviteCode ? (
            <div className="hearth-code-wrap">
              <span className="hearth-code-text">{inviteCode}</span>
              <button className="hearth-code-btn" onClick={copyCode}>
                {copied ? 'COPIED' : 'COPY'}
              </button>
              <button className="hearth-code-btn" onClick={() => {
                if (navigator.share) navigator.share({
                  title: 'Light my Hearth',
                  text: `Join me on Recall Hearth: ${inviteCode}`,
                  url: `https://t.me/recall_bot?start=hearth_${inviteCode}`,
                });
              }}>SHARE</button>
            </div>
          ) : (
            <button className="hearth-cta-btn" onClick={generateInvite}>
              Light your Hearth
            </button>
          )}

          <div style={{ width:'100%', display:'flex', flexDirection:'column', gap:8 }}>
            <input
              className="hearth-accept-input"
              placeholder="Have a code? Enter it here — RCL-XXXX-XXXX"
              value={acceptInput}
              onChange={e => setAcceptInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && acceptInvite()}
            />
            {acceptInput.length > 3 && (
              <button className="hearth-cta-btn" style={{ marginTop:0 }} onClick={acceptInvite}>
                Join Hearth
              </button>
            )}
            {acceptErr && (
              <span style={{ fontSize:11, color:'#8A5A3A', letterSpacing:'0.08em', fontFamily:'JetBrains Mono,monospace' }}>
                {acceptErr}
              </span>
            )}
          </div>
        </div>
      </div>

      <DevPanel onSelect={handleDevSelect} />
    </div>
  );
}

