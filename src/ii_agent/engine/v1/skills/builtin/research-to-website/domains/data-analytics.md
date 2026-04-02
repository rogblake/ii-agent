# Data & Analytics Domain

Interactive, chart-heavy, insight-driven design for data-rich research. Optimized for fundraising, investor presentations, and high-stakes decision-making contexts.

## Design Philosophy

Data is the hero. Every visualization should:
- Tell a story, not just display numbers
- Guide the eye to the insight first, details second
- Build credibility through precision and clarity
- Create emotional impact through well-timed reveals

---

## Color Strategy

### Principle: Color Serves Clarity

In data visualization, color is a **functional tool**, not decoration. Every color choice should enhance understanding.

### Color Selection Framework

When choosing a palette for data content, reason through:

1. **What is the data's emotional context?**
   - Financial/Investment → Trust, stability, growth (consider blues, greens)
   - Scientific/Research → Objectivity, precision (consider neutral bases with clear accents)
   - Performance/Metrics → Achievement, progress (consider warm accents for positive)

2. **What relationships must be shown?**
   - Good vs. Bad → Need semantic colors (typically green/red or blue/orange)
   - Categories → Need distinct, differentiable hues
   - Sequential data → Need single-hue progressions (light to dark)
   - Comparison → Need contrasting but harmonious pairs

3. **What is the brand/industry context?**
   - Research any relevant brand colors
   - Consider industry conventions (finance often uses conservative palettes)

### Palette Architecture

Build your palette in layers:

| Layer | Purpose | Selection Criteria |
|-------|---------|-------------------|
| **Background** | Canvas for data | Light, neutral, low saturation (reduces eye strain) |
| **Text** | Labels, annotations | High contrast with background, hierarchy through weight not color |
| **Primary** | Main data series, CTAs | Confident, professional, accessible |
| **Semantic** | Good/bad, up/down | Universally understood (green/red, or blue/orange for colorblind safety) |
| **Data Series** | Multiple categories | Perceptually distinct, colorblind-safe |

### Data Visualization Palette Principles

#### Categorical Data (Distinct Groups)

- Maximum 6-7 colors for clarity
- Must be distinguishable to colorblind users
- Vary both hue AND value for accessibility
- Test with colorblind simulators

#### Sequential Data (Ordered Values)

- Single hue, varying lightness
- Darker = higher value (or lighter, but be consistent)
- 5-7 steps maximum for human perception

#### Diverging Data (Positive/Negative)

- Two hues meeting at neutral
- Clear midpoint (often gray or white)
- Equal visual weight on both sides

---

## Typography

### Font Selection Reasoning

Data typography must balance **precision** and **readability**:

1. **Numbers**: Use monospace or tabular figures for alignment
2. **Labels**: Sans-serif for clarity at small sizes
3. **Headlines**: Can have more personality, but still professional
4. **Body**: Highly readable, good x-height

### Type Hierarchy for Data

| Element | Characteristics | Purpose |
|---------|-----------------|---------|
| **Hero Metric** | Large, monospace, bold | Immediate impact |
| **Section Metric** | Medium, monospace, semibold | Supporting data |
| **Chart Labels** | Small, uppercase, tracking | Structure, scannability |
| **Body** | Standard, high line-height | Extended explanation |

### Numeric Typography

```css
/* Key principles for data typography */
.metric {
  font-variant-numeric: tabular-nums; /* Align numbers in columns */
  letter-spacing: -0.02em;            /* Tighten for visual density */
}

.percentage::after {
  content: '%';
  font-size: 0.6em;                   /* Smaller unit indicators */
  vertical-align: super;
}
```

---

## Layout Patterns

### Metrics Grid

Lead with key numbers. Arrange by importance, not symmetry.

