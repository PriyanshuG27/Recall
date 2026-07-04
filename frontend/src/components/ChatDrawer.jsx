import React, { useState, useEffect, useRef } from 'react';

/**
 * 3D Card Tilt Hook
 */
function useCardTilt() {
  const [tilt, setTilt] = useState({ x: 0, y: 0 });
  const cardRef = useRef(null);

  const handleMouseMove = (e) => {
    if (!cardRef.current) return;
    const rect = cardRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left - rect.width / 2;
    const y = e.clientY - rect.top - rect.height / 2;
    
    // Max 10 degrees rotation
    const rotateX = -(y / (rect.height / 2)) * 10;
    const rotateY = (x / (rect.width / 2)) * 10;
    
    setTilt({ x: rotateX, y: rotateY });
  };

  const handleMouseLeave = () => {
    setTilt({ x: 0, y: 0 });
  };

  return { cardRef, tilt, handleMouseMove, handleMouseLeave };
}

/**
 * Single source card with 3D perspective tilt
 */
function SourceCard({ source, index, highlighted, onClick }) {
  const { cardRef, tilt, handleMouseMove, handleMouseLeave } = useCardTilt();
  const url = source.source_url || source.url;

  const handleTitleClick = (e) => {
    if (url) {
      e.stopPropagation();
      window.open(url, '_blank');
    }
  };

  return (
    <div
      ref={cardRef}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      onClick={onClick}
      className={`assistant-source-card ${highlighted ? 'highlighted' : ''}`}
      style={{
        transform: `perspective(600px) rotateX(${tilt.x}deg) rotateY(${tilt.y}deg)`,
        transition: 'transform 0.1s ease-out, border-color 0.3s ease, box-shadow 0.3s ease',
      }}
    >
      <div className="source-card-header">
        <span className="source-index">[{index + 1}]</span>
        <span 
          className={`source-title ${url ? 'clickable-link' : ''}`}
          onClick={handleTitleClick}
          title={url ? `Open source link: ${url}` : undefined}
        >
          {source.title || 'Untitled note'}
          {url && <span className="external-link-arrow"> ↗</span>}
        </span>
      </div>
      <p className="source-excerpt">{source.summary || 'No excerpt available.'}</p>
      {source.tags && source.tags.length > 0 && (
        <div className="source-tags">
          {source.tags.slice(0, 3).map((tag, i) => (
            <span key={i} className="source-tag">#{tag}</span>
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * Interactive liquid-droplet canvas Orb
 */
function LiquidOrb({ onClick }) {
  const canvasRef = useRef(null);
  const mouseRef = useRef({ x: 0, y: 0, px: 0, py: 0 });
  const hoverRef = useRef(false);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx || 
        typeof ctx.clearRect !== 'function' ||
        typeof ctx.beginPath !== 'function' ||
        typeof ctx.moveTo !== 'function' ||
        typeof ctx.quadraticCurveTo !== 'function' ||
        typeof ctx.closePath !== 'function' ||
        typeof ctx.fill !== 'function' ||
        typeof ctx.stroke !== 'function') {
      return;
    }
    let animationFrameId;

    const numPoints = 8;
    const baseRadius = 24;
    const points = [];

    // Initialize point coordinates
    for (let i = 0; i < numPoints; i++) {
      const angle = (i / numPoints) * Math.PI * 2;
      points.push({
        x: Math.cos(angle) * baseRadius,
        y: Math.sin(angle) * baseRadius,
        ox: Math.cos(angle) * baseRadius,
        oy: Math.sin(angle) * baseRadius,
        vx: 0,
        vy: 0,
        angle: angle,
      });
    }

    // Keep track of current mouse coordinates relative to canvas center
    const onMouseMove = (e) => {
      const rect = canvas.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      mouseRef.current.x = e.clientX - cx;
      mouseRef.current.y = e.clientY - cy;
      
      const dist = Math.hypot(mouseRef.current.x, mouseRef.current.y);
      hoverRef.current = dist < baseRadius * 1.5;
    };

    window.addEventListener('mousemove', onMouseMove);

    const render = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      const cx = canvas.width / 2;
      const cy = canvas.height / 2;

      // Mouse interactive variables
      const mx = mouseRef.current.x;
      const my = mouseRef.current.y;
      const mDist = Math.hypot(mx, my);

      // Slow organic warping base timer
      const time = Date.now() * 0.002;

      // Update point physics
      for (let i = 0; i < numPoints; i++) {
        const p = points[i];
        
        // Organic breathing warping
        const wave = Math.sin(time + p.angle * 2) * 2;
        const targetRadius = baseRadius + wave;
        
        const tx = Math.cos(p.angle) * targetRadius;
        const ty = Math.sin(p.angle) * targetRadius;

        // Force calculations
        let fx = (tx - p.x) * 0.12; // Spring stiffness
        let fy = (ty - p.y) * 0.12;

        // Mouse gravity pull: pull vertices toward mouse if mouse is close
        if (mDist < 80) {
          const force = (80 - mDist) * 0.15;
          const angleToMouse = Math.atan2(my - p.y, mx - p.x);
          
          // Pull direction vector
          fx += Math.cos(angleToMouse) * force;
          fy += Math.sin(angleToMouse) * force;
        }

        p.vx += fx;
        p.vy += fy;
        p.vx *= 0.72; // Dampening friction
        p.vy *= 0.72;

        p.x += p.vx;
        p.y += p.vy;
      }

      // Draw the organic fluid path
      ctx.beginPath();
      ctx.moveTo(cx + points[0].x, cy + points[0].y);
      
      for (let i = 0; i < numPoints; i++) {
        const p1 = points[i];
        const p2 = points[(i + 1) % numPoints];
        const xc = (p1.x + p2.x) / 2;
        const yc = (p1.y + p2.y) / 2;
        ctx.quadraticCurveTo(cx + p1.x, cy + p1.y, cx + xc, cy + yc);
      }

      ctx.closePath();
      
      // Paint liquid body (Obsidian Dark)
      ctx.fillStyle = '#131619';
      ctx.fill();

      // Paint gold accent border
      ctx.strokeStyle = hoverRef.current ? '#dfb375' : '#cfa365';
      ctx.lineWidth = 2;
      ctx.stroke();

      // Paint stylized golden "R" logo inside the orb center
      ctx.beginPath();
      ctx.lineWidth = 2;
      ctx.strokeStyle = hoverRef.current ? '#dfb375' : '#cfa365';
      
      // Calculate dynamic attraction shift for the "R" monogram
      let shiftX = 0;
      let shiftY = 0;
      if (mDist < 80) {
        const shiftRatio = (80 - mDist) * 0.08;
        const angle = Math.atan2(my, mx);
        shiftX = Math.cos(angle) * shiftRatio;
        shiftY = Math.sin(angle) * shiftRatio;
      }
      
      const rx = cx - 4 + shiftX;
      const ry = cy - 7 + shiftY;
      
      // Vertical left stem of R
      ctx.moveTo(rx, ry + 14);
      ctx.lineTo(rx, ry);
      
      // Top loop of R
      ctx.lineTo(rx + 5, ry);
      ctx.quadraticCurveTo(rx + 9, ry + 3, rx + 5, ry + 7);
      ctx.lineTo(rx, ry + 7);
      
      // Diagonal leg of R
      ctx.moveTo(rx + 2, ry + 7);
      ctx.lineTo(rx + 8, ry + 14);
      
      ctx.stroke();

      animationFrameId = requestAnimationFrame(render);
    };

    render();

    return () => {
      window.removeEventListener('mousemove', onMouseMove);
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  return (
    <div className="assistant-orb-wrapper" onClick={onClick}>
      <span className="assistant-orb-label">ASSISTANT</span>
      <canvas
        ref={canvasRef}
        width="80"
        height="80"
        className="assistant-orb-canvas"
      />
    </div>
  );
}

/**
 * Main Assistant ChatDrawer Component
 */
export default function ChatDrawer({ isOpen, onClose, onOpen, totalSaves, onItemSelect, onCitationClick }) {
  const [query, setQuery] = useState('');
  const [messages, setMessages] = useState([]);
  const [sources, setSources] = useState([]);
  const [loading, setLoading] = useState(false);
  const [highlightedSourceId, setHighlightedSourceId] = useState(null);
  
  const chatBottomRef = useRef(null);
  const sourcePanelRef = useRef(null);

  useEffect(() => {
    if (chatBottomRef.current && typeof chatBottomRef.current.scrollIntoView === 'function') {
      chatBottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, loading]);

  const handleSend = async (e) => {
    if (e) e.preventDefault();
    if (!query.trim() || loading) return;

    const userMsg = query.trim();
    setQuery('');
    setMessages(prev => [...prev, { role: 'user', content: userMsg }]);
    setLoading(true);

    try {
      const res = await fetch('/api/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: userMsg, rag: true, limit: 5 })
      });

      if (!res.ok) throw new Error('Search request failed');
      const data = await res.json();
      
      const aiResponse = data.answer || "I checked your notes, but the evidence was too thin to compile a synthesised answer.";
      setMessages(prev => [...prev, { role: 'assistant', content: aiResponse }]);
      if (data.sources) {
        setSources(data.sources);
      }
    } catch (err) {
      console.error('RAG query failed:', err);
      setMessages(prev => [...prev, { role: 'assistant', content: "Failed to connect to the cognitive network. Please try again." }]);
    } finally {
      setLoading(false);
    }
  };

  const handleCitationClick = (index) => {
    const sourceItem = sources[index];
    if (sourceItem) {
      setHighlightedSourceId(sourceItem.id);
      
      if (typeof onCitationClick === 'function') {
        onCitationClick(sourceItem.id, sourceItem);
      }
      
      // Auto scroll to source card
      setTimeout(() => {
        const el = document.getElementById(`source-card-${sourceItem.id}`);
        if (el && typeof el.scrollIntoView === 'function') {
          el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
      }, 50);

      // Remove highlight after a brief interval
      setTimeout(() => {
        setHighlightedSourceId(null);
      }, 2500);
    }
  };

  /**
   * Helper to parse [1] and [2] in text into interactive buttons
   */
  const renderMessageContent = (content) => {
    const regex = /\[(\d+)\]/g;
    const parts = [];
    let lastIndex = 0;
    let match;

    while ((match = regex.exec(content)) !== null) {
      const matchIndex = match.index;
      const citationNumber = parseInt(match[1], 10);
      const sourceIndex = citationNumber - 1;

      // Text before citation
      if (matchIndex > lastIndex) {
        parts.push(content.substring(lastIndex, matchIndex));
      }

      // Interactive citation badge
      parts.push(
        <button
          key={matchIndex}
          onClick={() => handleCitationClick(sourceIndex)}
          className="citation-badge"
          title={`View source: ${sources[sourceIndex]?.title || 'Note'}`}
        >
          [{citationNumber}]
        </button>
      );

      lastIndex = regex.lastIndex;
    }

    if (lastIndex < content.length) {
      parts.push(content.substring(lastIndex));
    }

    return parts.length > 0 ? parts : content;
  };

  if (!isOpen) {
    return <LiquidOrb onClick={onOpen || onClose} />;
  }

  return (
    <div className="assistant-drawer-panel">
      <div className="assistant-drawer-header">
        <div className="status-indicator">
          <span className="status-dot animate-pulse"></span>
          <span className="status-label">ASSISTANT: ACTIVE</span>
        </div>
        <button className="assistant-close-btn" onClick={onClose}>
          [ COLLAPSE ]
        </button>
      </div>

      <div className="assistant-drawer-layout">
        {/* Chat message stream */}
        <div className="assistant-chat-stream">
          {messages.length === 0 ? (
            <div className="chat-empty-state">
              <div className="system-boot-log">
                <div className="boot-line green">&gt; INITIALIZING COGNITIVE CORE...</div>
                <div className="boot-line">&gt; ACTIVE SCHEMAS: Neon Postgres + pgvector</div>
                <div className="boot-line">&gt; KNOWLEDGE CACHE: {totalSaves || 72} NODES INDEXED</div>
                <div className="boot-line gold">&gt; GRAPH ANCHOR: Obsidian OKF</div>
                <div className="boot-line blink">&gt; READY FOR INQUIRY _</div>
              </div>
            </div>
          ) : (
            messages.map((msg, idx) => (
              <div key={idx} className={`chat-message ${msg.role}`}>
                <div className="message-header">
                  {msg.role === 'user' ? 'USER' : 'AI'}
                </div>
                <div className="message-content">
                  {msg.role === 'assistant' ? renderMessageContent(msg.content) : msg.content}
                </div>
              </div>
            ))
          )}
          {loading && (
            <div className="chat-message assistant loading">
              <div className="message-header">AI</div>
              <div className="message-content">
                <span className="loading-dot"></span>
                <span className="loading-dot"></span>
                <span className="loading-dot"></span>
              </div>
            </div>
          )}
          <div ref={chatBottomRef} />
        </div>

        {/* Sources side bar (only shown if we have references) */}
        {sources.length > 0 && (
          <div className="assistant-sources-panel" ref={sourcePanelRef}>
            <div className="sources-header">
              <span>// RETRIEVED SOURCES</span>
            </div>
            <div className="sources-list">
              {sources.map((src, idx) => (
                <div key={src.id} id={`source-card-${src.id}`}>
                  <SourceCard
                    source={src}
                    index={idx}
                    highlighted={highlightedSourceId === src.id}
                    onClick={() => {
                      handleCitationClick(idx);
                      if (onItemSelect) {
                        onItemSelect(src);
                      }
                    }}
                  />
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Input query form */}
      <form className="assistant-drawer-footer" onSubmit={handleSend}>
        <div className="input-outline-wrapper">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Ask anything..."
            disabled={loading}
            className="assistant-query-input"
          />
          <button type="submit" disabled={loading || !query.trim()} className="assistant-send-btn">
            [ SEND ]
          </button>
        </div>
      </form>
    </div>
  );
}
