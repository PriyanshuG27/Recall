import React, { useEffect, useState, useRef, lazy, Suspense, useCallback } from 'react';
import { useAuth } from './context/AuthContext';
import Login from './pages/Login';
import { useToast } from './components/Toast';
import { setToastHandler, setUnauthorizedHandler } from './api/client';
import CustomCursor from './components/CustomCursor';
import Sidebar from './components/Sidebar';
import RoomTransition from './components/RoomTransition';
import SearchOverlay from './components/SearchOverlay';
import { PerfProvider } from './context/PerfContext';
import AudioEngine from './utils/AudioEngine';
import SplashScreen from './components/SplashScreen';
import ChatDrawer from './components/ChatDrawer';

/* ── Lazy-load rooms ──────────────────────────────────────── */
const Archive = lazy(() => import('./pages/Archive'));
const Map     = lazy(() => import('./pages/Map'));
const Drill   = lazy(() => import('./pages/Drill'));
const Settings = lazy(() => import('./pages/Settings'));
const Profile  = lazy(() => import('./pages/Profile'));
const Bridges  = lazy(() => import('./pages/Bridges'));
const BranchingPOC = lazy(() => import('./pages/BranchingPOC'));

/* ── Map pathname → room id ──────────────────────────────── */
function pathToRoom(pathname) {
  if (pathname.startsWith('/archive')) return 'archive';
  if (pathname.startsWith('/map'))     return 'map';
  if (pathname.startsWith('/nebula'))  return 'map'; // legacy redirect
  if (pathname.startsWith('/drill'))   return 'drill';
  if (pathname.startsWith('/settings')) return 'settings';
  if (pathname.startsWith('/profile')) return 'profile';
  if (pathname.startsWith('/bridges')) return 'bridges';
  if (pathname.startsWith('/poc/branching')) return 'poc-branching';
  return 'archive';
}

/* ── Loading fallback ─────────────────────────────────────── */
function RoomLoader() {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      height: '100%', color: 'var(--text-muted)',
      fontFamily: 'var(--font-mono)', fontSize: 12, letterSpacing: '0.08em',
    }}>
      <span>LOADING SIGNAL…</span>
    </div>
  );
}

