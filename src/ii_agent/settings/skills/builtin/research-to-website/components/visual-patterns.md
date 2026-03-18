# Visual Patterns

Image-driven scroll patterns for immersive storytelling. These patterns enhance aesthetics and create narrative flow through strategic image placement and animation.

## Domain Availability

| Pattern | Art-Creative | Business | Academic | Data | Government |
|---------|:------------:|:--------:|:--------:|:----:|:----------:|
| Story Flip | ✓ | - | - | - | - |
| Background Section | ✓ | ✓ | - | - | - |
| Zoom Reveal | ✓ | ✓ | - | ✓ | - |
| Panoramic Divider | ✓ | ✓ | ✓ | ✓ | - |
| Image Morph/Sequence | ✓ | - | - | - | - |
| Clip-path Reveal | ✓ | ✓ | - | ✓ | - |
| Split-Screen Scroll | ✓ | ✓ | ✓ | ✓ | - |
| Horizontal Gallery | ✓ | ✓ | - | - | - |
| Parallax Depth Layers | ✓ | - | - | - | - |

---

## Full-Viewport Patterns

### Story Flip (Page Takeover)

**Domains**: art-creative-storytelling only

Image scales to fill the entire viewport as user scrolls, creating a "chapter break" or "page turn" moment. The content pauses while the image dominates the screen before transitioning to the next section.

- **Behavior**: Image pins to viewport, scales from partial to full-bleed, holds, then releases
- **Purpose**: Major narrative transitions, chapter breaks, dramatic emphasis
- **Image Specs**: Landscape 16:9 or 3:2, minimum 1920x1080
- **Implementation**: GSAP ScrollTrigger with pin + scale transform
- **Duration**: 100-150vh scroll distance for full effect

**When to Use**:
- Transitioning between major topics or themes
- Introducing a new "chapter" in the narrative
- Maximum 2-3 times per page to maintain impact

---

### Background Section

**Domains**: art-creative-storytelling, business-financial

Full-bleed image as section background with text content overlaid. Creates continuous visual immersion beyond just the hero area.

- **Behavior**: Image remains fixed or subtle parallax while text scrolls over it
- **Purpose**: Atmospheric sections, quote highlights, key message emphasis
- **Image Specs**: Landscape, minimum 1920x1080, should work with text overlay
- **Implementation**: CSS background-attachment: fixed or GSAP parallax
- **Overlay Required**: Gradient or semi-transparent overlay for text readability

**Overlay Rules**:
- Dark images: Use light text with subtle dark gradient from text area
- Light images: Use dark text with subtle light gradient from text area
- Gradient direction: From the side where text appears (e.g., left-to-transparent if text is left-aligned)

**When to Use**:
- Key quotes or statistics that deserve visual emphasis
- Mood-setting transitions between content blocks
- Sections that benefit from environmental context

---

### Zoom Reveal

**Domains**: art-creative-storytelling, business-financial, data-analytics

Image starts zoomed in on a detail, then pulls back to reveal the full context as user scrolls. Creates a detail-to-big-picture narrative arc.

- **Behavior**: Image begins at 150-200% scale focused on a detail, animates to 100% showing full image
- **Purpose**: Reveal context, show scale, detail-to-overview storytelling
- **Image Specs**: High resolution required (minimum 2560x1440) to maintain quality when zoomed
- **Implementation**: GSAP ScrollTrigger with scale transform, transform-origin set to focal point

**When to Use**:
- Revealing the full scope of a topic after introducing a detail
- Data visualizations that benefit from progressive disclosure
- Products or subjects where detail matters

---

## Transition Patterns

### Panoramic Divider

**Domains**: art-creative-storytelling, business-financial, academic-technical, data-analytics

Wide, horizontal-crop image that spans full viewport width, acting as a visual divider between sections. Combined with fade effect for smooth transitions.

- **Behavior**: Image fades in as user scrolls into view, provides visual breathing room
- **Purpose**: Section transitions, topic shifts, visual pacing
- **Image Specs**: Panoramic aspect ratio (3:1, 4:1, or wider), minimum 1920px width, 300-600px height
- **Implementation**: CSS or Framer Motion fade-in on scroll intersection

**When to Use**:
- Between major content sections
- Topic or theme transitions
- Creating visual rhythm in long-scroll pages

---

### Image Morph/Sequence

**Domains**: art-creative-storytelling only

Multiple images cross-fade or morph into each other as user scrolls, creating a seamless visual transformation.

