# Government & Policy Domain

Formal, accessible, authoritative design for policy documents, public sector content, and civic information.

## Design Philosophy

Accessibility is non-negotiable. Design should:
- Meet WCAG 2.1 AA standards minimum (AAA preferred)
- Communicate clearly to diverse audiences
- Project authority without intimidation
- Prioritize function over aesthetic novelty

## Color System

### Official Palette

```css
/* Foundation - Maximum accessibility */
--background: #FFFFFF;
--surface: #F5F5F5;
--surface-alt: #E8E8E8;
--border: #CCCCCC;

/* Text - High contrast required */
--text-primary: #1A1A1A;       /* 15:1 contrast on white */
--text-secondary: #4D4D4D;     /* 7:1 contrast */
--text-tertiary: #666666;      /* 5.5:1 contrast */

/* Primary - Authoritative blue */
--primary: #1D4E89;            /* Government blue */
--primary-dark: #0F2D52;
--primary-light: #3A6EA5;

/* Secondary - Civic green */
--secondary: #1A5336;
--secondary-light: #2D7A4E;

/* Semantic */
--success: #1A5336;
--warning: #B45309;
--error: #9B1C1C;
--info: #1D4E89;

/* Alert backgrounds (accessible) */
--alert-success-bg: #D1FAE5;
--alert-warning-bg: #FEF3C7;
--alert-error-bg: #FEE2E2;
--alert-info-bg: #DBEAFE;
```

### Agency Branding

When representing a specific agency, use their official colors while maintaining accessibility:

```css
/* Verify all color combinations meet 4.5:1 contrast ratio */
/* Use WebAIM contrast checker */
```

## Typography

### Accessible Font Stack

```css
/* Primary - Government-approved accessible fonts */
--font-body: 'Public Sans', 'Source Sans Pro', 'Helvetica Neue', Arial, sans-serif;
--font-heading: 'Merriweather', 'Georgia', serif;
--font-mono: 'Roboto Mono', 'Courier New', monospace;

/* Font sizes - minimum 16px body */
--text-xs: 0.875rem;   /* 14px - captions only */
--text-sm: 1rem;       /* 16px - minimum body */
--text-base: 1.125rem; /* 18px - preferred body */
--text-lg: 1.25rem;    /* 20px */
--text-xl: 1.5rem;     /* 24px */
--text-2xl: 1.875rem;  /* 30px */
--text-3xl: 2.25rem;   /* 36px */
```

### Type Rules

```css
/* Body text */
.body {
  font-size: var(--text-base);
  line-height: 1.7;
  max-width: 75ch;
}

/* Headings - clear hierarchy */
h1 { font-size: var(--text-3xl); font-weight: 700; margin-bottom: 1rem; }
h2 { font-size: var(--text-2xl); font-weight: 600; margin-top: 2rem; }
h3 { font-size: var(--text-xl); font-weight: 600; margin-top: 1.5rem; }

/* Links - always underlined */
a {
  color: var(--primary);
  text-decoration: underline;
  text-underline-offset: 2px;
}
a:hover {
  text-decoration-thickness: 2px;
}
a:focus {
  outline: 3px solid var(--primary);
  outline-offset: 2px;
}
```

## Layout Patterns

### Standard Page Structure

```
┌─────────────────────────────────────────────────────────────┐
│  [AGENCY LOGO]        [Search]  [Menu]  [Language: EN ▼]   │
├─────────────────────────────────────────────────────────────┤
│  Home > Policies > Environmental > Clean Air Act            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Clean Air Act Overview                                     │
│  ═══════════════════════                                    │
│                                                             │
│  Last Updated: January 15, 2024                            │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ ON THIS PAGE                                        │   │
│  │ • Overview                                          │   │
│  │ • Key Provisions                                    │   │
│  │ • Compliance Requirements                           │   │
│  │ • Resources                                         │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Overview                                                   │
│  ────────                                                   │
│  The Clean Air Act is the comprehensive federal law that   │
│  regulates air emissions from stationary and mobile...     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Alert Banner

```
┌─────────────────────────────────────────────────────────────┐
│  ⚠️ IMPORTANT: New regulations take effect March 1, 2024   │
│     Read the full guidance → [Link]                        │
└─────────────────────────────────────────────────────────────┘
```

### Data Display

```
┌─────────────────────────────────────────────────────────────┐
│  COMPLIANCE STATISTICS                                      │
│                                                             │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐           │
│  │   94.2%     │ │   12,450    │ │    $2.3B    │           │
│  │  Compliance │ │  Inspections│ │  Investment │           │
│  │    Rate     │ │   (2024)    │ │   (Total)   │           │
│  └─────────────┘ └─────────────┘ └─────────────┘           │
│                                                             │
│  Source: EPA Annual Report 2024                            │
└─────────────────────────────────────────────────────────────┘
```

## Component Patterns

### Breadcrumbs

```tsx
<nav aria-label="Breadcrumb" className="text-sm mb-6">
  <ol className="flex items-center gap-2">
    <li>
      <a href="/" className="text-primary underline">Home</a>
    </li>
    <li aria-hidden="true">/</li>
    <li>
      <a href="/policies" className="text-primary underline">Policies</a>
    </li>
    <li aria-hidden="true">/</li>
    <li aria-current="page" className="text-gray-600">
      Clean Air Act
    </li>
  </ol>
