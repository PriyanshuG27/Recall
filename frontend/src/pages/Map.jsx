import React, { useEffect, useState, useCallback, useRef } from 'react';
import { 
  Compass, List, MagnifyingGlass, Crosshair, Tag, Play, Pause, Folder, Note, Link, Microphone, FilePdf, Image, Warning
} from '@phosphor-icons/react';
import MapCanvas from '../canvas/MapCanvas';
import NodePanel from '../components/NodePanel';
import AudioEngine from '../utils/AudioEngine';

const FILTERS = [
  { id: 'all',   label: 'All',   color: '#CFA365' },
  { id: 'url',   label: 'Links', color: '#7C6FD4' },
  { id: 'voice', label: 'Voice', color: '#3DAA8A' },
  { id: 'pdf',   label: 'PDF',   color: '#C9893C' },
  { id: 'image', label: 'Image', color: '#3D8AAA' },
  { id: 'text',  label: 'Notes', color: '#8A8582' },
];

const SOURCE_ICONS = {
  url: <Link size={12} color="#7C6FD4" />,
  voice: <Microphone size={12} color="#3DAA8A" />,
  pdf: <FilePdf size={12} color="#C9893C" />,
  image: <Image size={12} color="#3D8AAA" />,
  text: <Note size={12} color="#8A8582" />,
};

/* ══════════════════════════════════════════════════════════════════════════
   buildGraph
   – Hub per tag (≥3 items) placed on a circle
   – Every item connects to ALL its hubs (ensures every hub has edges)
   – No item→item edges (no spaghetti)
   ══════════════════════════════════════════════════════════════════════════ */
function buildGraph(items, W = 900, H = 600, tagPortraits = {}) {
  if (!items || items.length === 0) return { nodes: [], edges: [] };

  /* Tag buckets */
  const tagBuckets = {};
  items.forEach(it => {
    (it.tags || []).forEach(tag => {
      if (!tagBuckets[tag]) tagBuckets[tag] = [];
      tagBuckets[tag].push(it.id);
    });
  });

  /* Hub nodes (≥3 members) */
  const hubNodes = [];
  let seq = 1;
  Object.entries(tagBuckets)
    .filter(([tag, ids]) => ids.length >= 3 && tagPortraits[tag] !== undefined)
    .sort((a, b) => b[1].length - a[1].length)
    .forEach(([tag, memberIds]) => {
      // Compute last activity from member items' created_at
      const memberItems = items.filter(it => memberIds.includes(it.id));
      const lastActivityAt = memberItems.reduce((latest, it) => {
        const d = it.created_at ? new Date(it.created_at) : new Date(0);
        return d > latest ? d : latest;
      }, new Date(0));
      const daysSince = lastActivityAt.getTime() > 0
        ? Math.floor((Date.now() - lastActivityAt.getTime()) / 86400000)
        : 999;
      const portrait = tagPortraits[tag] || {};
      hubNodes.push({
        id:             -(seq++),
        title:          tag,
        label:          tag,
        type:           'hub',
        source_type:    'hub',
        tags:           [],
        summary:        portrait.description || `${memberIds.length} signals`,
        memberCount:    memberIds.length,
        source_url:     '',
        created_at:     new Date().toISOString(),
        lastActivityAt: lastActivityAt.toISOString(),
        daysSince,
        _members:       memberIds,
        icon:           portrait.icon || null,
        description:    portrait.description || null,
      });
    });

  /* Place hubs on a circle so they start spread out */
  const cx   = W / 2;
  const cy   = H / 2;
  const hubR = Math.min(W, H) * (hubNodes.length <= 4 ? 0.18 : 0.25);
  hubNodes.forEach((hub, i) => {
    const angle = (i / hubNodes.length) * 2 * Math.PI - Math.PI / 2;
    hub._sx = cx + Math.cos(angle) * hubR;
    hub._sy = cy + Math.sin(angle) * hubR * 0.72;
  });

  /* Build hub lookup by title */
  const hubByTag = {};
  hubNodes.forEach(h => { hubByTag[h.title] = h; });

  /* Item nodes — seeded at centroid of their connected hubs */
  const itemNodes = items.map(it => {
    const myHubs = (it.tags || []).map(tag => hubByTag[tag]).filter(Boolean);
    let sx, sy;
    if (myHubs.length > 0) {
      /* Average position of all connected hubs = natural resting point */
      sx = myHubs.reduce((s, h) => s + h._sx, 0) / myHubs.length;
      sy = myHubs.reduce((s, h) => s + h._sy, 0) / myHubs.length;
      /* Small random offset so items don't stack on same point */
      const a = Math.random() * 2 * Math.PI;
      const r = 15 + Math.random() * 25;
      sx += Math.cos(a) * r;
      sy += Math.sin(a) * r;
    } else {
      /* Untagged: scatter lightly around center */
      const a = Math.random() * 2 * Math.PI;
      const r = 40 + Math.random() * 60;
      sx = cx + Math.cos(a) * r;
      sy = cy + Math.sin(a) * r;
    }
    return {
      ...it,
      type:        'item',
      title:       it.title || 'Untitled',
      source_type: it.source_type || 'text',
      _sx:         sx,
      _sy:         sy,
    };
  });

  /* Edges: item → EVERY hub it belongs to (ensures all hubs connected) */
  const edges = [];
  const itemIdSet = new Set(items.map(it => it.id));
  items.forEach(it => {
    (it.tags || []).forEach(tag => {
      const hub = hubByTag[tag];
      if (hub && itemIdSet.has(it.id)) {
        edges.push({ source: hub.id, target: it.id, weight: 0.7 });
      }
    });
  });

  return { nodes: [...itemNodes, ...hubNodes], edges };
}

