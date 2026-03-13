# Assets And Animation

## Sprite Generation

Generate assets locally with the `generate_image` tool. Do not download third-party sprites or link external asset URLs.

### Required Tool Usage

- Use `generate_image` for every sprite sheet. Do not hand-wave asset creation.
- Save the generated files directly into `assets/images/` with explicit names such as `player-spritesheet.png`, `enemy-spritesheet.png`, or `items-spritesheet.png`.
- If the output is a single character illustration, a collage with touching poses, or a sheet without transparency, regenerate with a stricter prompt. Do not proceed to extraction until the sheet is usable.
- Be explicit about the number of poses and the sheet layout. Vague prompts often produce poster art instead of a real sprite sheet.
- Ask for the full strip in one request instead of generating tiny frame edits one by one. Full-strip generation is much better for character consistency.

### Full-Strip Prompting

When the animation extends an existing character, tell the model exactly how the strip should be laid out and what must stay unchanged:

- State the intended use, such as production spritesheet review or candidate game asset generation.
- If you already have a shipped idle frame, require that frame 1 remains the exact starting pose or the exact provided anchor image.
- Specify one row, exact frame count, exact slot size, and total canvas size.
- Repeat the character identity constraints: same silhouette family, same facing direction, same outfit colors, same body proportions, same readable face.
- Add negative constraints aggressively: no collage, no poster layout, no labels, no UI, no extra characters, no scenery, no floor, no glow, no haze, no blurry details, no shadows outside the sprite contour.

### Character Or Enemy Sheets

Generate one sprite sheet per animated entity with `generate_image`. Use prompts shaped like:

```text
sprite sheet with transparent background, PNG, showing the SAME character in multiple poses/states arranged in a single horizontal row with LARGE padding/gaps between each pose, no overlapping, no touching between poses, consistent art style across all poses
```

Stronger prompt template:

```text
[art style], side-view full-body [character description], game sprite sheet with transparent background, PNG, showing the SAME character in these exact states arranged in a single horizontal row: idle, run-1, run-2, run-3, jump, fall, attack. VERY LARGE padding/gaps between poses, no overlapping, no touching, each pose fully visible, consistent scale and lighting across all poses, clean silhouette, centered composition, no text, no UI, no background scene.
```

Example:

```text
bright polished 2D platformer art, side-view full-body fox knight adventurer, game sprite sheet with transparent background, PNG, showing the SAME character in these exact states arranged in a single horizontal row: idle, run-1, run-2, run-3, jump, fall, attack. VERY LARGE padding/gaps between poses, no overlapping, no touching, each pose fully visible, consistent scale and lighting across all poses, clean silhouette, centered composition, no text, no UI, no background scene.
```

Reference-aware prompt template for existing characters:

```text
Intended use: candidate production spritesheet for a 2D side-view [game genre] [animation name] review. Edit the provided transparent reference-canvas image into a single horizontal [frame count]-frame [animation name] spritesheet. The existing sprite in the leftmost slot is the exact shipped starting frame and must remain the starting frame for this sequence: same [character description], same facing direction, same outfit colors, same readable face, same proportions, same silhouette family. Composition: keep the image transparent, keep exactly one row of [frame count] equal [slot width]x[slot height] frame slots laid out left to right across the [canvas width]x[canvas height] canvas, centered vertically, no overlap between frame slots, no extra characters, no labels, no UI. Action: frame 1 stays the calm starting pose, frames 2 through [frame count] show [animation action description]. Keep body size, head size, and outfit proportions consistent across all frames. Style: authentic [pixel style] pixel art, crisp pixel clusters, stepped shading, restrained palette, production game asset, not concept art. Constraints: no scenery, no floor, no glow, no atmospheric haze, no impact effects, no shadows outside the sprite contours, no collage, no poster layout, no blurry details. Keep wide transparent empty space outside the frame slots.
```

Minimum states:

- `idle`
- `run` or `walk` with 2 to 4 frames
- `jump`
- `fall`
- `attack` when relevant
- `hurt` when relevant
- `death` when relevant

Use a large output size such as `2048x1024` or `2048x2048`.

### Static Asset Sheets

Generate one grid sheet for items, tiles, pickups, or HUD art with `generate_image`. Use prompts shaped like:

```text
sprite sheet with transparent background, PNG, each asset clearly separated with LARGE padding/gaps between them, arranged in a well-spaced grid layout, no overlapping, no touching between assets
```

Example contents: coin, heart, gem, platform tile, key.

Stronger prompt template:

