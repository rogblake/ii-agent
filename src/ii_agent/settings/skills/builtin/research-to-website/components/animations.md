# Animation System

Premium scroll-based animations for high-impact storytelling. Designed for fundraising-grade presentations where every interaction builds credibility and emotional momentum.

## Philosophy

Animations are not decoration — they are **narrative devices**. Each animation should:
- Guide attention to key insights
- Create "aha moments" at critical data reveals
- Build emotional momentum toward calls-to-action
- Establish credibility through polish and intentionality

## Animation Library

### 1. Scroll-Triggered Reveals

#### Fade + Rise (Trust Builder)
```typescript
// Elements rise from below with opacity fade
// Use for: Key statistics, testimonials, team sections
const fadeRise = {
  initial: { opacity: 0, y: 60 },
  whileInView: { opacity: 1, y: 0 },
  transition: { duration: 0.8, ease: [0.22, 1, 0.36, 1] }
}
```

#### Stagger Cascade (Data Sequences)
```typescript
// Multiple elements animate in sequence
// Use for: Metric grids, feature lists, timeline items
const staggerContainer = {
  whileInView: { transition: { staggerChildren: 0.12 } }
}
const staggerItem = {
  initial: { opacity: 0, y: 40 },
  whileInView: { opacity: 1, y: 0 },
  transition: { duration: 0.6, ease: "easeOut" }
}
```

#### Scale Pop (Emphasis Moments)
```typescript
// Element scales from 0.8 to 1 with slight overshoot
// Use for: Hero numbers, key achievements, logos
const scalePop = {
  initial: { opacity: 0, scale: 0.8 },
  whileInView: { opacity: 1, scale: 1 },
  transition: {
    duration: 0.5,
    ease: [0.34, 1.56, 0.64, 1] // Overshoot easing
  }
}
```

### 2. Number Animations (Fundraising Essential)

#### Count-Up Animation
```typescript
// Animated number counting for metrics
// Use for: Revenue, users, growth %, funding amounts
import { useSpring, animated } from '@react-spring/web'

const AnimatedNumber = ({ value, prefix = "", suffix = "" }) => {
  const { number } = useSpring({
    from: { number: 0 },
    to: { number: value },
    delay: 200,
    config: { mass: 1, tension: 20, friction: 10 }
  })

  return (
    <animated.span>
      {number.to(n => `${prefix}${n.toFixed(0).toLocaleString()}${suffix}`)}
    </animated.span>
  )
}
```

#### Odometer Style (High-Value Numbers)
```typescript
// Rolling digit animation for large numbers
// Use for: Funding rounds, valuations, ARR
// Library: react-countup or custom digit roller

<CountUp
  start={0}
  end={12500000}
  duration={2.5}
  separator=","
  prefix="$"
  useEasing={true}
  easingFn={(t, b, c, d) => c * (1 - Math.pow(2, -10 * t / d)) + b}
/>
```

### 3. Chart Animations (Data Storytelling)

#### Progressive Line Draw
```typescript
// Line charts that draw themselves
// Use for: Growth trends, timeline data
// Creates "journey" narrative

// Recharts example
<LineChart>
  <Line
    dataKey="value"
    strokeDasharray="2000"
    strokeDashoffset="2000"
    style={{
      animation: "drawLine 2s ease-out forwards"
    }}
  />
</LineChart>

// CSS
@keyframes drawLine {
  to { stroke-dashoffset: 0; }
}
```

#### Bar Chart Grow
```typescript
// Bars grow from zero
// Use for: Comparisons, category breakdowns
<BarChart>
  <Bar dataKey="value">
    {data.map((entry, index) => (
      <Cell
        key={index}
        style={{
          animation: `growBar 0.8s ease-out ${index * 0.1}s forwards`,
          transform: 'scaleY(0)',
          transformOrigin: 'bottom'
        }}
      />
    ))}
  </Bar>
</BarChart>
```

#### Pie/Donut Reveal
```typescript
// Segments animate in sequence
// Use for: Market share, allocation breakdowns
// Start from 12 o'clock, sweep clockwise
```

### 4. Scroll-Linked Animations (Parallax)

#### Depth Layers
```typescript
// Background moves slower than foreground
// Creates depth and premium feel
// Use for: Hero sections, section transitions

// Using GSAP ScrollTrigger
gsap.to(".bg-layer", {
  yPercent: -30,
  ease: "none",
  scrollTrigger: {
    trigger: ".hero",
    start: "top top",
    end: "bottom top",
    scrub: true
  }
})
```

#### Progress-Linked Elements
```typescript
// Element transforms based on scroll position
// Use for: Sticky sections, morph animations

// Progress bar that fills as user scrolls
const scrollProgress = useScrollProgress()
<div
  className="h-1 bg-primary"
  style={{ width: `${scrollProgress * 100}%` }}
/>
```

