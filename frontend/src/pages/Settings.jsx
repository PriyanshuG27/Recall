import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../components/Toast';
import axios from '../api/client';
import { 
  User, Gear, Clock, Database, Flame, Globe, 
  SpeakerHigh, SpeakerSlash, Plus, Trash, SignOut, Info, CalendarPlus, CheckCircle, Warning, Copy, UploadSimple, DownloadSimple
} from '@phosphor-icons/react';
import ConnectDriveCard from '../components/ConnectDriveCard';
import AudioEngine from '../utils/AudioEngine';

export default function Settings() {
  const { logout, user } = useAuth();
  const { addToast } = useToast();

  const [loading, setLoading] = useState(false);
  const [timezoneOffset, setTimezoneOffset] = useState(0);
  const [digestEnabled, setDigestEnabled] = useState(true);
  const [audioMuted, setAudioMuted] = useState(AudioEngine.isMuted());

  // Profile Stats
  const [stats, setStats] = useState({
    streak_count: 0,
    total_saves: 0,
    quizzes_answered: 0,
    drive_connected: false,
    google_last_sync: null,
    telegram_chat_id: '',
    last_7_days_activity: [false, false, false, false, false, false, false],
    last_activity_date: null
  });

  // Reminders
  const [reminders, setReminders] = useState([]);
  const [remindersLoading, setRemindersLoading] = useState(false);
  const [newReminderMsg, setNewReminderMsg] = useState('');
  const [newReminderTime, setNewReminderTime] = useState('');

  // Actions
  const [deleteConfirmText, setDeleteConfirmText] = useState('');
  const [deleting, setDeleting] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportingZip, setExportingZip] = useState(false);
  const [importingZip, setImportingZip] = useState(false);

  const fetchSettings = async () => {
    setLoading(true);
    try {
      const res = await axios.get('/api/me');
      const data = res.data;
      
      const dbOffset = data.timezone_offset ?? 0;
      const localOffset = -new Date().getTimezoneOffset() / 60;
      const hasBeenExplicitlySet = localStorage.getItem('timezone_explicitly_set') === 'true';


      setDigestEnabled(data.digest_enabled ?? true);
      setStats({
        streak_count: data.streak_count ?? 0,
        total_saves: data.total_saves ?? 0,
        quizzes_answered: data.quizzes_answered ?? 0,
        drive_connected: data.drive_connected ?? false,
        google_last_sync: data.google_last_sync,
        telegram_chat_id: data.telegram_chat_id ?? '',
        last_7_days_activity: data.last_7_days_activity ?? [false, false, false, false, false, false, false],
        last_activity_date: data.last_activity_date
      });

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
  };

  const fetchReminders = async () => {
    setRemindersLoading(true);
    try {
      const res = await axios.get('/api/reminders');
      setReminders(res.data || []);
    } catch (err) {
      console.error('Failed to fetch reminders:', err);
    } finally {
      setRemindersLoading(false);
    }
  };

  useEffect(() => {
    fetchSettings();
    fetchReminders();
  }, []);

  useEffect(() => {
    const handleMuteToggle = (e) => {
      setAudioMuted(e.detail);
    };
    window.addEventListener('recall-mute-toggle', handleMuteToggle);
    return () => window.removeEventListener('recall-mute-toggle', handleMuteToggle);
  }, []);

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

  const handleDigestToggle = async () => {
    const nextDigest = !digestEnabled;
    setDigestEnabled(nextDigest);
    try {
      await axios.patch('/api/me', { digest_enabled: nextDigest });
      addToast(`Daily digest ${nextDigest ? 'enabled' : 'disabled'}`, 'success');
    } catch (err) {
      console.error('Failed to update digest settings:', err);
      addToast('Failed to update digest preference', 'error');
    }
  };

  const handleCreateReminder = async (e) => {
    e.preventDefault();
    if (!newReminderMsg.trim() || !newReminderTime) {
      addToast('Please provide a message and a valid time', 'error');
      return;
    }

    const remindAtUTC = new Date(newReminderTime).toISOString();

    try {
      await axios.post('/api/reminders', {
        message: newReminderMsg,
        remind_at: remindAtUTC
      });
      addToast('Reminder scheduled successfully', 'success');
      setNewReminderMsg('');
      setNewReminderTime('');
      fetchReminders();
    } catch (err) {
      console.error('Failed to schedule reminder:', err);
      addToast(err.response?.data?.detail || 'Failed to schedule reminder', 'error');
    }
  };

  const handleDeleteReminder = async (id) => {
    try {
      await axios.delete(`/api/reminders/${id}`);
      addToast('Reminder removed', 'success');
      fetchReminders();
    } catch (err) {
      console.error('Failed to delete reminder:', err);
      addToast('Failed to delete reminder', 'error');
    }
  };

  const handleExportData = async () => {
    setExporting(true);
    try {
      const response = await axios.get('/api/export', { responseType: 'blob' });
      const filename = `recall-export-${new Date().toISOString().split('T')[0]}.json`;
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', filename);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      addToast('Data export downloaded', 'success');
    } catch (err) {
      console.error('Failed to export data:', err);
      addToast('Failed to export data', 'error');
    } finally {
      setExporting(false);
    }
  };

  const handleExportZip = async () => {
    setExportingZip(true);
    try {
      const response = await axios.get('/api/export/zip', { responseType: 'blob' });
      const filename = `recall-obsidian-export-${new Date().toISOString().split('T')[0]}.zip`;
      const url = window.URL.createObjectURL(response.data);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', filename);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      addToast('Obsidian Vault ZIP downloaded successfully', 'success');
    } catch (err) {
      console.error('Failed to export Obsidian ZIP:', err);
      addToast('Failed to export Obsidian ZIP', 'error');
    } finally {
      setExportingZip(false);
    }
  };

  const handleImportZip = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    
    setImportingZip(true);
    const formData = new FormData();
    formData.append('file', file);
    
    try {
      const response = await axios.post('/api/import/zip', formData, {
        headers: {
          'Content-Type': 'multipart/form-data'
        }
      });
      addToast(`Successfully imported ${response.data.imported_count} notes into your graph!`, 'success');
      e.target.value = '';
    } catch (err) {
      console.error('Failed to import Obsidian ZIP:', err);
      const detail = err.response?.data?.detail || 'Import failed';
      addToast(`Import failed: ${detail}`, 'error');
    } finally {
      setImportingZip(false);
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

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text);
    addToast('Channel ID copied to clipboard', 'success');
  };

  const initials = user?.first_name ? user.first_name[0].toUpperCase() : user?.username?.[0]?.toUpperCase() ?? '?';
  const nameLabel = user?.first_name || user?.username || 'Signal Observer';
  const roleLabel = stats.total_saves >= 100 ? 'Observatory Sage' : stats.total_saves >= 25 ? 'Signal Keeper' : 'Signal Novice';

  const rawOffsets = [];
  for (let h = -12; h <= 14; h++) {
    rawOffsets.push(h);
    if (h >= -11 && h <= 13) rawOffsets.push(h + 0.5);
  }
  rawOffsets.push(5.75);
  const uniqueOffsets = [...new Set(rawOffsets)].sort((a, b) => a - b);
  const timezones = uniqueOffsets.map(i => {
    const absI = Math.abs(i);
    const hours = Math.floor(absI);
    const mins = Math.round((absI - hours) * 60);
    const sign = i > 0 ? '+' : (i < 0 ? '-' : '');
    const minsStr = mins === 0 ? '' : `:${mins.toString().padStart(2, '0')}`;
    return { value: i, label: i === 0 ? 'UTC' : `UTC${sign}${hours}${minsStr}` };
  });

  const getDayLabel = (idx) => {
    const d = new Date();
    d.setDate(d.getDate() - (6 - idx));
    return d.toLocaleDateString('en-US', { weekday: 'short' });
  };

  if (loading) {
    return (
      <div style={{ width: '100%', height: '100vh', background: 'var(--bg-void)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '1.5rem' }}>
        <div style={{ width: 40, height: 40, borderRadius: '50%', border: '2px solid rgba(207,163,101,0.2)', borderTopColor: 'var(--accent-gold)', animation: 'spin 1s linear infinite' }} />
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', letterSpacing: '0.12em' }}>SYNCHRONIZING OBSERVER CONTROL…</span>
      </div>
    );
  }

  return (
    <div className="settings-page" style={{
      width: '100%',
      height: '100vh',
      background: 'var(--bg-void)',
      position: 'relative',
      overflowY: 'auto',
      display: 'flex',
      flexDirection: 'column',
    }}>
      {/* Decorative Background */}
      <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: '550px', background: 'radial-gradient(ellipse 65% 35% at 50% 0%, rgba(207, 163, 101, 0.05) 0%, transparent 80%)', pointerEvents: 'none' }} />

      {/* Header section */}
      <div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--accent-gold)', letterSpacing: '0.25em', textTransform: 'uppercase', marginBottom: '0.5rem' }}>
          <Gear size={14} /> Control Room
        </div>
        <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 'clamp(32px, 5vw, 48px)', fontWeight: 700, color: '#F0EDE8', letterSpacing: '-0.04em', margin: 0 }}>
          Profile & Settings
        </h1>
        <p style={{ fontFamily: 'var(--font-sans)', fontSize: '14px', color: 'var(--text-muted)', marginTop: '0.5rem', maxWidth: '650px', lineHeight: 1.6 }}>
          Calibrate system variables, review your cognitive streak rhythms, schedule Telegram memory reminders, and manage Google Drive synchronization.
        </p>
      </div>

      {/* 3-Column Premium Grid Layout */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 340px), 1fr))',
        gap: '2.5rem',
        alignItems: 'start'
      }}>
        
        {/* ════════ COLUMN 1: THE OBSERVER IDENTITY ════════ */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span style={{ width: '4px', height: '12px', background: 'var(--accent-gold)', borderRadius: '2px' }} />
            <h3 style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'rgba(240, 237, 232, 0.75)', letterSpacing: '0.12em', textTransform: 'uppercase' }}>
              Observer Profile
            </h3>
          </div>
          
          {/* Main Profile Info Card */}
          <div style={{ 
            background: 'linear-gradient(180deg, rgba(255,255,255,0.015) 0%, rgba(0,0,0,0) 100%)', 
            border: '1px solid rgba(207, 163, 101, 0.12)', 
            borderRadius: '20px', 
            padding: '2rem', 
            display: 'flex', 
            flexDirection: 'column',
            gap: '1.5rem',
            backdropFilter: 'blur(15px)',
            boxShadow: '0 10px 40px rgba(0,0,0,0.45)'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '1.25rem' }}>
              <div style={{
                width: '64px', height: '64px', borderRadius: '50%',
                background: 'radial-gradient(circle, rgba(207,163,101,0.25) 0%, rgba(207,163,101,0.02) 100%)',
                border: '1px solid rgba(207,163,101,0.5)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontFamily: 'var(--font-display)', fontSize: '24px', fontWeight: 600, color: 'var(--accent-gold)',
                boxShadow: '0 0 20px rgba(207,163,101,0.2)'
              }}>
                {initials}
              </div>
              <div>
                <h2 style={{ margin: 0, fontFamily: 'var(--font-sans)', fontSize: '18px', fontWeight: 600, color: '#F0EDE8' }}>
                  {nameLabel}
                </h2>
                <div style={{ display: 'inline-block', background: 'rgba(207,163,101,0.08)', border: '1px solid rgba(207,163,101,0.25)', borderRadius: '4px', padding: '2px 8px', marginTop: '6px' }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '9px', color: 'var(--accent-gold)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
                    {roleLabel}
                  </span>
                </div>
              </div>
            </div>

            {/* Telegram Channel details */}
            <div style={{ borderTop: '1px solid rgba(255,255,255,0.04)', paddingTop: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '9px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Observation Channel
              </span>
              <div style={{ display: 'flex', alignItems: 'center', justifyItems: 'center', justifyContent: 'space-between', background: 'rgba(0,0,0,0.2)', border: '1px solid rgba(207,163,101,0.08)', borderRadius: '8px', padding: '0.5rem 0.75rem' }}>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', color: '#F0EDE8' }}>
                  ID: {stats.telegram_chat_id || 'Not Linked'}
                </span>
                {stats.telegram_chat_id && (
                  <button 
                    onClick={() => copyToClipboard(stats.telegram_chat_id)}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'rgba(207,163,101,0.6)', display: 'flex', alignItems: 'center' }}
                    title="Copy Chat ID"
                  >
                    <Copy size={14} />
                  </button>
                )}
              </div>
            </div>

            {/* General joined date */}
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
              <span>Connection Established</span>
              <span style={{ color: '#F0EDE8' }}>
                {user?.created_at ? new Date(user.created_at).toLocaleDateString() : 'Active'}
              </span>
            </div>
          </div>

          {/* Flame Streak Display */}
          <div style={{
            background: 'linear-gradient(135deg, rgba(232,152,60,0.08) 0%, rgba(0,0,0,0) 100%)',
            border: '1px solid rgba(232, 152, 60, 0.2)',
            borderRadius: '20px',
            padding: '1.5rem 2rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            position: 'relative',
            overflow: 'hidden',
            boxShadow: '0 8px 32px rgba(232,152,60,0.04)'
          }}>
            <div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: '9px', color: 'rgba(232,152,60,0.85)', letterSpacing: '0.12em', textTransform: 'uppercase', marginBottom: '6px' }}>
                Consecutive Ritual
              </div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.4rem' }}>
                <span style={{ fontFamily: 'var(--font-display)', fontSize: '2.5rem', fontWeight: 800, color: '#F0EDE8', letterSpacing: '-0.04em' }}>
                  {stats.streak_count}
                </span>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'rgba(232,152,60,0.9)' }}>
                  days active
                </span>
              </div>
            </div>
            <Flame 
              size={54} 
              weight="fill" 
              color={stats.streak_count > 0 ? '#E8983C' : 'rgba(207, 163, 101, 0.15)'} 
              style={{ filter: stats.streak_count > 0 ? 'drop-shadow(0 0 12px rgba(232,152,60,0.5))' : 'none' }}
            />
          </div>

          {/* 7-Day Contribution Frequency Calendar */}
          <div style={{ background: 'rgba(255,255,255,0.01)', border: '1px solid rgba(207,163,101,0.06)', borderRadius: '20px', padding: '1.5rem 2rem' }}>
            <h4 style={{ margin: '0 0 1.25rem 0', fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--text-muted)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
              Ritual Frequency (Last 7 Days)
            </h4>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              {stats.last_7_days_activity.map((active, idx) => (
                <div key={idx} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.5rem' }}>
                  <div style={{
                    width: '32px', height: '32px', borderRadius: '50%',
                    background: active ? 'rgba(207, 163, 101, 0.15)' : 'rgba(255,255,255,0.02)',
                    border: `1.5px solid ${active ? 'var(--accent-gold)' : 'rgba(255,255,255,0.08)'}`,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    boxShadow: active ? '0 0 12px rgba(207,163,101,0.25)' : 'none',
                    transition: 'all 0.2s ease'
                  }}>
                    {active ? (
                      <CheckCircle size={14} color="var(--accent-gold)" weight="fill" />
                    ) : (
                      <div style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'rgba(255,255,255,0.15)' }} />
                    )}
                  </div>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '9px', color: active ? 'var(--accent-gold)' : 'var(--text-muted)' }}>
                    {getDayLabel(idx)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* ════════ COLUMN 2: SYSTEM VARIABLES & PREFERENCES ════════ */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span style={{ width: '4px', height: '12px', background: 'var(--accent-gold)', borderRadius: '2px' }} />
            <h3 style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'rgba(240, 237, 232, 0.75)', letterSpacing: '0.12em', textTransform: 'uppercase' }}>
              Calibrations
            </h3>
          </div>

          <div style={{ background: 'rgba(255,255,255,0.015)', border: '1px solid rgba(207,163,101,0.08)', borderRadius: '20px', padding: '2rem', display: 'flex', flexDirection: 'column', gap: '1.75rem', backdropFilter: 'blur(10px)' }}>
            
            {/* Timezone Selection */}
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '0.65rem' }}>
                <Globe size={14} color="var(--accent-gold)" />
                <label htmlFor="timezone-select" style={{ display: 'block', fontSize: '10px', fontFamily: 'var(--font-mono)', textTransform: 'uppercase', color: 'var(--text-muted)', letterSpacing: '0.08em', margin: 0 }}>
                  Local Timezone Offset
                </label>
              </div>
              <select
                id="timezone-select"
                value={timezoneOffset}
                onChange={handleTimezoneChange}
                style={{
                  width: '100%',
                  background: 'rgba(0, 0, 0, 0.25)',
                  border: '1px solid rgba(207, 163, 101, 0.15)',
                  color: '#F0EDE8',
                  padding: '0.85rem',
                  borderRadius: '10px',
                  outline: 'none',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '13px',
                  cursor: 'pointer',
                  transition: 'border-color 0.2s'
                }}
              >
                {timezones.map((tz) => (
                  <option key={tz.value} value={tz.value} style={{ background: '#09080E' }}>
                    {tz.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Daily Summary Digest Toggle */}
            <div style={{ display: 'flex', alignItems: 'center', justifyItems: 'center', justifyContent: 'space-between', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '1.5rem' }}>
              <div style={{ paddingRight: '1rem' }}>
                <h5 style={{ margin: 0, fontFamily: 'var(--font-sans)', fontSize: '14px', fontWeight: 600, color: '#F0EDE8' }}>
                  Daily Morning Digest
                </h5>
                <p style={{ margin: '4px 0 0', fontFamily: 'var(--font-sans)', fontSize: '12px', color: 'var(--text-muted)', lineHeight: 1.45 }}>
                  Receive a structured morning summary of your catalogued items inside Telegram.
                </p>
              </div>
              <button
                onClick={handleDigestToggle}
                style={{
                  border: 'none', cursor: 'pointer',
                  width: '44px', height: '24px', borderRadius: '12px',
                  background: digestEnabled ? 'var(--accent-gold)' : 'rgba(255,255,255,0.1)',
                  position: 'relative', display: 'flex', alignItems: 'center',
                  padding: '2px', transition: 'background-color 0.2s', flexShrink: 0
                }}
              >
                <div style={{
                  width: '20px', height: '20px', borderRadius: '50%', background: '#09080E',
                  transform: `translateX(${digestEnabled ? '20px' : '0'})`, transition: 'transform 0.2s'
                }} />
              </button>
            </div>

            {/* Audio Feedback Toggle */}
            <div style={{ display: 'flex', alignItems: 'center', justifyItems: 'center', justifyContent: 'space-between', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '1.5rem' }}>
              <div>
                <h5 style={{ margin: 0, fontFamily: 'var(--font-sans)', fontSize: '14px', fontWeight: 600, color: '#F0EDE8' }}>
                  Cybernetic Soundscapes
                </h5>
                <p style={{ margin: '4px 0 0', fontFamily: 'var(--font-sans)', fontSize: '12px', color: 'var(--text-muted)', lineHeight: 1.45 }}>
                  Play synthesized minor chords and sweep clicks when navigating.
                </p>
              </div>
              <button
                onClick={() => {
                  const next = !audioMuted;
                  setAudioMuted(next);
                  AudioEngine.setMuted(next);
                }}
                style={{
                  cursor: 'pointer',
                  padding: '10px', borderRadius: '8px',
                  background: audioMuted ? 'rgba(255,255,255,0.02)' : 'rgba(207,163,101,0.08)',
                  border: `1px solid ${audioMuted ? 'rgba(255,255,255,0.08)' : 'rgba(207,163,101,0.25)'}`,
                  color: audioMuted ? 'rgba(207,163,101,0.3)' : 'var(--accent-gold)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0
                }}
              >
                {audioMuted ? <SpeakerSlash size={18} /> : <SpeakerHigh size={18} />}
              </button>
            </div>
          </div>

          {/* Quick Mastery Stat Display Cards */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div style={{ background: 'rgba(255,255,255,0.01)', border: '1px solid rgba(207,163,101,0.05)', borderRadius: '16px', padding: '1.25rem' }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: '9px', color: 'var(--text-muted)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: '6px' }}>
                Archived Items
              </div>
              <span style={{ fontFamily: 'var(--font-display)', fontSize: '20px', fontWeight: 700, color: '#F0EDE8' }}>
                {stats.total_saves} signals
              </span>
            </div>
            <div style={{ background: 'rgba(255,255,255,0.01)', border: '1px solid rgba(207,163,101,0.05)', borderRadius: '16px', padding: '1.25rem' }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: '9px', color: 'var(--text-muted)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: '6px' }}>
                Drills Mastered
              </div>
              <span style={{ fontFamily: 'var(--font-display)', fontSize: '20px', fontWeight: 700, color: '#F0EDE8' }}>
                {stats.quizzes_answered} completed
              </span>
            </div>
          </div>
        </div>

        {/* ════════ COLUMN 3: BACKUP, INTEGRATIONS & INTEGRITY ════════ */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span style={{ width: '4px', height: '12px', background: 'var(--accent-gold)', borderRadius: '2px' }} />
            <h3 style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'rgba(240, 237, 232, 0.75)', letterSpacing: '0.12em', textTransform: 'uppercase' }}>
              Backup & Integrations
            </h3>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            {/* Google Drive Connection widget */}
            <ConnectDriveCard />

            {/* Last drive sync date indicator */}
            {stats.drive_connected && stats.google_last_sync && (
              <div style={{ display: 'flex', gap: '0.5rem', background: 'rgba(207,163,101,0.03)', border: '1px solid rgba(207,163,101,0.1)', borderRadius: '10px', padding: '0.75rem 1rem', fontSize: '11px', fontFamily: 'var(--font-mono)', color: 'var(--accent-gold)' }}>
                <Clock size={14} style={{ flexShrink: 0, marginTop: '1px' }} />
                <span>Last Cloud Sync: {new Date(stats.google_last_sync).toLocaleString()}</span>
              </div>
            )}

            {/* Chrome Extension Download Card */}
            <div style={{ background: 'rgba(255,255,255,0.015)', border: '1px solid rgba(207, 163, 101, 0.08)', borderRadius: '20px', padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem', backdropFilter: 'blur(10px)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Globe size={16} color="var(--accent-gold)" />
                <h5 style={{ margin: 0, fontFamily: 'var(--font-sans)', fontSize: '14px', fontWeight: 600, color: '#F0EDE8' }}>
                  Chrome Extension
                </h5>
              </div>
              <p style={{ margin: 0, fontFamily: 'var(--font-sans)', fontSize: '12px', color: 'var(--text-muted)', lineHeight: 1.55 }}>
                Capture links, page selections, and quote highlights from any webpage. Download the pre-packaged extension directly, extract the ZIP, and load it into Google Chrome via Developer Mode.
              </p>
              <button
                onClick={() => {
                  AudioEngine.playClick();
                  window.open('/api/extension/download', '_blank');
                }}
                style={{
                  width: '100%',
                  background: 'rgba(255, 255, 255, 0.02)',
                  border: '1px solid rgba(207, 163, 101, 0.18)',
                  color: '#F0EDE8',
                  padding: '0.75rem',
                  borderRadius: '10px',
                  cursor: 'pointer',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '11px',
                  letterSpacing: '0.05em',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '0.5rem',
                  transition: 'all 0.2s'
                }}
              >
                <DownloadSimple size={14} /> Download Extension (.ZIP)
              </button>
            </div>

            {/* Data Portability GDPR Export */}
            <div style={{ background: 'rgba(255,255,255,0.015)', border: '1px solid rgba(207, 163, 101, 0.08)', borderRadius: '20px', padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem', backdropFilter: 'blur(10px)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Database size={16} color="var(--accent-gold)" />
                <h5 style={{ margin: 0, fontFamily: 'var(--font-sans)', fontSize: '14px', fontWeight: 600, color: '#F0EDE8' }}>
                  Data Portability
                </h5>
              </div>
              <p style={{ margin: 0, fontFamily: 'var(--font-sans)', fontSize: '12px', color: 'var(--text-muted)', lineHeight: 1.55 }}>
                Pursue full information ownership. Download your complete profile, nodes connection database, reminders, and drill logs inside a structured JSON package.
              </p>
              <button
                onClick={handleExportData}
                disabled={exporting}
                style={{
                  width: '100%',
                  background: 'rgba(255, 255, 255, 0.02)',
                  border: '1px solid rgba(207, 163, 101, 0.18)',
                  color: '#F0EDE8',
                  padding: '0.75rem',
                  borderRadius: '10px',
                  cursor: 'pointer',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '11px',
                  letterSpacing: '0.05em',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '0.5rem',
                  transition: 'all 0.2s'
                }}
              >
                {exporting ? 'Exporting...' : 'Export My Data (JSON)'}
              </button>
            </div>

            {/* Obsidian Integration */}
            <div style={{ background: 'rgba(255,255,255,0.015)', border: '1px solid rgba(207, 163, 101, 0.08)', borderRadius: '20px', padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1.25rem', backdropFilter: 'blur(10px)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Globe size={16} color="var(--accent-gold)" />
                <h5 style={{ margin: 0, fontFamily: 'var(--font-sans)', fontSize: '14px', fontWeight: 600, color: '#F0EDE8' }}>
                  Obsidian & OKF Integration
                </h5>
              </div>
              <p style={{ margin: 0, fontFamily: 'var(--font-sans)', fontSize: '12px', color: 'var(--text-muted)', lineHeight: 1.55 }}>
                Recall uses standard Open Knowledge Format (OKF). Export your complete knowledge graph to edit inside Obsidian or bulk upload your Obsidian vault ZIP directly.
              </p>
              
              <div style={{ display: 'flex', gap: '0.75rem' }}>
                <button
                  onClick={handleExportZip}
                  disabled={exportingZip}
                  style={{
                    flex: 1,
                    background: 'rgba(255, 255, 255, 0.02)',
                    border: '1px solid rgba(207, 163, 101, 0.18)',
                    color: '#F0EDE8',
                    padding: '0.75rem',
                    borderRadius: '10px',
                    cursor: 'pointer',
                    fontFamily: 'var(--font-mono)',
                    fontSize: '11px',
                    letterSpacing: '0.05em',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '0.5rem',
                    transition: 'all 0.2s'
                  }}
                >
                  <DownloadSimple size={14} />
                  {exportingZip ? 'Exporting...' : 'Export Vault (ZIP)'}
                </button>

                <label
                  style={{
                    flex: 1,
                    background: 'rgba(207, 163, 101, 0.08)',
                    border: '1px solid rgba(207, 163, 101, 0.25)',
                    color: 'var(--accent-gold)',
                    padding: '0.75rem',
                    borderRadius: '10px',
                    cursor: 'pointer',
                    fontFamily: 'var(--font-mono)',
                    fontSize: '11px',
                    letterSpacing: '0.05em',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '0.5rem',
                    transition: 'all 0.2s',
                    textAlign: 'center'
                  }}
                >
                  <UploadSimple size={14} />
                  {importingZip ? 'Importing...' : 'Import Vault (ZIP)'}
                  <input
                    type="file"
                    accept=".zip"
                    onChange={handleImportZip}
                    disabled={importingZip}
                    style={{ display: 'none' }}
                  />
                </label>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ── SECTION: RITUAL CUE SCHEDULER ── */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', marginTop: '1rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span style={{ width: '4px', height: '12px', background: 'var(--accent-gold)', borderRadius: '2px' }} />
          <h3 style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'rgba(240, 237, 232, 0.75)', letterSpacing: '0.12em', textTransform: 'uppercase' }}>
            Ritual Scheduler
          </h3>
        </div>

        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))',
          gap: '2.5rem'
        }}>
          {/* Schedule Form */}
          <form onSubmit={handleCreateReminder} style={{ background: 'rgba(255,255,255,0.01)', border: '1px solid rgba(207,163,101,0.08)', borderRadius: '20px', padding: '2rem', display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            <h4 style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--accent-gold)', letterSpacing: '0.08em', textTransform: 'uppercase', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <CalendarPlus size={16} /> Schedule Telegram Cue
            </h4>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
              <input
                type="text"
                placeholder="Review topic or reminder message..."
                value={newReminderMsg}
                onChange={(e) => setNewReminderMsg(e.target.value)}
                style={{
                  width: '100%',
                  background: 'rgba(0, 0, 0, 0.2)',
                  border: '1px solid rgba(207, 163, 101, 0.15)',
                  color: '#F0EDE8',
                  padding: '0.85rem',
                  borderRadius: '10px',
                  outline: 'none',
                  fontSize: '13px'
                }}
              />
              <input
                type="datetime-local"
                value={newReminderTime}
                onChange={(e) => setNewReminderTime(e.target.value)}
                style={{
                  width: '100%',
                  background: 'rgba(0, 0, 0, 0.2)',
                  border: '1px solid rgba(207, 163, 101, 0.15)',
                  color: '#F0EDE8',
                  padding: '0.85rem',
                  borderRadius: '10px',
                  outline: 'none',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '12px',
                  cursor: 'pointer'
                }}
              />
            </div>
            <button
              type="submit"
              style={{
                width: '100%',
                background: 'rgba(207, 163, 101, 0.15)',
                border: '1px solid var(--accent-gold)',
                color: 'var(--accent-gold)',
                padding: '0.85rem',
                borderRadius: '10px',
                cursor: 'pointer',
                fontFamily: 'var(--font-mono)',
                fontSize: '11px',
                letterSpacing: '0.08em',
                textTransform: 'uppercase',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '0.4rem',
                transition: 'all 0.2s'
              }}
            >
              <Plus size={14} /> Schedule Reminder
            </button>
          </form>

          {/* Active reminders list */}
          <div style={{ background: 'rgba(255,255,255,0.01)', border: '1px solid rgba(207,163,101,0.08)', borderRadius: '20px', padding: '2rem', display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            <h4 style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--text-muted)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
              Pending Review Cues
            </h4>
            
            <div style={{ maxHeight: '200px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '0.75rem', paddingRight: '0.5rem' }}>
              {remindersLoading ? (
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'rgba(207,163,101,0.4)', textAlign: 'center', padding: '1.5rem 0' }}>
                  RETRIEVING CUES…
                </div>
              ) : reminders.length === 0 ? (
                <div style={{ border: '1px dashed rgba(207,163,101,0.06)', borderRadius: '12px', padding: '2.5rem', textAlign: 'center' }}>
                  <p style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-muted)' }}>
                    No pending Telegram cues configured.
                  </p>
                </div>
              ) : (
                reminders.map(rem => {
                  const dateLabel = new Date(rem.remind_at).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
                  return (
                    <div key={rem.id} style={{ display: 'flex', alignItems: 'center', justifyItems: 'center', justifyContent: 'space-between', background: 'rgba(255,255,255,0.015)', border: '1px solid rgba(207,163,101,0.06)', borderRadius: '10px', padding: '0.85rem 1.25rem' }}>
                      <div style={{ paddingRight: '0.75rem' }}>
                        <p style={{ margin: 0, fontFamily: 'var(--font-sans)', fontSize: '13px', color: '#F0EDE8', lineHeight: 1.45 }}>
                          {rem.message}
                        </p>
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '9px', color: 'var(--accent-gold)', display: 'flex', alignItems: 'center', gap: '0.35rem', marginTop: '6px' }}>
                          <Clock size={11} /> {dateLabel}
                        </span>
                      </div>
                      <button
                        onClick={() => handleDeleteReminder(rem.id)}
                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'rgba(239, 68, 68, 0.55)', padding: '0.35rem', borderRadius: '50%', transition: 'all 0.2s' }}
                        title="Remove Reminder"
                      >
                        <Trash size={15} />
                      </button>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ── SECTION: DANGER SYSTEM ACTIONS ── */}
      <div style={{ borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '3rem', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span style={{ width: '4px', height: '12px', background: '#ef4444', borderRadius: '2px' }} />
          <h3 style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: '11px', color: '#ef4444', letterSpacing: '0.12em', textTransform: 'uppercase' }}>
            System Integrity & Danger Actions
          </h3>
        </div>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '2rem', alignItems: 'start' }}>
          {/* Sign Out Button */}
          <button
            onClick={logout}
            style={{
              background: 'rgba(255, 255, 255, 0.02)',
              border: '1px solid rgba(207, 163, 101, 0.15)',
              color: '#F0EDE8',
              padding: '0.85rem 1.75rem',
              borderRadius: '10px',
              cursor: 'pointer',
              fontFamily: 'var(--font-mono)',
              fontSize: '12px',
              letterSpacing: '0.05em',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              transition: 'all 0.2s',
              boxShadow: '0 4px 15px rgba(0,0,0,0.2)'
            }}
          >
            <SignOut size={14} /> Sign Out Session
          </button>

          {/* Purge Account Box */}
          <div style={{ flex: 1, minWidth: '340px', border: '1px solid rgba(239, 68, 68, 0.2)', padding: '1.75rem 2rem', borderRadius: '20px', background: 'rgba(239, 68, 68, 0.015)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
              <Warning size={16} color="#ef4444" />
              <h5 style={{ margin: 0, color: '#ef4444', fontSize: '14px', fontWeight: 600 }}>Purge Observer Profile</h5>
            </div>
            <p style={{ margin: '0 0 1.25rem 0', fontSize: '12px', color: 'var(--text-muted)', lineHeight: 1.5 }}>
              Irreversibly delete your profile credentials, saved observation nodes from the network, pending reminder schedules, and logs history.
            </p>
            
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'center' }}>
              <input
                type="text"
                value={deleteConfirmText}
                onChange={(e) => setDeleteConfirmText(e.target.value)}
                placeholder='Type "DELETE" to verify'
                style={{
                  background: 'rgba(0,0,0,0.25)',
                  border: '1px solid rgba(239, 68, 68, 0.25)',
                  color: '#fff',
                  padding: '0.75rem',
                  borderRadius: '10px',
                  outline: 'none',
                  fontSize: '13px',
                  minWidth: '220px'
                }}
              />

              <button
                onClick={handleDeleteAccount}
                disabled={deleteConfirmText !== 'DELETE' || deleting}
                style={{
                  backgroundColor: deleteConfirmText === 'DELETE' ? '#ef4444' : 'rgba(239, 68, 68, 0.05)',
                  color: deleteConfirmText === 'DELETE' ? '#fff' : 'rgba(255, 255, 255, 0.2)',
                  border: 'none',
                  padding: '0.75rem 1.5rem',
                  borderRadius: '10px',
                  cursor: deleteConfirmText === 'DELETE' ? 'pointer' : 'not-allowed',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '11px',
                  letterSpacing: '0.05em',
                  textTransform: 'uppercase',
                  transition: 'background-color 0.2s'
                }}
              >
                {deleting ? 'Purging...' : 'Purge Account'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
