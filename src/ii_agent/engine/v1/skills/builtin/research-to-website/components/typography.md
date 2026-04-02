# Typography System

Principles for selecting and applying typography in research-to-website projects.

## Typography Philosophy

Typography is the voice of your content. Before selecting fonts, understand:
- **Who is the audience?** (Professional, consumer, academic, creative)
- **What is the content's tone?** (Authoritative, friendly, innovative, serious)
- **What domain does this serve?** (Business, creative, data, academic)

**Critical Rule**: Never default to common fonts without reasoning. Every font choice should match the content's character.

---

## Font Selection Framework

### Step 1: Define the Personality

Ask yourself what the typography should communicate:

| Personality | Font Direction |
|-------------|----------------|
| **Authoritative** | Serif with weight, structured sans-serif |
| **Innovative/Modern** | Geometric sans-serif, clean lines |
| **Friendly/Approachable** | Humanist sans-serif, rounded forms |
| **Elegant/Premium** | Refined serif, high contrast |
| **Technical/Precise** | Monospace elements, structured sans |
| **Editorial/Storytelling** | Serif display, expressive pairings |

### Step 2: Consider the Content Type

| Content Type | Typography Needs |
|--------------|------------------|
| **Data-heavy** | Clear hierarchy, monospace for numbers |
| **Long-form reading** | Comfortable body font, good x-height |
| **Headlines-first** | Distinctive display font |
| **Technical/Code** | Monospace with ligature support |
| **Marketing** | Expressive display, readable body |

### Step 3: Match the Domain

| Domain | Typography Character |
|--------|---------------------|
| **Business/Financial** | Conservative, trustworthy, clear |
| **Academic/Technical** | Readable, scholarly, precise |
| **Marketing/Creative** | Expressive, distinctive, bold |
| **Data/Analytics** | Clean, precise, number-optimized |
| **Government/Policy** | Accessible, neutral, authoritative |

---

## Font Pairing Principles

### The Core Pairing

Most websites need 2-3 fonts:

1. **Display/Heading**: Personality, impact, distinctiveness
2. **Body**: Readability, comfort, neutrality
3. **Monospace** (if needed): Data, code, precision

### Pairing Strategies

| Strategy | How It Works | Best For |
|----------|--------------|----------|
| **Contrast** | Serif + Sans-serif | Editorial, professional |
| **Superfamily** | Same family, different weights | Cohesive, modern |
| **Similar x-height** | Fonts with matching proportions | Visual harmony |
| **Mood match** | Both fonts share the same spirit | Unified brand feel |

### Pairing Questions

Before finalizing pairings, ask:
- Do these fonts look intentional together, or random?
- Can I tell them apart at a glance? (Hierarchy)
- Do they share similar "DNA" (proportions, curves)?
- Does the combination match the content's mood?

---

## Type Scale Principles

### Building Hierarchy

Use size, weight, and spacing to create clear hierarchy:

```
Display (Hero)     → Largest, boldest, most distinctive
H1 (Page Title)    → Large, bold, commands attention
H2 (Section)       → Medium-large, clear section breaks
H3 (Subsection)    → Medium, groups content
Body               → Comfortable reading size
Small/Caption      → Smaller, for metadata and labels
```

### Scale Ratios

Choose a ratio that matches the content's energy:

| Ratio | Character | Best For |
|-------|-----------|----------|
| **1.125 (Major Second)** | Subtle, tight | Dense data, compact layouts |
| **1.2 (Minor Third)** | Balanced | General purpose, professional |
| **1.25 (Major Third)** | Clear | Most websites, good default |
| **1.333 (Perfect Fourth)** | Spacious | Editorial, storytelling |
| **1.5 (Perfect Fifth)** | Dramatic | Bold, creative layouts |

### Fluid Typography

Use fluid sizing that scales between viewport sizes:
- Define minimum and maximum sizes
- Content should be readable on all devices
- Headlines can scale more dramatically than body

---

## Readability Principles

### Line Length (Measure)

- **Optimal**: 50-75 characters per line
- **Acceptable**: 45-90 characters
- **Too long**: Reader loses place returning to new line
- **Too short**: Constant eye movement, choppy reading

### Line Height (Leading)

| Text Type | Line Height Range |
|-----------|-------------------|
| **Headlines** | 1.0 - 1.2 (tight) |
| **Subheadings** | 1.2 - 1.4 |
| **Body text** | 1.5 - 1.8 (comfortable) |
| **Small text** | 1.4 - 1.6 |