#### Sticky Scroll Sections
```typescript
// Content pins while context changes around it
// Use for: Feature deep-dives, step-by-step explanations
// CRITICAL for complex data narratives

// Structure
<section className="relative h-[300vh]">
  <div className="sticky top-0 h-screen flex items-center">
    {/* Content that stays visible */}
    <AnimatedContent progress={scrollProgress} />
  </div>
</section>
```

### 5. Page & Section Transitions

#### Color Flood
```typescript
// Background color expands to fill screen
// Use for: Major section changes, mood shifts

// GSAP implementation
gsap.to(".section", {
  clipPath: "circle(150% at 50% 50%)",
  ease: "power2.inOut",
  duration: 1,
  scrollTrigger: { trigger: ".section", start: "top center" }
})
```

#### Crossfade Sections
```typescript
// Smooth opacity blend between sections
// Use for: Content-heavy transitions
<motion.section
  initial={{ opacity: 0 }}
  whileInView={{ opacity: 1 }}
  exit={{ opacity: 0 }}
  transition={{ duration: 0.6 }}
/>
```

### 6. Micro-Interactions

#### Hover States
```typescript
// Subtle feedback on interactive elements
// Cards: slight lift + shadow
// Buttons: scale 1.02 + color shift
// Links: underline draw animation

const cardHover = {
  rest: { y: 0, boxShadow: "0 4px 6px rgba(0,0,0,0.1)" },
  hover: {
    y: -4,
    boxShadow: "0 20px 25px rgba(0,0,0,0.15)",
    transition: { duration: 0.3, ease: "easeOut" }
  }
}
```

#### Loading States
```typescript
// Skeleton loaders for data
// Pulse animation for pending states
// Never show empty/broken UI
```

## Animation Patterns by Section

### Hero Section
- **Text**: Split-text animation (words or chars stagger in)
- **Numbers**: Count-up with 0.5s delay after text
- **Background**: Subtle parallax or gradient shift
- **CTA**: Gentle pulse or glow after 2s delay

### Metrics Grid
- **Container**: Fade in
- **Cards**: Stagger cascade (0.1s between each)
- **Numbers**: Count-up triggered when card is 50% visible
- **Labels**: Fade in 0.2s after number completes

### Charts Section
- **Chart**: Progressive reveal (draw/grow animations)
- **Legend**: Stagger in after chart completes
- **Annotations**: Pop in at specific data points
- **Insight callout**: Slide in from side after chart

### Timeline/Journey
- **Line**: Draw animation (SVG stroke)
- **Nodes**: Pop in as line reaches them
- **Content cards**: Alternate left/right fade-rise

### Team Section
- **Photos**: Scale pop with stagger
- **Names**: Fade in 0.1s after photo
- **Bio**: Reveal on hover/click

### CTA Section
- **Background**: Color flood or gradient shift
- **Headline**: Split-text animation
- **Button**: Delayed entrance + ambient glow

## Easing Reference

| Easing | Use Case |
|--------|----------|
| `[0.22, 1, 0.36, 1]` | Standard reveals (smooth decel) |
| `[0.34, 1.56, 0.64, 1]` | Emphasis moments (overshoot) |
| `[0.65, 0, 0.35, 1]` | Section transitions (smooth in/out) |
| `linear` | Scroll-linked only |
| `[0.16, 1, 0.3, 1]` | Quick micro-interactions |

## Performance Guidelines

1. **Use `will-change` sparingly** — only on elements about to animate
2. **Prefer `transform` and `opacity`** — GPU-accelerated properties
3. **Lazy-load heavy animations** — don't animate off-screen elements
4. **Respect `prefers-reduced-motion`** — provide static fallbacks
5. **Target 60fps** — test on mid-tier devices

```typescript
// Reduced motion fallback
const prefersReducedMotion = window.matchMedia(
  "(prefers-reduced-motion: reduce)"
).matches

const animation = prefersReducedMotion
  ? { opacity: 1 }
  : { opacity: 1, y: 0 }
```

## Implementation Libraries

| Library | Best For |
|---------|----------|
| **Framer Motion** | React components, gestures, layout animations |
| **GSAP + ScrollTrigger** | Complex scroll-linked, timeline sequences |
| **Lenis** | Smooth scroll foundation |
| **react-spring** | Physics-based, number animations |
| **react-countup** | Simple number counting |

## Fundraising-Specific Patterns

### The "Traction Reveal"
1. Show context (problem/market)
2. Pause (sticky section)
3. Animate key metrics one-by-one with count-up
4. Each metric gets a mini-celebration (subtle scale pop)
5. End with growth trajectory chart (line draws upward)

### The "Trust Builder"
1. Logos fade in with stagger
2. Testimonial cards slide in from alternating sides
3. Team photos pop in with warm hover states
4. Credentials/certifications fade in last (understated but present)

### The "Vision Cascade"
1. Current state (muted colors, static)
2. Transition animation (color flood to vibrant)
3. Future state animates in with energy
4. CTA pulses gently