```
┌─────────────────────────────────────────────────────────────┐
│                 PRIMARY METRIC                               │
│              [Large Number]                                  │
│            [Context/Change]                                  │
└─────────────────────────────────────────────────────────────┘

┌──────────────┬──────────────┬──────────────┐
│   METRIC 1   │   METRIC 2   │   METRIC 3   │
│   [Number]   │   [Number]   │   [Number]   │
│   [Label]    │   [Label]    │   [Label]    │
└──────────────┴──────────────┴──────────────┘
```

### Chart + Insight Layout

Always lead with the insight, not the chart:

```
┌─────────────────────────────────────────────────────────────┐
│  INSIGHT CALLOUT                                            │
│  "[Key finding stated as a sentence]"                       │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│              [CHART - supporting evidence]                  │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│  Source | Legend | Additional context                       │
└─────────────────────────────────────────────────────────────┘
```

### Comparison Layout

Visual before/after or us vs. them:

```
┌───────────────────────┬───────────────────────┐
│       BEFORE          │        AFTER          │
│   [Muted visual]      │   [Vibrant visual]    │
│      [Value]          │       [Value]         │
└───────────────────────┴───────────────────────┘
                   [Delta indicator]
```

---

## Chart Design Guidelines

### General Principles

1. **Lead with insight**: Headline above the chart states the takeaway
2. **Minimize chartjunk**: No 3D, excessive gridlines, or decoration
3. **Consistent colors**: Same metric = same color everywhere
4. **Annotate key moments**: Mark important events on timelines
5. **Provide context**: Show targets, benchmarks, prior periods

### Chart Type Selection

| Data Type | Recommended Chart | When to Use |
|-----------|-------------------|-------------|
| Trend over time | Line chart | Revenue, users, growth metrics |
| Part of whole | Donut chart | Market share, allocation |
| Comparison | Horizontal bar | Rankings, feature comparison |
| Distribution | Histogram | User segments, ranges |
| Correlation | Scatter plot | Two-variable relationships |
| Multiple metrics | Combo (line + bar) | Revenue + growth rate |

### Chart Configuration Principles

#### Line Charts

- Remove vertical gridlines (horizontal only, subtle)
- Use area fill with gradient for emphasis (primary series)
- Mark key events with annotated reference lines
- Limit to 3-4 series maximum

#### Bar Charts

- Horizontal for comparisons (easier label reading)
- Highlight the key bar (your product, current period)
- Use subtle colors for secondary data
- Add value labels at bar ends

#### Donut Charts

- Inner radius ~60% of outer (not too thin, not too thick)
- Place key metric in center
- Maximum 5-6 segments (group "other")
- Start from 12 o'clock, sort by size

---

## Metric Card Component

### Design Principles

A metric card should communicate:
1. **What** (label)
2. **How much** (value)
3. **So what** (context/change)

### Structure

```tsx
<div className="metric-card">
  <header>
    <span className="label">{label}</span>
    <Icon />
  </header>

  <div className="value font-mono">
    {formattedValue}
  </div>

  <footer className="change">
    <TrendIndicator direction={changeDirection} />
    <span>{changePercent}%</span>
    <span className="period">{comparisonPeriod}</span>
  </footer>
</div>
```

### Visual Treatment

- Clean background (white or very light neutral)
- Subtle border or shadow for definition
- Number should be largest element
- Change indicator uses semantic colors
- Icon optional, adds visual interest

---

## Interactive Elements

### Hover Tooltips

Rich tooltips provide context without cluttering the chart:

```tsx
<Tooltip content={({ payload }) => (
  <div className="tooltip">
    <div className="date">{payload.date}</div>
    <div className="value font-mono">{payload.value}</div>
    <div className="context">
      {payload.changeVsPrior}% vs prior month
    </div>
  </div>
)} />
```

### Data Filters

Allow users to explore different views:
- Time period selectors (All Time, 1Y, YTD, Q4)
- Segment toggles (by region, product, cohort)
- Comparison toggles (show/hide benchmarks)

Design as segmented controls or tabs, not dropdowns (visible options reduce friction).

---

## Animation Strategy

### Purpose-Driven Animation

Every animation should serve understanding:

| Animation | Purpose | When to Use |
|-----------|---------|-------------|
| **Count-up** | Create impact, draw attention | Hero metrics, key numbers |
| **Line draw** | Show progression, journey | Growth trends, timelines |
| **Bar grow** | Reveal comparisons gradually | Rankings, comparisons |
| **Stagger reveal** | Build understanding step-by-step | Metric grids, lists |

### Animation Timing

| Element | Trigger | Delay | Duration |
|---------|---------|-------|----------|
| Section container | 20% in viewport | 0s | 0.6s |
| Metric cards | Container visible | 0.1s stagger | 0.4s each |
| Numbers (count-up) | Card 50% visible | 0.2s | 1.5s |
| Charts | Card visible | 0.3s | 1.2s |

### Count-Up Animation

```tsx
// Animate numbers for impact
<AnimatedNumber
  value={value}
  duration={1.5}
  formatValue={(n) => formatCurrency(n)}
/>
```

### Chart Animations

- **Lines**: Draw from left to right (shows progression)
- **Bars**: Grow from axis (reveals magnitude)
- **Donut**: Sweep clockwise from 12 o'clock
- **Annotations**: Fade in after chart completes

---

## Fundraising-Specific Patterns

### The Traction Dashboard

Top-of-page section for key metrics:

1. **Primary Metric** (largest): ARR/Revenue with growth indicator
2. **Supporting Metrics** (3-4 cards): Customers, Retention, Unit Economics
3. **Trend Chart**: Below metrics showing trajectory
4. **Milestone Markers**: Funding rounds, product launches on timeline

### The Growth Trajectory

Line chart that tells the fundraising story:

1. Mark funding rounds on timeline (annotated reference lines)
2. Annotate product milestones that drove inflection points
3. Show projection line (dashed) for future trajectory
4. Use gradient fill under line for visual weight

### The Comparison Story

Before/After or Us vs. Competitors:

- Use muted/desaturated colors for "before" or competitors
- Use vibrant/saturated colors for "after" or your product
- Animate the delta between them
- State the comparison as a headline

### Key Metrics Callout

For maximum impact on critical numbers:

```
┌─────────────────────────────────────────────────────────────┐
│  "We've grown revenue [X]x in [time period]                 │
│   while maintaining [Y]% gross margins"                     │
│                                                             │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐              │
│  │  [Value]   │ │  [Value]   │ │  [Value]   │              │
│  │   [Label]  │ │   [Label]  │ │   [Label]  │              │
│  └────────────┘ └────────────┘ └────────────┘              │
└─────────────────────────────────────────────────────────────┘
```

---

## Trust Signals

Data credibility requires:

1. **Source citations**: Always attribute data sources
2. **Dates**: Show when data was collected
3. **Methodology notes**: Brief explanation where relevant
4. **Clear labels**: No ambiguous abbreviations
5. **Professional presentation**: No chartjunk, clean typography

---

## Background Strategy

### Data-First Backgrounds

Keep backgrounds **quiet** so data can shine:

| Section | Background Approach |
|---------|---------------------|
| Metrics | Clean, light, neutral |
| Charts | White or very light gray |
| Insight callouts | Slightly tinted (brand-adjacent) |
| Comparison sections | Can use contrast (dark for drama) |

Avoid:
- Busy patterns behind data
- Low-contrast backgrounds that reduce readability
- Gradients that interfere with chart colors

---

## Accessibility

1. **Never rely on color alone**: Use patterns, labels, or icons as backup
2. **Test with colorblind tools**: Verify all data series are distinguishable
3. **Provide text alternatives**: Describe chart insights in text
4. **Ensure contrast**: 4.5:1 minimum for labels and values
5. **Keyboard navigation**: Interactive elements must be accessible

---

## Don'ts

- Charts without insight headlines
- Too many data series (max 4-5)
- 3D charts or decorative effects
- Missing axis labels or units
- Inconsistent color meanings
- Animations that delay comprehension
- Dark backgrounds with light charts (reduces trust)
- Specific colors copied without reasoning about context