### Letter Spacing (Tracking)

| Context | Spacing Direction |
|---------|-------------------|
| **Large headlines** | Tighten slightly (negative) |
| **Body text** | Default (no adjustment) |
| **All-caps labels** | Loosen (positive) for readability |
| **Monospace numbers** | Default, ensure alignment |

---

## Weight Usage

### Weight Hierarchy

Don't just change size—use weight strategically:

| Weight | Usage |
|--------|-------|
| **Bold/Black (700-900)** | Primary headlines, key emphasis |
| **Semibold (600)** | Section headers, important labels |
| **Medium (500)** | Subheadings, button text, emphasis |
| **Regular (400)** | Body text, descriptions |
| **Light (300)** | Large display text only (creative contexts) |

### Weight Pairing Rules

- **Maximum 3 weights** from one family (too many = chaos)
- **Reserve bold** for true emphasis (overuse weakens it)
- **Light weights** only work at large sizes
- **Contrast matters**: Distinguish heading from body

---

## Numeric Typography

### When Numbers Matter

For data-heavy content, numbers need special attention:

1. **Use tabular figures** (`font-variant-numeric: tabular-nums`)
   - Aligns numbers in columns
   - Essential for tables, metrics, charts

2. **Monospace for key metrics**
   - Creates visual distinction
   - Signals "this is important data"

3. **Size hierarchy for numbers**
   - Hero metrics: Largest, boldest
   - Supporting data: Medium
   - Inline references: Same as body

### Number Formatting

- **Currency**: Symbol slightly smaller, number prominent
- **Percentages**: % symbol often smaller than number
- **Large numbers**: Use separators (1,234,567 or 1.2M)

---

## Domain-Specific Guidance

### Business & Financial
- **Character**: Professional, trustworthy, conservative
- **Headlines**: Strong but not flashy
- **Body**: Highly readable, neutral
- **Numbers**: Must feel precise and credible

### Academic & Technical
- **Character**: Scholarly, serious, clear
- **Headlines**: Structured, authoritative
- **Body**: Optimized for long-form reading
- **Math/Code**: Proper monospace support

### Marketing & Creative
- **Character**: Expressive, distinctive, memorable
- **Headlines**: Can be bold, unusual, artistic
- **Body**: Still readable, but personality permitted
- **Flexibility**: More room for experimentation

### Data & Analytics
- **Character**: Clean, precise, functional
- **Headlines**: Clear but secondary to data
- **Body**: Efficient, gets out of the way
- **Numbers**: First-class citizens, prominent

### Government & Policy
- **Character**: Accessible, neutral, authoritative
- **Headlines**: Clear, not intimidating
- **Body**: Maximum readability for diverse audiences
- **Accessibility**: Must work for everyone

---

## Responsive Typography

### Mobile Considerations

- **Increase body size** slightly on mobile (relative to desktop)
- **Reduce headline scale** (less dramatic jumps)
- **Increase line height** for touch scrolling
- **Ensure tap targets** in interactive text

### Desktop Considerations

- **Don't let lines get too long** (max-width on content)
- **Scale headlines** more dramatically
- **Consider viewport-based sizing** for hero elements

---

## Common Mistakes to Avoid

| Mistake | Why It Fails | Instead |
|---------|--------------|---------|
| Too many fonts | Visual chaos | Maximum 2-3 fonts |
| Inconsistent sizing | Unclear hierarchy | Use defined scale |
| Light fonts on small text | Illegible | Reserve light for large |
| All caps paragraphs | Hard to read | Caps for labels only |
| Ignoring line length | Eye fatigue | Constrain to 50-75 chars |
| Low contrast | Accessibility fail | Test contrast ratios |
| Copying brand fonts blindly | May not fit context | Reason about match |

---

## Decision Checklist

Before finalizing typography:

- [ ] Does the font personality match the content's tone?
- [ ] Is there clear hierarchy (size, weight, spacing)?
- [ ] Can I justify each font choice with a reason?
- [ ] Is body text comfortable for extended reading?
- [ ] Are numbers properly handled (tabular, aligned)?
- [ ] Does it work on mobile and desktop?
- [ ] Have I tested contrast for accessibility?
- [ ] Am I using maximum 2-3 font families?
