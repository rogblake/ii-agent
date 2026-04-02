# Marketing & Creative Domain

Animation-rich, visually dynamic, story-driven design for campaigns, brand content, and creative presentations.

## Design Philosophy

Experience over information. Design should:
- Create emotional connection through visual storytelling
- Use motion as a narrative device
- Break conventional grid layouts intentionally
- Make every scroll feel like a reveal

---

## Color Strategy

### Principle: Color as Narrative

Unlike data-driven domains that use consistent palettes, creative content uses **color as a storytelling device**. Colors should shift to match the emotional arc of the content.

### Color Selection Framework

When choosing colors, reason through these questions:

1. **What is the emotional arc of this content?**
   - Beginning → Middle → End = What feelings should each evoke?
   - Tension → Resolution? Mystery → Revelation? Doubt → Confidence?

2. **What is the subject matter?**
   - Nature/Environment → Draw from natural palettes (earth, sky, ocean, forest)
   - Technology/Innovation → Consider cooler, more electric tones
   - Human/Emotional → Warmer, more organic palettes
   - Luxury/Premium → Deep, rich, or refined neutral tones

3. **What cultural/industry context applies?**
   - Research the brand, industry, or topic for color associations
   - Consider cultural meanings of colors for the target audience

4. **What mood should dominate?**
   - Energetic → Higher saturation, warmer temperatures
   - Calm → Lower saturation, cooler or neutral temperatures
   - Serious → Deeper values, less saturation
   - Playful → Brighter values, more saturation variety

### Color Temperature Journeys

Design the page as a **temperature journey** that reinforces the narrative:

| Narrative Arc | Temperature Flow | Effect |
|---------------|------------------|--------|
| Problem → Solution | Cool/Muted → Warm/Clear | Tension releases into resolution |
| Past → Future | Warm/Sepia → Cool/Electric | Nostalgia transforms to innovation |
| Local → Global | Earthy/Grounded → Airy/Expansive | Intimate becomes universal |
| Doubt → Confidence | Desaturated → Saturated | Uncertainty crystallizes to clarity |
| Unknown → Known | Dark → Light | Mystery reveals to understanding |

### Palette Relationships

Instead of fixed colors, think in **relationships**:

- **Background ↔ Text**: Ensure sufficient contrast (light bg = dark text, or inverse)
- **Primary ↔ Accent**: Primary carries the mood; accent creates moments of emphasis
- **Section ↔ Section**: Adjacent sections should have intentional contrast or flow
- **Warm ↔ Cool**: Use temperature shifts to create visual "chapters"

### Color Harmony Approaches

Choose a harmony strategy based on content:

| Strategy | When to Use | How It Works |
|----------|-------------|--------------|
| **Monochromatic** | Sophisticated, focused content | One hue, vary lightness/saturation |
| **Analogous** | Harmonious, flowing narratives | Adjacent hues on color wheel |
| **Complementary** | High-impact, contrast-driven | Opposite hues (use sparingly) |
| **Split-complementary** | Dynamic but balanced | One hue + two adjacent to its complement |
| **Triadic** | Energetic, playful content | Three equidistant hues |

---

## Background Systems

Backgrounds are **narrative architecture**. Each background choice reinforces the story's emotional arc.

### Background Types

| Type | Use Case | Emotional Effect |
|------|----------|------------------|
| **Solid Color** | Breathing room, text-heavy sections | Calm, focused |
| **Gradient** | Transitions, hero sections | Energy, progression |
| **Image (Full-bleed)** | Hero, immersive moments | Impact, atmosphere |
| **Image (Partial)** | Asymmetric layouts | Sophistication, editorial |
| **Pattern/Texture** | Brand personality | Craft, uniqueness |
| **Video** | Maximum impact (use sparingly) | Cinematic, premium |

---

### 1. Image Backgrounds

#### When to Use Images

- **Hero sections**: Establish mood and context immediately
- **Transitional moments**: Bridge between conceptual sections
- **Proof points**: Show real-world application or results
- **Emotional peaks**: Amplify key moments in the narrative

#### Image + Overlay Principles

Always ensure text readability over images:
- Use gradient overlays (dark-to-transparent or light-to-transparent)
- Position text over less busy areas of the image
- Consider the image's natural light direction for overlay placement

```tsx
// Structure for image background with overlay
<section className="relative min-h-screen">
  {/* Background Image Layer */}
  <div className="absolute inset-0 bg-cover bg-center bg-no-repeat" />

  {/* Overlay Layer - adjust opacity based on image brightness */}
  <div className="absolute inset-0 bg-gradient-to-b from-black/60 via-black/40 to-black/80" />

  {/* Content Layer */}
  <div className="relative z-10">{content}</div>
</section>
```

#### Parallax Image Background

Creates depth and premium feel. Background moves slower than foreground content.

```tsx
const ParallaxBackground = ({ image, children }) => {
  const { scrollY } = useScroll()
  const y = useTransform(scrollY, [0, 1000], [0, -300])

  return (
    <section className="relative h-screen overflow-hidden">
      <motion.div
        className="absolute inset-0 scale-110"
        style={{ y, backgroundImage: `url(${image})`, backgroundSize: 'cover' }}
      />
      <div className="absolute inset-0 bg-black/30" />
      <div className="relative z-10">{children}</div>
    </section>
  )
}
```

