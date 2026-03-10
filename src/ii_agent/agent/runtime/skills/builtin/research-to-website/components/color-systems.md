# Color Systems

Strategic color palette design principles for research-to-website projects.

## Color Philosophy

Color communicates before content is read. It should:
- Establish emotional tone instantly
- Guide visual hierarchy
- Ensure accessibility
- Reinforce domain credibility

**Critical Rule**: Never copy colors blindly. Always reason about WHY a color fits the specific content, audience, and context.

---

## Color Selection Framework

### Step 1: Understand the Content

Ask yourself:

1. **What is the subject matter?**
   - Nature/Environment → Draw from natural palettes
   - Technology/Innovation → Consider cooler, more electric tones
   - Human/Emotional stories → Warmer, more organic palettes
   - Finance/Data → Conservative, trust-building tones
   - Luxury/Premium → Deep, rich, or refined neutrals

2. **What emotional arc does the content follow?**
   - Map the journey: Beginning → Middle → End
   - Each phase may warrant different color temperatures

3. **Who is the audience?**
   - Professional/Business → Conservative, restrained
   - Consumer/Lifestyle → More expressive permitted
   - Academic → Neutral, focused
   - Creative → Bold, distinctive

### Step 2: Research Context

Before selecting colors:

- **Check for brand guidelines**: If a company/organization is mentioned, research their colors
- **Consider industry conventions**: Finance = conservative, Tech = modern, Healthcare = calm
- **Cultural context**: Color meanings vary by culture and region

### Step 3: Build the Palette Architecture

Every palette needs these **functional layers**:

| Layer | Purpose | How to Select |
|-------|---------|---------------|
| **Background** | Canvas for content | Light for trust/readability, dark for drama/focus |
| **Surface** | Cards, sections | Slight variation from background |
| **Text Primary** | Headlines, key info | Maximum contrast with background |
| **Text Secondary** | Body, descriptions | Reduced contrast, still readable |
| **Text Tertiary** | Captions, metadata | Subtle, but accessible |
| **Primary** | CTAs, emphasis, links | Should feel confident and clickable |
| **Accent** | Highlights, moments | Used sparingly for emphasis |
| **Semantic** | Success/Error/Warning | Universally understood meanings |

---

## Color Relationship Principles

### Contrast Hierarchy

Build visual hierarchy through **contrast, not just hue**:

```
Most important  →  Highest contrast (darkest text on lightest bg, or inverse)
Supporting      →  Medium contrast
Tertiary        →  Lower contrast (but still accessible)
```

### Temperature as Narrative

Use warm ↔ cool shifts to create emotional "chapters":

| Warm Colors | Convey | Cool Colors | Convey |
|-------------|--------|-------------|--------|
| Reds, oranges, yellows | Energy, urgency, passion | Blues, greens, purples | Calm, trust, stability |
| Earthy browns, tans | Grounded, natural, authentic | Grays, silvers | Neutral, professional, modern |

### Saturation as Energy

| High Saturation | Effect | Low Saturation | Effect |
|-----------------|--------|----------------|--------|
| Vibrant, energetic | Excitement, action | Muted, sophisticated | Calm, serious |
| Use for CTAs, highlights | Draws attention | Use for backgrounds, body | Reduces visual noise |

### Value (Lightness) as Weight

| Light Values | Effect | Dark Values | Effect |
|--------------|--------|-------------|--------|
| Airy, open, fresh | Approachable, clean | Heavy, grounded, serious | Authoritative, dramatic |
| Good for backgrounds | Maximizes readability | Good for emphasis | Creates visual anchors |

---

## Color Harmony Strategies

Choose based on content needs:

### Monochromatic
- **One hue**, varying lightness and saturation
- **Best for**: Sophisticated, focused content; data-heavy sections
- **Effect**: Cohesive, calm, professional

### Analogous
- **Adjacent hues** on color wheel (e.g., blue-teal-green)
- **Best for**: Harmonious narratives, flowing content
- **Effect**: Natural, comfortable, unified

### Complementary
- **Opposite hues** on color wheel
- **Best for**: High-impact moments, key contrasts
- **Effect**: Energetic, attention-grabbing (use sparingly)

### Split-Complementary
- One hue + two adjacent to its complement
- **Best for**: Dynamic but balanced designs
- **Effect**: Vibrant yet harmonious

### Triadic
- Three equidistant hues
- **Best for**: Playful, energetic content
- **Effect**: Bold, lively (requires careful balance)

---

## Domain-Specific Guidance

### Business & Financial
- **Temperature**: Cool to neutral (builds trust)
- **Saturation**: Low to medium (professional)
- **Approach**: Conservative, restrained, let content lead

### Academic & Technical
- **Temperature**: Neutral to cool
- **Saturation**: Low (reduces distraction)
- **Approach**: Minimal palette, focus on readability

### Marketing & Creative
- **Temperature**: Can vary dramatically (narrative-driven)
- **Saturation**: Higher permitted (expressive)
- **Approach**: Color as storytelling device, shifts between sections

### Data & Analytics
- **Temperature**: Cool primary, semantic accents
- **Saturation**: Controlled (data must be clear)
- **Approach**: Functional first, beauty through clarity

