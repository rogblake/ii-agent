# Design Specification Template

Use this template when creating `design-spec.md` for a research-to-website project.

---

# Design Specification: [Project Title]

## Research Summary

**Source:** [report.md / report.pdf]
**Topic:** [Brief description]
**Key Findings:**
1. [Most important finding]
2. [Second finding]
3. [Third finding]

---

## Domain Classification

| Domain | Weight | Rationale |
|--------|--------|-----------|
| **Primary:** [domain] | 60% | [Why this is the main domain] |
| **Secondary:** [domain] | 30% | [Supporting influence] |
| **Tertiary:** [domain or none] | 10% | [Minor influence, if any] |

---

## Design Direction

**Style:** [e.g., "Data-driven storytelling with investor-grade polish"]

**Mood:** [e.g., "Confident, transparent, forward-looking"]

**Reference Sites:** [Optional - 1-2 similar sites for inspiration]

---

## Color System

### Palette

| Role | Color | Hex | Usage |
|------|-------|-----|-------|
| Background | [name] | `#FAFBFC` | Page background |
| Surface | [name] | `#FFFFFF` | Cards, sections |
| Primary | [name] | `#2563EB` | CTAs, links, emphasis |
| Secondary | [name] | `#059669` | Accents, success |
| Text Primary | [name] | `#111827` | Headlines, key content |
| Text Secondary | [name] | `#4B5563` | Body text |
| Text Tertiary | [name] | `#9CA3AF` | Captions, metadata |

### Data Visualization Palette

```
Chart Colors: [#3B82F6, #059669, #F59E0B, #8B5CF6, #EC4899]
Positive: #059669
Negative: #DC2626
Neutral: #6B7280
```

---

## Typography

### Font Stack

| Role | Font | Fallback |
|------|------|----------|
| Display | [font] | system-ui |
| Headings | [font] | system-ui |
| Body | [font] | system-ui |
| Mono/Data | [font] | monospace |

### Scale

| Element | Size | Weight | Line Height |
|---------|------|--------|-------------|
| H1 (Hero) | 4rem | 700 | 1.1 |
| H2 (Section) | 2.5rem | 600 | 1.2 |
| H3 (Subsection) | 1.5rem | 600 | 1.3 |
| Body | 1.125rem | 400 | 1.7 |
| Caption | 0.875rem | 400 | 1.5 |
| Metric | 3rem | 600 | 1.0 |

---

## Layout Structure

### Section Breakdown

| # | Section | Content | Layout |
|---|---------|---------|--------|
| 1 | Hero | Title, key stat, hook | Full-bleed, centered |
| 2 | Executive Summary | 3-4 key metrics | Grid, 3-4 columns |
| 3 | [Section Name] | [Content description] | [Layout type] |
| 4 | [Section Name] | [Content description] | [Layout type] |
| 5 | [Section Name] | [Content description] | [Layout type] |
| 6 | Conclusion/CTA | Key takeaway, next steps | Centered, emphasized |

### Grid System

```
Container: max-w-7xl (1280px)
Columns: 12-column grid
Gutter: 32px (desktop), 16px (mobile)
Section padding: 80px vertical (desktop), 48px (mobile)
```

---

## Animation Plan

### Scroll Behaviors

| Element | Animation | Trigger | Duration |
|---------|-----------|---------|----------|
| Section reveal | Fade + rise | Enter viewport | 0.6s |
| Metric numbers | Count-up | 50% visible | 1.5s |
| Charts | Progressive draw | 30% visible | 1.2s |
| Cards | Stagger cascade | Enter viewport | 0.1s delay each |

### Transitions

| Transition | Type | Easing |
|------------|------|--------|
| Section to section | Fade | ease-out |
| Color background | Gradient blend | ease-in-out |
| Hover states | Scale + shadow | ease-out, 0.2s |

### Reduced Motion

- All animations have `prefers-reduced-motion` fallback
- Fallback: instant state changes, no motion

---

## Data Visualization Plan

### Charts Required

| # | Chart Type | Data | Purpose |
|---|------------|------|---------|
| 1 | [Line/Bar/Donut/etc.] | [Data series] | [What insight it shows] |
| 2 | [Chart type] | [Data series] | [Insight] |

### Metrics Display

| Metric | Value | Format | Animation |
|--------|-------|--------|-----------|
| [Metric 1] | [value] | [e.g., "$X.XM"] | Count-up |
| [Metric 2] | [value] | [e.g., "XX%"] | Count-up |

### Interactive Elements

- [ ] Time period filters (if applicable)
- [ ] Hover tooltips on charts
- [ ] Data point annotations

---

## Image Requirements

### Hero/Atmospheric

| Image | Description | Style | Size |
|-------|-------------|-------|------|
| Hero | [Description] | [Photo/Illustration/Abstract] | Full-bleed |

### Explanatory

| Image | Purpose | Type |
|-------|---------|------|
| [Image 1] | [What it explains] | [Diagram/Infographic/etc.] |

### Icons

- **Library:** [Lucide / Heroicons / Custom]
- **Style:** [Outlined / Filled / Duotone]
- **Size:** [24px default, 20px inline, 32px feature]

---

## Technical Notes

### Framework & Libraries

```
Framework: Next.js 14 (App Router)
Styling: TailwindCSS + shadcn/ui
Animation: Framer Motion / GSAP + ScrollTrigger
Charts: Recharts / Chart.js
Icons: Lucide React
Fonts: [loaded via next/font or self-hosted]
```

### Performance Targets

- LCP: < 2.5s
- CLS: < 0.1
- FID: < 100ms

### Accessibility

- WCAG 2.1 AA compliance
- Semantic HTML structure
- Keyboard navigation support
- Screen reader tested

---

## Content Mapping

| Report Section | Website Section | Treatment |
|----------------|-----------------|-----------|
| [Report heading 1] | [Website section] | [How it's presented] |
| [Report heading 2] | [Website section] | [How it's presented] |
| [Key data point] | Hero / Metrics | [Prominent display] |

---

## Review Checklist

Before implementation:

- [ ] Color contrast verified (4.5:1 minimum)
- [ ] All required data extracted from report
- [ ] Animation plan respects reduced motion
- [ ] Mobile layout considered
- [ ] Chart types appropriate for data
- [ ] Image requirements clear
- [ ] No generic AI aesthetics (purple gradients, dark mode, etc.)