#### Split Layouts: Image + Color

Pair a full-height image with a colored content area. Choose the color based on:
- Dominant colors in the image (complementary or analogous)
- The emotional tone of the section's content
- The overall page color journey

```tsx
<section className="grid grid-cols-1 lg:grid-cols-2 min-h-screen">
  <div className="bg-cover bg-center min-h-[50vh] lg:min-h-screen" />
  <div className="flex items-center p-12 lg:p-24" style={{ backgroundColor: derivedColor }}>
    {content}
  </div>
</section>
```

---

### 2. Multi-Color Page Journeys

Design the **entire page** as an emotional color journey.

#### Journey Design Process

1. **Map the narrative**: Identify the story arc (e.g., Problem → Discovery → Solution → CTA)
2. **Assign emotional tones**: What feeling should each section evoke?
3. **Translate to color temperatures**: Match feelings to warm/cool, light/dark, saturated/muted
4. **Create transitions**: Design how colors flow from section to section

#### Transition Techniques

**Gradient Blend**: Sections blend smoothly via a gradient buffer zone
```tsx
<div className="h-32 bg-gradient-to-b from-[currentSectionColor] to-[nextSectionColor]" />
```

**Hard Cut with Contrast**: Dramatic shift for emphasis (use at narrative turning points)

**Shared Element**: An element (line, shape, image) bridges both color zones

#### Section-by-Section Reasoning

| Section Purpose | Color Approach | Reasoning |
|-----------------|----------------|-----------|
| **Opening/Hook** | Bold, attention-grabbing | Must stop the scroll, create intrigue |
| **Problem/Tension** | Muted, cooler, or darker | Reflect the discomfort of the status quo |
| **Discovery/Turning Point** | Transitional warmth | Hope emerges, energy shifts |
| **Solution/Product** | Clear, confident, fresh | Resolution feels like relief |
| **Social Proof** | Contrasting (often darker) | Creates emphasis, drama |
| **Vision/Future** | Aspirational, elevated | Forward momentum, possibility |
| **CTA** | High contrast, decisive | Demands action, no ambiguity |

---

### 3. Within-Page Color Shifts

Colors can shift **as the user scrolls** within a single section, creating immersive, dynamic experiences.

#### When to Use Scroll-Linked Color

- Long-form storytelling sections
- Timeline or journey visualizations
- Progressive reveals (building understanding step-by-step)
- Mood evolution within a single concept

#### Implementation Pattern

```tsx
const ScrollColorSection = () => {
  const ref = useRef(null)
  const { scrollYProgress } = useScroll({ target: ref })

  // Define color stops based on narrative arc
  const backgroundColor = useTransform(
    scrollYProgress,
    [0, 0.5, 1],
    [startColor, midColor, endColor] // Reason about these based on content
  )

  return (
    <motion.section ref={ref} style={{ backgroundColor }} className="min-h-[300vh]">
      <div className="sticky top-0 h-screen flex items-center justify-center">
        {/* Content that persists while background evolves */}
      </div>
    </motion.section>
  )
}
```

#### Color Interpolation Guidelines

- **3 stops minimum**: Start, middle, end (avoids abrupt midpoint)
- **Related hues**: Keep stops within a logical family unless the narrative demands contrast
- **Test the journey**: Scroll through at various speeds to ensure it feels intentional

---

### 4. Gradient Backgrounds

#### Gradient Types by Purpose

| Type | Effect | Best For |
|------|--------|----------|
| **Linear** | Directional energy | Hero sections, CTAs |
| **Radial** | Focus/spotlight | Highlighting central content |
| **Conic** | Dynamic, unusual | Experimental/artistic sections |
| **Mesh** | Organic, premium | Brand-forward, luxury content |

#### Animated Gradients

Subtle movement adds life without distraction. Keep animation slow (10-20s cycle).

```css
.animated-gradient {
  background-size: 400% 400%;
  animation: gradient-shift 15s ease infinite;
}

@keyframes gradient-shift {
  0% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
  100% { background-position: 0% 50%; }
}
```

#### Mesh Gradients

Layer multiple radial gradients at different positions for an organic, flowing effect. Choose colors that:
- Share a temperature (all warm, all cool, or intentional contrast)
- Support the section's emotional tone
- Don't compete with content for attention

---

### 5. Texture & Pattern Backgrounds

#### Noise/Grain Overlay

Adds tactile quality and reduces the "flat digital" feel. Keep opacity low (10-20%).

```tsx
<div className="absolute inset-0 opacity-[0.15] pointer-events-none grain-texture" />
```

#### Geometric Patterns

- **Dots**: Subtle, professional, works at small scales
- **Lines**: Directional energy, can guide the eye
- **Shapes**: More distinctive, use for brand personality

Pattern color should be subtle—same hue as background, slightly different value.

---

### 6. Image + Color Combinations

#### Color Wash Over Image

Apply a semi-transparent color layer with `mix-blend-mode: multiply` to unify an image with your palette.

