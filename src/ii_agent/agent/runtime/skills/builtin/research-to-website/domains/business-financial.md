# Business & Financial Domain

Professional, trustworthy, data-focused design for business reports, financial analysis, and investor-facing content.

## Design Philosophy

Credibility through restraint. Design should:
- Convey authority without arrogance
- Prioritize clarity over decoration
- Use whitespace as a trust signal
- Let data and insights command attention

## Color Strategy

### Principle: Trust Through Restraint

Business content requires conservative, restrained color choices. The goal is to build credibility, not attract attention.

### Color Selection Framework

When choosing colors for business/financial content:

1. **Default to conservative**
   - Neutral backgrounds (white, off-white, very light gray)
   - Deep, stable primary colors (navy, dark blue, charcoal)
   - Minimal accent usage

2. **Research industry context**
   - Finance/Banking → Traditional, authoritative (navy, gold accents)
   - Tech/SaaS → Modern but professional (blue family, subtle violet)
   - Healthcare → Calm, trustworthy (teal, soft blue)
   - Legal → Serious, established (charcoal, deep burgundy)
   - Consulting → Strategic, growth-oriented (navy, green accents)

3. **Match the stakes**
   - Higher stakes (investor materials) → More conservative
   - Internal/operational → Slightly more flexibility
   - Client-facing → Research their brand colors

### Palette Architecture

| Layer | Approach |
|-------|----------|
| **Background** | Light, neutral, maximizes readability |
| **Text** | High contrast hierarchy (near-black → medium gray → light gray) |
| **Primary** | Single confident color (often blue family for trust) |
| **Accent** | Used sparingly, often warmer (gold, amber) for success/emphasis |
| **Semantic** | Standard green/red for positive/negative data |

### Industry Color Associations

| Industry | Primary Direction | Accent Direction | Character |
|----------|-------------------|------------------|-----------|
| Finance/Banking | Deep navy, dark blue | Gold, warm metallics | Traditional authority |
| Tech/SaaS | Bright blue, violet | Purple, electric tones | Modern, innovative |
| Healthcare | Teal, soft blue | Calm blue-greens | Calm, trustworthy |
| Legal | Charcoal, near-black | Deep burgundy, maroon | Serious, established |
| Consulting | Navy, dark blue | Green, emerald | Strategic, growth |

---

## Typography

### Font Selection Principles

Business typography should convey **competence and clarity**:

1. **Sans-serif for modern credibility**: Clean, professional
2. **Serif for traditional authority**: Established, trustworthy
3. **Monospace for data**: Numbers need precision
4. **Match the company's positioning**: Conservative vs. innovative

### Type Scale

```css
/* Headlines - Confident, not shouting */
.h1 { font-size: 3rem; font-weight: 600; letter-spacing: -0.02em; line-height: 1.1; }
.h2 { font-size: 2rem; font-weight: 600; letter-spacing: -0.01em; line-height: 1.2; }
.h3 { font-size: 1.5rem; font-weight: 600; line-height: 1.3; }

/* Body - Highly readable */
.body-lg { font-size: 1.125rem; line-height: 1.7; }
.body { font-size: 1rem; line-height: 1.6; }
.body-sm { font-size: 0.875rem; line-height: 1.5; }

/* Labels - All caps for structure */
.label {
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-tertiary);
}
```

## Layout Patterns

### Executive Summary (Above the Fold)

```
┌─────────────────────────────────────────────────────────────┐
│  [LOGO]                              [CTA: Download Report] │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│           Strategic Analysis: Market Opportunity            │
│                   in Enterprise AI                          │
│                                                             │
│                     Q4 2024 Report                          │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │   $127B     │  │    34%      │  │    2.4x     │         │
│  │   Market    │  │    CAGR     │  │   Multiple  │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
└─────────────────────────────────────────────────────────────┘
```

### Section Structure

```
┌─────────────────────────────────────────────────────────────┐
│  SECTION LABEL                                              │
│  ─────────────                                              │
│                                                             │
│  Section Headline That States                               │
│  the Key Insight Clearly                                    │
│                                                             │
│  Body text that expands on the insight. Keep paragraphs    │
│  short. Use bullet points for scanability.                 │
│                                                             │
│  • First key point                                         │
│  • Second key point                                        │
│  • Third key point                                         │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                                                     │   │
│  │              [SUPPORTING CHART]                     │   │
│  │                                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Source: Company Analysis, 2024                            │
└─────────────────────────────────────────────────────────────┘
```

