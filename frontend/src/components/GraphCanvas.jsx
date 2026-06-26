import React from 'react';

function getNodeStyles(node) {
  if (node.type === 'hub') {
    return {
      bg: 'var(--color-secondary)',
      shadow: '0 0 20px 4px var(--color-secondary-glow)'
    };
  }
  
  switch(node.source_type) {
    case 'url':
      return { bg: '#00f2fe', shadow: '0 0 16px var(--glow-url)' };
    case 'pdf':
      return { bg: '#ff0844', shadow: '0 0 16px var(--glow-pdf)' };
    case 'voice':
      return { bg: '#b100ff', shadow: '0 0 16px var(--glow-voice)' };
    case 'image':
    case 'photo':
      return { bg: '#00ff87', shadow: '0 0 16px var(--glow-image)' };
    case 'text':
      return { bg: '#f9d423', shadow: '0 0 16px var(--glow-text)' };
    default:
      return { bg: 'var(--color-primary)', shadow: '0 0 14px var(--color-primary-glow)' };
  }
}

export default function GraphCanvas({ activeNodes, edges, matchingNodeIds, pan, zoom, handleNodeClick, selectedNodeId }) {
  return (
    <div 
      className="graph-canvas-inner"
      role="application"
      aria-label="Knowledge constellation"
      style={{
        position: 'relative',
        width: '100%',
        height: '100%',
        transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
        transformOrigin: 'center center',
        transition: 'none',
      }}
    >
      {activeNodes.map((node) => {
        // Compute search-matching logic
        let isMatched = false;
        if (matchingNodeIds === null) {
          isMatched = true;
        } else if (node.id < 0) {
          // Hub centroid node: match if any connected edge target is matched
          isMatched = edges.some(edge => 
            (edge.source === node.id && matchingNodeIds.has(edge.target)) ||
            (edge.target === node.id && matchingNodeIds.has(edge.source))
          );
        } else {
          isMatched = matchingNodeIds.has(node.id);
        }

        const opacity = isMatched ? 1.0 : 0.1;
        const styles = getNodeStyles(node);
        
        return (
          <div
            key={node.id}
            data-node-id={node.id}
            onClick={() => handleNodeClick(node)}
            role="button"
            tabIndex={0}
            aria-label={`Select node ${node.title}`}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                handleNodeClick(node);
              }
            }}
            className={`constellation-node ${node.type === 'hub' ? 'glass-glow-top' : ''} ${isMatched && matchingNodeIds !== null ? 'search-matched' : ''} ${node.id === selectedNodeId ? 'selected-node' : ''}`}
            style={{
              position: 'absolute',
              top: `${node.y}px`,
              left: `${node.x}px`,
              opacity: opacity,
              cursor: 'pointer',
              transform: 'translate(-50%, -50%)',
              zIndex: node.type === 'hub' ? 3 : 2,
              width: node.type === 'hub' ? '18px' : '11px',
              height: node.type === 'hub' ? '18px' : '11px',
              borderRadius: '50%',
              background: styles.bg,
              border: '1px solid rgba(255, 255, 255, 0.35)',
              boxShadow: styles.shadow,
            }}
          >
            {/* Rotating halo ring for Hub centroids */}
            {node.type === 'hub' && <div className="hub-halo" />}

            {node.type === 'hub' ? (
              // Hub centroid labels are always visible in dim monospace
              <span className="constellation-node-hub-label">
                {node.title}
              </span>
            ) : (
              // Orbital node labels are styled as floating glass badges that fade-in on hover
              <span className="constellation-node-label">
                {node.title}
              </span>
            )}
          </div>
        );
      })}
      
      {/* Constellation Connection Lines */}
      <svg style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', overflow: 'visible', pointerEvents: 'none', zIndex: 1 }}>
        {edges && edges.map((edge, idx) => {
          const sourceNode = activeNodes.find(n => n.id === edge.source);
          const targetNode = activeNodes.find(n => n.id === edge.target);
          if (!sourceNode || !targetNode) return null;

          // Calculate curved path (quadratic bezier curve)
          const x1 = sourceNode.x;
          const y1 = sourceNode.y;
          const x2 = targetNode.x;
          const y2 = targetNode.y;
          const mx = (x1 + x2) / 2;
          const my = (y1 + y2) / 2;
          const dx = x2 - x1;
          const dy = y2 - y1;
          const len = Math.sqrt(dx * dx + dy * dy) || 1;
          
          // Perpendicular offset of 25px
          const ox = -dy / len * 25;
          const oy = dx / len * 25;
          const cx = mx + ox;
          const cy = my + oy;
          const pathD = `M ${x1} ${y1} Q ${cx} ${cy} ${x2} ${y2}`;

          // Search-matching logic for edges
          let isEdgeMatched = false;
          if (matchingNodeIds === null) {
            isEdgeMatched = true;
          } else {
            const isSourceHub = sourceNode.id < 0;
            const isTargetHub = targetNode.id < 0;
            if (isSourceHub && !isTargetHub) {
              isEdgeMatched = matchingNodeIds.has(targetNode.id);
            } else if (!isSourceHub && isTargetHub) {
              isEdgeMatched = matchingNodeIds.has(sourceNode.id);
            } else {
              isEdgeMatched = matchingNodeIds.has(sourceNode.id) && matchingNodeIds.has(targetNode.id);
            }
          }

          const pathOpacity = isEdgeMatched ? 0.35 : 0.05;
          const pathColor = isEdgeMatched ? 'var(--color-secondary)' : 'rgba(255, 255, 255, 0.1)';

          return (
            <g key={idx}>
              {/* Base curved path */}
              <path
                d={pathD}
                fill="none"
                stroke={pathColor}
                strokeWidth="1.5"
                style={{ opacity: pathOpacity, transition: 'stroke 0.3s ease, opacity 0.3s ease' }}
              />
              {/* Glowing animated pulse overlay line */}
              {isEdgeMatched && (
                <path
                  d={pathD}
                  fill="none"
                  stroke="var(--color-secondary)"
                  strokeWidth="1.5"
                  className="flowing-edge"
                  style={{ opacity: 0.5 }}
                />
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}
