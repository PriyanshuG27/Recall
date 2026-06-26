import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import FormattedText from '../components/FormattedText';

describe('FormattedText Component', () => {
  it('returns null for empty text', () => {
    const { container } = render(<FormattedText text="" />);
    expect(container.firstChild).toBeNull();
  });

  it('strips thinking blocks completely', () => {
    const text = 'Before <think>some thought</think> After';
    render(<FormattedText text={text} />);
    expect(screen.getByText(/Before/)).toBeInTheDocument();
    expect(screen.getByText(/After/)).toBeInTheDocument();
    expect(screen.queryByText('some thought')).not.toBeInTheDocument();
  });

  it('handles unclosed thinking blocks', () => {
    const text = 'Before <think>unclosed thought';
    render(<FormattedText text={text} />);
    expect(screen.getByText(/Before/)).toBeInTheDocument();
    expect(screen.queryByText('unclosed thought')).not.toBeInTheDocument();
  });

  it('renders in excerpt mode by stripping all markdown tags', () => {
    const text = '### Heading\n**Bold** and *Italic*\n\\(x^2\\) and \\[E=mc^2\\]';
    render(<FormattedText text={text} excerptMode={true} />);
    expect(screen.getByText('Heading Bold and Italic x^2 and E=mc^2')).toBeInTheDocument();
  });

  it('truncates text in excerpt mode if exceeding limit', () => {
    const longText = 'a'.repeat(200);
    render(<FormattedText text={longText} excerptMode={true} />);
    expect(screen.getByText(new RegExp('a{177}\\.\\.\\.'))).toBeInTheDocument();
  });

  it('renders section headings correctly', () => {
    const text = '# Title\n## Subtitle\n### Section';
    render(<FormattedText text={text} />);
    expect(screen.getByRole('heading', { level: 3 })).toHaveTextContent('Title');
    expect(screen.getByRole('heading', { level: 4 })).toHaveTextContent('Subtitle');
    expect(screen.getByRole('heading', { level: 5 })).toHaveTextContent('Section');
  });

  it('renders bullet lists correctly', () => {
    const text = '- Item 1\n- Item 2';
    render(<FormattedText text={text} />);
    const listItems = screen.getAllByRole('listitem');
    expect(listItems).toHaveLength(2);
    expect(listItems[0]).toHaveTextContent('Item 1');
    expect(listItems[1]).toHaveTextContent('Item 2');
  });

  it('renders code blocks correctly', () => {
    const text = 'Here is code:\n```python\nprint("Hello")\n```\nDone.';
    render(<FormattedText text={text} />);
    expect(screen.getByText('print("Hello")')).toBeInTheDocument();
    expect(screen.getByText(/Here is code:/)).toBeInTheDocument();
    expect(screen.getByText(/Done\./)).toBeInTheDocument();
  });

  it('renders metadata italic blocks correctly', () => {
    const text = '*Type: Technical | Tone: Technical*';
    render(<FormattedText text={text} />);
    const emNode = screen.getByText('Type: Technical | Tone: Technical');
    expect(emNode.tagName).toBe('EM');
  });

  it('renders inline code backticks correctly', () => {
    const text = 'Here is `some code` inline.';
    const { container } = render(<FormattedText text={text} />);
    const codeNode = container.querySelector('.code-inline');
    expect(codeNode).toHaveTextContent('some code');
  });

  it('renders LaTeX math equations correctly', () => {
    const text = 'Math: \\(a^2 + b^2 = c^2\\) and block \\[x = y\\]';
    const { container } = render(<FormattedText text={text} />);
    const inlineMath = container.querySelector('.math-inline');
    const blockMath = container.querySelector('.math-block');
    expect(inlineMath).toHaveTextContent('a^2 + b^2 = c^2');
    expect(blockMath).toHaveTextContent('x = y');
  });

  it('cleans up complex LaTeX commands in equations', () => {
    const text = 'Inline: $d_{\\text{model}} = 512$ and block \\[\n\\text{Attention}(Q,K,V)=\\text{softmax}\\left(\\frac{Q K^T}{\\sqrt{d_k}}\\right)V\n\\]';
    const { container } = render(<FormattedText text={text} />);
    const inlineMath = container.querySelector('.math-inline');
    const blockMath = container.querySelector('.math-block');
    expect(inlineMath).toHaveTextContent('d_model = 512');
    expect(blockMath).toHaveTextContent('Attention(Q,K,V)=softmax(Q K^T / √(d_k))V');
  });

  it('cleans up Greek letters and sum/int operators in equations', () => {
    const text = 'Math: \\(\\theta_i = \\alpha + \\sum_{i=1}^N \\beta_i\\) and block \\[\\int_a^b f(x) dx \\ge 0\\]';
    const { container } = render(<FormattedText text={text} />);
    const inlineMath = container.querySelector('.math-inline');
    const blockMath = container.querySelector('.math-block');
    expect(inlineMath).toHaveTextContent('θ_i = α + ∑_i=1^N β_i');
    expect(blockMath).toHaveTextContent('∫_a^b f(x) dx ≥ 0');
  });

  it('renders markdown tables correctly including joined divider lines', () => {
    const text = '| Header 1 | Header 2 |\n|---|---||\n| Value 1 | Value 2 |';
    const { container } = render(<FormattedText text={text} />);
    const table = container.querySelector('table');
    expect(table).toBeInTheDocument();
    
    const ths = container.querySelectorAll('th');
    expect(ths).toHaveLength(2);
    expect(ths[0]).toHaveTextContent('Header 1');
    expect(ths[1]).toHaveTextContent('Header 2');

    const tds = container.querySelectorAll('td');
    expect(tds).toHaveLength(2);
    expect(tds[0]).toHaveTextContent('Value 1');
    expect(tds[1]).toHaveTextContent('Value 2');
  });
});
