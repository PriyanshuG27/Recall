import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import AudioEngine from '../utils/AudioEngine';

/* ============================================================
   Sidebar — The Observatory's 48px vertical navigation rail.
   ============================================================ */

const ROOMS = [
  {
    id: 'archive',
    path: '/archive',
    label: 'Archive',
    subtitle: 'Your signals in time',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <line x1="3" y1="6" x2="21" y2="6" />
        <line x1="3" y1="12" x2="21" y2="12" />
        <line x1="3" y1="18" x2="21" y2="18" />
      </svg>
    ),
  },
  {
    id: 'map',
    path: '/map',
    label: 'Map',
    subtitle: 'Your knowledge, connected',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="6"  cy="6"  r="2" />
        <circle cx="18" cy="6"  r="2" />
        <circle cx="12" cy="18" r="2" />
        <circle cx="6"  cy="18" r="2" />
        <line x1="8"  y1="6"  x2="16" y2="6"  />
        <line x1="7"  y1="7"  x2="11" y2="17" />
        <line x1="17" y1="7"  x2="13" y2="17" />
        <line x1="8"  y1="18" x2="10" y2="18" />
      </svg>
    ),
  },
  {
    id: 'hearth',
    path: '/hearth',
    label: 'Hearth',
    subtitle: 'Build together',
    hidden: false,
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 2C6 6 4 10 4 14a8 8 0 0 0 16 0c0-4-2-8-8-12z" />
        <path d="M12 14c0-3 2-5 2-5s-4 2-4 5" />
      </svg>
    ),
  },
  {
    id: 'drill',
    path: '/drill',
    label: 'Drill',
    subtitle: 'Recall as a ritual',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
      </svg>
    ),
  },
  {
    id: 'profile',
    path: '/profile',
    label: 'Profile',
    subtitle: 'Your cognitive identity',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
        <circle cx="12" cy="7" r="4" />
      </svg>
    ),
  },
];