- **Behavior**: Images blend/transition based on scroll position, one morphing into the next
- **Purpose**: Show evolution, transformation, passage of time, before/after
- **Image Specs**: All images in sequence must share same dimensions and similar composition for smooth morph
- **Implementation**: GSAP ScrollTrigger with opacity crossfade or CSS blend transitions

**When to Use**:
- Showing change over time (historical, seasonal, developmental)
- Before/after comparisons with emotional impact
- Visual metaphors for transformation

---

### Clip-path Reveal

**Domains**: art-creative-storytelling, business-financial, data-analytics

Image reveals progressively through an animated mask/clip-path as user scrolls. Creates dramatic unveiling effect.

- **Behavior**: Image is masked, clip-path animates to reveal more of the image on scroll
- **Purpose**: Dramatic reveals, progressive disclosure, building anticipation
- **Image Specs**: Standard landscape, minimum 1920x1080
- **Implementation**: CSS clip-path with GSAP animation, common shapes: circle expand, horizontal wipe, diagonal reveal

**Clip-path Variations**:
- Circle expand: Starts from center point, expands outward
- Horizontal wipe: Reveals left-to-right or right-to-left
- Diagonal: Corner-to-corner reveal
- Custom shape: Brand or theme-relevant shapes

**When to Use**:
- Revealing key findings or conclusions
- Data visualization dramatic reveals
- Building suspense before important content

---

## Layout Patterns

### Split-Screen Scroll

**Domains**: art-creative-storytelling, business-financial, academic-technical, data-analytics

Screen divided vertically with image on one side and text on the other. Each side can scroll independently or at different rates.

- **Behavior**: Image pins while text scrolls, or both scroll at different speeds
- **Purpose**: Comparisons, dual narratives, maintaining visual context while reading
- **Image Specs**: Portrait or square aspect ratios work best, minimum 1080px on shortest side
- **Implementation**: CSS sticky positioning or GSAP ScrollTrigger pin on image column

**Variations**:
- Image pins, text scrolls: Image stays fixed while multiple text blocks scroll past
- Alternating sides: Image switches left/right between sections
- Both scroll, different speeds: Subtle parallax between columns

**When to Use**:
- Extended explanations that benefit from persistent visual reference
- Comparisons or contrasting viewpoints
- Step-by-step processes with visual documentation

---

### Horizontal Gallery

**Domains**: art-creative-storytelling, business-financial

Horizontal scrolling image gallery embedded within vertical page scroll. Creates a "carousel" moment without pagination.

- **Behavior**: Vertical scroll translates to horizontal movement within the gallery section
- **Purpose**: Photo essays, product showcases, timeline visualization
- **Image Specs**: Consistent aspect ratio across all images in gallery, minimum 800px height
- **Implementation**: GSAP ScrollTrigger with horizontal scroll translation, or CSS scroll-snap

**When to Use**:
- Showcasing multiple related images (products, portfolio, team)
- Timeline or chronological content
- Breaking up vertical scroll monotony

---

### Parallax Depth Layers

**Domains**: art-creative-storytelling only

Multiple image layers moving at different scroll speeds, creating depth and dimensional atmosphere.

- **Behavior**: Background layers scroll slower than foreground, creating 3D-like depth effect
- **Purpose**: Atmosphere, environmental storytelling, immersive mood
- **Image Specs**: Layered images (background, midground, foreground), PNGs with transparency for foreground elements
- **Implementation**: GSAP or Framer Motion with varying scroll speed multipliers per layer

**Layer Configuration**:
- Background: 0.3x scroll speed (moves slowest)
- Midground: 0.6x scroll speed
- Foreground: 1x or 1.2x scroll speed (moves fastest)

**When to Use**:
- Nature or landscape storytelling
- Creating immersive environmental mood
- Artistic or editorial content that benefits from depth

---

## General Guidelines

### Image Quality Requirements

All patterns require high-quality source images:
- Minimum resolution based on pattern specs
- Properly compressed for web (WebP preferred, JPEG fallback)
- Downloaded to local storage, never remote URLs in production

### Pattern Frequency

Avoid overusing dramatic patterns:
- **Story Flip**: Maximum 2-3 per page
- **Parallax Depth**: 1-2 sections per page
- **Clip-path Reveal**: 2-4 per page
- **Lighter patterns** (Panoramic Divider, Split-Screen): Can use more freely

### Combining Patterns

Patterns can be combined within a single page, but avoid:
- Two heavy patterns in adjacent sections
- Mixing too many different animation styles
- Using the same pattern more than 3 times consecutively

Recommended flow example:
```
Hero → Content → Panoramic Divider → Split-Screen → Story Flip → Content → Zoom Reveal → Conclusion
```
