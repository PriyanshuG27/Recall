import React from 'react';

// Clean thinking tags and format markdown and LaTeX dynamically
export default function FormattedText({ text, excerptMode = false }) {
  if (!text) return null;

  // 1. Strip thinking blocks
  let cleanText = text.replace(/<think>[\s\S]*?<\/think>/g, '');
  cleanText = cleanText.replace(/<think>[\s\S]*/g, '');
  cleanText = cleanText.replace(/<\/think>/g, '');
  cleanText = cleanText.trim();

  // If in excerpt mode (e.g. for Feed cards), keep it short and strip markdown tags for clean layout
  if (excerptMode) {
    // Strip headers
    let plainText = cleanText.replace(/^#+\s+/gm, '');
    // Strip bold/italic markup
    plainText = plainText.replace(/\*\*([^*]+)\*\*/g, '$1');
    plainText = plainText.replace(/\*([^*]+)\*/g, '$1');
    // Strip block equations
    plainText = plainText.replace(/\\\[([\s\S]+?)\\\]/g, '$1');
    plainText = plainText.replace(/\\\(([\s\S]+?)\\\)/g, '$1');
    // Limit length
    if (plainText.length > 180) {
      plainText = plainText.substring(0, 177) + '...';
    }
    return <span>{plainText}</span>;
  }

  // 2. Parse code blocks
  const parts = cleanText.split(/```/g);
  const renderedElements = [];

  parts.forEach((part, index) => {
    // Odd indices are code blocks
    if (index % 2 === 1) {
      const lines = part.split('\n');
      const firstLine = lines[0].trim();
      const hasLang = /^[a-zA-Z0-9_-]+$/.test(firstLine);
      const code = hasLang ? lines.slice(1).join('\n') : lines.join('\n');

      renderedElements.push(
        <pre
          key={`code-${index}`}
          style={{
            background: 'rgba(0, 0, 0, 0.4)',
            border: '1px solid var(--border-glass)',
            borderRadius: '8px',
            padding: '0.75rem 1rem',
            overflowX: 'auto',
            fontFamily: 'var(--font-mono, monospace)',
            fontSize: '0.8125rem',
            color: '#34d399',
            margin: '0.75rem 0',
          }}
        >
          <code>{code.trim()}</code>
        </pre>
      );
    } else {
      // Even indices are standard block elements
      const lines = part.split('\n');
      let currentList = [];
      let currentParagraph = [];

      const flushParagraph = (key) => {
        if (currentParagraph.length > 0) {
          const paraText = currentParagraph.join(' ');
          renderedElements.push(
            <div
              key={`p-${key}`}
              style={{
                fontSize: '0.875rem',
                lineHeight: '1.5',
                color: 'var(--color-text-muted)',
                marginBottom: '0.75rem',
              }}
            >
              {parseInlineStyles(paraText)}
            </div>
          );
          currentParagraph = [];
        }
      };

      const flushList = (key) => {
        if (currentList.length > 0) {
          renderedElements.push(
            <ul
              key={`ul-${key}`}
              style={{
                paddingLeft: '1.25rem',
                margin: '0.5rem 0 0.75rem 0',
                listStyleType: 'disc',
                color: 'var(--color-text-muted)',
              }}
            >
              {currentList.map((itemText, lIdx) => (
                <li
                  key={`ul-${key}-li-${lIdx}`}
                  style={{
                    fontSize: '0.875rem',
                    lineHeight: '1.5',
                    marginBottom: '0.35rem',
                  }}
                >
                  {parseInlineStyles(itemText)}
                </li>
              ))}
            </ul>
          );
          currentList = [];
        }
      };

      lines.forEach((line, lineIdx) => {
        const trimmedLine = line.trim();
        const key = `part-${index}-line-${lineIdx}`;

        if (trimmedLine.startsWith('### ')) {
          flushParagraph(key);
          flushList(key);
          renderedElements.push(
            <h5
              key={`h5-${key}`}
              style={{
                fontSize: '0.95rem',
                fontWeight: 600,
                color: 'var(--color-secondary, #00D4AA)',
                marginTop: '1.25rem',
                marginBottom: '0.5rem',
                letterSpacing: '0.3px',
              }}
            >
              {parseInlineStyles(trimmedLine.replace('### ', ''))}
            </h5>
          );
        } else if (trimmedLine.startsWith('## ')) {
          flushParagraph(key);
          flushList(key);
          renderedElements.push(
            <h4
              key={`h4-${key}`}
              style={{
                fontSize: '1.1rem',
                fontWeight: 600,
                color: 'var(--color-primary, #6C63FF)',
                marginTop: '1.5rem',
                marginBottom: '0.75rem',
                letterSpacing: '0.4px',
              }}
            >
              {parseInlineStyles(trimmedLine.replace('## ', ''))}
            </h4>
          );
        } else if (trimmedLine.startsWith('# ')) {
          flushParagraph(key);
          flushList(key);
          renderedElements.push(
            <h3
              key={`h3-${key}`}
              style={{
                fontSize: '1.25rem',
                fontWeight: 700,
                color: 'var(--color-text, #F1F1F6)',
                marginTop: '1.75rem',
                marginBottom: '0.75rem',
              }}
            >
              {parseInlineStyles(trimmedLine.replace('# ', ''))}
            </h3>
          );
        } else if (trimmedLine.startsWith('- ') || trimmedLine.startsWith('* ')) {
          flushParagraph(key);
          currentList.push(trimmedLine.replace(/^[-*]\s+/, ''));
        } else if (!trimmedLine) {
          flushParagraph(key);
          flushList(key);
        } else {
          flushList(key);
          currentParagraph.push(trimmedLine);
        }
      });

      // Flush any remaining blocks
      const finalKey = `part-${index}-final`;
      flushParagraph(finalKey);
      flushList(finalKey);
    }
  });

  return <div className="formatted-summary">{renderedElements}</div>;
}

function formatMathText(math) {
  if (!math) return '';
  let formatted = math;
  // 1. Remove \left and \right prefixes for parens first to avoid prefix conflicts
  formatted = formatted.replace(/\\left\(/g, '(').replace(/\\right\)/g, ')');
  formatted = formatted.replace(/\\left\[/g, '[').replace(/\\right\]/g, ']');
  formatted = formatted.replace(/\\left\{/g, '{').replace(/\\right\}/g, '}');
  // 2. Replace \text{...} with just ...
  formatted = formatted.replace(/\\text\{([^}]+)\}/g, '$1');
  // 3. Replace \sqrt{...} with √($1)
  formatted = formatted.replace(/\\sqrt\{([^}]+)\}/g, '√($1)');
  // 4. Replace \frac{A}{B} with A/B
  formatted = formatted.replace(/\\frac\{([^}]+)\}\{([^}]+)\}/g, '$1 / $2');
  // 5. Replace symbols using negative lookahead to prevent prefix matching (e.g. matching \le in \left)
  formatted = formatted.replace(/\\le(q)?(?![a-zA-Z])/g, '≤');
  formatted = formatted.replace(/\\ge(q)?(?![a-zA-Z])/g, '≥');
  formatted = formatted.replace(/\\times(?![a-zA-Z])/g, '×');
  formatted = formatted.replace(/\\approx(?![a-zA-Z])/g, '≈');
  formatted = formatted.replace(/\\neq(?![a-zA-Z])/g, '≠');
  formatted = formatted.replace(/\\pm(?![a-zA-Z])/g, '±');
  formatted = formatted.replace(/\\cdot(?![a-zA-Z])/g, '·');
  formatted = formatted.replace(/\\div(?![a-zA-Z])/g, '÷');
  formatted = formatted.replace(/\\in(?![a-zA-Z])/g, '∈');
  
  // Greek letters & math operators
  formatted = formatted.replace(/\\sum(?![a-zA-Z])/g, '∑');
  formatted = formatted.replace(/\\prod(?![a-zA-Z])/g, '∏');
  formatted = formatted.replace(/\\int(?![a-zA-Z])/g, '∫');
  formatted = formatted.replace(/\\theta(?![a-zA-Z])/g, 'θ');
  formatted = formatted.replace(/\\alpha(?![a-zA-Z])/g, 'α');
  formatted = formatted.replace(/\\beta(?![a-zA-Z])/g, 'β');
  formatted = formatted.replace(/\\gamma(?![a-zA-Z])/g, 'γ');
  formatted = formatted.replace(/\\delta(?![a-zA-Z])/g, 'δ');
  formatted = formatted.replace(/\\epsilon(?![a-zA-Z])/g, 'ε');
  formatted = formatted.replace(/\\lambda(?![a-zA-Z])/g, 'λ');
  formatted = formatted.replace(/\\mu(?![a-zA-Z])/g, 'μ');
  formatted = formatted.replace(/\\pi(?![a-zA-Z])/g, 'π');
  formatted = formatted.replace(/\\sigma(?![a-zA-Z])/g, 'σ');
  formatted = formatted.replace(/\\omega(?![a-zA-Z])/g, 'ω');
  formatted = formatted.replace(/\\phi(?![a-zA-Z])/g, 'φ');
  formatted = formatted.replace(/\\Sigma(?![a-zA-Z])/g, 'Σ');
  formatted = formatted.replace(/\\Delta(?![a-zA-Z])/g, 'Δ');
  formatted = formatted.replace(/\\Theta(?![a-zA-Z])/g, 'Θ');
  formatted = formatted.replace(/\\infty(?![a-zA-Z])/g, '∞');
  formatted = formatted.replace(/\\to(?![a-zA-Z])/g, '→');
  formatted = formatted.replace(/\\partial(?![a-zA-Z])/g, '∂');

  // 6. Remove spacing commands like \!, \, , \;, \:
  formatted = formatted.replace(/\\[!,;:]/g, '');
  // 7. Simplify subscripts like _{word} to just _word
  formatted = formatted.replace(/_\{([^}]+)\}/g, '_$1');
  // 8. Simplify superscripts like ^{word} to just ^word
  formatted = formatted.replace(/\^\{([^}]+)\}/g, '^$1');
  
  return formatted.trim();
}

function parseInlineStyles(text) {
  if (!text) return '';

  let parts = [{ type: 'text', content: text }];

  // 1. Bold (**text**)
  parts = splitByRegex(parts, /\*\*([^*]+)\*\*/g, (match, content) => (
    <strong key={match} style={{ color: 'var(--color-text)', fontWeight: 600 }}>{content}</strong>
  ));

  // 2. Italic (*text*)
  parts = splitByRegex(parts, /\*([^*]+)\*/g, (match, content) => (
    <em key={match} style={{ fontStyle: 'italic' }}>{content}</em>
  ));

  // 3. Inline LaTeX (\(...\) or $...$)
  parts = splitByRegex(parts, /\\\(([\s\S]+?)\\\)/g, (match, content) => (
    <code key={match} className="math-inline" style={{ fontFamily: 'var(--font-mono, monospace)', fontSize: '0.8125rem', padding: '0.15rem 0.35rem', background: 'rgba(255,255,255,0.06)', borderRadius: '4px', color: '#00D4AA', wordBreak: 'break-word', whiteSpace: 'pre-wrap' }}>{formatMathText(content)}</code>
  ));
  parts = splitByRegex(parts, /\$([^$\n]+?)\$/g, (match, content) => (
    <code key={match} className="math-inline" style={{ fontFamily: 'var(--font-mono, monospace)', fontSize: '0.8125rem', padding: '0.15rem 0.35rem', background: 'rgba(255,255,255,0.06)', borderRadius: '4px', color: '#00D4AA', wordBreak: 'break-word', whiteSpace: 'pre-wrap' }}>{formatMathText(content)}</code>
  ));

  // 4. Block LaTeX (\[...\])
  parts = splitByRegex(parts, /\\\[([\s\S]+?)\\\]/g, (match, content) => (
    <div key={match} className="math-block" style={{ display: 'block', textAlign: 'center', margin: '0.75rem 0', padding: '0.75rem', fontFamily: 'var(--font-mono, monospace)', fontSize: '0.875rem', background: 'rgba(255,255,255,0.03)', borderRadius: '6px', borderLeft: '3px solid var(--color-primary)', color: '#00D4AA', overflowX: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>{formatMathText(content)}</div>
  ));

  return parts.map(p => p.type === 'text' ? p.content : p.element);
}

function splitByRegex(parts, regex, elementCreator) {
  const result = [];

  parts.forEach(part => {
    if (part.type !== 'text') {
      result.push(part);
      return;
    }

    let lastIndex = 0;
    let match;
    regex.lastIndex = 0;

    while ((match = regex.exec(part.content)) !== null) {
      const matchIndex = match.index;
      const matchedString = match[0];
      const captureGroup = match[1];

      if (matchIndex > lastIndex) {
        result.push({
          type: 'text',
          content: part.content.substring(lastIndex, matchIndex)
        });
      }

      result.push({
        type: 'element',
        element: elementCreator(matchedString, captureGroup)
      });

      lastIndex = regex.lastIndex;
    }

    if (lastIndex < part.content.length) {
      result.push({
        type: 'text',
        content: part.content.substring(lastIndex)
      });
    }
  });

  return result;
}