</nav>
```

### Alert Box

```tsx
<div
  role="alert"
  className="flex gap-3 p-4 bg-yellow-50 border-l-4 border-yellow-500"
>
  <AlertTriangle className="w-5 h-5 text-yellow-700 flex-shrink-0 mt-0.5" />
  <div>
    <p className="font-semibold text-yellow-900">Important Notice</p>
    <p className="text-yellow-800 mt-1">
      New regulations take effect on March 1, 2024.
      <a href="/guidance" className="underline ml-1">Read the full guidance</a>
    </p>
  </div>
</div>
```

### Accordion (FAQ Pattern)

```tsx
<div className="border border-gray-300 rounded-lg divide-y divide-gray-300">
  {faqs.map((faq, i) => (
    <details key={i} className="group">
      <summary className="flex justify-between items-center p-4 cursor-pointer hover:bg-gray-50">
        <span className="font-medium text-gray-900">{faq.question}</span>
        <ChevronDown className="w-5 h-5 text-gray-500 group-open:rotate-180 transition-transform" />
      </summary>
      <div className="p-4 pt-0 text-gray-700">
        {faq.answer}
      </div>
    </details>
  ))}
</div>
```

### Data Table (Accessible)

```tsx
<div className="overflow-x-auto">
  <table className="w-full border-collapse">
    <caption className="text-left font-semibold text-lg mb-2">
      Emissions Standards by Vehicle Type
    </caption>
    <thead>
      <tr className="bg-gray-100">
        <th scope="col" className="text-left p-3 border border-gray-300">
          Vehicle Type
        </th>
        <th scope="col" className="text-right p-3 border border-gray-300">
          CO₂ Limit (g/mi)
        </th>
        <th scope="col" className="text-right p-3 border border-gray-300">
          Effective Date
        </th>
      </tr>
    </thead>
    <tbody>
      <tr className="hover:bg-gray-50">
        <th scope="row" className="text-left p-3 border border-gray-300 font-normal">
          Passenger Cars
        </th>
        <td className="text-right p-3 border border-gray-300 font-mono">
          163
        </td>
        <td className="text-right p-3 border border-gray-300">
          Jan 1, 2024
        </td>
      </tr>
    </tbody>
  </table>
</div>
```

### Document Download

```tsx
<div className="flex items-center gap-4 p-4 border border-gray-300 rounded-lg hover:bg-gray-50">
  <FileText className="w-8 h-8 text-primary" />
  <div className="flex-1">
    <p className="font-medium text-gray-900">Clean Air Act Summary</p>
    <p className="text-sm text-gray-500">PDF, 2.4 MB, 24 pages</p>
  </div>
  <a
    href="/docs/clean-air-act.pdf"
    download
    className="px-4 py-2 bg-primary text-white rounded hover:bg-primary-dark focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
  >
    Download
  </a>
</div>
```

## Accessibility Requirements

### WCAG 2.1 AA Checklist

- [ ] **Color contrast**: 4.5:1 for normal text, 3:1 for large text
- [ ] **Focus indicators**: Visible on all interactive elements
- [ ] **Keyboard navigation**: All functions accessible via keyboard
- [ ] **Skip links**: "Skip to main content" at page top
- [ ] **Alt text**: All images have descriptive alternatives
- [ ] **Form labels**: All inputs have associated labels
- [ ] **Error identification**: Clear, specific error messages
- [ ] **Language**: `lang` attribute on `<html>`
- [ ] **Headings**: Logical hierarchy (no skipping levels)
- [ ] **Link purpose**: Clear from link text alone

### Skip Link

```tsx
<a
  href="#main-content"
  className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-50 focus:bg-primary focus:text-white focus:px-4 focus:py-2 focus:rounded"
>
  Skip to main content
</a>
```

### Screen Reader Considerations

```tsx
// Announce dynamic content changes
<div aria-live="polite" aria-atomic="true">
  {statusMessage}
</div>

// Hidden text for context
<span className="sr-only">
  (opens in new window)
</span>
```

## Animation Guidelines

**Minimal and purposeful only**:

| Element | Allowed Animation |
|---------|-------------------|
| Page transitions | Fade only (0.2s) |
| Accordions | Height transition (0.3s) |
| Tooltips | Fade (0.15s) |
| Focus states | Immediate |
| Loading states | Spinner or progress bar |

### Reduced Motion Support

```css
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

## Content Guidelines

### Plain Language

- Use short sentences (15-20 words average)
- Avoid jargon; define necessary technical terms
- Use active voice
- Address the reader as "you"
- Use bullet points for lists

### Information Hierarchy

1. **What do I need to know?** (Summary)
2. **What do I need to do?** (Actions)
3. **When do I need to do it?** (Deadlines)
4. **Where can I learn more?** (Resources)

## Don'ts

- Decorative animations
- Auto-playing media
- Infinite scroll
- Color as sole information indicator
- Small fonts (< 16px)
- Low contrast color combinations
- Complex navigation
- PDFs without accessible HTML alternative
- CAPTCHAs without alternatives
