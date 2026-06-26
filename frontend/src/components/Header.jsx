import React, { useState, useRef, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { MagnifyingGlass, GoogleLogo, CloudX, SignOut, CaretDown, CaretUp, ShareNetwork, List, Gear } from '@phosphor-icons/react';

export default function Header({ onSearch, dueQuizCount, viewMode = 'graph', onViewModeChange, searchInputRef: externalSearchInputRef, searchQuery = '', onSettingsClick }) {
  const { user, logout } = useAuth();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [searchVal, setSearchVal] = useState('');
  const [isSearchExpanded, setIsSearchExpanded] = useState(false);
  const dropdownRef = useRef(null);
  const internalSearchInputRef = useRef(null);
  const searchInputRef = externalSearchInputRef || internalSearchInputRef;
  const isFirstRender = useRef(true);

  // Synchronize with external search query clearing
  useEffect(() => {
    if (searchQuery === '') {
      setSearchVal('');
      setIsSearchExpanded(false);
    }
  }, [searchQuery]);

  // Close dropdown on clicking outside

  // Close dropdown on clicking outside
  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setDropdownOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('touchstart', handleClickOutside);
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
  }, [isSearchExpanded]);

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
      '/auth/google',
      'Connect Google Drive',
      `width=${width},height=${height},top=${top},left=${left},scrollbars=yes`
    );
    setDropdownOpen(false);
  };

  const handleDisconnectDrive = async () => {
    try {
      const res = await fetch('/api/drive', { method: 'DELETE' });
      if (res.status === 204) {
        alert('Google Drive disconnected.');
      } else {
        alert('Failed to disconnect Google Drive.');
      }
    } catch (err) {
      console.error('Disconnect Drive failed:', err);
      alert('Error disconnecting Google Drive.');
    } finally {
      setDropdownOpen(false);
    }
  };

  return (
    <header className="app-header">
      <div className="header-left">
        <a href="/" className="header-logo gradient-text">
          Recall
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
              <MagnifyingGlass size={16} aria-hidden="true" />
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
            <div className="view-toggle">
              <button 
                className={`toggle-btn ${viewMode === 'graph' ? 'active' : ''}`}
                onClick={() => onViewModeChange && onViewModeChange('graph')}
                aria-label="Switch to Graph View"
              >
                <ShareNetwork size={16} aria-hidden="true" /> Graph
              </button>
              <button 
                className={`toggle-btn ${viewMode === 'feed' ? 'active' : ''}`}
                onClick={() => onViewModeChange && onViewModeChange('feed')}
                aria-label="Switch to Feed View"
              >
                <List size={16} aria-hidden="true" /> Feed
              </button>
            </div>

            <button className="quiz-badge-btn">
              <span>Quiz</span>
              {dueQuizCount > 0 && (
                <span className="quiz-badge-count">{dueQuizCount}</span>
              )}
            </button>

            <div className="profile-menu-container" ref={dropdownRef}>
              <button
                className="profile-trigger"
                onClick={() => setDropdownOpen(!dropdownOpen)}
                aria-expanded={dropdownOpen}
                aria-haspopup="true"
                aria-label="Profile menu"
              >
                <div className="avatar-circle">
                  {user.chat_id ? user.chat_id.substring(0, 1) : 'U'}
                </div>
                <span>User {user.chat_id}</span>
                <span style={{ display: 'flex', alignItems: 'center', marginLeft: '0.25rem' }}>
                  {dropdownOpen ? <CaretUp size={12} aria-hidden="true" /> : <CaretDown size={12} aria-hidden="true" />}
                </span>
              </button>

              {dropdownOpen && (
                <div className="dropdown-menu glass-panel" role="menu">
                  <div className="dropdown-header" role="presentation">Drive Integration</div>
                  <button className="dropdown-item" onClick={handleConnectDrive} role="menuitem">
                    <GoogleLogo size={16} aria-hidden="true" /> Connect Google Drive
                  </button>
                  <button className="dropdown-item" onClick={handleDisconnectDrive} role="menuitem">
                    <CloudX size={16} aria-hidden="true" /> Disconnect Drive
                  </button>

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