/* ── Per-room error boundary ──────────────────────────────── */
class RoomErrorBoundary extends React.Component {
  constructor(props) { super(props); this.state = { error: null }; }
  static getDerivedStateFromError(e) { return { error: e }; }
  render() {
    if (this.state.error) {
      return (
        <div style={{
          display: 'flex', flexDirection: 'column', alignItems: 'center',
          justifyContent: 'center', height: '100%', gap: '0.75rem',
        }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: '#e07070', letterSpacing: '0.1em' }}>
            ROOM ERROR — {this.state.error.message}
          </div>
          <button
            onClick={() => this.setState({ error: null })}
            style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--accent-gold)', background: 'transparent', border: '1px solid rgba(207,163,101,0.3)', borderRadius: 3, padding: '4px 12px', cursor: 'pointer' }}
          >
            Retry
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

function App() {
  const { user, loading, logout } = useAuth();
  const { addToast, removeToast }  = useToast();
  const [assistantOpen, setAssistantOpen] = useState(false);

  /* ── Keyboard shortcut Ctrl+Shift+A for Assistant ──────── */
  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === 'a') {
        e.preventDefault();
        setAssistantOpen(prev => !prev);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  /* ── Axios callbacks ───────────────────────────────────── */
  useEffect(() => {
    setToastHandler(addToast);
    setUnauthorizedHandler(() => logout());
    return () => { setToastHandler(null); setUnauthorizedHandler(null); };
  }, [addToast, logout]);

  /* ── PWA install prompt ────────────────────────────────── */
  useEffect(() => {
    const isActive = sessionStorage.getItem('recall_session_active');
    if (!isActive) {
      sessionStorage.setItem('recall_session_active', 'true');
      const v = parseInt(localStorage.getItem('recall_visits') || '0', 10);
      localStorage.setItem('recall_visits', (v + 1).toString());
    }

    let deferred = null;
    let toastId  = null;

    const onPrompt = (e) => {
      e.preventDefault();
      deferred = e;
      const visits = parseInt(localStorage.getItem('recall_visits') || '0', 10);
      if (visits >= 3) {
        const doInstall = async () => {
          if (!deferred) return;
          deferred.prompt();
          const { outcome } = await deferred.userChoice;
          deferred = null;
          if (toastId) removeToast(toastId);
        };
        toastId = addToast(
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', justifyContent: 'space-between', width: '100%' }}>
            <span>Add Recall to your homescreen?</span>
            <button onClick={doInstall} className="btn" style={{ padding: '0.25rem 0.75rem', fontSize: '0.75rem', minHeight: 28, background: 'var(--accent-gold)', color: '#000', border: 'none', borderRadius: 4, cursor: 'pointer', fontWeight: 700 }}>
              Install
            </button>
          </div>,
          'info', { persistent: true }
        );
      }
    };

    window.addEventListener('beforeinstallprompt', onPrompt);
    return () => {
      window.removeEventListener('beforeinstallprompt', onPrompt);
      if (toastId) removeToast(toastId);
    };
  }, [addToast, removeToast]);

  /* ── Online / Offline ──────────────────────────────────── */
  useEffect(() => {
    let offlineId = null;
    const onOffline = () => { if (!offlineId) offlineId = addToast("You're offline", 'error', { persistent: true }); };
    const onOnline  = () => { if (offlineId) { removeToast(offlineId); offlineId = null; } window.dispatchEvent(new Event('online-refetch')); };
    window.addEventListener('offline', onOffline);
    window.addEventListener('online',  onOnline);
    if (!navigator.onLine) onOffline();
    return () => {
      window.removeEventListener('offline', onOffline);
      window.removeEventListener('online',  onOnline);
      if (offlineId) removeToast(offlineId);
    };
  }, [addToast, removeToast]);

  /* ── Stats & due count ─────────────────────────────────── */
  const [dueCount, setDueCount] = useState(0);
  const [streak, setStreak] = useState(0);
  const [totalSaves, setTotalSaves] = useState(0);

  const fetchStatsAndProfile = useCallback(async () => {
    if (!user) return;
    try {
      const statsRes = await fetch('/api/quizzes/stats');
      if (statsRes.ok) {
        const statsData = await statsRes.json();
        setDueCount(statsData.due_today || 0);
      }
    } catch (err) {
      console.error('Failed to fetch quiz stats in App:', err);
    }
    try {
      const meRes = await fetch('/api/me');
      if (meRes.ok) {
        const meData = await meRes.json();
        setStreak(meData.streak_count || 0);
        setTotalSaves(meData.total_saves || 0);
      }
    } catch (err) {
      console.error('Failed to fetch profile settings in App:', err);
    }
  }, [user]);

  useEffect(() => {
    if (!user) return;
    fetchStatsAndProfile();

    const handleUpdate = () => {
      fetchStatsAndProfile();
    };

    window.addEventListener('quiz-answered', handleUpdate);
    window.addEventListener('online-refetch', handleUpdate);
    window.addEventListener('items-updated', handleUpdate);
    return () => {
      window.removeEventListener('quiz-answered', handleUpdate);
      window.removeEventListener('online-refetch', handleUpdate);
      window.removeEventListener('items-updated', handleUpdate);
    };
  }, [user, fetchStatsAndProfile]);

  /* ── Routing ───────────────────────────────────────────── */
  const [currentPath, setCurrentPath] = useState(window.location.pathname);
  const prevRoomRef = useRef(null);

  useEffect(() => {
    const handler = () => setCurrentPath(window.location.pathname);
    window.addEventListener('popstate', handler);
    return () => window.removeEventListener('popstate', handler);
  }, []);

  /* ── Auth redirect ────────────────────────────────────── */
  useEffect(() => {
    if (loading) return;
    if (user) {
      if (['/login', '/', '/dashboard'].includes(currentPath)) {
        const search = window.location.search || '';
        window.history.replaceState({}, '', `/archive${search}`);
        setCurrentPath('/archive');
      }
    } else {
      if (currentPath !== '/login') {
        const search = window.location.search || '';
        window.history.replaceState({}, '', `/login${search}`);
        setCurrentPath('/login');
      }
    }
  }, [user, loading, currentPath]);

  const currentRoom = pathToRoom(currentPath);

  /* ── Cybernetic audio room transition sound effects ──────────────── */
  useEffect(() => {
    if (!user) return;
    AudioEngine.playTransition();
  }, [currentRoom, user]);

  /* ── Cmd+K search overlay ─────────────────────────────── */
  const [searchOpen, setSearchOpen] = useState(false);
  const [selectedItemForArchive, setSelectedItemForArchive] = useState(null);

  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setSearchOpen(open => !open);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  /* ── Navigation with transition ──────────────────────────── */
  const handleNavigate = useCallback((roomId) => {
    const paths = { archive: '/archive', map: '/map', drill: '/drill', settings: '/settings', profile: '/profile', bridges: '/bridges' };
    if (!paths[roomId] || roomId === currentRoom) return;
    prevRoomRef.current = currentRoom;
    window.history.pushState({}, '', paths[roomId]);
    setCurrentPath(paths[roomId]);
  }, [currentRoom]);

  /* ── Loading screen ───────────────────────────────────── */
  if (loading) {
    return <SplashScreen />;
  }

  /* ── Unauthenticated ──────────────────────────────────── */
  if (!user) {
    return (
      <>
        <CustomCursor />
        <Login />
      </>
    );
  }

  /* ── Isolated POC Route ────────────────────────────────── */
  if (currentRoom === 'poc-branching') {
    return (
      <PerfProvider>
        <Suspense fallback={<RoomLoader />}>
          <BranchingPOC />
        </Suspense>
      </PerfProvider>
    );
  }

  /* ── Observatory Shell ────────────────────────────────── */
  return (
    <PerfProvider>
      <div className={`observatory-shell ${assistantOpen ? 'assistant-active' : ''}`}>
        <CustomCursor />
      <Sidebar
        currentRoom={currentRoom}
        onNavigate={handleNavigate}
        onSearchOpen={() => setSearchOpen(true)}
        onSettingsOpen={() => handleNavigate('settings')}
        dueCount={dueCount}
        streak={streak}
      />
      
      {/* MB-1: Mobile Bottom Tab Bar */}
      <nav className="mobile-bottom-nav" aria-label="Mobile navigation">
        {[
          {
            id: 'archive',
            label: 'Archive',
            icon: (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <line x1="3" y1="6" x2="21" y2="6" />
                <line x1="3" y1="12" x2="21" y2="12" />
                <line x1="3" y1="18" x2="21" y2="18" />
              </svg>
            )
          },
          {
            id: 'map',
            label: 'Map',
            icon: (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <circle cx="6"  cy="6"  r="2" />
                <circle cx="18" cy="6"  r="2" />
                <circle cx="12" cy="18" r="2" />
                <circle cx="6"  cy="18" r="2" />
                <line x1="8"  y1="6"  x2="16" y2="6"  />
                <line x1="7"  y1="7"  x2="11" y2="17" />
                <line x1="17" y1="7"  x2="13" y2="17" />
                <line x1="8"  y1="18" x2="10" y2="18" />
              </svg>
            )
          },
          {
            id: 'drill',
            label: 'Drill',
            icon: (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <polygon points="12 2 2 22 22 22 12 2" />
              </svg>
            )
          },
          {
            id: 'settings',
            label: 'Settings',
            icon: (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <circle cx="12" cy="12" r="3"/>
                <path d="M12 2v2M12 20v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M2 12h2M20 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/>
              </svg>
            )
          }
        ].map(tab => {
          const isActive = currentRoom === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => { AudioEngine.playClick(); handleNavigate(tab.id); }}
              className={`mobile-nav-item ${isActive ? 'active' : ''}`}
            >
              <div style={{ position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                {tab.icon}
                {tab.id === 'drill' && dueCount > 0 && (
                  <span className="mobile-nav-badge">
                    {dueCount}
                  </span>
                )}
              </div>
              <span className="mobile-nav-label">{tab.label}</span>
            </button>
          );
        })}
      </nav>

      <main className="observatory-content" role="main">
        <RoomErrorBoundary>
          <RoomTransition
            fromRoom={prevRoomRef.current}
            toRoom={currentRoom}
            onDone={() => { prevRoomRef.current = null; }}
          >
            <Suspense fallback={<RoomLoader />}>
              {currentRoom === 'archive' && (
                <Archive
                  initialSelectedItem={selectedItemForArchive}
                  onClearInitialSelect={() => setSelectedItemForArchive(null)}
                />
              )}
              {currentRoom === 'map'     && <Map />}
              {currentRoom === 'drill'   && <Drill />}
              {currentRoom === 'settings' && <Settings />}
              {currentRoom === 'profile'  && <Profile />}
              {currentRoom === 'bridges'  && <Bridges />}
            </Suspense>
          </RoomTransition>
        </RoomErrorBoundary>
      </main>


      <ChatDrawer 
        isOpen={assistantOpen} 
        onOpen={() => setAssistantOpen(true)} 
        onClose={() => setAssistantOpen(false)} 
        totalSaves={totalSaves}
        onItemSelect={(item) => {
          setSelectedItemForArchive(item);
          handleNavigate('archive');
        }}
      />

      {/* Cmd+K search */}
      {searchOpen && (
        <SearchOverlay
          dueCount={dueCount}
          onClose={() => setSearchOpen(false)}
          onItemSelect={(item) => {
            if (item && item.type) {
              handleNavigate(item.type);
            } else {
              setSelectedItemForArchive(item);
              handleNavigate('archive');
            }
            setSearchOpen(false);
          }}
        />
      )}
      </div>
    </PerfProvider>
  );
}

export default App;