### Government & Policy
- **Temperature**: Neutral to cool
- **Saturation**: Low to medium
- **Approach**: Maximum accessibility, authoritative but not intimidating

---

## Data Visualization Colors

### Categorical Data

For distinct categories (max 6-7):

1. **Vary hue** (different colors)
2. **Also vary value** (light/dark) for colorblind accessibility
3. **Test with colorblind simulators**
4. **Ensure each color is distinguishable in grayscale**

### Sequential Data

For ordered values (low → high):

1. **Single hue**, varying lightness
2. **Darker = higher value** (conventional) OR lighter = higher (if inverted makes sense)
3. **5-7 steps maximum** for human perception

### Diverging Data

For positive/negative or above/below:

1. **Two hues** meeting at neutral center
2. **Clear midpoint** (often white or light gray)
3. **Equal visual weight** on both sides
4. **Consider colorblind-safe pairs** (blue/orange instead of green/red)

### Semantic Colors

For universal meanings:

| Meaning | Common Associations | Colorblind Considerations |
|---------|---------------------|---------------------------|
| Positive/Growth | Green | Pair with upward arrow icon |
| Negative/Decline | Red | Pair with downward arrow icon |
| Warning/Caution | Yellow/Amber | Pair with warning icon |
| Neutral/Unchanged | Gray | Clear labeling |
| Highlight/Attention | Your primary color | Position/size emphasis |

---

## Multi-Color Page Journeys

For creative/narrative content, design color as a **journey**:

### Journey Design Process

1. **Map the narrative arc** (Problem → Solution, Past → Future, etc.)
2. **Assign emotional tones** to each phase
3. **Translate emotions to color temperatures**
4. **Design transitions** between sections

### Common Journey Patterns

| Narrative | Color Flow | Emotional Effect |
|-----------|------------|------------------|
| Problem → Solution | Cool/Muted → Warm/Clear | Tension releases |
| Past → Future | Warm/Sepia → Cool/Electric | Evolution |
| Local → Global | Earthy → Airy | Expansion |
| Doubt → Confidence | Desaturated → Saturated | Clarity emerges |

### Transition Techniques

- **Gradient blend**: Smooth flow between sections
- **Hard cut**: Dramatic shift at narrative turning points
- **Shared element**: Color carried through via a consistent element

---

## Accessibility Requirements

### Contrast Ratios (WCAG 2.1)

| Context | Minimum Ratio |
|---------|---------------|
| Body text (normal) | 4.5:1 |
| Large text (24px+ or 18px+ bold) | 3:1 |
| UI components, icons | 3:1 |
| AAA compliance (enhanced) | 7:1 |

### Testing

- Use WebAIM Contrast Checker
- Test with colorblind simulators (Coblis, Stark)
- View in grayscale to verify hierarchy

### Never Rely on Color Alone

Always pair color with:
- Text labels
- Icons or symbols
- Patterns or textures (for charts)
- Position or size

---

## Background Color Principles

### Light Backgrounds (Default for Trust)

- **Pure white** can feel harsh; consider very slight warmth or gray
- **Off-white** reduces eye strain for reading
- **Light neutrals** work for cards and sections

### Dark Backgrounds (Use Purposefully)

- Creates drama and emphasis
- Good for: testimonials, hero sections, CTAs
- Requires careful contrast management for text
- Can reduce perceived trustworthiness in finance/business contexts

### Background + Content Relationship

- Quiet backgrounds → Loud content
- Bold backgrounds → Simple content
- Busy backgrounds → Avoid (compete with content)

---

## Color Shift Patterns

### Between Pages/Sections

Each major section can have its own color identity while maintaining cohesion:

1. **Shared primary**: Same primary color throughout, backgrounds shift
2. **Temperature shift**: Warm → Cool or vice versa
3. **Value shift**: Light → Dark for progression/emphasis

### Within Sections (Scroll-Linked)

Color can evolve as user scrolls:

- Use for long-form storytelling
- Keep transitions smooth (interpolate)
- Ensure text remains readable throughout

---

## Anti-Patterns to Avoid

| Pattern | Why It Fails |
|---------|--------------|
| Purple + cyan gradients | Overused AI aesthetic, signals "generic" |
| Neon on dark backgrounds | Unprofessional, hard to read |
| Rainbow palettes | Chaotic, accessibility nightmare |
| Pure black (#000) text | Too harsh, use near-black instead |
| Same saturation everywhere | Creates visual monotony |
| Copying colors without context | May not suit your content/audience |
| Ignoring brand colors | Misses opportunity for authenticity |
| Color without meaning | Decoration without purpose |

---

## Decision Checklist

Before finalizing your palette:

- [ ] Does it match the content's emotional tone?
- [ ] Does it suit the audience and domain?
- [ ] Have I checked for brand/industry context?
- [ ] Do all text/background combinations meet contrast ratios?
- [ ] Is the palette colorblind-accessible?
- [ ] Does each color serve a functional purpose?
- [ ] Are semantic colors (success/error) universally understood?
- [ ] Is the hierarchy clear (what's most important is most prominent)?