export default function Sidebar({ currentRoom, onNavigate, onMuteChange, onSearchOpen, onSettingsOpen, dueCount = 0, streak = 0 }) {
  const { user, logout } = useAuth();
  const [muted, setMuted] = useState(AudioEngine.isMuted());
  const [showDropdown, setShowDropdown] = useState(false);
  const [dropletY, setDropletY] = useState(-100);
  const [iconOffsets, setIconOffsets] = useState({});
  const railRef = useRef(null);
  const iconRefs = useRef({});
  const dropdownRef = useRef(null);

  /* Sync mute status from other sources (e.g. Settings Panel) */
  useEffect(() => {
    const handleMuteToggleEvent = (e) => {
      setMuted(e.detail);
    };
    window.addEventListener('recall-mute-toggle', handleMuteToggleEvent);
    return () => window.removeEventListener('recall-mute-toggle', handleMuteToggleEvent);
  }, []);

  /* ── Navigate to a room ─────────────────────────────────────────────────── */
  const navigate = useCallback((path, roomId) => {
    AudioEngine.playClick();
    if (onNavigate) onNavigate(roomId);
  }, [onNavigate]);



  /* ── Magnetic cursor effect + droplet ──────────────────────────────────── */
  useEffect(() => {
    // Touch detection: bypass hover droplet logic if touch device
    const isTouch = window.matchMedia('(hover: none)').matches;
    if (isTouch) return;

    const rail = railRef.current;
    if (!rail) return;

    const handleMouseMove = (e) => {
      const rect = rail.getBoundingClientRect();
      // Only activate when cursor is within 80px of the rail
      const distFromRail = Math.abs(e.clientX - (rect.left + rect.width / 2));
      if (distFromRail > 80) {
        setDropletY(-100);
        setIconOffsets({});
        return;
      }

      // Update droplet position (clamped to rail bounds)
      const railY = e.clientY - rect.top;
      const clampedY = Math.max(0, Math.min(rect.height, railY));
      setDropletY(clampedY);

      // Magnetic pull on icons
      const newOffsets = {};
      ROOMS.forEach((room) => {
        const iconEl = iconRefs.current[room.id];
        if (!iconEl) return;
        const iconRect = iconEl.getBoundingClientRect();
        const iconCenterY = iconRect.top + iconRect.height / 2;
        const dist = Math.abs(e.clientY - iconCenterY);
        if (dist < 40) {
          const pull = (1 - dist / 40) * 8; // max 8px pull
          newOffsets[room.id] = pull;
        } else {
          newOffsets[room.id] = 0;
        }
      });
      setIconOffsets(newOffsets);
    };

    const handleMouseLeave = () => {
      setDropletY(-100);
      setIconOffsets({});
    };

    window.addEventListener('mousemove', handleMouseMove);
    rail.addEventListener('mouseleave', handleMouseLeave);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      rail.removeEventListener('mouseleave', handleMouseLeave);
    };
  }, []);

  /* ── Close dropdown on outside click ───────────────────────────────────── */
  useEffect(() => {
    const handleClick = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setShowDropdown(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  const handleMuteToggle = () => {
    const nextMuted = !muted;
    setMuted(nextMuted);
    AudioEngine.setMuted(nextMuted);
    if (onMuteChange) onMuteChange(nextMuted);
  };

  const initials = user?.first_name
    ? user.first_name[0].toUpperCase()
    : user?.username?.[0]?.toUpperCase() ?? '?';

  return (
    <aside className="sidebar-rail" ref={railRef} aria-label="Observatory navigation">
      {/* ── Liquid amber droplet ── */}
      <div
        className="sidebar-droplet"
        style={{ top: dropletY > 0 ? dropletY : -100 }}
        aria-hidden="true"
      />

      {/* ── Monogram ── */}
      <div className="sidebar-monogram" aria-label="Recall">
        R
      </div>

      {/* ── Room navigation icons ── */}
      <nav className="sidebar-nav" role="navigation">
        {ROOMS.filter((r) => !r.hidden).map((room) => {
          const isActive = currentRoom === room.id;
          const pull = iconOffsets[room.id] || 0;
          return (
            <div key={room.id} className="sidebar-icon-wrapper">
              <button
                ref={(el) => { iconRefs.current[room.id] = el; }}
                className={`sidebar-icon-btn ${isActive ? 'active' : ''}`}
                style={{ transform: `translateX(${pull}px)` }}
                onClick={() => navigate(room.path, room.id)}
                aria-label={room.label}
                aria-current={isActive ? 'page' : undefined}
                id={`sidebar-${room.id}`}
              >
                {room.icon}
                {room.id === 'drill' && dueCount > 0 && (
                  <span className={`drill-badge ${dueCount >= 5 ? 'pulse' : ''}`}>
                    {dueCount}
                  </span>
                )}
                {/* Border-beam active indicator */}
                {isActive && <span className="border-beam" aria-hidden="true" />}
              </button>
              {/* Slide-right tooltip */}
              <div className="sidebar-tooltip" role="tooltip" aria-hidden="true">
                <span className="sidebar-tooltip-label">{room.label}</span>
                <span className="sidebar-tooltip-sub">{room.subtitle}</span>
              </div>
            </div>
          );
        })}
      </nav>

      {/* ── Bottom controls ── */}
      <div className="sidebar-bottom">
        {/* Search shortcut */}
        <div className="sidebar-icon-wrapper">
          <button
            className="sidebar-icon-btn"
            onClick={() => { AudioEngine.playClick(); onSearchOpen(); }}
            aria-label="Search (Cmd+K)"
            id="sidebar-search"
            title="Search"
          >
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
          </button>
          <div className="sidebar-tooltip" role="tooltip" aria-hidden="true">
            <span className="sidebar-tooltip-label">Search</span>
            <span className="sidebar-tooltip-sub">⌘K</span>
          </div>
        </div>

        {/* Mute toggle */}
        <div className="sidebar-icon-wrapper">
          <button
            className={`sidebar-icon-btn sidebar-mute ${muted ? 'muted' : 'unmuted'}`}
            onClick={handleMuteToggle}
            aria-label={muted ? 'Unmute audio' : 'Mute audio'}
            id="sidebar-mute"
          >
            {muted ? (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
                <line x1="22" y1="9" x2="16" y2="15" />
                <line x1="16" y1="9" x2="22" y2="15" />
              </svg>
            ) : (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
                <path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
                <path d="M19.07 4.93a10 10 0 0 1 0 14.14" />
              </svg>
            )}
          </button>
          <div className="sidebar-tooltip" role="tooltip" aria-hidden="true">
            <span className="sidebar-tooltip-label">{muted ? 'Unmute audio' : 'Mute audio'}</span>
          </div>
        </div>

        {/* Avatar / profile dropdown */}
        <div className="sidebar-icon-wrapper" ref={dropdownRef}>
          <button
            className="sidebar-icon-btn sidebar-avatar"
            onClick={() => { AudioEngine.playClick(); setShowDropdown(!showDropdown); }}
            aria-label="Profile menu"
            aria-expanded={showDropdown}
            id="sidebar-avatar"
          >
            <span className="sidebar-avatar-circle">{initials}</span>
          </button>

          <div className="sidebar-tooltip" role="tooltip" aria-hidden="true">
            <span className="sidebar-tooltip-label">
              {user?.first_name || user?.username || 'Profile'}
            </span>
          </div>

          {/* Dropdown */}
          {showDropdown && (
            <div className="sidebar-dropdown" role="menu">
              <div className="sidebar-dropdown-header">
                <span>{user?.first_name || user?.username || 'Signal User'}</span>
                <span className="sidebar-dropdown-sub">
                  {user?.telegram_id ? `@${user.username}` : ''}
                </span>
              </div>
              <button
                className="sidebar-dropdown-item"
                role="menuitem"
                onClick={() => { AudioEngine.playClick(); setShowDropdown(false); onSettingsOpen(); }}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="12" cy="12" r="3"/><path d="M12 2v2M12 20v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M2 12h2M20 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>
                Settings
              </button>
              <button
                className="sidebar-dropdown-item logout"
                role="menuitem"
                onClick={() => { setShowDropdown(false); logout(); }}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
                Sign out
              </button>
            </div>
          )}
        {streak > 0 && (
          <div className="sidebar-streak" title="Daily Review Streak">
            🔥{streak}d
          </div>
        )}
      </div>
      </div>
    </aside>
  );
}
