import React from 'react';

export function GraphSkeleton() {
  return (
    <div className="skeleton-graph shimmer" data-testid="skeleton-graph" />
  );
}

export function FeedCardSkeleton() {
  const cards = Array.from({ length: 6 });
  return (
    <div className="skeleton-card-grid" data-testid="skeleton-feed">
      {cards.map((_, i) => (
        <div key={i} className="skeleton-card glass-card">
          <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div className="skeleton-line badge shimmer"></div>
            <div className="skeleton-line shimmer" style={{ width: '50px', height: '12px' }}></div>
          </div>
          
          <div className="skeleton-line title shimmer" style={{ marginBottom: '1rem' }}></div>
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', marginBottom: '1.5rem' }}>
            <div className="skeleton-line excerpt shimmer" style={{ margin: 0 }}></div>
            <div className="skeleton-line excerpt-short shimmer" style={{ margin: 0 }}></div>
          </div>
          
          <div className="card-footer" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 'auto' }}>
            <div className="skeleton-line tags shimmer" style={{ margin: 0 }}></div>
            <div className="skeleton-line shimmer" style={{ width: '20px', height: '20px', borderRadius: '4px', margin: 0 }}></div>
          </div>
        </div>
      ))}
    </div>
  );
}

export function NodePanelSkeleton() {
  return (
    <div className="skeleton-node-panel" data-testid="skeleton-node-panel">
      <div className="skeleton-line title shimmer" style={{ width: '80%', height: '1.5rem', marginBottom: '1.5rem' }}></div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginBottom: '2rem' }}>
        <div className="skeleton-line excerpt shimmer" style={{ margin: 0, width: '100%' }}></div>
        <div className="skeleton-line excerpt shimmer" style={{ margin: 0, width: '95%' }}></div>
        <div className="skeleton-line excerpt-short shimmer" style={{ margin: 0, width: '70%' }}></div>
      </div>
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <div className="skeleton-line shimmer" style={{ width: '80px', height: '28px', borderRadius: '6px', margin: 0 }}></div>
      </div>
    </div>
  );
}