/* ── Hub Info Panel (Semantic Cluster Inspector) ─────────────────────── */
function HubPanel({ hub, memberItems, onItemSelect, onClose }) {
  if (!hub) return null;
  return (
    <div style={{ 
      position: 'absolute', top: 0, right: 0, bottom: 0, width: 360, 
      background: 'rgba(9, 8, 14, 0.96)', backdropFilter: 'blur(24px)', WebkitBackdropFilter: 'blur(24px)', 
      borderLeft: '1px solid rgba(207, 163, 101, 0.12)', display: 'flex', flexDirection: 'column', 
      zIndex: 40, animation: 'slideInP 0.28s cubic-bezier(0.16, 1, 0.3, 1)' 
    }}>
      <style>{`@keyframes slideInP{from{transform:translateX(100%);opacity:0}to{transform:translateX(0);opacity:1}}`}</style>
      
      <div style={{ padding: '1.5rem 1.5rem 1rem', borderBottom: '1px solid rgba(207, 163, 101, 0.08)' }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
          <div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--accent-gold)', letterSpacing: '0.16em', textTransform: 'uppercase', marginBottom: 6 }}>
              Knowledge Cluster
            </div>
            <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.5rem', fontWeight: 700, color: '#F0EDE8', letterSpacing: '-0.03em', lineHeight: 1.1, textTransform: 'capitalize', margin: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              {hub.icon && <span style={{ fontSize: '1.4rem' }}>{hub.icon}</span>}
              {hub.title}
            </h2>
          </div>
          <button 
            onClick={onClose} 
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'rgba(207, 163, 101, 0.4)', fontSize: 24, padding: '0 0 0 1rem', lineHeight: 1 }}
          >
            ×
          </button>
        </div>
        {hub.description && (
          <p style={{ margin: '8px 0 0', fontFamily: 'var(--font-body)', fontSize: 11, color: 'rgba(240, 237, 232, 0.65)', lineHeight: 1.4, fontStyle: 'italic' }}>
            {hub.description}
          </p>
        )}
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)', marginTop: 8 }}>
          {hub.memberCount} signals grouped inside
        </div>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '1rem 1.5rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
        {memberItems.map(item => (
          <div 
            key={item.id} 
            onClick={() => { AudioEngine.playClick(); onItemSelect(item); }}
            style={{ 
              padding: '1rem', 
              background: 'rgba(255,255,255,0.015)',
              border: '1px solid rgba(207,163,101,0.04)',
              borderRadius: '10px',
              cursor: 'pointer',
              transition: 'all 0.2s',
              display: 'flex',
              flexDirection: 'column',
              gap: '0.5rem'
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = 'rgba(207, 163, 101, 0.25)';
              e.currentTarget.style.background = 'rgba(207, 163, 101, 0.03)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = 'rgba(207, 163, 101, 0.04)';
              e.currentTarget.style.background = 'rgba(255,255,255,0.015)';
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              {SOURCE_ICONS[item.source_type] || <Note size={12} />}
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-muted)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
                {item.source_type}
              </span>
            </div>
            <p style={{ margin: 0, fontFamily: 'var(--font-sans)', fontSize: 13, color: 'rgba(240, 237, 232, 0.88)', fontWeight: 500, lineHeight: 1.45 }}>
              {item.title || item.summary?.slice(0, 80) || 'Untitled Signal'}
            </p>
            {item.summary && (
              <p style={{ margin: 0, fontFamily: 'var(--font-body)', fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.4 }}>
                {item.summary.slice(0, 100)}...
              </p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════════════
   MapPage
   ══════════════════════════════════════════════════════════════════════════ */
export default function MapPage() {
  const [items,        setItems]        = useState([]);
  const [graphNodes,   setGraphNodes]   = useState([]);
  const [tagPortraits, setTagPortraits] = useState({});
  const [pulseScore,   setPulseScore]   = useState(null);
  const [showPulseInfo, setShowPulseInfo] = useState(false);
  const [graphEdges,   setGraphEdges]   = useState([]);
  const [activeCandidates, setActiveCandidates] = useState([]);
  const [loading,      setLoading]      = useState(true);
  const [loadProgress, setLoadProgress] = useState(0);
  const [error,        setError]        = useState(null);
  
  // Custom interactive controls
  const [filterType,   setFilterType]   = useState('all');
  const [selectedNode, setSelectedNode] = useState(null);
  const [selectedHub,  setSelectedHub]  = useState(null);
  
  const [searchQuery,   setSearchQuery]   = useState('');
  const [physicsFrozen, setPhysicsFrozen] = useState(false);
  const [showLabels,    setShowLabels]    = useState('hover');
  const [viewMode,      setViewMode]      = useState('graph'); // 'graph' | 'orbit'
  const [gapsMode,      setGapsMode]      = useState(false);
  const [burstHubId,    setBurstHubId]    = useState(null);   // T4.3 hub burst
  const [viewTransitioning, setViewTransitioning] = useState(false);
  const [controlsExpanded, setControlsExpanded] = useState(false);
  const [flareNodeId, setFlareNodeId] = useState(null);
  const [controlsPosition, setControlsPosition] = useState(() => {
    try {
      const saved = localStorage.getItem('map_controls_position');
      if (saved) {
        const parsed = JSON.parse(saved);
        if (typeof parsed.x === 'number' && typeof parsed.y === 'number') {
          return parsed;
        }
      }
    } catch (e) {
      console.warn('Failed to parse map controls position:', e);
    }
    return { x: window.innerWidth - 38 - 16, y: 76 };
  });

  const dragRef = useRef({ isDragging: false, startX: 0, startY: 0, initialX: 0, initialY: 0, hasMoved: false });

  const handlePointerDown = (e) => {
    const target = e.currentTarget;
    target.setPointerCapture(e.pointerId);
    dragRef.current = {
      isDragging: true,
      startX: e.clientX,
      startY: e.clientY,
      initialX: controlsPosition.x,
      initialY: controlsPosition.y,
      hasMoved: false
    };
    e.stopPropagation();
  };

  const handlePointerMove = (e) => {
    const dr = dragRef.current;
    if (!dr.isDragging) return;
    const dx = e.clientX - dr.startX;
    const dy = e.clientY - dr.startY;
    if (Math.abs(dx) > 3 || Math.abs(dy) > 3) {
      dr.hasMoved = true;
    }
    const padding = 16;
    const containerW = 38;
    const containerH = 38;
    const newX = Math.max(padding, Math.min(window.innerWidth - containerW - padding, dr.initialX + dx));
    const newY = Math.max(padding, Math.min(window.innerHeight - containerH - padding - 80, dr.initialY + dy));
    setControlsPosition({ x: newX, y: newY });
    e.stopPropagation();
  };

  const handlePointerUp = (e) => {
    const dr = dragRef.current;
    if (!dr.isDragging) return;
    e.currentTarget.releasePointerCapture(e.pointerId);
    dr.isDragging = false;
    localStorage.setItem('map_controls_position', JSON.stringify(controlsPosition));
    setTimeout(() => {
      dr.hasMoved = false;
    }, 50);
    e.stopPropagation();
  };

  useEffect(() => {
    const handleResize = () => {
      setControlsPosition(prev => {
        const padding = 16;
        const containerW = 38;
        const containerH = 38;
        const newX = Math.max(padding, Math.min(window.innerWidth - containerW - padding, prev.x));
        const newY = Math.max(padding, Math.min(window.innerHeight - containerH - padding - 80, prev.y));
        return { x: newX, y: newY };
      });
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // T4.4: animated mode switch helper
  const switchView = (mode) => {
    if (mode === viewMode) return;
    setViewTransitioning(true);
    setTimeout(() => {
      setViewMode(mode);
      setViewTransitioning(false);
    }, 180);
  };

  const fetchData = useCallback(async () => {
    try {
      setLoading(true); setError(null); setLoadProgress(0);
      const all = [];
      let page = 1;
      while (page <= 10) {
        const res = await fetch(`/api/items?page=${page}&limit=50`, { credentials: 'include' });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data  = await res.json();
        const batch = data.items || (Array.isArray(data) ? data : []);
        all.push(...batch);
        setLoadProgress(Math.min(95, page * 10));
        if (batch.length < 50) break;
        page++;
      }
      // Fetch tag portraits
      let portraits = {};
      try {
        const portRes = await fetch('/api/tags/portraits', { credentials: 'include' });
        if (portRes.ok) {
          portraits = await portRes.json();
          setTagPortraits(portraits);
        }
      } catch (pErr) {
        console.error('[Map] failed to fetch tag portraits:', pErr);
      }

      // Fetch user profile pulse score
      try {
        const profRes = await fetch('/api/user/profile', { credentials: 'include' });
        if (profRes.ok) {
          const profData = await profRes.json();
          if (profData && profData.pulse_score !== undefined) {
            setPulseScore(profData.pulse_score);
          }
        }
      } catch (profErr) {
        console.error('[Map] failed to fetch profile pulse score:', profErr);
      }

      setItems(all);
      const { nodes, edges } = buildGraph(all, window.innerWidth, window.innerHeight, portraits);
      setGraphNodes(nodes);
      setGraphEdges(edges);
      
      // Fetch active connection candidates
      let candidates = [];
      try {
        const candRes = await fetch('/api/candidates/active', { credentials: 'include' });
        if (candRes.ok) {
          candidates = await candRes.json();
        }
      } catch (cErr) {
        console.error('[Map] failed to fetch active candidates:', cErr);
      }
      setActiveCandidates(candidates);

      // Select a random non-hub node for the daily "Star Flare"
      const nonHubs = nodes.filter(n => n.type !== 'hub');
      if (nonHubs.length > 0) {
        const randNode = nonHubs[Math.floor(Math.random() * nonHubs.length)];
        setFlareNodeId(randNode.id);
      }
    } catch (err) {
      console.error('[Map] fetch error:', err);
      setError(err.message || 'Failed to load');
    } finally {
      setLoading(false); setLoadProgress(100);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);
  useEffect(() => {
    const h = () => fetchData();
    window.dispatchEvent(new CustomEvent('online-refetch'));
    window.addEventListener('online-refetch', h);
    return () => window.removeEventListener('online-refetch', h);
  }, [fetchData]);

  // Sync selectedNode state with updated item in items list (for real-time updates)
  useEffect(() => {
    if (!selectedNode) return;
    const updated = items.find(item => String(item.id) === String(selectedNode.id));
    if (updated) {
      if (updated.context_note !== selectedNode.context_note || JSON.stringify(updated.tags) !== JSON.stringify(selectedNode.tags)) {
        setSelectedNode(updated);
      }
    }
  }, [items, selectedNode]);

  const handleNodeClick = useCallback((node) => {
    console.log('[Map] Node clicked:', node);
    if (node.type === 'hub') { 
      // T4.3: toggle burst expansion on hub click
      setBurstHubId(prev => prev === node.id ? null : node.id);
      setSelectedHub(node); 
      setSelectedNode(null); 
    } else { 
      setBurstHubId(null);
      const foundItem = items.find(it => it.id === node.id) || node;
      console.log('[Map] Setting selected node:', foundItem);
      setSelectedNode(foundItem); 
      setSelectedHub(null); 
    }
  }, [items]);

  const handleItemSelect = useCallback((item) => {
    setSelectedNode(item);
    setSelectedHub(null);
  }, []);

  useEffect(() => {
    const handleFocusNode = (e) => {
      const nodeId = e.detail?.nodeId;
      if (!nodeId) return;
      const foundItem = items.find(it => it.id != null && String(it.id) === String(nodeId));
      if (foundItem) {
        setSelectedNode(foundItem);
        setSelectedHub(null);
        setFlareNodeId(nodeId);
        window.dispatchEvent(new CustomEvent('map-canvas-focus', { detail: { nodeId } }));
        setTimeout(() => {
          setFlareNodeId(null);
        }, 8000); // 8 seconds to be clearly visible
      }
    };
    window.addEventListener('map-focus-node', handleFocusNode);
    return () => window.removeEventListener('map-focus-node', handleFocusNode);
  }, [items]);

  useEffect(() => {
    if (loading || items.length === 0) return;
    const pendingNodeId = sessionStorage.getItem('pending_map_focus_node');
    if (pendingNodeId) {
      sessionStorage.removeItem('pending_map_focus_node');
      const foundItem = items.find(it => it.id != null && String(it.id) === String(pendingNodeId));
      if (foundItem) {
        setSelectedNode(foundItem);
        setSelectedHub(null);
        setFlareNodeId(foundItem.id);
        
        // Wait briefly for canvas simulation initialization/mount
        setTimeout(() => {
          window.dispatchEvent(new CustomEvent('map-canvas-focus', { detail: { nodeId: foundItem.id } }));
        }, 250);

        setTimeout(() => {
          setFlareNodeId(null);
        }, 8000); // 8 seconds flare visibility
      }
    }
  }, [loading, items]);

  const handleAutoFit = () => {
    AudioEngine.playClick();
    window.dispatchEvent(new CustomEvent('map-autofit'));
  };

  const hubMemberItems = selectedHub
    ? (selectedHub._members || []).map(mid => items.find(it => it.id === mid)).filter(Boolean)
    : [];

  const typeCounts = {};
  items.forEach(it => { const t = it.source_type || 'text'; typeCounts[t] = (typeCounts[t] || 0) + 1; });
  const hubs = graphNodes.filter(n => n.type === 'hub');
  const hubCount = hubs.length;

  // Filter items in Orbit Registry view based on search query
  const filteredHubs = hubs.filter(h => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    const matchesHub = h.title.toLowerCase().includes(q);
    const matchesMembers = (h._members || []).some(mid => {
      const it = items.find(x => x.id === mid);
      return it && (
        (it.title || '').toLowerCase().includes(q) || 
        (it.summary || '').toLowerCase().includes(q)
      );
    });
    return matchesHub || matchesMembers;
  });

  if (loading) return (
    <div style={{ width:'100%', height:'100vh', background:'#08070B', display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center', gap:'1.5rem' }}>
      <div style={{ position:'relative', width:52, height:52 }}>
        <div style={{ position:'absolute', inset:0, borderRadius:'50%', border:'1.5px solid rgba(207,163,101,0.1)', borderTopColor:'rgba(207,163,101,0.7)', animation:'mapspin 1.1s linear infinite' }} />
        <div style={{ position:'absolute', inset:8, borderRadius:'50%', border:'1px solid rgba(207,163,101,0.06)', borderBottomColor:'rgba(207,163,101,0.35)', animation:'mapspin 1.8s linear infinite reverse' }} />
      </div>
      <div style={{ textAlign:'center' }}>
        <p style={{ fontFamily:'var(--font-mono)', fontSize:11, color:'rgba(207,163,101,0.6)', letterSpacing:'0.14em', marginBottom:8 }}>MAPPING YOUR KNOWLEDGE</p>
        <div style={{ width:160, height:2, background:'rgba(207,163,101,0.08)', borderRadius:2, overflow:'hidden' }}>
          <div style={{ height:'100%', background:'linear-gradient(90deg,#CFA365,#E8C47A)', borderRadius:2, width:`${loadProgress}%`, transition:'width 0.4s ease' }} />
        </div>
      </div>
      <style>{`@keyframes mapspin{to{transform:rotate(360deg);}}`}</style>
    </div>
  );

  return (
    <div style={{ position:'relative', width:'100%', height:'100vh', background:'#08070B', overflow:'hidden', display: 'flex', flexDirection: 'column' }}>
      
      {/* ── TOP CONTROL BAR ── */}
      <div className="map-control-bar" style={{ 
        padding: '1.25rem 2rem', 
        background: 'rgba(7,6,11,0.85)', 
        borderBottom: '1px solid rgba(207,163,101,0.08)', 
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'center',
        zIndex: 30,
        backdropFilter: 'blur(20px)',
        WebkitBackdropFilter: 'blur(20px)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <Compass size={22} color="var(--accent-gold)" style={{ animation: 'spin 20s linear infinite' }} />
          <div>
            <h1 style={{ margin: 0, fontFamily: 'var(--font-display)', fontSize: '18px', fontWeight: 700, color: '#F0EDE8', letterSpacing: '-0.02em' }}>
              Knowledge Constellation
            </h1>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '2px', flexWrap: 'wrap' }}>
              <p style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: '9px', color: 'var(--text-muted)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
                {items.length} Signals Catalogued
              </p>
              {pulseScore !== null && (
                <>
                  <span style={{ fontSize: '9px', color: 'rgba(207,163,101,0.2)' }}>|</span>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '9px', color: 'var(--accent-gold)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
                      PULSE:
                    </span>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '9px', fontWeight: 700, color: '#ffffff' }}>
                      {pulseScore}%
                    </span>
                    <div style={{
                      width: '6px',
                      height: '6px',
                      borderRadius: '50%',
                      background: '#CFA365',
                      boxShadow: '0 0 6px #CFA365',
                      animation: 'pulseGlow 1.6s infinite ease-in-out',
                    }} />
                    <button
                      onClick={() => { AudioEngine.playClick(); setShowPulseInfo(true); }}
                      style={{
                        background: 'none', border: 'none', color: 'rgba(207,163,101,0.5)',
                        fontFamily: 'var(--font-mono)', fontSize: '11px', cursor: 'pointer',
                        padding: '0 2px', display: 'flex', alignItems: 'center', transition: 'color 0.2s'
                      }}
                      onMouseEnter={(e) => e.currentTarget.style.color = 'var(--accent-gold)'}
                      onMouseLeave={(e) => e.currentTarget.style.color = 'rgba(207,163,101,0.5)'}
                      title="Diagnostics Info"
                    >
                      ⓘ
                    </button>
                  </div>
                </>
              )}
            </div>
            <style>{`
              @keyframes pulseGlow {
                0%, 100% { transform: scale(1); opacity: 0.65; box-shadow: 0 0 3px #CFA365; }
                50% { transform: scale(1.25); opacity: 1; box-shadow: 0 0 7px #CFA365; }
              }
            `}</style>
          </div>
        </div>

        {/* View mode toggle */}
        <div style={{ display: 'flex', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(207,163,101,0.12)', borderRadius: '10px', padding: '3px' }}>
          <button
            onClick={() => { AudioEngine.playClick(); switchView('graph'); }}
            style={{
              display: 'flex', alignItems: 'center', gap: '0.35rem',
              background: viewMode === 'graph' ? 'rgba(207,163,101,0.15)' : 'none',
              border: 'none', borderRadius: '7px',
              padding: '0.45rem 1rem', cursor: 'pointer',
              color: viewMode === 'graph' ? 'var(--accent-gold)' : 'var(--text-muted)',
              fontFamily: 'var(--font-mono)', fontSize: '10px', fontWeight: 600, letterSpacing: '0.05em',
              transition: 'all 0.2s'
            }}
          >
            <Compass size={13} /> Graph Space
          </button>
          <button
            onClick={() => { AudioEngine.playClick(); switchView('orbit'); }}
            style={{
              display: 'flex', alignItems: 'center', gap: '0.35rem',
              background: viewMode === 'orbit' ? 'rgba(207,163,101,0.15)' : 'none',
              border: 'none', borderRadius: '7px',
              padding: '0.45rem 1rem', cursor: 'pointer',
              color: viewMode === 'orbit' ? 'var(--accent-gold)' : 'var(--text-muted)',
              fontFamily: 'var(--font-mono)', fontSize: '10px', fontWeight: 600, letterSpacing: '0.05em',
              transition: 'all 0.2s'
            }}
          >
            <List size={13} /> Orbit Registry
          </button>
        </div>

        {/* Floating Search Bar */}
        <div className="map-search-wrapper" style={{ position: 'relative', width: '260px' }}>
          <MagnifyingGlass size={14} color="rgba(207,163,101,0.4)" style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)' }} />
          <input
            type="text"
            placeholder="Search constellation..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
              width: '100%',
              background: 'rgba(0,0,0,0.25)',
              border: '1px solid rgba(207,163,101,0.12)',
              borderRadius: '8px',
              color: '#F0EDE8',
              padding: '0.5rem 0.75rem 0.5rem 2.25rem',
              outline: 'none',
              fontSize: '12px',
              fontFamily: 'var(--font-sans)',
              transition: 'border-color 0.2s'
            }}
          />
        </div>
      </div>

      {/* ── MAIN WORKSPACE ── */}
      <div style={{
        flex: 1, position: 'relative', overflow: 'hidden',
        opacity: viewTransitioning ? 0 : 1,
        transform: viewTransitioning ? 'scale(0.98)' : 'scale(1)',
        transition: 'opacity 0.18s ease, transform 0.18s ease'
      }}>

        {/* VIEW 1: D3 FORCE GRAPH CANVAS */}
        {viewMode === 'graph' ? (
          <>
            <div style={{ position:'absolute', inset:0, background:'radial-gradient(ellipse 55% 45% at 50% 50%, rgba(207,163,101,0.02) 0%, transparent 65%)', pointerEvents:'none' }} />
            <div style={{ position:'absolute', inset:0 }}>
              <MapCanvas 
                nodes={graphNodes} 
                edges={graphEdges} 
                activeCandidates={activeCandidates}
                filterType={filterType} 
                selectedNodeId={selectedNode?.id ?? null} 
                selectedHubId={selectedHub?.id ?? null} 
                flareNodeId={flareNodeId}
                searchQuery={searchQuery}
                physicsFrozen={physicsFrozen}
                showLabels={showLabels}
                gapsMode={gapsMode}
                burstHubId={burstHubId}
                onNodeClick={handleNodeClick} 
              />
            </div>

            {/* T4.3 — Hub burst banner */}
            {burstHubId && selectedHub && (
              <div style={{
                position: 'absolute', top: 20, left: '50%', transform: 'translateX(-50%)',
                zIndex: 30, pointerEvents: 'none',
                background: 'rgba(10,9,15,0.9)', backdropFilter: 'blur(20px)',
                border: '1px solid rgba(207,163,101,0.25)', borderRadius: 10,
                padding: '0.5rem 1.25rem',
                display: 'flex', alignItems: 'center', gap: '0.75rem',
                animation: 'burstBannerIn 0.3s cubic-bezier(0.16,1,0.3,1) forwards'
              }}>
                <span style={{ fontFamily:'var(--font-mono)', fontSize:9, color:'rgba(207,163,101,0.5)', letterSpacing:'0.14em', textTransform:'uppercase' }}>CLUSTER</span>
                <span style={{ fontFamily:'var(--font-display)', fontSize:'1rem', fontWeight:700, color:'#F0EDE8', textTransform:'capitalize', display: 'flex', alignItems: 'center' }}>
                  {selectedHub.icon && <span style={{ marginRight: '0.4rem' }}>{selectedHub.icon}</span>}
                  {selectedHub.title}
                </span>
                <span style={{ fontFamily:'var(--font-mono)', fontSize:9, color:'rgba(207,163,101,0.6)', letterSpacing:'0.08em' }}>· {selectedHub.memberCount} signals</span>
                {selectedHub.daysSince != null && (
                  <span style={{ fontFamily:'var(--font-mono)', fontSize:8, color: selectedHub.daysSince < 1 ? '#8FA382' : selectedHub.daysSince < 7 ? 'rgba(207,163,101,0.8)' : 'rgba(138,133,130,0.5)', letterSpacing:'0.08em' }}>
                    · last active {selectedHub.daysSince < 1 ? 'today' : `${selectedHub.daysSince}d ago`}
                  </span>
                )}
              </div>
            )}

            {/* Left Filter Rails */}
            <div className="map-filter-rail" style={{ position:'absolute', top:20, left:20, zIndex:20, display:'flex', flexDirection:'column', gap:'0.6rem' }}>
              <div className="map-metrics-card" style={{ background:'rgba(10,9,15,0.78)', backdropFilter:'blur(20px)', border:'1px solid rgba(207,163,101,0.1)', borderRadius:12, padding:'0.875rem 1.125rem', minWidth:158 }}>
                <div style={{ fontFamily:'var(--font-mono)', fontSize:9, color:'rgba(207,163,101,0.4)', letterSpacing:'0.16em', textTransform:'uppercase', marginBottom:8 }}>Constellation Metrics</div>
                <div style={{ display:'flex', alignItems:'baseline', gap:'0.3rem', marginBottom:3 }}>
                  <span style={{ fontFamily:'var(--font-display)', fontSize:'1.875rem', fontWeight:800, color:'#F0EDE8', letterSpacing:'-0.05em', lineHeight:1 }}>{items.length.toLocaleString()}</span>
                  <span style={{ fontFamily:'var(--font-mono)', fontSize:10, color:'rgba(207,163,101,0.4)' }}>signals</span>
                </div>
                <div style={{ fontFamily:'var(--font-mono)', fontSize:9, color:'rgba(138,133,130,0.5)', letterSpacing:'0.06em' }}>{hubCount} clusters · {graphEdges.length} links</div>
                {Object.keys(typeCounts).length > 0 && (
                  <div style={{ marginTop:10, display:'flex', flexWrap:'wrap', gap:'0.28rem' }}>
                    {Object.entries(typeCounts).sort((a,b)=>b[1]-a[1]).map(([t,cnt]) => {
                      const f = FILTERS.find(x => x.id === t);
                      return <span key={t} style={{ fontFamily:'var(--font-mono)', fontSize:8, color:f?.color||'#8A8582', background:`${f?.color||'#8A8582'}14`, padding:'1px 5px', borderRadius:3 }}>{cnt} {t}</span>;
                    })}
                  </div>
                )}
              </div>

              {/* Source Filters */}
              <div className="map-source-filters" style={{ display:'flex', flexWrap:'wrap', gap:'0.28rem' }}>
                {FILTERS.map(f => {
                  const active = filterType === f.id;
                  const count  = f.id === 'all' ? items.length : (typeCounts[f.id] || 0);
                  if (f.id !== 'all' && count === 0) return null;
                  return (
                    <button 
                      key={f.id} 
                      onClick={() => { AudioEngine.playClick(); setFilterType(f.id); }} 
                      style={{ 
                        fontFamily:'var(--font-mono)', fontSize:10, letterSpacing:'0.07em', padding:'0.28rem 0.65rem', 
                        borderRadius:6, border:`1px solid ${active?f.color:'rgba(207,163,101,0.1)'}`, 
                        background:active?`${f.color}20`:'rgba(10,9,15,0.7)', color:active?f.color:'rgba(207,163,101,0.35)', 
                        cursor:'pointer', backdropFilter:'blur(8px)', transition:'all 0.15s ease' 
                      }}
                    >
                      {f.label}{f.id !== 'all' && <span style={{ marginLeft:4, opacity:0.5 }}>{count}</span>}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* 1. Desktop Bottom-Right Camera & Simulation Control panel */}
            <div className="map-control-panel desktop-only-controls" style={{ 
              position: 'absolute', bottom: 20, right: 110, zIndex: 20,
              background: 'rgba(10,9,15,0.78)', backdropFilter: 'blur(20px)', border: '1px solid rgba(207,163,101,0.1)',
              borderRadius: '12px', padding: '0.65rem', display: 'flex', gap: '0.5rem'
            }}>
              {/* Center Button */}
              <button
                onClick={handleAutoFit}
                title="Recenter Map Viewport"
                style={{
                  background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(207,163,101,0.15)',
                  borderRadius: '8px', width: '34px', height: '34px', display: 'flex', alignItems: 'center', justifyContent: 'center',
                  cursor: 'pointer', color: 'var(--accent-gold)', transition: 'all 0.2s'
                }}
                onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(207,163,101,0.1)'}
                onMouseLeave={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.02)'}
              >
                <Crosshair size={16} />
              </button>

              {/* Label Toggle */}
              <button
                onClick={() => { AudioEngine.playClick(); setShowLabels(showLabels === 'always' ? 'hover' : 'always'); }}
                title={showLabels === 'always' ? "Show Labels on Hover Only" : "Always Show Node Labels"}
                style={{
                  background: showLabels === 'always' ? 'rgba(207,163,101,0.15)' : 'rgba(255,255,255,0.02)', 
                  border: `1px solid ${showLabels === 'always' ? 'var(--accent-gold)' : 'rgba(207,163,101,0.15)'}`,
                  borderRadius: '8px', width: '34px', height: '34px', display: 'flex', alignItems: 'center', justifyContent: 'center',
                  cursor: 'pointer', color: showLabels === 'always' ? 'var(--accent-gold)' : 'var(--text-muted)', transition: 'all 0.2s'
                }}
              >
                <Tag size={16} />
              </button>

              {/* Physics Pause */}
              <button
                onClick={() => { AudioEngine.playClick(); setPhysicsFrozen(!physicsFrozen); }}
                title={physicsFrozen ? "Resume Simulation Physics" : "Freeze Simulation Nodes"}
                style={{
                  background: physicsFrozen ? 'rgba(239,68,68,0.15)' : 'rgba(255,255,255,0.02)',
                  border: `1px solid ${physicsFrozen ? '#ef4444' : 'rgba(207,163,101,0.15)'}`,
                  borderRadius: '8px', width: '34px', height: '34px', display: 'flex', alignItems: 'center', justifyContent: 'center',
                  cursor: 'pointer', color: physicsFrozen ? '#ef4444' : 'var(--text-muted)', transition: 'all 0.2s'
                }}
              >
                {physicsFrozen ? <Play size={16} /> : <Pause size={16} />}
              </button>

              {/* T4.2 — Gaps Mode Toggle */}
              <button
                onClick={() => { AudioEngine.playClick(); setGapsMode(g => !g); }}
                title={gapsMode ? "Exit Gaps Mode" : "Gaps Mode — find isolated clusters"}
                style={{
                  background: gapsMode ? 'rgba(239,100,100,0.15)' : 'rgba(255,255,255,0.02)',
                  border: `1px solid ${gapsMode ? 'rgba(239,100,100,0.5)' : 'rgba(207,163,101,0.15)'}`,
                  borderRadius: '8px', padding: '0 10px', height: '34px', display: 'flex', alignItems: 'center', justifyContent: 'center',
                  cursor: 'pointer', color: gapsMode ? '#E06060' : 'var(--text-muted)', transition: 'all 0.2s',
                  fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.08em', whiteSpace: 'nowrap'
                }}
              >
                <Warning size={14} style={{ marginRight: 4 }} />
                GAPS
              </button>
            </div>

            {/* 2. Mobile-Only Collapsible Top-Right Control Panel */}
            {/* 2. Mobile-Only Collapsible & Movable Control Panel */}
            <div className="mobile-only-controls" style={{
              position: 'absolute',
              left: `${controlsPosition.x}px`,
              top: `${controlsPosition.y}px`,
              zIndex: 25,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '6px',
            }}>
              {/* Trigger Toggle / Drag Handle */}
              <button
                onPointerDown={handlePointerDown}
                onPointerMove={handlePointerMove}
                onPointerUp={handlePointerUp}
                onClick={() => {
                  if (dragRef.current.hasMoved) return;
                  AudioEngine.playClick();
                  setControlsExpanded(e => !e);
                }}
                title="Drag to Move / Tap to Toggle"
                style={{
                  background: 'rgba(10,9,15,0.85)',
                  backdropFilter: 'blur(20px)',
                  border: '1px solid var(--accent-gold)',
                  borderRadius: '50%',
                  width: '38px',
                  height: '38px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  cursor: 'grab',
                  color: 'var(--accent-gold)',
                  boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
                  transition: 'transform 0.2s',
                  userSelect: 'none',
                  touchAction: 'none'
                }}
              >
                <Compass size={18} style={{ transform: controlsExpanded ? 'rotate(45deg)' : 'none', transition: 'transform 0.3s ease' }} />
              </button>

              {/* Collapsed/Expanded Stack */}
              {controlsExpanded && (
                <div style={{
                  background: 'rgba(10,9,15,0.88)',
                  backdropFilter: 'blur(20px)',
                  border: '1px solid rgba(207,163,101,0.15)',
                  borderRadius: '10px',
                  padding: '6px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '6px',
                  boxShadow: '0 8px 24px rgba(0,0,0,0.6)',
                  animation: 'slideDownFade 0.2s ease-out forwards',
                }}>
                  {/* Center Button */}
                  <button
                    onClick={handleAutoFit}
                    title="Recenter Map Viewport"
                    style={{
                      background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(207,163,101,0.15)',
                      borderRadius: '8px', width: '34px', height: '34px', display: 'flex', alignItems: 'center', justifyContent: 'center',
                      cursor: 'pointer', color: 'var(--accent-gold)', transition: 'all 0.2s'
                    }}
                  >
                    <Crosshair size={16} />
                  </button>

                  {/* Label Toggle */}
                  <button
                    onClick={() => { AudioEngine.playClick(); setShowLabels(showLabels === 'always' ? 'hover' : 'always'); }}
                    title={showLabels === 'always' ? "Show Labels on Hover Only" : "Always Show Node Labels"}
                    style={{
                      background: showLabels === 'always' ? 'rgba(207,163,101,0.15)' : 'rgba(255,255,255,0.02)', 
                      border: `1px solid ${showLabels === 'always' ? 'var(--accent-gold)' : 'rgba(207,163,101,0.15)'}`,
                      borderRadius: '8px', width: '34px', height: '34px', display: 'flex', alignItems: 'center', justifyContent: 'center',
                      cursor: 'pointer', color: showLabels === 'always' ? 'var(--accent-gold)' : 'var(--text-muted)', transition: 'all 0.2s'
                    }}
                  >
                    <Tag size={16} />
                  </button>

                  {/* Physics Pause */}
                  <button
                    onClick={() => { AudioEngine.playClick(); setPhysicsFrozen(!physicsFrozen); }}
                    title={physicsFrozen ? "Resume Simulation Physics" : "Freeze Simulation Nodes"}
                    style={{
                      background: physicsFrozen ? 'rgba(239,68,68,0.15)' : 'rgba(255,255,255,0.02)',
                      border: `1px solid ${physicsFrozen ? '#ef4444' : 'rgba(207,163,101,0.15)'}`,
                      borderRadius: '8px', width: '34px', height: '34px', display: 'flex', alignItems: 'center', justifyContent: 'center',
                      cursor: 'pointer', color: physicsFrozen ? '#ef4444' : 'var(--text-muted)', transition: 'all 0.2s'
                    }}
                  >
                    {physicsFrozen ? <Play size={16} /> : <Pause size={16} />}
                  </button>

                  {/* Gaps Toggle */}
                  <button
                    onClick={() => { AudioEngine.playClick(); setGapsMode(g => !g); }}
                    title={gapsMode ? "Exit Gaps Mode" : "Gaps Mode — find isolated clusters"}
                    style={{
                      background: gapsMode ? 'rgba(239,100,100,0.15)' : 'rgba(255,255,255,0.02)',
                      border: `1px solid ${gapsMode ? 'rgba(239,100,100,0.5)' : 'rgba(207,163,101,0.15)'}`,
                      borderRadius: '8px', width: '34px', height: '34px', display: 'flex', alignItems: 'center', justifyContent: 'center',
                      cursor: 'pointer', color: gapsMode ? '#E06060' : 'var(--text-muted)', transition: 'all 0.2s'
                    }}
                  >
                    <Warning size={14} />
                  </button>
                </div>
              )}
            </div>

            {/* T4.2 — Gaps mode tooltip banner */}
            {gapsMode && (
              <div style={{
                position: 'absolute', bottom: 50, left: '50%', transform: 'translateX(-50%)',
                zIndex: 25, pointerEvents: 'none',
                background: 'rgba(80,20,20,0.85)', backdropFilter: 'blur(12px)',
                border: '1px solid rgba(239,100,100,0.25)', borderRadius: 8,
                padding: '0.4rem 1rem',
                fontFamily: 'var(--font-mono)', fontSize: 9, color: '#E06060',
                letterSpacing: '0.1em', textTransform: 'uppercase'
              }}>
                Gaps Mode — clusters with fewer than 3 signals are highlighted in red
              </div>
            )}

            {/* Instruction tooltip */}
            <div className="map-instruction-tooltip" style={{ position:'absolute', bottom:18, left:'50%', transform:'translateX(-50%)', zIndex:20, pointerEvents:'none' }}>
              <span style={{ fontFamily:'var(--font-mono)', fontSize:9, color:'rgba(138,133,130,0.28)', letterSpacing:'0.12em' }}>
                SCROLL TO ZOOM · DRAG TO PAN · DRAG NODE TO ORBIT · CLICK TO FOCUS
              </span>
            </div>
          </>
        ) : (
          /* VIEW 2: ORBIT REGISTRY — KNOWLEDGE INDEX */
          <div className={`orbit-registry-wrapper ${selectedHub ? 'has-selection' : ''}`} style={{ 
            width: '100%', height: '100%', display: 'flex', overflow: 'hidden',
          }}>
            {/* ── LEFT RAIL: Cluster index ── */}
            <div className="orbit-left-rail" style={{
              width: 300,
              flexShrink: 0,
              borderRight: '1px solid rgba(207,163,101,0.08)',
              display: 'flex',
              flexDirection: 'column',
              overflow: 'hidden',
            }}>
              {/* Index header */}
              <div style={{
                padding: '1.25rem 1.5rem 1rem',
                borderBottom: '1px solid rgba(207,163,101,0.06)',
              }}>
                <div style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 9,
                  color: 'rgba(207,163,101,0.4)',
                  letterSpacing: '0.16em',
                  textTransform: 'uppercase',
                  marginBottom: 6,
                }}>
                  {filteredHubs.length} clusters
                </div>
                <div style={{
                  fontFamily: 'var(--font-display)',
                  fontSize: '1.1rem',
                  fontWeight: 700,
                  color: '#F0EDE8',
                  letterSpacing: '-0.025em',
                }}>
                  Orbit Registry
                </div>
              </div>
              
              {/* Scrollable cluster list */}
              <div style={{ flex: 1, overflowY: 'auto', padding: '0.5rem 0' }}>
                {filteredHubs.length === 0 ? (
                  <div style={{
                    padding: '2rem 1.5rem',
                    textAlign: 'center',
                    fontFamily: 'var(--font-mono)',
                    fontSize: 10,
                    color: 'rgba(138,133,130,0.4)',
                    letterSpacing: '0.08em',
                  }}>
                    No clusters match your search.
                  </div>
                ) : filteredHubs.map((hub, idx) => {
                  const members = (hub._members || []).map(mid => items.find(x => x.id === mid)).filter(Boolean);
                  const isActive = selectedHub?.id === hub.id;
                  // Type breakdown for mini-bar
                  const typeBreakdown = {};
                  members.forEach(m => { const t = m.source_type || 'text'; typeBreakdown[t] = (typeBreakdown[t] || 0) + 1; });
                  const typeColors = { url: '#7C6FD4', voice: '#3DAA8A', pdf: '#C9893C', image: '#3D8AAA', text: '#8A8582' };

                  return (
                    <div
                      key={hub.id}
                      onClick={() => { AudioEngine.playClick(); setSelectedHub(hub); setSelectedNode(null); }}
                      style={{
                        padding: '0.75rem 1.5rem',
                        cursor: 'pointer',
                        borderLeft: `2px solid ${isActive ? 'rgba(207,163,101,0.8)' : 'transparent'}`,
                        background: isActive ? 'rgba(207,163,101,0.04)' : 'transparent',
                        transition: 'all 0.18s ease',
                        position: 'relative',
                      }}
                      onMouseEnter={e => { if (!isActive) { e.currentTarget.style.background = 'rgba(255,255,255,0.02)'; e.currentTarget.style.borderLeftColor = 'rgba(207,163,101,0.25)'; }}}
                      onMouseLeave={e => { if (!isActive) { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.borderLeftColor = 'transparent'; }}}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
                        <span style={{
                          fontFamily: 'var(--font-display)',
                          fontSize: 13,
                          fontWeight: 600,
                          color: isActive ? '#CFA365' : 'rgba(240,237,232,0.85)',
                          textTransform: 'capitalize',
                          flex: 1,
                          paddingRight: 8,
                          lineHeight: 1.3,
                          display: 'flex',
                          alignItems: 'center',
                          gap: '0.35rem'
                        }}>
                          {hub.icon && <span style={{ fontSize: '1rem' }}>{hub.icon}</span>}
                          {hub.title}
                        </span>
                        <span style={{
                          fontFamily: 'var(--font-mono)',
                          fontSize: 9,
                          color: isActive ? 'rgba(207,163,101,0.7)' : 'rgba(138,133,130,0.5)',
                          background: isActive ? 'rgba(207,163,101,0.08)' : 'rgba(255,255,255,0.03)',
                          padding: '2px 6px',
                          borderRadius: 3,
                          flexShrink: 0,
                        }}>
                          {members.length}
                        </span>
                      </div>
                      {/* Mini type-breakdown strip */}
                      <div style={{ display: 'flex', height: 2, borderRadius: 1, overflow: 'hidden', gap: 1 }}>
                        {Object.entries(typeBreakdown).map(([type, count]) => (
                          <div
                            key={type}
                            style={{
                              flex: count,
                              background: typeColors[type] || '#8A8582',
                              opacity: isActive ? 0.8 : 0.35,
                              borderRadius: 1,
                              transition: 'opacity 0.2s',
                            }}
                          />
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* ── RIGHT PANEL: Cluster detail ── */}
            <div className="orbit-right-panel" style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
              {selectedHub ? (() => {
                const members = (selectedHub._members || []).map(mid => items.find(x => x.id === mid)).filter(Boolean);
                const typeBreakdown = {};
                members.forEach(m => { const t = m.source_type || 'text'; typeBreakdown[t] = (typeBreakdown[t] || 0) + 1; });
                const typeColors = { url: '#7C6FD4', voice: '#3DAA8A', pdf: '#C9893C', image: '#3D8AAA', text: '#8A8582' };
                const typeLabels = { url: 'Links', voice: 'Voice', pdf: 'PDFs', image: 'Images', text: 'Notes' };
                const sorted = [...members].sort((a, b) => new Date(b.created_at) - new Date(a.created_at));

                return (
                  <div style={{ display: 'flex', flexDirection: 'column', height: '100%', animation: 'orbitIn 0.28s cubic-bezier(0.16, 1, 0.3, 1)' }}>
                    <style>{`@keyframes orbitIn { from { opacity:0; transform:translateX(12px); } to { opacity:1; transform:translateX(0); } }`}</style>

                    {/* Detail header */}
                    <div style={{
                      padding: '1.5rem 2rem 1.25rem',
                      borderBottom: '1px solid rgba(207,163,101,0.08)',
                      background: 'rgba(207,163,101,0.012)',
                    }}>
                      {/* Back button (Mobile only) */}
                      <button
                        onClick={() => setSelectedHub(null)}
                        className="mobile-only-back"
                        style={{
                          background: 'transparent', color: 'var(--accent-gold)',
                          cursor: 'pointer', fontFamily: 'var(--font-mono)', fontSize: 10,
                          textTransform: 'uppercase', padding: '4px 8px', borderRadius: 4,
                          border: '1px solid rgba(207,163,101,0.2)', marginBottom: '0.75rem',
                          display: 'none', width: 'fit-content'
                        }}
                      >
                        [ Back to Registry ]
                      </button>

                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'rgba(207,163,101,0.4)', letterSpacing: '0.14em', textTransform: 'uppercase', marginBottom: 8 }}>
                        Knowledge Cluster
                      </div>
                      <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: '1rem', marginBottom: '1rem' }}>
                        <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.75rem', fontWeight: 800, color: '#F0EDE8', letterSpacing: '-0.04em', lineHeight: 1, margin: 0, textTransform: 'capitalize', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                          {selectedHub.icon && <span style={{ fontSize: '1.5rem' }}>{selectedHub.icon}</span>}
                          {selectedHub.title}
                        </h2>
                        <div style={{ display: 'flex', alignItems: 'baseline', gap: 4, flexShrink: 0 }}>
                          <span style={{ fontFamily: 'var(--font-display)', fontSize: '2rem', fontWeight: 800, color: '#CFA365', letterSpacing: '-0.04em', lineHeight: 1 }}>
                            {members.length}
                          </span>
                          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'rgba(207,163,101,0.45)', letterSpacing: '0.1em' }}>signals</span>
                        </div>
                      </div>
                      {selectedHub.description && (
                        <p style={{ margin: '0 0 1rem', fontFamily: 'var(--font-body)', fontSize: 12, color: 'rgba(240, 237, 232, 0.68)', lineHeight: 1.45, fontStyle: 'italic' }}>
                          {selectedHub.description}
                        </p>
                      )}

                      {/* Type distribution bar */}
                      <div style={{ marginBottom: '0.75rem' }}>
                        <div style={{ display: 'flex', height: 4, borderRadius: 2, overflow: 'hidden', gap: 1, marginBottom: 6 }}>
                          {Object.entries(typeBreakdown).map(([type, count]) => (
                            <div key={type} style={{ flex: count, background: typeColors[type] || '#8A8582', borderRadius: 2, opacity: 0.7 }} />
                          ))}
                        </div>
                        <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
                          {Object.entries(typeBreakdown).map(([type, count]) => (
                            <div key={type} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                              <div style={{ width: 6, height: 6, borderRadius: '50%', background: typeColors[type] || '#8A8582', opacity: 0.7 }} />
                              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'rgba(138,133,130,0.6)', letterSpacing: '0.06em' }}>
                                {typeLabels[type] || type} {count}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>

                    {/* Member signals list */}
                    <div style={{ flex: 1, overflowY: 'auto', padding: '1rem 2rem' }}>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'rgba(138,133,130,0.35)', letterSpacing: '0.14em', textTransform: 'uppercase', marginBottom: '0.75rem', paddingBottom: '0.5rem', borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
                        Signals in this cluster
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
                        {sorted.map((member, idx) => {
                          const tc = typeColors[member.source_type] || '#8A8582';
                          const d = new Date(member.created_at);
                          const dateStr = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                          return (
                            <div
                              key={member.id}
                              onClick={() => { AudioEngine.playClick(); handleItemSelect(member); }}
                              style={{
                                padding: '0.875rem 0',
                                borderBottom: idx < sorted.length - 1 ? '1px solid rgba(255,255,255,0.03)' : 'none',
                                cursor: 'pointer',
                                display: 'flex',
                                alignItems: 'flex-start',
                                gap: '0.875rem',
                                transition: 'all 0.15s ease',
                              }}
                              onMouseEnter={e => { e.currentTarget.querySelector('.signal-title').style.color = '#F0EDE8'; e.currentTarget.querySelector('.signal-arrow').style.opacity = '1'; }}
                              onMouseLeave={e => { e.currentTarget.querySelector('.signal-title').style.color = 'rgba(240,237,232,0.72)'; e.currentTarget.querySelector('.signal-arrow').style.opacity = '0'; }}
                            >
                              {/* Type indicator */}
                              <div style={{ width: 3, height: 16, borderRadius: 2, background: tc, opacity: 0.6, flexShrink: 0, marginTop: 2 }} />
                              {/* Content */}
                              <div style={{ flex: 1, minWidth: 0 }}>
                                <div className="signal-title" style={{ fontFamily: 'var(--font-sans)', fontSize: 13, fontWeight: 500, color: 'rgba(240,237,232,0.72)', lineHeight: 1.4, marginBottom: 3, overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', transition: 'color 0.15s' }}>
                                  {member.title || 'Untitled Signal'}
                                </div>
                                {member.summary && (
                                  <div style={{ fontFamily: 'var(--font-body)', fontSize: 11, color: 'rgba(138,133,130,0.5)', lineHeight: 1.5, overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 1, WebkitBoxOrient: 'vertical' }}>
                                    {member.summary}
                                  </div>
                                )}
                              </div>
                              {/* Right meta */}
                              <div style={{ flexShrink: 0, display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
                                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 8, color: 'rgba(138,133,130,0.35)', letterSpacing: '0.06em' }}>{dateStr}</span>
                                <span className="signal-arrow" style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: '#CFA365', opacity: 0, transition: 'opacity 0.15s' }}>→</span>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  </div>
                );
              })() : (
                /* Empty state — no cluster selected */
                <div style={{
                  flex: 1,
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '1rem',
                  opacity: 0.4,
                }}>
                  <div style={{
                    width: 48,
                    height: 48,
                    borderRadius: '50%',
                    border: '1px solid rgba(207,163,101,0.2)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}>
                    <Compass size={20} color="#CFA365" />
                  </div>
                  <p style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'rgba(207,163,101,0.5)', letterSpacing: '0.1em', textTransform: 'uppercase', margin: 0 }}>
                    Select a cluster
                  </p>
                </div>
              )}
            </div>
          </div>
        )}

      </div>

      {/* Floating Info Panels */}
      {selectedNode && (
        <NodePanel
          node={selectedNode}
          activeCandidates={activeCandidates}
          activeNodes={graphNodes}
          onClose={() => setSelectedNode(null)}
        />
      )}
      {selectedHub  && <HubPanel  hub={selectedHub} memberItems={hubMemberItems} onItemSelect={handleItemSelect} onClose={() => setSelectedHub(null)} />}

      {/* Error state */}
      {error && (
        <div style={{ position:'absolute', bottom:'4rem', left:'50%', transform:'translateX(-50%)', background:'rgba(160,60,60,0.12)', border:'1px solid rgba(160,60,60,0.3)', borderRadius:8, padding:'0.625rem 1.25rem', fontFamily:'var(--font-mono)', fontSize:11, color:'#D97070', zIndex:30, display:'flex', alignItems:'center', gap:'0.75rem' }}>
          {error}<button onClick={fetchData} style={{ color:'var(--accent-gold)', background:'none', border:'none', cursor:'pointer', fontFamily:'var(--font-mono)', fontSize:10 }}>↺</button>
        </div>
      )}

      {/* ── Pulse & Spaced Repetition Info Modal ── */}
      {showPulseInfo && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(5,4,8,0.72)', backdropFilter: 'blur(10px)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
          animation: 'fadeIn 0.2s ease-out'
        }}>
          <div style={{
            background: 'rgba(12,11,18,0.96)', border: '1px solid rgba(207,163,101,0.22)',
            borderRadius: '16px', padding: '2rem', maxWidth: '480px', width: '90%',
            boxShadow: '0 20px 50px rgba(0,0,0,0.6), 0 0 30px rgba(207,163,101,0.03)',
            animation: 'scaleIn 0.25s cubic-bezier(0.16, 1, 0.3, 1)',
            position: 'relative'
          }}>
            <button
              onClick={() => { AudioEngine.playClick(); setShowPulseInfo(false); }}
              style={{
                position: 'absolute', top: '1rem', right: '1.25rem', background: 'none', border: 'none',
                color: 'rgba(255,255,255,0.4)', fontSize: '1.5rem', cursor: 'pointer', outline: 'none'
              }}
            >
              ×
            </button>

            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '9px', color: 'var(--accent-gold)', letterSpacing: '0.16em', textTransform: 'uppercase', marginBottom: '6px' }}>
              System Diagnostics
            </div>
            <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.5rem', fontWeight: 700, color: '#F0EDE8', margin: '0 0 1.25rem 0', letterSpacing: '-0.02em' }}>
              Pulse & Recall Guide
            </h2>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
              <div>
                <h3 style={{ fontFamily: 'var(--font-display)', fontSize: '11px', color: '#ffffff', textTransform: 'uppercase', letterSpacing: '0.05em', margin: '0 0 6px 0' }}>
                  What is Cognitive Pulse?
                </h3>
                <p style={{ margin: 0, fontFamily: 'var(--font-body)', fontSize: '12px', color: 'var(--text-muted)', lineHeight: '1.5' }}>
                  A dynamic score (0-100%) tracking your cognitive synergy. <strong>100% Pulse</strong> represents peak synchronization: you have a high density of saved knowledge signals, a high success rate on your active recall quizzes, and zero days of mental inactivity.
                </p>
              </div>

              <div>
                <h3 style={{ fontFamily: 'var(--font-display)', fontSize: '11px', color: '#ffffff', textTransform: 'uppercase', letterSpacing: '0.05em', margin: '0 0 6px 0' }}>
                  Memory Retention Glows (Spaced Repetition)
                </h3>
                <p style={{ margin: '0 0 8px 0', fontFamily: 'var(--font-body)', fontSize: '12px', color: 'var(--text-muted)', lineHeight: '1.5' }}>
                  Individual node glows reflect your memory retention strength, calculated using the <strong>SM-2 algorithm</strong>:
                </p>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', background: 'rgba(255,255,255,0.01)', border: '1px solid rgba(255,255,255,0.03)', borderRadius: '8px', padding: '10px' }}>
                  <div style={{ display: 'flex', gap: '8px', alignItems: 'flex-start' }}>
                    <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#3498db', marginTop: '4px', boxShadow: '0 0 6px #3498db' }} />
                    <div>
                      <strong style={{ fontSize: '11px', color: '#ffffff' }}>Indigo Glow (Stable Retention)</strong>
                      <p style={{ margin: 0, fontSize: '11px', color: 'var(--text-muted)' }}>Signals recently saved or successfully recalled (interval &ge; 7 days). Keep them in mind!</p>
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: '8px', alignItems: 'flex-start' }}>
                    <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#e67e22', marginTop: '4px', boxShadow: '0 0 6px #e67e22' }} />
                    <div>
                      <strong style={{ fontSize: '11px', color: '#ffffff' }}>Amber Halo (Decaying Memory)</strong>
                      <p style={{ margin: 0, fontSize: '11px', color: 'var(--text-muted)' }}>Signals that are cooling down or have not been reviewed for &gt; 2 days. Take a quiz to refresh your memory!</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <button
              onClick={() => { AudioEngine.playClick(); setShowPulseInfo(false); }}
              style={{
                marginTop: '1.75rem', width: '100%', padding: '0.625rem', background: 'rgba(207,163,101,0.08)',
                border: '1px solid var(--accent-gold)', borderRadius: '8px', color: 'var(--accent-gold)',
                fontFamily: 'var(--font-mono)', fontSize: '10px', fontWeight: 600, cursor: 'pointer',
                transition: 'all 0.2s', outline: 'none'
              }}
              onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(207,163,101,0.15)'; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = 'rgba(207,163,101,0.08)'; }}
            >
              Acknowledge System Diagnostics
            </button>
          </div>
          <style>{`
            @keyframes scaleIn {
              from { transform: scale(0.95); opacity: 0; }
              to { transform: scale(1); opacity: 1; }
            }
          `}</style>
        </div>
      )}
    </div>
  );
}