```text
[art style] game asset sprite sheet with transparent background, PNG, containing these isolated assets arranged in a clean grid: [asset list]. VERY LARGE padding/gaps between assets, no overlapping, no touching, consistent scale, consistent lighting, each asset centered in its own space, no text, no UI, no background scene.
```

Example:

```text
bright polished 2D platformer art, game asset sprite sheet with transparent background, PNG, containing these isolated assets arranged in a clean grid: coin, heart pickup, blue gem, grass platform tile, silver key. VERY LARGE padding/gaps between assets, no overlapping, no touching, consistent scale, consistent lighting, each asset centered in its own space, no text, no UI, no background scene.
```

### Generation Checklist

Before moving to extraction, verify that the generated image:

- is a real sprite sheet, not splash art
- has a transparent background or a background that can be cleanly removed
- has clear separation between every frame or item
- preserves one consistent art style and camera angle
- includes every required state you asked for

## Extraction Workflow

Use `./scripts/extract_sprites.py` instead of manual crops. The script is designed around the workflow from `mobile_prompts.md`:

1. Remove edge-connected background colors sampled from the image corners.
2. Remove large near-white or near-black edge-connected background regions.
3. Build a foreground mask from alpha.
4. Dilate slightly to bridge tiny gaps inside a single sprite.
5. Label connected components.
6. Crop each component, zero out pixels outside the mask, trim transparency, and save PNG files.
7. Optionally normalize output canvases so animation frames match size.

Example commands:

```bash
python ./scripts/extract_sprites.py \
  --input assets/images/player-spritesheet.png \
  --output-dir assets/images/player \
  --names player-idle,player-run-1,player-run-2,player-run-3,player-jump,player-fall \
  --layout row \
  --normalize
```

```bash
python ./scripts/extract_sprites.py \
  --input assets/images/items-spritesheet.png \
  --output-dir assets/images/items \
  --names coin-gold,heart,platform-grass,key \
  --layout grid
```

If the extracted images still contain neighbor noise, reduce `--bg-threshold` or increase `--min-area` and rerun.

## Normalization Workflow

Raw strips are usually not game-ready even after extraction. Normalize them into standard frame canvases with one shared scale and one shared anchor:

1. Detect the extracted frame components.
2. Compute one global scale for the whole strip, not one scale per frame.
3. Pad each frame into a shared transparent canvas such as `64x64`.
4. If the animation extends an existing shipped character, optionally lock frame 01 to the exact in-game idle anchor instead of a regenerated version.

Use `./scripts/normalize_animation_frames.py` for this step:

```bash
python ./scripts/normalize_animation_frames.py \
  --input-dir assets/images/player-hurt-raw \
  --output-dir assets/images/player-hurt \
  --canvas-width 64 \
  --canvas-height 64 \
  --anchor-image assets/images/player-idle/frame-01.png \
  --lock-first-frame
```

Normalization rules:

- Use one global scale for the whole strip.
- Let tall or wide poses consume more of the frame instead of shrinking that pose alone.
- Use padding and a shared anchor, not per-frame rescaling.
- When the first frame must match the exact shipped idle sprite, replace normalized frame 01 with that anchor image.

Common failure mode:

- If a sword-up attack or another tall pose makes only that frame look smaller, you scaled frames independently. Re-run normalization with one shared scale and shared anchor placement.

## Naming

Use lowercase hyphenated names:

- `player-idle.png`
- `player-run-1.png`
- `player-jump.png`
- `enemy-slime-hurt.png`
- `coin-gold.png`

## Animation State Mapping

Map animation state from gameplay state:

- `velocity.x != 0` and grounded: run
- `velocity.x == 0` and grounded: idle
- `velocity.y < 0`: jump
- `velocity.y > 0` and not grounded: fall
- damage window active: hurt

Flip horizontal direction in code instead of generating left-facing duplicates:

```tsx
style={{ transform: [{ scaleX: facingLeft ? -1 : 1 }] }}
```

Example animation table:

```tsx
const playerAnimations = {
  idle: [require("./assets/images/player-idle.png")],
  run: [
    require("./assets/images/player-run-1.png"),
    require("./assets/images/player-run-2.png"),
    require("./assets/images/player-run-3.png"),
  ],
  jump: [require("./assets/images/player-jump.png")],
  fall: [require("./assets/images/player-fall.png")],
};
```

Use short frame durations for locomotion and longer durations for idle or impact frames. Normalize frame sizes before wiring the animation controller or the sprite will appear to jump between frames.