### Data Table Design

```tsx
// Clean, scannable tables
<table className="w-full">
  <thead>
    <tr className="border-b-2 border-gray-900">
      <th className="text-left py-3 text-xs font-semibold uppercase tracking-wider text-gray-500">
        Metric
      </th>
      <th className="text-right py-3 text-xs font-semibold uppercase tracking-wider text-gray-500">
        2023
      </th>
      <th className="text-right py-3 text-xs font-semibold uppercase tracking-wider text-gray-500">
        2024
      </th>
      <th className="text-right py-3 text-xs font-semibold uppercase tracking-wider text-gray-500">
        Change
      </th>
    </tr>
  </thead>
  <tbody className="divide-y divide-gray-100">
    <tr className="hover:bg-gray-50">
      <td className="py-4 font-medium">Revenue</td>
      <td className="py-4 text-right font-mono">$24.5M</td>
      <td className="py-4 text-right font-mono">$38.2M</td>
      <td className="py-4 text-right font-mono text-emerald-600">+56%</td>
    </tr>
  </tbody>
</table>
```

## Component Patterns

### Key Insight Callout

```tsx
<div className="border-l-4 border-primary bg-primary/5 p-6 my-8">
  <p className="text-xs font-semibold uppercase tracking-wider text-primary mb-2">
    Key Finding
  </p>
  <p className="text-xl font-medium text-gray-900">
    "Enterprise AI spending will reach $127B by 2028, with 67% of growth
    coming from mid-market companies."
  </p>
</div>
```

### Stat Card

```tsx
<div className="bg-white border border-gray-200 rounded-lg p-6">
  <p className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-2">
    Total Addressable Market
  </p>
  <p className="text-4xl font-semibold font-mono text-gray-900">
    $127B
  </p>
  <p className="text-sm text-gray-500 mt-2">
    by 2028 (34% CAGR)
  </p>
</div>
```

### Comparison Block

```tsx
<div className="grid grid-cols-2 gap-8">
  <div className="p-6 bg-gray-50 rounded-lg">
    <p className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-4">
      Traditional Approach
    </p>
    <ul className="space-y-2 text-gray-600">
      <li className="flex items-center gap-2">
        <X className="w-4 h-4 text-red-500" /> Manual processing
      </li>
      <li className="flex items-center gap-2">
        <X className="w-4 h-4 text-red-500" /> 2-3 week turnaround
      </li>
    </ul>
  </div>

  <div className="p-6 bg-primary/5 border border-primary/20 rounded-lg">
    <p className="text-xs font-semibold uppercase tracking-wider text-primary mb-4">
      Our Solution
    </p>
    <ul className="space-y-2 text-gray-900">
      <li className="flex items-center gap-2">
        <Check className="w-4 h-4 text-emerald-500" /> Automated pipeline
      </li>
      <li className="flex items-center gap-2">
        <Check className="w-4 h-4 text-emerald-500" /> Real-time results
      </li>
    </ul>
  </div>
</div>
```

## Animation Guidelines

Keep animations **subtle and purposeful**:

| Element | Animation | Duration |
|---------|-----------|----------|
| Section reveals | Fade + slight rise | 0.6s |
| Metric numbers | Count-up | 1.5s |
| Charts | Progressive draw | 1.2s |
| Hover states | Subtle lift | 0.2s |

**Avoid**: Parallax, aggressive scroll effects, decorative motion.

## Trust Signals

1. **Source citations** — Always attribute data sources
2. **Dates** — Show when data was collected
3. **Methodology notes** — Brief explanation where relevant
4. **Author/Company** — Clear attribution
5. **Professional imagery** — No stock photos; use data viz instead

## Content Hierarchy

1. **Executive Summary** — Key takeaways in first viewport
2. **Metrics Dashboard** — Supporting numbers
3. **Deep Dive Sections** — Detailed analysis
4. **Appendix/Methodology** — For credibility
5. **CTA** — Next steps, contact, download

## Don'ts

- Overly decorative elements
- Dark mode (reduces credibility for financial content)
- Animated backgrounds
- Emoji or informal elements
- Generic stock photography
- Rounded corners > 8px (too casual)
