import React, { useState, useEffect, useRef } from 'react';
import { 
  Link, 
  Microphone, 
  FilePdf, 
  Image as ImageIcon, 
  TextT, 
  X, 
  Bell, 
  BookOpen 
} from '@phosphor-icons/react';
import { NodePanelSkeleton } from './Skeleton';
import { useToast } from './Toast';
import FormattedText from './FormattedText';

export default function NodePanel({
  node,
  selectedNode,
  loadingNodeDetail,
  onClose,
  hubs = [],
  activeNodes = [],
  onViewAllMembers
}) {
  const displayNode = node || selectedNode;
  const [mounted, setMounted] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(false);
  const [showReminderInput, setShowReminderInput] = useState(false);
  const [reminderMessage, setReminderMessage] = useState('');
  const [reminderTime, setReminderTime] = useState('');
  const [savingReminder, setSavingReminder] = useState(false);
  const [showQuiz, setShowQuiz] = useState(false);
  const [selectedOptionIdx, setSelectedOptionIdx] = useState(null);
  const [quizAnswered, setQuizAnswered] = useState(false);
  
  const panelRef = useRef(null);
  const { addToast } = useToast();

  // Detect prefers-reduced-motion
  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    setReducedMotion(mediaQuery.matches);
    const listener = (e) => setReducedMotion(e.matches);
    mediaQuery.addEventListener('change', listener);
    return () => mediaQuery.removeEventListener('change', listener);
  }, []);

  // Update internal display states when node changes
  useEffect(() => {
    if (displayNode) {
      setReminderMessage(`Review: ${displayNode.title || 'Saved Item'}`);
      setReminderTime('');
      setShowReminderInput(false);
      setShowQuiz(false);
      setSelectedOptionIdx(null);
      setQuizAnswered(false);
      
      // Trigger slide-in transition on next frame
      const frame = requestAnimationFrame(() => setMounted(true));
      return () => cancelAnimationFrame(frame);
    } else {
      setMounted(false);
    }
  }, [displayNode]);

  // Escape key close & focus trapping
  useEffect(() => {
    if (!displayNode) return;

    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        onClose();
        return;
      }

      if (e.key === 'Tab') {
        const focusableElements = panelRef.current?.querySelectorAll(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        );
        if (!focusableElements || focusableElements.length === 0) return;

        const first = focusableElements[0];
        const last = focusableElements[focusableElements.length - 1];

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

    window.addEventListener('keydown', handleKeyDown);

    // Initial focus on the close button or first element
    const focusable = panelRef.current?.querySelectorAll(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    if (focusable && focusable.length > 0) {
      focusable[0].focus();
    }

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [displayNode, onClose]);

  // Click outside to close panel
  useEffect(() => {
    if (!displayNode) return;

    const handleClickOutside = (e) => {
      if (panelRef.current && !panelRef.current.contains(e.target)) {
        if (e.target.closest('.constellation-node') || e.target.closest('.context-menu')) {
          return;
        }
        onClose();
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('touchstart', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('touchstart', handleClickOutside);
    };
  }, [displayNode, onClose]);

  if (!displayNode) return null;

  const isHub = displayNode.type === 'hub' || displayNode.id < 0;
  
  let hubInfo = null;
  if (isHub) {
    const hubId = displayNode.id < 0 ? -displayNode.id : displayNode.id;
    const hub = hubs.find(h => h.id === hubId);
    if (hub) {
      const memberIds = hub.member_ids || [];
      const memberNodes = activeNodes.filter(n => n.id > 0 && memberIds.includes(n.id));
      const sortedMembers = [...memberNodes].sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
      hubInfo = {
        memberCount: memberIds.length,
        top5: sortedMembers.slice(0, 5),
        memberIds
      };
    }
  }

  // Check if a quiz exists on this node
  const hasQuiz = !!(displayNode.quiz || displayNode.has_quiz || displayNode.quiz_id);

  // Content type icon mapper
  const getSourceIcon = (type) => {
    switch (type?.toLowerCase()) {
      case 'url':
        return <Link size={16} data-testid="icon-Link" />;
      case 'voice':
        return <Microphone size={16} data-testid="icon-Microphone" />;
      case 'pdf':
        return <FilePdf size={16} data-testid="icon-FilePdf" />;
      case 'image':
        return <ImageIcon size={16} data-testid="icon-Image" />;
      case 'text':
      default:
        return <TextT size={16} data-testid="icon-TextT" />;
    }
  };

  const handleSaveReminder = async (e) => {
    e.preventDefault();
    if (!reminderTime) {
      addToast('Please select a reminder date and time', 'warning');
      return;
    }
    setSavingReminder(true);
    try {
      const remindAtUtc = new Date(reminderTime).toISOString();
      const res = await fetch('/api/reminders', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          item_id: displayNode.id > 0 ? displayNode.id : null,
          message: reminderMessage,
          remind_at: remindAtUtc
        })
      });
      if (res.ok) {
        addToast('Reminder configured successfully!', 'success');
        setShowReminderInput(false);
      } else {
        const errData = await res.json();
        addToast(errData.message || 'Failed to create reminder', 'error');
      }
    } catch (err) {
      console.error('Error creating reminder:', err);
      addToast('Network error, failed to save reminder', 'error');
    } finally {
      setSavingReminder(false);
    }
  };

  const handleSelectOption = (idx) => {
    setSelectedOptionIdx(idx);
    setQuizAnswered(true);
    if (idx === displayNode.quiz.correct_index) {
      addToast('Correct answer!', 'success');
    } else {
      addToast('Incorrect answer, try again!', 'error');
    }
  };

  const transitionStyle = reducedMotion 
    ? 'none' 
    : 'transform 0.4s cubic-bezier(0.16, 1, 0.3, 1)';
  const transformStyle = mounted ? 'translateX(0)' : 'translateX(360px)';

  return (
    <div 
      ref={panelRef}
      className="node-panel glass-card glass-glow-top"
      role="dialog"
      aria-modal="true"
      aria-label="Node Details"
      style={{
        position: 'fixed',
        right: 0,
        top: '56px',
        bottom: 0,
        width: '360px',
        zIndex: 1000,
        transform: transformStyle,
        transition: transitionStyle,
        overflowY: 'auto',
        display: 'flex',
        flexDirection: 'column',
        padding: '1.5rem',
        boxSizing: 'border-box'
      }}
    >
      {loadingNodeDetail ? (
        <NodePanelSkeleton />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
          {/* Header Close button */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '0.5rem' }}>
            <button 
              onClick={onClose}
              aria-label="Close panel"
              style={{
                background: 'none',
                border: 'none',
                color: 'var(--color-text-muted, #8e8e9f)',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                padding: '0.25rem',
                minWidth: '44px',
                minHeight: '44px'
              }}
            >
              <X size={20} />
            </button>
          </div>

          {/* Title */}
          <h2 style={{ fontFamily: 'Outfit, sans-serif', fontSize: '20px', fontWeight: 600, margin: '0 0 0.75rem 0', color: 'var(--color-text, #fff)' }}>
            {displayNode.title}
          </h2>

          {/* Source Type Badge */}
          {!isHub && (
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem', alignSelf: 'flex-start', padding: '0.25rem 0.6rem', borderRadius: '4px', background: 'rgba(255,255,255,0.06)', border: '1px solid var(--border-glass, rgba(255,255,255,0.08))', fontSize: '12px', color: 'var(--color-text, #fff)', textTransform: 'capitalize', marginBottom: '1rem' }}>
              {getSourceIcon(displayNode.source_type)}
              <span>{displayNode.source_type}</span>
            </div>
          )}

          {/* Summary Text (Inter, 14px, --text-secondary) */}
          {!isHub && (
            <div style={{ fontFamily: 'Inter, sans-serif', fontSize: '14px', color: 'var(--text-secondary, #8e8e9f)', lineHeight: '1.6', margin: '0 0 1.25rem 0' }}>
              <FormattedText text={displayNode.summary} />
            </div>
          )}

          {/* Source URL if present */}
          {displayNode.source_url && (
            <div style={{ marginBottom: '1rem' }}>
              <a 
                href={displayNode.source_url} 
                target="_blank" 
                rel="noopener noreferrer"
                style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', fontSize: '13px', color: 'var(--color-primary, #6c63ff)', textDecoration: 'none', fontWeight: 500 }}
              >
                <Link size={14} />
                View Source
              </a>
            </div>
          )}

          {/* Tags */}
          {displayNode.tags && displayNode.tags.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem', marginBottom: '1rem' }}>
              {displayNode.tags.map((tag, idx) => (
                <span 
                  key={idx}
                  className="tag-pill"
                  style={{ 
                    backgroundColor: 'var(--color-primary-glow, rgba(108, 99, 255, 0.15))', 
                    color: 'var(--color-primary, #6c63ff)', 
                    padding: '0.2rem 0.5rem', 
                    borderRadius: '4px', 
                    fontSize: '11px',
                    border: '1px solid rgba(108, 99, 255, 0.1)'
                  }}
                >
                  #{tag}
                </span>
              ))}
            </div>
          )}

          {/* Created At (JetBrains Mono, 12px) */}
          <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '12px', color: 'var(--color-text-muted, #8e8e9f)', marginBottom: '1.5rem' }}>
            Created: {new Date(displayNode.created_at).toLocaleString()}
          </div>

          {/* Hub members if it is a hub */}
          {isHub && hubInfo && (
            <div style={{ display: 'flex', flexDirection: 'column', flex: 1, marginBottom: '1.5rem' }}>
              <div style={{ fontSize: '14px', color: 'var(--color-accent, #00d4aa)', fontWeight: 600, marginBottom: '1rem' }}>
                {hubInfo.memberCount} items
              </div>
              <h3 style={{ fontSize: '14px', color: 'var(--color-text-muted, #8e8e9f)', marginBottom: '0.5rem', fontWeight: 600 }}>
                Recent Members
              </h3>
              <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 1.25rem 0' }}>
                {hubInfo.top5.map(member => (
                  <li 
                    key={member.id} 
                    style={{ 
                      fontSize: '13px', 
                      color: 'var(--color-text, #fff)', 
                      padding: '0.4rem 0', 
                      borderBottom: '1px solid var(--border-glass, rgba(255,255,255,0.08))',
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis'
                    }}
                  >
                    {member.title}
                  </li>
                ))}
              </ul>
              <button
                onClick={() => onViewAllMembers && onViewAllMembers(hubInfo.memberIds, displayNode.title)}
                className="btn btn-primary"
                style={{ width: '100%', minHeight: '44px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
              >
                View all members in Feed
              </button>
            </div>
          )}

          {/* Interactive buttons for non-hub items */}
          {!isHub && (
            <div style={{ marginTop: 'auto', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {hasQuiz && (
                <button 
                  onClick={() => setShowQuiz(!showQuiz)}
                  className="btn btn-primary"
                  style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem', width: '100%', minHeight: '44px' }}
                >
                  <BookOpen size={18} />
                  Open Quiz
                </button>
              )}

              {showQuiz && displayNode.quiz && (
                <div style={{ padding: '1rem', background: 'rgba(255, 255, 255, 0.03)', borderRadius: '8px', border: '1px solid var(--border-glass, rgba(255,255,255,0.08))', marginBottom: '0.5rem' }}>
                  <h4 style={{ fontSize: '13px', margin: '0 0 0.75rem 0', color: 'var(--color-text, #fff)', lineHeight: '1.4' }}>{displayNode.quiz.question}</h4>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                    {displayNode.quiz.options.map((opt, idx) => {
                      let btnStyle = {
                        width: '100%',
                        padding: '0.6rem',
                        borderRadius: '6px',
                        textAlign: 'left',
                        fontSize: '13px',
                        cursor: 'pointer',
                        background: 'rgba(255,255,255,0.05)',
                        border: '1px solid var(--border-glass, rgba(255,255,255,0.08))',
                        color: '#fff',
                        transition: 'all 0.2s ease',
                        minHeight: '44px'
                      };
                      
                      if (quizAnswered) {
                        if (idx === displayNode.quiz.correct_index) {
                          btnStyle.background = 'rgba(0, 212, 170, 0.2)';
                          btnStyle.borderColor = 'var(--color-accent, #00d4aa)';
                        } else if (idx === selectedOptionIdx) {
                          btnStyle.background = 'rgba(255, 8, 68, 0.2)';
                          btnStyle.borderColor = '#ff0844';
                        }
                      }
                      
                      return (
                        <button 
                          key={idx}
                          onClick={() => handleSelectOption(idx)}
                          disabled={quizAnswered}
                          style={btnStyle}
                        >
                          {opt}
                        </button>
                      );
                    })}
                  </div>
                  {quizAnswered && (
                    <div style={{ marginTop: '1rem', fontSize: '13px', borderTop: '1px solid var(--border-glass)', paddingTop: '0.75rem' }}>
                      <div style={{ fontWeight: 'bold', color: selectedOptionIdx === displayNode.quiz.correct_index ? 'var(--color-accent, #00d4aa)' : '#ff0844', marginBottom: '0.25rem' }}>
                        {selectedOptionIdx === displayNode.quiz.correct_index ? 'Correct!' : 'Incorrect'}
                      </div>
                      <p style={{ color: 'var(--color-text-muted, #8e8e9f)', margin: 0, lineHeight: '1.4' }}>{displayNode.quiz.explanation}</p>
                    </div>
                  )}
                </div>
              )}

              <button 
                onClick={() => setShowReminderInput(!showReminderInput)}
                className="btn btn-secondary"
                style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem', width: '100%', minHeight: '44px' }}
              >
                <Bell size={18} />
                {showReminderInput ? 'Hide Reminder' : 'Set Reminder'}
              </button>

              {showReminderInput && (
                <form onSubmit={handleSaveReminder} style={{ padding: '1rem', background: 'rgba(255,255,255,0.03)', borderRadius: '8px', border: '1px solid var(--border-glass, rgba(255,255,255,0.08))', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                  <div>
                    <label htmlFor="reminder-message" style={{ display: 'block', fontSize: '11px', marginBottom: '0.25rem', color: 'var(--color-text-muted, #8e8e9f)' }}>Message</label>
                    <input 
                      id="reminder-message"
                      type="text" 
                      value={reminderMessage}
                      onChange={(e) => setReminderMessage(e.target.value)}
                      className="form-control"
                      style={{ width: '100%', padding: '0.5rem', background: 'rgba(0,0,0,0.2)', border: '1px solid var(--border-glass, rgba(255,255,255,0.08))', borderRadius: '4px', color: '#fff', fontSize: '13px', boxSizing: 'border-box' }}
                      required
                    />
                  </div>
                  <div>
                    <label htmlFor="reminder-time" style={{ display: 'block', fontSize: '11px', marginBottom: '0.25rem', color: 'var(--color-text-muted, #8e8e9f)' }}>Remind At</label>
                    <input 
                      id="reminder-time"
                      type="datetime-local" 
                      value={reminderTime}
                      onChange={(e) => setReminderTime(e.target.value)}
                      className="form-control"
                      style={{ width: '100%', padding: '0.5rem', background: 'rgba(0,0,0,0.2)', border: '1px solid var(--border-glass, rgba(255,255,255,0.08))', borderRadius: '4px', color: '#fff', fontSize: '13px', boxSizing: 'border-box' }}
                      required
                    />
                  </div>
                  <button 
                    type="submit" 
                    disabled={savingReminder}
                    className="btn btn-primary"
                    style={{ width: '100%', minHeight: '44px' }}
                  >
                    {savingReminder ? 'Saving...' : 'Save Reminder'}
                  </button>
                </form>
              )}
            </div>
          )}

          {/* Close button at the bottom (required by existing dashboard test suites) */}
          <button
            onClick={onClose}
            className="btn btn-secondary"
            style={{ width: '100%', minHeight: '44px', marginTop: '0.75rem' }}
          >
            Close
          </button>
        </div>
      )}
    </div>
  );
}
