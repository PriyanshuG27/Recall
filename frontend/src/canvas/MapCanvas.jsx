import React, { useRef, useEffect } from 'react';
import * as d3 from 'd3';
import AudioEngine from '../utils/AudioEngine';

/* ── Palette ─────────────────────────────────────────────────────────────── */
const COLORS = {
  url: '#7C6FD4', voice: '#3DAA8A', pdf: '#C9893C',
  image: '#3D8AAA', text: '#8A8582', hub: '#CFA365', default: '#8A7A6A',
};
function nodeColor(n) {
  if (n.type === 'hub') {
    const daysSince = n.daysSince ?? 0;
    if (daysSince <= 1) return COLORS.hub;
    if (daysSince >= 7) return '#8A8582';
    const ratio = (daysSince - 1) / 6;
    const r = Math.round(207 - (207 - 138) * ratio);
    const g = Math.round(163 - (163 - 133) * ratio);
    const b = Math.round(101 - (101 - 130) * ratio);
    return `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}${b.toString(16).padStart(2, '0')}`;
  }
  return COLORS[n.source_type] || COLORS.default;
}
function isHub(n)     { return n.type === 'hub'; }
function nodeR(n)     { return isHub(n) ? 14 : 6; }
function ha(hex, a)   { return hex + Math.round(Math.max(0, Math.min(1, a)) * 255).toString(16).padStart(2, '0'); }

/* ── Stars ───────────────────────────────────────────────────────────────── */
function makeStars(W, H) {
  return Array.from({ length: 160 }, () => ({
    x: Math.random() * W, y: Math.random() * H,
    r: 0.3 + Math.random() * 0.65,
    a: 0.02 + Math.random() * 0.055,
    ph: Math.random() * Math.PI * 2,
    sp: 0.2 + Math.random() * 0.45,
  }));
}

/* ══════════════════════════════════════════════════════════════════════════
   MapCanvas — stable layout, customizable physics and search overlays
   ══════════════════════════════════════════════════════════════════════════ */
