import React, { useState, useEffect, useRef, useCallback } from 'react';
import { 
  Link as LinkIcon, 
  Microphone, 
  FilePdf, 
  Image as ImageIcon, 
  Note, 
  DotsThree, 
  Trash, 
  Eye 
} from '@phosphor-icons/react';
import EmptyState from '../components/EmptyState';
import { useToast } from '../components/Toast';
import { FeedCardSkeleton } from '../components/Skeleton';
import FormattedText from '../components/FormattedText';


// Relative time helper
function formatRelativeTime(dateString) {
  const now = new Date();
  const date = new Date(dateString);
  const diffMs = now - date;
  
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays === 1) return 'yesterday';
  return `${diffDays}d ago`;
}

// Icon mapping per source type
const iconMap = {
  url: <LinkIcon size={16} />,
  voice: <Microphone size={16} />,
  pdf: <FilePdf size={16} />,
  image: <ImageIcon size={16} />,
  text: <Note size={16} />
};

const DEFAULT_ACTIVE_NODES = [];

export default function Feed({ onNodeClick, onViewInGraph, searchQuery = '', memberIdsFilter = null, activeNodes = DEFAULT_ACTIVE_NODES, onClearMemberFilter, filterHubLabel = '' }) {
  const { addToast } = useToast();
  const [items, setItems] = useState([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [isFirstLoad, setIsFirstLoad] = useState(true);

  // Filters
  const [sourceType, setSourceType] = useState('all');
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [tagFilter, setTagFilter] = useState('');
  const [tagsList, setTagsList] = useState([]);

  // Menu dropdowns
  const [activeMenuId, setActiveMenuId] = useState(null);
  const menuRef = useRef(null);

  // Intersection Observer for Infinite Scroll
  const observer = useRef(null);
  const lastCardRef = useCallback((node) => {
    if (loading) return;
    if (observer.current) observer.current.disconnect();
    
    observer.current = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting && hasMore) {
        setPage(prevPage => prevPage + 1);
      }
    });
    
    if (node) observer.current.observe(node);
  }, [loading, hasMore]);

  // Close dropdown on click outside
  useEffect(() => {
    function handleClickOutside(event) {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setActiveMenuId(null);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('touchstart', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('touchstart', handleClickOutside);
    };
  }, []);

  // Fetch tag counts for typeahead
  useEffect(() => {
    async function fetchTags() {
      try {
        const res = await fetch('/api/tags');
        if (res.ok) {
          const data = await res.json();
          setTagsList(data);
        }
      } catch (err) {
        console.error('Failed to fetch tags list:', err);
      }
    }
    fetchTags();
  }, []);

  // Fetch items list
  const fetchItems = useCallback(async (pageNum, isReset = false) => {
    if (memberIdsFilter) {
      setLoading(true);
      try {
        let matched = activeNodes.filter(n => n.id > 0 && memberIdsFilter.includes(n.id));
        if (sourceType !== 'all') {
          matched = matched.filter(item => item.source_type === sourceType);
        }
        if (tagFilter) {
          matched = matched.filter(item => item.tags && item.tags.includes(tagFilter));
        }
        if (fromDate) {
          const fDate = new Date(fromDate);
          matched = matched.filter(item => new Date(item.created_at) >= fDate);
        }
        if (toDate) {
          const tDate = new Date(toDate);
          matched = matched.filter(item => new Date(item.created_at) <= tDate);
        }
        setItems(matched);
        setTotalPages(1);
        setHasMore(false);
      } catch (err) {
        console.error('Failed to filter items locally:', err);
      } finally {
        setLoading(false);
        setIsFirstLoad(false);
      }
      return;
    }

    setLoading(true);
    try {
      if (searchQuery.trim()) {
        const res = await fetch('/api/search', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query: searchQuery, limit: 50, rag: false })
        });
        if (res.ok) {
          const data = await res.json();
          let searchItems = (data.sources || []).map(s => ({
            id: s.id,
            title: s.title,
            summary: s.summary,
            source_type: s.source_type || 'text',
            source_url: s.source_url,
            tags: s.tags || [],
            created_at: s.created_at
          }));

          // Apply local filters on search results
          if (sourceType !== 'all') {
            searchItems = searchItems.filter(item => item.source_type === sourceType);
          }
          if (tagFilter) {
            searchItems = searchItems.filter(item => item.tags && item.tags.includes(tagFilter));
          }
          if (fromDate) {
            const fDate = new Date(fromDate);
            searchItems = searchItems.filter(item => new Date(item.created_at) >= fDate);
          }
          if (toDate) {
            const tDate = new Date(toDate);
            searchItems = searchItems.filter(item => new Date(item.created_at) <= tDate);
          }

          setItems(searchItems);
          setTotalPages(1);
          setHasMore(false);
        }
        return;
      }

      const queryParams = new URLSearchParams({
        page: pageNum.toString(),
        limit: '20'
      });

      if (sourceType !== 'all') {
        queryParams.append('source_type', sourceType);
      }
      if (tagFilter) {
        queryParams.append('tag', tagFilter);
      }
      if (fromDate) {
        queryParams.append('from_date', fromDate);
      }
      if (toDate) {
        queryParams.append('to_date', toDate);
      }

      const res = await fetch(`/api/items?${queryParams.toString()}`);
      if (res.ok) {
        const data = await res.json();
        setItems(prevItems => isReset ? data.items : [...prevItems, ...data.items]);
        setTotalPages(data.pages);
        setHasMore(pageNum < data.pages);
      }
    } catch (err) {
      console.error('Failed to fetch items:', err);
    } finally {
      setLoading(false);
      setIsFirstLoad(false);
    }
  }, [sourceType, tagFilter, fromDate, toDate, searchQuery, memberIdsFilter, activeNodes]);

  // Reset page and refetch when filters change
  useEffect(() => {
    setPage(1);
    fetchItems(1, true);
  }, [sourceType, tagFilter, fromDate, toDate, searchQuery, fetchItems]);

  // Refetch items when internet reconnects
  useEffect(() => {
    const handleRefetch = () => {
      fetchItems(1, true);
    };
    window.addEventListener('online-refetch', handleRefetch);
    return () => {
      window.removeEventListener('online-refetch', handleRefetch);
    };
  }, [fetchItems]);

  // Fetch next page when page increments
  useEffect(() => {
    if (page > 1) {
      fetchItems(page);
    }
  }, [page, fetchItems]);

  const handleDeleteItem = async (e, itemId) => {
    e.stopPropagation();
    setActiveMenuId(null);
    if (!confirm('Are you sure you want to delete this item?')) return;

    try {
      const res = await fetch(`/api/items/${itemId}`, { method: 'DELETE' });
      if (res.ok) {
        setItems(prev => prev.filter(item => item.id !== itemId));
        addToast('Item deleted', 'success');
      }
    } catch (err) {
      console.error('Failed to delete item:', err);
    }
  };

  const handleToggleMenu = (e, itemId) => {
    e.stopPropagation();
    setActiveMenuId(activeMenuId === itemId ? null : itemId);
  };

  return (
    <div className="feed-view-container">
      {memberIdsFilter && (
        <div className="member-filter-banner glass-card" style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '0.75rem 1rem',
          marginBottom: '1rem',
          borderRadius: '8px',
          border: '1px solid var(--color-accent-glow)',
          background: 'rgba(0, 212, 170, 0.05)',
          pointerEvents: 'auto'
        }}>
          <span style={{ fontSize: '0.875rem', color: 'var(--color-accent)' }}>
            Showing members of <strong>{filterHubLabel || 'semantic hub'}</strong>
          </span>
          <button 
            className="btn btn-secondary" 
            onClick={onClearMemberFilter}
            style={{ padding: '0.25rem 0.75rem', fontSize: '0.75rem', minHeight: '32px', cursor: 'pointer' }}
          >
            Show all
          </button>
        </div>
      )}
      {/* Filter Bar */}
      <div className="filter-bar glass-card">
        <div className="filter-group">
          {['all', 'url', 'voice', 'pdf', 'image', 'text'].map((type) => (
            <button
              key={type}
              onClick={() => setSourceType(type)}
              className={`filter-btn ${sourceType === type ? 'active' : ''}`}
            >
              {type === 'all' ? 'All' : type === 'url' ? 'Links' : type === 'voice' ? 'Voice' : type === 'pdf' ? 'PDFs' : type === 'image' ? 'Images' : 'Text'}
            </button>
          ))}
        </div>

        <div className="filter-inputs">
          {/* Date range picker */}
          <div className="date-picker-group">
            <input 
              type="date" 
              value={fromDate} 
              onChange={(e) => setFromDate(e.target.value)} 
              className="date-input"
              aria-label="From Date"
            />
            <span style={{ color: 'var(--color-text-muted)' }}>to</span>
            <input 
              type="date" 
              value={toDate} 
              onChange={(e) => setToDate(e.target.value)} 
              className="date-input"
              aria-label="To Date"
            />
          </div>

          {/* Search by tag typeahead */}
          <div className="tag-input-group">
            <input
              type="text"
              placeholder="Search by tag..."
              value={tagFilter}
              onChange={(e) => setTagFilter(e.target.value)}
              list="tags-autocomplete"
              className="tag-search-input"
            />
            <datalist id="tags-autocomplete">
              {tagsList.map((t) => (
                <option key={t.tag} value={t.tag}>
                  {t.count} saves
                </option>
              ))}
            </datalist>
          </div>
        </div>
      </div>

      {/* Card Grid / Skeletons / Empty State */}
      {isFirstLoad ? (
        <FeedCardSkeleton />
      ) : items.length > 0 ? (
        <div className="card-grid">
          {items.map((item, index) => {
            const isLastCard = index === items.length - 1;
            const relativeTime = formatRelativeTime(item.created_at);
            
            return (
              <div
                key={item.id}
                ref={isLastCard ? lastCardRef : null}
                onClick={() => onNodeClick(item)}
                className="feed-card glass-card"
              >
                <div className="card-header">
                  <span className={`source-badge badge-${item.source_type}`}>
                    {iconMap[item.source_type]}
                    <span>{item.source_type.toUpperCase()}</span>
                  </span>
                  <span className="card-time">{relativeTime}</span>
                </div>

                <h4 className="card-title">{item.title || 'Untitled Save'}</h4>
                
                <p className="card-excerpt">
                  <FormattedText text={item.summary || 'No summary available.'} excerptMode={true} />
                </p>

                <div className="card-footer">
                  <div className="card-tags">
                    {item.tags.map(t => (
                      <span key={t} className="tag-pill">{t}</span>
                    ))}
                  </div>

                  <div className="card-menu-container" ref={activeMenuId === item.id ? menuRef : null}>
                    <button 
                      onClick={(e) => handleToggleMenu(e, item.id)}
                      className="card-menu-trigger"
                      aria-label="Item Actions"
                    >
                      <DotsThree size={20} weight="bold" />
                    </button>

                    {activeMenuId === item.id && (
                      <div className="card-dropdown glass-panel">
                        <button 
                          onClick={(e) => { e.stopPropagation(); onViewInGraph(item); }}
                          className="dropdown-item"
                        >
                          <Eye size={14} /> View in Graph
                        </button>
                        <button 
                          onClick={(e) => handleDeleteItem(e, item.id)}
                          className="dropdown-item delete-action"
                        >
                          <Trash size={14} /> Delete
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <EmptyState variant={searchQuery ? "search" : "feed"} query={searchQuery} />
      )}

      {loading && !isFirstLoad && (
        <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--color-text-muted)' }}>
          Loading items...
        </div>
      )}
    </div>
  );
}
