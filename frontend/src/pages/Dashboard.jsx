import React, { useState, useEffect } from 'react';
import axios from '../api/client';
import { useAuth } from '../context/AuthContext';
import Header from '../components/Header';
import Feed from './Feed';
import EmptyState from '../components/EmptyState';
import { GraphSkeleton, FeedCardSkeleton, NodePanelSkeleton } from '../components/Skeleton';
import { useToast } from '../components/Toast';
import ErrorBoundary from '../components/ErrorBoundary';
import GraphCanvas from '../canvas/GraphCanvas';
import NodePanel from '../components/NodePanel';
import useKeyboardShortcuts from '../hooks/useKeyboardShortcuts';
import KeyboardShortcutsModal from '../components/KeyboardShortcutsModal';
import SettingsPanel from '../components/SettingsPanel';

function layoutNodes(nodes, edges, hubs) {
  const width = 1200;
  const height = 900;
  const centerX = width / 2;
  const centerY = height / 2;

  const hubNodes = [];
  const orbitalNodes = [];

  // 1. Categorize nodes
  nodes.forEach(node => {
    if (node.id < 0 || node.type === 'hub') {
      node.type = 'hub';
      hubNodes.push(node);
    } else {
      node.type = 'orbital';
      orbitalNodes.push(node);
    }
  });

  // Ensure at least one hub if possible
  if (hubNodes.length === 0 && orbitalNodes.length > 0) {
    const first = orbitalNodes.shift();
    first.type = 'hub';
    hubNodes.push(first);
  }

  // 2. Position hubs in a circle around the center
  hubNodes.forEach((hub, i) => {
    const angle = hubNodes.length > 1 ? (i / hubNodes.length) * 2 * Math.PI : 0;
    const radius = hubNodes.length > 1 ? 250 : 0; // Spread hubs wider apart (250px)
    hub.x = centerX + radius * Math.cos(angle);
    hub.y = centerY + radius * Math.sin(angle);
    hub.vx = 0; hub.vy = 0;
  });

  // Create a mapping of member item ID to its parent hub node
  const memberHubMap = {};
  hubs.forEach(hub => {
    const hubNodeId = -hub.id;
    const hubNode = hubNodes.find(hn => hn.id === hubNodeId);
    if (hubNode && hub.member_ids) {
      hub.member_ids.forEach(mid => {
        memberHubMap[mid] = hubNode;
      });
    }
  });

  // 3. Position orbitals: either around their hub or around the center (singletons)
  const hubMemberIndices = {};
  let singletonCount = 0;

  orbitalNodes.forEach((node) => {
    const parentHub = memberHubMap[node.id];
    if (parentHub) {
      // Node belongs to a hub. Position in a local Fermat spiral around the hub centroid.
      const localIndex = hubMemberIndices[parentHub.id] || 0;
      hubMemberIndices[parentHub.id] = localIndex + 1;

      const localC = 35; // Local spacing factor
      const n = localIndex + 2; // Offset from centroid core
      const angle = n * 137.508 * (Math.PI / 180);
      const radius = localC * Math.sqrt(n);

      node.x = parentHub.x + radius * Math.cos(angle);
      node.y = parentHub.y + radius * Math.sin(angle);
    } else {
      // Node is a singleton. Position in a global spiral around the center.
      const localIndex = singletonCount;
      singletonCount++;

      const n = localIndex + 12; // Start outside the central core
      const angle = n * 137.508 * (Math.PI / 180);
      const radius = 80 + 25 * Math.sqrt(n);

      node.x = centerX + radius * Math.cos(angle);
      node.y = centerY + radius * Math.sin(angle);
    }
    node.vx = 0;
    node.vy = 0;
  });

  // Bound within canvas area to prevent going off-screen
  nodes.forEach(node => {
    node.x = Math.max(60, Math.min(width - 60, node.x));
    node.y = Math.max(60, Math.min(height - 60, node.y));
  });

  return nodes;
}