export default function MapCanvas({
  nodes = [], edges = [],
  activeCandidates = [],
  filterType = 'all',
  selectedNodeId = null,
  selectedHubId  = null,
  flareNodeId    = null,
  searchQuery = '',
  physicsFrozen = false,
  showLabels = 'hover',
  gapsMode = false,
  burstHubId = null,
  onNodeClick,
}) {
  const canvasRef = useRef(null);
  const s = useRef({
    simNodes: [], simLinks: [],
    hovered: null, transform: { x: 0, y: 0, k: 1 },
    isDragging: false, dragNode: null, panStart: null,
    rafId: null, filterType: 'all',
    selectedNodeId: null, selectedHubId: null, flareNodeId: null,
    searchQuery: '', physicsFrozen: false, showLabels: 'hover',
    gapsMode: false, burstHubId: null,
    activeCandidates: [],
    alive: false, stars: [],
  });

  useEffect(() => { s.current.filterType     = filterType;    }, [filterType]);
  useEffect(() => { s.current.selectedNodeId = selectedNodeId; }, [selectedNodeId]);
  useEffect(() => { s.current.selectedHubId  = selectedHubId;  }, [selectedHubId]);
  useEffect(() => { s.current.flareNodeId    = flareNodeId;    }, [flareNodeId]);
  useEffect(() => { s.current.searchQuery    = searchQuery;   }, [searchQuery]);
  useEffect(() => { s.current.showLabels     = showLabels;    }, [showLabels]);
  useEffect(() => { s.current.gapsMode       = gapsMode;      }, [gapsMode]);
  useEffect(() => { s.current.burstHubId     = burstHubId;    }, [burstHubId]);
  useEffect(() => { s.current.activeCandidates = activeCandidates; }, [activeCandidates]);

  useEffect(() => {
    s.current.physicsFrozen = physicsFrozen;
    if (s.current.sim) {
      if (physicsFrozen) s.current.sim.stop();
      else s.current.sim.alpha(0.08).restart();
    }
  }, [physicsFrozen]);

  /* ── Auto-Fit Camera Event Listener ─────────────────────────────────── */
  useEffect(() => {
    const handleAutoFit = () => {
      const canvas = canvasRef.current;
      if (!canvas || s.current.simNodes.length === 0) return;
      const W = canvas.width;
      const H = canvas.height;
      const sn = s.current.simNodes;

      let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
      sn.forEach(n => {
        if (n.x == null) return;
        if (n.x < minX) minX = n.x;
        if (n.x > maxX) maxX = n.x;
        if (n.y < minY) minY = n.y;
        if (n.y > maxY) maxY = n.y;
      });

      const dW = maxX - minX || 100;
      const dH = maxY - minY || 100;
      const pad = 120; // safe padding

      const k = Math.max(0.18, Math.min(2.0, Math.min((W - pad) / dW, (H - pad) / dH)));
      const tx = W / 2 - k * (minX + dW / 2);
      const ty = H / 2 - k * (minY + dH / 2);

      s.current.transform = { x: tx, y: ty, k };
    };

    window.addEventListener('map-autofit', handleAutoFit);
    return () => window.removeEventListener('map-autofit', handleAutoFit);
  }, []);

  /* ── Simulation: pre-settle 140 ticks then go live ─────────────────── */
  useEffect(() => {
    if (nodes.length === 0) return;
    const canvas = canvasRef.current;
    const W = canvas?.offsetWidth  || window.innerWidth;
    const H = canvas?.offsetHeight || window.innerHeight;
    const st = s.current;

    const prev = {};
    st.simNodes.forEach(n => { prev[n.id] = { x: n.x, y: n.y, vx: n.vx, vy: n.vy }; });

    const sn = nodes.map(n => {
      const p = prev[n.id];
      return {
        ...n,
        x:  p ? p.x : (n._sx ?? W / 2 + (Math.random() - 0.5) * 200),
        y:  p ? p.y : (n._sy ?? H / 2 + (Math.random() - 0.5) * 200),
        vx: p?.vx ?? 0,
        vy: p?.vy ?? 0,
      };
    });

    const idSet = new Set(sn.map(n => n.id));
    const sl = edges
      .map(e => ({
        ...e,
        source: typeof e.source === 'object' ? e.source.id : e.source,
        target: typeof e.target === 'object' ? e.target.id : e.target,
      }))
      .filter(e => idSet.has(e.source) && idSet.has(e.target));

    if (st.sim) st.sim.stop();

    const sim = d3.forceSimulation(sn)
      .force('link', d3.forceLink(sl).id(d => d.id)
        .distance(65).strength(link => {
          let str = 0.75;
          const hub = isHub(link.source) ? link.source : (isHub(link.target) ? link.target : null);
          if (hub && hub.daysSince >= 7) {
            str *= Math.max(0.2, 1.0 - (hub.daysSince - 7) / 23);
          }
          return str;
        }))
      .force('charge', d3.forceManyBody()
        .strength(n => isHub(n) ? -130 : -30)
        .distanceMax(280))
      .force('x', d3.forceX(W / 2).strength(0.035))
      .force('y', d3.forceY(H / 2).strength(0.035))
      .force('collide', d3.forceCollide()
        .radius(n => nodeR(n) + (isHub(n) ? 22 : 9))
        .strength(0.8))
      .velocityDecay(0.4)
      .stop();

    sim.tick(140);

    if (!st.physicsFrozen) {
      sim.restart();
    }

    st.sim      = sim;
    st.simNodes = sn;
    st.simLinks = sl;

    return () => st.sim?.stop();
  }, [nodes.length, edges.length]);

  /* ── Resize + stars ─────────────────────────────────────────────────── */
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const resize = () => {
      canvas.width  = canvas.offsetWidth;
      canvas.height = canvas.offsetHeight;
      s.current.stars = makeStars(canvas.width, canvas.height);
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);
    return () => ro.disconnect();
  }, []);

  /* ── Bind non-passive scroll/touch listeners manually to prevent browser warnings ── */
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const onWheel = (e) => {
      handleWheel(e);
    };
    const onTouchStart = (e) => {
      handleTouchStart(e);
    };
    const onTouchMove = (e) => {
      handleTouchMove(e);
    };

    canvas.addEventListener('wheel', onWheel, { passive: false });
    canvas.addEventListener('touchstart', onTouchStart, { passive: false });
    canvas.addEventListener('touchmove', onTouchMove, { passive: false });

    return () => {
      canvas.removeEventListener('wheel', onWheel);
      canvas.removeEventListener('touchstart', onTouchStart);
      canvas.removeEventListener('touchmove', onTouchMove);
    };
  }, []);

  /* ── Draw loop ───────────────────────────────────────────────────────── */
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const st  = s.current;
    st.alive  = true;

    function draw() {
      if (!st.alive) return;
      st.rafId = requestAnimationFrame(draw);

      const W  = canvas.width;
      const H  = canvas.height;
      const {x: tx, y: ty, k} = st.transform;
      const sn = st.simNodes;
      const sl = st.simLinks;
      const fil = st.filterType;
      const sel = st.selectedNodeId;
      const hub = st.selectedHubId;
      const hov = st.hovered;
      const query = (st.searchQuery || '').trim().toLowerCase();
      const burstId = st.burstHubId;
      const flareId = st.flareNodeId;
      const gaps = st.gapsMode;
      const now = performance.now() * 0.001;

      ctx.clearRect(0, 0, W, H);

      /* Stars */
      st.stars.forEach(star => {
        const a  = star.a * (0.5 + 0.5 * Math.sin(now * star.sp + star.ph));
        const sx = ((star.x + tx * 0.05) % W + W) % W;
        const sy = ((star.y + ty * 0.05) % H + H) % H;
        ctx.beginPath();
        ctx.arc(sx, sy, star.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(255,245,220,${a})`;
        ctx.fill();
      });

      ctx.save();
      ctx.translate(tx, ty);
      ctx.scale(k, k);

      /* ── Search Query Highlights ──────────────────────────────────── */
      const matches = new Set();
      if (query) {
        sn.forEach(n => {
          if (isHub(n)) {
            const memberMatches = (n._members || []).some(mid => {
              const m = sn.find(x => x.id === mid);
              return m && (
                (m.title || '').toLowerCase().includes(query) || 
                (m.summary || '').toLowerCase().includes(query)
              );
            });
            if (n.title.toLowerCase().includes(query) || memberMatches) {
              matches.add(n.id);
            }
          } else {
            if (
              (n.title || '').toLowerCase().includes(query) || 
              (n.summary || '').toLowerCase().includes(query) ||
              (n.raw_text || '').toLowerCase().includes(query)
            ) {
              matches.add(n.id);
            }
          }
        });
      }

      /* ── Highlight sets ───────────────────────────────────────────── */
      const litEdges = new Set();
      const litNodes = new Set();
      const anySel   = sel != null || hub != null;

      if (hub != null) {
        litNodes.add(hub);
        sl.forEach(link => {
          const sid = typeof link.source === 'object' ? link.source.id : link.source;
          const tid = typeof link.target === 'object' ? link.target.id : link.target;
          if (sid === hub || tid === hub) { litEdges.add(link); litNodes.add(sid); litNodes.add(tid); }
        });
      }
      if (sel != null) {
        litNodes.add(sel);
        sl.forEach(link => {
          const sid = typeof link.source === 'object' ? link.source.id : link.source;
          const tid = typeof link.target === 'object' ? link.target.id : link.target;
          if (sid === sel || tid === sel) { litEdges.add(link); litNodes.add(sid); litNodes.add(tid); }
        });
      }

      /* ── Hub halos — recency-encoded glow (T4.1) ─────────────────────── */
      sn.forEach(n => {
        if (!isHub(n) || n.x == null) return;
        const col    = nodeColor(n);
        const pulse  = 0.5 + 0.5 * Math.sin(now * 0.4 + Math.abs(n.id) * 0.8);
        const isHSel = n.id === hub;
        const inSearch = query ? matches.has(n.id) : false;

        // T4.1: recency dims older hubs
        const daysSince = n.daysSince ?? 999;
        const recencyMult = daysSince < 1 ? 1.0 : daysSince < 7 ? 0.65 : daysSince < 30 ? 0.35 : 0.12;
        
        let haloR  = isHSel ? 90 + pulse * 20 : 45 + pulse * 10;
        if (inSearch) haloR += 15;

        const g = ctx.createRadialGradient(n.x, n.y, 0, n.x, n.y, haloR);
        let alpha = (isHSel ? 0.12 + pulse * 0.04 : 0.055 + pulse * 0.02) * recencyMult;
        if (query && !inSearch) alpha *= 0.05;

        g.addColorStop(0, ha(col, alpha));
        g.addColorStop(1, ha(col, 0));
        ctx.beginPath();
        ctx.arc(n.x, n.y, haloR, 0, Math.PI * 2);
        ctx.fillStyle = g;
        ctx.fill();
      });

      /* ── Edges ─────────────────────────────────────────────────────── */
      sl.forEach(link => {
        const src = typeof link.source === 'object' ? link.source : sn.find(n => n.id === link.source);
        const tgt = typeof link.target === 'object' ? link.target : sn.find(n => n.id === link.target);
        if (!src || !tgt || src.x == null || tgt.x == null) return;

        // Level-of-Detail (LOD): Zoomed out hides non-hub connection edges
        const srcHub = isHub(src);
        const tgtHub = isHub(tgt);
        if (k < 0.8 && (!srcHub || !tgtHub)) {
          return;
        }

        // Cold Storage: Hide connection lines for cold nodes (daysSince >= 30)
        const srcCold = !srcHub && (src.daysSince ?? 0) >= 30;
        const tgtCold = !tgtHub && (tgt.daysSince ?? 0) >= 30;
        if ((srcCold || tgtCold) && !litEdges.has(link)) {
          return;
        }

        const isLit = litEdges.has(link);
        let alpha;
        if (query) {
          const bothMatch = matches.has(src.id) && matches.has(tgt.id);
          alpha = bothMatch ? 0.8 : 0.01;
        } else if (!anySel && hov == null) {
          alpha = 0.28;
        } else if (isLit) {
          alpha = 0.9;
        } else if (hov != null) {
          alpha = (src.id === hov || tgt.id === hov) ? 0.7 : 0.04;
        } else {
          alpha = 0.03;
        }

        if (fil !== 'all') {
          const sm = src.source_type === fil || isHub(src);
          const tm = tgt.source_type === fil || isHub(tgt);
          if (!sm && !tm) alpha *= 0.04;
        }

        const hubN  = isHub(src) ? src : (isHub(tgt) ? tgt : null);
        const itemN = isHub(src) ? tgt : src;
        if (hubN) {
          const grd = ctx.createLinearGradient(hubN.x, hubN.y, itemN.x, itemN.y);
          grd.addColorStop(0, ha(nodeColor(hubN),  alpha));
          grd.addColorStop(1, ha(nodeColor(itemN), alpha * 0.4));
          ctx.beginPath();
          ctx.moveTo(src.x, src.y);
          ctx.lineTo(tgt.x, tgt.y);
          ctx.strokeStyle = grd;
          ctx.lineWidth   = isLit ? 1.6 / k : 0.9 / k;
        } else {
          ctx.beginPath();
          ctx.moveTo(src.x, src.y);
          ctx.lineTo(tgt.x, tgt.y);
          ctx.strokeStyle = `rgba(138,133,130,${alpha * 0.45})`;
          ctx.lineWidth   = 0.5 / k;
        }
        ctx.stroke();
      });

      // Render active candidate connections (Drift Windows and Near-Misses)
      if (st.activeCandidates && st.activeCandidates.length > 0) {
        st.activeCandidates.forEach(cand => {
          const nodeA = sn.find(n => n.id === cand.item_id_a);
          const nodeB = sn.find(n => n.id === cand.item_id_b);
          if (nodeA && nodeB && nodeA.x != null && nodeB.x != null) {
            if (cand.status === 'near_miss') {
              // Only draw near-miss when hovering one of its nodes
              if (hov !== cand.item_id_a && hov !== cand.item_id_b) {
                return;
              }
              // Faint, low-opacity edge
              ctx.save();
              ctx.beginPath();
              ctx.moveTo(nodeA.x, nodeA.y);
              ctx.lineTo(nodeB.x, nodeB.y);
              ctx.strokeStyle = 'rgba(138,133,130,0.28)'; // faint gray
              ctx.lineWidth = 1.0 / k;
              ctx.setLineDash([4, 4]); // dashed line to indicate "almost connected"
              ctx.stroke();
              ctx.restore();
            } else {
              // Calculate remaining time ratio against 6 hours (21600 seconds)
              const expiresAt = new Date(cand.expires_at).getTime();
              const now = Date.now();
              const timeLeftMs = Math.max(0, expiresAt - now);
              const totalDurationMs = 6 * 60 * 60 * 1000;
              const ratio = Math.min(1.0, timeLeftMs / totalDurationMs);

              // Pulsing effect for lineWidth
              const pulse = Math.sin(now / 150) * 0.4 + 1.2; // fluctuates between 0.8 and 1.6
              const lineWidth = (pulse * ratio) / k;

              // Opacity decay
              const baseAlpha = 0.95;
              let alpha = baseAlpha * ratio;

              // Context-aware dimming: fade drift edges that do not connect to the focused/selected subgraph
              if (query) {
                const bothMatch = matches.has(nodeA.id) && matches.has(nodeB.id);
                if (!bothMatch) alpha *= 0.01;
              } else if (anySel) {
                const isLit = litNodes.has(nodeA.id) || litNodes.has(nodeB.id);
                if (!isLit) alpha *= 0.03;
              } else if (hov != null) {
                const isNearHov = nodeA.id === hov || nodeB.id === hov;
                if (!isNearHov) alpha *= 0.04;
              }

              // Interpolate color desaturation: glowing gold/orange (230, 160, 60) -> desaturated gray (138, 133, 130)
              const r = Math.round(230 * ratio + 138 * (1 - ratio));
              const g = Math.round(160 * ratio + 133 * (1 - ratio));
              const b = Math.round(60 * ratio + 130 * (1 - ratio));

              ctx.beginPath();
              ctx.moveTo(nodeA.x, nodeA.y);
              ctx.lineTo(nodeB.x, nodeB.y);
              ctx.strokeStyle = `rgba(${r},${g},${b},${alpha})`;
              ctx.lineWidth = lineWidth;
              ctx.stroke();
            }
          }
        });
      }

      /* ── Nodes ─────────────────────────────────────────────────────── */
      sn.forEach(node => {
        if (node.x == null) return;
        const hubNode  = isHub(node);
        const isSel    = node.id === sel;
        const isHubSel = node.id === hub;
        const isHov    = node.id === hov;
        const isLit    = litNodes.has(node.id);

        // Level-of-Detail (LOD): Zoomed out hides non-hub stars
        if (k < 0.8 && !hubNode && !isSel && !isHov && !isLit) {
          return;
        }

        // Cold Storage: Skip drawing individual nodes that are cold (daysSince >= 30)
        const isCold = !hubNode && (node.daysSince ?? 0) >= 30;
        if (isCold && !isSel && !isHov && !isLit) {
          return;
        }

        const col      = nodeColor(node);
        const r        = nodeR(node);
        const inSearch = query ? matches.has(node.id) : true;

        // T4.1: desaturate very old hub nodes (30+ days) via opacity
        const daysSince = node.daysSince ?? 0;
        const recencyOpacityMult = hubNode && daysSince >= 30 ? 0.35 : 1;

        // T4.3: burst expansion — non-members of the burst hub fade out
        let burstOpacityMult = 1;
        if (burstId != null && hubNode) {
          burstOpacityMult = node.id === burstId ? 1 : 0.08;
        } else if (burstId != null && !hubNode) {
          // check if this item is a member of the burst hub
          const burstHub = sn.find(n => n.id === burstId);
          const isMember = burstHub && (burstHub._members || []).includes(node.id);
          burstOpacityMult = isMember ? 1 : 0.08;
        }

        let opacity = 1 * recencyOpacityMult * burstOpacityMult;
        if (fil !== 'all' && !hubNode && node.source_type !== fil) opacity *= 0.06;
        if (query && !inSearch) opacity *= 0.05;
        else if (anySel && !isLit) opacity = Math.min(opacity, 0.08);
        else if (!anySel && hov != null && !isHov) opacity = Math.min(opacity, 0.45);

        ctx.save();
        ctx.globalAlpha = opacity;

        if (hubNode) {
          if (k >= 0.8) {
            ctx.save();
            ctx.beginPath();
            ctx.arc(node.x, node.y, 45, 0, Math.PI * 2);
            ctx.strokeStyle = ha(col, 0.08);
            ctx.lineWidth = 1.0 / k;
            ctx.setLineDash([4, 6]);
            ctx.stroke();

            ctx.beginPath();
            ctx.arc(node.x, node.y, 70, 0, Math.PI * 2);
            ctx.strokeStyle = ha(col, 0.04);
            ctx.lineWidth = 0.8 / k;
            ctx.setLineDash([2, 8]);
            ctx.stroke();
            ctx.restore();
          }

          const p1    = 0.5 + 0.5 * Math.sin(now * 1.2 + Math.abs(node.id) * 1.1);
          const p2    = 0.5 + 0.5 * Math.sin(now * 0.6 + Math.abs(node.id) * 0.7 + 2.1);
          const boost = isHubSel ? 2.0 : 1;

          ctx.beginPath();
          ctx.arc(node.x, node.y, r + 5 + p1 * 6 * boost, 0, Math.PI * 2);
          ctx.strokeStyle = ha(col, (0.08 + p1 * 0.07) * (isHubSel ? 1.7 : 1));
          ctx.lineWidth   = (isHubSel ? 1.5 : 1) / k;
          ctx.stroke();

          ctx.beginPath();
          ctx.arc(node.x, node.y, r + 2 + p2 * 3, 0, Math.PI * 2);
          ctx.strokeStyle = ha(col, (0.16 + p2 * 0.1) * (isHubSel ? 1.5 : 1));
          ctx.lineWidth   = 0.8 / k;
          ctx.stroke();

          const glowR = r * (isHubSel ? 3.5 : 2.0);
          const g = ctx.createRadialGradient(node.x, node.y, 0, node.x, node.y, glowR);
          g.addColorStop(0,   ha(col, isHubSel ? 0.92 : 0.68));
          g.addColorStop(0.45, ha(col, isHubSel ? 0.45 : 0.24));
          g.addColorStop(1,   ha(col, 0));
          ctx.beginPath();
          ctx.arc(node.x, node.y, glowR, 0, Math.PI * 2);
          ctx.fillStyle = g;
          ctx.fill();

          const gf = ctx.createRadialGradient(node.x - r*0.3, node.y - r*0.3, 0, node.x, node.y, r);
          gf.addColorStop(0, '#FFF5DC');
          gf.addColorStop(0.6, col);
          gf.addColorStop(1, ha(col, 0.8));
          ctx.beginPath();
          ctx.arc(node.x, node.y, r, 0, Math.PI * 2);
          ctx.fillStyle = gf;
          ctx.fill();

          // T4.2: gaps mode — red ring on sparse clusters
          if (gaps && node.memberCount < 3) {
            ctx.beginPath();
            ctx.arc(node.x, node.y, r + 5, 0, Math.PI * 2);
            ctx.strokeStyle = `rgba(224,96,96,${0.6 + 0.3 * Math.sin(now * 2 + Math.abs(node.id))})`;
            ctx.lineWidth = 1.5 / k;
            ctx.stroke();
          }

          // Cold Storage: Draw secondary outer dashed halo around old Hubs (daysSince >= 30)
          if (node.daysSince >= 30) {
            ctx.beginPath();
            ctx.arc(node.x, node.y, r + 12, 0, Math.PI * 2);
            ctx.strokeStyle = ha(col, 0.18);
            ctx.lineWidth = 1.0 / k;
            ctx.setLineDash([2, 4]);
            ctx.stroke();
            ctx.setLineDash([]);
          }

        } else {
          const drawR = (isSel || isHov || isLit) ? r * 1.7 : r;

          // Spaced Repetition (SM2) Node Glows
          // Active review warning: Amber/Orange glow for cooling nodes (interval_days <= 2 or unquizzed days_since_saved > 2)
          // Solid retention: Indigo/Blue glow for stable nodes (interval_days >= 7)
          let interval = node.interval_days;
          
          if (interval === undefined || interval === null) {
            const created = node.created_at ? new Date(node.created_at) : null;
            if (created) {
              const daysSince = (now - created.getTime()) / 86400000;
              if (daysSince > 2.0) {
                // Decayed without review -> trigger warning glow
                interval = 1;
              } else {
                // Freshly saved -> stable indigo glow
                interval = 7;
              }
            }
          }

          if (interval !== undefined && interval !== null) {
            let sm2Col = null;
            let sm2Alpha = 0.22;
            if (interval <= 2) {
              sm2Col = '#e67e22';
              sm2Alpha = 0.22 + 0.08 * Math.sin(now * 3.0 + Math.abs(node.id));
            } else if (interval >= 7) {
              sm2Col = '#3498db';
              sm2Alpha = 0.16;
            }

            if (sm2Col) {
              const sm2Glow = ctx.createRadialGradient(node.x, node.y, 0, node.x, node.y, drawR * 3.0);
              sm2Glow.addColorStop(0, ha(sm2Col, sm2Alpha));
              sm2Glow.addColorStop(1, ha(sm2Col, 0));
              ctx.beginPath();
              ctx.arc(node.x, node.y, drawR * 3.0, 0, Math.PI * 2);
              ctx.fillStyle = sm2Glow;
              ctx.fill();

              if (interval <= 2) {
                ctx.beginPath();
                ctx.arc(node.x, node.y, drawR + 4.0/k, 0, Math.PI * 2);
                ctx.strokeStyle = `rgba(230,126,34,${0.35 + 0.15 * Math.sin(now * 2.5 + Math.abs(node.id))})`;
                ctx.lineWidth = 1.0 / k;
                ctx.setLineDash([1, 2]);
                ctx.stroke();
                ctx.setLineDash([]);
              }
            }
          }

          if (isSel || isHov || isLit || (query && inSearch)) {
            const glow = ctx.createRadialGradient(node.x, node.y, 0, node.x, node.y, drawR * 3.5);
            glow.addColorStop(0, ha(col, (isSel || (query && inSearch)) ? 0.65 : 0.28));
            glow.addColorStop(1, ha(col, 0));
            ctx.beginPath();
            ctx.arc(node.x, node.y, drawR * 3.5, 0, Math.PI * 2);
            ctx.fillStyle = glow;
            ctx.fill();

            ctx.beginPath();
            ctx.arc(node.x, node.y, drawR + 2.5/k, 0, Math.PI * 2);
            ctx.strokeStyle = isSel ? '#CFA365' : ha(col, 0.75);
            ctx.lineWidth   = 1.5 / k;
            ctx.stroke();
          }

          ctx.beginPath();
          ctx.arc(node.x, node.y, drawR, 0, Math.PI * 2);
          ctx.fillStyle = isSel ? '#F4EFEB' : col;
          ctx.fill();

          if (node.id === flareId) {
            const flarePulse = 0.5 + 0.5 * Math.sin(now * 3.5);
            const flareR = drawR + 4 + flarePulse * 18;
            ctx.beginPath();
            ctx.arc(node.x, node.y, flareR, 0, Math.PI * 2);
            ctx.strokeStyle = `rgba(207,163,101,${0.45 * (1 - flarePulse)})`;
            ctx.lineWidth = 1.5 / k;
            ctx.stroke();
          }
        }
        ctx.restore();

        /* Labels */
        const alwaysDraw = st.showLabels === 'always' && k > 0.45 && inSearch;
        if (hubNode || isSel || isHov || isHubSel || alwaysDraw) {
          const drawR = hubNode ? r : (isSel || isHov ? r * 1.7 : r);
          const raw   = (node.title || node.label || '').slice(0, 28).toLowerCase();
          if (!raw) return;
          const fSz  = hubNode ? Math.max(9, Math.min(12, 11/k)) : Math.max(8, Math.min(11, 10/k));
          ctx.save();
          ctx.globalAlpha = opacity;
          ctx.font = `${hubNode ? '600' : '400'} ${fSz}px "JetBrains Mono","Courier New",monospace`;
          const tw = ctx.measureText(raw).width;
          const ly = node.y - drawR/k - 8/k;
          const pH = 5/k, pV = 3/k;
          const bx = node.x - tw/2 - pH, by = ly - fSz - pV*2;
          const bw = tw + pH*2, bh = fSz + pV*2, br = 3/k;

          ctx.fillStyle = 'rgba(7,6,11,0.92)';
          ctx.beginPath();
          ctx.moveTo(bx+br, by); ctx.lineTo(bx+bw-br, by);
          ctx.arcTo(bx+bw, by, bx+bw, by+br, br);
          ctx.lineTo(bx+bw, by+bh-br);
          ctx.arcTo(bx+bw, by+bh, bx+bw-br, by+bh, br);
          ctx.lineTo(bx+br, by+bh);
          ctx.arcTo(bx, by+bh, bx, by+bh-br, br);
          ctx.lineTo(bx, by+br);
          ctx.arcTo(bx, by, bx+br, by, br);
          ctx.closePath();
          ctx.fill();

          ctx.fillStyle    = hubNode ? (isHubSel ? '#FFE8AA' : '#CFA365') : (isSel ? '#F0EDE8' : '#9A9590');
          ctx.textAlign    = 'center';
          ctx.textBaseline = 'bottom';
          ctx.fillText(raw, node.x, ly);

          if (hubNode && node.memberCount) {
            ctx.font      = `400 ${fSz*0.78}px "JetBrains Mono",monospace`;
            ctx.fillStyle = 'rgba(207,163,101,0.4)';
            const badge = ` ×${node.memberCount}`;
            ctx.fillText(badge, node.x + tw/2 + pH + ctx.measureText(badge).width/2, ly);
            // T4.1: show last active below label for hubs
            if (node.daysSince != null) {
              const activeStr = node.daysSince < 1 ? 'active today' : `${node.daysSince}d ago`;
              ctx.font      = `400 ${fSz*0.7}px "JetBrains Mono",monospace`;
              ctx.fillStyle = node.daysSince < 1 ? 'rgba(143,163,130,0.5)' : node.daysSince < 7 ? 'rgba(207,163,101,0.35)' : 'rgba(138,133,130,0.25)';
              ctx.fillText(activeStr, node.x, ly - fSz - pV*2 - 2/k);
            }
          }
          ctx.restore();
        }
      });

      ctx.restore();
    }

    draw();
    return () => { st.alive = false; if (st.rafId) cancelAnimationFrame(st.rafId); };
  }, []);

  /* ── Pointer helpers ─────────────────────────────────────────────────── */
  function getMouse(e) {
    const r = canvasRef.current.getBoundingClientRect();
    return { mx: e.clientX - r.left, my: e.clientY - r.top };
  }
  function getTouch(t) {
    const r = canvasRef.current.getBoundingClientRect();
    return { mx: t.clientX - r.left, my: t.clientY - r.top };
  }
  function toWorld(mx, my) {
    const {x: tx, y: ty, k} = s.current.transform;
    return { wx: (mx-tx)/k, wy: (my-ty)/k };
  }
  function hitNode(mx, my) {
    const {wx, wy} = toWorld(mx, my);
    return s.current.simNodes.find(n => {
      if (n.x == null) return false;
      const r = nodeR(n) + (isHub(n) ? 14 : 10);
      return (n.x-wx)**2 + (n.y-wy)**2 <= r*r;
    });
  }

  function handleMouseMove(e) {
    const {mx, my} = getMouse(e);
    const st = s.current;
    if (st.isDragging && st.dragNode) {
      const {wx, wy} = toWorld(mx, my);
      st.dragNode.x = wx;
      st.dragNode.y = wy;
      if (!st.physicsFrozen) {
        st.dragNode.fx = wx;
        st.dragNode.fy = wy;
        st.sim?.alpha(0.12).restart();
      }
      return;
    }
    if (st.panStart) {
      st.transform.x = st.panStart.tx + mx - st.panStart.mx;
      st.transform.y = st.panStart.ty + my - st.panStart.my;
      return;
    }
    const hit  = hitNode(mx, my);
    const prev = st.hovered;
    st.hovered = hit ? hit.id : null;
    if (st.hovered !== prev) canvasRef.current.style.cursor = hit ? 'pointer' : 'grab';
  }

  function handleMouseDown(e) {
    const {mx, my} = getMouse(e);
    const st = s.current;
    const hit = hitNode(mx, my);
    if (hit) {
      st.isDragging = true;
      st.dragNode   = hit;
      st.dragStart  = { mx, my };
      hit.fx = hit.x;
      hit.fy = hit.y;
    } else {
      st.panStart = { mx, my, tx: st.transform.x, ty: st.transform.y };
      canvasRef.current.style.cursor = 'grabbing';
    }
  }

  function handleMouseUp(e) {
    const {mx, my} = getMouse(e);
    const st = s.current;
    if (st.isDragging && st.dragNode) {
      const dragStart = st.dragStart;
      const moved = dragStart ? Math.abs(mx - dragStart.mx) + Math.abs(my - dragStart.my) : 0;
      if (dragStart && moved < 15) {
        if (isHub(st.dragNode)) {
          AudioEngine.playClusterChord();
        } else {
          AudioEngine.playClick();
        }
        onNodeClick?.(st.dragNode);
      }

      if (!st.physicsFrozen) {
        if (!isHub(st.dragNode)) {
          st.dragNode.fx = null;
          st.dragNode.fy = null;
        }
        st.sim?.alpha(0.1).restart();
      } else {
        st.dragNode.fx = null;
        st.dragNode.fy = null;
      }
      st.isDragging = false;
      st.dragNode   = null;
      st.dragStart  = null;
    } else if (st.panStart) {
      const moved = Math.abs(mx - st.panStart.mx) + Math.abs(my - st.panStart.my);
      if (moved < 15) {
        const hit = hitNode(mx, my);
        if (hit) {
          if (isHub(hit)) {
            AudioEngine.playClusterChord();
          } else {
            AudioEngine.playClick();
          }
          onNodeClick?.(hit);
        }
      }
      st.panStart = null;
      canvasRef.current.style.cursor = 'grab';
    }
  }

  function handleWheel(e) {
    e.preventDefault();
    const {mx, my} = getMouse(e);
    const st = s.current;
    const k0 = st.transform.k;
    const k1 = Math.max(0.06, Math.min(8, k0 * (1 - e.deltaY * 0.0008)));
    const sc = k1 / k0;
    st.transform.x = mx + (st.transform.x - mx) * sc;
    st.transform.y = my + (st.transform.y - my) * sc;
    st.transform.k = k1;
  }

  /* ── Mobile Touch Handlers ─────────────────────────────────────────────── */
  function handleTouchStart(e) {
    const st = s.current;
    if (e.touches.length === 1) {
      const {mx, my} = getTouch(e.touches[0]);
      const hit = hitNode(mx, my);
      if (hit) {
        st.isDragging = true;
        st.dragNode   = hit;
        st.dragStart  = { mx, my };
        hit.fx = hit.x;
        hit.fy = hit.y;
      } else {
        st.panStart = { mx, my, tx: st.transform.x, ty: st.transform.y };
      }
    } else if (e.touches.length === 2) {
      const t1 = e.touches[0];
      const t2 = e.touches[1];
      st.pinchStartDist = Math.hypot(t1.clientX - t2.clientX, t1.clientY - t2.clientY);
      st.pinchStartK    = st.transform.k;
      
      const {mx: m1x, my: m1y} = getTouch(t1);
      const {mx: m2x, my: m2y} = getTouch(t2);
      st.pinchStartMid  = { mx: (m1x + m2x) / 2, my: (m1y + m2y) / 2 };
    }
  }

  function handleTouchMove(e) {
    const st = s.current;
    if (e.touches.length === 1) {
      const {mx, my} = getTouch(e.touches[0]);
      if (st.isDragging && st.dragNode) {
        const {wx, wy} = toWorld(mx, my);
        st.dragNode.x = wx;
        st.dragNode.y = wy;
        if (!st.physicsFrozen) {
          st.dragNode.fx = wx;
          st.dragNode.fy = wy;
          st.sim?.alpha(0.12).restart();
        }
      } else if (st.panStart) {
        st.transform.x = st.panStart.tx + mx - st.panStart.mx;
        st.transform.y = st.panStart.ty + my - st.panStart.my;
      }
    } else if (e.touches.length === 2 && st.pinchStartDist) {
      const t1 = e.touches[0];
      const t2 = e.touches[1];
      const dist = Math.hypot(t1.clientX - t2.clientX, t1.clientY - t2.clientY);
      const factor = dist / st.pinchStartDist;
      
      const k0 = st.transform.k;
      const k1 = Math.max(0.06, Math.min(8, st.pinchStartK * factor));
      const sc = k1 / k0;
      
      const mid = st.pinchStartMid || { mx: 0, my: 0 };
      st.transform.x = mid.mx + (st.transform.x - mid.mx) * sc;
      st.transform.y = mid.my + (st.transform.y - mid.my) * sc;
      st.transform.k = k1;
    }
  }

  function handleTouchEnd(e) {
    const st = s.current;
    if (st.isDragging && st.dragNode) {
      let mx = st.dragNode.x;
      let my = st.dragNode.y;
      if (e.changedTouches.length === 1) {
        const touch = getTouch(e.changedTouches[0]);
        mx = touch.mx;
        my = touch.my;
      }

      const dragStart = st.dragStart;
      const moved = dragStart ? Math.abs(mx - dragStart.mx) + Math.abs(my - dragStart.my) : 0;
      if (dragStart && moved < 15) {
        if (isHub(st.dragNode)) {
          AudioEngine.playClusterChord();
        } else {
          AudioEngine.playClick();
        }
        onNodeClick?.(st.dragNode);
      }

      if (!st.physicsFrozen) {
        if (!isHub(st.dragNode)) {
          st.dragNode.fx = null;
          st.dragNode.fy = null;
        }
        st.sim?.alpha(0.1).restart();
      } else {
        st.dragNode.fx = null;
        st.dragNode.fy = null;
      }
      st.isDragging = false;
      st.dragNode   = null;
      st.dragStart  = null;
    } else if (st.panStart) {
      // Check if it was a quick tap
      if (e.changedTouches.length === 1) {
        const {mx, my} = getTouch(e.changedTouches[0]);
        const moved = Math.abs(mx - st.panStart.mx) + Math.abs(my - st.panStart.my);
        if (moved < 15) {
          const hit = hitNode(mx, my);
          if (hit) {
            if (isHub(hit)) {
              AudioEngine.playClusterChord();
            } else {
              AudioEngine.playClick();
            }
            onNodeClick?.(hit);
          }
        }
      }
      st.panStart = null;
    }
    st.pinchStartDist = null;
  }

  return (
    <canvas
      ref={canvasRef}
      onMouseMove={handleMouseMove}
      onMouseDown={handleMouseDown}
      onMouseUp={handleMouseUp}
      onTouchEnd={handleTouchEnd}
      style={{ width:'100%', height:'100%', display:'block', cursor:'grab', background:'transparent', touchAction:'none' }}
    />
  );
}
