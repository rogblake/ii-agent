# Academic & Technical Domain

Clean, structured, evidence-based design for research papers, technical documentation, and scholarly content.

## Design Philosophy

Clarity enables understanding. Design should:
- Prioritize readability above all else
- Support deep, focused reading
- Present evidence systematically
- Maintain scholarly credibility

## Color System

```css
/* Foundation - Maximum readability */
--background: #FFFFFE;        /* Pure white with warmth */
--surface: #F8F9FA;           /* Subtle gray for cards */
--border: #DEE2E6;

/* Text - High contrast */
--text-primary: #212529;
--text-secondary: #495057;
--text-tertiary: #6C757D;

/* Accent - Scholarly, subdued */
--primary: #0D6EFD;           /* Link blue */
--primary-dark: #0A58CA;
--accent: #6C757D;            /* Neutral accent */

/* Semantic */
--note: #0DCAF0;              /* Info callouts */
--warning: #FFC107;           /* Cautions */
--important: #DC3545;         /* Critical notes */

/* Code */
--code-bg: #F8F9FA;
--code-border: #DEE2E6;
```

## Typography

### Font Stack

```css
/* Primary - Optimized for long-form reading */
--font-body: 'Source Serif Pro', 'Georgia', serif;
/* OR for technical docs */
--font-body: 'IBM Plex Sans', 'Source Sans Pro', sans-serif;

/* Headings */
--font-heading: 'Source Sans Pro', sans-serif;

/* Code */
--font-mono: 'JetBrains Mono', 'Fira Code', monospace;
```

### Type Scale

```css
/* Academic reading optimized */
.body {
  font-size: 1.125rem;        /* 18px - easier on eyes */
  line-height: 1.8;           /* Generous leading */
  max-width: 70ch;            /* Optimal line length */
}

/* Headings - Clear hierarchy */
.h1 { font-size: 2.5rem; font-weight: 700; margin-top: 3rem; }
.h2 { font-size: 1.875rem; font-weight: 600; margin-top: 2.5rem; }
.h3 { font-size: 1.5rem; font-weight: 600; margin-top: 2rem; }
.h4 { font-size: 1.25rem; font-weight: 600; margin-top: 1.5rem; }

/* Abstract/Summary */
.abstract {
  font-size: 1rem;
  font-style: italic;
  color: var(--text-secondary);
  border-left: 3px solid var(--primary);
  padding-left: 1.5rem;
}
```

## Layout Patterns

### Title Section

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│           A Comprehensive Analysis of Large                 │
│           Language Model Architectures                      │
│                                                             │
│           ─────────────────────────────                     │
│                                                             │
│           Dr. Jane Smith¹, Prof. John Doe²                  │
│           ¹MIT, ²Stanford University                        │
│                                                             │
│           Published: January 2024                           │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  ABSTRACT                                                   │
│                                                             │
│  This paper presents a comprehensive analysis of modern     │
│  large language model architectures, examining their        │
│  computational efficiency, scaling properties, and          │
│  emergent capabilities...                                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Two-Column Layout (Wide Screens)

```
┌─────────────────────────────────┬───────────────────────────┐
│                                 │                           │
│   Main Content                  │   Sidebar                 │
│   ────────────                  │   ───────                 │
│                                 │                           │
│   Body text flows here with    │   • Table of Contents     │
│   optimal line length for      │   • Key Definitions       │
│   sustained reading...         │   • Quick References      │
│                                 │   • Related Work          │
│                                 │                           │
└─────────────────────────────────┴───────────────────────────┘
```

### Figure/Table Layout

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│                    [FIGURE/CHART]                           │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  Figure 1: Attention mechanism performance across model     │
│  sizes. Error bars represent 95% confidence intervals.      │
│  Source: Author's experiments (n=1000).                     │
└─────────────────────────────────────────────────────────────┘
```

## Component Patterns

### Abstract Box

```tsx
<div className="my-8 border-l-4 border-blue-500 pl-6">
  <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-500 mb-2">
    Abstract
  </h2>
  <p className="text-gray-700 italic leading-relaxed">
    {abstract}
  </p>
</div>
```

### Citation Block

```tsx
<blockquote className="my-6 pl-6 border-l-2 border-gray-300">
  <p className="text-gray-700 italic">
    "The transformer architecture has fundamentally changed how we approach
    sequence modeling tasks."
  </p>
  <footer className="mt-2 text-sm text-gray-500">
    — Vaswani et al., 2017
  </footer>
