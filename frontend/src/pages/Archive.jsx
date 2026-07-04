import React, { useEffect, useState, useCallback, useRef } from 'react';
import NodePanel from '../components/NodePanel';
import ArchiveCylinder from '../canvas/ArchiveCylinder';
import AddNoteModal from '../components/AddNoteModal';
import AudioEngine from '../utils/AudioEngine';
import { useToast } from '../components/Toast';

/* ============================================================
   Archive Room — Observatory 3D Cylindrical Review.

   Features:
   - 3D cylindrical carousel of signals
   - Left HUD Observatory Control panel (collapses when item selected)
   - Left HUD collapses/expands smoothly with width transition on hover
   - Floating search pill at the top-center (filters cards client-side)
   - Clicking tag pills in NodePanel bridges to this room pre-filtered
   - Manual Add Note button at the bottom of the HUD
   - SCROLL TO EXPLORE first-visit hint
   - Left/Right click navigation chevrons
   - Active index tracking with interactive dot pagination window
   ============================================================ */
export default function Archive({ initialSelectedItem, onClearInitialSelect }) {
  const { addToast } = useToast();
  const [items, setSelectedItemForArchive] = useState([]);
  const [itemsList, setItems] = useState([]);
  const [selectedItem, setSelectedItem] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filterSourceType, setFilterSourceType] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');

  // HUD persistent hover collapse state
  const [hoveredHUD, setHoveredHUD] = useState(false);
  const [showAddModal, setShowAddModal] = useState(false);
  const [showScrollHint, setShowScrollHint] = useState(false);
  const [hudMinimized, setHudMinimized] = useState(false);
  const [mobileHudOpen, setMobileHudOpen] = useState(false);

  // Show explore hint on first visit
  useEffect(() => {
    const hintSeen = localStorage.getItem('recall-archive-hint');
    if (!hintSeen) {
      setShowScrollHint(true);
      const timer = setTimeout(() => {
        setShowScrollHint(false);
        localStorage.setItem('recall-archive-hint', 'true');
      }, 5000);
      return () => clearTimeout(timer);
    }
  }, []);

  // Track popstate to parse active search queries from url parameters
  useEffect(() => {
    const updateSearchQuery = () => {
      const params = new URLSearchParams(window.location.search);
      setSearchQuery(params.get('search') || '');

      const status = params.get('status');
      if (status === 'shared_success') {
        addToast('Shared content ingested into your memory graph! 🧠', 'success');
        window.history.replaceState({}, '', window.location.pathname);
      } else if (status === 'share_failed') {
        addToast('Failed to ingest shared content. Please try again.', 'error');
        window.history.replaceState({}, '', window.location.pathname);
      }
    };
    updateSearchQuery();
    window.addEventListener('popstate', updateSearchQuery);
    return () => window.removeEventListener('popstate', updateSearchQuery);
  }, [addToast]);

  // Listen to custom popState select parameters
  useEffect(() => {
    if (initialSelectedItem) {
      setSelectedItem(initialSelectedItem);
      if (onClearInitialSelect) onClearInitialSelect();
    }
  }, [initialSelectedItem, onClearInitialSelect]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const itemId = params.get('item');
    if (itemId && itemsList.length > 0) {
      const item = itemsList.find(it => it.id.toString() === itemId);
      if (item) {
        setSelectedItem(item);
        const newSearch = window.location.search.replace(/[?&]item=[^&]*/, '').replace(/^&/, '?').replace(/^\?$/, '');
        const newUrl = window.location.pathname + newSearch;
        window.history.replaceState({}, '', newUrl);
      }
    }
  }, [itemsList]);

  // Fetch signals archive
  const fetchItems = useCallback(async () => {
    try {
      setLoading(true);
      let allItems = [];
      let pageNum = 1;
      let hasMore = true;

      while (hasMore && pageNum <= 6) {
        const res = await fetch(`/api/items?page=${pageNum}&limit=50`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        const fetched = data.items || data || [];

        if (fetched.length === 0) {
          hasMore = false;
        } else {
          allItems = [...allItems, ...fetched];
          if (fetched.length < 50) {
            hasMore = false;
          } else {
            pageNum++;
          }
        }
      }

      setItems(allItems);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchItems(); }, [fetchItems]);

  useEffect(() => {
    const handler = () => fetchItems();
    window.addEventListener('online-refetch', handler);
    return () => window.removeEventListener('online-refetch', handler);
  }, [fetchItems]);

  const handleCardClick = useCallback((item) => { setSelectedItem(item); }, []);
  const handlePanelClose = useCallback(() => { setSelectedItem(null); }, []);

  // Compute metrics for the HUD
  const totalCount = itemsList.length;
  const pdfCount   = itemsList.filter(it => it.source_type === 'pdf').length;
  const voiceCount = itemsList.filter(it => it.source_type === 'voice').length;
  const urlCount   = itemsList.filter(it => it.source_type === 'url').length;
  const imgCount   = itemsList.filter(it => it.source_type === 'image').length;

  const filteredItems = itemsList.filter(it => {
    // Filter by source type
    if (filterSourceType && it.source_type !== filterSourceType) return false;
    
    // Filter by text search query / tags
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      if (q.startsWith('#')) {
        const tag = q.slice(1);
        return (it.tags || []).some(t => t.toLowerCase() === tag);
      }
      const titleMatch = it.title && it.title.toLowerCase().includes(q);
      const summaryMatch = it.summary && it.summary.toLowerCase().includes(q);
      const tagsMatch = (it.tags || []).some(t => t.toLowerCase().includes(q));
      return titleMatch || summaryMatch || tagsMatch;
    }
    return true;
  });

  const showContent = !selectedItem || hoveredHUD;



  return (
    <div className="archive-room" style={{ width: '100%', height: '100vh', position: 'relative', background: '#08070a', overflow: 'hidden' }}>
      
      {/* ── Left HUD Panel (collapses when item selected, expands on hover) ── */}
      {/* Floating R button (Mobile only) */}
      {!loading && itemsList.length > 0 && (
        <button
          onClick={() => { AudioEngine.playClick(); setMobileHudOpen(true); }}
          className="archive-mobile-r-btn"
          aria-label="Open Archive Stats"
          style={{
            position: 'absolute',
            top: '2.5rem',
            left: '1.5rem',
            width: '40px',
            height: '40px',
            borderRadius: '50%',
            background: 'rgba(17,15,20,0.85)',
            border: '1px solid rgba(207,163,101,0.25)',
            boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
            backdropFilter: 'blur(20px)',
            color: 'var(--accent-gold)',
            fontFamily: 'var(--font-display)',
            fontSize: '18px',
            fontWeight: 800,
            display: 'none',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            zIndex: 11,
            transition: 'all 0.2s'
          }}
        >
          R
        </button>
      )}

      {/* ── Left HUD Panel (collapses when item selected, expands on hover) ── */}
      {!loading && itemsList.length > 0 && (
        <div 
          onMouseEnter={() => selectedItem && setHoveredHUD(true)}
          onMouseLeave={() => setHoveredHUD(false)}
          className={`archive-hud ${!showContent ? 'collapsed' : ''} ${hudMinimized ? 'minimized' : ''} ${mobileHudOpen ? 'mobile-open' : ''}`}
        >
          {/* Header */}
          <div className="archive-hud-header" style={{ position: 'relative' }}>
            <button
              onClick={() => {
                AudioEngine.playClick();
                if (mobileHudOpen) {
                  setMobileHudOpen(false);
                } else {
                  setHudMinimized(!hudMinimized);
                }
              }}
              className="hud-toggle-btn"
              style={{
                position: 'absolute', right: 0, top: 0,
                background: 'transparent',
                color: 'var(--accent-gold)', cursor: 'pointer',
                fontFamily: 'var(--font-mono)', fontSize: 9,
                textTransform: 'uppercase', padding: '3px 8px',
                border: '1px solid rgba(207,163,101,0.25)',
                borderRadius: 4
              }}
            >
              <span className="desktop-hud-toggle-label">{hudMinimized ? '[ Show Stats ]' : '[ Minimize ]'}</span>
              <span className="mobile-hud-close-label">✕</span>
            </button>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--accent-gold)', letterSpacing: '0.15em', textTransform: 'uppercase', marginBottom: '0.25rem' }}>
              RECALL // OBSERVATORY
            </div>
            <h1 style={{ fontFamily: 'var(--font-display)', fontSize: '1.75rem', fontWeight: 600, color: 'var(--text-signal)', letterSpacing: '-0.02em', margin: 0 }}>
              Signal Archive
            </h1>
            {searchQuery && (
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                marginTop: '0.625rem',
                background: 'rgba(207, 163, 101, 0.1)',
                border: '1px solid rgba(207, 163, 101, 0.25)',
                borderRadius: '4px',
                padding: '3px 8px',
                width: 'fit-content'
              }}>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '9px', color: 'var(--accent-gold)', textTransform: 'uppercase' }}>
                  Filter: {searchQuery}
                </span>
                <button 
                  onClick={() => {
                    const newUrl = window.location.pathname;
                    window.history.replaceState({}, '', newUrl);
                    setSearchQuery('');
                  }}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    color: 'var(--accent-gold)',
                    cursor: 'pointer',
                    fontSize: '9px',
                    fontFamily: 'var(--font-mono)',
                    fontWeight: 'bold',
                    padding: 0,
                    marginLeft: '4px',
                    display: 'flex',
                    alignItems: 'center'
                  }}
                >
                  ✕
                </button>
              </div>
            )}
            <p style={{ fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--text-muted)', lineHeight: 1.5, marginTop: '0.5rem' }}>
              Your collection of voice, links, and documents structured in real-time.
            </p>
          </div>

          {/* Quick Metrics */}
          <div className="archive-hud-metrics" style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '0.75rem',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', letterSpacing: '0.04em' }}>TOTAL SIGNALS</span>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 16, color: 'var(--accent-gold)', fontWeight: 600 }}>{totalCount}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', letterSpacing: '0.04em' }}>LAST SYNC STATUS</span>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--accent-sage)', letterSpacing: '0.08em' }}>● SECURE</span>
            </div>
          </div>

          {/* Filters List */}
          <div className="archive-hud-filters" style={{ 
            display: 'flex', 
            flexDirection: 'column', 
            gap: '0.875rem', 
            borderTop: showContent ? '1px solid rgba(244,239,235,0.06)' : 'none', 
            paddingTop: showContent ? '1.25rem' : 0 
          }}>
            {showContent && (
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)', letterSpacing: '0.1em' }}>FILTER BY TYPE</span>
            )}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', alignItems: showContent ? 'stretch' : 'center' }}>
              {[
                { type: 'pdf', label: 'PDF Documents', count: pdfCount, color: '#CFA365' },
                { type: 'voice', label: 'Voice Notes', count: voiceCount, color: '#8FA382' },
                { type: 'url', label: 'Web Links', count: urlCount, color: '#9E88A1' },
                { type: 'image', label: 'Saved Images', count: imgCount, color: '#7C9EAA' },
              ].map(opt => {
                const isSelected = filterSourceType === opt.type;
                if (!showContent && opt.count === 0) return null;
                return (
                  <button
                    key={opt.type}
                    onClick={() => setFilterSourceType(isSelected ? null : opt.type)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: showContent ? 'space-between' : 'center',
                      background: isSelected ? 'rgba(244,239,235,0.04)' : 'transparent',
                      border: `1px solid ${isSelected ? 'rgba(207,163,101,0.2)' : 'transparent'}`,
                      borderRadius: 6,
                      padding: showContent ? '0.5rem 0.75rem' : '0.5rem',
                      cursor: 'pointer',
                      width: showContent ? '100%' : '36px',
                      textAlign: 'left',
                      transition: 'all 0.15s ease',
                    }}
                    title={opt.label}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem' }}>
                      <span style={{ width: 6, height: 6, borderRadius: '50%', background: opt.color, flexShrink: 0 }} />
                      {showContent && (
                        <span style={{ fontFamily: 'var(--font-body)', fontSize: 13, color: isSelected ? 'var(--text-signal)' : 'var(--text-muted)' }}>
                          {opt.label}
                        </span>
                      )}
                    </div>
                    {showContent && (
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: isSelected ? 'var(--accent-gold)' : 'rgba(244,239,235,0.3)' }}>
                        {opt.count}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Add Manual Note Button at the bottom of the HUD */}
          {showContent ? (
            <button
              onClick={() => {
                setSelectedItem(null); // close NodePanel if open
                setShowAddModal(true);
              }}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '0.5rem',
                marginTop: 'auto',
                background: 'rgba(207, 163, 101, 0.1)',
                border: '1px solid rgba(207, 163, 101, 0.25)',
                borderRadius: 6,
                padding: '0.625rem 0.75rem',
                color: 'var(--accent-gold)',
                cursor: 'pointer',
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                fontWeight: 600,
                textTransform: 'uppercase',
                transition: 'all 0.15s ease',
                width: '100%',
                letterSpacing: '0.04em'
              }}
              onMouseEnter={e => e.target.style.background = 'rgba(207, 163, 101, 0.18)'}
              onMouseLeave={e => e.target.style.background = 'rgba(207, 163, 101, 0.1)'}
            >
              <span>+ Add Manual Note</span>
            </button>
          ) : (
            <button
              onClick={() => {
                setSelectedItem(null); // close NodePanel if open
                setShowAddModal(true);
              }}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                marginTop: 'auto',
                background: 'rgba(207, 163, 101, 0.1)',
                border: '1px solid rgba(207, 163, 101, 0.25)',
                borderRadius: 6,
                padding: '0.5rem',
                color: 'var(--accent-gold)',
                cursor: 'pointer',
                fontFamily: 'var(--font-mono)',
                fontSize: 14,
                fontWeight: 600,
                transition: 'all 0.15s ease',
                width: '36px',
                height: '36px',
                alignSelf: 'center'
              }}
              title="Add Manual Note"
              onMouseEnter={e => e.target.style.background = 'rgba(207, 163, 101, 0.18)'}
              onMouseLeave={e => e.target.style.background = 'rgba(207, 163, 101, 0.1)'}
            >
              +
            </button>
          )}
        </div>
      )}

      {/* Floating search pill */}
      {!loading && itemsList.length > 0 && (
        <div className="archive-search-pill" style={{
          position: 'absolute',
          top: '2.5rem',
          left: '50%',
          transform: 'translateX(-50%)',
          zIndex: 11,
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
          background: 'rgba(17,15,20,0.85)',
          border: '1px solid rgba(207,163,101,0.15)',
          borderRadius: '30px',
          padding: '0.35rem 1rem',
          width: 'min(380px, 80vw)',
          backdropFilter: 'blur(20px)',
          boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
          transition: 'border-color 0.2s ease, box-shadow 0.2s ease'
        }}
        onMouseEnter={e => {
          e.currentTarget.style.borderColor = 'rgba(207,163,101,0.35)';
          e.currentTarget.style.boxShadow = '0 8px 32px rgba(207,163,101,0.06)';
        }}
        onMouseLeave={e => {
          e.currentTarget.style.borderColor = 'rgba(207,163,101,0.15)';
          e.currentTarget.style.boxShadow = '0 8px 32px rgba(0,0,0,0.4)';
        }}
        >
          <span style={{ color: 'rgba(207,163,101,0.6)', display: 'flex', alignItems: 'center' }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
          </span>
          <input
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            placeholder="Search signals..."
            style={{
              background: 'transparent',
              border: 'none',
              outline: 'none',
              fontFamily: 'var(--font-body)',
              fontSize: 12,
              color: 'var(--text-signal)',
              width: '100%',
              caretColor: 'var(--accent-gold)'
            }}
          />
          {searchQuery ? (
            <button 
              onClick={() => {
                const newUrl = window.location.pathname;
                window.history.replaceState({}, '', newUrl);
                setSearchQuery('');
              }}
              style={{
                background: 'transparent',
                border: 'none',
                color: 'var(--accent-gold)',
                cursor: 'pointer',
                fontSize: 10,
                fontFamily: 'var(--font-mono)',
                padding: '2px 6px'
              }}
            >
              ✕
            </button>
          ) : (
            <span style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 8,
              color: 'rgba(244,239,235,0.25)',
              border: '1px solid rgba(244,239,235,0.1)',
              borderRadius: 3,
              padding: '1px 4px',
              whiteSpace: 'nowrap'
            }}>
              ⌘K
            </span>
          )}
        </div>
      )}



      {/* 3D Cylinder Scene — wrapped in isolation:isolate so the WebGL canvas
           cannot pierce position:fixed overlays (modal, NodePanel) */}
      <div style={{ position: 'absolute', inset: 0, isolation: 'isolate' }}>
        <ArchiveCylinder 
          items={itemsList} 
          matchingIds={new Set(filteredItems.map(it => it.id))} 
          loading={loading} 
          onCardClick={handleCardClick} 
          hasSelection={!!selectedItem} 
          selectedItemId={selectedItem?.id}
          searchQuery={searchQuery}
        />

      </div>



      {/* Side drawer NodePanel */}
      {selectedItem && (
        <NodePanel
          node={selectedItem}
          onClose={handlePanelClose}
          onDelete={(id) => { setItems(prev => prev.filter(it => it.id !== id)); setSelectedItem(null); }}
        />
      )}

      {showAddModal && (
        <AddNoteModal 
          onClose={() => setShowAddModal(false)}
          onSuccess={(newItem) => {
            setItems(prev => [newItem, ...prev]);
          }}
        />
      )}

      {/* First-visit scroll hint */}
      {showScrollHint && (
        <div style={{
          position: 'absolute',
          bottom: '2.5rem',
          left: '50%',
          transform: 'translateX(-50%)',
          fontFamily: 'var(--font-mono)',
          fontSize: 10,
          color: 'var(--accent-gold)',
          letterSpacing: '0.15em',
          background: 'rgba(8,7,10,0.8)',
          padding: '6px 12px',
          borderRadius: 20,
          border: '1px solid rgba(207,163,101,0.2)',
          zIndex: 100,
          animation: 'hintFade 5s linear forwards',
          pointerEvents: 'none'
        }}>
          SCROLL TO EXPLORE ↕
        </div>
      )}

      {error && !loading && (
        <div style={{ position: 'absolute', bottom: '2rem', left: '50%', transform: 'translateX(-50%)', background: 'rgba(180,84,84,0.1)', border: '1px solid rgba(180,84,84,0.3)', borderRadius: 8, padding: '0.75rem 1.25rem', fontFamily: 'var(--font-mono)', fontSize: 11, color: '#e07070', letterSpacing: '0.06em' }}>SIGNAL LOST — {error}</div>
      )}

      {!loading && !error && itemsList.length === 0 && (
        <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%,-50%)', textAlign: 'center', display: 'flex', flexDirection: 'column', gap: '1rem', alignItems: 'center' }}>
          <div style={{ fontFamily: 'var(--font-display)', fontSize: '3rem', color: 'var(--accent-gold)', opacity: 0.3 }}>≡</div>
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>No signals received yet.</p>
          <p style={{ fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--text-muted)', maxWidth: 280, lineHeight: 1.6 }}>Send your first message to the Recall Telegram bot to begin archiving.</p>
        </div>
      )}

      <style>{`
        @keyframes fade-in {
          from { opacity: 0; transform: translateX(-12px); }
          to   { opacity: 1; transform: translateX(0); }
        }
        @keyframes hintFade {
          0% { opacity: 0; transform: translate(-50%, 10px); }
          10% { opacity: 1; transform: translate(-50%, 0); }
          90% { opacity: 1; transform: translate(-50%, 0); }
          100% { opacity: 0; transform: translate(-50%, -10px); }
        }
      `}</style>
    </div>
  );
}
