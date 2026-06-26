import React from 'react';
import { MagnifyingGlass, Binoculars, PaperPlane } from '@phosphor-icons/react';

export default function EmptyState({ variant, query }) {
  const botUsername = import.meta.env.VITE_BOT_USERNAME || 'RecallTestEnvBot';
  const botUrl = `https://t.me/${botUsername}`;

  if (variant === 'graph') {
    return (
      <div className="empty-state-container full-canvas" data-testid="empty-state-graph">
        <div className="empty-state-orbital-container">
          <div className="empty-state-orbital-ring"></div>
          <div className="empty-state-orbital-node"></div>
        </div>
        <h3 className="empty-state-title">Your constellation is empty</h3>
        <p className="empty-state-subtext">
          Forward any link, voice note, or PDF to your Telegram bot to start mapping your knowledge.
        </p>
        <a 
          href={botUrl} 
          target="_blank" 
          rel="noopener noreferrer" 
          className="empty-state-btn"
        >
          <PaperPlane size={16} /> Open Telegram Bot
        </a>
      </div>
    );
  }

  if (variant === 'feed') {
    return (
      <div className="empty-state-container" data-testid="empty-state-feed">
        <div className="empty-state-icon">
          <MagnifyingGlass size={64} style={{ color: 'var(--color-text-muted)' }} />
        </div>
        <h3 className="empty-state-title">Nothing found</h3>
        <p className="empty-state-subtext">Try a different filter or search term.</p>
      </div>
    );
  }

  if (variant === 'search') {
    return (
      <div className="empty-state-container" data-testid="empty-state-search">
        <div className="empty-state-icon">
          <Binoculars size={64} style={{ color: 'var(--color-text-muted)' }} />
        </div>
        <h3 className="empty-state-title">No results for '{query}'</h3>
        <p className="empty-state-subtext">Try a different search term or check for typos.</p>
      </div>
    );
  }

  return null;
}
