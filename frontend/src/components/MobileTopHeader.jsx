import React, { useState, useEffect, useRef } from 'react';
import AudioEngine from '../utils/AudioEngine';
import StreakPanel from './StreakPanel';
import { MagnifyingGlass } from '@phosphor-icons/react';

export default function MobileTopHeader({ currentRoom, onNavigate, onSearchOpen, streak, user, logout }) {
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [streakPanelOpen, setStreakPanelOpen] = useState(false);
  const [muted, setMuted] = useState(AudioEngine.isMuted());
  const [userProfile, setUserProfile] = useState(null);

  const dropdownRef = useRef(null);

  // Sync mute state with AudioEngine events
  useEffect(() => {
    const handleMuteToggle = (e) => {
      setMuted(e.detail);
    };
    window.addEventListener('atrium-mute-toggle', handleMuteToggle);
    return () => window.removeEventListener('atrium-mute-toggle', handleMuteToggle);
  }, []);

  const handleMuteClick = () => {
    const next = !muted;
    setMuted(next);
    AudioEngine.setMuted(next);
  };

  // Fetch detailed profile info only when streak panel is opened
  useEffect(() => {
    if (!streakPanelOpen || !user) return;
    const fetchProfile = async () => {
      try {
        const res = await fetch('/api/me');
        if (res.ok) {
          const data = await res.json();
          setUserProfile(data);
        }
      } catch (err) {
        console.error('Failed to fetch profile settings in MobileTopHeader:', err);
      }
    };
    fetchProfile();
  }, [streakPanelOpen, user]);

  // Click outside & Escape listeners to close dropdown & streak panel
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (dropdownOpen && dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setDropdownOpen(false);
      }
    };
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        setDropdownOpen(false);
        setStreakPanelOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('touchstart', handleClickOutside, { passive: true });
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('touchstart', handleClickOutside);
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [dropdownOpen]);

  // Lock body scrolling when the streak panel is open
  useEffect(() => {
    if (streakPanelOpen) {
      document.body.classList.add('body-lock-scroll');
    } else {
      document.body.classList.remove('body-lock-scroll');
    }
    return () => {
      document.body.classList.remove('body-lock-scroll');
    };
  }, [streakPanelOpen]);

  const avatarLetter = user?.chat_id 
    ? (user.chat_id.substring(0, 1).toUpperCase() === 'R' ? 'A' : user.chat_id.substring(0, 1).toUpperCase()) 
    : (user?.username 
        ? (user.username[0].toUpperCase() === 'R' ? 'A' : user.username[0].toUpperCase()) 
        : 'A');

  const navigateTo = (roomId) => {
    setDropdownOpen(false);
    onNavigate(roomId);
  };

  return (
    <header className="mobile-top-header" aria-label="Mobile top navigation" role="banner">
      <button 
        type="button"
        className="mobile-header-logo" 
        onClick={() => navigateTo('archive')}
        style={{
          background: 'none',
          border: 'none',
          padding: 0,
          cursor: 'pointer',
          textAlign: 'left',
          touchAction: 'manipulation',
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          color: 'var(--text-signal)',
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
      </button>

      <div className="mobile-header-right">
        {/* Search trigger — onClick only, touch-action:manipulation removes 300ms delay */}
        <button 
          type="button"
          className="mobile-header-btn" 
          onClick={() => { AudioEngine.playClick(); onSearchOpen(); }}
          aria-label="Search"
          style={{ minWidth: 44, minHeight: 44, touchAction: 'manipulation' }}
        >
          <MagnifyingGlass size={18} />
        </button>

        {/* Mute toggle */}
        <button 
          type="button"
          className="mobile-header-btn" 
          onClick={handleMuteClick}
          aria-label={muted ? 'Unmute audio' : 'Mute audio'}
          style={{ minWidth: 44, minHeight: 44, touchAction: 'manipulation' }}
        >
          {muted ? (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
              <line x1="22" y1="9" x2="16" y2="15" />
              <line x1="16" y1="9" x2="22" y2="15" />
            </svg>
          ) : (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
              <path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
            </svg>
          )}
        </button>

        {/* Streak badge */}
        {streak > 0 && (
          <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
            <button 
              type="button"
              className="mobile-header-btn mobile-streak-badge streak-badge-btn"
              onClick={() => setStreakPanelOpen(!streakPanelOpen)}
              aria-label={`Streak: ${streak} days`}
              style={{ minWidth: 44, minHeight: 44, touchAction: 'manipulation' }}
            >
              🔥{streak}
            </button>
            <StreakPanel 
              isOpen={streakPanelOpen}
              onClose={() => setStreakPanelOpen(false)}
              streakCount={userProfile?.streak_count || streak}
              lastActivityDate={userProfile?.last_activity_date}
              last7DaysActivity={userProfile?.last_7_days_activity}
            />
          </div>
        )}

        {/* User Avatar dropdown */}
        <div className="mobile-profile-container" ref={dropdownRef}>
          <button 
            type="button"
            className="mobile-avatar-btn" 
            onClick={() => { AudioEngine.playClick(); setDropdownOpen(!dropdownOpen); }}
            aria-label="Profile Menu"
            aria-expanded={dropdownOpen}
            style={{ minWidth: 44, minHeight: 44, display: 'flex', alignItems: 'center', justifyContent: 'center', touchAction: 'manipulation' }}
          >
            <div className="avatar-circle">
              {avatarLetter}
            </div>
          </button>

          {dropdownOpen && (
            <div className="dropdown-menu glass-panel mobile-dropdown" role="menu">
              <div className="dropdown-header">
                User {user.chat_id}
              </div>
              <button 
                type="button"
                className={`dropdown-item ${currentRoom === 'profile' ? 'active' : ''}`}
                onClick={() => { AudioEngine.playClick(); navigateTo('profile'); }}
                role="menuitem"
                style={{ minHeight: 44, touchAction: 'manipulation' }}
              >
                Profile
              </button>

              <button 
                type="button"
                className={`dropdown-item ${currentRoom === 'settings' ? 'active' : ''}`}
                onClick={() => { AudioEngine.playClick(); navigateTo('settings'); }}
                role="menuitem"
                style={{ minHeight: 44, touchAction: 'manipulation' }}
              >
                Settings
              </button>
              <button 
                type="button"
                className="dropdown-item logout-item"
                onClick={() => { setDropdownOpen(false); logout(); }}
                role="menuitem"
                style={{ minHeight: 44, touchAction: 'manipulation' }}
              >
                Logout
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
