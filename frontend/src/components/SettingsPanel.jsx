import React, { useState, useEffect, useRef } from 'react';
import { useAuth } from '../context/AuthContext';
import { useToast } from './Toast';
import axios from '../api/client';
import { Gear, Trash, SignOut } from '@phosphor-icons/react';
import ConnectDriveCard from './ConnectDriveCard';

export default function SettingsPanel({ isOpen, onClose }) {
  const { logout } = useAuth();
  const { addToast } = useToast();
  const panelRef = useRef(null);

  const [loading, setLoading] = useState(false);
  const [timezoneOffset, setTimezoneOffset] = useState(0);
  const [stats, setStats] = useState({
    streak_count: 0,
    total_saves: 0,
    quizzes_answered: 0,
    drive_connected: false
  });
  const [deleteConfirmText, setDeleteConfirmText] = useState('');
  const [deleting, setDeleting] = useState(false);
  const [exporting, setExporting] = useState(false);

  // Fetch settings on open
  useEffect(() => {
    if (!isOpen) return;

    async function fetchSettings() {
      setLoading(true);
      try {
        const res = await axios.get('/api/me');
        const dbOffset = res.data.timezone_offset;

        // Detect local browser timezone offset in hours (with decimals, e.g. 5.5)
        const localOffset = -new Date().getTimezoneOffset() / 60;

        setStats({
          streak_count: res.data.streak_count,
          total_saves: res.data.total_saves,
          quizzes_answered: res.data.quizzes_answered,
          drive_connected: res.data.drive_connected
        });

        const hasBeenExplicitlySet = localStorage.getItem('timezone_explicitly_set') === 'true';
        if (dbOffset !== localOffset && !hasBeenExplicitlySet) {
          try {
            await axios.patch('/api/me', { timezone_offset: localOffset });
            setTimezoneOffset(localOffset);
            addToast(`Timezone auto-detected and set to UTC${localOffset >= 0 ? '+' : ''}${localOffset}`, 'info');
          } catch (patchErr) {
            console.error('Failed to auto-set detected timezone:', patchErr);
            setTimezoneOffset(dbOffset);
          }
        } else {
          setTimezoneOffset(dbOffset);
        }
      } catch (err) {
        console.error('Failed to fetch settings:', err);
        addToast('Failed to load settings', 'error');
      } finally {
        setLoading(false);
      }
    }

    fetchSettings();
  }, [isOpen, addToast]);

  // Focus trap and Escape listener
  useEffect(() => {
    if (!isOpen || loading) return;

    // Focus the first focusable element (the timezone select or close button)
    const focusable = panelRef.current?.querySelectorAll('button, select, input, [tabindex="0"]');
    if (focusable && focusable.length > 0) {
      focusable[0].focus();
    }

    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      } else if (e.key === 'Tab') {
        const elements = panelRef.current?.querySelectorAll('button, select, input, [tabindex="0"]');
        if (!elements || elements.length === 0) return;
        const first = elements[0];
        const last = elements[elements.length - 1];

        if (e.shiftKey) {
          if (document.activeElement === first) {
            e.preventDefault();
            last.focus();
          }
        } else {
          if (document.activeElement === last) {
            e.preventDefault();
            first.focus();
          }
        }
      }
    };

    const handleClickOutside = (e) => {
      if (panelRef.current && !panelRef.current.contains(e.target)) {
        if (e.target.closest('.profile-menu-container') || e.target.closest('.dropdown-menu')) {
          return;
        }
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('touchstart', handleClickOutside);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('touchstart', handleClickOutside);
    };
  }, [isOpen, onClose, loading]);

  if (!isOpen) return null;

  const handleTimezoneChange = async (e) => {
    const val = parseFloat(e.target.value);
    setTimezoneOffset(val);
    localStorage.setItem('timezone_explicitly_set', 'true');
    try {
      await axios.patch('/api/me', { timezone_offset: val });
      addToast('Timezone updated successfully', 'success');
    } catch (err) {
      console.error('Failed to update timezone:', err);
      addToast('Failed to update timezone', 'error');
    }
  };

  const handleDeleteAccount = async () => {
    if (deleteConfirmText !== 'DELETE') return;
    if (!confirm('WARNING: This will permanently delete your account and all associated data. Are you absolutely sure?')) return;

    setDeleting(true);
    try {
      await axios.delete('/api/me');
      addToast('Account deleted successfully', 'success');
      logout();
    } catch (err) {
      console.error('Failed to delete account:', err);
      addToast('Failed to delete account', 'error');
    } finally {
      setDeleting(false);
    }
  };

  const handleExportData = async () => {
    setExporting(true);
    try {
      const response = await axios.get('/api/export', {
        responseType: 'blob'
      });
      
      let filename = `recall-export-${new Date().toISOString().split('T')[0]}.json`;
      const disposition = response.headers['content-disposition'];
      if (disposition && disposition.indexOf('attachment') !== -1) {
        const filenameRegex = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/;
        const matches = filenameRegex.exec(disposition);
        if (matches != null && matches[1]) { 
          filename = matches[1].replace(/['"]/g, '');
        }
      }

      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', filename);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      addToast('Data export downloaded successfully', 'success');
    } catch (err) {
      console.error('Failed to export data:', err);
      if (err.response && err.response.status === 429) {
        try {
          const text = await err.response.data.text();
          const parsed = JSON.parse(text);
          if (parsed.error === 'rate_limit_exceeded') {
            const hours = Math.ceil(parsed.retry_after / 3600);
            addToast(`Export limit exceeded. Please try again in ${hours} hour${hours > 1 ? 's' : ''}.`, 'error');
            return;
          }
        } catch (parseErr) {
          // Fallback
        }
        addToast('Export limit exceeded (1 per 24 hours). Please try again later.', 'error');
      } else {
        addToast('Failed to export data. Please try again.', 'error');
      }
    } finally {
      setExporting(false);
    }
  };

  const rawOffsets = [];
  for (let h = -12; h <= 14; h++) {
    rawOffsets.push(h);
    if (h >= -11 && h <= 13) {
      rawOffsets.push(h + 0.5);
    }
  }
  // Add common quarter-hour offsets
  rawOffsets.push(5.75); // Nepal
  rawOffsets.push(8.75); // Central Western Australia
  rawOffsets.push(12.75); // Chatham Islands
  rawOffsets.sort((a, b) => a - b);
  const uniqueOffsets = [...new Set(rawOffsets)];

  const timezones = uniqueOffsets.map(i => {
    const absI = Math.abs(i);
    const hours = Math.floor(absI);
    const mins = Math.round((absI - hours) * 60);
    const sign = i > 0 ? '+' : (i < 0 ? '-' : '');
    const minsStr = mins === 0 ? '' : `:${mins.toString().padStart(2, '0')}`;
    const label = i === 0 ? 'UTC' : `UTC${sign}${hours}${minsStr}`;
    return { value: i, label };
  });

  return (
    <div 
      ref={panelRef}
      className="node-panel glass-card settings-panel"
      role="dialog"
      aria-modal="true"
      aria-labelledby="settings-title-id"
      style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--border-glass)', paddingBottom: '0.75rem' }}>
        <h3 id="settings-title-id" style={{ fontSize: '1.25rem', color: 'var(--color-text)', margin: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Gear size={20} aria-hidden="true" /> Settings
        </h3>
        <button 
          onClick={onClose} 
          className="btn btn-secondary"
          style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem', minHeight: '32px' }}
        >
          Close
        </button>
      </div>

      {loading ? (
        <div style={{ color: 'var(--color-text-muted)', fontSize: '0.875rem' }}>Loading preferences...</div>
      ) : (
        <>
          {/* Timezone Preference */}
          <div>
            <label htmlFor="timezone-select" style={{ display: 'block', fontSize: '0.875rem', fontWeight: 500, color: 'var(--color-text)', marginBottom: '0.5rem' }}>
              Local Timezone Offset
            </label>
            <select
              id="timezone-select"
              value={timezoneOffset}
              onChange={handleTimezoneChange}
              style={{
                width: '100%',
                background: 'rgba(255, 255, 255, 0.05)',
                border: '1px solid var(--border-glass)',
                color: 'var(--color-text)',
                padding: '0.5rem',
                borderRadius: '6px',
                outline: 'none',
                fontFamily: 'var(--font-sans)',
                fontSize: '0.875rem'
              }}
            >
              {timezones.map((tz) => (
                <option key={tz.value} value={tz.value} style={{ background: 'var(--bg-base)' }}>
                  {tz.label}
                </option>
              ))}
            </select>
          </div>

          {/* Stats Display */}
          <div style={{ background: 'rgba(255, 255, 255, 0.02)', padding: '1rem', borderRadius: '8px', border: '1px solid var(--border-glass)' }}>
            <h4 style={{ margin: '0 0 0.75rem 0', fontSize: '0.9rem', color: 'var(--color-text)' }}>Your Stats</h4>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', fontSize: '0.8125rem', color: 'var(--color-text-muted)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Total Saves</span>
                <span style={{ color: 'var(--color-text)', fontWeight: 600 }}>{stats.total_saves}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Daily Streak</span>
                <span style={{ color: 'var(--color-text)', fontWeight: 600 }}>🔥 {stats.streak_count} days</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Quizzes Answered</span>
                <span style={{ color: 'var(--color-text)', fontWeight: 600 }}>{stats.quizzes_answered}</span>
              </div>
            </div>
          </div>

          {/* Google Drive Connection Card */}
          <ConnectDriveCard />

          {/* GDPR Data Portability */}
          <div style={{ background: 'rgba(255, 255, 255, 0.02)', padding: '1rem', borderRadius: '8px', border: '1px solid var(--border-glass)', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            <h4 style={{ margin: 0, fontSize: '0.9rem', color: 'var(--color-text)' }}>Export Data (GDPR)</h4>
            <p style={{ margin: 0, fontSize: '0.75rem', color: 'var(--color-text-muted)', lineHeight: 1.4 }}>
              Download all your saved items, profile statistics, reminders, and quiz schedules in standard, portable JSON format.
            </p>
            <button
              onClick={handleExportData}
              disabled={exporting}
              className="btn btn-primary"
              style={{
                width: '100%',
                minHeight: '40px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '0.5rem',
                fontSize: '0.875rem'
              }}
            >
              {exporting ? 'Exporting...' : 'Export My Data (JSON)'}
            </button>
          </div>

          {/* Danger Zone */}
          <div style={{ borderTop: '1px solid var(--border-glass)', paddingTop: '1.5rem', marginTop: 'auto', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <button
              onClick={logout}
              className="btn btn-secondary"
              style={{ width: '100%', minHeight: '44px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem', fontSize: '0.875rem' }}
            >
              <SignOut size={16} aria-hidden="true" /> Logout
            </button>

            <div style={{ border: '1px solid rgba(239, 68, 68, 0.2)', padding: '1rem', borderRadius: '8px', background: 'rgba(239, 68, 68, 0.02)' }}>
              <h5 style={{ margin: '0 0 0.5rem 0', color: '#ef4444', fontSize: '0.875rem' }}>Danger Zone</h5>
              <p style={{ margin: '0 0 0.75rem 0', fontSize: '0.75rem', color: 'var(--color-text-muted)', lineHeight: 1.4 }}>
                Permanently delete your account and all associated data. This action is irreversible.
              </p>
              
              <label htmlFor="delete-confirm-input" style={{ display: 'block', fontSize: '0.75rem', color: 'var(--color-text-muted)', marginBottom: '0.25rem' }}>
                Type "DELETE" to confirm
              </label>
              <input
                id="delete-confirm-input"
                type="text"
                value={deleteConfirmText}
                onChange={(e) => setDeleteConfirmText(e.target.value)}
                placeholder="DELETE"
                style={{
                  width: '100%',
                  background: 'rgba(255, 255, 255, 0.05)',
                  border: '1px solid var(--border-glass)',
                  color: 'var(--color-text)',
                  padding: '0.4rem 0.6rem',
                  borderRadius: '6px',
                  outline: 'none',
                  fontSize: '0.8125rem',
                  marginBottom: '0.75rem'
                }}
              />

              <button
                onClick={handleDeleteAccount}
                disabled={deleteConfirmText !== 'DELETE' || deleting}
                className="btn"
                style={{
                  width: '100%',
                  minHeight: '44px',
                  backgroundColor: deleteConfirmText === 'DELETE' ? '#ef4444' : 'rgba(239, 68, 68, 0.1)',
                  color: deleteConfirmText === 'DELETE' ? '#fff' : 'rgba(255, 255, 255, 0.3)',
                  border: 'none',
                  borderRadius: '6px',
                  cursor: deleteConfirmText === 'DELETE' ? 'pointer' : 'not-allowed',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '0.5rem',
                  fontSize: '0.875rem',
                  transition: 'background-color 0.2s'
                }}
              >
                <Trash size={16} aria-hidden="true" /> {deleting ? 'Deleting...' : 'Delete Account'}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