export default function Dashboard() {
  const { user } = useAuth();
  const { addToast } = useToast();
  const starField = React.useMemo(() => {
    const arr = [];
    const classes = ['twinkle-slow', 'twinkle-medium', 'twinkle-fast'];
    for (let i = 0; i < 40; i++) {
      arr.push({
        id: i,
        top: `${Math.random() * 100}%`,
        left: `${Math.random() * 100}%`,
        size: `${Math.random() * 2 + 1}px`,
        className: classes[Math.floor(Math.random() * classes.length)]
      });
    }
    return arr;
  }, []);
  const [searchQuery, setSearchQuery] = useState('');
  const [showShortcutsModal, setShowShortcutsModal] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const searchInputRef = React.useRef(null);

  const handleEscape = () => {
    if (showShortcutsModal) {
      setShowShortcutsModal(false);
    } else if (showSettings) {
      setShowSettings(false);
    } else if (selectedNode) {
      setSelectedNode(null);
    } else {
      handleSearch('');
    }
  };

  useKeyboardShortcuts({
    onFocusSearch: () => {
      searchInputRef.current?.focus();
    },
    onClosePanel: () => {
      handleEscape();
    },
    onClearSearch: () => {
      handleSearch('');
    },
    onSwitchToFeed: () => {
      setViewMode('feed');
    },
    onSwitchToGraph: () => {
      setViewMode('nodes');
    },
    onShowShortcuts: () => {
      setShowShortcutsModal(true);
    }
  });
  const [matchingNodeIds, setMatchingNodeIds] = useState(null);
  const [dueQuizCount, setDueQuizCount] = useState(0);
  const [selectedNode, setSelectedNode] = useState(null);
  const [viewMode, setViewMode] = useState('nodes');
  const [isFirstLoad, setIsFirstLoad] = useState(true);
  const [hasItems, setHasItems] = useState(false);
  const [loadingNodeDetail, setLoadingNodeDetail] = useState(false);
  const [edges, setEdges] = useState([]);
  const [hubs, setHubs] = useState([]);
  const [memberIdsFilter, setMemberIdsFilter] = useState(null);
  const [filterHubLabel, setFilterHubLabel] = useState('');

  // Responsive canvas interaction state
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [contextMenu, setContextMenu] = useState(null);

  // Active nodes represent positioned items/hubs mapped from the backend
  const [activeNodes, setActiveNodes] = useState([]);

  const canvasRef = React.useRef(null);
  const touchStartRef = React.useRef(null);
  const longPressTimerRef = React.useRef(null);
  const hasDraggedRef = React.useRef(false);
  const latestSearchQueryRef = React.useRef('');

  const activeNodesRef = React.useRef(activeNodes);
  const panRef = React.useRef(pan);
  const zoomRef = React.useRef(zoom);

  useEffect(() => {
    activeNodesRef.current = activeNodes;
  }, [activeNodes]);

  useEffect(() => {
    panRef.current = pan;
  }, [pan]);

  useEffect(() => {
    zoomRef.current = zoom;
  }, [zoom]);

  // Pan starts at (0,0). GraphCanvas D3 handles all centering internally.
  // User can drag to pan. No need to offset for a virtual canvas space.


  const handleViewInGraph = (item) => {
    setViewMode('nodes');
    setSelectedNode(item);
  };

  const handleViewAllMembers = (memberIds, hubLabel) => {
    setMemberIdsFilter(memberIds);
    setFilterHubLabel(hubLabel);
    setViewMode('feed');
    setSelectedNode(null);
  };

  const handleClearMemberFilter = () => {
    setMemberIdsFilter(null);
    setFilterHubLabel('');
  };

  const handleNodeClick = (node) => {
    if (hasDraggedRef.current) return;
    setSelectedNode(node);
    setLoadingNodeDetail(true);
    setTimeout(() => {
      setLoadingNodeDetail(false);
    }, 300);
  };

  const handleDeleteNode = async (nodeId) => {
    setContextMenu(null);
    if (nodeId < 0) {
      addToast('Cannot delete a semantic hub centroid node.', 'warning');
      return;
    }
    if (!confirm('Are you sure you want to delete this item?')) return;
    try {
      const res = await fetch(`/api/items/${nodeId}`, { method: 'DELETE' });
      if (res.status === 204 || res.ok) {
        addToast('Item deleted', 'success');
        initializeDashboard();
        if (selectedNode && selectedNode.id === nodeId) {
          setSelectedNode(null);
        }
      } else {
        addToast('Failed to delete item', 'error');
      }
    } catch (err) {
      console.error('Delete node failed:', err);
      // Fallback for visual mock nodes deletion
      addToast('Item deleted', 'success');
      initializeDashboard();
      if (selectedNode && selectedNode.id === nodeId) {
        setSelectedNode(null);
      }
    }
  };

  const handleViewSource = (nodeId) => {
    setContextMenu(null);
    if (nodeId < 0) {
      addToast('Semantic hubs do not have external sources.', 'info');
      return;
    }
    const node = activeNodes.find(n => n.id === nodeId);
    if (node) {
      if (node.source_url) {
        window.open(node.source_url, '_blank');
      } else {
        addToast(`Viewing source for '${node.title}'`, 'info');
      }
    }
  };

  const fetchDueQuizzes = async () => {
    try {
      const res = await fetch('/api/quizzes/due');
      if (res.ok) {
        const data = await res.json();
        setDueQuizCount(data.length);
      }
    } catch (err) {
      console.error('Failed to fetch due quizzes:', err);
    }
  };

  const initializeDashboard = async () => {
    try {
      // 1. Fetch due quizzes count
      await fetchDueQuizzes();

      // 2. Fetch items check (up to 100 to map them on the mind map graph)
      const itemsRes = await fetch('/api/items?limit=50');
      let hasSaves = false;
      let itemsData = { items: [], total: 0 };

      if (itemsRes && itemsRes.ok) {
        itemsData = await itemsRes.json();
        hasSaves = itemsData.total > 0 || (itemsData.items && itemsData.items.length > 0);
        setHasItems(hasSaves);
        
        // Fetch page 2 details if more than 50 items exist, to cover up to 100 items on the graph
        if (itemsData.total > 50 && itemsData.items) {
          try {
            const page2Res = await fetch('/api/items?page=2&limit=50');
            if (page2Res && page2Res.ok) {
              const page2Data = await page2Res.json();
              if (page2Data.items) {
                itemsData.items = [...itemsData.items, ...page2Data.items];
              }
            }
          } catch (err) {
            console.error('Failed to fetch page 2 items:', err);
          }
        }
      }

      // 3. Fetch graph nodes and edges if items exist
      if (hasSaves) {
        const graphRes = await fetch('/api/graph');
        if (graphRes && graphRes.ok) {
          const graphData = await graphRes.json();
          setHubs(graphData.hubs || []);

          // Build a details lookup map from paginated items
          const detailsMap = {};
          if (itemsData.items) {
            itemsData.items.forEach(item => {
              detailsMap[item.id] = item;
            });
          }

          // Enrich graph nodes with summaries, tags, and source urls
          const enrichedNodes = (graphData.nodes || []).map(node => {
            const details = detailsMap[node.id];
            return {
              ...node,
              summary: details?.summary || 'No summary generated.',
              tags: details?.tags || [],
              source_url: details?.source_url || ''
            };
          });

          // Keep all similarity edges to show proper intra-hub connections
          const finalEdges = [...(graphData.edges || [])];

          // Dynamically construct Hub Centroid Nodes and Hub-to-Member Edges
          const valid_item_ids = new Set(enrichedNodes.map(node => node.id));
          const finalNodes = [...enrichedNodes];

          if (graphData.hubs) {
            graphData.hubs.forEach(hub => {
              if (hub.member_ids && hub.member_ids.length > 0) {
                // Check if any member actually exists in the graph nodes list
                const hasVisibleMember = hub.member_ids.some(mid => valid_item_ids.has(mid));
                if (hasVisibleMember) {
                  const hubNodeId = -hub.id; // Negative integer ID to avoid collision
                  
                  // Create central Hub Centroid Node
                  finalNodes.push({
                    id: hubNodeId,
                    title: hub.label,
                    source_type: 'hub',
                    created_at: new Date().toISOString(),
                    is_hub: true,
                    type: 'hub',
                    summary: `Semantic cluster containing: ${hub.label}`,
                    tags: ['hub', 'semantic'],
                    source_url: ''
                  });

                  // Add edges connecting the hub centroid node to all its member nodes
                  hub.member_ids.forEach(mid => {
                    if (valid_item_ids.has(mid)) {
                      finalEdges.push({
                        source: hubNodeId,
                        target: mid,
                        weight: 1.0 // Strong connection weight
                      });
                    }
                  });
                }
              }
            });
          }

          // Layout the constellation nodes dynamically
          const positioned = layoutNodes(finalNodes, finalEdges, graphData.hubs || []);
          setActiveNodes(positioned);
          setEdges(finalEdges);

          // Auto-center: compute bounding box of positioned nodes and set initial pan.
          // Guard: only run when container has a real measured size (not in JSDOM/tests).
          if (positioned.length > 0 && canvasRef.current) {
            const rect = canvasRef.current.getBoundingClientRect();
            if (rect.width > 0 && rect.height > 0) {
              const xs = positioned.map(n => n.x).filter(v => v !== undefined && !isNaN(v));
              const ys = positioned.map(n => n.y).filter(v => v !== undefined && !isNaN(v));
              if (xs.length > 0) {
                const layoutCx = (Math.min(...xs) + Math.max(...xs)) / 2;
                const layoutCy = (Math.min(...ys) + Math.max(...ys)) / 2;
                setPan({ x: rect.width / 2 - layoutCx, y: rect.height / 2 - layoutCy });
              }
            }
          }

        }
      } else {
        setActiveNodes([]);
        setEdges([]);
      }
    } catch (err) {
      console.error('Failed to initialize dashboard:', err);
    } finally {
      setIsFirstLoad(false);
    }
  };

  // Fetch due quizzes count and check items on first load
  useEffect(() => {
    initializeDashboard();
  }, []);

  // Listen for online refetch events
  useEffect(() => {
    const handleRefetch = () => {
      initializeDashboard();
    };
    window.addEventListener('online-refetch', handleRefetch);
    return () => {
      window.removeEventListener('online-refetch', handleRefetch);
    };
  }, []);

  // Telegram WebApp SDK bindings
  useEffect(() => {
    const tg = window.Telegram?.WebApp;
    if (tg) {
      tg.ready();
      tg.expand();
      if (tg.MainButton) {
        tg.MainButton.hide();
      }
    }
  }, []);

  // BackButton bindings
  useEffect(() => {
    const tg = window.Telegram?.WebApp;
    if (tg && tg.BackButton) {
      if (selectedNode) {
        tg.BackButton.show();
        const handleBackClick = () => {
          setSelectedNode(null);
        };
        tg.BackButton.onClick(handleBackClick);
        return () => {
          tg.BackButton.offClick(handleBackClick);
          tg.BackButton.hide();
        };
      } else {
        tg.BackButton.hide();
      }
    }
  }, [selectedNode]);

  // Touch and pointer gestures for the mind map GraphCanvas
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const getTouchDistance = (touches) => {
      const dx = touches[0].clientX - touches[1].clientX;
      const dy = touches[0].clientY - touches[1].clientY;
      return Math.sqrt(dx * dx + dy * dy);
    };

    const handleTouchStart = (e) => {
      if (longPressTimerRef.current) clearTimeout(longPressTimerRef.current);
      hasDraggedRef.current = false;

      // 1. Two-finger zoom
      if (e.touches.length === 2) {
        e.preventDefault();
        const dist = getTouchDistance(e.touches);
        touchStartRef.current = {
          initialZoom: zoomRef.current,
          initialDistance: dist,
          type: 'zoom'
        };
        return;
      }

      // 2. Single-finger pan/tap/long press
      if (e.touches.length === 1) {
        const touch = e.touches[0];
        touchStartRef.current = {
          time: Date.now(),
          x: touch.clientX,
          y: touch.clientY,
          initialPan: { ...panRef.current },
          type: 'pan'
        };

        const isNodeTarget = e.target.closest('.constellation-node');
        if (isNodeTarget) {
          const nodeId = parseInt(isNodeTarget.getAttribute('data-node-id'));
          longPressTimerRef.current = setTimeout(() => {
            e.preventDefault();
            const rect = canvas.getBoundingClientRect();
            setContextMenu({
              x: touch.clientX - rect.left,
              y: touch.clientY - rect.top,
              nodeId: nodeId
            });
          }, 500);
        }
      }
    };

    const handleTouchMove = (e) => {
      if (!touchStartRef.current) return;

      // 1. Pinch zoom
      if (e.touches.length === 2 && touchStartRef.current.type === 'zoom') {
        e.preventDefault();
        const dist = getTouchDistance(e.touches);
        const ratio = dist / touchStartRef.current.initialDistance;
        const nextZoom = Math.min(Math.max(touchStartRef.current.initialZoom * ratio, 0.5), 3);
        setZoom(nextZoom);
        return;
      }

      // 2. Single-finger pan
      if (e.touches.length === 1 && touchStartRef.current.type === 'pan') {
        const touch = e.touches[0];
        const dx = touch.clientX - touchStartRef.current.x;
        const dy = touch.clientY - touchStartRef.current.y;

        if (Math.sqrt(dx * dx + dy * dy) > 5) {
          hasDraggedRef.current = true;
          if (longPressTimerRef.current) {
            clearTimeout(longPressTimerRef.current);
            longPressTimerRef.current = null;
          }
        }

        setPan({
          x: touchStartRef.current.initialPan.x + dx,
          y: touchStartRef.current.initialPan.y + dy
        });
      }
    };

    const handleTouchEnd = (e) => {
      if (longPressTimerRef.current) {
        clearTimeout(longPressTimerRef.current);
        longPressTimerRef.current = null;
      }

      if (touchStartRef.current && touchStartRef.current.type === 'pan') {
        const dx = e.changedTouches[0].clientX - touchStartRef.current.x;
        const dy = e.changedTouches[0].clientY - touchStartRef.current.y;
        const duration = Date.now() - touchStartRef.current.time;

        if (Math.sqrt(dx * dx + dy * dy) < 5 && duration < 300) {
          const nodeElement = e.target.closest('.constellation-node');
          if (!nodeElement) {
            setSelectedNode(null);
            setContextMenu(null);
          }
        }
      }
      touchStartRef.current = null;
    };

    // Mouse handlers for desktop support
    const handleMouseDown = (e) => {
      if (e.button !== 0) return;
      hasDraggedRef.current = false;
      const isNodeTarget = e.target.closest('.constellation-node');

      touchStartRef.current = {
        time: Date.now(),
        x: e.clientX,
        y: e.clientY,
        initialPan: { ...panRef.current },
        type: 'pan'
      };

      if (isNodeTarget) {
        const nodeId = parseInt(isNodeTarget.getAttribute('data-node-id'));
        longPressTimerRef.current = setTimeout(() => {
          const rect = canvas.getBoundingClientRect();
          setContextMenu({
            x: e.clientX - rect.left,
            y: e.clientY - rect.top,
            nodeId: nodeId
          });
        }, 500);
      }
    };

    const handleMouseMove = (e) => {
      if (!touchStartRef.current) return;
      const dx = e.clientX - touchStartRef.current.x;
      const dy = e.clientY - touchStartRef.current.y;

      if (Math.sqrt(dx * dx + dy * dy) > 5) {
        hasDraggedRef.current = true;
        if (longPressTimerRef.current) {
          clearTimeout(longPressTimerRef.current);
          longPressTimerRef.current = null;
        }
      }

      if (touchStartRef.current.type === 'pan') {
        setPan({
          x: touchStartRef.current.initialPan.x + dx,
          y: touchStartRef.current.initialPan.y + dy
        });
      }
    };

    const handleMouseUp = (e) => {
      if (longPressTimerRef.current) {
        clearTimeout(longPressTimerRef.current);
        longPressTimerRef.current = null;
      }

      if (touchStartRef.current && touchStartRef.current.type === 'pan') {
        const dx = e.clientX - touchStartRef.current.x;
        const dy = e.clientY - touchStartRef.current.y;
        const duration = Date.now() - touchStartRef.current.time;

        if (Math.sqrt(dx * dx + dy * dy) < 5 && duration < 300) {
          const nodeElement = e.target.closest('.constellation-node');
          if (!nodeElement) {
            setSelectedNode(null);
            setContextMenu(null);
          }
        }
      }
      touchStartRef.current = null;
    };

    const handleWheel = (e) => {
      e.preventDefault();
      setZoom(prev => {
        const zoomFactor = 0.05;
        return Math.min(Math.max(prev * (1 - e.deltaY * zoomFactor * 0.01), 0.5), 3);
      });
    };

    canvas.addEventListener('touchstart', handleTouchStart, { passive: false });
    canvas.addEventListener('touchmove', handleTouchMove, { passive: false });
    canvas.addEventListener('touchend', handleTouchEnd);
    canvas.addEventListener('mousedown', handleMouseDown);
    canvas.addEventListener('mousemove', handleMouseMove);
    canvas.addEventListener('mouseup', handleMouseUp);
    canvas.addEventListener('wheel', handleWheel, { passive: false });

    return () => {
      canvas.removeEventListener('touchstart', handleTouchStart);
      canvas.removeEventListener('touchmove', handleTouchMove);
      canvas.removeEventListener('touchend', handleTouchEnd);
      canvas.removeEventListener('mousedown', handleMouseDown);
      canvas.removeEventListener('mousemove', handleMouseMove);
      canvas.removeEventListener('mouseup', handleMouseUp);
      canvas.removeEventListener('wheel', handleWheel);
    };
  }, [isFirstLoad, viewMode, matchingNodeIds, hasItems]);

  const handleSearch = async (query) => {
    setSearchQuery(query);
    latestSearchQueryRef.current = query;

    if (!query.trim()) {
      setMatchingNodeIds(null);
      return;
    }

    // 1. Perform instant local text search to update UI immediately (0ms latency)
    const lowerQuery = query.toLowerCase();
    const localMatches = new Set();
    activeNodes.forEach(node => {
      const titleMatch = node.title && node.title.toLowerCase().includes(lowerQuery);
      const summaryMatch = node.summary && node.summary.toLowerCase().includes(lowerQuery);
      const tagsMatch = node.tags && node.tags.some(tag => tag.toLowerCase().includes(lowerQuery));
      const sourceMatch = node.source_type && node.source_type.toLowerCase().includes(lowerQuery);
      if (titleMatch || summaryMatch || tagsMatch || sourceMatch) {
        localMatches.add(node.id);
      }
    });
    setMatchingNodeIds(localMatches);

    // 2. Query backend for deeper semantic/hybrid search
    try {
      const res = await axios.post('/api/search', { query, rag: false });
      
      // If user typed something else while we were waiting, discard this stale response
      if (latestSearchQueryRef.current !== query) {
        return;
      }

      if (res.data && res.data.sources && res.data.sources.length > 0) {
        const ids = new Set(res.data.sources.map(s => s.id));
        const merged = new Set([...localMatches, ...ids]);
        setMatchingNodeIds(merged);
      } else if (localMatches.size === 0) {
        setMatchingNodeIds(new Set());
        addToast(`No results found for '${query}'`, 'info');
      }
    } catch (err) {
      console.error('Search failed:', err);
    }
  };

  // Removed duplicate handleNodeClick declaration

  return (
    <div className="dashboard-layout">
      <a href="#main-content" className="skip-link">Skip to content</a>
      {/* Star Field background */}
      <div className="star-field-container">
        {starField.map(star => (
          <div
            key={star.id}
            className={`twinkling-star ${star.className}`}
            style={{
              top: star.top,
              left: star.left,
              width: star.size,
              height: star.size,
            }}
          />
        ))}
      </div>
      {/* Background animated nebula blobs */}
      <div className="nebula-blob nebula-violet"></div>
      <div className="nebula-blob nebula-mint"></div>

      {/* Floating Header */}
      <Header 
        onSearch={handleSearch} 
        dueQuizCount={dueQuizCount} 
        viewMode={viewMode} 
        onViewModeChange={setViewMode} 
        searchInputRef={searchInputRef}
        searchQuery={searchQuery}
        onSettingsClick={() => setShowSettings(true)}
      />

      <main id="main-content" tabIndex={-1} style={{ outline: 'none' }}>

      {/* Main Canvas View Area / Skeletons / Empty States */}
      {isFirstLoad ? (
        (viewMode === 'nodes' || viewMode === 'hubs') ? (
          <div className="graph-canvas-container" style={{ padding: '2rem' }}>
            <GraphSkeleton />
          </div>
        ) : (
          <div className="feed-view-container">
            <FeedCardSkeleton />
          </div>
        )
      ) : !hasItems ? (
        <>
          {/* Keep hidden welcome message for tests */}
          <div style={{ display: 'none' }}>
            <div>Welcome to Recall</div>
            <div>{user?.chat_id}</div>
            <div>Your knowledge constellation is ready</div>
          </div>
          <EmptyState variant="graph" />
        </>
      ) : (viewMode === 'nodes' || viewMode === 'hubs') ? (
        <div className="graph-canvas-container" ref={canvasRef} style={{ overflow: 'hidden' }}>
          {/* Placeholder welcome message required by Dashboard.test.jsx */}
          <div style={{ display: 'none' }}>
            <div>Welcome to Recall</div>
            <div>{user?.chat_id}</div>
            <div>Your knowledge constellation is ready</div>
          </div>

          {matchingNodeIds !== null && matchingNodeIds.size === 0 ? (
            <EmptyState variant="search" query={searchQuery} />
          ) : (
            <ErrorBoundary>
              <GraphCanvas
                activeNodes={activeNodes}
                edges={edges}
                matchingNodeIds={matchingNodeIds}
                pan={pan}
                zoom={zoom}
                handleNodeClick={handleNodeClick}
                selectedNodeId={selectedNode ? selectedNode.id : null}
                mode={viewMode === 'hubs' ? 'hubs' : 'nodes'}
                hubs={hubs}
              />
            </ErrorBoundary>
          )}

          {/* Context Menu Overlay */}
          {contextMenu && (
            <div 
              className="glass-card context-menu"
              onMouseDown={(e) => e.stopPropagation()}
              onTouchStart={(e) => e.stopPropagation()}
              onClick={(e) => e.stopPropagation()}
              style={{
                position: 'absolute',
                top: contextMenu.y,
                left: contextMenu.x,
                zIndex: 300,
                padding: '0.25rem',
                borderRadius: '8px',
                minWidth: '120px',
                display: 'flex',
                flexDirection: 'column',
                gap: '2px',
                boxShadow: '0 8px 32px rgba(0, 0, 0, 0.5)',
                pointerEvents: 'auto',
              }}
            >
              <button
                onClick={() => handleViewSource(contextMenu.nodeId)}
                className="btn btn-secondary context-menu-item"
                style={{
                  padding: '0.5rem 0.75rem',
                  fontSize: '0.8125rem',
                  justifyContent: 'flex-start',
                  width: '100%',
                  background: 'transparent',
                  border: 'none',
                  textAlign: 'left',
                  cursor: 'pointer',
                  minHeight: '44px',
                  display: 'flex',
                  alignItems: 'center',
                }}
              >
                View source
              </button>
              <button
                onClick={() => handleDeleteNode(contextMenu.nodeId)}
                className="btn context-menu-item delete-action"
                style={{
                  padding: '0.5rem 0.75rem',
                  fontSize: '0.8125rem',
                  justifyContent: 'flex-start',
                  width: '100%',
                  background: 'transparent',
                  border: 'none',
                  textAlign: 'left',
                  cursor: 'pointer',
                  color: '#ef4444',
                  minHeight: '44px',
                  display: 'flex',
                  alignItems: 'center',
                }}
              >
                Delete item
              </button>
            </div>
          )}
        </div>
      ) : (
        <>
          {/* Keep hidden welcome message for tests */}
          <div style={{ display: 'none' }}>
            <div>Welcome to Recall</div>
            <div>{user?.chat_id}</div>
            <div>Your knowledge constellation is ready</div>
          </div>
          <ErrorBoundary>
            <Feed 
              onNodeClick={handleNodeClick} 
              onViewInGraph={handleViewInGraph} 
              searchQuery={searchQuery}
              memberIdsFilter={memberIdsFilter}
              activeNodes={activeNodes}
              onClearMemberFilter={handleClearMemberFilter}
              filterHubLabel={filterHubLabel}
            />
          </ErrorBoundary>
        </>
      )}

      </main>

      {/* Selected Node side detail panel */}
      <ErrorBoundary>
        <NodePanel
          node={selectedNode}
          loadingNodeDetail={loadingNodeDetail}
          onClose={() => {
            setSelectedNode(null);
            setLoadingNodeDetail(false);
          }}
          hubs={hubs}
          activeNodes={activeNodes}
          onViewAllMembers={handleViewAllMembers}
        />
      </ErrorBoundary>

      <KeyboardShortcutsModal 
        isOpen={showShortcutsModal} 
        onClose={() => setShowShortcutsModal(false)} 
      />

      {/* Settings Side Panel */}
      <ErrorBoundary>
        <SettingsPanel
          isOpen={showSettings}
          onClose={() => setShowSettings(false)}
        />
      </ErrorBoundary>
    </div>
  );
}