</blockquote>
```

### Definition Box

```tsx
<div className="my-6 bg-gray-50 border border-gray-200 rounded-lg p-4">
  <p className="text-sm font-semibold text-gray-900 mb-1">
    Definition: Attention Mechanism
  </p>
  <p className="text-gray-600">
    A component that allows the model to focus on relevant parts of the input
    when producing each part of the output.
  </p>
</div>
```

### Equation Display

```tsx
<div className="my-8 py-4 bg-gray-50 rounded-lg text-center overflow-x-auto">
  <span className="text-gray-500 text-sm absolute left-4">(1)</span>
  {/* KaTeX or MathJax rendered equation */}
  <span className="font-mono text-lg">
    Attention(Q, K, V) = softmax(QK^T / √d_k)V
  </span>
</div>
```

### Code Block

```tsx
<div className="my-6 rounded-lg overflow-hidden border border-gray-200">
  <div className="bg-gray-100 px-4 py-2 text-xs font-mono text-gray-600 border-b border-gray-200">
    algorithm.py
  </div>
  <pre className="bg-gray-50 p-4 overflow-x-auto">
    <code className="text-sm font-mono">
      {code}
    </code>
  </pre>
</div>
```

### Table of Contents

```tsx
<nav className="sticky top-4 p-4 bg-gray-50 rounded-lg">
  <p className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-3">
    Contents
  </p>
  <ul className="space-y-2 text-sm">
    <li>
      <a href="#intro" className="text-gray-600 hover:text-blue-600">
        1. Introduction
      </a>
    </li>
    <li>
      <a href="#methods" className="text-gray-600 hover:text-blue-600">
        2. Methodology
      </a>
    </li>
    {/* Active state */}
    <li>
      <a href="#results" className="text-blue-600 font-medium">
        3. Results
      </a>
    </li>
  </ul>
</nav>
```

## Data Visualization

### Scientific Charts

- Use **minimal chart chrome** — no 3D, gradients, or decorations
- Always include **error bars** where applicable
- Label axes clearly with **units**
- Use **figure numbers** and descriptive captions
- Prefer **grayscale-friendly** palettes

```css
/* Scientific color palette */
--chart-1: #2563EB;  /* Primary data */
--chart-2: #DC2626;  /* Comparison/contrast */
--chart-3: #059669;  /* Third series */
--chart-4: #7C3AED;  /* Fourth series */
--chart-baseline: #9CA3AF;  /* Baseline/reference */
```

### Table Design

```tsx
<table className="w-full text-sm">
  <caption className="text-left text-gray-600 mb-2">
    Table 1: Model performance comparison across benchmarks
  </caption>
  <thead>
    <tr className="border-b-2 border-gray-900">
      <th className="text-left py-2 font-semibold">Model</th>
      <th className="text-right py-2 font-semibold">Params</th>
      <th className="text-right py-2 font-semibold">Accuracy (%)</th>
      <th className="text-right py-2 font-semibold">F1 Score</th>
    </tr>
  </thead>
  <tbody className="divide-y divide-gray-200">
    {/* Highlight best result */}
    <tr className="bg-blue-50">
      <td className="py-2 font-medium">Our Method</td>
      <td className="py-2 text-right font-mono">125M</td>
      <td className="py-2 text-right font-mono font-semibold">94.2</td>
      <td className="py-2 text-right font-mono">0.923</td>
    </tr>
  </tbody>
</table>
```

## Animation Guidelines

**Minimal to none** — academic content prioritizes reading:

| Element | Animation |
|---------|-----------|
| Page load | Simple fade-in (0.3s) |
| Section navigation | Smooth scroll |
| Figures | None (instant render) |
| Interactive elements | Subtle hover states only |

## Content Structure

1. **Title & Authors**
2. **Abstract**
3. **Table of Contents** (sidebar)
4. **Introduction**
5. **Background/Related Work**
6. **Methodology**
7. **Results**
8. **Discussion**
9. **Conclusion**
10. **References**
11. **Appendices**

## Accessibility

- **Focus indicators** — clear for keyboard navigation
- **Heading hierarchy** — semantic HTML (h1 → h2 → h3)
- **Alt text for figures** — describe the insight, not just content
- **High contrast** — minimum 4.5:1 for body text
- **Responsive tables** — horizontal scroll on mobile

## Don'ts

- Parallax or distracting scroll effects
- Dark mode (reduces reading comfort)
- Centered body text
- Small font sizes (< 16px body)
- Missing citations/sources
- **Text-only pages** — use diagrams, figures, and imagery to break up dense content
