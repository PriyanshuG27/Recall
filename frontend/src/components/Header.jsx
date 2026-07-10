import React, { useState, useRef, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { MagnifyingGlass, GoogleLogo, CloudX, CloudArrowUp, SignOut, CaretDown, CaretUp, ShareNetwork, List, Gear, Bell, BookOpen } from '@phosphor-icons/react';
import ConnectionStatus from './ConnectionStatus';
import ConnectDriveCard from './ConnectDriveCard';
import { useToast } from './Toast';
import axios from '../api/client';
import StreakBadge from './StreakBadge';
import StreakPanel from './StreakPanel';

export default function Header({ onSearch, dueQuizCount, viewMode = 'graph', onViewModeChange, searchInputRef: externalSearchInputRef, searchQuery = '', onSettingsClick, onStatsClick }) {
  const { user, logout, checkAuth } = useAuth();
  const { addToast } = useToast();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [searchVal, setSearchVal] = useState('');
  const [isSearchExpanded, setIsSearchExpanded] = useState(false);
  const dropdownRef = useRef(null);
  const internalSearchInputRef = useRef(null);
  const searchInputRef = externalSearchInputRef || internalSearchInputRef;
  const isFirstRender = useRef(true);
  const [stats, setStats] = useState(null);
  const [profileData, setProfileData] = useState(null);
  const [streakPanelOpen, setStreakPanelOpen] = useState(false);

  useEffect(() => {
    if (!user) return;

    const fetchStats = async () => {
      try {
        const res = await fetch('/api/quizzes/stats');
        if (res.ok) {
          const data = await res.json();
          setStats(data);
        }
      } catch (err) {
        console.error('Failed to fetch quiz stats in header:', err);
      }
    };

    const fetchProfile = async () => {
      try {
        const res = await fetch('/api/me');
        if (res.ok) {
          const data = await res.json();
          setProfileData(data);
        }
      } catch (err) {
        console.error('Failed to fetch profile settings in header:', err);
      }
    };

    fetchStats();
    fetchProfile();

    const handleUpdate = () => {
      fetchStats();
      fetchProfile();
    };

    window.addEventListener('quiz-answered', handleUpdate);
    window.addEventListener('online-refetch', handleUpdate);
    window.addEventListener('items-updated', handleUpdate);
    return () => {
      window.removeEventListener('quiz-answered', handleUpdate);
      window.removeEventListener('online-refetch', handleUpdate);
      window.removeEventListener('items-updated', handleUpdate);
    };
  }, [user]);


  // Listen for message events (e.g. from OAuth popup)
  useEffect(() => {
    const handleMessage = (event) => {
      if (event.data === 'google_connected') {
        checkAuth();
      }
    };
    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [checkAuth]);

  // Synchronize with external search query clearing
  const [prevSearchQuery, setPrevSearchQuery] = useState(searchQuery);
  if (searchQuery !== prevSearchQuery) {
    setPrevSearchQuery(searchQuery);
    if (searchQuery === '') {
      setSearchVal('');
      setIsSearchExpanded(false);
    }
  }

  // Close dropdown on clicking outside

  // Close dropdown on clicking outside
  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setDropdownOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('touchstart', handleClickOutside, { passive: true });
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('touchstart', handleClickOutside);
    };
  }, []);

  // Debounced search logic (300 ms exactly)
  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }
    const handler = setTimeout(() => {
      onSearch(searchVal);
    }, 300);
    return () => clearTimeout(handler);
  }, [searchVal, onSearch]);

  const handleSearchChange = (e) => {
    setSearchVal(e.target.value);
  };

  const handleClearSearch = () => {
    setSearchVal('');
    onSearch('');
    setIsSearchExpanded(false);
  };

  // Auto-focus search input when expanded
  useEffect(() => {
    if (isSearchExpanded && searchInputRef.current) {
      searchInputRef.current.focus();
    }
  }, [isSearchExpanded, searchInputRef]);

  const handleSearchContainerClick = () => {
    if (!isSearchExpanded) {
      setIsSearchExpanded(true);
    }
  };

  const handleSearchBlur = () => {
    if (!searchVal.trim()) {
      setIsSearchExpanded(false);
    }
  };

  const handleConnectDrive = () => {
    const width = 500;
    const height = 600;
    const left = window.screen.width / 2 - width / 2;
    const top = window.screen.height / 2 - height / 2;
    window.open(
      '/auth/google?popup=true',
      'Connect Google Drive',
      `width=${width},height=${height},top=${top},left=${left},scrollbars=yes`
    );
    setDropdownOpen(false);
  };

  const handleDisconnectDrive = async () => {
    try {
      const res = await axios.delete('/api/drive');
      if (res.status === 204) {
        addToast('Google Drive disconnected.', 'success');
        checkAuth();
      } else {
        addToast('Failed to disconnect Google Drive.', 'error');
      }
    } catch (err) {
      console.error('Disconnect Drive failed:', err);
      addToast('Error disconnecting Google Drive.', 'error');
    } finally {
      setDropdownOpen(false);
    }
  };

  const handleSyncDrive = async () => {
    try {
      const res = await axios.post('/api/drive/sync');
      if (res.status === 202 || res.status === 200) {
        addToast('Sync triggered successfully!', 'success');
      } else {
        addToast('Failed to trigger sync.', 'error');
      }
    } catch (err) {
      console.error('Sync failed:', err);
      addToast('Failed to trigger sync.', 'error');
    } finally {
      setDropdownOpen(false);
    }
  };

  // Derive initial letter for avatar
  const avatarLetter = user?.chat_id ? user.chat_id.substring(0, 1) : 'U';

  return (
    <header className="app-header">
      <div className="header-left">
        {/* Logo — small watermark, ~40% opacity, clicking resets pan/zoom */}
        <a
          href="/"
          className="header-logo"
          style={{
            opacity: 0.85,
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            textDecoration: 'none',
            color: 'var(--text-signal)',
            pointerEvents: 'auto',
            fontFamily: "'DM Serif Display', Georgia, serif",
            fontSize: '1.15rem',
            letterSpacing: '-0.01em',
          }}
        >
          <svg viewBox="0 0 100 100" style={{ width: '18px', height: '18px', fill: 'var(--accent-gold)' }} aria-hidden="true">
            <path d="M 25 85 V 50 A 25 25 0 0 1 75 50 V 85 H 63 V 50 A 13 13 0 0 0 37 50 V 85 Z" />
            <circle cx="50" cy="48" r="3.5" />
            <circle cx="43" cy="62" r="2.2" />
            <circle cx="57" cy="67" r="2.2" />
            <circle cx="47" cy="76" r="1.3" />
          </svg>
          Atrium
        </a>

        {user && (
          <div 
            onClick={handleSearchContainerClick}
            className={`search-bar-container ${isSearchExpanded ? 'expanded' : ''}`}
            data-testid="search-container"
          >
            <span 
              className="search-icon" 
              data-testid="search-icon-trigger"
              role="button"
              tabIndex={0}
              aria-label="Expand search"
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  handleSearchContainerClick();
                }
              }}
            >
              <MagnifyingGlass size={14} aria-hidden="true" />
            </span>
            <input
              ref={searchInputRef}
              type="text"
              placeholder="Search your brain..."
              value={searchVal}
              onChange={handleSearchChange}
              onFocus={() => setIsSearchExpanded(true)}
              onBlur={handleSearchBlur}
              className="search-input"
            />
            {searchVal && (
              <button onClick={handleClearSearch} className="clear-search-btn">
                Clear
              </button>
            )}
          </div>
        )}
      </div>

      <div className="header-right">
        {user && (
          <>
            {/* View toggle — icon-only, minimal */}
            <div className="view-toggle">
              <button 
                className={`toggle-btn ${viewMode === 'graph' ? 'active' : ''}`}
                onClick={() => onViewModeChange && onViewModeChange('graph')}
                aria-label="Switch to Graph View"
                title="Graph"
              >
                <ShareNetwork size={14} aria-hidden="true" />
              </button>
              <button 
                className={`toggle-btn ${viewMode === 'feed' ? 'active' : ''}`}
                onClick={() => onViewModeChange && onViewModeChange('feed')}
                aria-label="Switch to Feed View"
                title="Feed"
              >
                <List size={14} aria-hidden="true" />
              </button>
              <button 
                className={`toggle-btn ${viewMode === 'quiz' ? 'active' : ''}`}
                onClick={() => onViewModeChange && onViewModeChange('quiz')}
                aria-label="Switch to Quiz View"
                title="Quiz"
              >
                <BookOpen size={14} aria-hidden="true" />
              </button>
            </div>

            {/* Stats card — compact numbers only */}
            {stats && (
              <div 
                className="quiz-stats-card" 
                onClick={onStatsClick}
                title="View detailed quiz performance history"
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onStatsClick && onStatsClick();
                  }
                }}
              >
                <span className="stats-compact">
                  <span style={{ color: 'var(--text-tertiary)' }}>Due:</span>
                  <span className="stat-val">{stats.due_today}</span>
                  <span style={{ color: 'rgba(240,237,232,0.12)' }}>|</span>
                  <span style={{ color: 'var(--text-tertiary)' }}>Avg:</span>
                  <span className="stat-val">{stats.avg_ease_factor.toFixed(1)}</span>
                </span>
              </div>
            )}

            {profileData && (
              <div style={{ position: 'relative' }}>
                <StreakBadge 
                  streakCount={profileData.streak_count} 
                  onClick={() => setStreakPanelOpen(!streakPanelOpen)} 
                />
                <StreakPanel 
                  isOpen={streakPanelOpen}
                  onClose={() => setStreakPanelOpen(false)}
                  streakCount={profileData.streak_count}
                  lastActivityDate={profileData.last_activity_date}
                  last7DaysActivity={profileData.last_7_days_activity}
                />
              </div>
            )}

            <ConnectionStatus />

            {/* Profile area — avatar only, no username text */}
            <div className="profile-menu-container" ref={dropdownRef}>
              <button
                className="profile-trigger"
                onClick={() => setDropdownOpen(!dropdownOpen)}
                aria-expanded={dropdownOpen}
                aria-haspopup="true"
                aria-label="Profile menu"
                style={{ padding: '0.2rem', borderRadius: '50%', border: '1px solid var(--border-subtle)' }}
              >
                <div className="avatar-circle">
                  {avatarLetter}
                </div>
                {/* Hidden span for tests — keeps user identifier accessible without showing it */}
                <span className="sr-only">User {user.chat_id}</span>
              </button>

              {dropdownOpen && (
                <div className="dropdown-menu glass-panel" role="menu" style={{ width: '280px' }}>
                  {/* User identity — shown inside dropdown */}
                  <div style={{
                    padding: '0.625rem 0.875rem',
                    borderBottom: '1px solid var(--border-subtle)',
                    marginBottom: '0.25rem',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.6rem'
                  }}>
                    <div className="avatar-circle" style={{ width: '22px', height: '22px', fontSize: '0.625rem' }}>
                      {avatarLetter}
                    </div>
                    <span style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
                      User {user.chat_id}
                    </span>
                  </div>

                  <div className="dropdown-header" role="presentation">Drive Integration</div>
                  <div style={{ padding: '0.25rem 0.5rem' }}>
                    <ConnectDriveCard />
                  </div>

                  <div
                    className="dropdown-header"
                    role="presentation"
                    style={{
                      borderTop: '1px solid var(--border-glass)',
                      marginTop: '0.25rem',
                    }}
                  >
                    Account
                  </div>
                  <button
                    className="dropdown-item"
                    onClick={() => {
                      onViewModeChange && onViewModeChange('reminders');
                      setDropdownOpen(false);
                    }}
                    role="menuitem"
                  >
                    <Bell size={16} aria-hidden="true" /> Reminders
                  </button>
                  <button
                    className="dropdown-item"
                    onClick={() => {
                      onSettingsClick && onSettingsClick();
                      setDropdownOpen(false);
                    }}
                    role="menuitem"
                  >
                    <Gear size={16} aria-hidden="true" /> Settings
                  </button>
                  <button
                    className="dropdown-item logout-item"
                    onClick={logout}
                    role="menuitem"
                    style={{ fontWeight: '600' }}
                  >
                    <SignOut size={16} aria-hidden="true" /> Logout
                  </button>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </header>
  );
}