#### Duotone Treatment

Convert image to grayscale, then apply a two-color gradient overlay. Creates cohesive, branded imagery from any photo.

#### Reasoning for Overlay Color

- **Brand color**: Reinforces identity
- **Section color**: Creates visual continuity
- **Complementary to subject**: Makes subject pop
- **Narrative color**: Supports the story (e.g., warm for hopeful moments)

---

### Background Strategy Summary

| Section | Background Choice | Reasoning |
|---------|-------------------|-----------|
| **Hero** | Image + overlay OR bold gradient | Maximum first impression |
| **Introduction** | Warm solid color | Welcoming, readable |
| **Problem** | Muted/cooler tones | Creates productive tension |
| **Solution** | Fresh, clear colors | Resolution, relief |
| **Data/Stats** | Light, neutral | Clarity, focus on content |
| **Testimonials** | Contrasting section (often darker) | Drama, emphasis |
| **Vision** | Gradient or color shift | Forward momentum |
| **CTA** | High contrast, bold | Decisive, action-driving |

---

## Typography

### Font Pairing Principles

For creative content, typography should have **personality**. Consider:

1. **Display vs. Body contrast**: Distinctive display font + readable body font
2. **Serif + Sans pairing**: Classic contrast that creates hierarchy
3. **Weight variation**: Use extreme weights (thin + bold) for drama
4. **Match the mood**: Elegant serif for sophistication, geometric sans for modern, humanist for warmth

### Type as Visual Element

```css
/* Hero Headlines - Oversized, impactful */
.hero-text {
  font-size: clamp(3rem, 10vw, 8rem);
  font-weight: 800;
  line-height: 0.95;
  letter-spacing: -0.03em;
}

/* Pull Quotes - Statement pieces */
.pull-quote {
  font-size: clamp(2rem, 5vw, 4rem);
  font-style: italic;
  font-weight: 300;
}
```

---

## Layout Patterns

### Full-Bleed Hero

Content breaks free of containers. Image or color extends edge-to-edge.

```
┌─────────────────────────────────────────────────────────────┐
│░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░│
│░░░░░░░░░░  BOLD STATEMENT                   ░░░░░░░░░░░░░░░░│
│░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░│
│                                          [Scroll Indicator] │
└─────────────────────────────────────────────────────────────┘
```

### Asymmetric Grid

Break the expected symmetry. Large elements paired with small. Creates editorial sophistication.

### Scrollytelling Section

Content pins in place while surrounding context changes. Perfect for:
- Multi-step explanations
- Before/after comparisons
- Data that evolves over time

```tsx
<section className="relative h-[300vh]">
  <div className="sticky top-0 h-screen flex items-center">
    {/* Sticky content */}
  </div>
  {/* Scroll triggers that change the sticky content */}
</section>
```

---

## Animation Patterns

### Text Reveals

Words or characters animate in sequence. Creates anticipation and guides reading.

```typescript
// Stagger words into view
{words.map((word, i) => (
  <motion.span
    initial={{ opacity: 0, y: 40 }}
    whileInView={{ opacity: 1, y: 0 }}
    transition={{ delay: i * 0.08 }}
  />
))}
```

### Image Reveals

- **Mask reveal**: Image reveals through expanding shape (clip-path animation)
- **Scale reveal**: Image starts zoomed in, scales to normal
- **Fade + parallax**: Fades in while moving slightly

### Page Transitions

- **Color flood**: Background color expands from a point (circle, edge)
- **Crossfade**: Smooth opacity blend between sections
- **Slide**: Content slides in from edges

---

## Interactive Elements

### Hover Effects

- **Cards**: Subtle lift (y: -4 to -8px) + shadow deepening
- **Images**: Slight scale (1.02-1.05) + overlay change
- **Buttons**: Color shift + scale

### Scroll Behaviors

Use **Lenis** or similar for smooth, refined scrolling:

```typescript
const lenis = new Lenis({
  duration: 1.2,
  easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
  smoothWheel: true,
})
```

---

## Content Flow

1. **Hook** — Dramatic visual + provocative statement
2. **Context** — Set the scene (parallax section)
3. **Journey** — Scrollytelling narrative
4. **Proof** — Testimonials, results (animated reveals)
5. **Vision** — Future-looking statement
6. **Call to Action** — Clear, compelling next step

---

## Image Strategy

### Purpose-Driven Selection

Every image must earn its place:
- **Atmospheric**: Sets mood, evokes feeling
- **Illustrative**: Explains a concept visually
- **Proof**: Shows real results, real people, real products
- **Textural**: Adds visual richness without competing with content

### Image Treatments

- **Duotone**: Unifies disparate images under one palette
- **Grain overlay**: Adds tactile, analog quality
- **Color wash**: Tints image to match section palette
- **Blur/vignette**: Creates depth, focuses attention

---

## Don'ts

- Static, grid-locked layouts throughout
- Stock photography without treatment
- Walls of text without visual breaks
- Same animation repeated everywhere
- Animations that block content access
- Ignoring performance on mobile
- Using colors without reasoning about the narrative
- Defaulting to "safe" palettes without considering the content
