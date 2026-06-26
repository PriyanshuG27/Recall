import React, { useRef, useEffect, useState, useMemo } from 'react';
import * as d3 from 'd3';

// Helper to get node radius
function getNodeRadius(node, hubs = []) {
  if (node.type === 'hub' || node.id < 0) {
    const hubId = node.id < 0 ? -node.id : node.id;
    const hub = hubs.find(h => h.id === hubId);
    const memberCount = hub?.member_ids?.length || 0;
    return Math.max(20, 20 + memberCount * 0.8);
  }
  return 8;
}

// Helper to get source type glow color
function getGlowColor(sourceType) {
  switch (sourceType) {
    case 'url':
      return 'rgba(0, 242, 254, 0.4)'; // Neon Cyan
    case 'pdf':
      return 'rgba(255, 8, 68, 0.4)';  // Ruby Crimson
    case 'voice':
      return 'rgba(177, 0, 255, 0.4)'; // Electric Purple
    case 'image':
    case 'photo':
      return 'rgba(0, 255, 135, 0.4)'; // Neon Mint
    case 'text':
      return 'rgba(249, 212, 35, 0.4)';  // Golden Amber
    default:
      return 'rgba(108, 99, 255, 0.4)'; // Electric Indigo / Primary Glow
  }
}

export default function GraphCanvas({
  activeNodes = [],
  edges = [],
  matchingNodeIds = null,
  pan = { x: 0, y: 0 },
  zoom = 1,
  handleNodeClick,
  onNodeClick,
  selectedNodeId = null,
  mode = 'nodes',
  hubs = []
}) {
  const canvasRef = useRef(null);
  const containerRef = useRef(null);
  const overlayRef = useRef(null);

  // Fallbacks for onClick handler
  const clickHandler = onNodeClick || handleNodeClick;

  const isHubsMode = mode === 'hubs';
  const displayNodes = isHubsMode
    ? activeNodes.filter(n => n.type === 'hub' || n.id < 0)
    : activeNodes.filter(n => n.id > 0);

  const displayEdges = useMemo(() => {
    if (!isHubsMode) {
      // In nodes mode, only keep item-to-item similarity edges
      return edges.filter(edge => {
        const s = typeof edge.source === 'object' ? edge.source.id : edge.source;
        const t = typeof edge.target === 'object' ? edge.target.id : edge.target;
        return s > 0 && t > 0;
      });
    }
    
    // Map item ID to hub node ID (negative integer)
    const itemToHubMap = new Map();
    hubs.forEach(h => {
      const hubNodeId = -h.id;
      if (h.member_ids) {
        h.member_ids.forEach(mId => {
          itemToHubMap.set(mId, hubNodeId);
        });
      }
    });

    const hubEdgesMap = new Map();
    edges.forEach(edge => {
      const s = typeof edge.source === 'object' ? edge.source.id : edge.source;
      const t = typeof edge.target === 'object' ? edge.target.id : edge.target;
      
      // Only look at similarity edges between items (positive IDs)
      if (s > 0 && t > 0) {
        const hubS = itemToHubMap.get(s);
        const hubT = itemToHubMap.get(t);
        if (hubS && hubT && hubS !== hubT) {
          const uS = Math.min(hubS, hubT);
          const uT = Math.max(hubS, hubT);
          const key = `${uS}_${uT}`;
          if (!hubEdgesMap.has(key)) {
            hubEdgesMap.set(key, { source: uS, target: uT, weight: edge.weight || 1.0 });
          }
        }
      }
    });
    return Array.from(hubEdgesMap.values());
  }, [edges, hubs, isHubsMode]);

  // Local pan and zoom states in case parent does not manage them
  const [localPan, setLocalPan] = useState(pan);
  const [localZoom, setLocalZoom] = useState(zoom);

  // Sync props to local state
  useEffect(() => {
    setLocalPan(pan);
  }, [pan.x, pan.y]);

  useEffect(() => {
    setLocalZoom(zoom);
  }, [zoom]);

  // Keep refs for pan and zoom to read inside requestAnimationFrame without closures
  const panRef = useRef(localPan);
  const zoomRef = useRef(localZoom);
  useEffect(() => {
    panRef.current = localPan;
  }, [localPan]);
  useEffect(() => {
    zoomRef.current = localZoom;
  }, [localZoom]);

  // Refs for tracking drag state
  const isDraggingRef = useRef(false);
  const dragStartRef = useRef({ x: 0, y: 0 });

  // Refs for D3 simulation
  const simulationRef = useRef(null);
  const nodesRef = useRef([]);
  const linksRef = useRef([]);

  // Animation values
  const animationFrameRef = useRef(null);
  const rotAngleRef = useRef(0);
  const flowOffsetRef = useRef(0);
  const hoveredNodeIdRef = useRef(null);

  // Detect prefers-reduced-motion
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;
    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    setPrefersReducedMotion(mediaQuery.matches);
    const listener = (e) => setPrefersReducedMotion(e.matches);
    mediaQuery.addEventListener('change', listener);
    return () => mediaQuery.removeEventListener('change', listener);
  }, []);

  // Handle window resizing using ResizeObserver
  // Initialize with actual DOM size immediately to avoid forceCenter targeting the wrong point
  const getDimensions = () => {
    const container = containerRef.current;
    if (container) {
      const rect = container.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) {
        return { width: rect.width, height: rect.height };
      }
    }
    return { width: 900, height: 650 };
  };
  const [dimensions, setDimensions] = useState(() => getDimensions());
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    // Read real size immediately on mount
    const rect = container.getBoundingClientRect();
    if (rect.width > 0 && rect.height > 0) {
      setDimensions({ width: rect.width, height: rect.height });
    }

    if (typeof ResizeObserver === 'undefined') return;

    const observer = new ResizeObserver((entries) => {
      if (!entries || entries.length === 0) return;
      const { width, height } = entries[0].contentRect;
      if (width > 0 && height > 0) {
        setDimensions({ width, height });
      }
    });

    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  // Use the completely static, mathematically perfect Golden Spiral layout from Dashboard.
  // We completely strip D3 here because physics engines on densely connected star graphs
  // inevitably collapse into a singularity or explode unless perfectly tuned.
  // This guarantees 0 overlaps, 0 crashes, and instant performance.
  useEffect(() => {
    if (!displayNodes || displayNodes.length === 0) {
      nodesRef.current = [];
      linksRef.current = [];
      return;
    }

    // 1. Direct copy of pre-computed, guaranteed-spread positions
    nodesRef.current = displayNodes.map(node => ({ ...node }));

    // 2. Map links to node object references safely
    const nodeMap = new Map(nodesRef.current.map(n => [n.id, n]));
    linksRef.current = (displayEdges || [])
      .map(edge => {
        const s = typeof edge.source === 'object' ? edge.source.id : edge.source;
        const t = typeof edge.target === 'object' ? edge.target.id : edge.target;
        return { ...edge, source: nodeMap.get(s), target: nodeMap.get(t) };
      })
      .filter(edge => edge.source && edge.target);

    if (typeof window !== 'undefined') window.__graphNodes = nodesRef.current;
  }, [displayNodes, displayEdges]);

  // Setup canvas drawing loop (requestAnimationFrame)
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let lastTime = 0;

    const renderLoop = (timestamp) => {
      if (!lastTime) lastTime = timestamp;
      const dt = timestamp - lastTime;
      lastTime = timestamp;

      // Update offsets for rotations and dashes
      if (!prefersReducedMotion) {
        rotAngleRef.current += 0.000785 * dt; // slow rotating hub halo (360 deg every 8s)
        flowOffsetRef.current += 0.15 * dt; // flowing pulse offset
      }

      // 1. Clear Canvas
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // 2. Apply Pan & Zoom Transform
      ctx.save();
      ctx.translate(panRef.current.x, panRef.current.y);
      ctx.scale(zoomRef.current, zoomRef.current);

      // 3. Separate nodes into Hubs and Orbitals for drawing order
      const nodesList = nodesRef.current;
      const linksList = linksRef.current;

      // Check if a hub is selected (Click hub: highlight all member nodes; dim non-members to 20% opacity)
      const isHubSelected = selectedNodeId !== null && selectedNodeId < 0;
      const selectedHubMemberIds = new Set();
      if (isHubSelected) {
        linksList.forEach(link => {
          const s = typeof link.source === 'object' ? link.source.id : link.source;
          const t = typeof link.target === 'object' ? link.target.id : link.target;
          if (s === selectedNodeId) {
            selectedHubMemberIds.add(t);
          } else if (t === selectedNodeId) {
            selectedHubMemberIds.add(s);
          }
        });
      }

      const hubsList = [];
      const orbitals = [];
      nodesList.forEach(n => {
        if (n.type === 'hub' || n.id < 0) {
          hubsList.push(n);
        } else {
          orbitals.push(n);
        }
      });

      // 4. Draw Edges (Quadratic Bezier Curves)
      linksList.forEach(link => {
        const sourceNode = link.source;
        const targetNode = link.target;
        if (!sourceNode || !targetNode || sourceNode.x === undefined || targetNode.x === undefined) return;

        const x1 = sourceNode.x;
        const y1 = sourceNode.y;
        const x2 = targetNode.x;
        const y2 = targetNode.y;

        const midX = (x1 + x2) / 2;
        const midY = (y1 + y2) / 2;
        const controlX = midX + (y2 - y1) * 0.05;
        const controlY = midY - (x2 - x1) * 0.05;

        // Determine edge activation based on search-matching logic
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

        ctx.save();
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.quadraticCurveTo(controlX, controlY, x2, y2);

        if (isEdgeMatched) {
          ctx.strokeStyle = 'rgba(0, 212, 170, 0.65)';
          ctx.lineWidth = 2;
          ctx.shadowBlur = 8;
          ctx.shadowColor = '#00D4AA';
          ctx.stroke();

          // Secondary flowing dashed path
          if (!prefersReducedMotion) {
            ctx.shadowBlur = 0;
            ctx.strokeStyle = 'rgba(0, 212, 170, 0.9)';
            ctx.lineWidth = 1.5;
            ctx.setLineDash([4, 8]);
            ctx.lineDashOffset = -flowOffsetRef.current;
            ctx.beginPath();
            ctx.moveTo(x1, y1);
            ctx.quadraticCurveTo(controlX, controlY, x2, y2);
            ctx.stroke();
          }
        } else {
          ctx.strokeStyle = 'rgba(0, 212, 170, 0.15)';
          ctx.lineWidth = 1;
          ctx.stroke();
        }
        ctx.restore();
      });

      // 5. Draw Orbital Nodes (Standard Items)
      orbitals.forEach(node => {
        if (node.x === undefined || node.y === undefined) return;
        const isHovered = hoveredNodeIdRef.current === node.id;
        const isSelected = selectedNodeId === node.id;
        let opacity = 1.0;
        if (isHubSelected) {
          opacity = selectedHubMemberIds.has(node.id) ? 1.0 : 0.2;
        } else if (matchingNodeIds !== null) {
          opacity = matchingNodeIds.has(node.id) ? 1.0 : 0.1;
        }

        ctx.save();
        ctx.globalAlpha = opacity;

        // Calculate node degree for star glow sizing
        const degree = linksList.filter(l => l.source.id === node.id || l.target.id === node.id).length;
        const radius = 8;
        
        // 1. Draw Star Glow (radial gradient behind node)
        const glowScale = isHovered ? 1.3 : 1.0;
        const glowRadius = radius * (1.5 + degree * 0.3) * glowScale;
        const radialGlow = ctx.createRadialGradient(node.x, node.y, radius * 0.2, node.x, node.y, glowRadius);
        const glowColor = getGlowColor(node.source_type);
        
        radialGlow.addColorStop(0, glowColor);
        radialGlow.addColorStop(1, 'rgba(0, 0, 0, 0)');
        
        ctx.fillStyle = radialGlow;
        ctx.beginPath();
        ctx.arc(node.x, node.y, glowRadius, 0, Math.PI * 2);
        ctx.fill();

        // 2. Draw Frosted Glass Surface
        ctx.fillStyle = 'rgba(10, 10, 20, 0.8)';
        ctx.strokeStyle = isHovered || isSelected ? 'rgba(108, 99, 255, 0.6)' : 'rgba(255, 255, 255, 0.12)';
        ctx.lineWidth = isSelected ? 2.5 : 1.5;
        
        if (isHovered || isSelected) {
          ctx.shadowBlur = 12;
          ctx.shadowColor = '#6C63FF';
        }

        ctx.beginPath();
        ctx.arc(node.x, node.y, radius, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();

        // Check if node is a pulse node (created < 5 min ago)
        const ageInMs = node.created_at ? Date.now() - new Date(node.created_at).getTime() : Infinity;
        const isPulse = ageInMs < 5 * 60 * 1000 || node.type === 'pulse';

        if (isPulse) {
          // White Core
          ctx.fillStyle = '#ffffff';
          ctx.beginPath();
          ctx.arc(node.x, node.y, radius * 0.6, 0, Math.PI * 2);
          ctx.fill();

          // Concentric ripple animation (skip if prefers-reduced-motion is active)
          if (!prefersReducedMotion) {
            const rippleProgress = (timestamp % 1500) / 1500;
            const rippleRadius = radius + rippleProgress * 24;
            const rippleOpacity = 1 - rippleProgress;
            ctx.beginPath();
            ctx.arc(node.x, node.y, rippleRadius, 0, Math.PI * 2);
            ctx.strokeStyle = `rgba(255, 255, 255, ${rippleOpacity})`;
            ctx.lineWidth = 1.5;
            ctx.stroke();
          }
        }

        // Draw Canvas labels for hovered/selected nodes
        if (isHovered || isSelected) {
          ctx.shadowBlur = 0;
          ctx.font = '500 11px Inter';
          ctx.fillStyle = '#F1F1F6';
          ctx.textAlign = 'center';
          ctx.fillText(node.title, node.x, node.y + radius + 18);
        }

        ctx.restore();
      });

      // 6. Draw Hub Nodes (Louvain Centroids) - drawn ABOVE orbital nodes
      hubsList.forEach(node => {
        if (node.x === undefined || node.y === undefined) return;
        const isHovered = hoveredNodeIdRef.current === node.id;
        const isSelected = selectedNodeId === node.id;
        let opacity = 1.0;
        if (isHubSelected) {
          opacity = node.id === selectedNodeId ? 1.0 : 0.2;
        } else if (matchingNodeIds !== null) {
          const isMatched = (
            node.id < 0
              ? [...matchingNodeIds].some(mId => 
                  linksList.some(l => 
                    (l.source.id === node.id && l.target.id === mId) ||
                    (l.target.id === node.id && l.source.id === mId)
                  )
                )
              : matchingNodeIds.has(node.id)
          );
          opacity = isMatched ? 1.0 : 0.1;
        }

        ctx.save();
        ctx.globalAlpha = opacity;

        const radius = getNodeRadius(node, hubs);
        
        // 1. Draw Centroid Glow (mint-teal halo)
        const glowRadius = radius * (1.5 + (isHovered ? 0.5 : 0));
        const radialGlow = ctx.createRadialGradient(node.x, node.y, radius * 0.2, node.x, node.y, glowRadius);
        radialGlow.addColorStop(0, 'rgba(0, 212, 170, 0.25)');
        radialGlow.addColorStop(1, 'rgba(0, 0, 0, 0)');
        
        ctx.fillStyle = radialGlow;
        ctx.beginPath();
        ctx.arc(node.x, node.y, glowRadius, 0, Math.PI * 2);
        ctx.fill();

        // 2. Draw Frosted Surface (teal borders)
        ctx.fillStyle = 'rgba(10, 10, 20, 0.85)';
        ctx.strokeStyle = '#00D4AA';
        ctx.lineWidth = isSelected ? 3 : 2;

        if (isHovered || isSelected) {
          ctx.shadowBlur = 12;
          ctx.shadowColor = '#00D4AA';
        }

        ctx.beginPath();
        ctx.arc(node.x, node.y, radius, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();

        // 3. Draw Slow-Rotating Outer Dashed Ring
        ctx.shadowBlur = 0;
        ctx.strokeStyle = 'rgba(0, 212, 170, 0.4)';
        ctx.lineWidth = 1;
        ctx.setLineDash([4, 6]);
        ctx.lineDashOffset = 0;
        ctx.beginPath();
        ctx.arc(node.x, node.y, radius + 8, rotAngleRef.current, rotAngleRef.current + Math.PI * 2);
        ctx.stroke();

        // Draw label for Hub centroids on canvas (staggered if close to others)
        ctx.font = '600 10px JetBrains Mono';
        ctx.fillStyle = isHovered ? '#00D4AA' : '#8E8E9F';
        ctx.textAlign = 'center';
        
        let labelY = node.y + radius + 20;
        const closeHub = hubsList.find(other => {
          if (other.id === node.id || other.x === undefined || other.y === undefined) return false;
          const dx = node.x - other.x;
          const dy = node.y - other.y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          return dist < 120;
        });
        if (closeHub) {
          const isAbove = node.id < closeHub.id;
          if (isAbove) {
            labelY = node.y - radius - 12;
          }
        }
        ctx.fillText(node.title.toUpperCase(), node.x, labelY);

        ctx.restore();
      });

      ctx.restore();

      // 7. Imperatively update transparent DOM overlay positions at 60 FPS
      if (overlayRef.current) {
        overlayRef.current.style.transform = `translate(${panRef.current.x}px, ${panRef.current.y}px) scale(${zoomRef.current})`;
        
        const overlayChildren = overlayRef.current.children;
        for (let i = 0; i < overlayChildren.length; i++) {
          const child = overlayChildren[i];
          const nodeId = parseInt(child.getAttribute('data-node-id'));
          const node = nodesList.find(n => n.id === nodeId);
          if (node && node.x !== undefined) {
            child.style.left = `${node.x}px`;
            child.style.top = `${node.y}px`;

            // Sync visual opacity for Vitest selectors
            let opacityVal = '1';
            if (isHubSelected) {
              if (node.id === selectedNodeId) {
                opacityVal = '1';
              } else if (node.id < 0) {
                opacityVal = '0.2';
              } else {
                opacityVal = selectedHubMemberIds.has(node.id) ? '1' : '0.2';
              }
            } else if (matchingNodeIds === null) {
              opacityVal = '1';
            } else if (node.id < 0) {
              const isMatched = [...matchingNodeIds].some(mId => 
                linksList.some(link => 
                  (link.source.id === node.id && link.target.id === mId) ||
                  (link.target.id === node.id && link.source.id === mId)
                )
              );
              opacityVal = isMatched ? '1' : '0.1';
            } else {
              opacityVal = matchingNodeIds.has(node.id) ? '1' : '0.1';
            }
            child.style.opacity = opacityVal;
          }
        }
      }

      animationFrameRef.current = requestAnimationFrame(renderLoop);
    };

    animationFrameRef.current = requestAnimationFrame(renderLoop);

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [matchingNodeIds, selectedNodeId, prefersReducedMotion, mode, hubs, displayNodes, displayEdges]);

  // Local drag pan mouse handlers
  const handleMouseDown = (e) => {
    if (e.button !== 0) return;
    const isNode = e.target.closest('.constellation-node');
    if (isNode) return;

    isDraggingRef.current = true;
    dragStartRef.current = { x: e.clientX - localPan.x, y: e.clientY - localPan.y };
  };

  const handleMouseMove = (e) => {
    if (!isDraggingRef.current) return;
    const newPan = {
      x: e.clientX - dragStartRef.current.x,
      y: e.clientY - dragStartRef.current.y
    };
    setLocalPan(newPan);
  };

  const handleMouseUp = () => {
    isDraggingRef.current = false;
  };

  // Local scroll-wheel zoom handler
  // Wheel zoom — must use native listener with {passive:false} to call preventDefault.
  // React's onWheel is passive by default in modern browsers.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const handleWheel = (e) => {
      e.preventDefault();
      const zoomFactor = 0.05;
      const nextZoom = Math.min(Math.max(zoomRef.current * (1 - e.deltaY * zoomFactor * 0.01), 0.3), 3);
      setLocalZoom(nextZoom);
    };
    container.addEventListener('wheel', handleWheel, { passive: false });
    return () => container.removeEventListener('wheel', handleWheel);
  }, []);

  // Helper to compute initial node opacities for JSDOM / test runners
  const getInitialOpacity = (node) => {
    const isHubSelected = selectedNodeId !== null && selectedNodeId < 0;
    if (isHubSelected) {
      if (node.id === selectedNodeId) return '1';
      if (node.id < 0) return '0.2';
      const isMember = edges.some(edge => {
        const sId = typeof edge.source === 'object' ? edge.source.id : edge.source;
        const tId = typeof edge.target === 'object' ? edge.target.id : edge.target;
        return (sId === selectedNodeId && tId === node.id) ||
               (tId === selectedNodeId && sId === node.id);
      });
      return isMember ? '1' : '0.2';
    }
    if (matchingNodeIds === null) return '1';
    if (node.id < 0) {
      const isMatched = edges.some(edge => {
        const sId = typeof edge.source === 'object' ? edge.source.id : edge.source;
        const tId = typeof edge.target === 'object' ? edge.target.id : edge.target;
        return (sId === node.id && matchingNodeIds.has(tId)) ||
               (tId === node.id && matchingNodeIds.has(sId));
      });
      return isMatched ? '1' : '0.1';
    }
    return matchingNodeIds.has(node.id) ? '1' : '0.1';
  };

  return (
    <div
      ref={containerRef}
      style={{
        position: 'relative',
        width: '100%',
        height: '100%',
        overflow: 'hidden',
        background: '#030307',
        userSelect: 'none'
      }}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
    >
      {/* 1. Star Constellation Canvas Drawing Layer */}
      <canvas
        ref={canvasRef}
        width={dimensions.width}
        height={dimensions.height}
        style={{
          display: 'block',
          width: '100%',
          height: '100%'
        }}
      />

      {/* 2. Interactive DOM overlay container for clicks, hovers, accessibility, and Vitest test selectors */}
      <div
        ref={overlayRef}
        className="graph-canvas-inner"
        role="application"
        aria-label="Knowledge constellation"
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          pointerEvents: 'none',
          transformOrigin: '0 0',
          transform: `translate(${localPan.x}px, ${localPan.y}px) scale(${localZoom})`
        }}
      >
        {displayNodes.map((node) => {
          const isHub = node.type === 'hub' || node.id < 0;
          const isSelected = selectedNodeId === node.id;
          const initialOpacity = getInitialOpacity(node);
          const radius = getNodeRadius(node, hubs);
          
          let labelStyle = { pointerEvents: 'none' };
          if (isHub) {
            const closeHub = displayNodes.find(other => {
              if (other.id === node.id || other.x === undefined || other.y === undefined) return false;
              const dx = node.x - other.x;
              const dy = node.y - other.y;
              const dist = Math.sqrt(dx * dx + dy * dy);
              return dist < 120;
            });
            if (closeHub) {
              const isAbove = node.id < closeHub.id;
              if (isAbove) {
                labelStyle = {
                  ...labelStyle,
                  top: 'auto',
                  bottom: '100%',
                  transform: 'translateX(-50%) translateY(-4px)'
                };
              }
            }
          }
          
          return (
            <div
              key={node.id}
              data-node-id={node.id}
              onClick={(e) => {
                e.stopPropagation();
                if (clickHandler) clickHandler(node);
              }}
              onMouseEnter={() => {
                hoveredNodeIdRef.current = node.id;
              }}
              onMouseLeave={() => {
                hoveredNodeIdRef.current = null;
              }}
              role="button"
              tabIndex={0}
              aria-label={`Select node ${node.title}`}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  if (clickHandler) clickHandler(node);
                }
              }}
              className={`constellation-node ${isHub ? 'glass-glow-top' : ''} ${isSelected ? 'selected-node' : ''}`}
              style={{
                position: 'absolute',
                left: node.x !== undefined ? `${node.x}px` : '50%',
                top: node.y !== undefined ? `${node.y}px` : '50%',
                opacity: initialOpacity,
                cursor: 'pointer',
                transform: 'translate(-50%, -50%)',
                pointerEvents: 'auto',
                width: `${radius * 2}px`,
                height: `${radius * 2}px`,
                borderRadius: '50%',
                background: 'transparent',
                border: 'none',
                transition: 'opacity 0.35s ease'
              }}
            >
              {isHub ? (
                <span className="constellation-node-hub-label" style={labelStyle}>
                  {node.title}
                </span>
              ) : (
                <span className="constellation-node-label" style={{ pointerEvents: 'none' }}>
                  {node.title}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
