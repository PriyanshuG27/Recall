import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import NodeHoverCard from '../canvas/NodeHoverCard';

describe('NodeHoverCard Component', () => {
  it('renders node details and tags correctly', () => {
    const mockNode = {
      title: 'Haskell Types',
      summary: 'Strong static type system',
      source_type: 'url',
      tags: ['haskell', 'fp']
    };

    render(
      <NodeHoverCard 
        node={mockNode} 
        isHub={false} 
        color="#7C6FD4" 
      />
    );

    expect(screen.getByText('Haskell Types')).toBeInTheDocument();
    expect(screen.getByText('Strong static type system')).toBeInTheDocument();
    expect(screen.getByText('#haskell #fp')).toBeInTheDocument();
  });
});
